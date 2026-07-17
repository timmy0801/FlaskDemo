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


def test_openapi_includes_order_paths(client):
    resp = client.get('/api/openapi.json')
    paths = resp.get_json()['paths']
    assert '/api/orders' in paths
    assert '/api/orders/{order_id}' in paths
    assert '/api/orders/{order_id}/status' in paths


def test_openapi_includes_user_paths(client):
    resp = client.get('/api/openapi.json')
    paths = resp.get_json()['paths']
    assert '/api/users' in paths
    assert '/api/users/{user_id}' in paths


def test_openapi_spec_covers_all_blueprints(client):
    resp = client.get('/api/openapi.json')
    paths = resp.get_json()['paths']
    expected = [
        '/api/auth/register', '/api/auth/login', '/api/auth/me',
        '/api/auth/refresh', '/api/auth/logout',
        '/api/products', '/api/products/{product_id}',
        '/api/products/{product_id}/inventory-logs',
        '/api/orders', '/api/orders/{order_id}', '/api/orders/{order_id}/status',
        '/api/users', '/api/users/{user_id}',
    ]
    for path in expected:
        assert path in paths, f'{path} missing from OpenAPI spec'
