# JW Library Sync Web Application

Flask web version of the JW Library backup merger.

## Quick Start

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run locally:**
   ```bash
   python app.py
   ```
   Then visit: http://localhost:5000

3. **Deploy to Python Anywhere:**
   - Upload all files to your Python Anywhere account
   - Set WSGI file to import from `run_web.py`
   - Install requirements via console: `pip3.10 install --user -r requirements.txt`

## Files Structure

- `app.py` - Main Flask web application
- `jwlibrarysync.py` - Core backup merging logic (modified for web use)
- `run_web.py` - WSGI startup script for deployment
- `templates/` - HTML templates for web interface
- `requirements.txt` - Python dependencies

## Features

- Web-based file upload interface
- Progress indication during processing
- Secure file handling with temporary storage
- Download merged backup files
- Error handling and user feedback
- Mobile-friendly responsive design

## Usage

1. Visit the web application
2. Upload source .jwlibrary file (data to merge FROM)
3. Upload destination .jwlibrary file (data to merge TO)  
4. Click "Merge Backups"
5. Download the merged result

The original desktop version (`jwlibrarysync.py`) still works independently for CLI usage.
