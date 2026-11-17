"""Exercise the real origin/bootstrap boundary for application API tests."""
from fastapi.testclient import TestClient


class LocalClient(TestClient):
    def __init__(self, app, **kwargs):
        kwargs.setdefault('base_url', 'http://127.0.0.1:8731')
        kwargs.setdefault('client', ('127.0.0.1', 50000))
        super().__init__(app, **kwargs)
        self.headers['Origin'] = 'http://localhost:3000'
        if hasattr(app.state, 'local_session'):
            response = self.post('/api/local-session', headers={'X-Panel-Bootstrap': '1'})
            assert response.status_code == 200, response.text
            self.headers['X-Panel-Session'] = response.json()['token']
