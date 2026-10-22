import time

import pytest
from fastapi.testclient import TestClient
from itsdangerous import URLSafeSerializer

from app import auth, main, sso


@pytest.mark.parametrize('method,path,body', [
    ('GET', '/api/current-run', None), ('GET', '/api/scenarios', None),
    ('GET', '/api/runs', None), ('GET', '/api/runs/missing', None),
    ('POST', '/api/runs', {'scenarios': ['00_web_login']}),
    ('GET', '/api/schedule', None),
    ('POST', '/api/schedule', {'enabled': True}),
    ('GET', '/output/private.png', None),
])
def test_anonymous_requests_cannot_read_or_trigger_runs(method, path, body):
    client = TestClient(main.app)
    assert client.request(method, path, json=body).status_code == 401


def test_manual_login_allows_api_and_logout_revokes_cookie(monkeypatch):
    monkeypatch.setattr(auth, 'VALIDATOR_PASSWORD', 'test-only-password')
    monkeypatch.setattr(main, 'list_scenarios', lambda: ['sample'])
    client = TestClient(main.app, base_url='https://testserver')
    assert client.get('/api/auth/bootstrap').status_code == 200
    assert client.post('/api/auth/login', json={'username': auth.VALIDATOR_USER, 'password': 'wrong'}).status_code == 401
    assert client.post('/api/auth/login', json={'username': auth.VALIDATOR_USER, 'password': 'test-only-password'}).status_code == 200
    assert client.get('/api/scenarios').json() == {'scenarios': ['sample']}
    assert client.post('/api/auth/logout').status_code == 200
    assert client.get('/api/scenarios').status_code == 401


def test_console_sessions_are_accepted_and_invalid_sessions_rejected(monkeypatch):
    monkeypatch.setattr(main, 'list_scenarios', lambda: [])
    client = TestClient(main.app, base_url='https://testserver')
    for expiry in [int(time.time()) + 60, int(time.time()) - 1, 'invalid', None]:
        session = auth.build_session(auth.VALIDATOR_USER, 'console', expiry)
        client.cookies.set(auth.AUTH_COOKIE, auth._serializer().dumps(session))
        assert client.get('/api/scenarios').status_code == (200 if isinstance(expiry, int) and expiry > time.time() else 401)
    client.cookies.set(auth.AUTH_COOKIE, 'tampered-cookie')
    assert client.get('/api/scenarios').status_code == 401


def test_missing_password_never_enables_default_login(monkeypatch):
    monkeypatch.setattr(auth, 'VALIDATOR_PASSWORD', '')
    assert not auth.verify_manual_credentials(auth.VALIDATOR_USER, '')
    assert not auth.verify_manual_credentials(auth.VALIDATOR_USER, 'qa')


def test_signed_console_launch_preserves_distinct_console_username(monkeypatch):
    monkeypatch.setattr(sso, 'QA_CONSOLE_SHARED_SECRET', 'test-shared-secret')
    monkeypatch.setattr(main, 'list_scenarios', lambda: [])
    client = TestClient(main.app, base_url='https://testserver')
    payload = {'source': 'qa-console', 'user': 'console-admin', 'target': 'validator', 'exp': int(time.time()) + 60}
    token = URLSafeSerializer('test-shared-secret', salt=sso.SSO_SALT).dumps(payload)
    response = client.get('/sso/launch', params={'qa_console_token': token}, headers={'referer': sso.QA_CONSOLE_ALLOWED_ORIGIN + '/'})
    assert response.status_code == 200
    assert client.get('/api/scenarios').status_code == 200
    assert client.get('/api/auth/bootstrap').json()['session']['user'] == 'console-admin'
    client.cookies.clear()
    assert client.get('/sso/launch', params={'qa_console_token': 'tampered'}).status_code == 401
    assert client.get('/api/scenarios').status_code == 401
