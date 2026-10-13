"""Key-transform blindness (i2mint/pydrivedol#4): wrapped stores over an in-memory fake Drive."""

import re

import pytest
from dol import KeyCodecs, ValueCodecs, filt_iter, wrap_kvs

import pydrivedol.base as B
from pydrivedol import get_url, metadata, upload
from pydrivedol.base import GDFiles, GDStore, GOOGLE_MIME

B._PYDRIVE2_AVAILABLE = True  # drive= is injected; skip the pydrive2 guard
FOLDER = "https://drive.google.com/drive/folders/ROOT"
GFOLDER = "application/vnd.google-apps.folder"


class FakeFile(dict):
    def __init__(self, drive, **kw):
        super().__init__(**kw)
        self._drive = drive

    def __getitem__(self, k):
        if k == "alternateLink":
            return f"link-to:{self['id']}"
        return super().__getitem__(k)

    def GetContentString(self, mimetype=None):
        return self._drive.files[self["id"]]["content"].decode("latin-1")

    def GetContentIOBuffer(self, mimetype=None):
        import io

        return io.BytesIO(self._drive.files[self["id"]]["content"])

    def SetContentString(self, s):
        self["content"] = s.encode("latin-1")

    def SetContentFile(self, path):
        self["content"] = open(path, "rb").read()

    def InsertPermission(self, perm):
        self._drive.permission_log.append((self["id"], perm))

    def Upload(self, param=None):
        self._drive.files[self["id"]] = self

    def Delete(self):
        self._drive.files.pop(self["id"], None)


class FakeDrive:
    def __init__(self):
        self.files, self._n, self.permission_log = {}, 0, []
        self.created_meta = []

    def add(self, id, title, parent, mimeType="text/plain", content=b""):
        self.files[id] = FakeFile(
            self, id=id, title=title, mimeType=mimeType,
            parents=[{"id": parent}], content=content,
        )

    def ListFile(self, q):
        query, out = q["q"], []
        parent = re.search(r"'([^']+)' in parents", query).group(1)
        title = re.search(r"title='([^']+)'", query)
        mime = re.search(r"mimeType='([^']+)'", query)
        for f in self.files.values():
            if not any(p["id"] == parent for p in f["parents"]):
                continue
            if title and f["title"] != title.group(1):
                continue
            if mime and f["mimeType"] != mime.group(1):
                continue
            out.append(f)
        return type("L", (), {"GetList": lambda s: out})()

    def CreateFile(self, meta):
        self.created_meta.append(dict(meta))
        if meta.get("id") in self.files:
            return self.files[meta["id"]]
        self._n += 1
        return FakeFile(
            self, id=meta.get("id") or f"NEW{self._n}", title=meta.get("title", ""),
            parents=meta.get("parents", []), mimeType=meta.get("mimeType", "text/plain"),
            content=b"",
        )


def fresh():
    """A folder holding BOTH 'b' and 'a/b' -- an ordinary layout."""
    d = FakeDrive()
    d.add("F_ROOT_B", "b", "ROOT", content=b"IMPORTANT ROOT DATA")
    d.add("F_A", "a", "ROOT", mimeType=GFOLDER)
    d.add("F_A_B", "b", "F_A", content=b"inner data")
    return d


def contents(d):
    return {f["id"]: f["content"] for f in d.files.values() if f["mimeType"] != GFOLDER}


def prefixed_store(d):
    return KeyCodecs.prefixed("a/")(GDStore(FOLDER, drive=d))


def test_methods_removed_name_their_replacement():
    s = GDStore(FOLDER, drive=fresh())
    with pytest.raises(AttributeError, match="pydrivedol.ops.upload"):
        s.upload("b", b"x")
    with pytest.raises(AttributeError, match="pydrivedol.ops.get_url"):
        s.get_url("b")
    with pytest.raises(AttributeError, match="pydrivedol.ops.metadata"):
        GDFiles(fresh()).metadata("x")
    # ... including through a wrapper, which is the whole point
    with pytest.raises(AttributeError):
        prefixed_store(fresh()).upload("b", b"x")


def test_upload_maps_key_and_spares_the_colliding_file():
    d = fresh()
    w = prefixed_store(d)
    url = upload(w, "b", b"OVERWRITTEN")
    assert contents(d) == {"F_ROOT_B": b"IMPORTANT ROOT DATA", "F_A_B": b"OVERWRITTEN"}
    assert url == "link-to:F_A_B" and w["b"] == b"OVERWRITTEN"


def test_upload_creates_new_file_under_mapped_path():
    d = fresh()
    w = prefixed_store(d)
    upload(w, "new/c.txt", b"fresh")  # -> a/new/c.txt
    assert sorted(w.store) == ["a/b", "a/new/c.txt", "b"]
    assert w["new/c.txt"] == b"fresh"


def test_upload_bare_store_and_path(tmp_path):
    d = fresh()
    s = GDStore(FOLDER, drive=d)
    f = tmp_path / "f.bin"
    f.write_bytes(b"from file")
    assert upload(s, "b", path=str(f)).startswith("link-to:")
    assert contents(d)["F_ROOT_B"] == b"from file"
    with pytest.raises(ValueError):
        upload(s, "b")
    with pytest.raises(ValueError):
        upload(s, "b", b"x", path=str(f))


def test_upload_passes_through_value_codec():
    d = fresh()
    w = wrap_kvs(GDStore(FOLDER, drive=d), data_of_obj=lambda s: s.encode(), obj_of_data=lambda b: b.decode())
    upload(w, "b", "text value")
    assert contents(d)["F_ROOT_B"] == b"text value"


def test_upload_respects_write_guard_and_scope():
    d = fresh()
    ro = wrap_kvs(GDStore(FOLDER, drive=d))

    class RO(type(ro)):
        def __setitem__(self, k, v):
            raise PermissionError("read-only")

    with pytest.raises(PermissionError):
        upload(RO(GDStore(FOLDER, drive=d)), "b", b"x")
    assert contents(d)["F_ROOT_B"] == b"IMPORTANT ROOT DATA"


def test_upload_redirecting_layer_raises():
    d = fresh()
    base = GDStore(FOLDER, drive=d)

    class Redirect(type(wrap_kvs(base))):
        def __setitem__(self, k, v):
            self.store["a/b"] = v  # writes somewhere else than the mapped key

    with pytest.raises(RuntimeError, match="reached no Drive store"):
        upload(Redirect(base), "other", b"x")


def test_request_does_not_leak_after_call():
    d = fresh()
    w = prefixed_store(d)
    upload(w, "b", b"one")
    assert B._UPLOAD_REQUEST.get() is None
    w["b"] = b"plain"  # ordinary setitem unaffected
    assert contents(d)["F_A_B"] == b"plain"


def test_get_url_maps_key_and_grants_on_the_right_file():
    d = fresh()
    w = prefixed_store(d)
    assert get_url(w, "b") == "link-to:F_A_B"
    assert d.permission_log == [
        ("F_A_B", {"type": "anyone", "value": "anyone", "role": "reader"})
    ]


def test_get_url_outside_view_is_keyerror_and_grants_nothing():
    d = fresh()
    d.add("F_C", "c", "ROOT")
    w = prefixed_store(d)  # 'a/c' does not exist; leaf 'c' does but is outside the view
    with pytest.raises(KeyError):
        get_url(w, "c")
    scoped = filt_iter(GDStore(FOLDER, drive=d), filt=lambda k: k.startswith("a/"))
    with pytest.raises(KeyError):
        get_url(scoped, "b")
    assert d.permission_log == []


def test_get_url_bare_store():
    d = fresh()
    assert get_url(GDStore(FOLDER, drive=d), "b") == "link-to:F_ROOT_B"


def test_metadata_maps_key(monkeypatch):
    seen = []
    monkeypatch.setattr(
        B, "get_metadata", lambda key, *, drive, fields=None: seen.append(key) or {"id": key}
    )
    files = KeyCodecs.prefixed("https://drive.google.com/file/d/")(GDFiles(fresh()))
    assert metadata(files, "ABC123def456") == {
        "id": "https://drive.google.com/file/d/ABC123def456"
    }
    # the existence probe (key in files) and the call itself both used the mapped key
    assert set(seen) == {"https://drive.google.com/file/d/ABC123def456"}


class PlainPrefix:
    """A key-mapping wrapper with no ``_id_of_key`` (not a dol layer)."""

    def __init__(self, store):
        self.store = store

    def __contains__(self, k):
        return "a/" + k in self.store

    def __getitem__(self, k):
        return self.store["a/" + k]

    def __setitem__(self, k, v):
        self.store["a/" + k] = v


def test_wrapper_without_id_of_key_is_refused_not_guessed():
    d = fresh()
    w = PlainPrefix(GDStore(FOLDER, drive=d))
    for call in (
        lambda: get_url(w, "b"),
        lambda: upload(w, "b", b"x"),
    ):
        with pytest.raises(TypeError, match="_id_of_key"):
            call()
    assert d.permission_log == [] and contents(d)["F_ROOT_B"] == b"IMPORTANT ROOT DATA"


def test_upload_from_another_store_is_not_accepted():
    d = fresh()
    other = GDStore(FOLDER, drive=fresh())
    base = GDStore(FOLDER, drive=d)

    class ToOther(type(wrap_kvs(base))):
        def __setitem__(self, k, v):
            other[k] = v  # same relative key, different store

    with pytest.raises(RuntimeError, match="reached no Drive store"):
        upload(ToOther(base), "b", b"x")


def test_upload_path_extension_picks_google_type(tmp_path):
    d = fresh()
    s = GDStore(FOLDER, drive=d)
    f = tmp_path / "x.xlsx"
    f.write_bytes(b"PK")
    upload(s, "report", path=str(f), convert=True)
    [meta] = [m for m in d.created_meta if m.get("title") == "report"]
    assert meta["mimeType"] == GOOGLE_MIME[".xlsx"]
