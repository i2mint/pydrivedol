# pydrivedol.rest

Read a Drive folder over the plain Drive v3 REST API, and mirror it to disk.

No PyDrive2 and no OAuth flow: a folder shared “anyone with the link” needs only an API
key; a private folder works the same way with an authorized session (for instance
`google.auth.transport.requests.AuthorizedSession`) passed as `session=`. That
`session` is the one seam between the two; everything else is shared.

```pycon
>>> folder = PublicDriveFolder(folder_url, api_key=key)
>>> list(folder)
['intro.mp3', 'clips/a.mp4']
>>> folder.meta('clips/a.mp4')['size']
>>> report = sync_to_dir(folder, 'mirror/', include={'.mp4'})
>>> report.added, report.changed, report.unchanged
```

### Module Attributes

| [`DRIVE_V3_FILES`](#pydrivedol.rest.DRIVE_V3_FILES)      | Drive v3 files endpoint.                                                                                                |
|----------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------|
| [`API_KEY_ENV_VARS`](#pydrivedol.rest.API_KEY_ENV_VARS)    | Environment variables the default key resolver reads, in order.                                                         |
| [`LISTING_FIELDS`](#pydrivedol.rest.LISTING_FIELDS)      | Metadata requested for every file in a listing.                                                                         |
| [`LISTING_PAGE_SIZE`](#pydrivedol.rest.LISTING_PAGE_SIZE)   | Items Drive returns per listing page (its maximum).                                                                     |
| [`SYNC_INDEX_NAME`](#pydrivedol.rest.SYNC_INDEX_NAME)     | Name of the (name -> md5) index [`sync_to_dir()`](#pydrivedol.rest.sync_to_dir) keeps inside the mirror. |
| [`PART_SUFFIX`](#pydrivedol.rest.PART_SUFFIX)         | Suffix of the temporary file a download streams into.                                                                   |
| [`DOWNLOAD_CHUNK_SIZE`](#pydrivedol.rest.DOWNLOAD_CHUNK_SIZE) | Bytes read per chunk when streaming a download to disk.                                                                 |
| [`SESSION_RETRIES`](#pydrivedol.rest.SESSION_RETRIES)     | Retries of a transient failure (429/5xx) on the default session.                                                        |
| [`REQUEST_TIMEOUT`](#pydrivedol.rest.REQUEST_TIMEOUT)     | Seconds before a Drive request times out.                                                                               |

### Functions

| [`env_api_key`](#pydrivedol.rest.env_api_key)()                                 | The default API-key resolver: the first of [`API_KEY_ENV_VARS`](#pydrivedol.rest.API_KEY_ENV_VARS) that is set.   |
|------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------|
| [`sync_to_dir`](#pydrivedol.rest.sync_to_dir)(folder, dest, \*[, include, ...]) | Mirror a Drive folder into `dest`, downloading only what is new or changed.                                                 |

### Classes

| [`PublicDriveFolder`](#pydrivedol.rest.PublicDriveFolder)(url_or_id, \*[, api_key, ...])   | Read-only `Mapping[path, bytes]` over a Drive folder, through Drive v3 REST.                                |
|-----------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------|
| [`SyncReport`](#pydrivedol.rest.SyncReport)([added, changed, unchanged, ...])       | What [`sync_to_dir()`](#pydrivedol.rest.sync_to_dir) did, as lists of folder-relative paths. |

### pydrivedol.rest.API_KEY_ENV_VARS *= ('PYDRIVEDOL_API_KEY', 'GOOGLE_API_KEY')*

Environment variables the default key resolver reads, in order.

### pydrivedol.rest.DOWNLOAD_CHUNK_SIZE *= 1048576*

Bytes read per chunk when streaming a download to disk.

### pydrivedol.rest.DRIVE_V3_FILES *= 'https://www.googleapis.com/drive/v3/files'*

Drive v3 files endpoint.

### pydrivedol.rest.LISTING_FIELDS *= ('id', 'name', 'mimeType', 'size', 'modifiedTime', 'md5Checksum')*

Metadata requested for every file in a listing.

### pydrivedol.rest.LISTING_PAGE_SIZE *= 1000*

Items Drive returns per listing page (its maximum).

### pydrivedol.rest.PART_SUFFIX *= '.pydrivedol-part'*

Suffix of the temporary file a download streams into.

### *class* pydrivedol.rest.PublicDriveFolder(url_or_id, , api_key=None, session=None, recursive=True, include=None)

Bases: [`Mapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)

Read-only `Mapping[path, bytes]` over a Drive folder, through Drive v3 REST.

Keys are paths inside the folder (`"sub/file.mp3"`); Google-native documents
(Docs, Sheets, …) have no bytes and are left out.

* **Parameters:**
  * **url_or_id** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – the folder’s URL or its id.
  * **api_key** ([`Union`](https://docs.python.org/3/library/typing.html#typing.Union)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[], [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]], [`None`](https://docs.python.org/3/builtins/constants.html#None)]) – a string, a zero-argument callable returning one, or `None` for
    [`env_api_key()`](#pydrivedol.rest.env_api_key). Never shown in `repr`. Not needed when `session`
    authenticates the requests.
  * **session** – a `requests`-compatible session; default a plain
    `requests.Session`. Pass an `AuthorizedSession` to read private folders.
  * **recursive** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – descend into subfolders.
  * **include** – `None`, a suffix or collection of suffixes, or a predicate
    `meta -> bool` (`meta` holds `name`, `mimeType`, …).

#### check_access()

Fetch the folder itself; raises `requests.HTTPError` (404/403) if unreachable.

A listing of a folder the key cannot see may come back empty rather than failing.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

#### download_to(path, dest)

Stream a file to `dest` atomically (a temporary file, then a rename).

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

#### media_url(path)

The `alt=media` URL of a file, for a server that proxies `Range` requests.

It embeds the API key when one is configured: hand it to trusted server code only.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

#### meta(path)

Metadata of one file: `id`, `name`, `size` (int), `modifiedTime`, `md5Checksum`…

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

#### refresh()

Forget the cached listing so the next access lists the folder again.

* **Return type:**
  [`PublicDriveFolder`](#pydrivedol.rest.PublicDriveFolder)

### pydrivedol.rest.REQUEST_TIMEOUT *= 60*

Seconds before a Drive request times out.

### pydrivedol.rest.SESSION_RETRIES *= 4*

Retries of a transient failure (429/5xx) on the default session.

### pydrivedol.rest.SYNC_INDEX_NAME *= '.pydrivedol/index.json'*

Name of the (name -> md5) index [`sync_to_dir()`](#pydrivedol.rest.sync_to_dir) keeps inside the mirror.

### *class* pydrivedol.rest.SyncReport(added=list(), changed=list(), unchanged=list(), removed=list(), failed=dict())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What [`sync_to_dir()`](#pydrivedol.rest.sync_to_dir) did, as lists of folder-relative paths.

### pydrivedol.rest.env_api_key()

The default API-key resolver: the first of [`API_KEY_ENV_VARS`](#pydrivedol.rest.API_KEY_ENV_VARS) that is set.

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### pydrivedol.rest.sync_to_dir(folder, dest, , include=None, index_name='.pydrivedol/index.json', prune=False, \*\*folder_kwargs)

Mirror a Drive folder into `dest`, downloading only what is new or changed.

An index (path -> md5) is kept in `dest`, so a re-run with nothing changed
downloads nothing. A file is fetched when it is absent locally or its md5 differs
from the indexed one. A file that fails to download is reported in
`SyncReport.failed` and the rest carry on.

* **Parameters:**
  * **folder** ([`Union`](https://docs.python.org/3/library/typing.html#typing.Union)[[`PublicDriveFolder`](#pydrivedol.rest.PublicDriveFolder), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – a [`PublicDriveFolder`](#pydrivedol.rest.PublicDriveFolder), or a folder URL/id (then built with
    `folder_kwargs`: `api_key`, `session`, `recursive`).
  * **dest** ([`Union`](https://docs.python.org/3/library/typing.html#typing.Union)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)]) – the local directory (created if needed).
  * **include** – as for [`PublicDriveFolder`](#pydrivedol.rest.PublicDriveFolder); applied on top of the folder’s own.
  * **index_name** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – index file, relative to `dest`.
  * **prune** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – also delete local files this mirror downloaded that are no longer in the
    folder. Narrowing `include` never prunes; an empty listing, or a change of
    `recursive` since the last run, refuses to prune.
* **Return type:**
  [`SyncReport`](#pydrivedol.rest.SyncReport)
