def test_cors_allows_configured_origin(client):
    resp = client.get("/api/products", headers={"Origin": "http://localhost:3000"})
    assert resp.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"


def test_cors_preflight_returns_200(client):
    resp = client.options(
        "/api/products",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 200
    assert "Access-Control-Allow-Origin" in resp.headers


def test_cors_rejects_unknown_origin(client):
    resp = client.get("/api/products", headers={"Origin": "http://evil.com"})
    assert "Access-Control-Allow-Origin" not in resp.headers
