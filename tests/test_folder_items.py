"""A folder listing carries each file's metadata: one listing call, no per-file fetches."""

from pydrivedol import GDReader, iter_folder_items
from pydrivedol.base import _FOLDER_MIMETYPE


def _file(id, title, size=None, modified="2026-01-01T00:00:00.000Z"):
    item = {"id": id, "title": title, "mimeType": "text/plain", "modifiedDate": modified}
    if size is not None:
        item["fileSize"] = str(size)  # Drive sends sizes as strings
    return item


TREE = {
    "root": [
        _file("f1", "a.txt", 12),
        _file("f2", ".hidden", 1),
        {"id": "sub", "title": "sub", "mimeType": _FOLDER_MIMETYPE},
        {"id": "gsheet", "title": "sheet", "mimeType": "application/vnd.google-apps.spreadsheet"},
    ],
    "sub": [_file("f3", "b.txt", 345)],
}


class _List:
    def __init__(self, items):
        self._items = items

    def GetList(self):
        return list(self._items)


class _Drive:
    """Records ListFile calls; any CreateFile (a per-file fetch) fails the test."""

    def __init__(self):
        self.list_calls = []

    def ListFile(self, params):
        self.list_calls.append(params)
        parent = params["q"].split("'")[1]
        return _List(TREE[parent])

    def CreateFile(self, *args, **kwargs):
        raise AssertionError("no per-file metadata fetch should be needed")


def test_items_have_metadata_with_int_sizes():
    drive = _Drive()
    items = dict(iter_folder_items(drive, "root"))
    assert set(items) == {"a.txt", "sheet", "sub/b.txt"}  # hidden and folders skipped
    assert items["a.txt"]["fileSize"] == 12
    assert items["sub/b.txt"]["title"] == "b.txt"
    assert "fileSize" not in items["sheet"]  # Google-native: no byte size
    assert len(drive.list_calls) == 2  # one call per folder, N files notwithstanding


def test_levels_hidden_and_fields():
    drive = _Drive()
    top = dict(iter_folder_items(drive, "root", max_levels=0))
    assert set(top) == {"a.txt", "sheet"}
    both = dict(iter_folder_items(drive, "root", include_hidden=True, fields=("title",)))
    assert both[".hidden"] == {"title": ".hidden"}
    assert "items(id,title,mimeType)" in drive.list_calls[-1]["fields"]
    assert dict(iter_folder_items(drive, "root", fields=None))["a.txt"]["fileSize"] == 12  # None keeps every field, still normalised


def test_reader_metadata_comes_from_the_cached_listing():
    drive = _Drive()
    reader = GDReader("https://drive.google.com/drive/folders/root", drive=drive)
    assert sorted(reader) == ["a.txt", "sheet", "sub/b.txt"]
    assert reader.metadata("sub/b.txt")["fileSize"] == 345
    assert len(drive.list_calls) == 2  # metadata() added no call
    try:
        reader.metadata("nope")
    except KeyError:
        pass
    else:
        raise AssertionError("expected KeyError")
