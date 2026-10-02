# Security Policy

## Supported Versions

Security fixes are currently provided for the latest stable release.

| Version   | Supported |
| --------- | --------- |
| `1.0.x`   | Yes       |
| `< 1.0.0` | No        |

For the latest release, see the repository's Releases page.

---

## Reporting a Vulnerability

Please report suspected security vulnerabilities **privately**.

### Preferred method

Open a **GitHub Security Advisory** for this repository.

If GitHub Security Advisories are unavailable, use a private contact method provided by the repository maintainers or the release notes.

Please do **not** disclose security-sensitive details in a public GitHub issue before the vulnerability has been assessed and, where appropriate, fixed.

### What to include

A useful report should include:

* A clear description of the vulnerability
* The affected component or file
* Steps to reproduce the issue
* A minimal proof of concept, when safe to provide
* Affected version, commit, or build
* Expected behavior
* Observed behavior
* Security impact and what an attacker could potentially achieve
* Any relevant logs, stack traces, or configuration details

Please avoid including real private datasets, credentials, API keys, personal information, or other sensitive data in a report.

### Examples of security-sensitive issues

Please report issues privately when they could result in:

* Arbitrary file read or write
* Path traversal
* Unsafe archive extraction
* Remote code execution
* Unauthorized access to audit data
* Cross-user data exposure
* Bypass of application security boundaries
* Server-side request forgery or unintended external network access
* Other unintended access to files or resources outside the application's intended scope

We will acknowledge valid reports, investigate the issue, and coordinate remediation and disclosure as appropriate.

---

## Scope and Threat Model

ImageAudit is designed primarily as a **local-first dataset auditing application**.

Its default security model assumes that the application is operated locally by a trusted user.

### Default deployment

* The API binds to `127.0.0.1` by default.
* Authentication is **not included** in v1.0.0.
* The application should not be exposed to an untrusted network without additional authentication and deployment hardening.
* Dataset paths and uploaded archives are treated as untrusted input.
* The application does not intentionally send dataset data or telemetry to external services.

### Security-sensitive areas

The following components contain important security controls:

| Component                             | Responsibility                                                              |
| ------------------------------------- | --------------------------------------------------------------------------- |
| `backend/imageaudit/core/security.py` | Path containment and archive extraction limits                              |
| `backend/imageaudit/api/service.py`   | Audit ID validation, image access by opaque ID, upload handling and cleanup |
| `backend/imageaudit/api/app.py`       | CORS configuration, static serving and HTML report security headers         |
| `frontend/lib/api.ts`                 | API base URL behavior                                                       |
| `frontend/next.config.mjs`            | Static export configuration used by the packaged application                |
| `packaging/`                          | Windows executable packaging and runtime integration                        |

---

## Archive Security

Uploaded ZIP archives are treated as potentially hostile input.

The application applies controls including:

* Absolute-path rejection
* `..` traversal protection
* Symlink rejection
* Encrypted archive rejection
* Member-count limits
* Per-member size limits
* Total extraction-size limits
* Compression-ratio limits
* Extraction inside controlled application storage

These controls are intended to prevent archive-based path traversal and resource-exhaustion attacks.

They are not intended to provide protection against a fully compromised host or every possible parser vulnerability in third-party image/archive libraries.

---

## Local API Security

The default deployment is intentionally local.

There is **no authentication mechanism in v1.0.0**.

If the API is deliberately exposed beyond loopback, the operator is responsible for providing appropriate:

* Authentication
* Authorization
* TLS
* Network access controls
* CORS configuration
* Rate limiting
* Resource limits
* Monitoring and logging

Do not treat the default local deployment configuration as suitable for an internet-facing service.

---

## Out of Scope

The following are generally outside the security scope of this project:

* Attacks requiring an already compromised local machine
* Vulnerabilities that depend entirely on a malicious or compromised operating system environment
* Denial-of-service caused solely by intentionally processing extremely large legitimate datasets
* Resource exhaustion beyond the application's documented operational limits
* Issues that occur only after deliberately exposing the API beyond localhost without adding authentication or deployment controls
* Vulnerabilities in third-party software that cannot be reproduced through ImageAudit's supported usage

Resource limits are defensive controls, but they should not be considered an absolute security boundary.

---

## Responsible Disclosure

Please allow maintainers reasonable time to investigate and address a privately reported vulnerability before making technical details public.

Once a fix is available, disclosure may include:

* The affected versions
* The security impact
* The fixed version
* Relevant mitigation guidance
* Credit to the reporter, if requested

Please do not publicly disclose exploit details while a report is still under active investigation.

---

## Security Updates

Security fixes will be documented through the project's release notes and, where appropriate, GitHub Security Advisories.

Users should keep ImageAudit updated to the latest supported release.
