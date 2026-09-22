"""
Base objects for pydrivedol: download functions, GDFiles, GDReader, GDStore.

Two access levels, both returning ``bytes``:

- **Public, no setup**: :func:`get_bytes` against Google's unauthenticated download endpoint.
  It raises :class:`NotPubliclyShared` rather than handing back the HTML sign-in page Drive
  serves (with HTTP 200) when the file is not shared publicly.
- **Authenticated**: pass a PyDrive2 ``GoogleDrive`` -- from :func:`drive_from_service_account`
  for headless use -- as ``drive=`` to :func:`get_bytes` / :func:`get_metadata`, or build a
  :class:`GDFiles` (file-level Mapping, keyed by file id or URL), :class:`GDReader` /
  :class:`GDStore` (folder-level, keyed by relative path).

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
# Errors
# =============================================================================


class NotPubliclyShared(RuntimeError):
    """Raised when an unauthenticated download returns a sign-in page instead of file content.

    Google serves its HTML sign-in / permission interstitial with HTTP **200**, so without an
    explicit check that page body would be returned as if it were the file: plausible-looking
    bytes that only blow up much later, in whatever tries to parse them. Catch this to fall
    back to an authenticated fetch (``get_bytes(url, drive=...)``).
    """


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
        r"drive\.google\.com/file/d/([A-Za-z0-9_-]+)",
        r"drive\.google\.com/open\?id=([A-Za-z0-9_-]+)",
        r"drive\.google\.com/uc\?.*id=([A-Za-z0-9_-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def _q(value) -> str:
    """Quote *value* as a string literal in the Drive search-query language.

    Backslashes and single quotes are escaped, so a file or folder name such as
    ``x' or title contains '`` stays one literal instead of rewriting the query
    (which would let a key select -- and ``__setitem__`` overwrite -- files
    outside the store's folder).

    >>> _q("it's")
    "'it\\\\'s'"
    """
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def _extract_folder_id(url: str) -> Optional[str]:
    """
    Extract Google Drive folder ID from URL.

    >>> _extract_folder_id('https://drive.google.com/drive/folders/ABC123')
    'ABC123'
    """
    pattern = r"drive\.google\.com/drive/(?:u/\d+/)?folders/([A-Za-z0-9_-]+)"
    match = re.search(pattern, url)
    return match.group(1) if match else None


#: A bare Drive file id: URL-safe base64-ish, and long enough not to be a typo'd URL.
_FILE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{10,}$")


def _resolve_file_id(url_or_id: str) -> str:
    """Normalise a file key -- a Drive file URL *or* a bare file id -- to a file id.

    URLs are parsed with :func:`_extract_file_id`; anything else is accepted only if it looks
    like a Drive id, so that a malformed URL still fails loudly instead of being sent to the
    API as a nonsense id.

    >>> _resolve_file_id('https://drive.google.com/file/d/1AbCdEfGhIjKlMnOp/view')
    '1AbCdEfGhIjKlMnOp'
    >>> _resolve_file_id('1AbCdEfGhIjKlMnOp')
    '1AbCdEfGhIjKlMnOp'
    """
    file_id = _extract_file_id(url_or_id)
    if file_id:
        return file_id
    if _FILE_ID_PATTERN.match(url_or_id):
        return url_or_id
    raise ValueError(
        f"Not a Google Drive file URL or file id: {url_or_id!r}. Expected something like "
        "'https://drive.google.com/file/d/<id>/view' or the bare '<id>'."
    )


def _is_not_found(error: BaseException) -> bool:
    """Whether a Drive API error means "no such file" rather than a transient failure.

    Used to keep the Mapping contract honest: a genuinely missing file becomes ``KeyError``,
    while a 5xx / auth / network failure is left to propagate as itself.

    >>> _is_not_found(Exception('<HttpError 404 ... "File not found: abc">'))
    True
    >>> _is_not_found(Exception('<HttpError 500 ... "Backend Error">'))
    False
    """
    text = str(error).lower()
    return "404" in text or "not found" in text or "notfound" in text


def _resolve_cache_dir(use_cache: Union[bool, str]) -> Optional[str]:
    """Get cache directory path, creating if needed."""
    if use_cache is False:
        return None
    if use_cache is True:
        cache_dir = os.path.expanduser("~/.cache/pydrivedol/cached/")
    else:
        cache_dir = use_cache
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def _get_cached_path(file_id: str, cache_dir: str) -> str:
    """Get path for cached file."""
    return os.path.join(cache_dir, file_id)


# =============================================================================
# HTML-interstitial detection (the "silent success" guard)
# =============================================================================

#: Content type Drive declares for its sign-in / confirmation pages.
_HTML_CONTENT_TYPE = "text/html"
#: Document prefixes that mark a payload as an HTML page rather than file bytes.
_HTML_BODY_PREFIXES = (b"<!doctype html", b"<html")
#: How much of the body to sniff for those prefixes.
_HTML_SNIFF_NBYTES = 64


def _looks_like_html(content: bytes, content_type: str = "") -> bool:
    """Whether a downloaded payload is an HTML page rather than raw file bytes.

    True when the declared content type is HTML, or when the body itself opens with an HTML
    document prefix. Leading whitespace and a UTF-8 BOM are tolerated; matching is
    case-insensitive.

    >>> _looks_like_html(b'id,name', 'text/csv')
    False
    >>> _looks_like_html(b'  <!DOCTYPE HTML><html><head>...')
    True
    >>> _looks_like_html(b'anything at all', 'text/html; charset=utf-8')
    True
    """
    if _HTML_CONTENT_TYPE in content_type.lower():
        return True
    head = content[:_HTML_SNIFF_NBYTES].lstrip(b"\xef\xbb\xbf").lstrip().lower()
    return head.startswith(_HTML_BODY_PREFIXES)


def _not_publicly_shared_message(file_id: str) -> str:
    """Compose the actionable error text for an HTML payload from the public endpoint."""
    return (
        f"Google Drive returned an HTML page, not file content, for file id {file_id!r}. "
        "That page is Google's sign-in / permission interstitial, served with HTTP 200, so the "
        "download 'succeeded' with the wrong bytes. It means the file is not shared publicly "
        "and the unauthenticated endpoint cannot reach it (it can also be Drive's large-file "
        "confirmation page).\n"
        "Fix -- authenticate and pass a drive= client:\n"
        "    from pydrivedol import drive_from_service_account, get_bytes\n"
        "    drive = drive_from_service_account('service-account-key.json')\n"
        "    content = get_bytes(url, drive=drive)\n"
        "...having shared the file (or its folder) with the service account's client_email.\n"
        "If you really are downloading an HTML file, pass allow_html=True."
    )


# =============================================================================
# Simple Download (No API Required)
# =============================================================================


def get_bytes(
    url: str,
    *,
    local_path: Union[bool, str] = False,
    use_cache: Union[bool, str] = False,
    drive=None,
    allow_html: bool = False,
) -> Union[bytes, str]:
    """
    Download bytes from a Google Drive URL.

    Without ``drive`` this uses Google's public download endpoint -- no API setup, but it only
    reaches files shared "anyone with the link", and it raises :class:`NotPubliclyShared` if
    Drive answers with its sign-in page instead of the file. Pass an authenticated ``drive``
    (see :func:`drive_from_service_account`) to reach **private** files shared with that
    identity.

    Args:
        url: Google Drive file link (a bare file id is accepted too).
        local_path: False (return bytes), True (save to temp), or str (save to path)
        use_cache: False (no cache), True (use ~/.cache/pydrivedol/cached/), or str (use dir)
        drive: an authenticated PyDrive2 ``GoogleDrive``. When given, the download goes through
            the API; ``None`` (default) keeps the public, unauthenticated behaviour exactly.
        allow_html: by default an HTML payload from the *public* endpoint raises, because it is
            Google's login page masquerading as file content. Set True only when the file you
            are downloading genuinely is HTML. Ignored on the authenticated path.

    Returns:
        bytes if local_path is False or str, filepath str if local_path is True

    Raises:
        NotPubliclyShared: the public endpoint returned a sign-in page; pass ``drive=``.

    >>> content = get_bytes(url)  # doctest: +SKIP
    >>> path = get_bytes(url, local_path=True)  # doctest: +SKIP
    >>> content = get_bytes(url, local_path='/tmp/file.txt')  # doctest: +SKIP

    A private file, shared with a service account:

    >>> drive = drive_from_service_account('service-account-key.json')  # doctest: +SKIP
    >>> content = get_bytes(private_url, drive=drive)  # doctest: +SKIP
    """
    file_id = _resolve_file_id(url)

    # Check cache
    cache_dir = _resolve_cache_dir(use_cache)
    cached_file = _get_cached_path(file_id, cache_dir) if cache_dir else None
    if cached_file and os.path.exists(cached_file):
        content = Path(cached_file).read_bytes()
        return _handle_local_path_output(content, local_path, cached_file)

    # Download
    if drive is not None:
        content = _download_via_api(drive, file_id)
    else:
        content = _download_from_drive(file_id, allow_html=allow_html)

    # Cache if requested
    if cached_file:
        Path(cached_file).write_bytes(content)

    return _handle_local_path_output(content, local_path, None)


def _download_from_drive(file_id: str, *, allow_html: bool = False) -> bytes:
    """Download file content from Google Drive's public (unauthenticated) endpoint.

    Guards against the silent-success failure: Drive answers an unauthorised request with its
    HTML sign-in page under HTTP 200, which would otherwise be returned as the file's content.
    """
    download_url = f"https://drive.google.com/uc?export=download&id={file_id}"

    session = requests.Session()
    response = session.get(download_url, stream=True)

    # Handle virus scan warning for large files
    if "download_warning" in response.text or "virus" in response.text.lower():
        for key, value in response.cookies.items():
            if key.startswith("download_warning"):
                params = {"id": file_id, "confirm": value}
                response = session.get(download_url, params=params, stream=True)
                break

    if response.status_code != 200:
        raise RuntimeError(f"Download failed. Status: {response.status_code}")

    content = response.content
    if not allow_html and _looks_like_html(
        content, response.headers.get("Content-Type", "")
    ):
        raise NotPubliclyShared(_not_publicly_shared_message(file_id))

    return content


def _handle_local_path_output(
    content: bytes, local_path: Union[bool, str], cached_file: Optional[str]
) -> Union[bytes, str]:
    """Handle local_path argument logic."""
    if local_path is True:
        if cached_file and os.path.exists(cached_file):
            return cached_file
        with tempfile.NamedTemporaryFile(delete=False, suffix="") as tmp:
            tmp.write(content)
            return tmp.name
    elif isinstance(local_path, str):
        os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
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
            "PyDrive2 required for GDReader/GDStore. Install: pip install pydrive2"
        )


def _init_google_drive(
    credentials_file: str = "client_secrets.json",
    settings_file: str = "settings.yaml",
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


def drive_from_service_account(
    key_file: str,
    *,
    scopes=("https://www.googleapis.com/auth/drive",),
    subject: Optional[str] = None,
):
    """Build an authenticated ``GoogleDrive`` from a service-account key file.

    For headless / server use — no browser OAuth flow. Share the target Drive folder
    with the service account's ``client_email`` (Viewer for read, Editor for write).
    Pass the resulting drive to ``GDReader``/``GDStore`` via their ``drive=`` argument.

    Args:
        key_file: path to the service-account JSON key.
        scopes: OAuth scopes; default is full Drive (use ``.../auth/drive.readonly``
            to enforce read-only at the token level).
        subject: optional user email to impersonate (domain-wide delegation).

    >>> drive = drive_from_service_account('sa-key.json')   # doctest: +SKIP
    >>> reader = GDReader(folder_url, drive=drive)           # doctest: +SKIP
    """
    _require_pydrive2()
    service_config = {"client_json_file_path": key_file}
    if subject:
        service_config["client_user_email"] = subject
    gauth = GoogleAuth(
        settings={
            "client_config_backend": "service",
            "service_config": service_config,
            "oauth_scope": list(scopes),
        }
    )
    gauth.ServiceAuth()
    return GoogleDrive(gauth)


# =============================================================================
# Authenticated access (needs a ``drive``)
# =============================================================================

#: Drive's mimeType for a folder -- the marker that a listing entry should be recursed into.
_FOLDER_MIMETYPE = "application/vnd.google-apps.folder"

#: Metadata fields fetched by default: enough to decide whether a download is worth making.
DEFAULT_METADATA_FIELDS = (
    "id",
    "title",
    "mimeType",
    "fileSize",
    "modifiedDate",
    "alternateLink",
)

#: Metadata the Drive API returns as decimal strings but that are natural numbers.
_INTEGER_METADATA_FIELDS = ("fileSize", "quotaBytesUsed", "version")


def _download_via_api(drive, file_id: str) -> bytes:
    """Download a file's content through the authenticated Drive API.

    Streams the content chunk by chunk into memory via PyDrive2's ``GetContentIOBuffer`` --
    byte-exact (no text decode/encode round trip, which corrupts binaries) and with no
    temporary file on disk.

    ``drive`` is injected (a PyDrive2 ``GoogleDrive``) so this stays pure and unit-testable.
    """
    gfile = drive.CreateFile({"id": file_id})
    return b"".join(chunk for chunk in gfile.GetContentIOBuffer() if chunk)


def _normalized_metadata(gfile, fields) -> dict:
    """Pick ``fields`` out of a fetched PyDrive2 file, coercing numeric strings to ``int``."""
    metadata = {field: gfile[field] for field in fields if field in gfile}
    for field in _INTEGER_METADATA_FIELDS:
        value = metadata.get(field)
        if isinstance(value, str) and value.isdigit():
            metadata[field] = int(value)
    return metadata


def get_metadata(url_or_id: str, *, drive, fields=DEFAULT_METADATA_FIELDS) -> dict:
    """Fetch a Drive file's metadata **without downloading its content**.

    The cheap half of :func:`get_bytes`: use it to decide *whether* to download -- an 18MB
    spreadsheet is not something you fetch just to learn its name.

    Args:
        url_or_id: a Drive file URL or a bare file id.
        drive: an authenticated PyDrive2 ``GoogleDrive`` (see
            :func:`drive_from_service_account`).
        fields: which metadata fields to request; ``None`` fetches everything Drive offers.
            The default, :data:`DEFAULT_METADATA_FIELDS`, covers name (``title``), ``fileSize``,
            ``mimeType`` and ``modifiedDate``.

    Returns:
        A plain ``dict`` of the requested fields that the file actually has. ``fileSize`` is
        returned as an ``int`` (Drive sends it as a string), and is **absent** for
        Google-native files -- Sheets/Docs/Slides have no stored byte size.

    >>> drive = drive_from_service_account('service-account-key.json')  # doctest: +SKIP
    >>> info = get_metadata(url, drive=drive)  # doctest: +SKIP
    >>> info['title'], info['fileSize']  # doctest: +SKIP
    ('client_export.xlsx', 18512345)
    """
    file_id = _resolve_file_id(url_or_id)
    gfile = drive.CreateFile({"id": file_id})
    if fields:
        gfile.FetchMetadata(fields=",".join(fields))
        wanted = fields
    else:
        gfile.FetchMetadata(fetch_all=True)
        wanted = tuple(gfile.keys())
    return _normalized_metadata(gfile, wanted)


def _iter_folder_files(
    drive,
    folder_id: str,
    *,
    max_levels: Optional[int] = None,
    include_hidden: bool = False,
    prefix: str = "",
    level: int = 0,
):
    """Yield ``(relative_path, file_id)`` for every file under ``folder_id``.

    Recurses into subfolders up to ``max_levels`` (``None`` = unlimited, ``0`` = this folder
    only). ``drive`` is injected so the traversal is shared by :class:`GDFiles` and
    :class:`GDReader` rather than duplicated in each.
    """
    if max_levels is not None and level > max_levels:
        return

    query = f"{_q(folder_id)} in parents and trashed=false"
    for item in drive.ListFile({"q": query}).GetList():
        name = item["title"]
        if not include_hidden and name.startswith("."):
            continue

        item_path = os.path.join(prefix, name) if prefix else name

        if item["mimeType"] == _FOLDER_MIMETYPE:
            if max_levels is None or level < max_levels:
                yield from _iter_folder_files(
                    drive,
                    item["id"],
                    max_levels=max_levels,
                    include_hidden=include_hidden,
                    prefix=item_path,
                    level=level + 1,
                )
        else:
            yield (item_path, item["id"])


# Office → Google-native editor MIME types (the target when ``convert=True``).
GOOGLE_MIME = {
    ".xlsx": "application/vnd.google-apps.spreadsheet",
    ".xls": "application/vnd.google-apps.spreadsheet",
    ".csv": "application/vnd.google-apps.spreadsheet",
    ".docx": "application/vnd.google-apps.document",
    ".doc": "application/vnd.google-apps.document",
    ".pptx": "application/vnd.google-apps.presentation",
    ".ppt": "application/vnd.google-apps.presentation",
}


def _upload_converting(
    drive,
    *,
    parent_id: Optional[str],
    title: str,
    content: Optional[bytes] = None,
    path: Optional[str] = None,
    convert: bool = False,
    google_mimetype: Optional[str] = None,
    file_id: Optional[str] = None,
):
    """Create/update a Drive file from ``content`` (bytes) or a ``path``, optionally converting.

    When ``convert`` is True the uploaded office file is converted to the corresponding **Google
    editor format** — ``.xlsx`` → a *native Google Sheet*, ``.docx`` → Doc, ``.pptx`` → Slides —
    so you get an editable Google file rather than an uploaded blob. The target type defaults to
    the extension mapping in :data:`GOOGLE_MIME`; pass ``google_mimetype`` to force it. Pass
    ``file_id`` to update an existing file in place.

    ``drive`` is injected (a PyDrive2 ``GoogleDrive``) so this stays pure and unit-testable.
    Returns the uploaded PyDrive2 ``GoogleFile``.
    """
    if content is None and path is None:
        raise ValueError("provide either content (bytes) or path")
    meta = {"title": title}
    if file_id:
        meta["id"] = file_id
    elif parent_id:
        meta["parents"] = [{"id": parent_id}]
    if convert:
        if google_mimetype is None:
            ext = os.path.splitext(path or title)[1].lower()
            google_mimetype = GOOGLE_MIME.get(ext)
        if google_mimetype:
            meta["mimeType"] = google_mimetype
    gfile = drive.CreateFile(meta)
    tmp_to_clean = None
    try:
        if path is not None:
            gfile.SetContentFile(path)
        else:
            suffix = os.path.splitext(title)[1] or ""
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(content)
                tmp_to_clean = tmp.name
            gfile.SetContentFile(tmp_to_clean)
        # In Drive v2, param={'convert': True} converts the uploaded media to the Google type.
        gfile.Upload(param={"convert": True} if convert else {})
    finally:
        if tmp_to_clean and os.path.exists(tmp_to_clean):
            os.remove(tmp_to_clean)
    return gfile


_UNSCOPED_ITERATION_MESSAGE = (
    "GDFiles has no folder scope, so it cannot be listed: an unscoped instance addresses the "
    "whole Drive, which is unbounded and paginated. Lookup (files[key], key in files, "
    "files.get(key)) works without a scope; to iterate, construct with "
    "GDFiles(drive, folder_url='https://drive.google.com/drive/folders/<id>')."
)


class GDFiles(Mapping):
    """Read-only Mapping of Google Drive **files**, keyed by file id or file URL.

    The file-level sibling of :class:`GDReader`. Where ``GDReader`` is scoped to a folder and
    keyed by relative path, ``GDFiles`` is keyed by whatever identifies a single file: a bare
    file id, or any Drive file URL -- both normalise to the same key through
    :func:`_extract_file_id`, so ``files[url]`` and ``files[file_id]`` are one entry. Values
    are ``bytes``, fetched over the authenticated API, so **private** files work as long as
    they are shared with the authenticated identity.

    That is the shape a caller has when files arrive as *links* -- the usual Drive sharing
    idiom -- rather than as a folder listing.

    ``drive`` is required and injected: a file-level view is pointless without auth, since its
    whole reason to exist is reaching files the public endpoint cannot.

    **Iteration requires a scope.** Unscoped, this mapping covers the entire Drive, which is
    unbounded and paginated; enumerating it is never what a caller wants, so offering it would
    be a trap. ``__iter__``/``__len__`` therefore raise ``NotImplementedError`` unless
    ``folder_url`` is given, in which case they yield that folder's file **ids** (honouring
    ``max_levels`` and ``include_hidden``, the same traversal :class:`GDReader` uses). Lookup
    always works, scoped or not -- it is the primary use case and needs no listing.

    >>> drive = drive_from_service_account('service-account-key.json')  # doctest: +SKIP
    >>> files = GDFiles(drive)  # doctest: +SKIP
    >>> files.metadata(url)['fileSize']  # cheap: no download  # doctest: +SKIP
    >>> content = files[url]  # or files[file_id]  # doctest: +SKIP
    >>> url in files  # metadata probe, not a download  # doctest: +SKIP
    True

    Scoped, so it can be listed:

    >>> scoped = GDFiles(drive, folder_url=folder_url)  # doctest: +SKIP
    >>> list(scoped)  # file ids  # doctest: +SKIP
    """

    def __init__(
        self,
        drive,
        *,
        folder_url: Optional[str] = None,
        max_levels: Optional[int] = None,
        include_hidden: bool = False,
    ):
        """
        Initialize a file-level mapping.

        Args:
            drive: an authenticated PyDrive2 ``GoogleDrive`` (see
                :func:`drive_from_service_account`). Required.
            folder_url: optional Drive folder URL scoping ``__iter__``/``__len__``. Without it
                those raise; lookup is unaffected.
            max_levels: recursion depth for the scope (None=infinite, 0=files only)
            include_hidden: include files starting with '.'
        """
        self._drive = drive
        self.folder_url = folder_url
        self.folder_id = _extract_folder_id(folder_url) if folder_url else None
        if folder_url and not self.folder_id:
            raise ValueError(f"Invalid folder URL: {folder_url}")
        self.max_levels = max_levels
        self.include_hidden = include_hidden
        self._file_cache = None

    @property
    def _file_ids(self):
        """Cached file ids of the scoping folder; raises if there is no scope."""
        if self.folder_id is None:
            raise NotImplementedError(_UNSCOPED_ITERATION_MESSAGE)
        if self._file_cache is None:
            listing = _iter_folder_files(
                self._drive,
                self.folder_id,
                max_levels=self.max_levels,
                include_hidden=self.include_hidden,
            )
            # dict.fromkeys: dedupe (Drive files can have several parents) keeping order
            self._file_cache = list(dict.fromkeys(file_id for _, file_id in listing))
        return self._file_cache

    def _refresh_cache(self):
        """Forget the cached folder listing; the next iteration re-lists."""
        self._file_cache = None

    def __iter__(self):
        return iter(self._file_ids)

    def __len__(self):
        return len(self._file_ids)

    def __contains__(self, key: str) -> bool:
        """Whether the file exists and is reachable -- a metadata probe, never a download."""
        try:
            self.metadata(key, fields=("id",))
        except ValueError:
            return False  # not a usable file key at all
        except Exception as error:
            if _is_not_found(error):
                return False
            raise  # auth / network / server failures are not "absent"
        return True

    def __getitem__(self, key: str) -> bytes:
        """The file's content as bytes, downloaded over the authenticated API."""
        file_id = _resolve_file_id(key)
        try:
            return _download_via_api(self._drive, file_id)
        except Exception as error:
            if _is_not_found(error):
                raise KeyError(f"File not found or not accessible: {key}") from error
            raise

    def metadata(self, key: str, *, fields=DEFAULT_METADATA_FIELDS) -> dict:
        """Metadata (name, size, mimeType, modifiedDate) for ``key``, without downloading it.

        Thin method form of :func:`get_metadata` -- see it for the field semantics.
        """
        return get_metadata(key, drive=self._drive, fields=fields)


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
        credentials_file: str = "client_secrets.json",
        settings_file: str = "settings.yaml",
        include_hidden: bool = False,
        drive=None,
    ):
        """
        Initialize reader.

        Args:
            folder_url: Google Drive folder URL
            max_levels: Recursion depth (None=infinite, 0=files only)
            credentials_file: OAuth2 credentials path
            settings_file: Auth settings path
            include_hidden: Include files starting with '.'
            drive: a pre-authenticated ``GoogleDrive`` (e.g. from
                ``drive_from_service_account``). When given, the OAuth
                ``credentials_file``/``settings_file`` flow is skipped.
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

        self._drive = (
            drive
            if drive is not None
            else _init_google_drive(credentials_file, settings_file)
        )
        self._file_cache = None

    def _list_files(self, folder_id: str, prefix: str = "", level: int = 0):
        """Recursively list ``(relative_path, file_id)`` pairs under ``folder_id``."""
        yield from _iter_folder_files(
            self._drive,
            folder_id,
            max_levels=self.max_levels,
            include_hidden=self.include_hidden,
            prefix=prefix,
            level=level,
        )

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
        """Get file content as bytes.

        Goes through :func:`_download_via_api`, which is byte-exact: the previous
        ``GetContentString(...).encode('latin-1')`` route decoded as utf-8 first, so it
        corrupted (or raised on) every real binary -- xlsx, pdf, images.
        """
        if key not in self._files:
            raise KeyError(f"File not found: {key}")

        return _download_via_api(self._drive, self._files[key])

    def get_url(
        self,
        key: str,
        *,
        permission_type: str = "anyone",
        permission_role: str = "reader",
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
        gfile = self._drive.CreateFile({"id": file_id})

        gfile.InsertPermission(
            {
                "type": permission_type,
                "value": permission_type if permission_type == "anyone" else None,
                "role": permission_role,
            }
        )

        return gfile["alternateLink"]


class GDStore(GDReader, MutableMapping):
    """
    Read-write MutableMapping to Google Drive folder.

    Extends GDReader with write and delete operations.

    >>> store = GDStore(folder_url)  # doctest: +SKIP
    >>> store['file.txt'] = b'Hello'  # doctest: +SKIP
    >>> store['dir/file.txt'] = b'Nested'  # doctest: +SKIP
    >>> del store['file.txt']  # doctest: +SKIP

    Pass ``convert_office=True`` to make ``store['x.xlsx'] = xlsx_bytes`` create a *native
    Google Sheet* (xlsx → Sheet, docx → Doc, pptx → Slides) instead of an uploaded blob. For
    one-off control use :meth:`upload` with ``convert=True``.
    """

    def __init__(self, folder_url: str, *, convert_office: bool = False, **kwargs):
        """Like :class:`GDReader`, plus ``convert_office`` (default off, backward-compatible):
        when True, office uploads are converted to their native Google editor type."""
        super().__init__(folder_url, **kwargs)
        self.convert_office = convert_office

    def upload(
        self,
        key: str,
        value: Optional[bytes] = None,
        *,
        path: Optional[str] = None,
        convert: Optional[bool] = None,
        google_mimetype: Optional[str] = None,
    ) -> str:
        """Upload ``value`` (bytes) or a file ``path`` to ``key``; return the shareable URL.

        With ``convert=True`` (or the store's ``convert_office`` default) an office file becomes a
        native Google doc — e.g. ``store.upload('schema.xlsx', xlsx_bytes, convert=True)`` yields a
        Google Sheet. Updates an existing same-named file in the target folder, else creates it.
        """
        if convert is None:
            convert = self.convert_office
        parent_id = self._get_or_create_folders(key)
        filename = os.path.basename(key)
        query = f"{_q(parent_id)} in parents and title={_q(filename)} and trashed=false"
        existing = self._drive.ListFile({"q": query}).GetList()
        file_id = existing[0]["id"] if existing else None
        gfile = _upload_converting(
            self._drive,
            parent_id=parent_id,
            title=filename,
            content=value,
            path=path,
            convert=convert,
            google_mimetype=google_mimetype,
            file_id=file_id,
        )
        self._refresh_cache()
        return gfile["alternateLink"]

    def _get_or_create_folders(self, key: str) -> str:
        """
        Create nested folders as needed, return parent folder ID.

        Args:
            key: File path like 'dir1/dir2/file.txt'

        Returns:
            Parent folder ID
        """
        parts = key.split("/")
        folder_parts = parts[:-1]

        current_id = self.folder_id

        for folder_name in folder_parts:
            query = (
                f"{_q(current_id)} in parents "
                f"and title={_q(folder_name)} "
                f"and mimeType='application/vnd.google-apps.folder' "
                f"and trashed=false"
            )
            folders = self._drive.ListFile({"q": query}).GetList()

            if folders:
                current_id = folders[0]["id"]
            else:
                folder = self._drive.CreateFile(
                    {
                        "title": folder_name,
                        "parents": [{"id": current_id}],
                        "mimeType": "application/vnd.google-apps.folder",
                    }
                )
                folder.Upload()
                current_id = folder["id"]

        return current_id

    def __setitem__(self, key: str, value: bytes):
        """Write bytes to file, creating folders as needed.

        If the store was created with ``convert_office=True`` and ``key`` is an office file, it
        is uploaded as a native Google doc (see :meth:`upload`); otherwise it is stored as raw bytes.
        """
        if not isinstance(value, bytes):
            raise TypeError(f"Value must be bytes, got {type(value)}")

        if getattr(self, "convert_office", False):
            self.upload(key, value, convert=True)
            return

        parent_id = self._get_or_create_folders(key)
        filename = os.path.basename(key)

        # Check if file exists
        query = f"{_q(parent_id)} in parents and title={_q(filename)} and trashed=false"
        files = self._drive.ListFile({"q": query}).GetList()

        if files:
            # Update existing
            gfile = files[0]
        else:
            # Create new
            gfile = self._drive.CreateFile(
                {"title": filename, "parents": [{"id": parent_id}]}
            )

        gfile.SetContentString(value.decode("latin-1"))
        gfile.Upload()

        self._refresh_cache()

    def __delitem__(self, key: str):
        """Delete file."""
        if key not in self._files:
            raise KeyError(f"File not found: {key}")

        file_id = self._files[key]
        gfile = self._drive.CreateFile({"id": file_id})
        gfile.Delete()

        self._refresh_cache()


# =============================================================================
# Convenience: make a native Google Sheet from an .xlsx
# =============================================================================


def xlsx_to_google_sheet(
    folder_url: Optional[str],
    title: str,
    xlsx: Union[str, Path, bytes],
    *,
    share_with=(),
    anyone_reader: bool = False,
    credentials_file: str = "client_secrets.json",
    settings_file: str = "settings.yaml",
    drive=None,
) -> str:
    """Upload an ``.xlsx`` as a **native Google Sheet** and return its shareable URL.

    The whole point: Drive can *convert* an uploaded spreadsheet into an editable Google Sheet
    (preserving cell formatting), rather than parking an ``.xlsx`` blob. This wraps that.

    Args:
        folder_url: destination Drive folder URL (``None`` → the account's root).
        title: the Google Sheet's name.
        xlsx: a path (``str``/``Path``) or raw ``bytes``.
        share_with: emails to grant ``writer`` access (no notification email sent).
        anyone_reader: also grant anyone-with-link ``reader`` access.
        credentials_file / settings_file: PyDrive2 auth (ignored if ``drive`` is given).
        drive: an existing PyDrive2 ``GoogleDrive`` (skips auth).

    Returns:
        The Google Sheet URL (``alternateLink``).

    >>> url = xlsx_to_google_sheet(folder_url, 'My Schema', '/tmp/schema.xlsx',
    ...                            anyone_reader=True)  # doctest: +SKIP
    """
    if drive is None:
        _require_pydrive2()
        drive = _init_google_drive(credentials_file, settings_file)
    parent_id = _extract_folder_id(folder_url) if folder_url else None
    path = str(xlsx) if isinstance(xlsx, (str, Path)) else None
    content = xlsx if isinstance(xlsx, bytes) else None
    gfile = _upload_converting(
        drive,
        parent_id=parent_id,
        title=title,
        content=content,
        path=path,
        convert=True,
        google_mimetype="application/vnd.google-apps.spreadsheet",
    )
    for email in share_with:
        gfile.InsertPermission({"type": "user", "value": email, "role": "writer"})
    if anyone_reader:
        gfile.InsertPermission({"type": "anyone", "value": "anyone", "role": "reader"})
    return gfile["alternateLink"]
