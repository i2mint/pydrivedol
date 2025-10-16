"""
Tests for pydrivedol module.

Setup via Environment Variables:
1. Create a folder 'pydrivedol_tests' in your Google Drive
2. Share it and get the URL
3. Create a test file in that folder (e.g., 'test_file.txt' with content 'test content')
4. Make the test file publicly shareable and get its URL
5. Set environment variables:

   export PYDRIVEDOL_TEST_FOLDER_URL="https://drive.google.com/drive/folders/YOUR_FOLDER_ID"
   export PYDRIVEDOL_TEST_PUBLIC_FILE_URL="https://drive.google.com/file/d/YOUR_FILE_ID/view"

6. For API tests, ensure client_secrets.json is in your working directory

Run tests:
    pytest test_pydrivedol.py -v
    # or
    python test_pydrivedol.py

Skip tests if env vars not set:
    pytest test_pydrivedol.py -v  # Will skip tests requiring env vars

Check which tests would run:
    pytest test_pydrivedol.py -v --collect-only
"""

import os
import tempfile
from pathlib import Path
import pytest

# Import module under test
import pydrivedol

# Get test URLs from environment variables
TEST_FOLDER_URL = os.environ.get('PYDRIVEDOL_TEST_FOLDER_URL')
TEST_PUBLIC_FILE_URL = os.environ.get('PYDRIVEDOL_TEST_PUBLIC_FILE_URL')

# Conditional skip markers
skip_if_no_public_url = pytest.mark.skipif(
    TEST_PUBLIC_FILE_URL is None,
    reason="PYDRIVEDOL_TEST_PUBLIC_FILE_URL not set. "
    "Set with: export PYDRIVEDOL_TEST_PUBLIC_FILE_URL='https://...'",
)

skip_if_no_folder_url = pytest.mark.skipif(
    TEST_FOLDER_URL is None,
    reason="PYDRIVEDOL_TEST_FOLDER_URL not set. "
    "Set with: export PYDRIVEDOL_TEST_FOLDER_URL='https://...'",
)


class TestGetBytes:
    """Tests for get_bytes function."""

    @skip_if_no_public_url
    def test_get_bytes_returns_bytes(self):
        """Test that get_bytes returns bytes by default."""
        content = pydrivedol.get_bytes(TEST_PUBLIC_FILE_URL)
        assert isinstance(content, bytes)
        assert len(content) > 0

    @skip_if_no_public_url
    def test_get_bytes_with_temp_file(self):
        """Test saving to temp file."""
        filepath = pydrivedol.get_bytes(TEST_PUBLIC_FILE_URL, local_path=True)
        assert isinstance(filepath, str)
        assert os.path.exists(filepath)
        assert os.path.getsize(filepath) > 0
        # Clean up
        os.remove(filepath)

    @skip_if_no_public_url
    def test_get_bytes_with_specific_path(self):
        """Test saving to specific path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, 'test_file.txt')
            content = pydrivedol.get_bytes(TEST_PUBLIC_FILE_URL, local_path=filepath)

            assert isinstance(content, bytes)
            assert os.path.exists(filepath)
            assert Path(filepath).read_bytes() == content

    @skip_if_no_public_url
    def test_get_bytes_with_cache(self):
        """Test caching functionality."""
        with tempfile.TemporaryDirectory() as cache_dir:
            # First call - downloads
            content1 = pydrivedol.get_bytes(TEST_PUBLIC_FILE_URL, use_cache=cache_dir)

            # Second call - from cache
            content2 = pydrivedol.get_bytes(TEST_PUBLIC_FILE_URL, use_cache=cache_dir)

            assert content1 == content2
            assert len(os.listdir(cache_dir)) == 1  # One cached file


class TestGDReader:
    """Tests for GDReader class."""

    @skip_if_no_folder_url
    def test_reader_initialization(self):
        """Test that GDReader can be initialized."""
        reader = pydrivedol.GDReader(TEST_FOLDER_URL)
        assert reader.folder_url == TEST_FOLDER_URL
        assert reader.folder_id is not None

    @skip_if_no_folder_url
    def test_reader_iteration(self):
        """Test iterating over files."""
        reader = pydrivedol.GDReader(TEST_FOLDER_URL, max_levels=0)
        files = list(reader)
        assert isinstance(files, list)
        # Should have at least the test file
        assert len(files) > 0

    @skip_if_no_folder_url
    def test_reader_len(self):
        """Test __len__ method."""
        reader = pydrivedol.GDReader(TEST_FOLDER_URL, max_levels=0)
        assert len(reader) > 0

    @skip_if_no_folder_url
    def test_reader_contains(self):
        """Test __contains__ method."""
        reader = pydrivedol.GDReader(TEST_FOLDER_URL, max_levels=0)
        files = list(reader)
        if files:
            # Check that first file is in reader
            assert files[0] in reader
            # Check that non-existent file is not in reader
            assert 'nonexistent_file_xyz.txt' not in reader

    @skip_if_no_folder_url
    def test_reader_getitem(self):
        """Test __getitem__ method."""
        reader = pydrivedol.GDReader(TEST_FOLDER_URL, max_levels=0)
        files = list(reader)
        if files:
            content = reader[files[0]]
            assert isinstance(content, bytes)
            assert len(content) > 0

    @skip_if_no_folder_url
    def test_reader_max_levels(self):
        """Test max_levels parameter."""
        # Only files in root folder
        reader_0 = pydrivedol.GDReader(TEST_FOLDER_URL, max_levels=0)
        files_0 = list(reader_0)

        # All files recursively
        reader_all = pydrivedol.GDReader(TEST_FOLDER_URL, max_levels=None)
        files_all = list(reader_all)

        # Should have at least as many files recursively
        assert len(files_all) >= len(files_0)


class TestGDStore:
    """Tests for GDStore class."""

    @skip_if_no_folder_url
    def test_store_write_and_read(self):
        """Test writing and reading a file."""
        store = pydrivedol.GDStore(TEST_FOLDER_URL)

        test_key = 'test_write.txt'
        test_content = b'test content from pydrivedol'

        # Write
        store[test_key] = test_content

        # Read back
        content = store[test_key]
        assert content == test_content

        # Clean up
        del store[test_key]

    @skip_if_no_folder_url
    def test_store_nested_write(self):
        """Test writing to nested folders."""
        store = pydrivedol.GDStore(TEST_FOLDER_URL)

        test_key = 'test_folder/nested_file.txt'
        test_content = b'nested content'

        # Write
        store[test_key] = test_content

        # Read back
        content = store[test_key]
        assert content == test_content

        # Clean up
        del store[test_key]

    @skip_if_no_folder_url
    def test_store_delete(self):
        """Test deleting a file."""
        store = pydrivedol.GDStore(TEST_FOLDER_URL)

        test_key = 'test_delete.txt'
        test_content = b'will be deleted'

        # Write
        store[test_key] = test_content
        assert test_key in store

        # Delete
        del store[test_key]

        # Verify deleted
        assert test_key not in store

    @skip_if_no_folder_url
    def test_store_update_existing(self):
        """Test updating an existing file."""
        store = pydrivedol.GDStore(TEST_FOLDER_URL)

        test_key = 'test_update.txt'
        content_v1 = b'version 1'
        content_v2 = b'version 2'

        try:
            # Write v1
            store[test_key] = content_v1
            assert store[test_key] == content_v1

            # Update to v2
            store[test_key] = content_v2
            assert store[test_key] == content_v2
        finally:
            # Clean up
            if test_key in store:
                del store[test_key]


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_extract_file_id(self):
        """Test _extract_file_id function."""
        urls = [
            ('https://drive.google.com/file/d/ABC123/view', 'ABC123'),
            ('https://drive.google.com/open?id=XYZ789', 'XYZ789'),
            ('https://drive.google.com/uc?id=DEF456&export=download', 'DEF456'),
        ]
        for url, expected_id in urls:
            file_id = pydrivedol._extract_file_id(url)
            assert file_id == expected_id, f"Failed for URL: {url}"

    def test_extract_folder_id(self):
        """Test _extract_folder_id function."""
        urls = [
            ('https://drive.google.com/drive/folders/ABC123', 'ABC123'),
            ('https://drive.google.com/drive/u/0/folders/XYZ789', 'XYZ789'),
        ]
        for url, expected_id in urls:
            folder_id = pydrivedol._extract_folder_id(url)
            assert folder_id == expected_id, f"Failed for URL: {url}"


def print_test_config_status():
    """Print status of test configuration."""
    print("\n" + "=" * 70)
    print("PyDriveDol Test Configuration Status")
    print("=" * 70)

    if TEST_PUBLIC_FILE_URL:
        print(f"✓ PYDRIVEDOL_TEST_PUBLIC_FILE_URL: {TEST_PUBLIC_FILE_URL[:50]}...")
    else:
        print("✗ PYDRIVEDOL_TEST_PUBLIC_FILE_URL: Not set")
        print("  Set with: export PYDRIVEDOL_TEST_PUBLIC_FILE_URL='https://...'")

    if TEST_FOLDER_URL:
        print(f"✓ PYDRIVEDOL_TEST_FOLDER_URL: {TEST_FOLDER_URL[:50]}...")
    else:
        print("✗ PYDRIVEDOL_TEST_FOLDER_URL: Not set")
        print("  Set with: export PYDRIVEDOL_TEST_FOLDER_URL='https://...'")

    print("\nTests that will run:")
    if TEST_PUBLIC_FILE_URL:
        print("  ✓ TestGetBytes (4 tests)")
    else:
        print("  ✗ TestGetBytes (4 tests) - SKIPPED")

    if TEST_FOLDER_URL:
        print("  ✓ TestGDReader (6 tests)")
        print("  ✓ TestGDStore (4 tests)")
    else:
        print("  ✗ TestGDReader (6 tests) - SKIPPED")
        print("  ✗ TestGDStore (4 tests) - SKIPPED")

    print("  ✓ TestHelperFunctions (2 tests) - Always run")

    print("\nFor full setup instructions, see:")
    print("  https://github.com/i2mint/pydrivedol#testing")
    print("=" * 70 + "\n")


if __name__ == '__main__':
    # Print configuration status
    print_test_config_status()

    # Run tests with pytest if available, otherwise with unittest
    try:
        import pytest

        pytest.main([__file__, '-v'])
    except ImportError:
        import unittest

        unittest.main()
