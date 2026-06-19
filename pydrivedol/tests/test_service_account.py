"""Tests for service-account (headless) auth support.

Mockable — no live Drive. Verifies ``drive_from_service_account`` builds the pydrive2
service-account settings, and that ``GDReader``/``GDStore`` use an injected ``drive=``
client instead of the interactive OAuth flow.
"""

import pydrivedol.base as base
from pydrivedol import drive_from_service_account, GDReader


def test_drive_from_service_account_builds_service_settings(monkeypatch):
    captured = {}

    class FakeAuth:
        def __init__(self, settings=None):
            captured["settings"] = settings

        def ServiceAuth(self):
            captured["service_auth"] = True

    monkeypatch.setattr(base, "_PYDRIVE2_AVAILABLE", True)
    monkeypatch.setattr(base, "GoogleAuth", FakeAuth)
    monkeypatch.setattr(base, "GoogleDrive", lambda auth: ("DRIVE", auth))

    drive = drive_from_service_account("/key.json", scopes=("scope-a",), subject="u@x.com")

    s = captured["settings"]
    assert s["client_config_backend"] == "service"
    assert s["service_config"]["client_json_file_path"] == "/key.json"
    assert s["service_config"]["client_user_email"] == "u@x.com"  # impersonation when subject given
    assert s["oauth_scope"] == ["scope-a"]
    assert captured["service_auth"] is True
    assert drive[0] == "DRIVE"


def test_drive_from_service_account_no_subject_omits_impersonation(monkeypatch):
    captured = {}

    class FakeAuth:
        def __init__(self, settings=None):
            captured["settings"] = settings

        def ServiceAuth(self):
            pass

    monkeypatch.setattr(base, "_PYDRIVE2_AVAILABLE", True)
    monkeypatch.setattr(base, "GoogleAuth", FakeAuth)
    monkeypatch.setattr(base, "GoogleDrive", lambda auth: "DRIVE")
    drive_from_service_account("/key.json")
    assert "client_user_email" not in captured["settings"]["service_config"]


def test_gdreader_uses_injected_drive(monkeypatch):
    monkeypatch.setattr(base, "_PYDRIVE2_AVAILABLE", True)

    def _no_oauth(*a, **k):
        raise AssertionError("must not run the OAuth flow when drive= is provided")

    monkeypatch.setattr(base, "_init_google_drive", _no_oauth)
    sentinel = object()
    reader = GDReader("https://drive.google.com/drive/folders/ABC123", drive=sentinel)
    assert reader._drive is sentinel
    assert reader.folder_id == "ABC123"
