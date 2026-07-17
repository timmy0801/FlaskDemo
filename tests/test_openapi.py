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
