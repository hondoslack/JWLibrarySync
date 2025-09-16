#!/usr/bin/env python3
"""
Simple startup script for the JW Library Sync web application.
Run this on Python Anywhere or any other web hosting service.

Environment Variables:
- ENVIRONMENT: 'production' or 'development' (defaults to 'development')
- LOG_LEVEL: 'DEBUG', 'INFO', 'WARNING', 'ERROR', or 'CRITICAL' (optional)

For production deployment on PythonAnywhere, set:
ENVIRONMENT=production

For debugging issues in production, temporarily set:
ENVIRONMENT=production
LOG_LEVEL=DEBUG
"""

import os

# CRITICAL: Set production environment BEFORE any imports
# This ensures logging is configured correctly for WSGI deployment
if not os.getenv('ENVIRONMENT') and __name__ != '__main__':
    os.environ['ENVIRONMENT'] = 'production'

try:
    from app import app, cleanup_old_files
    import threading
    
    # Start cleanup thread for production
    cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
    cleanup_thread.start()
    
    if __name__ == '__main__':
        # For local development
        environment = os.getenv('ENVIRONMENT', 'development').lower()
        debug_mode = environment != 'production'
        app.run(debug=debug_mode, host='0.0.0.0', port=5000)
    else:
        # For WSGI deployment (Python Anywhere, etc.)
        application = app
        
except ImportError as e:
    print("Missing dependencies. Install with: pip install -r requirements.txt")
    print(f"Error: {e}")
