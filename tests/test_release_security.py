"""Behavioral regressions for the mobile release's privacy boundary."""
import io
import time
import pytest
from fastapi.testclient import TestClient
from gridfs.errors import NoFile
from PIL import Image
from app.main import app
from app.database import store
from app import config


def account(client):
    return client.post('/api/v1/auth/signup', json={
        'email': f'release-{time.time_ns()}@example.com', 'password': 'password123'
    }).json()


def test_private_endpoints_require_authentication():
    with TestClient(app) as client:
        for path in ('/products', '/scan/x', '/scan/x/image/front', '/product/x',
                     '/compliance-report/x', '/compliance-report/x/summary', '/auth/me'):
            assert client.get('/api/v1' + path).status_code == 401


def test_cross_account_access_is_hidden():
    with TestClient(app) as first, TestClient(app) as second:
        owner = account(first)
        account(second)
        pid = 'private-' + str(time.time_ns())
        sid = 'scan-' + pid
        store.products.insert_one({'product_id': pid, 'user_id': owner['user_id'], 'created_at': '2026'})
        store.scans.insert_one({'scan_id': sid, 'user_id': owner['user_id'], 'status': 'processing'})
        assert first.get('/api/v1/product/' + pid).status_code == 200
        for path in (f'/product/{pid}', f'/scan/{sid}', f'/scan/{sid}/image/front',
                     f'/compliance-report/{pid}', f'/compliance-report/{pid}/summary'):
            assert second.get('/api/v1' + path).status_code == 404
        assert second.get('/api/v1/products').json()['products'] == []
        assert second.post('/api/v1/compare', json={'product_id_a': pid, 'product_id_b': pid}).status_code == 404
        assert second.post('/api/v1/personalize', json={'product_id': pid}).status_code == 404


def test_browser_session_cookie_logout_and_origin():
    with TestClient(app) as client:
        account(client)
        assert client.get('/api/v1/auth/me').status_code == 200
        cookie = next(cookie for cookie in client.cookies.jar if cookie.name == 'll_session')
        assert 'HttpOnly' in cookie._rest
        assert cookie._rest.get('SameSite') == 'strict'
        response = client.post('/api/v1/auth/logout', headers={'Origin': 'https://attacker.example'})
        assert response.status_code == 403
        assert client.get('/api/v1/auth/me').status_code == 200
        assert client.post('/api/v1/auth/logout').status_code == 200
        assert client.get('/api/v1/auth/me').status_code == 401


def test_truncated_image_rejected_before_enqueue():
    with TestClient(app) as client:
        account(client)
        data = b'\x89PNG\r\n\x1a\ninvalid'
        response = client.post('/api/v1/scan', files={
            'front_image': ('front.png', data, 'image/png'),
            'back_image': ('back.png', data, 'image/png')})
        assert response.status_code == 400


def test_production_accepts_durable_job_before_poll(monkeypatch):
    with TestClient(app) as client:
        owner = account(client)
        # Enable production submission after startup; no worker races this assertion.
        monkeypatch.setattr(config, 'PRODUCTION', True)
        buffer = io.BytesIO()
        Image.new('RGB', (20, 20), 'white').save(buffer, 'PNG')
        response = client.post('/api/v1/scan', files={
            'front_image': ('f.png', buffer.getvalue(), 'image/png'),
            'back_image': ('b.png', buffer.getvalue(), 'image/png')})
        assert response.status_code == 202
        sid = response.json()['scan_id']
        document = store.scans.find_one({'scan_id': sid})
        assert document['user_id'] == owner['user_id']
        assert document['job_state'] == 'queued'
        assert store.fs.get(document['images']['front']).read() == buffer.getvalue()
        assert client.get('/api/v1/scan/' + sid).json()['status'] == 'processing'


def test_shell_and_security_headers():
    with TestClient(app) as client:
        response = client.get('/', headers={'Accept': 'text/html'})
        assert response.url.path == '/ui'
        assert 'manifest.webmanifest' in response.text
        assert response.headers['X-Content-Type-Options'] == 'nosniff'
        assert "script-src 'self'" in response.headers['Content-Security-Policy']
        assert client.get('/sw.js').headers['Service-Worker-Allowed'] == '/'
        assert client.get('/static/manifest.webmanifest').json()['display'] == 'standalone'


@pytest.mark.parametrize('payload', [{'email': [], 'password': 'password123'},
                                    {'email': 'x@example.com', 'password': {}},
                                    {'email': 'x@example.com', 'password': 'x' * 129}])
def test_auth_malformed_types_are_client_errors(payload):
    with TestClient(app) as client:
        assert client.post('/api/v1/auth/signup', json=payload).status_code == 400


def test_replaying_job_does_not_duplicate_products(monkeypatch):
    from app.api import routes
    monkeypatch.setattr(routes, 'run_ocr_with_retries', lambda _: {'text': '', 'confidence': None})
    sid = 'replay-' + str(time.time_ns())
    from app.models.scan_model import create_scan_document
    fid = store.fs.put(b'photo')
    store.scans.insert_one(create_scan_document(sid, 'replay-owner', {'front': fid, 'back': fid}))
    routes._process_scan(sid)
    routes._process_scan(sid)
    assert len(list(store.products.find({'scan_id': sid}))) == 1
    assert store.scans.find_one({'scan_id': sid})['status'] == 'done'


def test_logout_revokes_copied_token():
    with TestClient(app) as client:
        credentials = account(client)
        token = credentials['token']
        assert client.post('/api/v1/auth/logout').status_code == 200
        assert client.get('/api/v1/auth/me', headers={'Authorization': 'Bearer ' + token}).status_code == 401


def test_delete_requires_password_and_erases_owned_data():
    with TestClient(app) as client:
        owner = account(client)
        sid = 'delete-' + str(time.time_ns())
        fid = store.fs.put(b'private photo')
        store.scans.insert_one({'scan_id': sid, 'user_id': owner['user_id'], 'status': 'done', 'images': {'front': fid}})
        store.products.insert_one({'product_id': sid, 'user_id': owner['user_id']})
        assert client.get('/api/v1/account/export').json()['products'][0]['product_id'] == sid
        assert client.request('DELETE', '/api/v1/account', json={'password': 'wrong'}).status_code == 401
        assert client.request('DELETE', '/api/v1/account', json={'password': 'password123'}).status_code == 200
        assert store.users.find_one({'user_id': owner['user_id']}) is None
        assert store.products.find_one({'product_id': sid}) is None
        assert store.scans.find_one({'scan_id': sid}) is None
        with pytest.raises(NoFile):
            store.fs.get(fid)


def test_delete_survives_already_missing_image():
    """Account deletion must be idempotent: an image id already gone from
    storage (GridFS NoFile) must not abort cleanup and strand the account."""
    with TestClient(app) as client:
        owner = account(client)
        sid = 'delete-orphan-' + str(time.time_ns())
        store.scans.insert_one({
            'scan_id': sid, 'user_id': owner['user_id'], 'status': 'done',
            'images': {'front': 999999},  # id that was never stored
        })
        response = client.request('DELETE', '/api/v1/account', json={'password': 'password123'})
        assert response.status_code == 200
        assert store.scans.find_one({'scan_id': sid}) is None
        assert store.users.find_one({'user_id': owner['user_id']}) is None
