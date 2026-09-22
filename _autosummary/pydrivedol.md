# pydrivedol

Google Drive Data Object Layer

Provides Mapping and MutableMapping interfaces to Google Drive data.

Key Features:

- get_bytes(url): Download bytes from public Google Drive URLs (no API setup needed)
- get_bytes(url, drive=…): Same, but authenticated – reaches *private* files
- get_metadata(url, drive=…): Name/size/mimeType/modifiedDate without downloading
- GDFiles: Read-only Mapping of files, keyed by file id or file URL
- GDReader: Read-only Mapping interface to a Google Drive folder
- GDStore: Read-write MutableMapping interface to a Google Drive folder

Setup (optional) for API-based features (GDReader/GDStore):

1. pip install pydrive2
2. Go to [https://console.cloud.google.com/](https://console.cloud.google.com/)
3. Create project, enable Google Drive API
4. Create OAuth 2.0 credentials (Desktop app), download client_secrets.json
5. First run opens browser for authentication

Usage:

> Simple download (no API needed) – public files only. If the file is not public,
> Google answers with its HTML sign-in page (under HTTP 200); pydrivedol raises
> NotPubliclyShared rather than handing that page back as the file’s content.

> ```pycon
> >>> content = get_bytes(url)
> >>> path = get_bytes(url, local_path=True)
> ```

> Private files: authenticate once, then pass the drive around

> ```pycon
> >>> drive = drive_from_service_account('service-account-key.json')
> >>> get_metadata(url, drive=drive)['fileSize']  # decide before downloading
> >>> content = get_bytes(url, drive=drive)
> ```

> Files as a Mapping, keyed by file id or URL

> ```pycon
> >>> files = GDFiles(drive)
> >>> content = files[url]
> ```

> Read folder

> ```pycon
> >>> reader = GDReader(folder_url)
> >>> list(reader)
> >>> content = reader['path/to/file.txt']
> ```

> Write to folder

> ```pycon
> >>> store = GDStore(folder_url)
> >>> store['file.txt'] = b'content'
> >>> del store['file.txt']
> ```

> Make a native Google Sheet from an .xlsx (Drive converts it, keeping formatting)

> ```pycon
> >>> url = xlsx_to_google_sheet(folder_url, 'My Schema', '/tmp/schema.xlsx')
> >>> store = GDStore(folder_url, convert_office=True)
> >>> store['schema.xlsx'] = xlsx_bytes  # -> a Google Sheet
> ```

### Modules

| [`base`](pydrivedol.base.md#module-pydrivedol.base)   | Base objects for pydrivedol: download functions, GDFiles, GDReader, GDStore.   |
|--------------------------------------------------------------------------------|--------------------------------------------------------------------------------|
