def test_openapi_json_returns_valid_spec(client):
    resp = client.get('/api/openapi.json')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['openapi'] == '3.0.3'
    assert data['info']['title']


def test_docs_page_returns_html(client):
    resp = client.get('/api/docs/')
    assert resp.status_code == 200
    assert 'text/html' in resp.content_type


def test_openapi_includes_auth_paths(client):
    resp = client.get('/api/openapi.json')
    paths = resp.get_json()['paths']
    assert '/api/auth/register' in paths
    assert '/api/auth/login' in paths
    assert '/api/auth/me' in paths
    assert '/api/auth/refresh' in paths
    assert '/api/auth/logout' in paths


def test_openapi_includes_product_paths(client):
    resp = client.get('/api/openapi.json')
    paths = resp.get_json()['paths']
    assert '/api/products' in paths
    assert '/api/products/{product_id}' in paths
    assert '/api/products/{product_id}/inventory-logs' in paths
