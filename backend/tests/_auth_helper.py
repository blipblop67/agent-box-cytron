"""
Shared helper so every test file doesn't reimplement "register or log in a
test user and build the Authorization header." Not a test itself.
"""
DEFAULT_PASSWORD = "test-password-123"


def auth_headers(client, name: str, password: str = DEFAULT_PASSWORD) -> dict:
    resp = client.post("/api/auth/authenticate", json={"name": name, "password": password})
    assert resp.status_code == 200, resp.text
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}
