from flask import Flask, request, jsonify, session, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
import redis
import fnmatch
import datetime  # Added for timestamp
import json
try:
    # Upstash Redis client for Vercel KV
    from upstash_redis import Redis as UpstashRedis
except Exception:
    UpstashRedis = None



app = Flask(__name__)
# Secret key from env for security (required on Vercel)
app.secret_key = os.getenv('SECRET_KEY', os.urandom(24).hex())

# Configure CORS via env FRONTEND_ORIGIN (comma-separated). Defaults to local dev origins.
frontend_origins = os.getenv('FRONTEND_ORIGIN', '')
origins = [o.strip() for o in frontend_origins.split(',') if o.strip()] or ['http://127.0.0.1:5000', 'http://localhost:5000']
CORS(app, supports_credentials=True, origins=origins)

# Session cookie settings; secure by default on Vercel/production
app.config['SESSION_COOKIE_SAMESITE'] = os.getenv('SESSION_COOKIE_SAMESITE', 'Lax')
_secure_default = ('VERCEL' in os.environ) or (os.getenv('FLASK_ENV') == 'production')
app.config['SESSION_COOKIE_SECURE'] = os.getenv('SESSION_COOKIE_SECURE', '1' if _secure_default else '0').lower() in ('1', 'true', 'yes')

# Resolve upload root. On Vercel (read-only FS), default to /tmp unless UPLOAD_ROOT is provided.
UPLOAD_ROOT = os.getenv('UPLOAD_ROOT')
if (('VERCEL' in os.environ) or os.getenv('READONLY_FS') == '1') and not UPLOAD_ROOT:
    UPLOAD_ROOT = '/tmp'

UPLOAD_FOLDER = os.path.join(UPLOAD_ROOT, 'uploads') if UPLOAD_ROOT else 'uploads'
PDF_UPLOAD_FOLDER = os.path.join(UPLOAD_ROOT, 'uploads_pdf') if UPLOAD_ROOT else 'uploads_pdf'
DOCX_UPLOAD_FOLDER = os.path.join(UPLOAD_ROOT, 'uploads_docx') if UPLOAD_ROOT else 'uploads_docx'
AUDIO_UPLOAD_FOLDER = os.path.join(UPLOAD_ROOT, 'uploads_audio') if UPLOAD_ROOT else 'uploads_audio'
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv'}
ALLOWED_PDF_EXTENSIONS = {'pdf'} # Allowed extensions for PDFs
ALLOWED_DOCX_EXTENSIONS = {'docx'} # Allowed extensions for DOCX files
ALLOWED_AUDIO_EXTENSIONS = {'mp3', 'wav', 'ogg'} # Allowed extensions for Audio files
app.config['UPLOAD_ROOT'] = UPLOAD_ROOT
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PDF_UPLOAD_FOLDER'] = PDF_UPLOAD_FOLDER # Add to app config
app.config['DOCX_UPLOAD_FOLDER'] = DOCX_UPLOAD_FOLDER # Add to app config
app.config['AUDIO_UPLOAD_FOLDER'] = AUDIO_UPLOAD_FOLDER # Add to app config

class RedisAdapter:
    """Adapter to provide redis-py-like API for either Upstash (Vercel KV) or redis-py client."""
    def __init__(self, client, flavor: str):
        self.client = client
        self.flavor = flavor  # 'upstash' or 'redis'

    # Simple KV
    def ping(self):
        try:
            return self.client.ping()
        except Exception:
            # Fallback probe for Upstash REST if ping not supported
            try:
                self.client.set("__ping__", "1")
                return True
            except Exception:
                return False

    def get(self, key):
        return self.client.get(key)

    def set(self, key, value):
        return self.client.set(key, value)

    def exists(self, key):
        try:
            res = self.client.exists(key)
            # Upstash returns int; redis-py also returns int
            return bool(res)
        except Exception:
            return False

    def delete(self, key):
        try:
            return self.client.delete(key)
        except Exception:
            return 0

    # Hashes
    def hset(self, name, key, value=None):
        # Support both mapping and field/value forms for compatibility
        try:
            if value is None and isinstance(key, dict):
                return self.client.hset(name, key)
            return self.client.hset(name, key, value)
        except TypeError:
            # Upstash may prefer mapping
            return self.client.hset(name, {key: value})

    def hget(self, name, key):
        return self.client.hget(name, key)

    def hgetall(self, name):
        data = self.client.hgetall(name)
        if isinstance(data, dict):
            return data
        # Upstash may return a flat list [k1, v1, k2, v2, ...]
        if isinstance(data, list):
            it = iter(data)
            return {k: v for k, v in zip(it, it)}
        return {}

    def hdel(self, name, key):
        return self.client.hdel(name, key)

    def hkeys(self, name):
        try:
            keys = self.client.hkeys(name)
            if isinstance(keys, list):
                return keys
        except Exception:
            pass
        return list(self.hgetall(name).keys())

    # Scans/Keys
    def keys(self, pattern="*"):
        try:
            return self.client.keys(pattern)
        except Exception:
            # Attempt SCAN iteration if available
            try:
                cursor = 0
                out = []
                while True:
                    cursor, keys = self.client.scan(cursor=cursor, match=pattern, count=100)
                    out.extend(keys)
                    if cursor == 0:
                        break
                return out
            except Exception:
                # As a last resort (for limited in-memory fallback), return empty
                return []


class FallbackRedis:
    """Simple in-memory fallback; not for production."""
    def __init__(self):
        self.data = {'courses': json.dumps([])}

    def ping(self):
        return True

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value):
        self.data[key] = value
        return True

    def exists(self, key):
        return key in self.data

    def delete(self, key):
        return 1 if self.data.pop(key, None) is not None else 0

    def hset(self, hash_name, key, value=None):
        if hash_name not in self.data or not isinstance(self.data[hash_name], dict):
            self.data[hash_name] = {}
        if value is None and isinstance(key, dict):
            self.data[hash_name].update(key)
        else:
            self.data[hash_name][key] = value
        return True

    def hget(self, hash_name, key):
        if hash_name not in self.data or not isinstance(self.data[hash_name], dict):
            return None
        return self.data[hash_name].get(key)

    def hgetall(self, hash_name):
        if hash_name not in self.data or not isinstance(self.data[hash_name], dict):
            return {}
        return dict(self.data[hash_name])

    def hdel(self, hash_name, key):
        if hash_name in self.data and isinstance(self.data[hash_name], dict) and key in self.data[hash_name]:
            del self.data[hash_name][key]
            return 1
        return 0

    def hkeys(self, hash_name):
        return list(self.hgetall(hash_name).keys())

    def keys(self, pattern="*"):
        # Support glob patterns using fnmatch
        return [k for k in self.data.keys() if fnmatch.fnmatch(k, pattern)]


def create_kv_client():
    # Prefer Vercel KV (Upstash) if env vars are present
    kv_url = os.getenv('KV_REST_API_URL')
    kv_token = os.getenv('KV_REST_API_TOKEN')
    if kv_url and kv_token and UpstashRedis is not None:
        client = UpstashRedis(url=kv_url, token=kv_token)
        return RedisAdapter(client, 'upstash')

    # Fallback to local Redis for development
    host = os.getenv('REDIS_HOST', 'localhost')
    port = int(os.getenv('REDIS_PORT', '6379'))
    db = int(os.getenv('REDIS_DB', '0'))
    client = redis.Redis(host=host, port=port, db=db, decode_responses=True)
    return RedisAdapter(client, 'redis')


# Connect to KV/Redis with error handling
try:
    r = create_kv_client()
    if not r.ping():
        raise Exception('Ping failed')
    print("Connected to Vercel KV" if getattr(r, 'flavor', '') == 'upstash' else "Redis connection successful")

    # Initialize course key in store if it doesn't exist
    if not r.exists('courses'):
        r.set('courses', json.dumps([]))
        print("Initialized empty courses array in KV/Redis")
except Exception as _e:
    print(f"ERROR: Cannot connect to KV/Redis. Using in-memory fallback. Details: {_e}")
    r = FallbackRedis()

# Best-effort directory creation; on Vercel, only /tmp is writable.
for p in [UPLOAD_FOLDER, PDF_UPLOAD_FOLDER, DOCX_UPLOAD_FOLDER, AUDIO_UPLOAD_FOLDER]:
    try:
        os.makedirs(p, exist_ok=True)
    except Exception as e:
        print(f"WARNING: Unable to create directory {p}: {e}")

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_pdf_file(filename): # New function for PDF files
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_PDF_EXTENSIONS

def allowed_docx_file(filename): # New function for DOCX files
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_DOCX_EXTENSIONS



def allowed_audio_file(filename): # New function for Audio files
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_AUDIO_EXTENSIONS

 

# Auth endpoints
@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json(silent=True) or {}
        name = data.get('name')
        role = data.get('role')
        if not name or role not in ('instructor', 'student'):
            return jsonify({'success': False, 'message': 'Invalid credentials'}), 400

        session['name'] = name
        session['role'] = role
        return jsonify({'success': True, 'name': name, 'role': role})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/check_auth', methods=['GET'])
def check_auth():
    if 'name' in session and 'role' in session:
        return jsonify({'success': True, 'name': session['name'], 'role': session['role']})
    return jsonify({'success': False, 'message': 'Not authenticated'}), 401
@app.route('/api/upload_audio', methods=['POST']) # New endpoint for Audio uploads
def upload_audio():
    try:
        if session.get('role') != 'instructor':
            return jsonify({'success': False, 'message': 'Unauthorized - Please login as instructor'}), 403
        instructor_name = session.get('name')
        if not instructor_name:
            return jsonify({'success': False, 'message': 'Instructor name not found in session. Please login again.'}), 401

        course_id = request.form.get('courseId')
        if not course_id:
            return jsonify({'success': False, 'message': 'Course ID is required'}), 400

        if 'file' not in request.files:
            return jsonify({'success': False, 'message': 'No file part'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No selected file'}), 400

        if file and allowed_audio_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['AUDIO_UPLOAD_FOLDER'], filename)

            if os.path.exists(filepath):
                print(f"Audio file {filename} already exists, will overwrite")

            file.save(filepath)
            now = datetime.datetime.now().isoformat()
            audio_data = {
                'filetype': 'audio',
                'last_updated': now,
                'instructor_name': instructor_name,
                'course_id': course_id
            }
            r.hset('audio_files', filename, json.dumps(audio_data))
            return jsonify({'success': True, 'filename': filename, 'filetype': 'audio', 'last_updated': now, 'instructor_name': instructor_name, 'course_id': course_id})
        else:
            return jsonify({'success': False, 'message': 'Invalid file type, only MP3, WAV, OGG allowed'}), 400

    except Exception as e:
        print(f"Error in upload_audio: {str(e)}")
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500

@app.route('/api/videos', methods=['GET'])
def list_videos():
    videos_raw = r.hgetall('videos')
    videos_list = []

    current_role = session.get('role')
    current_instructor_name = session.get('name')
    course_id = request.args.get('courseId')  # Get course_id from query parameters

    for k, v_json in videos_raw.items():
        try:
            v_data = json.loads(v_json)  # Parse JSON string

            # Filter by course_id if provided
            if course_id and v_data.get('course_id') != course_id:
                continue

            video_item = {
                'filename': k,
                'filetype': v_data.get('filetype', 'video'),
                'last_updated': v_data.get('last_updated'),
                'instructor_name': v_data.get('instructor_name'), # Include instructor name
                'course_id': v_data.get('course_id', '')  # Include course_id with default empty string
            }

            # For multi-instructor collaboration: show all videos in a course to any instructor
            if current_role == 'instructor':
                videos_list.append(video_item)  # Show all videos to instructors
            else: # For students or other roles, show all videos
                videos_list.append(video_item)

        except json.JSONDecodeError:
            # Handle cases where data might not be a valid JSON (e.g., old data)
            # These videos won't have an instructor_name and won't show for specific instructors unless logic is added
            if current_role != 'instructor' and not course_id: # Only show to non-instructors if malformed and not filtering by course
                videos_list.append({'filename': k, 'filetype': 'unknown', 'last_updated': 'N/A', 'instructor_name': 'Unknown', 'course_id': ''})
    return jsonify(videos_list)

@app.route('/api/pdfs', methods=['GET']) # New endpoint to list PDFs
def list_pdfs():
    pdfs_raw = r.hgetall('pdfs')
    pdfs_list = []
    current_role = session.get('role')
    current_instructor_name = session.get('name')
    course_id = request.args.get('courseId')  # Get course_id from query parameters

    for k, v_json in pdfs_raw.items():
        try:
            v_data = json.loads(v_json)

            # Filter by course_id if provided
            if course_id and v_data.get('course_id') != course_id:
                continue

            pdf_item = {
                'filename': k,
                'filetype': v_data.get('filetype'),
                'last_updated': v_data.get('last_updated'),
                'instructor_name': v_data.get('instructor_name'),
                'course_id': v_data.get('course_id', '')  # Include course_id with default empty string
            }
            # For multi-instructor collaboration: show all PDFs in a course to any instructor
            if current_role == 'instructor':
                pdfs_list.append(pdf_item)  # Show all PDFs to instructors
            else: # For students or other roles, show all pdfs
                pdfs_list.append(pdf_item)
        except json.JSONDecodeError:
            if current_role != 'instructor' and not course_id:
                pdfs_list.append({'filename': k, 'filetype': 'unknown', 'last_updated': 'N/A', 'instructor_name': 'Unknown', 'course_id': ''})
    return jsonify(pdfs_list)

@app.route('/api/docx_files', methods=['GET']) # New endpoint to list DOCX files
def list_docx_files():
    docx_raw = r.hgetall('docx_files')
    docx_list = []
    current_role = session.get('role')
    current_instructor_name = session.get('name')
    course_id = request.args.get('courseId')  # Get course_id from query parameters

    for k, v_json in docx_raw.items():
        try:
            v_data = json.loads(v_json)

            # Filter by course_id if provided
            if course_id and v_data.get('course_id') != course_id:
                continue

            docx_item = {
                'filename': k,
                'filetype': v_data.get('filetype'),
                'last_updated': v_data.get('last_updated'),
                'instructor_name': v_data.get('instructor_name'),
                'course_id': v_data.get('course_id', '')  # Include course_id with default empty string
            }
            # For multi-instructor collaboration: show all DOCX files in a course to any instructor
            if current_role == 'instructor':
                docx_list.append(docx_item)  # Show all DOCX files to instructors
            else: # For students or other roles, show all docx files
                docx_list.append(docx_item)
        except json.JSONDecodeError:
            if current_role != 'instructor' and not course_id:
                docx_list.append({'filename': k, 'filetype': 'unknown', 'last_updated': 'N/A', 'instructor_name': 'Unknown', 'course_id': ''})
    return jsonify(docx_list)


@app.route('/api/audio_files', methods=['GET']) # New endpoint to list Audio files
def list_audio_files():
    audio_raw = r.hgetall('audio_files')
    audio_list = []
    current_role = session.get('role')
    current_instructor_name = session.get('name')
    course_id = request.args.get('courseId')  # Get course_id from query parameters

    for k, v_json in audio_raw.items():
        try:
            v_data = json.loads(v_json)

            # Filter by course_id if provided
            if course_id and v_data.get('course_id') != course_id:
                continue

            audio_item = {
                'filename': k,
                'filetype': v_data.get('filetype'),
                'last_updated': v_data.get('last_updated'),
                'instructor_name': v_data.get('instructor_name'),
                'course_id': v_data.get('course_id', '')  # Include course_id with default empty string
            }
            # For multi-instructor collaboration: show all audio files in a course to any instructor
            if current_role == 'instructor':
                audio_list.append(audio_item)  # Show all audio files to instructors
            else: # For students or other roles, show all audio files
                audio_list.append(audio_item)
        except json.JSONDecodeError:
            if current_role != 'instructor' and not course_id:
                audio_list.append({'filename': k, 'filetype': 'unknown', 'last_updated': 'N/A', 'instructor_name': 'Unknown', 'course_id': ''})
    return jsonify(audio_list)

@app.route('/api/video/<filename>', methods=['DELETE'])
def delete_video_file(filename):
    if session.get('role') != 'instructor':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    current_instructor_name = session.get('name')
    if not current_instructor_name:
        return jsonify({'success': False, 'message': 'Instructor name not found in session.'}), 401

    secure_name = secure_filename(filename)
    if not secure_name:
        return jsonify({'success': False, 'message': 'Invalid filename'}), 400

    video_json = r.hget('videos', secure_name)
    if not video_json:
        # If not in Redis, check filesystem and attempt to inform, but likely already gone or never tracked
        filepath_check = os.path.join(app.config['UPLOAD_FOLDER'], secure_name)
        if os.path.exists(filepath_check):
            # Potentially an untracked file, or Redis entry was lost.
            # For safety, don't delete if not owned, but it's not in Redis to check ownership.
            # Or, decide if instructors can delete any file in the folder if not tracked.
            # Current logic: if not in Redis, can't confirm ownership.
             return jsonify({'success': False, 'message': f'{secure_name} not found in database. Cannot confirm ownership.'}), 404
        return jsonify({'success': False, 'message': f'{secure_name} not found in database or filesystem.'}), 404

    try:
        video_data = json.loads(video_json)
        owner_instructor = video_data.get('instructor_name')

        if owner_instructor != current_instructor_name:
            return jsonify({'success': False, 'message': 'Unauthorized. You do not own this video.'}), 403

        filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_name)
        if os.path.exists(filepath):
            os.remove(filepath)

        result = r.hdel('videos', secure_name)
        if result > 0:
            return jsonify({'success': True, 'message': f'{secure_name} deleted successfully from database and filesystem (if present).'})
        else:
            # This implies the key, previously confirmed by r.hget, was not found by r.hdel.
            # This could be due to a rapid concurrent deletion or an unexpected Redis state change.
            fs_status_message = "File on filesystem might have been removed in this attempt."
            # Check current state of file, as os.remove might have been skipped if file didn't exist initially,
            # or it might have failed silently if not caught by the broader exception handler (unlikely).
            if os.path.exists(filepath):
                fs_status_message = "File on filesystem still exists."
            elif not os.path.exists(filepath) and not os.path.join(app.config['UPLOAD_FOLDER'], secure_name) == filepath :
                 # This condition is a bit complex, if filepath was already checked and os.remove was called
                 # we assume it was removed or failed (which would be an exception).
                 # This re-check is mostly for the message accuracy.
                 pass


            return jsonify({'success': False, 'message': f'Error: {secure_name} was not found in database for deletion, though it was expected. {fs_status_message}'}), 500

    except json.JSONDecodeError:
        return jsonify({'success': False, 'message': 'Error decoding video data from database.'}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/pdf/<filename>', methods=['DELETE']) # New endpoint to delete a PDF
def delete_pdf_file(filename):
    if session.get('role') != 'instructor':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    current_instructor_name = session.get('name')
    if not current_instructor_name:
        return jsonify({'success': False, 'message': 'Instructor name not found in session.'}), 401

    secure_name = secure_filename(filename)
    if not secure_name:
        return jsonify({'success': False, 'message': 'Invalid filename'}), 400

    pdf_json = r.hget('pdfs', secure_name)
    if not pdf_json:
        filepath_check = os.path.join(app.config['PDF_UPLOAD_FOLDER'], secure_name)
        if os.path.exists(filepath_check):
             return jsonify({'success': False, 'message': f'{secure_name} not found in database. Cannot confirm ownership.'}), 404
        return jsonify({'success': False, 'message': f'{secure_name} not found in database or filesystem.'}), 404
    try:
        pdf_data = json.loads(pdf_json)
        owner_instructor = pdf_data.get('instructor_name')

        if owner_instructor != current_instructor_name:
            return jsonify({'success': False, 'message': 'Unauthorized. You do not own this PDF.'}), 403

        filepath = os.path.join(app.config['PDF_UPLOAD_FOLDER'], secure_name)
        if os.path.exists(filepath):
            os.remove(filepath)

        result = r.hdel('pdfs', secure_name)
        if result > 0:
            return jsonify({'success': True, 'message': f'{secure_name} deleted successfully.'})
        else:
            # This case implies a race condition or unexpected Redis state.
            fs_status_message = "File on filesystem might have been removed."
            if os.path.exists(filepath):
                fs_status_message = "File on filesystem still exists."
            return jsonify({'success': False, 'message': f'Error: {secure_name} not found in database for deletion. {fs_status_message}'}), 500
    except json.JSONDecodeError:
        return jsonify({'success': False, 'message': 'Error decoding PDF data from database.'}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/docx/<filename>', methods=['DELETE']) # New endpoint to delete a DOCX file
def delete_docx_file(filename):
    if session.get('role') != 'instructor':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    current_instructor_name = session.get('name')
    if not current_instructor_name:
        return jsonify({'success': False, 'message': 'Instructor name not found in session.'}), 401

    secure_name = secure_filename(filename)
    if not secure_name:
        return jsonify({'success': False, 'message': 'Invalid filename'}), 400

    docx_json = r.hget('docx_files', secure_name)
    if not docx_json:
        filepath_check = os.path.join(app.config['DOCX_UPLOAD_FOLDER'], secure_name)
        if os.path.exists(filepath_check):
             return jsonify({'success': False, 'message': f'{secure_name} not found in database. Cannot confirm ownership.'}), 404
        return jsonify({'success': False, 'message': f'{secure_name} not found in database or filesystem.'}), 404
    try:
        docx_data = json.loads(docx_json)
        owner_instructor = docx_data.get('instructor_name')

        if owner_instructor != current_instructor_name:
            return jsonify({'success': False, 'message': 'Unauthorized. You do not own this DOCX file.'}), 403

        filepath = os.path.join(app.config['DOCX_UPLOAD_FOLDER'], secure_name)
        if os.path.exists(filepath):
            os.remove(filepath)

        result = r.hdel('docx_files', secure_name)
        if result > 0:
            return jsonify({'success': True, 'message': f'{secure_name} deleted successfully.'})
        else:
            # This case implies a race condition or unexpected Redis state.            fs_status_message = "File on filesystem might have been removed."
            if os.path.exists(filepath):
                fs_status_message = "File on filesystem still exists."
            return jsonify({'success': False, 'message': f'Error: {secure_name} not found in database for deletion. {fs_status_message}'}), 500
    except json.JSONDecodeError:
        return jsonify({'success': False, 'message': 'Error decoding DOCX data from database.'}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/audio/<filename>', methods=['DELETE']) # New endpoint to delete an Audio file
def delete_audio_file(filename):
    if session.get('role') != 'instructor':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    current_instructor_name = session.get('name')
    if not current_instructor_name:
        return jsonify({'success': False, 'message': 'Instructor name not found in session.'}), 401

    secure_name = secure_filename(filename)
    if not secure_name:
        return jsonify({'success': False, 'message': 'Invalid filename'}), 400

    audio_json = r.hget('audio_files', secure_name)
    if not audio_json:
        filepath_check = os.path.join(app.config['AUDIO_UPLOAD_FOLDER'], secure_name)
        if os.path.exists(filepath_check):
             return jsonify({'success': False, 'message': f'{secure_name} not found in database. Cannot confirm ownership.'}), 404
        return jsonify({'success': False, 'message': f'{secure_name} not found in database or filesystem.'}), 404
    try:
        audio_data = json.loads(audio_json)
        owner_instructor = audio_data.get('instructor_name')

        if owner_instructor != current_instructor_name:
            return jsonify({'success': False, 'message': 'Unauthorized. You do not own this Audio file.'}), 403

        filepath = os.path.join(app.config['AUDIO_UPLOAD_FOLDER'], secure_name)
        if os.path.exists(filepath):
            os.remove(filepath)

        result = r.hdel('audio_files', secure_name)
        if result > 0:
            return jsonify({'success': True, 'message': f'{secure_name} deleted successfully.'})
        else:
            # This case implies a race condition or unexpected Redis state.
            fs_status_message = "File on filesystem might have been removed."
            if os.path.exists(filepath):
                fs_status_message = "File on filesystem still exists."
            return jsonify({'success': False, 'message': f'Error: {secure_name} not found in database for deletion. {fs_status_message}'}), 500
    except json.JSONDecodeError:
        return jsonify({'success': False, 'message': 'Error decoding Audio data from database.'}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/get_session_info', methods=['GET'])
def get_session_info():
    print(f"Session check - Session data: {dict(session)}")  # Debug
    if 'name' in session and 'role' in session:
        return jsonify({'success': True, 'name': session['name'], 'role': session['role']})
    else:
        return jsonify({'success': False, 'message': 'No active session'}), 401

# This route is already defined above, removing duplicate
# @app.route('/api/check_auth', methods=['GET'])
# def check_auth():
#     """Check if user is authenticated and return session details"""
#     # Duplicate route removed to avoid conflicts

@app.route('/api/progress/<student>/<filename>', methods=['GET', 'POST'])
def progress(student, filename):
    key = f'progress:{student}:{filename}'
    if request.method == 'GET':
        progress = r.get(key) or 0
        return jsonify({'progress': float(progress)})
    else:
        data = request.json
        progress = data.get('progress', 0)
        r.set(key, progress)
        return jsonify({'success': True})

@app.route('/api/progress_pdf/<student>/<filename>', methods=['GET', 'POST']) # New endpoint for PDF progress
def pdf_progress(student, filename):
    # Key for storing current page and max percentage progress for a student and a PDF
    # e.g., progress_pdf:student_name:example.pdf -> {"currentPage": 5, "maxProgressPercent": 50}
    key = f'progress_pdf:{student}:{secure_filename(filename)}'
    if request.method == 'GET':
        progress_data_json = r.get(key)
        if progress_data_json:
            progress_data = json.loads(progress_data_json)
            return jsonify({
                'currentPage': int(progress_data.get('currentPage', 1)),
                'maxProgressPercent': float(progress_data.get('maxProgressPercent', 0))
            })
        return jsonify({'currentPage': 1, 'maxProgressPercent': 0}) # Default if no progress found
    else: # POST
        data = request.json
        current_page = data.get('currentPage')
        max_progress_percent = data.get('maxProgressPercent')
        if current_page is not None and max_progress_percent is not None:
            r.set(key, json.dumps({'currentPage': current_page, 'maxProgressPercent': max_progress_percent}))
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Missing currentPage or maxProgressPercent'}), 400

@app.route('/api/progress_docx/<student>/<filename>', methods=['GET', 'POST']) # New endpoint for DOCX progress
def docx_progress(student, filename):
    # Key for storing max percentage progress for a student and a DOCX file
    # e.g., progress_docx:student_name:example.docx -> {"maxProgressPercent": 50}
    key = f'progress_docx:{student}:{secure_filename(filename)}'
    if request.method == 'GET':
        progress_data_json = r.get(key)
        if progress_data_json:
            progress_data = json.loads(progress_data_json)
            return jsonify({
                'maxProgressPercent': float(progress_data.get('maxProgressPercent', 0))
            })
        return jsonify({'maxProgressPercent': 0}) # Default if no progress found
    else: # POST
        data = request.json
        max_progress_percent = data.get('maxProgressPercent')
        if max_progress_percent is not None:
            r.set(key, json.dumps({'maxProgressPercent': max_progress_percent}))
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Missing maxProgressPercent'}), 400




@app.route('/api/progress_audio/<student>/<filename>', methods=['GET', 'POST']) # New endpoint for Audio progress
def audio_progress(student, filename):
    key = f'progress_audio:{student}:{secure_filename(filename)}'
    if request.method == 'GET':
        progress = r.get(key) or 0
        return jsonify({'progress': float(progress)})
    else: # POST
        data = request.json
        progress = data.get('progress', 0)
        r.set(key, progress)
        return jsonify({'success': True})

@app.route('/uploads/<filename>')
def serve_video(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/uploads_pdf/<filename>') # New route to serve PDF files
def serve_pdf(filename):
    # The filename from the URL is already URL-decoded by Flask.
    # It should correspond to the filename stored on the disk (which was secured during upload).
    # No need to call secure_filename() again here.
    return send_from_directory(app.config['PDF_UPLOAD_FOLDER'], filename)

@app.route('/uploads_docx/<filename>') # New route to serve DOCX files
def serve_docx(filename):
    # The filename from the URL is already URL-decoded by Flask.
    # It should correspond to the filename stored on the disk (which was secured during upload).
    # No need to call secure_filename() again here.
    return send_from_directory(app.config['DOCX_UPLOAD_FOLDER'], filename)



@app.route('/uploads_audio/<filename>') # New route to serve Audio files
def serve_audio(filename):
    return send_from_directory(app.config['AUDIO_UPLOAD_FOLDER'], filename)


@app.route('/')
def root():
    return send_from_directory('.', 'login.html')

# Note: Keep specific routes BEFORE the catch-all route
@app.route('/<path:path>')
def static_proxy(path):
    if path == 'pdf_tracker.html': # Serve pdf_tracker.html
        return send_from_directory('.', 'pdf_tracker.html')
    if path == 'docx_tracker.html': # Serve docx_tracker.html
        return send_from_directory('.', 'docx_tracker.html')
    
    return send_from_directory('.', path)



@app.route('/api/courses', methods=['GET'])
def list_courses():
    """Retrieves all available courses"""
    courses_json = r.get('courses')
    if courses_json:
        courses = json.loads(courses_json)
    else:
        courses = []
        r.set('courses', json.dumps(courses))
    return jsonify(courses)

@app.route('/api/courses', methods=['POST'])
def create_course():
    """Creates a new course"""
    print(f"Create course request received - Session data: {dict(session)}")
    print(f"Request data: {request.json}")

    if session.get('role') != 'instructor':
        print(f"Create course authorization failed. Role in session: {session.get('role')}")
        return jsonify({'success': False, 'message': 'Unauthorized - Only instructors can create courses'}), 403

    instructor_name = session.get('name')
    if not instructor_name:
        print("Create course - Instructor name not found in session")
        return jsonify({'success': False, 'message': 'Instructor name not found in session'}), 401

    try:
        data = request.json
        if not data:
            print("Create course - No JSON data in request")
            return jsonify({'success': False, 'message': 'No data provided'}), 400

        course_name = data.get('courseName')

        if not course_name:
            print("Create course - No course name provided")
            return jsonify({'success': False, 'message': 'Course name is required'}), 400

        print(f"Creating course: {course_name} by instructor: {instructor_name}")

        # Get existing courses
        courses_json = r.get('courses')
        if courses_json:
            try:
                courses = json.loads(courses_json)
                print(f"Found existing courses: {len(courses)}")
            except json.JSONDecodeError:
                print("Error decoding courses JSON, resetting to empty array")
                courses = []
                r.set('courses', json.dumps([]))
        else:
            print("No courses found, initializing empty array")
            courses = []
            r.set('courses', json.dumps([]))

        # Check for duplicate course name
        for course in courses:
            if course.get('name') == course_name:
                print(f"Duplicate course name: {course_name}")
                return jsonify({'success': False, 'message': 'Course with this name already exists'}), 400

        # Create new course
        new_course = {
            'id': str(len(courses) + 1),  # Simple ID generation
            'name': course_name,
            'instructor': instructor_name,
            'created_at': datetime.datetime.now().isoformat()
        }

        courses.append(new_course)
        r.set('courses', json.dumps(courses))
        print(f"Course created successfully: {new_course}")

        return jsonify({'success': True, 'course': new_course})
    except Exception as e:
        print(f"Error creating course: {str(e)}")
        return jsonify({'success': False, 'message': f'Error creating course: {str(e)}'}), 500

@app.route('/api/courses/<course_id>', methods=['GET'])
def get_course(course_id):
    """Retrieve a specific course by ID"""
    courses_json = r.get('courses')
    if not courses_json:
        return jsonify({'success': False, 'message': 'Course not found'}), 404

    courses = json.loads(courses_json)
    for course in courses:
        if course.get('id') == course_id:
            return jsonify({'success': True, 'course': course})

    return jsonify({'success': False, 'message': 'Course not found'}), 404

@app.route('/api/courses/<course_id>', methods=['DELETE'])
def delete_course(course_id):
    """Deletes a course and all associated files"""
    if session.get('role') != 'instructor':
        return jsonify({'success': False, 'message': 'Unauthorized - Only instructors can delete courses'}), 403

    instructor_name = session.get('name')
    if not instructor_name:
        return jsonify({'success': False, 'message': 'Instructor name not found in session'}), 401

    try:
        # Get existing courses
        courses_json = r.get('courses')
        if not courses_json:
            return jsonify({'success': False, 'message': 'Course not found'}), 404

        courses = json.loads(courses_json)

        # Find the course
        course_index = None
        course_to_delete = None
        for i, course in enumerate(courses):
            if course.get('id') == course_id and course.get('instructor') == instructor_name:
                course_index = i
                course_to_delete = course
                break

        if course_index is None:
            return jsonify({'success': False, 'message': 'Course not found or you are not authorized to delete it'}), 404

        # Delete all files associated with this course
        deleted_files = []

        # For PDFs
        for pdf_key in r.hkeys('pdfs') or []:
            try:
                pdf_data = json.loads(r.hget('pdfs', pdf_key) or '{}')
                if pdf_data.get('course_id') == course_id:
                    # Delete file from filesystem
                    filepath = os.path.join(app.config['PDF_UPLOAD_FOLDER'], pdf_key)
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    # Remove from Redis
                    r.hdel('pdfs', pdf_key)
                    deleted_files.append(f"PDF: {pdf_key}")
            except (json.JSONDecodeError, Exception) as e:
                print(f"Error deleting PDF {pdf_key}: {str(e)}")

        # For DOCXs
        for docx_key in r.hkeys('docx_files') or []:
            try:
                docx_data = json.loads(r.hget('docx_files', docx_key) or '{}')
                if docx_data.get('course_id') == course_id:
                    # Delete file from filesystem
                    filepath = os.path.join(app.config['DOCX_UPLOAD_FOLDER'], docx_key)
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    # Remove from Redis
                    r.hdel('docx_files', docx_key)
                    deleted_files.append(f"DOCX: {docx_key}")
            except (json.JSONDecodeError, Exception) as e:
                print(f"Error deleting DOCX {docx_key}: {str(e)}")

        # For Videos
        for video_key in r.hkeys('videos') or []:
            try:
                video_data = json.loads(r.hget('videos', video_key) or '{}')
                if video_data.get('course_id') == course_id:
                    # Delete file from filesystem
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], video_key)
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    # Remove from Redis
                    r.hdel('videos', video_key)
                    deleted_files.append(f"Video: {video_key}")
            except (json.JSONDecodeError, Exception) as e:
                print(f"Error deleting Video {video_key}: {str(e)}")


        # For Audio files (MISSING IN ORIGINAL CODE - BUG FIX)
        for audio_key in r.hkeys('audio_files') or []:
            try:
                audio_data = json.loads(r.hget('audio_files', audio_key) or '{}')
                if audio_data.get('course_id') == course_id:
                    # Delete file from filesystem
                    filepath = os.path.join(app.config['AUDIO_UPLOAD_FOLDER'], audio_key)
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    # Remove from Redis
                    r.hdel('audio_files', audio_key)
                    deleted_files.append(f"Audio: {audio_key}")
            except (json.JSONDecodeError, Exception) as e:
                print(f"Error deleting Audio {audio_key}: {str(e)}")

        # Clean up progress tracking data for all deleted files (BUG FIX)
        progress_keys_deleted = []
        try:
            # Get all progress keys from Redis
            all_keys = r.keys('progress*')
            for key in all_keys:
                key_str = key.decode('utf-8') if isinstance(key, bytes) else key

                # Check if this progress key belongs to any of the deleted files
                for deleted_file in deleted_files:
                    _, filename = deleted_file.split(': ', 1)

                    # Check different progress key patterns
                    # Use secure_filename to match the pattern used in progress storage
                    secure_name = secure_filename(filename)
                    if (f':{secure_name}' in key_str and
                        ('progress:' in key_str or 'progress_pdf:' in key_str or
                         'progress_docx:' in key_str or 
                         'progress_audio:' in key_str)):

                        r.delete(key_str)
                        progress_keys_deleted.append(key_str)
                        break  # Found match, no need to check other files

        except Exception as e:
            print(f"Error cleaning up progress data: {str(e)}")

        # Remove the course
        courses.pop(course_index)

        # Save updated courses list
        r.set('courses', json.dumps(courses))

        # Log the deletion summary
        print(f"Course '{course_id}' deleted successfully:")
        print(f"  - Files deleted: {len(deleted_files)}")
        for file in deleted_files:
            print(f"    * {file}")
        print(f"  - Progress records cleaned: {len(progress_keys_deleted)}")

        return jsonify({
            'success': True,
            'message': f'Course and all associated files deleted successfully. Removed {len(deleted_files)} files and {len(progress_keys_deleted)} progress records.',
            'deleted_files_count': len(deleted_files),
            'deleted_progress_count': len(progress_keys_deleted)
        })
    except Exception as e:
        print(f"Error deleting course: {str(e)}")
        return jsonify({'success': False, 'message': f'Error deleting course: {str(e)}'}), 500



if __name__ == '__main__':
    app.run(debug=True)