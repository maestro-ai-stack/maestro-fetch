# Security Policy

## Supported Versions

Only the latest release receives security fixes.

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Email: hello@maestro.onl
Subject: `[maestro-fetch] Security: <brief description>`

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (optional)

We will acknowledge within 48 hours and aim to release a fix within 7 days
for critical issues.

## Scope

In scope: RCE via crafted URLs or adapter inputs, credential leakage,
path traversal in file adapters, SSRF in proxy or extension backends.

Out of scope: Issues in third-party sites accessed via tab-exec adapters,
rate limiting, or features marked experimental.
