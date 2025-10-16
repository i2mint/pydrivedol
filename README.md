# pydrivedol

> Google Drive Data Object Layer - Pythonic mapping interfaces to Google Drive

[![Python](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**pydrivedol** provides clean, Pythonic `Mapping` and `MutableMapping` interfaces to Google Drive, following the design patterns of the [`dol` package](https://github.com/i2mint/dol). Access Google Drive files and folders as if they were dictionaries!

## Features

- 🚀 **Simple public downloads** - No API setup required for public files
- 📂 **Folder as dict** - Browse folders with `dict`-like interface
- 💾 **Read/write operations** - Full CRUD support through mapping protocol
- 🔄 **Recursive traversal** - Control depth with `max_levels`
- 🎯 **Minimal boilerplate** - Follows `dol` patterns you already know
- 🔐 **OAuth2 handled** - Simple authentication flow

## Installation

```bash
pip install pydrive2 requests
```

Then install pydrivedol:

```bash
pip install pydrivedol  # When published to PyPI
# OR for development:
git clone https://github.com/i2mint/pydrivedol.git
cd pydrivedol
pip install -e .
```

## Quick Start

### Simple Downloads (No Setup Required!)

Download from public Google Drive URLs without any API configuration:

```python
from pydrivedol import get_bytes

# Download public file
url = "https://drive.google.com/file/d/YOUR_FILE_ID/view"
content = get_bytes(url)

# Save to temp file
temp_path = get_bytes(url, local_path=True)

# Save to specific path
get_bytes(url, local_path='/path/to/save.pdf')

# With caching
get_bytes(url, use_cache=True)  # Uses ~/.cache/pydrivedol/cached/
```

### Working with Folders (Requires API Setup)

```python
from pydrivedol import GDReader, GDStore

# Read-only access
folder_url = "https://drive.google.com/drive/folders/YOUR_FOLDER_ID"
reader = GDReader(folder_url)

# List all files (keys are relative paths with extensions)
for filepath in reader:
    print(filepath)
# Output:
# file.txt
# folder/nested.pdf
# data/report.xlsx

# Get file contents (values are bytes)
content = reader['file.txt']
pdf_bytes = reader['folder/nested.pdf']

# Check if file exists
if 'data/report.xlsx' in reader:
    print("Found report!")

# Get number of files
num_files = len(reader)

# Get shareable URL
url = reader.get_url('file.txt')
```

### Read-Write Operations

```python
from pydrivedol import GDStore

# Read-write access
store = GDStore(folder_url)

# Write a file
store['newfile.txt'] = b'Hello, World!'

# Write to nested folder (creates folders automatically)
store['reports/2024/summary.txt'] = b'Q1 results...'

# Update existing file
store['newfile.txt'] = b'Updated content'

# Delete file
del store['newfile.txt']

# Full CRUD operations
store['data.json'] = b'{"key": "value"}'
data = store['data.json']  # Read
store['data.json'] = b'{"key": "new"}'  # Update
del store['data.json']  # Delete
```

## API Setup (for GDReader/GDStore)

### 1. Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable **Google Drive API**:
   - Navigate to "APIs & Services" → "Library"
   - Search for "Google Drive API"
   - Click "Enable"

### 2. Create OAuth2 Credentials

1. Go to "APIs & Services" → "Credentials"
2. Click "Create Credentials" → "OAuth client ID"
3. Choose "Desktop app" as application type
4. Download the JSON file
5. Rename it to `client_secrets.json`
6. Place it in your working directory

### 3. First-Time Authentication

On first use, a browser window will open for authentication:

```python
from pydrivedol import GDReader

# This will open browser for authentication
reader = GDReader(folder_url)
```

1. Sign in with your Google account
2. Grant permissions
3. Credentials are saved for future use

That's it! You only need to authenticate once.

## Advanced Usage

### Control Recursion Depth

```python
from pydrivedol import GDReader

# Only files in the root folder
reader = GDReader(folder_url, max_levels=0)

# One level deep
reader = GDReader(folder_url, max_levels=1)

# Fully recursive (default)
reader = GDReader(folder_url, max_levels=None)
```

### Include Hidden Files

```python
reader = GDReader(folder_url, include_hidden=True)
```

### Custom Credentials Location

```python
reader = GDReader(
    folder_url,
    credentials_file='/path/to/client_secrets.json',
    settings_file='/path/to/settings.yaml'
)
```

### Generate Shareable URLs

```python
# Get public URL for a file
url = reader.get_url('file.txt')

# With specific permissions
url = reader.get_url(
    'file.txt',
    permission_type='anyone',  # 'anyone', 'user', 'group', 'domain'
    permission_role='reader'    # 'reader', 'writer', 'commenter'
)
```

### Caching Downloads

```python
from pydrivedol import get_bytes

# Use default cache directory (~/.cache/pydrivedol/cached/)
content = get_bytes(url, use_cache=True)

# Use custom cache directory
content = get_bytes(url, use_cache='/path/to/cache/')

# Files are cached by ID, subsequent calls are instant
content = get_bytes(url, use_cache=True)  # From cache!
```

## Examples

### Backup Local Files to Google Drive

```python
from pydrivedol import GDStore
from pathlib import Path

store = GDStore(folder_url)

# Backup all .py files
for filepath in Path('.').glob('**/*.py'):
    store[str(filepath)] = filepath.read_bytes()
```

### Download All Files from a Folder

```python
from pydrivedol import GDReader
from pathlib import Path

reader = GDReader(folder_url)

for filepath in reader:
    # Preserve folder structure
    local_path = Path(filepath)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(reader[filepath])
```

### Sync Between Two Folders

```python
from pydrivedol import GDReader, GDStore

source = GDReader(source_folder_url)
target = GDStore(target_folder_url)

# Copy missing files
for filepath in source:
    if filepath not in target:
        target[filepath] = source[filepath]
        print(f"Copied: {filepath}")
```

### Process CSV Files in Drive

```python
from pydrivedol import GDReader
import csv
from io import StringIO

reader = GDReader(folder_url)

for filepath in reader:
    if filepath.endswith('.csv'):
        content = reader[filepath].decode('utf-8')
        csv_reader = csv.DictReader(StringIO(content))
        for row in csv_reader:
            print(row)
```

## Architecture

pydrivedol follows the `dol` package patterns:

```
Helper Functions
  └─ get_bytes()              # Simple public downloads (no API)
  
API-Based Classes  
  └─ GDReader (Mapping)       # Read-only folder access
      └─ GDStore (MutableMapping)  # Read-write folder access
```

**Design Principles:**
- Collections as Mappings
- Minimal boilerplate
- Familiar dict-like interface
- Lazy evaluation where possible
- Clear separation of concerns

## Comparison with Other Tools

### vs. PyDrive2 directly

```python
# PyDrive2
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive

gauth = GoogleAuth()
gauth.LocalWebserverAuth()
drive = GoogleDrive(gauth)

file_list = drive.ListFile({'q': "'folder_id' in parents"}).GetList()
for file in file_list:
    content = file.GetContentString()

# pydrivedol
from pydrivedol import GDReader

reader = GDReader(folder_url)
for filepath, content in reader.items():
    pass  # content is already bytes!
```

### vs. google-api-python-client

```python
# google-api-python-client
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

creds = Credentials.from_authorized_user_file('token.json', SCOPES)
service = build('drive', 'v3', credentials=creds)
results = service.files().list().execute()
items = results.get('files', [])

# pydrivedol  
from pydrivedol import GDReader

reader = GDReader(folder_url)
items = list(reader)  # Just keys!
```

**pydrivedol advantages:**
- ✅ Dict-like interface
- ✅ Less boilerplate
- ✅ Follows familiar patterns
- ✅ Recursive traversal built-in
- ✅ Public file downloads without API

## Testing

### Quick Test (No Setup)

```bash
pytest test_pydrivedol.py -v
# Runs helper function tests, skips API tests
```

### Full Test Setup

```bash
# 1. Set environment variables
export PYDRIVEDOL_TEST_FOLDER_URL="https://drive.google.com/drive/folders/YOUR_ID"
export PYDRIVEDOL_TEST_PUBLIC_FILE_URL="https://drive.google.com/file/d/YOUR_ID/view"

# 2. Ensure client_secrets.json is in place

# 3. Run tests
pytest test_pydrivedol.py -v
```

See [TEST_SETUP.md](TEST_SETUP.md) for detailed instructions.

## FAQ

**Q: Do I need a Google Cloud project for `get_bytes()`?**  
A: No! `get_bytes()` works with public URLs without any API setup.

**Q: Can I use this in production?**  
A: Yes, but be aware of [Google Drive API quotas](https://developers.google.com/drive/api/guides/limits).

**Q: How do I handle large files?**  
A: Files are loaded into memory as bytes. For very large files, consider streaming or using the PyDrive2 API directly.

**Q: Can I use service accounts?**  
A: Currently pydrivedol uses OAuth2 for user accounts. Service account support is planned.

**Q: What about Google Workspace files (Docs, Sheets)?**  
A: These need to be exported first. Currently pydrivedol focuses on regular files.

**Q: Is this thread-safe?**  
A: File operations are atomic, but concurrent modifications to the same file may conflict.

## Troubleshooting

### "No module named 'pydrive2'"

```bash
pip install pydrive2
```

### "Invalid client secrets file"

1. Ensure `client_secrets.json` is in your working directory
2. Verify it's the correct OAuth2 credentials JSON
3. Try creating new credentials in Google Cloud Console

### "Permission denied"

1. Check that your Google account has access to the folder
2. Verify folder sharing settings
3. Re-authenticate: delete saved credentials and run again

### Tests are skipped

Check environment variables:
```bash
python test_pydrivedol.py  # Shows configuration status
```

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## Related Projects

- [dol](https://github.com/i2mint/dol) - The underlying data object layer framework
- [s3dol](https://github.com/i2mint/s3dol) - Similar interface for AWS S3
- [PyDrive2](https://github.com/iterative/PyDrive2) - Google Drive API wrapper (used by pydrivedol)

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Credits

Built with ❤️ using:
- [PyDrive2](https://github.com/iterative/PyDrive2) for Google Drive API
- [dol](https://github.com/i2mint/dol) patterns for clean interfaces
- [requests](https://requests.readthedocs.io/) for HTTP operations

---

**Part of the [i2mint](https://github.com/i2mint) ecosystem of data access tools.**