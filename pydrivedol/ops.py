"""Key-taking operations, as free functions over the caller's (possibly wrapped) store.

``dol`` wraps stores by delegation, so a *method* of a wrapped ``GDStore`` runs bound to the
inner leaf and receives the caller's **outer**, unmapped key (i2mint/pydrivedol#4,
i2mint/dol#83). Under a key codec ``upload`` overwrote the wrong Drive file in place and
``get_url`` shared (``anyone``/``reader``) the wrong one. A free function is handed the outer
store, so the key is resolved through every layer:

- :func:`get_url` ``(reader, key)``: ``key in reader`` through the caller's own store (key
  mapping and any scope filter), then the link of the file the leaf holds under the mapped key.
- :func:`metadata` ``(files, key)``: the same for :class:`~pydrivedol.base.GDFiles`.
- :func:`upload` ``(store, key, value)``: performs ``store[key] = value`` on the caller's own
  store, after authorising the leaf (through a context variable, for that one mapped key) to
  honour the ``convert`` / ``google_mimetype`` options and report the file's link. So key
  mapping, value codecs, write guards (read-only wrappers) and scope are the layers' own. A
  layer that redirects, buffers or swallows the write makes ``upload`` raise ``RuntimeError``.

The methods ``GDReader.get_url``, ``GDStore.upload`` and ``GDFiles.metadata`` were removed (they
raise ``AttributeError`` naming the replacement). Same design as cosmodol.ops and s3dol's
ADR-0011.

What stays outside reach, stated rather than hidden: ``upload(path=...)`` reads the file into
memory (the store's ``__setitem__`` takes bytes) and the value goes through the store's value
codec like any value; a layer that performs the write in another thread escapes the options
(the write then happens as a plain ``store[key] = value``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from dol import inner_most_key

from pydrivedol.base import (
    DEFAULT_METADATA_FIELDS,
    GDFiles,
    GDReader,
    GDStore,
    _UPLOAD_REQUEST,
    _UploadRequest,
)


def _leaf_of(store, cls):
    """The innermost layer of ``store`` that is an instance of ``cls``."""
    cur, seen = store, set()
    while not isinstance(cur, cls):
        inner = getattr(cur, "store", None)
        if inner is None or id(cur) in seen:
            raise TypeError(f"{type(store).__name__} does not wrap a {cls.__name__}")
        seen.add(id(cur))
        cur = inner
    return cur


def _inner_key(store, k):
    """``k`` resolved through every layer of ``store``; ``k`` itself if no layer maps keys."""
    inner = inner_most_key(store, k, default=None)
    return inner if isinstance(inner, str) else k


def get_url(
    reader,
    key: str,
    *,
    permission_type: str = "anyone",
    permission_role: str = "reader",
) -> str:
    """Shareable URL of ``key`` (a key of ``reader``), granting the permission on that file.

    :raises KeyError: if ``key`` is not in ``reader`` (checked through the caller's own store)
    """
    leaf = _leaf_of(reader, GDReader)
    if key not in reader:
        raise KeyError(f"File not found: {key}")
    return leaf._get_url(
        _inner_key(reader, key),
        permission_type=permission_type,
        permission_role=permission_role,
    )


def metadata(files, key: str, *, fields=DEFAULT_METADATA_FIELDS) -> dict:
    """Metadata (name, size, mimeType, modifiedDate) of ``key`` (a key of ``files``), no download."""
    leaf = _leaf_of(files, GDFiles)
    if key not in files:
        raise KeyError(f"File not found or not accessible: {key}")
    return leaf._metadata(_inner_key(files, key), fields=fields)


def upload(
    store,
    key: str,
    value=None,
    *,
    path: Optional[str] = None,
    convert: Optional[bool] = None,
    google_mimetype: Optional[str] = None,
) -> str:
    """Write ``value`` (or the file at ``path``) under ``key`` of ``store``; return the file's link.

    With ``convert=True`` (or the leaf's ``convert_office``) an office file becomes a native
    Google doc. See the module docstring for how the write goes through the caller's store.
    """
    leaf = _leaf_of(store, GDStore)
    if (value is None) == (path is None):
        raise ValueError("Pass exactly one of value= and path=")
    if path is not None:
        value = Path(path).read_bytes()
    request = _UploadRequest(
        key=_inner_key(store, key), convert=convert, google_mimetype=google_mimetype
    )
    token = _UPLOAD_REQUEST.set(request)
    try:
        store[key] = value
    finally:
        _UPLOAD_REQUEST.reset(token)
    if request.url is None:
        raise RuntimeError(
            f"The write of {key!r} did not reach the Drive store under {request.key!r}: a "
            "layer redirected, buffered or swallowed it."
        )
    return request.url
