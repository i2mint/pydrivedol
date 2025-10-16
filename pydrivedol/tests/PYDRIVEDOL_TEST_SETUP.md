# Testing pydrivedol

## Quick Start

### 1. Run Tests Without Setup

Some tests (helper functions) work without any setup:

```bash
pytest test_pydrivedol.py -v
```

You'll see tests like `TestHelperFunctions` pass, while others are skipped.

### 2. Check Test Status

See which tests will run with your current configuration:

```bash
python test_pydrivedol.py
```

This shows a status report of configured environment variables and which test suites will run.

## Full Test Setup

### Step 1: Create Test Resources in Google Drive

1. **Create a test folder:**
   - Name it `pydrivedol_tests` (or any name you prefer)
   - This will hold test files

2. **Create a test file:**
   - In the test folder, create a file: `test_file.txt`
   - Add some content: "test content for pydrivedol"

3. **Get the folder URL:**
   - Right-click the folder → Share → Copy link
   - Example: `https://drive.google.com/drive/folders/1a2b3c4d5e6f7g8h9i0j`

4. **Get the file URL:**
   - Right-click the test file → Share
   - Set to "Anyone with the link" (public)
   - Copy link
   - Example: `https://drive.google.com/file/d/1a2b3c4d5e6f7g8h9i0j/view`

### Step 2: Setup OAuth2 (for GDReader/GDStore tests)

1. **Go to [Google Cloud Console](https://console.cloud.google.com/)**

2. **Create/Select Project:**
   - Create new project or select existing
   - Name it (e.g., "pydrivedol-testing")

3. **Enable Google Drive API:**
   - Navigate to "APIs & Services" → "Library"
   - Search "Google Drive API"
   - Click "Enable"

4. **Create OAuth2 Credentials:**
   - Go to "APIs & Services" → "Credentials"
   - Click "Create Credentials" → "OAuth client ID"
   - Choose "Desktop app"
   - Name it (e.g., "pydrivedol-test-client")
   - Click "Create"

5. **Download Credentials:**
   - Download the JSON file
   - Rename to `client_secrets.json`
   - Place in your working directory

### Step 3: Set Environment Variables

#### Option A: Temporary (Current Shell Session)

```bash
export PYDRIVEDOL_TEST_FOLDER_URL="https://drive.google.com/drive/folders/YOUR_FOLDER_ID"
export PYDRIVEDOL_TEST_PUBLIC_FILE_URL="https://drive.google.com/file/d/YOUR_FILE_ID/view"
```

#### Option B: Permanent (Add to Shell Profile)

**For bash (~/.bashrc or ~/.bash_profile):**
```bash
echo 'export PYDRIVEDOL_TEST_FOLDER_URL="https://drive.google.com/drive/folders/YOUR_FOLDER_ID"' >> ~/.bashrc
echo 'export PYDRIVEDOL_TEST_PUBLIC_FILE_URL="https://drive.google.com/file/d/YOUR_FILE_ID/view"' >> ~/.bashrc
source ~/.bashrc
```

**For zsh (~/.zshrc):**
```bash
echo 'export PYDRIVEDOL_TEST_FOLDER_URL="https://drive.google.com/drive/folders/YOUR_FOLDER_ID"' >> ~/.zshrc
echo 'export PYDRIVEDOL_TEST_PUBLIC_FILE_URL="https://drive.google.com/file/d/YOUR_FILE_ID/view"' >> ~/.zshrc
source ~/.zshrc
```

#### Option C: Using direnv (Recommended for Project-Specific)

1. **Install direnv:** `brew install direnv` (macOS) or see [direnv.net](https://direnv.net/)

2. **Create `.envrc` in project directory:**
   ```bash
   export PYDRIVEDOL_TEST_FOLDER_URL="https://drive.google.com/drive/folders/YOUR_FOLDER_ID"
   export PYDRIVEDOL_TEST_PUBLIC_FILE_URL="https://drive.google.com/file/d/YOUR_FILE_ID/view"
   ```

3. **Allow direnv:**
   ```bash
   direnv allow
   ```

Now environment variables load automatically when you enter the directory!

### Step 4: Verify Configuration

Check that environment variables are set:

```bash
echo $PYDRIVEDOL_TEST_FOLDER_URL
echo $PYDRIVEDOL_TEST_PUBLIC_FILE_URL
```

Or run the test status checker:

```bash
python test_pydrivedol.py
```

### Step 5: Run Tests

```bash
# Run all tests with verbose output
pytest test_pydrivedol.py -v

# Run specific test class
pytest test_pydrivedol.py::TestGetBytes -v

# Run specific test
pytest test_pydrivedol.py::TestGetBytes::test_get_bytes_returns_bytes -v

# Show test collection without running
pytest test_pydrivedol.py --collect-only
```

## What Gets Tested

### TestHelperFunctions (Always Run)
- ✓ URL parsing for file IDs
- ✓ URL parsing for folder IDs
- **No setup required**

### TestGetBytes (Requires Public File URL)
- Download bytes from public URL
- Save to temp file
- Save to specific path
- Caching functionality
- **Requires:** `PYDRIVEDOL_TEST_PUBLIC_FILE_URL`

### TestGDReader (Requires Folder URL + OAuth2)
- Reader initialization
- File iteration
- File reading
- Contains check
- Max levels parameter
- **Requires:** `PYDRIVEDOL_TEST_FOLDER_URL` + `client_secrets.json`

### TestGDStore (Requires Folder URL + OAuth2)
- Write and read files
- Nested folder creation
- File deletion
- File updates
- **Requires:** `PYDRIVEDOL_TEST_FOLDER_URL` + `client_secrets.json`

## First Time Authentication

When you first run tests that use GDReader/GDStore:

1. A browser window will open
2. Sign in to your Google account
3. Grant permissions
4. Credentials are saved for future use

The credentials are saved in `credentials_file` (default: `client_secrets.json`), so you only need to authenticate once.

## Troubleshooting

### Tests are skipped

**Check environment variables:**
```bash
python test_pydrivedol.py
```

**Or check directly:**
```bash
env | grep PYDRIVEDOL
```

### "No module named 'pydrive2'"

```bash
pip install pydrive2
```

### "Invalid client secrets file"

1. Ensure `client_secrets.json` is in your working directory
2. Verify it's valid JSON from Google Cloud Console
3. Try creating new OAuth2 credentials

### "Permission denied" or "Forbidden"

1. Ensure the Google account used has access to the test folder
2. Check folder/file sharing settings
3. Re-authenticate: delete `credentials_file` and run tests again

## CI/CD Setup

For automated testing in CI/CD:

1. **Store credentials as secrets:**
   - `PYDRIVEDOL_TEST_FOLDER_URL`
   - `PYDRIVEDOL_TEST_PUBLIC_FILE_URL`
   - `CLIENT_SECRETS_JSON` (base64 encoded client_secrets.json)

2. **In CI pipeline:**
   ```bash
   # Decode and save client_secrets.json
   echo "$CLIENT_SECRETS_JSON" | base64 -d > client_secrets.json
   
   # Set environment variables (already set as secrets)
   # Run tests
   pytest test_pydrivedol.py -v
   ```

**Note:** For OAuth2 in CI, you'll need to use service accounts or pre-generated credentials. See Google Drive API documentation for service account setup.

## Example Output

**With all environment variables set:**
```
======================================================================
PyDriveDol Test Configuration Status
======================================================================
✓ PYDRIVEDOL_TEST_PUBLIC_FILE_URL: https://drive.google.com/file/d/1a2b3c4d5e6f7...
✓ PYDRIVEDOL_TEST_FOLDER_URL: https://drive.google.com/drive/folders/1a2b3c4...

Tests that will run:
  ✓ TestGetBytes (4 tests)
  ✓ TestGDReader (6 tests)
  ✓ TestGDStore (4 tests)
  ✓ TestHelperFunctions (2 tests) - Always run

For full setup instructions, see:
  https://github.com/i2mint/pydrivedol#testing
======================================================================
```

**Without environment variables:**
```
======================================================================
PyDriveDol Test Configuration Status
======================================================================
✗ PYDRIVEDOL_TEST_PUBLIC_FILE_URL: Not set
  Set with: export PYDRIVEDOL_TEST_PUBLIC_FILE_URL='https://...'
✗ PYDRIVEDOL_TEST_FOLDER_URL: Not set
  Set with: export PYDRIVEDOL_TEST_FOLDER_URL='https://...'

Tests that will run:
  ✗ TestGetBytes (4 tests) - SKIPPED
  ✗ TestGDReader (6 tests) - SKIPPED
  ✗ TestGDStore (4 tests) - SKIPPED
  ✓ TestHelperFunctions (2 tests) - Always run

For full setup instructions, see:
  https://github.com/i2mint/pydrivedol#testing
======================================================================
```