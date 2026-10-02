# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |

## Reporting a vulnerability

Please report security issues privately.

1. Open a GitHub Security Advisory on this repository, **or**
2. Contact the maintainers via the address listed in the repository profile or release notes (if provided).

Include:

- A clear description of the issue
- Steps to reproduce
- Affected version / commit
- Impact assessment (what an attacker can achieve)

Do **not** open a public issue for vulnerabilities that could lead to remote code execution, arbitrary file read/write, or data exposure beyond the local machine’s intended dataset scope.

You should receive an acknowledgement within a reasonable time. We will coordinate a fix and public disclosure.

## Scope and threat model

ImageAudit is designed as a **local-first** tool:

- The default bind address is loopback (`127.0.0.1`).
- There is **no authentication**. Do not expose the API or UI on a public interface without adding your own auth and hardening.
- Dataset paths and uploaded zip archives are treated as untrusted input.
- The application does not intentionally contact external services.

Security-sensitive areas of the code:

- `backend/imageaudit/core/security.py` — path containment, zip extraction limits
- `backend/imageaudit/api/service.py` — audit id validation, image serving by opaque id, upload cleanup
- `backend/imageaudit/api/app.py` — CORS allow-list, HTML report CSP
- `frontend/lib/api.ts` + `frontend/next.config.mjs` — same-origin packaging for the Windows EXE

## Out of scope (examples)

- Attacks that require an already compromised local machine
- Denial of service by feeding extremely large legitimate datasets (resource limits exist but are not a hard security boundary)
- Issues that only appear when the API is deliberately exposed beyond localhost without authentication
