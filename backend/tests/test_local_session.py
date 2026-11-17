"""Hostile browser inputs, rotation, expiry and the private desktop handoff."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.main import create_app
from app.security.local_session import LocalSession, DEV_ORIGINS, DESKTOP_ORIGINS


def client_for(session, peer='127.0.0.1', host='127.0.0.1:8731'):
    app = create_app(local_session=session)
    @app.post('/mutation')
    def mutation():
        return {'saved': True}
    return TestClient(app, base_url='http://'+host, client=(peer, 30000))


def bootstrap(client, origin='http://localhost:3000', **headers):
    return client.post('/api/local-session', headers={'Origin': origin,
        'X-Panel-Bootstrap': '1', **headers})


@pytest.mark.parametrize('method', ['POST', 'PUT', 'PATCH', 'DELETE'])
def test_missing_session_is_rejected_before_service_or_body_parsing(method):
    client = client_for(LocalSession(mode='development'))
    response = client.request(method, '/api/projects', content='not-json',
        headers={'Origin': 'http://localhost:3000'})
    assert response.status_code == 401
    assert response.json()['error']['code'] == 'LOCAL_SESSION_REQUIRED'


@pytest.mark.parametrize('origin', ['null', 'https://evil.example', 'http://localhost:3000.evil',
    'http://localhost:3001', 'http://user@localhost:3000', 'http://localhost:3000/',
    'http://localhost:3000 https://evil.example', 'http://LOCALHOST:3000'])
def test_hostile_origin_cannot_bootstrap_read_or_mutate_even_with_token(origin):
    client = client_for(LocalSession(mode='development'))
    token = bootstrap(client).json()['token']
    assert bootstrap(client, origin).status_code == 403
    for method, path in [('GET', '/health'), ('POST', '/mutation')]:
        response = client.request(method, path, headers={'Origin': origin, 'X-Panel-Session': token})
        assert response.status_code == 403 and token not in response.text
    preflight = client.options('/mutation', headers={'Origin': origin, 'Access-Control-Request-Method': 'POST'})
    assert preflight.status_code == 400 and 'access-control-allow-origin' not in preflight.headers


def test_authorized_development_session_rotation_and_expiry():
    now = [0]
    client = client_for(LocalSession(mode='development', ttl_seconds=60, clock=lambda: now[0]))
    assert client.post('/api/local-session').status_code == 401
    assert bootstrap(client, **{'X-Panel-Launch': 'a'*64}).status_code == 401
    response = bootstrap(client)
    assert response.headers['cache-control'] == 'no-store'
    token = response.json()['token']
    headers = {'Origin': 'http://localhost:3000', 'X-Panel-Session': token}
    assert client.post('/mutation', headers=headers).status_code == 200
    # Explicit local CLI credentials also work; no cookie ambient authority.
    assert client.post('/mutation', headers={'X-Panel-Session': token}).status_code == 200
    assert not client.cookies
    rotated = client.post('/api/local-session/rotate', headers=headers)
    assert rotated.status_code == 200 and rotated.json()['token'] != token
    assert client.post('/mutation', headers=headers).status_code == 401
    fresh = rotated.json()['token']
    assert client.post('/mutation', headers={'X-Panel-Session': fresh}).status_code == 200
    now[0] = 61
    assert client.post('/mutation', headers={'X-Panel-Session': fresh}).status_code == 401
    assert bootstrap(client).json()['token'] != fresh
    # A new backend never accepts the previous process credential.
    restarted = client_for(LocalSession(mode='development'))
    assert restarted.post('/mutation', headers={'X-Panel-Session': fresh}).status_code == 401


@pytest.mark.parametrize('origin', sorted(DESKTOP_ORIGINS))
def test_desktop_requires_private_launch_handoff(origin):
    launch = 'a'*64
    session = LocalSession(launch_secret=launch)
    client = client_for(session)
    assert bootstrap(client, origin).status_code == 401
    assert bootstrap(client, origin, **{'X-Panel-Launch': 'b'*64}).status_code == 401
    response = bootstrap(client, origin, **{'X-Panel-Launch': launch})
    assert response.status_code == 200
    token = response.json()['token']
    assert token != launch and launch not in repr(session)
    assert client.post('/mutation', headers={'Origin': origin, 'X-Panel-Session': token}).status_code == 200
    assert client.post('/mutation', headers={'Origin': origin, 'X-Panel-Session': launch}).status_code == 401
    for dev in DEV_ORIGINS:
        assert bootstrap(client, dev, **{'X-Panel-Launch': launch}).status_code == 403
    rotated = client.post('/api/local-session/rotate', headers={'Origin': origin, 'X-Panel-Session': token}).json()['token']
    assert bootstrap(client, origin, **{'X-Panel-Launch': launch}).json()['token'] == rotated


@pytest.mark.parametrize('peer,host', [('192.0.2.1', '127.0.0.1:8731'), ('127.0.0.1', 'attacker.example:8731')])
def test_remote_peer_and_dns_rebinding_fail_closed(peer, host):
    client = client_for(LocalSession(mode='development'), peer, host)
    assert bootstrap(client).status_code == 403
    assert client.get('/api/projects').status_code == 403


def test_duplicate_forwarded_and_malformed_auth_headers_are_rejected():
    client = client_for(LocalSession(mode='development'))
    token = bootstrap(client).json()['token']
    assert client.post('/mutation', headers=[('X-Panel-Session', token), ('X-Panel-Session', token)]).status_code == 403
    assert client.get('/health', headers={'X-Forwarded-Host': 'evil'}).status_code == 403
    assert client.post('/mutation', headers={'X-Panel-Session': 'x'*10000}).status_code == 401
    assert client.post('/mutation', headers=[(b'X-Panel-Session', b'\xe9'*64)]).status_code == 401


def test_launch_secret_consumed_and_invalid_or_hosted_settings_fail(monkeypatch):
    monkeypatch.setenv('PANEL_LOCAL_LAUNCH_SECRET', 'a'*64)
    assert LocalSession.load()
    assert 'PANEL_LOCAL_LAUNCH_SECRET' not in __import__('os').environ
    monkeypatch.setenv('PANEL_LOCAL_MODE', 'hosted')
    with pytest.raises(ValueError, match='hidden'):
        LocalSession.load()


def test_concurrent_rotation_accepts_old_credential_exactly_once():
    session = LocalSession(mode='development')
    old = session.bootstrap('http://localhost:3000', '1', None)
    with ThreadPoolExecutor(max_workers=8) as pool:
        replacements = [value for value in pool.map(session.rotate, [old]*8) if value]
    assert len(replacements) == 1
    assert not session.authorized(old) and session.authorized(replacements[0])


def test_desktop_configuration_contains_no_renderer_shell_permission_or_static_secret():
    root = Path(__file__).resolve().parents[2]
    capability = json.loads((root/'frontend/src-tauri/capabilities/default.json').read_text())
    assert capability['windows'] == ['main']
    assert capability['permissions'] == ['core:default', 'allow-local-session']
    source = (root/'frontend/src-tauri/src/lib.rs').read_text()
    assert '.env("PANEL_LOCAL_LAUNCH_SECRET", &credential)' in source
    assert 'getrandom::fill' in source and 'trusted_window(window.label()' in source
    assert 'host="127.0.0.1"' in (root/'backend/desktop_main.py').read_text()
