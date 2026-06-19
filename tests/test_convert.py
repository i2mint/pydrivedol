"""Unit tests for the Google-native conversion path (no real Drive / no PyDrive2 needed).

`_upload_converting` and `xlsx_to_google_sheet` take an injected ``drive``, so a fake records
the calls and we assert the convert param + target Google mimetype + sharing are wired correctly.
"""

from pydrivedol.base import _upload_converting, xlsx_to_google_sheet, GOOGLE_MIME

SHEET_MIME = 'application/vnd.google-apps.spreadsheet'


class FakeFile(dict):
    def __init__(self, meta, log):
        super().__init__(meta or {})
        self._log = log
        self.setdefault('alternateLink', 'https://docs.google.com/spreadsheets/d/FAKE/edit')

    def SetContentFile(self, path):
        self._log.append(('SetContentFile', path))

    def Upload(self, param=None):
        self._log.append(('Upload', dict(param or {}), dict(self)))

    def InsertPermission(self, perm):
        self._log.append(('InsertPermission', dict(perm)))


class _EmptyList:
    def GetList(self):
        return []


class FakeDrive:
    def __init__(self):
        self.log = []

    def CreateFile(self, meta=None):
        self.log.append(('CreateFile', dict(meta or {})))
        return FakeFile(meta, self.log)

    def ListFile(self, q):
        return _EmptyList()


def _upload_calls(drive):
    return [c for c in drive.log if c[0] == 'Upload']


def test_convert_sets_param_and_google_mimetype():
    d = FakeDrive()
    _upload_converting(d, parent_id='P', title='schema.xlsx', content=b'bytes', convert=True)
    (_, param, meta), = _upload_calls(d)
    assert param == {'convert': True}
    assert meta['mimeType'] == SHEET_MIME           # xlsx → Google Sheet target
    assert meta['parents'] == [{'id': 'P'}]


def test_no_convert_uploads_raw_blob():
    d = FakeDrive()
    _upload_converting(d, parent_id='P', title='schema.xlsx', content=b'bytes', convert=False)
    (_, param, meta), = _upload_calls(d)
    assert param == {}                               # no conversion
    assert 'mimeType' not in meta or meta.get('mimeType') != SHEET_MIME


def test_mimetype_map_covers_office_types():
    assert GOOGLE_MIME['.xlsx'] == SHEET_MIME
    assert GOOGLE_MIME['.docx'] == 'application/vnd.google-apps.document'
    assert GOOGLE_MIME['.pptx'] == 'application/vnd.google-apps.presentation'


def test_xlsx_to_google_sheet_converts_shares_and_returns_url():
    d = FakeDrive()
    url = xlsx_to_google_sheet(
        None, 'My Schema', b'xlsxbytes',
        share_with=['a@example.com'], anyone_reader=True, drive=d,
    )
    assert 'docs.google.com' in url
    (_, param, meta), = _upload_calls(d)
    assert param == {'convert': True} and meta['mimeType'] == SHEET_MIME
    perms = [c[1] for c in d.log if c[0] == 'InsertPermission']
    assert {'type': 'user', 'value': 'a@example.com', 'role': 'writer'} in perms
    assert {'type': 'anyone', 'value': 'anyone', 'role': 'reader'} in perms
