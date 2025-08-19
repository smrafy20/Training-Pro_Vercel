from flask import Flask, request, jsonify, session, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
import redis
import datetime
import json
from vercel_blob import blob # Import the Vercel Blob library

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'a-super-secret-key-for-dev')
CORS(app, supports_credentials=True, origins=['http://127.0.0.1:5000', 'http://localhost:5000'])

# --- REDIS/KV CONNECTION ---
try:
    if 'KV_URL' in os.environ:
        r = redis.from_url(os.environ.get('KV_URL'), decode_responses=True)
    else:
        r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    r.ping()
    print("Redis/KV connection successful")
    if not r.exists('courses'):
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

# --- REWRITTEN UPLOAD ENDPOINTS ---
def handle_file_upload(file, course_id, file_type, allowed_extensions_check_func, redis_hash_name):
    if session.get('role') != 'instructor':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    instructor_name = session.get('name')
    if not file or file.filename == '' or not allowed_extensions_check_func(file.filename):
        return jsonify({'success': False, 'message': 'Invalid or no file selected'}), 400

    filename = secure_filename(file.filename)

    try:
        # Upload to Vercel Blob with a unique path per course
        pathname = f"{course_id}/{filename}"
        blob_result = blob.upload(pathname=pathname, body=file, options={'access': 'public'})

        # Save metadata to Redis/KV, including the public URL
        now = datetime.datetime.now().isoformat()
        file_data = {
            'filetype': file_type,
            'last_updated': now,
            'instructor_name': instructor_name,
            'course_id': course_id,
            'url': blob_result['url']
        }
        r.hset(redis_hash_name, filename, json.dumps(file_data))

        return jsonify({'success': True, 'filename': filename, 'filetype': file_type, 'url': blob_result['url']})

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

# --- REWRITTEN LISTING ENDPOINTS ---
def list_files_by_type(redis_hash_name):
    files_raw = r.hgetall(redis_hash_name)
    files_list = []
    course_id = request.args.get('courseId')
    for k, v_json in files_raw.items():
        try:
            v_data = json.loads(v_json)
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

# --- REWRITTEN DELETE ENDPOINTS ---
def delete_file_by_type(filename, redis_hash_name):
    if session.get('role') != 'instructor':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    file_json = r.hget(redis_hash_name, filename)
    if not file_json:
        return jsonify({'success': False, 'message': 'File not found'}), 404

    try:
        file_data = json.loads(file_json)
        if file_data.get('url'):
            blob.delete(file_data['url'])

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

# --- STATIC FILE & ROOT ROUTES ---
@app.route('/')
def root():
    return send_from_directory('.', 'login.html')

@app.route('/<path:path>')
def static_proxy(path):
    return send_from_directory('.', path)