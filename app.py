import os
import tempfile
import threading
import time
import logging
import uuid
import json
from flask import Flask, render_template, request, send_file, flash, redirect, url_for, jsonify
from werkzeug.utils import secure_filename
from jwlibrarysync import JWLibrarySync, JWLibrarySyncError

app = Flask(__name__)
app.secret_key = 'jwlibrary-sync-secret-key'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size

# Configure Flask logging based on environment
def configure_app_logging():
    """Configure Flask and Werkzeug logging based on environment"""
    environment = os.getenv('ENVIRONMENT', 'development').lower()
    log_level_str = os.getenv('LOG_LEVEL', '').upper()
    
    if environment == 'production':
        # In production, reduce Flask/Werkzeug logging noise
        default_level = logging.WARNING
    else:
        # In development, show more information
        default_level = logging.INFO
        
    # Override with explicit LOG_LEVEL if provided
    if log_level_str:
        try:
            explicit_level = getattr(logging, log_level_str)
            default_level = explicit_level
        except AttributeError:
            pass  # Invalid log level, use defaults
    
    # Configure Flask's logger
    app.logger.setLevel(default_level)
    
    # Configure Werkzeug's logger (handles HTTP request logging)
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.setLevel(default_level)
    
    # In production, we want minimal console output
    if environment == 'production' and not log_level_str:
        # Remove default handlers and add a minimal one
        app.logger.handlers.clear()
        werkzeug_logger.handlers.clear()
        
        # Add a simple console handler for errors only
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.ERROR)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        
        app.logger.addHandler(console_handler)
        werkzeug_logger.addHandler(console_handler)

# Configure logging when module is imported
configure_app_logging()

def reconfigure_logging_for_production():
    """Force reconfiguration of all loggers for production - call this if logging was set up incorrectly"""
    # Force production environment
    os.environ['ENVIRONMENT'] = 'production'
    
    # Reconfigure Flask/Werkzeug logging
    configure_app_logging()
    
    # Reconfigure root logger to be quiet
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.WARNING)
    
    # Clear and add minimal handler to root logger
    root_logger.handlers.clear()
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.ERROR)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    print(f"Logging reconfigured for production. Environment: {os.getenv('ENVIRONMENT')}")

# If we detect we're still in development mode but should be in production, fix it
if __name__ != '__main__' and os.getenv('ENVIRONMENT', 'development').lower() != 'production':
    reconfigure_logging_for_production()

# Store generated files for cleanup
generated_files = {}
cleanup_lock = threading.Lock()

# Store job progress information
job_progress = {}
progress_lock = threading.Lock()

def cleanup_old_files():
    """Clean up files older than 1 hour and old jobs"""
    while True:
        current_time = time.time()
        
        # Clean up old files
        with cleanup_lock:
            files_to_remove = []
            for filepath, created_time in generated_files.items():
                if current_time - created_time > 3600:  # 1 hour
                    try:
                        if os.path.exists(filepath):
                            os.unlink(filepath)
                        files_to_remove.append(filepath)
                    except Exception:
                        pass  # Ignore cleanup errors
            
            for filepath in files_to_remove:
                generated_files.pop(filepath, None)
        
        # Clean up old jobs
        cleanup_old_jobs()
        
        time.sleep(300)  # Check every 5 minutes

def register_generated_file(filepath):
    """Register a file for cleanup"""
    with cleanup_lock:
        generated_files[filepath] = time.time()

def cleanup_file(filepath):
    """Immediately cleanup a specific file"""
    try:
        if os.path.exists(filepath):
            os.unlink(filepath)
        with cleanup_lock:
            generated_files.pop(filepath, None)
    except Exception:
        pass  # Ignore cleanup errors

def create_job(job_id):
    """Create a new job with initial progress"""
    with progress_lock:
        job_progress[job_id] = {
            'status': 'starting',
            'progress': 0,
            'message': 'Initializing...',
            'result_file': None,
            'error': None,
            'created_at': time.time()
        }

def update_job_progress(job_id, status=None, progress=None, message=None, result_file=None, error=None):
    """Update job progress"""
    with progress_lock:
        if job_id in job_progress:
            if status is not None:
                job_progress[job_id]['status'] = status
            if progress is not None:
                job_progress[job_id]['progress'] = progress
            if message is not None:
                job_progress[job_id]['message'] = message
            if result_file is not None:
                job_progress[job_id]['result_file'] = result_file
            if error is not None:
                job_progress[job_id]['error'] = error

def get_job_progress(job_id):
    """Get current job progress"""
    with progress_lock:
        return job_progress.get(job_id, None)

def cleanup_old_jobs():
    """Clean up job progress data older than 2 hours"""
    current_time = time.time()
    with progress_lock:
        jobs_to_remove = []
        for job_id, job_data in job_progress.items():
            if current_time - job_data['created_at'] > 7200:  # 2 hours
                jobs_to_remove.append(job_id)
        
        for job_id in jobs_to_remove:
            job_progress.pop(job_id, None)

class WebJWLibrarySync(JWLibrarySync):
    def __init__(self, job_id=None):
        # Create progress callback that updates job progress
        def progress_callback(progress=None, message=None):
            if job_id:
                update_job_progress(job_id, progress=progress, message=message)
        
        super().__init__(progress_callback=progress_callback)
        self.result_file = None
        self.job_id = job_id
    
    def process_files(self, source_file_path, dest_file_path):
        """Process files with progress reporting"""
        try:
            if self.job_id:
                update_job_progress(self.job_id, status='processing', progress=10, message='Extracting archive files...')
            
            self.logger.info("Processing JW Library backup files...")
            
            # Extract archives
            self.extract_archives(source_file_path, dest_file_path)
            
            if self.job_id:
                update_job_progress(self.job_id, progress=25, message='Validating backup files...')
            
            # Validate schema versions
            source_manifest, _ = self.validate_schema_versions()
            
            if self.job_id:
                update_job_progress(self.job_id, progress=35, message='Starting database merge...')
            
            # Merge databases
            self.merge_databases()
            
            if self.job_id:
                update_job_progress(self.job_id, progress=85, message='Updating manifest and creating archive...')
            
            # Update manifest and create new archive
            new_name = self.update_manifest(source_manifest)
            self.result_file = self.create_new_archive(new_name)
            
            if self.job_id:
                update_job_progress(self.job_id, progress=100, status='completed', 
                                  message='Merge completed successfully!', 
                                  result_file=os.path.basename(self.result_file))
            
            # Register file for cleanup
            register_generated_file(self.result_file)
            
            return self.result_file
            
        except Exception as e:
            if self.job_id:
                update_job_progress(self.job_id, status='error', 
                                  message=f'Error: {str(e)}', error=str(e))
            raise
        finally:
            # ALWAYS clean up temp directories immediately after processing
            self.cleanup()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/progress/<job_id>')
def progress_page(job_id):
    """Display progress page for a specific job"""
    job_data = get_job_progress(job_id)
    if not job_data:
        flash('Job not found or expired')
        return redirect(url_for('index'))
    return render_template('progress.html', job_id=job_id)

@app.route('/api/upload', methods=['POST'])
def api_upload_files():
    """AJAX endpoint for uploading files and starting background processing"""
    if 'source_file' not in request.files or 'dest_file' not in request.files:
        return jsonify({'error': 'Please select both source and destination files'}), 400
    
    source_file = request.files['source_file']
    dest_file = request.files['dest_file']
    
    if source_file.filename == '' or dest_file.filename == '':
        return jsonify({'error': 'Please select both files'}), 400
    
    if not (source_file.filename.endswith('.jwlibrary') and 
            dest_file.filename.endswith('.jwlibrary')):
        return jsonify({'error': 'Please upload .jwlibrary files only'}), 400
    
    # Generate unique job ID
    job_id = str(uuid.uuid4())
    create_job(job_id)
    
    # Save uploaded files
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jwlibrary') as source_temp:
            source_file.save(source_temp.name)
            source_temp_path = source_temp.name
            
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jwlibrary') as dest_temp:
            dest_file.save(dest_temp.name)
            dest_temp_path = dest_temp.name
        
        update_job_progress(job_id, status='uploaded', progress=5, message='Files uploaded successfully. Starting processing...')
        
        # Start processing in background thread
        def process_in_background():
            try:
                sync = WebJWLibrarySync(job_id)
                sync.process_files(source_temp_path, dest_temp_path)
                
                # Clean up uploaded files
                os.unlink(source_temp_path)
                os.unlink(dest_temp_path)
                
            except Exception as e:
                # Clean up uploaded files on error
                try:
                    os.unlink(source_temp_path)
                    os.unlink(dest_temp_path)
                except:
                    pass
                
                # Error already logged in WebJWLibrarySync
                app.logger.error(f"Background processing failed for job {job_id}: {str(e)}")
        
        # Start background thread
        thread = threading.Thread(target=process_in_background)
        thread.daemon = True
        thread.start()
        
        return jsonify({'job_id': job_id}), 202
        
    except Exception as e:
        update_job_progress(job_id, status='error', message=f'Upload failed: {str(e)}', error=str(e))
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500

@app.route('/api/progress/<job_id>')
def api_get_progress(job_id):
    """API endpoint to get job progress"""
    job_data = get_job_progress(job_id)
    if not job_data:
        return jsonify({'error': 'Job not found'}), 404
    
    return jsonify(job_data)

@app.route('/download/<path:filename>')
def download_file(filename):
    try:
        # Security: Only allow downloading from script directory
        file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
        if os.path.exists(file_path) and filename.endswith('.jwlibrary'):
            # Send file with download prompt
            response = send_file(file_path, as_attachment=True, download_name=filename)
            return response
        else:
            return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'error': f'Download error: {str(e)}'}), 500

@app.route('/api/download-success/<path:filename>', methods=['POST'])
def confirm_download_success(filename):
    """Called by client to confirm successful download and trigger cleanup"""
    try:
        file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
        if os.path.exists(file_path) and filename.endswith('.jwlibrary'):
            # Clean up the file immediately after successful download
            cleanup_file(file_path)
            app.logger.info(f"File {filename} downloaded successfully and cleaned up")
            return jsonify({'status': 'cleaned_up'}), 200
        else:
            return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'error': f'Cleanup error: {str(e)}'}), 500

@app.route('/api/download-failed/<path:filename>', methods=['POST']) 
def handle_download_failed(filename):
    """Called when download fails - file kept for retry"""
    try:
        file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
        if os.path.exists(file_path) and filename.endswith('.jwlibrary'):
            app.logger.info(f"Download failed for {filename}, file kept for retry")
            return jsonify({'status': 'kept_for_retry'}), 200
        else:
            return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'error': f'Error handling failed download: {str(e)}'}), 500

@app.route('/api/cleanup-abandoned/<path:filename>', methods=['POST'])
def cleanup_abandoned_file(filename):
    """Called when user navigates away without downloading"""
    try:
        file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
        if os.path.exists(file_path) and filename.endswith('.jwlibrary'):
            cleanup_file(file_path)
            app.logger.info(f"Abandoned file {filename} cleaned up")
            return jsonify({'status': 'cleaned_up'}), 200
        else:
            return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'error': f'Cleanup error: {str(e)}'}), 500

@app.route('/cleanup/<path:filename>', methods=['POST'])
def manual_cleanup(filename):
    """Allow manual cleanup of a specific file"""
    try:
        file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
        if filename.endswith('.jwlibrary'):
            cleanup_file(file_path)
        return '', 204  # No content response
    except Exception:
        return '', 500
        

if __name__ == '__main__':
    # Start cleanup thread
    cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
    cleanup_thread.start()
    
    app.run(debug=True)
