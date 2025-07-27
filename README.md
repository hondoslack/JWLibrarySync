# JWLSync

A Python utility for merging JW Library backup archives (*.jwlibrary files).

## Requirements

- Python 3.8 or higher (includes tkinter)
- Windows 11

## Installation

1. Install Python using winget:
```powershell
winget install Python.Python.3.11
```

2. Verify Python installation:
```powershell
python --version
```

3. Verify tkinter is available (should be included with Python):
```powershell
python -c "import tkinter; print('tkinter is available')"
```

4. Clone this repository

5. Create and activate a virtual environment:
```powershell
# Navigate to the project directory
cd JWLSync

# Create virtual environment
python -m venv venv

# Activate virtual environment
.\venv\Scripts\activate

# Your prompt should now show (venv) at the beginning
```

6. Install dependencies:
```powershell
pip install -r requirements.txt
```

7. When you're done, you can deactivate the virtual environment:
```powershell
deactivate
```

## Usage

Run the program (make sure virtual environment is activated):
```powershell
# Activate virtual environment if not already active
.\venv\Scripts\activate

# Run the program
python jwlsync.py
```

The program will:
1. Prompt you to select source and destination backup files
2. Validate the archives and their schema versions
3. Merge the databases while maintaining referential integrity
4. Generate a new backup file with the merged data
5. Clean up temporary files

## Features

- Merges user data from two JW Library backup files (*.jwlibrary)
- Maintains referential integrity across all tables
- Updates manifest.json with new hash and timestamps
- Generates new backup file with merged data 