# pydrivedol.base

Base objects for pydrivedol: download functions, GDFiles, GDReader, GDStore.

Two access levels, both returning `bytes`:

- **Public, no setup**: [`get_bytes()`](#pydrivedol.base.get_bytes) against Google’s unauthenticated download endpoint.
  It raises [`NotPubliclyShared`](#pydrivedol.base.NotPubliclyShared) rather than handing back the HTML sign-in page Drive
  serves (with HTTP 200) when the file is not shared publicly.
- **Authenticated**: pass a PyDrive2 `GoogleDrive` – from [`drive_from_service_account()`](#pydrivedol.base.drive_from_service_account)
  for headless use – as `drive=` to [`get_bytes()`](#pydrivedol.base.get_bytes) / [`get_metadata()`](#pydrivedol.base.get_metadata), or build a
  [`GDFiles`](#pydrivedol.base.GDFiles) (file-level Mapping, keyed by file id or URL), [`GDReader`](#pydrivedol.base.GDReader) /
  [`GDStore`](#pydrivedol.base.GDStore) (folder-level, keyed by relative path).

### Module Attributes

| [`DEFAULT_METADATA_FIELDS`](#pydrivedol.base.DEFAULT_METADATA_FIELDS)   | enough to decide whether a download is worth making.   |
|----------------------------------------------------------------------------|--------------------------------------------------------|

### Functions

| [`drive_from_service_account`](#pydrivedol.base.drive_from_service_account)(key_file, \*[, ...])   | Build an authenticated `GoogleDrive` from a service-account key file.        |
|----------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------|
| [`get_bytes`](#pydrivedol.base.get_bytes)(url, \*[, local_path, use_cache, ...])  | Download bytes from a Google Drive URL.                                      |
| [`get_metadata`](#pydrivedol.base.get_metadata)(url_or_id, \*, drive[, fields])      | Fetch a Drive file's metadata **without downloading its content**.           |
| [`xlsx_to_google_sheet`](#pydrivedol.base.xlsx_to_google_sheet)(folder_url, title, xlsx, \*) | Upload an `.xlsx` as a **native Google Sheet** and return its shareable URL. |

### Classes

| [`GDFiles`](#pydrivedol.base.GDFiles)(drive, \*[, folder_url, max_levels, ...])   | Read-only Mapping of Google Drive **files**, keyed by file id or file URL.   |
|------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------|
| [`GDReader`](#pydrivedol.base.GDReader)(folder_url, \*[, max_levels, ...])         | Read-only Mapping to Google Drive folder.                                    |
| [`GDStore`](#pydrivedol.base.GDStore)(folder_url, \*[, convert_office])           | Read-write MutableMapping to Google Drive folder.                            |

### Exceptions

| [`NotPubliclyShared`](#pydrivedol.base.NotPubliclyShared)   | Raised when an unauthenticated download returns a sign-in page instead of file content.   |
|----------------------------------------------------------------------|-------------------------------------------------------------------------------------------|

### pydrivedol.base.DEFAULT_METADATA_FIELDS *= ('id', 'title', 'mimeType', 'fileSize', 'modifiedDate', 'alternateLink')*

enough to decide whether a download is worth making.

* **Type:**
  Metadata fields fetched by default

### *class* pydrivedol.base.GDFiles(drive, , folder_url=None, max_levels=None, include_hidden=False)

Bases: [`Mapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)

Read-only Mapping of Google Drive **files**, keyed by file id or file URL.

The file-level sibling of [`GDReader`](#pydrivedol.base.GDReader). Where `GDReader` is scoped to a folder and
keyed by relative path, `GDFiles` is keyed by whatever identifies a single file: a bare
file id, or any Drive file URL – both normalise to the same key through
`_extract_file_id()`, so `files[url]` and `files[file_id]` are one entry. Values
are `bytes`, fetched over the authenticated API, so **private** files work as long as
they are shared with the authenticated identity.

That is the shape a caller has when files arrive as *links* – the usual Drive sharing
idiom – rather than as a folder listing.

`drive` is required and injected: a file-level view is pointless without auth, since its
whole reason to exist is reaching files the public endpoint cannot.

**Iteration requires a scope.** Unscoped, this mapping covers the entire Drive, which is
unbounded and paginated; enumerating it is never what a caller wants, so offering it would
be a trap. `__iter__`/`__len__` therefore raise `NotImplementedError` unless
`folder_url` is given, in which case they yield that folder’s file **ids** (honouring
`max_levels` and `include_hidden`, the same traversal [`GDReader`](#pydrivedol.base.GDReader) uses). Lookup
always works, scoped or not – it is the primary use case and needs no listing.

```pycon
>>> drive = drive_from_service_account('service-account-key.json')
>>> files = GDFiles(drive)
>>> files.metadata(url)['fileSize']  # cheap: no download
>>> content = files[url]  # or files[file_id]
>>> url in files  # metadata probe, not a download
True
```

Scoped, so it can be listed:

```pycon
>>> scoped = GDFiles(drive, folder_url=folder_url)
>>> list(scoped)  # file ids
```

#### metadata(key, , fields=('id', 'title', 'mimeType', 'fileSize', 'modifiedDate', 'alternateLink'))

Metadata (name, size, mimeType, modifiedDate) for `key`, without downloading it.

Thin method form of [`get_metadata()`](#pydrivedol.base.get_metadata) – see it for the field semantics.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### *class* pydrivedol.base.GDReader(folder_url, , max_levels=None, credentials_file='client_secrets.json', settings_file='settings.yaml', include_hidden=False, drive=None)

Bases: [`Mapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)

Read-only Mapping to Google Drive folder.

Keys are relative file paths, values are file contents as bytes.

```pycon
>>> reader = GDReader(folder_url)
>>> list(reader)[:3]
>>> content = reader['path/to/file.txt']
>>> len(reader)
>>> 'file.txt' in reader
>>> url = reader.get_url('file.txt')
```

#### get_url(key, , permission_type='anyone', permission_role='reader')

Get shareable URL for file.

* **Parameters:**
  * **key** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – File path
  * **permission_type** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – ‘anyone’, ‘user’, ‘group’, ‘domain’
  * **permission_role** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – ‘reader’, ‘writer’, ‘commenter’
* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
* **Returns:**
  Shareable URL

### *class* pydrivedol.base.GDStore(folder_url, , convert_office=False, \*\*kwargs)

Bases: [`GDReader`](#pydrivedol.base.GDReader), [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)

Read-write MutableMapping to Google Drive folder.

Extends GDReader with write and delete operations.

```pycon
>>> store = GDStore(folder_url)
>>> store['file.txt'] = b'Hello'
>>> store['dir/file.txt'] = b'Nested'
>>> del store['file.txt']
```

Pass `convert_office=True` to make `store['x.xlsx'] = xlsx_bytes` create a \*native
Google Sheet\* (xlsx → Sheet, docx → Doc, pptx → Slides) instead of an uploaded blob. For
one-off control use [`upload()`](#pydrivedol.base.GDStore.upload) with `convert=True`.

#### upload(key, value=None, , path=None, convert=None, google_mimetype=None)

Upload `value` (bytes) or a file `path` to `key`; return the shareable URL.

With `convert=True` (or the store’s `convert_office` default) an office file becomes a
native Google doc — e.g. `store.upload('schema.xlsx', xlsx_bytes, convert=True)` yields a
Google Sheet. Updates an existing same-named file in the target folder, else creates it.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### *exception* pydrivedol.base.NotPubliclyShared

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

Raised when an unauthenticated download returns a sign-in page instead of file content.

Google serves its HTML sign-in / permission interstitial with HTTP **200**, so without an
explicit check that page body would be returned as if it were the file: plausible-looking
bytes that only blow up much later, in whatever tries to parse them. Catch this to fall
back to an authenticated fetch (`get_bytes(url, drive=...)`).

### pydrivedol.base.drive_from_service_account(key_file, , scopes=('https://www.googleapis.com/auth/drive',), subject=None)

Build an authenticated `GoogleDrive` from a service-account key file.

For headless / server use — no browser OAuth flow. Share the target Drive folder
with the service account’s `client_email` (Viewer for read, Editor for write).
Pass the resulting drive to `GDReader`/`GDStore` via their `drive=` argument.

* **Parameters:**
  * **key_file** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – path to the service-account JSON key.
  * **scopes** – OAuth scopes; default is full Drive (use `.../auth/drive.readonly`
    to enforce read-only at the token level).
  * **subject** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – optional user email to impersonate (domain-wide delegation).

```pycon
>>> drive = drive_from_service_account('sa-key.json')
>>> reader = GDReader(folder_url, drive=drive)
```

### pydrivedol.base.get_bytes(url, , local_path=False, use_cache=False, drive=None, allow_html=False)

Download bytes from a Google Drive URL.

Without `drive` this uses Google’s public download endpoint – no API setup, but it only
reaches files shared “anyone with the link”, and it raises [`NotPubliclyShared`](#pydrivedol.base.NotPubliclyShared) if
Drive answers with its sign-in page instead of the file. Pass an authenticated `drive`
(see [`drive_from_service_account()`](#pydrivedol.base.drive_from_service_account)) to reach **private** files shared with that
identity.

* **Parameters:**
  * **url** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Google Drive file link (a bare file id is accepted too).
  * **local_path** (`Union`[[`bool`](https://docs.python.org/3/builtins/functions.html#bool), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – False (return bytes), True (save to temp), or str (save to path)
  * **use_cache** (`Union`[[`bool`](https://docs.python.org/3/builtins/functions.html#bool), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – False (no cache), True (use ~/.cache/pydrivedol/cached/), or str (use dir)
  * **drive** – an authenticated PyDrive2 `GoogleDrive`. When given, the download goes through
    the API; `None` (default) keeps the public, unauthenticated behaviour exactly.
  * **allow_html** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – by default an HTML payload from the *public* endpoint raises, because it is
    Google’s login page masquerading as file content. Set True only when the file you
    are downloading genuinely is HTML. Ignored on the authenticated path.
* **Return type:**
  `Union`[[`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
* **Returns:**
  bytes if local_path is False or str, filepath str if local_path is True
* **Raises:**
  [**NotPubliclyShared**](#pydrivedol.base.NotPubliclyShared) – the public endpoint returned a sign-in page; pass `drive=`.

```pycon
>>> content = get_bytes(url)
>>> path = get_bytes(url, local_path=True)
>>> content = get_bytes(url, local_path='/tmp/file.txt')
```

A private file, shared with a service account:

```pycon
>>> drive = drive_from_service_account('service-account-key.json')
>>> content = get_bytes(private_url, drive=drive)
```

### pydrivedol.base.get_metadata(url_or_id, , drive, fields=('id', 'title', 'mimeType', 'fileSize', 'modifiedDate', 'alternateLink'))

Fetch a Drive file’s metadata **without downloading its content**.

The cheap half of [`get_bytes()`](#pydrivedol.base.get_bytes): use it to decide *whether* to download – an 18MB
spreadsheet is not something you fetch just to learn its name.

* **Parameters:**
  * **url_or_id** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – a Drive file URL or a bare file id.
  * **drive** – an authenticated PyDrive2 `GoogleDrive` (see
    [`drive_from_service_account()`](#pydrivedol.base.drive_from_service_account)).
  * **fields** – which metadata fields to request; `None` fetches everything Drive offers.
    The default, [`DEFAULT_METADATA_FIELDS`](#pydrivedol.base.DEFAULT_METADATA_FIELDS), covers name (`title`), `fileSize`,
    `mimeType` and `modifiedDate`.
* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)
* **Returns:**
  A plain `dict` of the requested fields that the file actually has. `fileSize` is
  returned as an `int` (Drive sends it as a string), and is **absent** for
  Google-native files – Sheets/Docs/Slides have no stored byte size.

```pycon
>>> drive = drive_from_service_account('service-account-key.json')
>>> info = get_metadata(url, drive=drive)
>>> info['title'], info['fileSize']
('client_export.xlsx', 18512345)
```

### pydrivedol.base.xlsx_to_google_sheet(folder_url, title, xlsx, , share_with=(), anyone_reader=False, credentials_file='client_secrets.json', settings_file='settings.yaml', drive=None)

Upload an `.xlsx` as a **native Google Sheet** and return its shareable URL.

The whole point: Drive can *convert* an uploaded spreadsheet into an editable Google Sheet
(preserving cell formatting), rather than parking an `.xlsx` blob. This wraps that.

* **Parameters:**
  * **folder_url** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – destination Drive folder URL (`None` → the account’s root).
  * **title** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – the Google Sheet’s name.
  * **xlsx** (`Union`[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path), [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)]) – a path (`str`/`Path`) or raw `bytes`.
  * **share_with** – emails to grant `writer` access (no notification email sent).
  * **anyone_reader** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – also grant anyone-with-link `reader` access.
  * **settings_file** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – PyDrive2 auth (ignored if `drive` is given).
  * **drive** – an existing PyDrive2 `GoogleDrive` (skips auth).
* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
* **Returns:**
  The Google Sheet URL (`alternateLink`).

```pycon
>>> url = xlsx_to_google_sheet(folder_url, 'My Schema', '/tmp/schema.xlsx',
...                            anyone_reader=True)
```
