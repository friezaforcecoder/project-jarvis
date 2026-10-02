from __future__ import annotations

from fastapi.testclient import TestClient


def test_root_serves_operator_hud_with_security_headers(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    policy = response.headers["content-security-policy"]
    assert "default-src 'none'" in policy
    assert "script-src 'self'" in policy
    assert "style-src 'self'" in policy
    assert "connect-src 'self'" in policy
    assert "frame-ancestors 'none'" in policy

    html = response.text
    assert "J.A.R.V.I.S." in html
    assert 'id="chat-form"' in html
    assert 'id="transcript"' in html
    assert 'src="/assets/hud.js?v=0.11.0"' in html
    assert 'href="/assets/hud.css?v=0.11.0"' in html
    assert "http://" not in html
    assert "https://" not in html


def test_hud_assets_are_packaged_and_local_only(client: TestClient) -> None:
    styles = client.get("/assets/hud.css")
    script = client.get("/assets/hud.js")

    assert styles.status_code == 200
    assert styles.headers["content-type"].startswith("text/css")
    assert styles.headers["cache-control"] == "no-store"
    assert "--cyan" in styles.text
    assert "@media (max-width: 820px)" in styles.text
    assert "@media (max-width: 700px)" in styles.text
    assert "http://" not in styles.text
    assert "https://" not in styles.text

    assert script.status_code == 200
    assert "javascript" in script.headers["content-type"]
    assert script.headers["cache-control"] == "no-store"
    assert 'fetch("/v1/chat"' in script.text
    assert "textContent" in script.text
    assert "innerHTML" not in script.text
    assert "http://" not in script.text
    assert "https://" not in script.text
    assert "localStorage.setItem(SESSION_STORAGE_KEY, sessionId)" in script.text
    assert "localStorage.setItem(SESSION_STORAGE_KEY, message" not in script.text


def test_hud_assets_are_not_added_to_openapi(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    assert "/" not in schema["paths"]
    assert "/assets/hud.css" not in schema["paths"]
    assert "/assets/hud.js" not in schema["paths"]
    assert "/v1/conversations/{session_id}/messages" in schema["paths"]
