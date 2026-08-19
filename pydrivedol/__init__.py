"""
Google Drive Data Object Layer

Provides Mapping and MutableMapping interfaces to Google Drive data.

Key Features:
- get_bytes(url): Download bytes from public Google Drive URLs (no API setup needed)
- get_bytes(url, drive=...): Same, but authenticated -- reaches *private* files
- get_metadata(url, drive=...): Name/size/mimeType/modifiedDate without downloading
- GDFiles: Read-only Mapping of files, keyed by file id or file URL
- GDReader: Read-only Mapping interface to a Google Drive folder
- GDStore: Read-write MutableMapping interface to a Google Drive folder

Setup (optional) for API-based features (GDReader/GDStore):
1. pip install pydrive2
2. Go to https://console.cloud.google.com/
3. Create project, enable Google Drive API
4. Create OAuth 2.0 credentials (Desktop app), download client_secrets.json
5. First run opens browser for authentication

Usage:

    Simple download (no API needed) -- public files only. If the file is not public,
    Google answers with its HTML sign-in page (under HTTP 200); pydrivedol raises
    NotPubliclyShared rather than handing that page back as the file's content.

    >>> content = get_bytes(url)  # doctest: +SKIP
    >>> path = get_bytes(url, local_path=True)  # doctest: +SKIP

    Private files: authenticate once, then pass the drive around

    >>> drive = drive_from_service_account('service-account-key.json')  # doctest: +SKIP
    >>> get_metadata(url, drive=drive)['fileSize']  # decide before downloading  # doctest: +SKIP
    >>> content = get_bytes(url, drive=drive)  # doctest: +SKIP

    Files as a Mapping, keyed by file id or URL

    >>> files = GDFiles(drive)  # doctest: +SKIP
    >>> content = files[url]  # doctest: +SKIP

    Read folder

    >>> reader = GDReader(folder_url)  # doctest: +SKIP
    >>> list(reader)  # doctest: +SKIP
    >>> content = reader['path/to/file.txt']  # doctest: +SKIP

    Write to folder

    >>> store = GDStore(folder_url)  # doctest: +SKIP
    >>> store['file.txt'] = b'content'  # doctest: +SKIP
    >>> del store['file.txt']  # doctest: +SKIP

    Make a native Google Sheet from an .xlsx (Drive converts it, keeping formatting)

    >>> url = xlsx_to_google_sheet(folder_url, 'My Schema', '/tmp/schema.xlsx')  # doctest: +SKIP
    >>> store = GDStore(folder_url, convert_office=True)  # doctest: +SKIP
    >>> store['schema.xlsx'] = xlsx_bytes  # -> a Google Sheet  # doctest: +SKIP

"""

from pydrivedol.base import (
    get_bytes,  # simple download function (authenticated when given drive=)
    NotPubliclyShared,  # raised when a public download returns Google's sign-in page
    # Needing API setup:
    get_metadata,  # a file's name/size/mimeType/modifiedDate, without downloading it
    DEFAULT_METADATA_FIELDS,  # the metadata fields get_metadata asks for by default
    GDFiles,  # read-only Mapping of files, keyed by file id or file URL
    GDReader,  # read-only Mapping interface to a Google Drive folder
    GDStore,  # read-write MutableMapping interface to a Google Drive folder
    drive_from_service_account,  # headless auth: build a GoogleDrive from an SA key
    xlsx_to_google_sheet,  # upload an .xlsx as a native Google Sheet -> URL
    GOOGLE_MIME,  # office-ext -> Google-native editor mimetype map
)
