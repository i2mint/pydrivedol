# pydrivedol

> Google Drive Data Object Layer - Pythonic mapping interfaces to Google Drive

[![Python](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**pydrivedol** provides clean, Pythonic `Mapping` and `MutableMapping` interfaces to Google Drive, following the design patterns of the [`dol` package](https://github.com/i2mint/dol). Access Google Drive files and folders as if they were dictionaries!

## Features

- 🚀 **Simple public downloads** - No API setup required for public files
- 🔒 **Private files too** - Pass an authenticated `drive=` to reach files shared only with you
- 🗂️ **Files as dict** - `GDFiles` keyed by file id *or* Drive URL
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
get_bytes(url, local_path="/path/to/save.pdf")

# With caching
get_bytes(url, use_cache=True)  # Uses ~/.cache/pydrivedol/cached/
```

If the file is **not** publicly shared, Google answers with its HTML sign-in page — under
HTTP 200, so it looks like a successful download. pydrivedol refuses to hand that back as
file content and raises `NotPubliclyShared` instead, telling you to authenticate:

```python
from pydrivedol import get_bytes, NotPubliclyShared

try:
    content = get_bytes(url)
except NotPubliclyShared:
    content = get_bytes(url, drive=drive)  # see below
```

(If you really are downloading an HTML file, pass `allow_html=True`.)

### Private Files (Requires API Setup)

Authenticate once, then pass the `drive` wherever bytes are needed:

```python
from pydrivedol import drive_from_service_account, get_bytes, get_metadata, GDFiles

drive = drive_from_service_account("service-account-key.json")

# Is it worth downloading? Metadata is cheap — it fetches no content.
info = get_metadata(url, drive=drive)
info["title"], info["fileSize"], info["mimeType"], info["modifiedDate"]
# ('client_export.xlsx', 18512345, 'application/vnd...sheet', '2026-08-01T12:00:00.000Z')

# Same get_bytes, now authenticated — local_path= and use_cache= work as before
content = get_bytes(url, drive=drive)
```

`fileSize` comes back as an `int` (Drive sends it as a string), and is **absent** for
Google-native files — Sheets/Docs/Slides have no stored byte size.

### Files as a Mapping: `GDFiles`

When files arrive as *links* rather than as a folder listing, key by the link:

```python
files = GDFiles(drive)

content = files[url]  # a Drive file URL...
content = files[file_id]  # ...or the bare id: same entry
url in files  # metadata probe, never a download
files.metadata(url)  # name / size / mimeType / modifiedDate

# Iteration needs a scope — an unscoped GDFiles addresses the whole Drive
scoped = GDFiles(drive, folder_url=folder_url)
list(scoped)  # file ids
```

Unscoped, `iter()` and `len()` raise `NotImplementedError` (with a message naming
`folder_url=`) rather than silently paginating your entire Drive. Lookup works either way.

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
content = reader["file.txt"]
pdf_bytes = reader["folder/nested.pdf"]

# Check if file exists
if "data/report.xlsx" in reader:
    print("Found report!")

# Get number of files
num_files = len(reader)

# Get shareable URL
url = reader.get_url("file.txt")
```

### Read-Write Operations

```python
from pydrivedol import GDStore

# Read-write access
store = GDStore(folder_url)

# Write a file
store["newfile.txt"] = b"Hello, World!"

# Write to nested folder (creates folders automatically)
store["reports/2024/summary.txt"] = b"Q1 results..."

# Update existing file
store["newfile.txt"] = b"Updated content"

# Delete file
del store["newfile.txt"]

# Full CRUD operations
store["data.json"] = b'{"key": "value"}'
data = store["data.json"]  # Read
store["data.json"] = b'{"key": "new"}'  # Update
del store["data.json"]  # Delete
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

### Headless / server: use a service account instead

The browser flow above is unusable from a script, a server, or an agent. For those, create a
**service account** — a robot identity with its own key file and no interactive login:

1. [Google Cloud Console](https://console.cloud.google.com/) → your project →
   "APIs & Services" → "Credentials"
2. "Create Credentials" → **Service account**. Any name; no roles needed.
3. Open the new service account → "Keys" → "Add key" → "Create new key" → **JSON**. The key
   file downloads once and cannot be re-downloaded.
4. Copy the service account's **`client_email`** (it looks like
   `something@your-project.iam.gserviceaccount.com`).
5. In Google Drive, **share the file or folder with that `client_email`** — Viewer to read,
   Editor to write. This is the step people forget: the service account is a separate
   identity, and a file shared with *you* is not shared with *it*.
6. Point pydrivedol at the key file:

```python
from pydrivedol import drive_from_service_account

drive = drive_from_service_account("service-account-key.json")
```

Keep the key file out of version control (this repo's `.gitignore` covers the usual names) and
out of the repo entirely if you can — read its path from an environment variable.

Read-only by token, if you want the extra guarantee:

```python
drive = drive_from_service_account(
    key_file, scopes=("https://www.googleapis.com/auth/drive.readonly",)
)
```

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
    credentials_file="/path/to/client_secrets.json",
    settings_file="/path/to/settings.yaml",
)
```

### Generate Shareable URLs

```python
# Get public URL for a file
url = reader.get_url("file.txt")

# With specific permissions
url = reader.get_url(
    "file.txt",
    permission_type="anyone",  # 'anyone', 'user', 'group', 'domain'
    permission_role="reader",  # 'reader', 'writer', 'commenter'
)
```

### Caching Downloads

```python
from pydrivedol import get_bytes

# Use default cache directory (~/.cache/pydrivedol/cached/)
content = get_bytes(url, use_cache=True)

# Use custom cache directory
content = get_bytes(url, use_cache="/path/to/cache/")

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
for filepath in Path(".").glob("**/*.py"):
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
    if filepath.endswith(".csv"):
        content = reader[filepath].decode("utf-8")
        csv_reader = csv.DictReader(StringIO(content))
        for row in csv_reader:
            print(row)
```

## Architecture

pydrivedol follows the `dol` package patterns:

```
Helper Functions
  └─ get_bytes(url)                    # Simple public downloads (no API)
  └─ get_bytes(url, drive=...)         # Authenticated: reaches private files
  └─ get_metadata(url, drive=...)      # Name/size/mimeType/date, no download

API-Based Classes
  └─ GDFiles (Mapping)                 # Files, keyed by file id or file URL
  └─ GDReader (Mapping)                # Read-only folder access, keyed by path
      └─ GDStore (MutableMapping)      # Read-write folder access
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

folder_id = "YOUR_FOLDER_ID"  # a Drive id: [A-Za-z0-9_-]; quote any other value
file_list = drive.ListFile({"q": f"'{folder_id}' in parents"}).GetList()
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

creds = Credentials.from_authorized_user_file("token.json", SCOPES)
service = build("drive", "v3", credentials=creds)
results = service.files().list().execute()
items = results.get("files", [])

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

### `NotPubliclyShared` from `get_bytes`

The file is not shared "anyone with the link", so the unauthenticated endpoint cannot reach
it. Either make it public, or authenticate and pass `drive=` (see *Private Files* above). For
a service account, remember the file/folder must be shared with the account's `client_email`.

### Downloaded file won't open / `BadZipFile` on an xlsx

You are almost certainly holding Google's sign-in page rather than the file. Recent versions
raise `NotPubliclyShared` for exactly this; if you are pinned to an older one, upgrade.

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