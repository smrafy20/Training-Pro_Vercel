# Training PRO - Progress Tracker Dashboard

A comprehensive web-based learning management system that allows instructors to upload educational content and track student progress across multiple media formats.

## 🚀 Features

### 📚 Multi-Format Content Support
- Video Files: MP4, AVI, MOV, MKV with progress tracking
- PDF Documents: Interactive PDF viewer with page-by-page progress
- Word Documents: DOCX files with interactive document viewer
- Audio Files: MP3, WAV, OGG with playback progress tracking

### 👥 User Management
- Role-based Authentication: Separate interfaces for instructors and students
- Session Management: Secure login/logout with session persistence
- User-specific Progress: Individual progress tracking per student

### 🎓 Course Management
- Course Creation: Instructors can create and manage multiple courses
- File Organization: Content organized by courses for better structure
- Course Statistics: Real-time file count and progress analytics
- Course Deletion: Complete cleanup of courses and associated files

### 📊 Progress Tracking
- Real-time Progress: Automatic progress saving as students consume content
- Resume Functionality: Students can continue from where they left off
- Progress Visualization: Visual progress bars and percentage indicators
- Reset Options: Students can reset their progress if needed

### 🎨 Modern UI/UX
- Responsive Design: Works seamlessly on desktop and mobile devices
- Professional Interface: Clean, modern design with smooth animations
- Intuitive Navigation: Easy-to-use dashboards for both instructors and students
- Interactive Controls: Zoom, navigation, and playback controls for supported media types

## 🛠️ Technology Stack

- Backend: Flask (Python web framework)
- Database: Redis (local dev) or Vercel KV (Upstash) in production (for session management and progress tracking)
- Frontend: HTML5, CSS3, JavaScript (ES6+)
- File Processing:
  - PDF processing with pdf2image
  - Image processing with Pillow

## 📋 Prerequisites

### System Requirements
- Python 3.7 or higher
- Redis server

### Redis Installation

#### Ubuntu/Debian:
```bash
sudo apt-get update
sudo apt-get install redis-server
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

#### macOS:
```bash
brew install redis
brew services start redis
```

#### CentOS/RHEL/Fedora:
```bash
sudo yum install redis
# or for newer versions:
sudo dnf install redis

sudo systemctl start redis
sudo systemctl enable redis
```

## 🚀 Installation & Setup

### 1. Clone the Repository
```bash
git clone https://github.com/smrafy20/Training-PRO.git
```

### 2. Create Virtual Environment
```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On Linux/macOS:
source venv/bin/activate

# On Windows:
# venv\Scripts\activate
```

### 3. Install Python Dependencies
```bash
pip install -r requirements.txt
```

### 4. Verify Redis Connection
```bash
# Test Redis connection
redis-cli ping
# Should return: PONG
```

### 5. Run the Application
```bash
# Make sure Redis is running
sudo systemctl status redis-server  # Linux
brew services list | grep redis     # macOS

# Start the Flask application
python app.py
```

### 6. Access the Application
Open your web browser and navigate to:
```
http://localhost:5000
```

## 📁 Project Structure

```
Training-PRO/
├── app.py                      # Main Flask application
├── requirements.txt            # Python dependencies
├── modern-style.css           # Main stylesheet
├── login.html                 # Login page
├── instructor_dashboard.html  # Instructor main dashboard
├── student_dashboard.html     # Student main dashboard
├── instructor.html            # Course management interface
├── create_course.html         # Course creation page
├── index.html                 # Video player interface
├── pdf_tracker.html          # PDF viewer interface
├── docx_tracker.html         # Word document viewer interface
├── audio_tracker.html        # Audio player interface
├── uploads/                   # Video files storage
├── uploads_pdf/              # PDF files storage
├── uploads_docx/             # Word documents storage
└── uploads_audio/            # Audio files storage
```

## 🎯 Usage

### For Instructors:
1. Login: Access the system with instructor credentials
2. Create Course: Set up new courses for content organization
3. Upload Content: Add videos, PDFs, documents, and audio files
4. Monitor Progress: Track student engagement and progress
5. Manage Courses: Edit or delete courses as needed

### For Students:
1. Login: Access with student credentials
2. Browse Courses: View available courses and content
3. Consume Content: Watch videos, read documents, listen to audio
4. Track Progress: Monitor your learning progress across all materials
5. Resume Learning: Continue from where you left off

## 🔧 Configuration

### Environment Variables (Optional)
```bash
export FLASK_ENV=development    # For development mode
export FLASK_DEBUG=1           # Enable debug mode
export REDIS_HOST=localhost    # Redis server host
export REDIS_PORT=6379         # Redis server port
```

### Redis Configuration
The application uses Redis with default settings:
- Host: localhost
- Port: 6379
- Database: 0

## ☁️ Deploying to Vercel with Vercel KV

This project is ready to run on Vercel using Vercel KV (Upstash) instead of a self-hosted Redis. The backend runs as a Python Serverless Function and serves only API routes, while static assets are served directly by Vercel.

Key files involved:
- Backend app with KV auto-detection: [app.py](app.py)
- Vercel serverless entrypoint: [api/index.py](api/index.py:1)
- Vercel configuration and routing: [vercel.json](vercel.json:1)
- Vercel build artifacts ignored: [.gitignore](.gitignore:1)

### Environment Variables

Set these in Vercel Project Settings → Environment Variables:

- KV_REST_API_URL: Provided by Vercel KV integration
- KV_REST_API_TOKEN: Provided by Vercel KV integration
- SECRET_KEY: A long random string for Flask session signing
- FRONTEND_ORIGIN: Your site origin(s), comma-separated, e.g. https://your-app.vercel.app
- UPLOAD_ROOT (optional): Override upload root; defaults to /tmp on Vercel

How it works:
- The application detects Vercel KV if KV_REST_API_URL and KV_REST_API_TOKEN are present and uses Upstash client automatically via create_kv_client in [app.py](app.py:187).
- Otherwise it falls back to local Redis using REDIS_HOST/REDIS_PORT during local development.

### One-time Data Migration (Local Redis → Vercel KV)

Run locally before deploying (requires access to your existing Redis):

1) Install dependencies locally:
   pip install -r requirements.txt

2) Export your Upstash credentials as env vars in the same shell:
   export KV_REST_API_URL="https://...upstash.io"
   export KV_REST_API_TOKEN="xxxxxxxxxxxxxxxx"

3) Use this quick Python snippet to copy the keys you use in this app:
   python - <<'PY'
   import os, json, redis
   from upstash_redis import Redis as UpstashRedis

   # Local Redis
   r = redis.Redis(host=os.getenv("REDIS_HOST","localhost"),
                   port=int(os.getenv("REDIS_PORT","6379")),
                   db=int(os.getenv("REDIS_DB","0")),
                   decode_responses=True)

   # Vercel KV (Upstash)
   kv = UpstashRedis(url=os.environ["KV_REST_API_URL"], token=os.environ["KV_REST_API_TOKEN"])

   # Simple key
   for k in ["courses"]:
       val = r.get(k)
       if val is not None:
           kv.set(k, val)

   # Hashes
   for h in ["videos","pdfs","docx_files","audio_files"]:
       data = r.hgetall(h)
       if data:
           # Upstash supports mapping form for HSET
           kv.hset(h, data)

   # Progress keys (strings)
   for pattern in ["progress*","progress_pdf*","progress_docx*","progress_audio*"]:
       for key in r.scan_iter(match=pattern, count=100):
           val = r.get(key)
           if val is not None:
               kv.set(key, val)

   print("Migration completed.")
   PY

Notes:
- This only migrates the keys this application uses.
- If you added custom keys, extend the snippet with your patterns.

### Uploads and File Storage on Vercel

- Vercel serverless filesystem is read-only except for /tmp. The code already detects Vercel and writes to /tmp for uploads. See configuration near the top of [app.py](app.py:26).
- Files written to /tmp are ephemeral and not persisted across invocations. For production-grade storage, move media to an external store (e.g., Vercel Blob, S3, GCS) and save only metadata/URLs in KV.

### Routing on Vercel

- All static files are served directly by Vercel CDN.
- API routes are handled by the Flask app through the serverless entry point:
  - Rewrites configured in [vercel.json](vercel.json:1):
    - "/" → login.html
    - "/api/(.*)" → [api/index.py](api/index.py:1)

### CORS and Sessions

- CORS origins are set via FRONTEND_ORIGIN env var. Multiple origins can be provided (comma-separated).
- Flask sessions are signed cookies. Ensure SECRET_KEY is set in production so sessions remain valid across serverless invocations.
- Cookies are sent with Secure flag automatically when running on Vercel.

### Step-by-step Deploy on Vercel

1) Create a Vercel project and import this repository.
2) Add the “Vercel KV” integration to the project (Vercel → Storage → KV). This will inject KV_REST_API_URL and KV_REST_API_TOKEN env vars.
3) In Project Settings → Environment Variables, add:
   - SECRET_KEY
   - FRONTEND_ORIGIN (e.g., https://your-app.vercel.app)
   - (Optional) UPLOAD_ROOT if you want a custom writable root; otherwise /tmp is used on Vercel.
4) Run the “One-time Data Migration” locally to copy existing Redis data into Vercel KV (optional if you’re starting fresh).
5) Commit and deploy. Vercel will:
   - Serve all static files (HTML/CSS/JS) from the repository root.
   - Route /api/* to the Flask serverless function via [api/index.py](api/index.py:1).
6) After deploy completes, open your Vercel URL. The app should load login.html at the root, and API requests will route through /api.

Troubleshooting:
- If you see “Using in-memory fallback” in logs, make sure KV_REST_API_URL and KV_REST_API_TOKEN are set correctly and the upstash-redis dependency is installed (it is in [requirements.txt](requirements.txt:1)).
- CORS errors: set FRONTEND_ORIGIN to your deployed domain.
- Large file uploads will not persist in /tmp; use an external object storage for production media.
