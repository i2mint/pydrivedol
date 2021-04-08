
# pydrivedol
pydrive (googledrive) with a simple (dict-like or list-like) interface

To install:	```pip install pydrivedol```

A basic Google Drive persister implemented with the pydrive library.
Keys must be names of files.

**** Authentication ***
Drive API requires OAuth2.0 for authentication.
1. Go to APIs Console (https://console.cloud.google.com/cloud-resource-manager) and make your own project.
2. Search for ‘Google Drive API’, select the entry, and click ‘Enable’.
3. Select ‘Credentials’ from the left menu, click ‘Create Credentials’, select ‘OAuth client ID’.
4. Now, the product name and consent screen need to be set -> click ‘Configure consent screen’ and follow the instructions.
   Once finished:
    - Select ‘Application type’ to be Web application.
    - Enter an appropriate name.
    - Input http://localhost:8080 for ‘Authorized JavaScript origins’.
    - Input http://localhost:8080/ for ‘Authorized redirect URIs’.
    - Click ‘Save’.
5. Click ‘Download JSON’ on the right side of Client ID to download client_secret_<really long ID>.json.
see: https://pythonhosted.org/PyDrive/quickstart.html for details.
6. Rename the file to “client_secrets.json” and place it in your working directory.

```python
>>> from pydrive import GoogleDrivePersister
>>> s = GoogleDrivePersister()
>>> k = 'foo'
>>> v = 'bar'
>>> for _key in s:
...     del s[_key]
>>> len(s)
0
>>> s[k] = v
>>> s[k]
'bar'
>>> s.get(k)
'bar'
>>> len(s)
1
>>> list(s.values())
['bar']
>>> k in s
True
>>> del s[k]
>>> k in s
False
>>> len(s)
0
```
