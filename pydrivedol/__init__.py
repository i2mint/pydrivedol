"""
Google Drive Data Object Layer

Provides Mapping and MutableMapping interfaces to Google Drive data.

Key Features:
- get_bytes(url): Download bytes from public Google Drive URLs (no API setup needed)
- GDReader: Read-only Mapping interface to a Google Drive folder
- GDStore: Read-write MutableMapping interface to a Google Drive folder

Setup (optional) for API-based features (GDReader/GDStore):
1. pip install pydrive2
2. Go to https://console.cloud.google.com/
3. Create project, enable Google Drive API
4. Create OAuth 2.0 credentials (Desktop app), download client_secrets.json
5. First run opens browser for authentication

Usage:

    Simple download (no API needed)

    >>> content = get_bytes(url)  # doctest: +SKIP
    >>> path = get_bytes(url, local_path=True)  # doctest: +SKIP

    Read folder

    >>> reader = GDReader(folder_url)  # doctest: +SKIP
    >>> list(reader)  # doctest: +SKIP
    >>> content = reader['path/to/file.txt']  # doctest: +SKIP

    Write to folder

    >>> store = GDStore(folder_url)  # doctest: +SKIP
    >>> store['file.txt'] = b'content'  # doctest: +SKIP
    >>> del store['file.txt']  # doctest: +SKIP

"""

from pydrivedol.base import (
    get_bytes,  # simple download function
    # Needing API setup:
    GDReader,  # read-only Mapping interface to a Google Drive folder
    GDStore,  # read-write MutableMapping interface to a Google Drive folder
)
