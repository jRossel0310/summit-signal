"""Auth: invite-gated signup, login, token validation."""
import os
import tempfile

os.environ.setdefault("SUMMIT_SIGNAL_DB", os.path.join(tempfile.mkdtemp(), "auth.db"))
os.environ.setdefault("SIGNUP_CODE", "test-invite-code")

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

_cm = TestClient(app)
client = _cm.__enter__()


def teardown_module(_m):
    _cm.__exit__(None, None, None)


def test_signup_requires_invite_code():
    r = client.post("/auth/signup", json={"email": "a@b.com", "password": "password123",
                                          "invite_code": "wrong"})
    assert r.status_code == 400


def test_signup_then_login_and_me():
    r = client.post("/auth/signup", json={"email": "Alice@Example.com", "password": "password123",
                                          "invite_code": os.environ["SIGNUP_CODE"]})
    assert r.status_code == 200
    token = r.json()["token"]
    assert r.json()["user"]["email"] == "alice@example.com"  # normalized

    r2 = client.post("/auth/login", json={"email": "alice@example.com", "password": "password123"})
    assert r2.status_code == 200 and r2.json()["token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["email"] == "alice@example.com"


def test_duplicate_email_rejected():
    body = {"email": "dup@example.com", "password": "password123",
            "invite_code": os.environ["SIGNUP_CODE"]}
    assert client.post("/auth/signup", json=body).status_code == 200
    assert client.post("/auth/signup", json=body).status_code == 409


def test_login_wrong_password():
    client.post("/auth/signup", json={"email": "bob@example.com", "password": "password123",
                                      "invite_code": os.environ["SIGNUP_CODE"]})
    r = client.post("/auth/login", json={"email": "bob@example.com", "password": "nope"})
    assert r.status_code == 401


def test_me_requires_valid_token():
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
