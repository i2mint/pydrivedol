"""Unit tests for authenticated file access -- no real Drive, no network, no credentials.

Everything here runs off two fakes: a ``FakeDrive`` implementing the slice of the PyDrive2
``GoogleDrive`` API that ``pydrivedol`` actually calls, and a ``FakeSession`` standing in for
``requests.Session``. That covers all three concerns end to end:

- the silent-HTML guard on the public download path (``NotPubliclyShared``),
- the authenticated download / metadata path (``drive=``),
- the file-level ``GDFiles`` mapping.
"""

import os
import re

import pytest

import pydrivedol.base as base
from pydrivedol import (
    GDFiles,
    GDReader,
    NotPubliclyShared,
    get_bytes,
    get_metadata,
)

FILE_ID = '1AbCdEfGhIjKlMnOpQrStUvWxYz012345'
FILE_URL = f'https://drive.google.com/file/d/{FILE_ID}/view?usp=sharing'
FOLDER_ID = '1FoLdErIdAbCdEfGhIjKlMnOpQrStUvW'
FOLDER_URL = f'https://drive.google.com/drive/folders/{FOLDER_ID}'

# A real xlsx starts with the zip magic; nothing about it looks like HTML.
XLSX_BYTES = b'PK\x03\x04\x14\x00\x08\x08\x08\x00' + b'\xe2\x80\x93' * 100

# Abridged shape of what Drive actually serves (with HTTP 200) for a non-public file.
GOOGLE_SIGNIN_HTML = (
    b'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
    b'<title>Sign in - Google Accounts</title></head>'
    b'<body>You need access. Ask for access, or switch to an account with access.</body></html>'
)


# =============================================================================
# Fakes
# =============================================================================


class _FakeList:
    """What PyDrive2's ``ListFile`` returns: something with ``GetList()``."""

    def __init__(self, items):
        self._items = items

    def GetList(self):
        return list(self._items)


class FakeGDriveFile(dict):
    """The slice of PyDrive2's ``GoogleDriveFile`` that pydrivedol calls."""

    def __init__(self, meta, drive):
        super().__init__(meta or {})
        self._drive = drive

    def GetContentIOBuffer(self, **kwargs):
        self._drive.calls.append(('GetContentIOBuffer', self['id']))
        content = self._drive.content_of(self['id'])
        # PyDrive2 yields chunks; two of them here so the join is actually exercised.
        midpoint = len(content) // 2
        return iter([content[:midpoint], content[midpoint:]])

    def FetchMetadata(self, fields=None, fetch_all=False):
        self._drive.calls.append(('FetchMetadata', self['id'], fields, fetch_all))
        self.update(self._drive.metadata_of(self['id']))


class FakeDrive:
    """A stand-in ``GoogleDrive``: ``files`` map ids to metadata dicts (with ``_content``)."""

    def __init__(self, files=None, listings=None, errors=None):
        self.files = dict(files or {})
        self.listings = dict(listings or {})  # folder_id -> list of listing entries
        self.errors = dict(errors or {})  # file_id -> exception to raise
        self.calls = []

    def _check(self, file_id):
        if file_id in self.errors:
            raise self.errors[file_id]
        if file_id not in self.files:
            raise Exception(f'<HttpError 404 ... "File not found: {file_id}">')

    def content_of(self, file_id):
        self._check(file_id)
        return self.files[file_id].get('_content', b'')

    def metadata_of(self, file_id):
        self._check(file_id)
        return {k: v for k, v in self.files[file_id].items() if not k.startswith('_')}

    def CreateFile(self, meta=None):
        self.calls.append(('CreateFile', dict(meta or {})))
        return FakeGDriveFile(meta, self)

    def ListFile(self, param):
        folder_id = re.match(r"'([^']+)' in parents", param['q']).group(1)
        self.calls.append(('ListFile', folder_id))
        return _FakeList(self.listings.get(folder_id, []))


class FakeResponse:
    """A ``requests`` response carrying whatever bytes/content-type the test wants."""

    def __init__(self, content, *, content_type='application/octet-stream', status_code=200):
        self.content = content
        self.status_code = status_code
        self.headers = {'Content-Type': content_type}
        self.cookies = {}

    @property
    def text(self):
        return self.content.decode('utf-8', 'replace')


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.gets = []

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        return self.response


@pytest.fixture
def fake_drive():
    """A drive holding one binary file, one Google-native Sheet, and a two-level folder tree."""
    return FakeDrive(
        files={
            FILE_ID: {
                'id': FILE_ID,
                'title': 'client_export.xlsx',
                'mimeType': (
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                ),
                'fileSize': '18512345',  # Drive sends sizes as strings
                'modifiedDate': '2026-08-01T12:00:00.000Z',
                'alternateLink': FILE_URL,
                '_content': XLSX_BYTES,
            },
            'nativeSheetId0123456789': {
                'id': 'nativeSheetId0123456789',
                'title': 'A Google Sheet',
                'mimeType': 'application/vnd.google-apps.spreadsheet',
                # no fileSize: Google-native files have no stored byte size
                'modifiedDate': '2026-08-02T12:00:00.000Z',
                '_content': b'',
            },
            'nestedFileId0123456789': {
                'id': 'nestedFileId0123456789',
                'title': 'nested.csv',
                '_content': b'a,b',
            },
        },
        listings={
            FOLDER_ID: [
                {'id': FILE_ID, 'title': 'client_export.xlsx', 'mimeType': 'application/x'},
                {'id': 'hiddenFileId012345678', 'title': '.hidden', 'mimeType': 'application/x'},
                {
                    'id': 'subFolderId0123456789',
                    'title': 'sub',
                    'mimeType': 'application/vnd.google-apps.folder',
                },
            ],
            'subFolderId0123456789': [
                {'id': 'nestedFileId0123456789', 'title': 'nested.csv', 'mimeType': 'text/csv'},
            ],
        },
    )


def _use_session(monkeypatch, response):
    """Point ``base.requests.Session`` at a fake returning ``response``; return the fake."""
    session = FakeSession(response)
    monkeypatch.setattr(base.requests, 'Session', lambda: session)
    return session


def _forbid_network(monkeypatch):
    """Make any use of ``requests.Session`` an outright test failure."""

    def _boom():
        raise AssertionError('the authenticated path must not touch the public endpoint')

    monkeypatch.setattr(base.requests, 'Session', _boom)


# =============================================================================
# Key resolution
# =============================================================================


def test_resolve_file_id_accepts_urls_and_bare_ids():
    assert base._resolve_file_id(FILE_URL) == FILE_ID
    assert base._resolve_file_id(FILE_ID) == FILE_ID
    assert base._resolve_file_id(f'https://drive.google.com/open?id={FILE_ID}') == FILE_ID


@pytest.mark.parametrize('bad', ['', 'nope', 'not a url', FOLDER_URL, 'https://example.com/x'])
def test_resolve_file_id_rejects_non_file_keys(bad):
    with pytest.raises(ValueError):
        base._resolve_file_id(bad)


# =============================================================================
# The silent-HTML guard
# =============================================================================


@pytest.mark.parametrize(
    'content, content_type, expected',
    [
        (XLSX_BYTES, 'application/octet-stream', False),
        (b'id,name', 'text/csv', False),
        (b'', '', False),
        (GOOGLE_SIGNIN_HTML, 'text/html; charset=utf-8', True),
        (GOOGLE_SIGNIN_HTML, '', True),  # body alone is enough
        (b'anything at all', 'text/html; charset=utf-8', True),  # content type alone is enough
        (b'  \n\t<html lang="en">', '', True),  # leading whitespace tolerated
        (b'\xef\xbb\xbf<!DOCTYPE HTML>', '', True),  # BOM tolerated
        (b'<!doctype html>', '', True),  # lowercase
    ],
)
def test_looks_like_html(content, content_type, expected):
    assert base._looks_like_html(content, content_type) is expected


def test_get_bytes_raises_instead_of_returning_the_sign_in_page(monkeypatch):
    """The bug this guards: HTTP 200 + HTML body was returned as if it were the file."""
    _use_session(monkeypatch, FakeResponse(GOOGLE_SIGNIN_HTML, content_type='text/html'))

    with pytest.raises(NotPubliclyShared) as excinfo:
        get_bytes(FILE_URL)

    message = str(excinfo.value)
    assert FILE_ID in message
    assert 'drive=' in message  # says how to fix it
    assert 'allow_html=True' in message  # ...and how to opt out


def test_get_bytes_detects_html_even_when_content_type_lies(monkeypatch):
    _use_session(
        monkeypatch, FakeResponse(GOOGLE_SIGNIN_HTML, content_type='application/octet-stream')
    )
    with pytest.raises(NotPubliclyShared):
        get_bytes(FILE_URL)


def test_get_bytes_allow_html_opts_out(monkeypatch):
    _use_session(monkeypatch, FakeResponse(GOOGLE_SIGNIN_HTML, content_type='text/html'))
    assert get_bytes(FILE_URL, allow_html=True) == GOOGLE_SIGNIN_HTML


def test_get_bytes_public_path_still_returns_real_content(monkeypatch):
    """No false positives: ordinary binary payloads pass through untouched."""
    session = _use_session(monkeypatch, FakeResponse(XLSX_BYTES))
    assert get_bytes(FILE_URL) == XLSX_BYTES
    assert FILE_ID in session.gets[0][0]


def test_get_bytes_public_path_still_raises_on_bad_status(monkeypatch):
    _use_session(monkeypatch, FakeResponse(b'nope', status_code=403))
    with pytest.raises(RuntimeError):
        get_bytes(FILE_URL)


# =============================================================================
# Authenticated get_bytes
# =============================================================================


def test_get_bytes_with_drive_downloads_via_api(fake_drive, monkeypatch):
    _forbid_network(monkeypatch)
    assert get_bytes(FILE_URL, drive=fake_drive) == XLSX_BYTES
    assert ('CreateFile', {'id': FILE_ID}) in fake_drive.calls
    assert ('GetContentIOBuffer', FILE_ID) in fake_drive.calls


def test_get_bytes_with_drive_accepts_a_bare_file_id(fake_drive, monkeypatch):
    _forbid_network(monkeypatch)
    assert get_bytes(FILE_ID, drive=fake_drive) == XLSX_BYTES


def test_get_bytes_with_drive_honours_local_path(fake_drive, monkeypatch, tmp_path):
    _forbid_network(monkeypatch)
    target = tmp_path / 'sub' / 'export.xlsx'
    content = get_bytes(FILE_URL, drive=fake_drive, local_path=str(target))
    assert content == XLSX_BYTES
    assert target.read_bytes() == XLSX_BYTES


def test_get_bytes_with_drive_honours_use_cache(fake_drive, monkeypatch, tmp_path):
    _forbid_network(monkeypatch)
    cache_dir = str(tmp_path / 'cache')

    assert get_bytes(FILE_URL, drive=fake_drive, use_cache=cache_dir) == XLSX_BYTES
    downloads = [c for c in fake_drive.calls if c[0] == 'GetContentIOBuffer']
    assert len(downloads) == 1

    # Second call is served from cache -- the drive is not touched again.
    assert get_bytes(FILE_URL, drive=fake_drive, use_cache=cache_dir) == XLSX_BYTES
    downloads = [c for c in fake_drive.calls if c[0] == 'GetContentIOBuffer']
    assert len(downloads) == 1


def test_get_bytes_without_drive_never_calls_the_api(monkeypatch, fake_drive):
    """drive=None must keep the public behaviour exactly."""
    _use_session(monkeypatch, FakeResponse(XLSX_BYTES))
    get_bytes(FILE_URL)
    assert fake_drive.calls == []


# =============================================================================
# Metadata without downloading
# =============================================================================


def test_get_metadata_returns_the_decision_making_fields(fake_drive):
    info = get_metadata(FILE_URL, drive=fake_drive)
    assert info['title'] == 'client_export.xlsx'
    assert info['modifiedDate'] == '2026-08-01T12:00:00.000Z'
    assert 'spreadsheetml' in info['mimeType']


def test_get_metadata_coerces_file_size_to_int(fake_drive):
    """Drive sends fileSize as a string; callers compare it against a threshold."""
    assert get_metadata(FILE_URL, drive=fake_drive)['fileSize'] == 18512345


def test_get_metadata_does_not_download(fake_drive):
    get_metadata(FILE_URL, drive=fake_drive)
    assert not any(c[0] == 'GetContentIOBuffer' for c in fake_drive.calls)


def test_get_metadata_requests_only_the_named_fields(fake_drive):
    get_metadata(FILE_URL, drive=fake_drive, fields=('id', 'fileSize'))
    (fetch,) = [c for c in fake_drive.calls if c[0] == 'FetchMetadata']
    assert fetch[2] == 'id,fileSize'
    assert fetch[3] is False


def test_get_metadata_fields_none_fetches_everything(fake_drive):
    info = get_metadata(FILE_URL, drive=fake_drive, fields=None)
    (fetch,) = [c for c in fake_drive.calls if c[0] == 'FetchMetadata']
    assert fetch[3] is True
    assert info['title'] == 'client_export.xlsx'


def test_get_metadata_omits_file_size_for_google_native_files(fake_drive):
    info = get_metadata('nativeSheetId0123456789', drive=fake_drive)
    assert info['mimeType'] == 'application/vnd.google-apps.spreadsheet'
    assert 'fileSize' not in info


# =============================================================================
# GDFiles
# =============================================================================


def test_gdfiles_keyed_by_url_or_id(fake_drive):
    files = GDFiles(fake_drive)
    assert files[FILE_URL] == XLSX_BYTES
    assert files[FILE_ID] == XLSX_BYTES


def test_gdfiles_unscoped_iteration_raises_with_an_actionable_message(fake_drive):
    files = GDFiles(fake_drive)
    for call in (lambda: list(files), lambda: len(files)):
        with pytest.raises(NotImplementedError) as excinfo:
            call()
        assert 'folder_url' in str(excinfo.value)


def test_gdfiles_scoped_iteration_yields_file_ids(fake_drive):
    files = GDFiles(fake_drive, folder_url=FOLDER_URL)
    assert list(files) == [FILE_ID, 'nestedFileId0123456789']
    assert len(files) == 2


def test_gdfiles_scope_respects_max_levels(fake_drive):
    files = GDFiles(fake_drive, folder_url=FOLDER_URL, max_levels=0)
    assert list(files) == [FILE_ID]


def test_gdfiles_scope_respects_include_hidden(fake_drive):
    files = GDFiles(fake_drive, folder_url=FOLDER_URL, max_levels=0, include_hidden=True)
    assert list(files) == [FILE_ID, 'hiddenFileId012345678']


def test_gdfiles_scoped_values_are_the_file_contents(fake_drive):
    files = GDFiles(fake_drive, folder_url=FOLDER_URL)
    assert dict(files) == {FILE_ID: XLSX_BYTES, 'nestedFileId0123456789': b'a,b'}


def test_gdfiles_rejects_a_bad_folder_url(fake_drive):
    with pytest.raises(ValueError):
        GDFiles(fake_drive, folder_url='https://example.com/not-a-folder')


def test_gdfiles_contains_probes_metadata_rather_than_downloading(fake_drive):
    files = GDFiles(fake_drive)
    assert FILE_URL in files
    assert not any(c[0] == 'GetContentIOBuffer' for c in fake_drive.calls)


def test_gdfiles_contains_is_false_for_missing_or_unusable_keys(fake_drive):
    files = GDFiles(fake_drive)
    assert 'noSuchFileId0123456789' not in files
    assert 'not a drive key' not in files


def test_gdfiles_contains_propagates_non_404_failures(fake_drive):
    fake_drive.errors[FILE_ID] = Exception('<HttpError 500 ... "Backend Error">')
    files = GDFiles(fake_drive)
    with pytest.raises(Exception, match='500'):
        FILE_URL in files  # noqa: B015 -- the point is that it raises


def test_gdfiles_getitem_raises_keyerror_for_a_missing_file(fake_drive):
    files = GDFiles(fake_drive)
    with pytest.raises(KeyError):
        files['noSuchFileId0123456789']


def test_gdfiles_getitem_propagates_non_404_failures(fake_drive):
    """A 5xx must not be disguised as 'absent' -- that would hide real outages."""
    fake_drive.errors[FILE_ID] = Exception('<HttpError 500 ... "Backend Error">')
    files = GDFiles(fake_drive)
    with pytest.raises(Exception, match='500'):
        files[FILE_URL]


def test_gdfiles_getitem_rejects_an_unusable_key(fake_drive):
    with pytest.raises(ValueError):
        GDFiles(fake_drive)['not a drive key']


def test_gdfiles_metadata_method_delegates(fake_drive):
    files = GDFiles(fake_drive)
    assert files.metadata(FILE_URL)['fileSize'] == 18512345
    assert files.metadata(FILE_URL, fields=('id',)) == {'id': FILE_ID}


def test_gdfiles_needs_no_pydrive2_import(fake_drive, monkeypatch):
    """The drive is injected, so GDFiles must not require PyDrive2 to be importable."""
    monkeypatch.setattr(base, '_PYDRIVE2_AVAILABLE', False)
    assert GDFiles(fake_drive)[FILE_URL] == XLSX_BYTES


# =============================================================================
# GDReader: binary reads must be byte-exact
# =============================================================================


# GDReader keys are built with os.path.join, so the separator is the platform's.
NESTED_KEY = os.path.join('sub', 'nested.csv')


def test_gdreader_getitem_returns_exact_bytes(fake_drive, monkeypatch):
    """Regression: GetContentString(...).encode('latin-1') mangled every real binary."""
    monkeypatch.setattr(base, '_init_google_drive', _no_oauth)
    reader = GDReader(FOLDER_URL, drive=fake_drive)
    assert reader['client_export.xlsx'] == XLSX_BYTES
    assert reader[NESTED_KEY] == b'a,b'


def test_gdreader_listing_is_unchanged_by_the_shared_traversal(fake_drive, monkeypatch):
    monkeypatch.setattr(base, '_init_google_drive', _no_oauth)
    assert list(GDReader(FOLDER_URL, drive=fake_drive)) == [
        'client_export.xlsx',
        NESTED_KEY,
    ]
    assert list(GDReader(FOLDER_URL, drive=fake_drive, max_levels=0)) == [
        'client_export.xlsx'
    ]


def _no_oauth(*args, **kwargs):
    raise AssertionError('must not run the OAuth flow when drive= is provided')
