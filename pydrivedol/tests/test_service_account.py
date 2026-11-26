"""Tests for service-account (headless) auth support.

Mockable — no live Drive. Verifies ``drive_from_service_account`` builds the pydrive2
service-account settings, and that ``GDReader``/``GDStore`` use an injected ``drive=``
client instead of the interactive OAuth flow.
"""

import json

import pydrivedol.base as base
from pydrivedol import drive_from_service_account, GDReader


def _throwaway_key_file(tmp_path):
    """A service-account key file with a freshly generated RSA key (never a real one)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    path = tmp_path / "sa.json"
    path.write_text(
        json.dumps(
            {
                "type": "service_account",
                "project_id": "p",
                "private_key_id": "k1",
                "private_key": pem,
                "client_email": "sa@p.iam.gserviceaccount.com",
                "client_id": "1",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        )
    )
    return str(path)


def test_drive_from_service_account_signs_jwt_with_current_crypto(tmp_path):
    """Regression for #17: signing must work with whatever pyOpenSSL is installed.

    Builds the drive from a throwaway key and signs a real JWT assertion, which is the
    step that used to raise ``AttributeError: module 'OpenSSL.crypto' has no attribute 'sign'``.
    """
    drive = drive_from_service_account(
        _throwaway_key_file(tmp_path), scopes=("scope-a",), subject="u@x.com"
    )
    creds = drive.auth.credentials._credentials
    assert creds.service_account_email == "sa@p.iam.gserviceaccount.com"
    assert list(creds.scopes) == ["scope-a"]
    assert creds._subject == "u@x.com"
    assert drive.auth.credentials.access_token_expired is False
    assertion = creds._make_authorization_grant_assertion()  # signs with the RSA key
    assert assertion.count(b".") == 2


def test_authorized_http_refreshes_via_google_auth(tmp_path, monkeypatch):
    """The adapter really authorizes requests: token is fetched and sent as Bearer."""
    from google.auth import credentials as _gc

    drive = drive_from_service_account(_throwaway_key_file(tmp_path))
    creds = drive.auth.credentials._credentials

    def fake_refresh(request):
        creds.token = "tok123"
        creds.expiry = None

    monkeypatch.setattr(creds, "refresh", fake_refresh)
    seen = {}

    class FakeHttp:
        def request(self, uri, method="GET", body=None, headers=None, **kw):
            seen["auth"] = (headers or {}).get("authorization")

            class R(dict):
                status = 200

            return R(), b"{}"

    http = drive.auth.credentials.authorize(FakeHttp())
    http.request("https://www.googleapis.com/drive/v2/about")
    assert seen["auth"] == "Bearer tok123"
    assert isinstance(creds, _gc.Credentials)


def test_gdreader_uses_injected_drive(monkeypatch):
    monkeypatch.setattr(base, "_PYDRIVE2_AVAILABLE", True)

    def _no_oauth(*a, **k):
        raise AssertionError("must not run the OAuth flow when drive= is provided")

    monkeypatch.setattr(base, "_init_google_drive", _no_oauth)
    sentinel = object()
    reader = GDReader("https://drive.google.com/drive/folders/ABC123", drive=sentinel)
    assert reader._drive is sentinel
    assert reader.folder_id == "ABC123"
