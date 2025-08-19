from flask import Flask, request, jsonify, session, send_from_directory, redirect
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
import redis
import datetime
import json
# Optional Vercel Blob SDK (persistent storage). Guard import to avoid crashing if package is missing
# and be compatible with different SDK versions (delete vs del_blob).
try:
    import importlib
    vblob = importlib.import_module('vercel_blob')
    put = getattr(vblob, 'put', None)
    # Older SDKs exported `del_blob`, newer may export `delete`
    delete_blob = getattr(vblob, 'delete', None) or getattr(vblob, 'del_blob', None)
except Exception:
    put = None
    delete_blob = None

# Optional Upstash (Vercel KV) REST client
try:
    from upstash_redis import Redis as UpstashRedis
except Exception:
    UpstashRedis = None

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'a-super-secret-key-for-dev')

# Session cookie settings: make cookies secure on Vercel
if os.getenv('VERCEL'):
    # Vercel runs on HTTPS; allow cross-site usage when needed
    app.config.update(
        SESSION_COOKIE_SAMESITE='None',
        SESSION_COOKIE_SECURE=True,
    )
else:
    app.config.update(
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=False,
    )

# CORS: allow origins from env (comma-separated) or default to localhost for dev
_frontend_origins = os.getenv('FRONTEND_ORIGIN', '')
origins = [o.strip() for o in _frontend_origins.split(',') if o.strip()] or ['http://127.0.0.1:5000', 'http://localhost:5000']
CORS(app, supports_credentials=True, origins=origins)

# --- REDIS/KV CONNECTION ---
def create_kv_client():
    """
    Connection strategy:
    1) Prefer Vercel KV (Upstash REST) via KV_REST_API_URL/TOKEN or UPSTASH_REDIS_REST_URL/TOKEN
    2) Then try REDIS_URL / KV_URL (e.g., Upstash rediss:// URL)
    3) Fallback to local Redis (dev)
    """
    kv_url = os.getenv('KV_REST_API_URL') or os.getenv('UPSTASH_REDIS_REST_URL')
    kv_token = os.getenv('KV_REST_API_TOKEN') or os.getenv('UPSTASH_REDIS_REST_TOKEN')
    if kv_url and kv_token and UpstashRedis is not None:
        return UpstashRedis(url=kv_url, token=kv_token)

    redis_url = os.getenv('REDIS_URL') or os.getenv('KV_URL')
    if redis_url:
        return redis.from_url(redis_url, decode_responses=True)

    host = os.getenv('REDIS_HOST', 'localhost')
    port = int(os.getenv('REDIS_PORT', '6379'))
    db = int(os.getenv('REDIS_DB', '0'))
    return redis.Redis(host=host, port=port, db=db, decode_responses=True)

try:
    r = create_kv_client()
    # Not all clients support ping; attempt it, otherwise perform a simple write probe
    try:
        _ok = getattr(r, 'ping', lambda: True)()
        if _ok is False:
            raise Exception("Ping returned False")
    except Exception:
        if hasattr(r, 'set'):
            r.set('__ping__', '1')
    print("Connected to Vercel KV (Upstash)" if UpstashRedis and isinstance(r, UpstashRedis) else "Redis/KV connection successful")

    # Ensure 'courses' key exists
    try:
        current = r.get('courses')
        if not current:
            r.set('courses', json.dumps([]))
    except Exception:
        # Some clients may not support exists; set defensively
        r.set('courses', json.dumps([]))
except Exception as e:
    print(f"ERROR: Cannot connect to Redis/KV. {e}")
    r = None

# Allowed extensions
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv'}
ALLOWED_PDF_EXTENSIONS = {'pdf'}
ALLOWED_DOCX_EXTENSIONS = {'docx'}
ALLOWED_AUDIO_EXTENSIONS = {'mp3', 'wav', 'ogg'}

# --- AUTH AND SESSION ROUTES ---
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    name = data.get('name')
    role = data.get('role')
    if not name or role not in ['instructor', 'student']:
        return jsonify({'success': False, 'message': 'Invalid login'}), 400
    session['name'] = name
    session['role'] = role
    return jsonify({'success': True, 'role': role})

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out successfully'})

@app.route('/api/get_session_info', methods=['GET'])
def get_session_info():
    if 'name' in session and 'role' in session:
        return jsonify({'success': True, 'name': session['name'], 'role': session['role']})
    return jsonify({'success': False, 'message': 'No active session'}), 401

@app.route('/api/check_auth', methods=['GET'])
def check_auth():
    """Front-end convenience route: returns {authenticated, name, role}."""
    if 'name' in session and 'role' in session:
        return jsonify({'authenticated': True, 'name': session['name'], 'role': session['role']})
    return jsonify({'authenticated': False}), 401

# --- BLOB HELPERS ---
def _blob_put(pathname: str, body_bytes: bytes, content_type: str, token: str):
    """Upload bytes to Vercel Blob using a best-effort call compatible across SDK versions."""
    if not put:
        raise RuntimeError("Vercel Blob SDK not available. Install 'vercel-blob' and import must succeed.")
    last_err = None
    # Attempt 1: options dict (most common)
    try:
        return put(
            pathname,
            body_bytes,
            {
                "access": "public",
                "contentType": content_type or "application/octet-stream",
                "addRandomSuffix": True,
                "token": token,
            },
        )
    except Exception as e:
        last_err = e
    # Attempt 2: keyword args style
    try:
        return put(
            pathname,
            body_bytes,
            access="public",
            contentType=content_type or "application/octet-stream",
            addRandomSuffix=True,
            token=token,
        )
    except Exception as e:
        last_err = e
        raise last_err


def _blob_delete(target: str, token: str):
    """Delete a blob using url or pathname; support both options dict and kwarg token."""
    if not delete_blob:
        return False
    # Attempt 1: options dict
    try:
        delete_blob(target, {"token": token})
        return True
    except Exception:
        pass
    # Attempt 2: kwarg style
    try:
        delete_blob(target, token=token)
        return True
    except Exception:
        return False

# --- REWRITTEN UPLOAD ENDPOINTS ---
def handle_file_upload(file, course_id, file_type, allowed_extensions_check_func, redis_hash_name):
    if session.get('role') != 'instructor':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    instructor_name = session.get('name')
    if not file or file.filename == '' or not allowed_extensions_check_func(file.filename):
        return jsonify({'success': False, 'message': 'Invalid or no file selected'}), 400

    filename = secure_filename(file.filename)

    try:
        pathname = f"{course_id}/{filename}"

        # Ensure we have the Blob RW token and SDK available
        token = os.getenv('BLOB_READ_WRITE_TOKEN') or os.getenv('VERCEL_BLOB_RW_TOKEN')
        if not put or not token:
            raise RuntimeError("Vercel Blob not configured. Missing SDK import or BLOB_READ_WRITE_TOKEN")

        # Read file bytes for upload and include content type; add random suffix to avoid collisions
        file.stream.seek(0)
        body_bytes = file.stream.read()
        content_type = getattr(file, "mimetype", None) or "application/octet-stream"

        # Upload to Vercel Blob
        blob_result = _blob_put(pathname, body_bytes, content_type, token)

        # blob_result is typically a dict with url and pathname
        url = blob_result.get("url") if isinstance(blob_result, dict) else None
        if not url:
            # Some versions may return a string URL
            url = str(blob_result)

        now = datetime.datetime.now().isoformat()
        file_data = {
            'filetype': file_type,
            'last_updated': now,
            'instructor_name': instructor_name,
            'course_id': course_id,
            'url': url,
            'pathname': blob_result.get('pathname') if isinstance(blob_result, dict) else pathname
        }
        r.hset(redis_hash_name, filename, json.dumps(file_data))

        return jsonify({'success': True, 'filename': filename, 'filetype': file_type, 'url': url})

    except Exception as e:
        print(f"Error during Vercel Blob upload: {e}")
        return jsonify({'success': False, 'message': 'An error occurred while uploading the file.'}), 500

def is_allowed(filename, exts):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in exts

@app.route('/api/upload_pdf', methods=['POST'])
def upload_pdf():
    return handle_file_upload(request.files.get('file'), request.form.get('courseId'), 'pdf', lambda f: is_allowed(f, ALLOWED_PDF_EXTENSIONS), 'pdfs')

@app.route('/api/upload_docx', methods=['POST'])
def upload_docx():
    return handle_file_upload(request.files.get('file'), request.form.get('courseId'), 'docx', lambda f: is_allowed(f, ALLOWED_DOCX_EXTENSIONS), 'docx_files')

@app.route('/api/upload_audio', methods=['POST'])
def upload_audio():
    return handle_file_upload(request.files.get('file'), request.form.get('courseId'), 'audio', lambda f: is_allowed(f, ALLOWED_AUDIO_EXTENSIONS), 'audio_files')

@app.route('/api/upload', methods=['POST'])
def upload_video():
    return handle_file_upload(request.files.get('file'), request.form.get('courseId'), 'video', lambda f: is_allowed(f, ALLOWED_EXTENSIONS), 'videos')

# --- LISTING AND DELETING (Adjusted for new delete function) ---
def list_files_by_type(redis_hash_name):
    # (This function can remain the same as the last version)
    if not r:
        return jsonify([])
    files_raw = r.hgetall(redis_hash_name)
    files_list = []
    course_id = request.args.get('courseId')
    for k, v_json in files_raw.items():
        try:
            # This needs to be a complete dictionary for the frontend
            v_data = json.loads(v_json)
            v_data['filename'] = k # Ensure filename is part of the object
            if course_id and v_data.get('course_id') != course_id:
                continue
            files_list.append(v_data)
        except (json.JSONDecodeError, KeyError):
            continue
    return jsonify(files_list)

@app.route('/api/videos', methods=['GET'])
def list_videos(): return list_files_by_type('videos')

@app.route('/api/pdfs', methods=['GET'])
def list_pdfs(): return list_files_by_type('pdfs')

@app.route('/api/docx_files', methods=['GET'])
def list_docx_files(): return list_files_by_type('docx_files')

@app.route('/api/audio_files', methods=['GET'])
def list_audio_files(): return list_files_by_type('audio_files')

def delete_file_by_type(filename, redis_hash_name):
    if session.get('role') != 'instructor':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    file_json = r.hget(redis_hash_name, filename)
    if not file_json:
        return jsonify({'success': False, 'message': 'File not found'}), 404

    try:
        file_data = json.loads(file_json)

        # Attempt to delete from Vercel Blob if URL is present and SDK/token available
        try:
            token = os.getenv('BLOB_READ_WRITE_TOKEN') or os.getenv('VERCEL_BLOB_RW_TOKEN')
            target = file_data.get('pathname') or file_data.get('url')
            if token and target:
                _blob_delete(target, token)
        except Exception as _e:
            # Log but do not fail the API if remote delete fails; metadata will still be removed
            print(f"WARNING: Failed to delete from Vercel Blob: {_e}")

        # Remove metadata from KV/Redis
        r.hdel(redis_hash_name, filename)
        return jsonify({'success': True, 'message': 'File deleted'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/video/<filename>', methods=['DELETE'])
def delete_video(filename): return delete_file_by_type(filename, 'videos')

@app.route('/api/pdf/<filename>', methods=['DELETE'])
def delete_pdf(filename): return delete_file_by_type(filename, 'pdfs')

@app.route('/api/docx/<filename>', methods=['DELETE'])
def delete_docx(filename): return delete_file_by_type(filename, 'docx_files')

@app.route('/api/audio/<filename>', methods=['DELETE'])
def delete_audio(filename): return delete_file_by_type(filename, 'audio_files')

# ... (Keep all your other routes for courses, progress, etc.)
# --- ADD THE MISSING ROUTES BACK IN ---
@app.route('/api/progress/<student>/<filename>', methods=['GET', 'POST'])
def progress(student, filename):
    key = f'progress:{student}:{filename}'
    if request.method == 'GET':
        progress_val = r.get(key) or 0
        return jsonify({'progress': float(progress_val)})
    else:
        data = request.json
        progress_val = data.get('progress', 0)
        r.set(key, progress_val)
        return jsonify({'success': True})

@app.route('/api/progress_pdf/<student>/<filename>', methods=['GET', 'POST'])
def pdf_progress(student, filename):
    key = f'progress_pdf:{student}:{secure_filename(filename)}'
    if request.method == 'GET':
        progress_data_json = r.get(key)
        if progress_data_json:
            return jsonify(json.loads(progress_data_json))
        return jsonify({'currentPage': 1, 'maxProgressPercent': 0})
    else:
        data = request.json
        r.set(key, json.dumps(data))
        return jsonify({'success': True})

@app.route('/api/progress_docx/<student>/<filename>', methods=['GET', 'POST'])
def docx_progress(student, filename):
    key = f'progress_docx:{student}:{secure_filename(filename)}'
    if request.method == 'GET':
        progress_data_json = r.get(key)
        if progress_data_json:
            return jsonify(json.loads(progress_data_json))
        return jsonify({'maxProgressPercent': 0})
    else:
        data = request.json
        r.set(key, json.dumps(data))
        return jsonify({'success': True})

@app.route('/api/progress_audio/<student>/<filename>', methods=['GET', 'POST'])
def audio_progress(student, filename):
    key = f'progress_audio:{student}:{secure_filename(filename)}'
    if request.method == 'GET':
        progress_val = r.get(key) or 0
        return jsonify({'progress': float(progress_val)})
    else:
        data = request.json
        progress_val = data.get('progress', 0)
        r.set(key, progress_val)
        return jsonify({'success': True})

@app.route('/api/courses', methods=['GET', 'POST'])
def courses():
    if request.method == 'GET':
        courses_json = r.get('courses')
        return jsonify(json.loads(courses_json) if courses_json else [])

    if request.method == 'POST':
        if session.get('role') != 'instructor':
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403

        data = request.json
        course_name = data.get('courseName')
        instructor_name = session.get('name')

        if not course_name:
            return jsonify({'success': False, 'message': 'Course name required'}), 400

        courses_json = r.get('courses')
        courses = json.loads(courses_json) if courses_json else []

        if any(c['name'] == course_name for c in courses):
            return jsonify({'success': False, 'message': 'Course name already exists'}), 409

        new_course = {
            'id': str(len(courses) + 1),
            'name': course_name,
            'instructor': instructor_name,
            'created_at': datetime.datetime.now().isoformat()
        }
        courses.append(new_course)
        r.set('courses', json.dumps(courses))
        return jsonify({'success': True, 'course': new_course})

# --- Blob-aware redirects for legacy local file URLs ---
def _send_or_redirect_from_kv(hash_name: str, folder: str, filename: str):
    """
    If a Blob URL is stored in KV for this filename, 302-redirect to it.
    Otherwise, fall back to serving from local folder (useful in local dev).
    """
    try:
        if r:
            meta_json = r.hget(hash_name, filename)
            if meta_json:
                data = json.loads(meta_json)
                url = data.get("url") or data.get("blob_url")
                if url:
                    return redirect(url, code=302)
    except Exception as e:
        print(f"WARNING: redirect lookup failed for {hash_name}/{filename}: {e}")
    # Fallback for local/dev
    return send_from_directory(folder, filename)

@app.route('/uploads/<path:filename>')
def serve_video_blob_aware(filename):
    return _send_or_redirect_from_kv('videos', 'uploads', filename)

@app.route('/uploads_pdf/<path:filename>')
def serve_pdf_blob_aware(filename):
    return _send_or_redirect_from_kv('pdfs', 'uploads_pdf', filename)

@app.route('/uploads_docx/<path:filename>')
def serve_docx_blob_aware(filename):
    return _send_or_redirect_from_kv('docx_files', 'uploads_docx', filename)

@app.route('/uploads_audio/<path:filename>')
def serve_audio_blob_aware(filename):
    return _send_or_redirect_from_kv('audio_files', 'uploads_audio', filename)
# --- STATIC FILE & ROOT ROUTES ---
@app.route('/')
def root():
    return send_from_directory('.', 'login.html')

@app.route('/<path:path>')
def static_proxy(path):
    return send_from_directory('.', path)