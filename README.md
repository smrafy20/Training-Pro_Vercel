# Training PRO - Progress Tracker Dashboard

A comprehensive web-based learning management system that allows instructors to upload educational content and track student progress across multiple media formats.

## 🚀 Features

### 📚 Multi-Format Content Support
- **Video Files**: MP4, AVI, MOV, MKV with progress tracking
- **PDF Documents**: Interactive PDF viewer with page-by-page progress
- **PowerPoint Presentations**: PPT/PPTX files converted to images with slide navigation
- **Word Documents**: DOCX files with interactive document viewer
- **Audio Files**: MP3, WAV, OGG with playback progress tracking

### 👥 User Management
- **Role-based Authentication**: Separate interfaces for instructors and students
- **Session Management**: Secure login/logout with session persistence
- **User-specific Progress**: Individual progress tracking per student

### 🎓 Course Management
- **Course Creation**: Instructors can create and manage multiple courses
- **File Organization**: Content organized by courses for better structure
- **Course Statistics**: Real-time file count and progress analytics
- **Course Deletion**: Complete cleanup of courses and associated files

### 📊 Progress Tracking
- **Real-time Progress**: Automatic progress saving as students consume content
- **Resume Functionality**: Students can continue from where they left off
- **Progress Visualization**: Visual progress bars and percentage indicators
- **Reset Options**: Students can reset their progress if needed

### 🎨 Modern UI/UX
- **Responsive Design**: Works seamlessly on desktop and mobile devices
- **Professional Interface**: Clean, modern design with smooth animations
- **Intuitive Navigation**: Easy-to-use dashboards for both instructors and students
- **Interactive Controls**: Zoom, navigation, and playback controls for all media types

## 🛠️ Technology Stack

- **Backend**: Flask (Python web framework)
- **Database**: Redis (for session management and progress tracking)
- **Frontend**: HTML5, CSS3, JavaScript (ES6+)
- **File Processing**: 
  - PowerPoint conversion (win32com for Windows, LibreOffice for cross-platform)
  - PDF processing with pdf2image
  - Image processing with Pillow

## 📋 Prerequisites

### System Requirements
- Python 3.7 or higher
- Redis server
- LibreOffice (for PowerPoint conversion on Linux/macOS)

### For PowerPoint Conversion (Linux/macOS)
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install libreoffice poppler-utils

# macOS (using Homebrew)
brew install libreoffice poppler

# CentOS/RHEL/Fedora
sudo yum install libreoffice poppler-utils
# or for newer versions:
sudo dnf install libreoffice poppler-utils
```

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
git clone <https://github.com/smrafy20/Training-PRO.git>
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
├── ppt_tracker.html          # PowerPoint viewer interface
├── docx_tracker.html         # Word document viewer interface
├── audio_tracker.html        # Audio player interface
├── uploads/                   # Video files storage
├── uploads_pdf/              # PDF files storage
├── uploads_docx/             # Word documents storage
├── uploads_ppt/              # PowerPoint files storage
├── uploads_ppt_images/       # Converted PPT images
└── uploads_audio/            # Audio files storage
```

## 🎯 Usage

### For Instructors:
1. **Login**: Access the system with instructor credentials
2. **Create Course**: Set up new courses for content organization
3. **Upload Content**: Add videos, PDFs, presentations, documents, and audio files
4. **Monitor Progress**: Track student engagement and progress
5. **Manage Courses**: Edit or delete courses as needed

### For Students:
1. **Login**: Access with student credentials
2. **Browse Courses**: View available courses and content
3. **Consume Content**: Watch videos, read documents, view presentations
4. **Track Progress**: Monitor your learning progress across all materials
5. **Resume Learning**: Continue from where you left off

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




