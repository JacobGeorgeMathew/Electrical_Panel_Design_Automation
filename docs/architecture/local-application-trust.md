# Approved local application boundary (P3-T12)

The approved [D01 deployment](../decisions/approved-product-scope.md) has one OS
user, one backend process, local PostgreSQL and private application storage. That
user owns every project in the configured database. Session credentials authorize
mutations across that user's projects; they are not accounts, per-project ACLs or
multi-user identities. Existing document/project, job/project and revision/project
ownership checks still reject mismatched references. Do not share this database
or backend among mutually untrusted users. Hosted deployment, proxies, tunnels,
remote API bases and network listening remain unsupported pending a separately
approved identity/authorization backlog. No hosted release approval is implied.

The packaged entry binds Uvicorn to `127.0.0.1`. Development must also bind
loopback. The ASGI boundary additionally rejects non-loopback peers, non-loopback
Host values, duplicate authorization/origin headers and forwarded headers. There
is no proxy-trust mode. Known Tauri origins are exact (`tauri://localhost`,
`http://tauri.localhost`, `https://tauri.localhost`); `null`, suffix lookalikes,
alternate ports and trailing-slash origins fail. An Origin header on any request
must be allowed. CORS permits only the same explicit origins and request headers;
it does not itself authorize a mutation. WebSocket connections fail closed.

Every method other than GET/HEAD/OPTIONS requires `X-Panel-Session`, including
preview, validation, job submission and cancellation. Originless native/CLI
mutations also require that credential. Health/readiness and ordinary local reads
do not require it; hostile-origin reads still fail. Local processes running as
the same OS account are trusted. This is not protection from a compromised OS
account, browser profile, renderer/XSS, administrator or malicious local service.
Keep the database, data directory, development server and shell private.

## Desktop handoff

Release Tauri generates 32 random bytes with the OS random source on every launch.
It retains the launch secret in Rust memory and passes it only through the
sidecar's environment, never command-line arguments, a bundled constant, a URL or
a log. The backend consumes/removes `PANEL_LOCAL_LAUNCH_SECRET` before spawning
engineering children. Tauri forces `PANEL_LOCAL_MODE=desktop`. A narrow
`local_session` IPC command returns the launch secret only to the local `main`
window with an approved URL. The renderer has `allow-local-session` and core UI
permissions; it has no shell permissions. Native code still owns sidecar startup
and shutdown. See the upstream [Tauri command](https://v2.tauri.app/develop/calling-rust/)
and [capability](https://v2.tauri.app/security/capabilities/) contracts.

The central API client exchanges that launch secret at `POST /api/local-session`
with `X-Panel-Bootstrap: 1` and `X-Panel-Launch`. The response is an independent
session token, retained only in JavaScript memory. Desktop bootstrap requires
both the exact origin and launch secret. Starting an unrelated backend without
the matching secret cannot authorize the desktop. Failure retains local edits;
no request is automatically replayed. A development backend rejects a release
launch header, so a port collision cannot silently pair a release window with
the development backend. Sidecar restart requires a new launch.

## Explicit development workflow

From `backend/`, using the existing virtual environment and private PostgreSQL
configuration:

```sh
PANEL_LOCAL_MODE=development .venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8731
```

From `frontend/`, use `npm run dev` or `npm run tauri dev`. Only development mode
adds `http://localhost:3000` and `http://127.0.0.1:3000` to the origin set.
Development bootstrap requires the exact allowed origin and non-simple
`X-Panel-Bootstrap: 1` header. It omits the private desktop launch secret but
retains session authorization on every mutation. A hostile web origin cannot
read the token or satisfy this handshake through browser forms. Do not run a
second untrusted application at the approved development origin. No static token
belongs in `.env`, VITE variables, localStorage or source control. API bases must
remain loopback, or relative `/api` through the local Vite proxy. Restart after
changing deployment mode.

CLI tools must explicitly bootstrap using the same development origin/header and
send the returned token in `X-Panel-Session`. Do not put it in shell history or
URLs. Interactive API docs are for contract inspection; their backend origin is
not an allowed mutation origin. Use the frontend or an explicitly authorized CLI
for mutations. The private browser harness allocates an ephemeral frontend
origin and injects that exact value into its own `LocalSession`; production
configuration has no arbitrary-origin override or test bypass.

## Rotation and lifetime

Session lifetime defaults to eight hours. `PANEL_LOCAL_SESSION_SECONDS` accepts
60–86400 seconds and invalid settings stop startup. An authorized
`POST /api/local-session/rotate` atomically invalidates the old session credential
and returns a fresh one. Expiry or process restart invalidates earlier tokens.
The launch secret can retrieve the current desktop token after rotation; it
cannot authorize ordinary mutations. Bootstrap and rotation responses use
`Cache-Control: no-store`. Requests use no cookies and reject redirects, keeping
authorization away from redirected hosts. The client refuses non-loopback API
bases before sending credentials.

The exported frontend `rotateLocalSession` updates the in-memory token. A rejected
credential is forgotten, with a generic error and no reflected response body;
the next explicit action can bootstrap again. Mutations are never automatically
retried. Rotation does not roll back already-authorized in-flight requests or
cancel durable jobs. Concurrent tabs share one local session; rotation invalidates
their old credentials until they bootstrap again. Nothing here alters document
version checks, immutable publication, recovery or engineering constraints.

Release packaging, clean installation, upgrade and interactive WebGL/Tauri smoke
checks require actual supported-platform review. Automated Rust, API, browser and
frontend tests are evidence of their respective contracts, not installer or
engineering certification. [Diagnostics](local-diagnostics.md) describe redaction
and bounded log retention separately.
