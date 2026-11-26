"""Tests for PublicDriveFolder / sync_to_dir against a fake Drive v3 session (no network)."""

import hashlib
import json

import pytest

from pydrivedol import PublicDriveFolder, sync_to_dir

FOLDER = "https://drive.google.com/drive/folders/ROOT123456"
DIR = "application/vnd.google-apps.folder"


class FakeResponse:
    def __init__(self, payload=None, content=b""):
        self._payload, self.content = payload, content

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload

    def iter_content(self, n):
        for i in range(0, len(self.content), n):
            yield self.content[i : i + n]


class FakeDrive:
    """Folders: id -> list of items; blobs: id -> bytes. Pages of 2 to exercise paging."""

    def __init__(self, tree, blobs):
        self.tree, self.blobs, self.calls = tree, blobs, []

    def get(self, url, params=None, **kw):
        self.calls.append((url, dict(params)))
        if params.get("alt") == "media":
            return FakeResponse(content=self.blobs[url.rsplit("/", 1)[1]])
        parent = params["q"].split("'")[1]
        items = self.tree[parent]
        start = int(params.get("pageToken", 0))
        page = items[start : start + 2]
        nxt = start + 2 if start + 2 < len(items) else None
        return FakeResponse(
            {"files": page, **({"nextPageToken": str(nxt)} if nxt else {})}
        )


def _item(id, name, content=None, mime="audio/mpeg"):
    meta = {"id": id, "name": name, "mimeType": mime, "modifiedTime": "t"}
    if content is not None:
        meta.update(
            md5Checksum=hashlib.md5(content).hexdigest(), size=str(len(content))
        )
    return meta


@pytest.fixture
def drive():
    blobs = {"a": b"AAA", "b": b"BBBB", "c": b"CC", "d": b"D"}
    tree = {
        "ROOT123456": [
            _item("a", "a.mp3", blobs["a"]),
            _item("b", "b.txt", blobs["b"], "text/plain"),
            _item("sub", "sub", mime=DIR),
            _item("doc", "notes", mime="application/vnd.google-apps.document"),
        ],
        "sub": [_item("c", "c.mp3", blobs["c"]), _item("d", "d.mp3", blobs["d"])],
    }
    return FakeDrive(tree, blobs)


def test_mapping_lists_recursively_and_reads_bytes(drive):
    f = PublicDriveFolder(FOLDER, api_key="K", session=drive)
    assert sorted(f) == [
        "a.mp3",
        "b.txt",
        "sub/c.mp3",
        "sub/d.mp3",
    ]  # paged, native doc skipped
    assert f["sub/c.mp3"] == b"CC"
    assert f.meta("a.mp3")["size"] == 3
    assert all(p.get("key") == "K" for _, p in drive.calls)


def test_include_suffix_and_non_recursive(drive):
    assert sorted(PublicDriveFolder(FOLDER, session=drive, include=".mp3")) == [
        "a.mp3",
        "sub/c.mp3",
        "sub/d.mp3",
    ]
    assert sorted(PublicDriveFolder(FOLDER, session=drive, recursive=False)) == [
        "a.mp3",
        "b.txt",
    ]


def test_media_url_and_repr_do_not_leak_key_in_repr(drive):
    f = PublicDriveFolder(FOLDER, api_key="SECRET", session=drive)
    assert "SECRET" not in repr(f)
    assert f.media_url("a.mp3").endswith("/a?alt=media&key=SECRET")


def test_key_comes_from_env_by_default(drive, monkeypatch):
    monkeypatch.setenv("PYDRIVEDOL_API_KEY", "ENVKEY")
    f = PublicDriveFolder(FOLDER, session=drive)
    list(f)
    assert drive.calls[0][1]["key"] == "ENVKEY"


def test_sync_is_incremental(drive, tmp_path):
    f = PublicDriveFolder(FOLDER, session=drive)
    r1 = sync_to_dir(f, tmp_path, include=".mp3")
    assert sorted(r1.added) == ["a.mp3", "sub/c.mp3", "sub/d.mp3"]
    assert (tmp_path / "sub" / "c.mp3").read_bytes() == b"CC"
    assert not list(tmp_path.rglob("*.part"))

    media_before = sum(p.get("alt") == "media" for _, p in drive.calls)
    r2 = sync_to_dir(f, tmp_path, include=".mp3")
    assert r2.downloaded == 0 and len(r2.unchanged) == 3
    assert sum(p.get("alt") == "media" for _, p in drive.calls) == media_before

    drive.blobs["a"] = b"A2"
    drive.tree["ROOT123456"][0] = _item("a", "a.mp3", b"A2")
    (tmp_path / "sub" / "d.mp3").unlink()
    r3 = sync_to_dir(f, tmp_path, include=".mp3")
    assert r3.changed == ["a.mp3"] and r3.added == ["sub/d.mp3"]
    assert (tmp_path / "a.mp3").read_bytes() == b"A2"


def test_sync_prune_and_unsafe_names(drive, tmp_path):
    drive.tree["ROOT123456"].append(_item("e", "..", b"E"))
    drive.blobs["e"] = b"E"
    r = sync_to_dir(
        FOLDER, tmp_path, session=drive, include=lambda m: m["name"] != "b.txt"
    )
    assert "_.." in r.added and (tmp_path / "_..").exists()  # stays inside dest
    drive.tree["ROOT123456"] = [i for i in drive.tree["ROOT123456"] if i["id"] != "a"]
    r = sync_to_dir(FOLDER, tmp_path, session=drive, prune=True)
    assert "a.mp3" in r.removed and not (tmp_path / "a.mp3").exists()
    assert json.loads((tmp_path / ".drive_index.json").read_text()).get("a.mp3") is None
