import os
import sys
import json
import time
import shutil
import sqlite3
import hashlib
import zipfile
import tempfile
import datetime
import logging
from datetime import UTC
from pathlib import Path
# from tkinter import Tk, filedialog  # Only needed for CLI version
from tqdm import tqdm

class JWLibrarySyncError(Exception):
    pass

class JWLibrarySync:
    def __init__(self, progress_callback=None):
        self.temp_dir = None
        self.source_dir = None
        self.dest_dir = None
        self.progress_callback = progress_callback
        self.id_mappings = {
            'LocationId': {},
            'UserMarkId': {},
            'PlaylistItemId': {},
            'TagId': {},
            'BlockRangeId': {},
            'NoteId': {},
            'TagMapId': {}
        }
        
        # Setup logging
        self.setup_logging()

    def setup_logging(self):
        """Configure logging to write to both file and console"""
        self.logger = logging.getLogger('JWLibrarySync')
        
        # Get logging configuration from environment
        environment = os.getenv('ENVIRONMENT', 'development').lower()
        log_level_str = os.getenv('LOG_LEVEL', '').upper()
        
        # Set default log levels based on environment
        if environment == 'production':
            default_file_level = logging.INFO
            default_console_level = logging.WARNING
        else:
            default_file_level = logging.DEBUG
            default_console_level = logging.INFO
            
        # Override with explicit LOG_LEVEL if provided
        if log_level_str:
            try:
                explicit_level = getattr(logging, log_level_str)
                default_file_level = explicit_level
                # In production, keep console quiet unless explicitly set to DEBUG
                if environment != 'production' or log_level_str == 'DEBUG':
                    default_console_level = explicit_level
            except AttributeError:
                # Invalid log level, use defaults
                pass
        
        # Set logger level to the lowest level we'll use
        self.logger.setLevel(min(default_file_level, default_console_level))
        
        # Clear any existing handlers (important for web apps)
        self.logger.handlers.clear()
        
        # Create logs directory if it doesn't exist (only if we're doing file logging)
        if environment != 'production' or log_level_str == 'DEBUG':
            log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
            os.makedirs(log_dir, exist_ok=True)
            
            # File handler with timestamp in filename
            log_file = os.path.join(log_dir, f'jwlsync_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(default_file_level)
            
            # Create formatter for file
            file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(default_console_level)
        
        # Create formatter for console
        console_formatter = logging.Formatter('%(message)s')
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
        # Log startup info
        self.logger.info(f"JWLibrarySync started (Environment: {environment}, Log Level: File={logging.getLevelName(default_file_level)}, Console={logging.getLevelName(default_console_level)})")
        if environment != 'production' or log_level_str == 'DEBUG':
            self.logger.debug(f"Log file: {log_file if 'log_file' in locals() else 'None (production mode)'}")

    def cleanup(self):
        """Clean up temporary directories immediately after processing"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                self.logger.debug(f"Cleaning up temporary directory: {self.temp_dir}")
                
                # Calculate size before cleanup for logging
                total_size = 0
                file_count = 0
                try:
                    for root, dirs, files in os.walk(self.temp_dir):
                        for file in files:
                            filepath = os.path.join(root, file)
                            try:
                                total_size += os.path.getsize(filepath)
                                file_count += 1
                            except:
                                pass
                except:
                    pass
                
                # Give Windows a moment to release file handles
                time.sleep(0.1)
                
                # Force close any SQLite connections in the temp directory
                if self.source_dir:
                    source_db_path = os.path.join(self.source_dir, 'userData.db')
                    if os.path.exists(source_db_path):
                        try:
                            conn = sqlite3.connect(source_db_path)
                            conn.close()
                        except:
                            pass
                        
                if self.dest_dir:
                    dest_db_path = os.path.join(self.dest_dir, 'userData.db')
                    if os.path.exists(dest_db_path):
                        try:
                            conn = sqlite3.connect(dest_db_path)
                            conn.close()
                        except:
                            pass
                
                # Remove the temp directory
                shutil.rmtree(self.temp_dir)
                
                # Log cleanup success with size info
                size_mb = total_size / (1024 * 1024) if total_size > 0 else 0
                self.logger.info(f"Cleaned up temp directory ({file_count} files, {size_mb:.1f} MB freed)")
                
                # Reset temp directory references
                self.temp_dir = None
                self.source_dir = None
                self.dest_dir = None
                
            except PermissionError:
                self.logger.warning(f"Could not remove temporary directory {self.temp_dir}")
                self.logger.warning("It may be in use. Please remove it manually.")
                self.logger.warning(f"Path: {self.temp_dir}")
            except Exception as e:
                self.logger.error(f"Error cleaning up temporary directory {self.temp_dir}")
                self.logger.error(f"Error: {str(e)}")
                self.logger.warning("You may need to remove it manually.")
        else:
            self.logger.debug("No temporary directory to clean up")

    def select_files(self):
        """Prompt user to select source and destination files"""
        try:
            from tkinter import Tk, filedialog
        except ImportError:
            raise JWLibrarySyncError("GUI functionality requires tkinter. Use web interface instead.")
            
        root = Tk()
        root.withdraw()  # Hide the main window

        print("Select the source backup file...")
        source_file = filedialog.askopenfilename(
            title="Select Source Backup",
            filetypes=[("JW Library Backup", "*.jwlibrary")]
        )
        if not source_file:
            print("\nOperation cancelled: No source file selected")
            sys.exit(0)

        print("Select the destination backup file...")
        dest_file = filedialog.askopenfilename(
            title="Select Destination Backup",
            filetypes=[("JW Library Backup", "*.jwlibrary")]
        )
        if not dest_file:
            print("\nOperation cancelled: No destination file selected")
            sys.exit(0)

        return source_file, dest_file

    def extract_archives(self, source_file, dest_file):
        """Extract both archives to temporary directories"""
        self.temp_dir = tempfile.mkdtemp()
        self.source_dir = os.path.join(self.temp_dir, "source")
        self.dest_dir = os.path.join(self.temp_dir, "dest")

        os.makedirs(self.source_dir)
        os.makedirs(self.dest_dir)

        with zipfile.ZipFile(source_file, 'r') as zip_ref:
            zip_ref.extractall(self.source_dir)
        
        with zipfile.ZipFile(dest_file, 'r') as zip_ref:
            zip_ref.extractall(self.dest_dir)

    def validate_schema_versions(self):
        """Compare schema versions between source and destination"""
        with open(os.path.join(self.source_dir, 'manifest.json')) as f:
            source_manifest = json.load(f)
        with open(os.path.join(self.dest_dir, 'manifest.json')) as f:
            dest_manifest = json.load(f)

        if source_manifest['userDataBackup']['schemaVersion'] != dest_manifest['userDataBackup']['schemaVersion']:
            raise JWLibrarySyncError("Schema versions do not match")
        
        return source_manifest, dest_manifest

    def merge_table(self, cursor_src, cursor_dest, table_name, id_column=None, dependencies=None):
        """Merge a single table while maintaining referential integrity"""
        try:
            # Get all columns except the auto-incrementing ID
            cursor_src.execute(f"PRAGMA table_info({table_name})")
            all_columns = [col[1] for col in cursor_src.fetchall()]
            columns = [col for col in all_columns if col != id_column]
            columns_str = ', '.join(columns)

            # Log column information
            self.logger.debug(f"Table {table_name} columns: {columns}")
            if dependencies:
                self.logger.debug(f"Table {table_name} dependencies: {dependencies}")
                for dep_col, mapping in dependencies.items():
                    self.logger.debug(f"Dependency mapping for {dep_col}: {mapping}")

            # Fetch all records from source
            if id_column:
                select_cols = f"{id_column}, {columns_str}"
            else:
                select_cols = columns_str

            cursor_src.execute(f"SELECT {select_cols} FROM {table_name}")
            source_records = cursor_src.fetchall()
            self.logger.debug(f"Found {len(source_records)} records in {table_name}")

            for record in tqdm(source_records, desc=f"Merging {table_name}"):
                if id_column:
                    old_id = record[0]
                    values = list(record[1:])  # Convert to list for potential modifications
                else:
                    old_id = None
                    values = list(record)  # Convert to list for potential modifications

                # Log original values for debugging
                if table_name in ['Note', 'UserMark', 'Location']:
                    self.logger.debug(f"Processing {table_name} record:")
                    self.logger.debug(f"  Original values: {dict(zip(columns, values))}")
                
                # Replace dependent IDs with their new mappings
                if dependencies:
                    for col, mapping in dependencies.items():
                        try:
                            col_index = columns.index(col)
                            old_dep_id = values[col_index]
                            if old_dep_id is not None:
                                new_dep_id = mapping.get(old_dep_id)
                                if new_dep_id is not None:
                                    self.logger.debug(f"  {table_name}.{col}: Mapping {old_dep_id} -> {new_dep_id}")
                                    values[col_index] = new_dep_id
                                else:
                                    self.logger.warning(f"  {table_name}.{col}: No mapping found for ID {old_dep_id}")
                            else:
                                self.logger.debug(f"  {table_name}.{col}: Skipping NULL value")
                        except ValueError as e:
                            self.logger.warning(f"Column {col} not found in {table_name}: {str(e)}")
                            continue
                    values = tuple(values)

                    # Log final values after mapping
                    if table_name in ['Note', 'UserMark', 'Location']:
                        self.logger.debug(f"  Final values after mapping: {dict(zip(columns, values))}")

                # Special handling for Location table's unique constraints
                if table_name == 'Location':
                    type_index = columns.index('Type')
                    record_type = values[type_index]
                    document_id_index = columns.index('DocumentId')
                    document_id = values[document_id_index]
                    
                    if record_type == 3:
                        # Use constraint for Type = 3
                        unique_columns = ['KeySymbol', 'IssueTagNumber', 'MepsLanguage', 'DocumentId', 'Track', 'Type']
                    elif record_type != 3 and document_id is not None:
                        unique_columns = ['BookNumber', 'ChapterNumber', 'KeySymbol', 'MepsLanguage', 'Type', 'DocumentId']
                    else:
                        unique_columns = ['BookNumber', 'ChapterNumber', 'KeySymbol', 'MepsLanguage', 'Type']   
                        
                    where_conditions = []
                    where_values = []
                    for col in unique_columns:
                        col_index = columns.index(col)
                        if values[col_index] is None:
                            where_conditions.append(f"{col} IS NULL")
                        else:
                            where_conditions.append(f"{col} = ?")
                            where_values.append(values[col_index])
                else:
                    # Default behavior for other tables
                    where_conditions = []
                    where_values = []
                    for i, col in enumerate(columns):
                        if values[i] is None:
                            where_conditions.append(f"{col} IS NULL")
                        else:
                            where_conditions.append(f"{col} = ?")
                            where_values.append(values[i])
                        
                # Check if record exists in destination
                where_clause = ' AND '.join(where_conditions)
                cursor_dest.execute(f"""
                    SELECT COUNT(*) FROM {table_name}
                    WHERE {where_clause}
                """, where_values)
                
                if cursor_dest.fetchone()[0] == 0:
                    try:
                        # Insert new record
                        placeholders = ','.join(['?' for _ in columns])
                        cursor_dest.execute(f"""
                            INSERT INTO {table_name} ({columns_str})
                            VALUES ({placeholders})
                        """, values)
                        
                        # Store ID mapping if needed
                        if id_column:
                            new_id = cursor_dest.lastrowid
                            self.id_mappings[id_column][old_id] = new_id
                            self.logger.debug(f"  Created new {table_name} mapping: {id_column}={old_id} -> {new_id}")
                    except sqlite3.IntegrityError as e:
                        # If insert fails due to unique constraint, skip this record but still get the ID
                        self.logger.warning(f"Skipping duplicate record in {table_name}")
                        self.logger.debug(f"  Skipped values: {dict(zip(columns, values))}")
                        self.logger.debug(f"  Reason: {str(e)}")
                        
                        if id_column:
                            # Find the existing record's ID
                            cursor_dest.execute(f"""
                                SELECT {id_column} FROM {table_name}
                                WHERE {where_clause}
                            """, where_values)
                            existing_id = cursor_dest.fetchone()
                            if existing_id:
                                self.id_mappings[id_column][old_id] = existing_id[0]
                                self.logger.debug(f"  Mapped skipped {table_name}: {id_column}={old_id} -> {existing_id[0]}")
                        continue
                else:
                    # Record exists, log the details and store mapping if needed
                    self.logger.debug(f"  Skipping existing {table_name} record:")
                    self.logger.debug(f"  Values: {dict(zip(columns, values))}")
                    self.logger.debug(f"  Where clause: {where_clause}")
                    self.logger.debug(f"  Where values: {where_values}")
                    
                    if id_column:
                        # Find the existing record's ID
                        cursor_dest.execute(f"""
                            SELECT {id_column} FROM {table_name}
                            WHERE {where_clause}
                        """, where_values)
                        existing_id = cursor_dest.fetchone()
                        if existing_id:
                            self.id_mappings[id_column][old_id] = existing_id[0]
                            self.logger.debug(f"  Mapped existing {table_name}: {id_column}={old_id} -> {existing_id[0]}")

        except Exception as e:
            raise JWLibrarySyncError(f"Error merging table {table_name}: {str(e)}")

    def merge_databases(self):
        """Merge all tables from source to destination"""
        source_db = None
        dest_db = None
        
        # Define merge steps with progress ranges
        merge_steps = [
            ('Location', 'LocationId', None, 35, 45, 'Merging locations...'),
            ('UserMark', 'UserMarkId', {'LocationId': 'LocationId'}, 45, 55, 'Merging user marks...'),
            ('BlockRange', 'BlockRangeId', {'UserMarkId': 'UserMarkId'}, 55, 60, 'Merging block ranges...'),
            ('Note', 'NoteId', {'UserMarkId': 'UserMarkId', 'LocationId': 'LocationId'}, 60, 70, 'Merging notes...'),
            ('PlaylistItem', 'PlaylistItemId', None, 70, 75, 'Merging playlist items...'),
            ('Tag', 'TagId', None, 75, 78, 'Merging tags...'),
            ('InputField', None, {'LocationId': 'LocationId'}, 78, 80, 'Merging input fields...'),
            ('TagMap', 'TagMapId', {'PlaylistItemId': 'PlaylistItemId', 'LocationId': 'LocationId', 'NoteId': 'NoteId', 'TagId': 'TagId'}, 80, 85, 'Merging tag mappings...')
        ]
        
        try:
            source_db = sqlite3.connect(os.path.join(self.source_dir, 'userData.db'))
            dest_db = sqlite3.connect(os.path.join(self.dest_dir, 'userData.db'))
            
            cursor_src = source_db.cursor()
            cursor_dest = dest_db.cursor()

            for i, (table_name, id_column, dependencies, start_progress, end_progress, message) in enumerate(merge_steps):
                if self.progress_callback:
                    self.progress_callback(progress=start_progress, message=message)
                
                # Resolve dependencies
                resolved_dependencies = None
                if dependencies:
                    resolved_dependencies = {}
                    for dep_col, mapping_key in dependencies.items():
                        resolved_dependencies[dep_col] = self.id_mappings[mapping_key]
                
                self.merge_table(cursor_src, cursor_dest, table_name, id_column, resolved_dependencies)
                
                if self.progress_callback:
                    self.progress_callback(progress=end_progress)

            dest_db.commit()

        except sqlite3.IntegrityError as e:
            if source_db:
                source_db.rollback()
            if dest_db:
                dest_db.rollback()
            raise JWLibrarySyncError(f"Database constraint violation: {str(e)}")
        finally:
            if source_db:
                source_db.close()
            if dest_db:
                dest_db.close()

    def calculate_db_hash(self):
        """Calculate SHA-256 hash of the destination database"""
        db_path = os.path.join(self.dest_dir, 'userData.db')
        sha256_hash = hashlib.sha256()
        
        with open(db_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                sha256_hash.update(chunk)
                
        return sha256_hash.hexdigest()

    def update_manifest(self, source_manifest):
        """Update the destination manifest.json with new values"""
        manifest_path = os.path.join(self.dest_dir, 'manifest.json')
        with open(manifest_path) as f:
            dest_manifest = json.load(f)

        # Update hash
        dest_manifest['userDataBackup']['hash'] = self.calculate_db_hash()

        # Update lastModifiedDate if source is newer
        source_modified = datetime.datetime.fromisoformat(source_manifest['userDataBackup']['lastModifiedDate'].replace('Z', '+00:00'))
        dest_modified = datetime.datetime.fromisoformat(dest_manifest['userDataBackup']['lastModifiedDate'].replace('Z', '+00:00'))
        
        if source_modified > dest_modified:
            dest_manifest['userDataBackup']['lastModifiedDate'] = source_manifest['userDataBackup']['lastModifiedDate']

        # Update creationDate with local timezone
        dest_manifest['creationDate'] = datetime.datetime.now().isoformat()

        # Generate new name (assuming format: backup_YYYY-MM-DD_HH-MM-SS)
        new_name = f"merged_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
        dest_manifest['name'] = f"{new_name}.jwlibrary"

        with open(manifest_path, 'w') as f:
            json.dump(dest_manifest, f, indent=2)

        return new_name

    def create_new_archive(self, new_name):
        """Create a new ZIP archive with the merged data"""
        output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{new_name}.jwlibrary")
        
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(self.dest_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, self.dest_dir)
                    zipf.write(file_path, arcname)

        return output_path

    def run(self):
        """Main execution flow"""
        try:
            self.logger.info("JWLibrarySync - JW Library Backup Merger")
            self.logger.info("---------------------------------")

            # Select files
            try:
                source_file, dest_file = self.select_files()
                self.logger.info(f"\nSource: {source_file}")
                self.logger.info(f"Destination: {dest_file}\n")
            except SystemExit as e:
                if e.code == 0:  # Clean exit
                    return
                raise  # Re-raise other system exits

            # Extract archives
            self.logger.info("Extracting archives...")
            self.extract_archives(source_file, dest_file)

            # Validate schema versions
            self.logger.info("Validating schema versions...")
            source_manifest, _ = self.validate_schema_versions()

            # Merge databases
            self.logger.info("\nMerging databases...")
            self.merge_databases()

            # Update manifest and create new archive
            self.logger.info("\nUpdating manifest...")
            new_name = self.update_manifest(source_manifest)

            self.logger.info("\nCreating new archive...")
            output_path = self.create_new_archive(new_name)

            self.logger.info("\nOperation completed successfully!")
            self.logger.info(f"New backup file created: {output_path}")

        except JWLibrarySyncError as e:
            self.logger.error(f"\nError: {str(e)}")
            sys.exit(1)
        except Exception as e:
            self.logger.error(f"\nUnexpected error: {str(e)}")
            sys.exit(1)
        finally:
            self.cleanup()

if __name__ == '__main__':
    JWLibrarySync().run() 