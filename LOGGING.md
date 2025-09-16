# Logging Configuration Guide

The JW Library Sync application now supports configurable logging levels to reduce noise in production environments.

## Environment Variables

### `ENVIRONMENT`
- **Options**: `production`, `development`  
- **Default**: `development`
- **Purpose**: Controls default logging behavior

### `LOG_LEVEL` (Optional)
- **Options**: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
- **Default**: Depends on `ENVIRONMENT`
- **Purpose**: Override default logging levels

## Default Logging Behavior

### Development Mode (`ENVIRONMENT=development`)
- **Console**: INFO level and higher
- **File**: DEBUG level and higher (saved to `logs/` directory)
- **Flask/Werkzeug**: INFO level request logging

### Production Mode (`ENVIRONMENT=production`)
- **Console**: WARNING level and higher only
- **File**: No file logging (to save disk space)
- **Flask/Werkzeug**: WARNING level and higher only

## PythonAnywhere Setup

### 1. Automatic Production Mode (Recommended)
**No configuration needed!** The application automatically detects WSGI deployment and enables production logging mode.

### 2. Manual Override (Optional)
If you want to explicitly set the environment, add this in your PythonAnywhere web app environment variables:
```bash
ENVIRONMENT=production
```

### 3. Debugging Production Issues
If you need to debug issues in production, temporarily add:
```bash
ENVIRONMENT=production
LOG_LEVEL=DEBUG
```

**Remember to remove `LOG_LEVEL=DEBUG` after debugging** to avoid filling up logs again.

### 4. Custom Log Level
For fine-tuned control, set both variables:
```bash
ENVIRONMENT=production
LOG_LEVEL=INFO
```

## Troubleshooting

### Still Seeing Debug Logs in Production?

If you're still seeing too much logging output on PythonAnywhere:

1. **Check your environment**: Look for "Logging reconfigured for production" message in your logs
2. **Reload your web app** on PythonAnywhere to ensure changes take effect
3. **Clear old logs** and monitor new requests to see if the issue persists

The app now has automatic logging fixes that should resolve timing issues with WSGI deployment.

## Benefits

✅ **Reduced log noise** in production environments  
✅ **Configurable** without code changes  
✅ **Maintains debugging** capability when needed  
✅ **Automatic file management** (no logs directory created in production by default)  
✅ **Flask request logging** properly configured for each environment  

## Log File Management

- **Development**: Log files created in `logs/` with timestamps
- **Production**: No log files by default (console-only)
- **Debug Mode**: Set `LOG_LEVEL=DEBUG` to enable file logging in production
