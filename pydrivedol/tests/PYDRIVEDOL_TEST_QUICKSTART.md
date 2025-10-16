# pydrivedol Testing Quick Reference

## TL;DR

```bash
# 1. Run tests (some will be skipped without setup)
pytest test_pydrivedol.py -v

# 2. See what's configured
python test_pydrivedol.py

# 3. Full setup (one-time)
export PYDRIVEDOL_TEST_FOLDER_URL="https://drive.google.com/drive/folders/YOUR_ID"
export PYDRIVEDOL_TEST_PUBLIC_FILE_URL="https://drive.google.com/file/d/YOUR_ID/view"
# ... then rerun tests
```

## Environment Variables

| Variable | Purpose | Required For |
|----------|---------|--------------|
| `PYDRIVEDOL_TEST_PUBLIC_FILE_URL` | Public file URL | TestGetBytes |
| `PYDRIVEDOL_TEST_FOLDER_URL` | Folder URL | TestGDReader, TestGDStore |
| `client_secrets.json` file | OAuth2 credentials | TestGDReader, TestGDStore |

## Quick Setup

### 1. Create Test Resources

```bash
# In Google Drive:
# 1. Create folder "pydrivedol_tests"
# 2. Add file "test_file.txt" with content
# 3. Share file publicly
# 4. Get both URLs
```

### 2. Set Environment Variables (Choose One)

**Temporary:**
```bash
export PYDRIVEDOL_TEST_FOLDER_URL="https://drive.google.com/drive/folders/1a2b3c..."
export PYDRIVEDOL_TEST_PUBLIC_FILE_URL="https://drive.google.com/file/d/1a2b3c.../view"
```

**Permanent (bash):**
```bash
echo 'export PYDRIVEDOL_TEST_FOLDER_URL="https://..."' >> ~/.bashrc
echo 'export PYDRIVEDOL_TEST_PUBLIC_FILE_URL="https://..."' >> ~/.bashrc
source ~/.bashrc
```

**Permanent (zsh):**
```bash
echo 'export PYDRIVEDOL_TEST_FOLDER_URL="https://..."' >> ~/.zshrc
echo 'export PYDRIVEDOL_TEST_PUBLIC_FILE_URL="https://..."' >> ~/.zshrc
source ~/.zshrc
```

**Project-specific (.envrc with direnv):**
```bash
# Create .envrc file with:
export PYDRIVEDOL_TEST_FOLDER_URL="https://..."
export PYDRIVEDOL_TEST_PUBLIC_FILE_URL="https://..."

# Then:
direnv allow
```

### 3. OAuth2 Setup (for API tests)

```bash
# 1. Go to https://console.cloud.google.com/
# 2. Create project → Enable Google Drive API
# 3. Create OAuth2 credentials (Desktop app)
# 4. Download as client_secrets.json
# 5. Place in working directory
```

### 4. Run Tests

```bash
pytest test_pydrivedol.py -v
```

## What Runs When

| Test Suite | Runs Without Setup | Requires |
|------------|-------------------|----------|
| TestHelperFunctions | ✓ Always | Nothing |
| TestGetBytes | Only with URL | `PYDRIVEDOL_TEST_PUBLIC_FILE_URL` |
| TestGDReader | Only with URL + OAuth | `PYDRIVEDOL_TEST_FOLDER_URL` + `client_secrets.json` |
| TestGDStore | Only with URL + OAuth | `PYDRIVEDOL_TEST_FOLDER_URL` + `client_secrets.json` |

## Useful Commands

```bash
# Check configuration
python test_pydrivedol.py

# Verify env vars are set
env | grep PYDRIVEDOL

# Run specific test suite
pytest test_pydrivedol.py::TestGetBytes -v

# Run one specific test
pytest test_pydrivedol.py::TestGetBytes::test_get_bytes_returns_bytes -v

# See all tests without running
pytest test_pydrivedol.py --collect-only

# Run tests with more detail
pytest test_pydrivedol.py -vv
```

## Troubleshooting

**Tests skipped?**
```bash
python test_pydrivedol.py  # Shows what's missing
```

**Can't authenticate?**
```bash
# Delete credentials and try again
rm client_secrets.json
# Download new credentials from Google Cloud Console
```

**Import error?**
```bash
pip install pydrive2 requests
```

For detailed setup: See [TEST_SETUP.md](TEST_SETUP.md)