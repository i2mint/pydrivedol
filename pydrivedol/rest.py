"""Read a Drive folder over the plain Drive v3 REST API, and mirror it to disk.

No PyDrive2 and no OAuth flow: a folder shared "anyone with the link" needs only an API
key; a private folder works the same way with an authorized session (for instance
``google.auth.transport.requests.AuthorizedSession``) passed as ``session=``. That
``session`` is the one seam between the two; everything else is shared.

>>> folder = PublicDriveFolder(folder_url, api_key=key)       # doctest: +SKIP
>>> list(folder)                                              # doctest: +SKIP
['intro.mp3', 'clips/a.mp4']
>>> folder.meta('clips/a.mp4')['size']                        # doctest: +SKIP
>>> report = sync_to_dir(folder, 'mirror/', include={'.mp4'})  # doctest: +SKIP
>>> report.added, report.changed, report.unchanged            # doctest: +SKIP
"""

import json
import os
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Optional, Union

import requests

from pydrivedol.base import _FOLDER_MIMETYPE, _extract_folder_id, _q

#: Drive v3 files endpoint.
DRIVE_V3_FILES = "https://www.googleapis.com/drive/v3/files"

#: Environment variables the default key resolver reads, in order.
API_KEY_ENV_VARS = ("PYDRIVEDOL_API_KEY", "GOOGLE_API_KEY")

#: Metadata requested for every file in a listing.
LISTING_FIELDS = ("id", "name", "mimeType", "size", "modifiedTime", "md5Checksum")

#: Items Drive returns per listing page (its maximum).
LISTING_PAGE_SIZE = 1000

#: Name of the (name -> md5) index :func:`sync_to_dir` keeps inside the mirror.
SYNC_INDEX_NAME = ".drive_index.json"

#: Bytes read per chunk when streaming a download to disk.
DOWNLOAD_CHUNK_SIZE = 1 << 20

#: Seconds before a Drive request times out.
REQUEST_TIMEOUT = 60

_GOOGLE_NATIVE_PREFIX = "application/vnd.google-apps."


def env_api_key() -> Optional[str]:
    """The default API-key resolver: the first of :data:`API_KEY_ENV_VARS` that is set."""
    for name in API_KEY_ENV_VARS:
        if os.environ.get(name):
            return os.environ[name]
    return None


def _as_filter(include) -> Callable[[dict], bool]:
    """Normalise ``include`` (None, a suffix or suffixes, or a predicate on the metadata)."""
    if include is None:
        return lambda meta: True
    if callable(include):
        return include
    suffixes = tuple(
        s.lower() for s in ([include] if isinstance(include, str) else include)
    )
    return lambda meta: meta["name"].lower().endswith(suffixes)


def _safe_name(name: str) -> str:
    """A Drive name as one path component (Drive allows ``/`` and ``..`` in names)."""
    name = name.replace("/", "_").replace("\\", "_")
    return "_" + name if name in ("", ".", "..") else name


class PublicDriveFolder(Mapping):
    """Read-only ``Mapping[path, bytes]`` over a Drive folder, through Drive v3 REST.

    Keys are paths inside the folder (``"sub/file.mp3"``); Google-native documents
    (Docs, Sheets, ...) have no bytes and are left out.

    Args:
        url_or_id: the folder's URL or its id.
        api_key: a string, a zero-argument callable returning one, or ``None`` for
            :func:`env_api_key`. Never shown in ``repr``. Not needed when ``session``
            authenticates the requests.
        session: a ``requests``-compatible session; default a plain
            ``requests.Session``. Pass an ``AuthorizedSession`` to read private folders.
        recursive: descend into subfolders.
        include: ``None``, a suffix or collection of suffixes, or a predicate
            ``meta -> bool`` (``meta`` holds ``name``, ``mimeType``, ...).
    """

    def __init__(
        self,
        url_or_id: str,
        *,
        api_key: Union[str, Callable[[], Optional[str]], None] = None,
        session=None,
        recursive: bool = True,
        include=None,
    ):
        self.folder_id = _extract_folder_id(url_or_id) or url_or_id.strip()
        self._api_key = api_key
        self._session = session if session is not None else requests.Session()
        self.recursive = recursive
        self._include = _as_filter(include)

    def __repr__(self):
        return f"{type(self).__name__}({self.folder_id!r}, recursive={self.recursive})"

    # -- request plumbing -------------------------------------------------------------

    def _key(self) -> Optional[str]:
        key = self._api_key
        return key() if callable(key) else (key or env_api_key())

    def _params(self, **params) -> dict:
        key = self._key()
        if key:
            params["key"] = key
        return params

    def _get(self, url: str, **params):
        response = self._session.get(
            url, params=self._params(**params), timeout=REQUEST_TIMEOUT, stream=False
        )
        response.raise_for_status()
        return response

    # -- listing ----------------------------------------------------------------------

    def _children(self, folder_id: str) -> Iterator[dict]:
        page_token = None
        while True:
            params = dict(
                q=f"{_q(folder_id)} in parents and trashed = false",
                pageSize=LISTING_PAGE_SIZE,
                fields=f"nextPageToken, files({','.join(LISTING_FIELDS)})",
                supportsAllDrives="true",
                includeItemsFromAllDrives="true",
            )
            if page_token:
                params["pageToken"] = page_token
            data = self._get(DRIVE_V3_FILES, **params).json()
            yield from data.get("files", ())
            page_token = data.get("nextPageToken")
            if not page_token:
                return

    def _walk(self, folder_id: str, prefix: str = "") -> Iterator[tuple[str, dict]]:
        for item in self._children(folder_id):
            path = prefix + _safe_name(item["name"])
            if item["mimeType"] == _FOLDER_MIMETYPE:
                if self.recursive:
                    yield from self._walk(item["id"], path + "/")
            elif not item["mimeType"].startswith(_GOOGLE_NATIVE_PREFIX):
                if self._include(item):
                    yield path, item

    @cached_property
    def _index(self) -> dict[str, dict]:
        """``path -> metadata``, listed once; call :meth:`refresh` to list again."""
        index: dict[str, dict] = {}
        for path, item in self._walk(self.folder_id):
            if path in index:  # two files with one name: keep both, disambiguated
                stem, dot, ext = path.rpartition(".")
                path = (
                    f"{stem}~{item['id'][:6]}.{ext}"
                    if dot
                    else f"{path}~{item['id'][:6]}"
                )
            index[path] = item
        return index

    def refresh(self) -> "PublicDriveFolder":
        """Forget the cached listing so the next access lists the folder again."""
        self.__dict__.pop("_index", None)
        return self

    # -- Mapping ----------------------------------------------------------------------

    def __iter__(self):
        return iter(self._index)

    def __len__(self):
        return len(self._index)

    def __contains__(self, path):
        return path in self._index

    def __getitem__(self, path: str) -> bytes:
        return self._get(self._media_endpoint(path), alt="media").content

    # -- file-level extras ------------------------------------------------------------

    def meta(self, path: str) -> dict:
        """Metadata of one file: ``id``, ``name``, ``size`` (int), ``modifiedTime``, ``md5Checksum``..."""
        item = dict(self._index[path])
        if "size" in item:
            item["size"] = int(item["size"])
        return item

    def _media_endpoint(self, path: str) -> str:
        return f"{DRIVE_V3_FILES}/{self._index[path]['id']}"

    def media_url(self, path: str) -> str:
        """The ``alt=media`` URL of a file, for a server that proxies ``Range`` requests.

        It embeds the API key when one is configured: hand it to trusted server code only.
        """
        params = self._params(alt="media")
        return f"{self._media_endpoint(path)}?" + "&".join(
            f"{k}={v}" for k, v in params.items()
        )

    def download_to(self, path: str, dest: Union[str, Path]) -> Path:
        """Stream a file to ``dest`` atomically (a ``.part`` file, then a rename)."""
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(dest.name + ".part")
        response = self._session.get(
            self._media_endpoint(path),
            params=self._params(alt="media"),
            timeout=REQUEST_TIMEOUT,
            stream=True,
        )
        response.raise_for_status()
        with open(part, "wb") as f:
            for chunk in response.iter_content(DOWNLOAD_CHUNK_SIZE):
                f.write(chunk)
        os.replace(part, dest)
        return dest


@dataclass
class SyncReport:
    """What :func:`sync_to_dir` did, as lists of folder-relative paths."""

    added: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    @property
    def downloaded(self) -> int:
        return len(self.added) + len(self.changed)


def _change_token(meta: dict) -> Optional[str]:
    """What says a file changed: its md5, else its modified time (None if neither)."""
    return meta.get("md5Checksum") or meta.get("modifiedTime")


def sync_to_dir(
    folder: Union[PublicDriveFolder, str],
    dest: Union[str, Path],
    *,
    include=None,
    index_name: str = SYNC_INDEX_NAME,
    prune: bool = False,
    **folder_kwargs,
) -> SyncReport:
    """Mirror a Drive folder into ``dest``, downloading only what is new or changed.

    An index (path -> md5) is kept in ``dest``, so a re-run with nothing changed
    downloads nothing. A file is fetched when it is absent locally or its md5 differs
    from the indexed one.

    Args:
        folder: a :class:`PublicDriveFolder`, or a folder URL/id (then built with
            ``folder_kwargs``: ``api_key``, ``session``, ``recursive``).
        dest: the local directory (created if needed).
        include: as for :class:`PublicDriveFolder`; applied on top of the folder's own.
        index_name: file inside ``dest`` holding the index.
        prune: also delete local files that are no longer in the folder (only ones this
            mirror put there, i.e. that are in the index).
    """
    if not isinstance(folder, PublicDriveFolder):
        folder = PublicDriveFolder(folder, **folder_kwargs)
    keep = _as_filter(include)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    index_path = dest / index_name
    index = json.loads(index_path.read_text()) if index_path.exists() else {}

    report = SyncReport()
    remote = {p: folder.meta(p) for p in folder.refresh() if keep(folder._index[p])}
    for path, meta in remote.items():
        local = dest / path
        token = _change_token(meta)
        if local.exists() and index.get(path) == token and token is not None:
            report.unchanged.append(path)
            continue
        (report.changed if local.exists() else report.added).append(path)
        folder.download_to(path, local)
        index[path] = token
        index_path.write_text(
            json.dumps(index, indent=1)
        )  # survives an interrupted run
    if prune:
        for path in sorted(set(index) - set(remote)):
            (dest / path).unlink(missing_ok=True)
            index.pop(path)
            report.removed.append(path)
    index_path.write_text(json.dumps(index, indent=1))
    return report
