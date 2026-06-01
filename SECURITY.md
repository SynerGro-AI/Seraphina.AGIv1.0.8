# Security Policy

## Supported versions

The latest minor release of `seraphina-agi` on PyPI receives security
fixes. Older versions are best-effort only.

| Version | Supported |
|---|---|
| 1.0.x (latest) | ✅ |
| < 1.0.0 | ❌ |

## Reporting a vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Email: **security@synergroaicorp.com**
(or, if email is bouncing, open a [private security advisory](https://github.com/SynerGro-AI/Seraphina.AGIv1.0.8/security/advisories/new))

Please include:

- A clear description of the vulnerability and its impact
- Steps to reproduce (proof-of-concept welcomed)
- Affected version(s) and platform(s)
- Whether you've disclosed this elsewhere

We aim to acknowledge reports within **3 business days** and ship a fix
or mitigation within **30 days** for high-severity issues. We will credit
you in the release notes unless you ask us not to.

## Scope

In scope:

- The `seraphina-agi` PyPI package (the deterministic engine, RWAST,
  Glyph CLI bundled in the wheel)
- The Glyph install pipeline (`glyph install`, manifest verification,
  SHA256 gates)
- Anything that executes code on a user's machine after `pip install
  seraphina-agi`

Out of scope:

- Vulnerabilities in third-party services (xAI Grok API, PyPI itself,
  GitHub Actions runners) — report those upstream
- Issues that require the user to disable our existing safety gates
  (e.g. setting `SERAPHINA_GROK_API_KEY` and then complaining about
  egress)
- DoS via uncapped local resource consumption (we're stdlib-only; users
  control their own machines)

## Verifying releases

Every PyPI artifact is built by GitHub Actions via [PyPI Trusted
Publisher (OIDC)](.github/workflows/publish.yml) — no human-held tokens.
See the **Verify this is real** section of [README.md](README.md) for
the full integrity-check ladder.
