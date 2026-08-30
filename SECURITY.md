# Security Policy

Communeer manages real member phone numbers and connects to a real
WhatsApp account (via WPPConnect). Please report suspected vulnerabilities
responsibly rather than opening a public issue or PR — anything that
touches session/auth handling, the WhatsApp provider integration, or the
inbound webhook could expose that data.

## Supported Versions

This is an early-stage, single-maintainer project. There is no
version-support matrix yet — only the latest tagged release and the
`main` branch are maintained. Please make sure you're on the latest
release before reporting an issue.

## Reporting a Vulnerability

Please use GitHub's private vulnerability reporting for this repository:

<https://github.com/Friedjof/communeer/security/advisories/new>

This opens a private advisory visible only to the maintainer, so details
(and any proof-of-concept) aren't exposed publicly before a fix is
available. Please include:

- A description of the vulnerability and its potential impact.
- Steps to reproduce (or a proof-of-concept), ideally against the mock
  WhatsApp provider rather than a real account.
- The affected version/commit.

There's no formal SLA given the project's size, but reports are taken
seriously and you can expect an initial response within a few days.
Please allow time to investigate and release a fix before any public
disclosure.
