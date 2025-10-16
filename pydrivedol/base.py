"""
Base objects for pydrivedol: simple download function, GDReader, GDStore.

"""

import os
import re
import tempfile
from pathlib import Path
from typing import Optional, Union
from collections.abc import Mapping, MutableMapping

import requests

# TODO: Make pydrive2 an optional dependency in setup.cfg
# Optional PyDrive2 for API-based access
try:
    from pydrive2.auth import GoogleAuth
    from pydrive2.drive import GoogleDrive

    _PYDRIVE2_AVAILABLE = True
except ImportError:
    _PYDRIVE2_AVAILABLE = False


# =============================================================================
# Helper Functions
# =============================================================================


def _extract_file_id(url: str) -> Optional[str]:
    """
    Extract Google Drive file ID from URL.

    >>> _extract_file_id('https://drive.google.com/file/d/ABC123/view')
    'ABC123'
    """
    patterns = [
        r'drive\.google\.com/file/d/([^/]+)',
        r'drive\.google\.com/open\?id=([^&]+)',
        r'drive\.google\.com/uc\?.*id=([^&]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def _extract_folder_id(url: str) -> Optional[str]:
    """
    Extract Google Drive folder ID from URL.

    >>> _extract_folder_id('https://drive.google.com/drive/folders/ABC123')
    'ABC123'
    """
    pattern = r'drive\.google\.com/drive/(?:u/\d+/)?folders/([^?]+)'
    match = re.search(pattern, url)
    return match.group(1) if match else None


def _resolve_cache_dir(use_cache: Union[bool, str]) -> Optional[str]:
    """Get cache directory path, creating if needed."""
    if use_cache is False:
        return None
    if use_cache is True:
        cache_dir = os.path.expanduser('~/.cache/pydrivedol/cached/')
    else:
        cache_dir = use_cache
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def _get_cached_path(file_id: str, cache_dir: str) -> str:
    """Get path for cached file."""
    return os.path.join(cache_dir, file_id)


# =============================================================================
# Simple Download (No API Required)
# =============================================================================


def get_bytes(
    url: str,
    *,
    local_path: Union[bool, str] = False,
    use_cache: Union[bool, str] = False,
) -> Union[bytes, str]:
    """
    Download bytes from public Google Drive URL.

    Works with publicly shared files, no API setup required.

    Args:
        url: Google Drive shared link
        local_path: False (return bytes), True (save to temp), or str (save to path)
        use_cache: False (no cache), True (use ~/.cache/pydrivedol/cached/), or str (use dir)

    Returns:
        bytes if local_path is False or str, filepath str if local_path is True

    >>> content = get_bytes(url)  # doctest: +SKIP
    >>> path = get_bytes(url, local_path=True)  # doctest: +SKIP
    >>> content = get_bytes(url, local_path='/tmp/file.txt')  # doctest: +SKIP
    """
    file_id = _extract_file_id(url)
    if not file_id:
        raise ValueError(f"Could not extract file ID from URL: {url}")

    # Check cache
    cache_dir = _resolve_cache_dir(use_cache)
    if cache_dir:
        cached_file = _get_cached_path(file_id, cache_dir)
        if os.path.exists(cached_file):
            content = Path(cached_file).read_bytes()
            return _handle_local_path_output(content, local_path, cached_file)

    # Download
    content = _download_from_drive(file_id)

    # Cache if requested
    if cache_dir:
        Path(cached_file).write_bytes(content)

    return _handle_local_path_output(content, local_path, None)


def _download_from_drive(file_id: str) -> bytes:
    """Download file content from Google Drive."""
    download_url = f'https://drive.google.com/uc?export=download&id={file_id}'

    session = requests.Session()
    response = session.get(download_url, stream=True)

    # Handle virus scan warning for large files
    if 'download_warning' in response.text or 'virus' in response.text.lower():
        for key, value in response.cookies.items():
            if key.startswith('download_warning'):
                params = {'id': file_id, 'confirm': value}
                response = session.get(download_url, params=params, stream=True)
                break

    if response.status_code != 200:
        raise RuntimeError(f"Download failed. Status: {response.status_code}")

    return response.content


def _handle_local_path_output(
    content: bytes, local_path: Union[bool, str], cached_file: Optional[str]
) -> Union[bytes, str]:
    """Handle local_path argument logic."""
    if local_path is True:
        if cached_file and os.path.exists(cached_file):
            return cached_file
        with tempfile.NamedTemporaryFile(delete=False, suffix='') as tmp:
            tmp.write(content)
            return tmp.name
    elif isinstance(local_path, str):
        os.makedirs(os.path.dirname(local_path) or '.', exist_ok=True)
        Path(local_path).write_bytes(content)
        return content
    else:
        return content


# =============================================================================
# API-Based Classes
# =============================================================================


def _require_pydrive2():
    """Raise ImportError if PyDrive2 not available."""
    if not _PYDRIVE2_AVAILABLE:
        raise ImportError(
            "PyDrive2 required for GDReader/GDStore. " "Install: pip install pydrive2"
        )


def _init_google_drive(
    credentials_file: str = 'client_secrets.json',
    settings_file: str = 'settings.yaml',
):
    """Initialize and authenticate Google Drive."""
    gauth = GoogleAuth()
    gauth.LoadCredentialsFile(credentials_file)

    if gauth.credentials is None:
        gauth.LocalWebserverAuth()
    elif gauth.access_token_expired:
        gauth.Refresh()
    else:
        gauth.Authorize()

    gauth.SaveCredentialsFile(credentials_file)
    return GoogleDrive(gauth)


class GDReader(Mapping):
    """
    Read-only Mapping to Google Drive folder.

    Keys are relative file paths, values are file contents as bytes.

    >>> reader = GDReader(folder_url)  # doctest: +SKIP
    >>> list(reader)[:3]  # doctest: +SKIP
    >>> content = reader['path/to/file.txt']  # doctest: +SKIP
    >>> len(reader)  # doctest: +SKIP
    >>> 'file.txt' in reader  # doctest: +SKIP
    >>> url = reader.get_url('file.txt')  # doctest: +SKIP
    """

    def __init__(
        self,
        folder_url: str,
        *,
        max_levels: Optional[int] = None,
        credentials_file: str = 'client_secrets.json',
        settings_file: str = 'settings.yaml',
        include_hidden: bool = False,
    ):
        """
        Initialize reader.

        Args:
            folder_url: Google Drive folder URL
            max_levels: Recursion depth (None=infinite, 0=files only)
            credentials_file: OAuth2 credentials path
            settings_file: Auth settings path
            include_hidden: Include files starting with '.'
        """
        _require_pydrive2()

        self.folder_url = folder_url
        self.folder_id = _extract_folder_id(folder_url)
        if not self.folder_id:
            raise ValueError(f"Invalid folder URL: {folder_url}")

        self.max_levels = max_levels
        self.include_hidden = include_hidden
        self._credentials_file = credentials_file
        self._settings_file = settings_file

        self._drive = _init_google_drive(credentials_file, settings_file)
        self._file_cache = None

    def _list_files(self, folder_id: str, prefix: str = '', level: int = 0):
        """Recursively list files in folder."""
        if self.max_levels is not None and level > self.max_levels:
            return

        query = f"'{folder_id}' in parents and trashed=false"
        file_list = self._drive.ListFile({'q': query}).GetList()

        for item in file_list:
            name = item['title']
            if not self.include_hidden and name.startswith('.'):
                continue

            item_path = os.path.join(prefix, name) if prefix else name

            if item['mimeType'] == 'application/vnd.google-apps.folder':
                if self.max_levels is None or level < self.max_levels:
                    yield from self._list_files(item['id'], item_path, level + 1)
            else:
                yield (item_path, item['id'])

    @property
    def _files(self):
        """Cached file listing."""
        if self._file_cache is None:
            self._file_cache = dict(self._list_files(self.folder_id))
        return self._file_cache

    def _refresh_cache(self):
        """Clear file cache."""
        self._file_cache = None

    def __iter__(self):
        return iter(self._files)

    def __len__(self):
        return len(self._files)

    def __contains__(self, key):
        return key in self._files

    def __getitem__(self, key: str) -> bytes:
        """Get file content as bytes."""
        if key not in self._files:
            raise KeyError(f"File not found: {key}")

        file_id = self._files[key]
        gfile = self._drive.CreateFile({'id': file_id})

        # Download as bytes
        content = gfile.GetContentString(mimetype='application/octet-stream')
        if isinstance(content, str):
            content = content.encode('latin-1')

        return content

    def get_url(
        self,
        key: str,
        *,
        permission_type: str = 'anyone',
        permission_role: str = 'reader',
    ) -> str:
        """
        Get shareable URL for file.

        Args:
            key: File path
            permission_type: 'anyone', 'user', 'group', 'domain'
            permission_role: 'reader', 'writer', 'commenter'

        Returns:
            Shareable URL
        """
        if key not in self._files:
            raise KeyError(f"File not found: {key}")

        file_id = self._files[key]
        gfile = self._drive.CreateFile({'id': file_id})

        gfile.InsertPermission(
            {
                'type': permission_type,
                'value': permission_type if permission_type == 'anyone' else None,
                'role': permission_role,
            }
        )

        return gfile['alternateLink']


class GDStore(GDReader, MutableMapping):
    """
    Read-write MutableMapping to Google Drive folder.

    Extends GDReader with write and delete operations.

    >>> store = GDStore(folder_url)  # doctest: +SKIP
    >>> store['file.txt'] = b'Hello'  # doctest: +SKIP
    >>> store['dir/file.txt'] = b'Nested'  # doctest: +SKIP
    >>> del store['file.txt']  # doctest: +SKIP
    """

    def _get_or_create_folders(self, key: str) -> str:
        """
        Create nested folders as needed, return parent folder ID.

        Args:
            key: File path like 'dir1/dir2/file.txt'

        Returns:
            Parent folder ID
        """
        parts = key.split('/')
        folder_parts = parts[:-1]

        current_id = self.folder_id

        for folder_name in folder_parts:
            query = (
                f"'{current_id}' in parents "
                f"and title='{folder_name}' "
                f"and mimeType='application/vnd.google-apps.folder' "
                f"and trashed=false"
            )
            folders = self._drive.ListFile({'q': query}).GetList()

            if folders:
                current_id = folders[0]['id']
            else:
                folder = self._drive.CreateFile(
                    {
                        'title': folder_name,
                        'parents': [{'id': current_id}],
                        'mimeType': 'application/vnd.google-apps.folder',
                    }
                )
                folder.Upload()
                current_id = folder['id']

        return current_id

    def __setitem__(self, key: str, value: bytes):
        """Write bytes to file, creating folders as needed."""
        if not isinstance(value, bytes):
            raise TypeError(f"Value must be bytes, got {type(value)}")

        parent_id = self._get_or_create_folders(key)
        filename = os.path.basename(key)

        # Check if file exists
        query = (
            f"'{parent_id}' in parents " f"and title='{filename}' " f"and trashed=false"
        )
        files = self._drive.ListFile({'q': query}).GetList()

        if files:
            # Update existing
            gfile = files[0]
        else:
            # Create new
            gfile = self._drive.CreateFile(
                {'title': filename, 'parents': [{'id': parent_id}]}
            )

        gfile.SetContentString(value.decode('latin-1'))
        gfile.Upload()

        self._refresh_cache()

    def __delitem__(self, key: str):
        """Delete file."""
        if key not in self._files:
            raise KeyError(f"File not found: {key}")

        file_id = self._files[key]
        gfile = self._drive.CreateFile({'id': file_id})
        gfile.Delete()

        self._refresh_cache()
