"""Keys are quoted as literals in Drive search queries, never spliced in.

A key such as ``x' or title contains '`` used to rewrite the ``q`` query, so
lookups (and the "update existing file" branch of ``__setitem__``) could match
files outside the store's folder. File/folder ids taken from URLs are likewise
limited to Drive's id alphabet, so they cannot carry ``../`` into cache paths.
"""

import pytest

from pydrivedol.base import GDStore, _extract_file_id, _extract_folder_id, _q


class _File(dict):
    def SetContentString(self, s):
        self["content"] = s

    def Upload(self, param=None):
        pass


class _List:
    def GetList(self):
        return []


class _Drive:
    def __init__(self):
        self.queries = []

    def ListFile(self, q):
        self.queries.append(q["q"])
        return _List()

    def CreateFile(self, meta=None):
        return _File(meta or {}, id="new-id")


def _store():
    s = object.__new__(GDStore)
    s.folder_id = "ROOTFOLDER123"
    s._drive = _Drive()
    s._refresh_cache = lambda: None
    return s


HOSTILE = "x' or title contains '"


def test_hostile_filename_stays_one_literal():
    s = _store()
    s[HOSTILE] = b"data"
    q = s._drive.queries[-1]
    assert q == (
        "'ROOTFOLDER123' in parents and title='x\\' or title contains \\'' "
        "and trashed=false"
    )


def test_hostile_folder_name_stays_one_literal():
    s = _store()
    s[f"{HOSTILE}/f.txt"] = b"data"
    assert "title='x\\' or title contains \\'' " in s._drive.queries[0]


@pytest.mark.parametrize(
    "value, literal",
    [("plain", "'plain'"), ("it's", "'it\\'s'"), ("a\\b", "'a\\\\b'"), ("\\'", "'\\\\\\''")],
)
def test_q(value, literal):
    assert _q(value) == literal


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://drive.google.com/open?id=../secret/s.txt", None),
        ("https://drive.google.com/file/d/AbC_12-x/view", "AbC_12-x"),
        ("https://drive.google.com/uc?export=download&id=AbC123", "AbC123"),
    ],
)
def test_file_ids_are_confined_to_the_id_alphabet(url, expected):
    assert _extract_file_id(url) == expected


def test_folder_id_stops_at_the_id():
    assert _extract_folder_id("https://drive.google.com/drive/folders/AbC123/") == "AbC123"
