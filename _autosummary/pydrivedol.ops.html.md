# pydrivedol.ops

Key-taking operations, as free functions over the caller’s (possibly wrapped) store.

`dol` wraps stores by delegation, so a *method* of a wrapped `GDStore` runs bound to the
inner leaf and receives the caller’s **outer**, unmapped key (i2mint/pydrivedol#4,
i2mint/dol#83). Under a key codec `upload` overwrote the wrong Drive file in place and
`get_url` shared (`anyone`/`reader`) the wrong one. A free function is handed the outer
store, so the key is resolved through every layer:

- [`get_url()`](#pydrivedol.ops.get_url) `(reader, key)`: `key in reader` through the caller’s own store (key
  mapping and any scope filter), then the link of the file the leaf holds under the mapped key.
- [`metadata()`](#pydrivedol.ops.metadata) `(files, key)`: the same for [`GDFiles`](pydrivedol.base.html.md#pydrivedol.base.GDFiles).
- [`upload()`](#pydrivedol.ops.upload) `(store, key, value)`: performs `store[key] = value` on the caller’s own
  store, after authorising the leaf (through a context variable, for that one mapped key) to
  honour the `convert` / `google_mimetype` options and report the file’s link. So key
  mapping, value codecs, write guards (read-only wrappers) and scope are the layers’ own. A
  layer that redirects, buffers or swallows the write makes `upload` raise `RuntimeError`.

The methods `GDReader.get_url`, `GDStore.upload` and `GDFiles.metadata` were removed (they
raise `AttributeError` naming the replacement). Same design as cosmodol.ops and s3dol’s
ADR-0011.

What stays outside reach, stated rather than hidden: `upload(path=...)` reads the file into
memory (the store’s `__setitem__` takes bytes) and the value goes through the store’s value
codec like any value; a layer that performs the write in another thread escapes the options
(the write then happens as a plain `store[key] = value`).

### Functions

| [`get_url`](#pydrivedol.ops.get_url)(reader, key, \*[, permission_type, ...])   | Shareable URL of `key` (a key of `reader`), granting the permission on that file.       |
|-----------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------|
| [`metadata`](#pydrivedol.ops.metadata)(files, key, \*[, fields])                 | Metadata (name, size, mimeType, modifiedDate) of `key` (a key of `files`), no download. |
| [`upload`](#pydrivedol.ops.upload)(store, key[, value, path, convert, ...])    | Write `value` (or the file at `path`) under `key` of `store`; return the file's link.   |

### pydrivedol.ops.get_url(reader, key, , permission_type='anyone', permission_role='reader')

Shareable URL of `key` (a key of `reader`), granting the permission on that file.

* **Raises:**
  [**KeyError**](https://docs.python.org/3/builtins/exceptions.html#KeyError) – if `key` is not in `reader` (checked through the caller’s own store)
* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### pydrivedol.ops.metadata(files, key, , fields=('id', 'title', 'mimeType', 'fileSize', 'modifiedDate', 'alternateLink'))

Metadata (name, size, mimeType, modifiedDate) of `key` (a key of `files`), no download.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### pydrivedol.ops.upload(store, key, value=None, , path=None, convert=None, google_mimetype=None)

Write `value` (or the file at `path`) under `key` of `store`; return the file’s link.

With `convert=True` (or the leaf’s `convert_office`) an office file becomes a native
Google doc. See the module docstring for how the write goes through the caller’s store.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
