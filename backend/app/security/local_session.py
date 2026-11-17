"""One OS user, one local backend, all projects owned by that user.

This is a local browser/CSRF boundary, not hosted identity or isolation from
processes running as the same OS account. No forwarded-host/proxy deployment.
"""
import hmac
import ipaddress
import os
import re
import secrets
from threading import RLock
import time

from fastapi.responses import JSONResponse

DEV_ORIGINS = frozenset({'http://localhost:3000', 'http://127.0.0.1:3000'})
DESKTOP_ORIGINS = frozenset({'tauri://localhost', 'http://tauri.localhost', 'https://tauri.localhost'})
HEADER = 'X-Panel-Session'


class LocalSession:
    def __init__(self, *, mode='desktop', launch_secret=None, ttl_seconds=8*3600, clock=time.monotonic):
        if mode not in {'desktop', 'development'} or not 60 <= ttl_seconds <= 86400:
            raise ValueError('Invalid local session configuration; hosted deployment is blocked.')
        if launch_secret is not None and not re.fullmatch(r'[0-9a-f]{64}', launch_secret):
            raise ValueError('Invalid local launch credential.')
        self.mode = mode
        self.origins = DESKTOP_ORIGINS if mode == 'desktop' else DEV_ORIGINS | DESKTOP_ORIGINS
        self._launch_secret = launch_secret or secrets.token_hex(32)
        self._token = secrets.token_hex(32)
        self._clock, self._ttl, self._expires = clock, ttl_seconds, clock()+ttl_seconds
        self._lock = RLock()

    @classmethod
    def load(cls):
        # Remove the launch credential before spawning engineering children.
        launch_secret = os.environ.pop('PANEL_LOCAL_LAUNCH_SECRET', None)
        try:
            return cls(mode=os.getenv('PANEL_LOCAL_MODE', 'desktop'), launch_secret=launch_secret,
                       ttl_seconds=int(os.getenv('PANEL_LOCAL_SESSION_SECONDS', '28800')))
        except ValueError:
            raise ValueError('Invalid local session configuration; details are hidden.') from None

    def __repr__(self):
        return '<LocalSession credentials=hidden>'

    def bootstrap(self, origin, marker, launch):
        if marker != '1' or origin not in self.origins:
            return None
        # A release desktop must pair with its own sidecar, even when a dev
        # backend already occupies the fixed local port. Never downgrade it.
        if self.mode == 'development' and launch is not None:
            return None
        if self.mode == 'desktop' and (not isinstance(launch, str) or
                not re.fullmatch(r'[0-9a-f]{64}', launch) or
                not hmac.compare_digest(launch, self._launch_secret)):
            return None
        with self._lock:
            if self._clock() >= self._expires:
                self._rotate()
            return self._token

    def authorized(self, token):
        with self._lock:
            return (isinstance(token, str) and bool(re.fullmatch(r'[0-9a-f]{64}', token)) and
                    self._clock() < self._expires and hmac.compare_digest(token, self._token))

    def _rotate(self):
        self._token = secrets.token_hex(32)
        self._expires = self._clock()+self._ttl
        return self._token

    def rotate(self, token):
        with self._lock:
            return self._rotate() if self.authorized(token) else None


def rejection(code, status):
    return JSONResponse(status_code=status, content={'error': {'code': code,
        'message': 'Local application authorization failed. Reconnect the application.'}},
        headers={'Cache-Control': 'no-store'})


class LocalBoundary:
    def __init__(self, app, session):
        self.app, self.session = app, session

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'lifespan':
            return await self.app(scope, receive, send)
        if scope['type'] != 'http':
            if scope['type'] == 'websocket':
                await send({'type': 'websocket.close', 'code': 1008})
            return
        pairs = scope.get('headers', [])
        headers = {k.decode('latin1').lower(): v.decode('latin1') for k, v in pairs}
        protected = {b'host', b'origin', b'x-panel-session', b'x-panel-bootstrap', b'x-panel-launch'}
        duplicate = any(sum(k.lower() == key for k, _ in pairs) > 1 for key in protected)
        try:
            local_peer = ipaddress.ip_address(scope['client'][0]).is_loopback
        except (ValueError, TypeError):
            local_peer = False
        host = headers.get('host', '')
        local_host = bool(re.fullmatch(r'(?:127\.0\.0\.1|localhost|\[::1\])(?::[0-9]{1,5})?', host))
        origin = headers.get('origin')
        if (duplicate or not local_peer or not local_host or
                any(k.startswith('forwarded') or k.startswith('x-forwarded-') for k in headers) or
                (origin is not None and origin not in self.session.origins)):
            return await rejection('LOCAL_ORIGIN_REJECTED', 403)(scope, receive, send)
        path, method = scope['path'], scope['method']
        if path == '/api/local-session' and method == 'POST':
            token = self.session.bootstrap(origin, headers.get('x-panel-bootstrap'), headers.get('x-panel-launch'))
            response = (JSONResponse({'token': token}, headers={'Cache-Control': 'no-store'})
                        if token else rejection('LOCAL_SESSION_REQUIRED', 401))
            return await response(scope, receive, send)
        if method not in {'GET', 'HEAD', 'OPTIONS'}:
            token = headers.get('x-panel-session')
            if path == '/api/local-session/rotate' and method == 'POST':
                rotated = self.session.rotate(token)
                response = (JSONResponse({'token': rotated}, headers={'Cache-Control': 'no-store'})
                            if rotated else rejection('LOCAL_SESSION_REQUIRED', 401))
                return await response(scope, receive, send)
            if not self.session.authorized(token):
                return await rejection('LOCAL_SESSION_REQUIRED', 401)(scope, receive, send)
        return await self.app(scope, receive, send)
