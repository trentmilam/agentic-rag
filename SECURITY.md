# Security Policy

## Supported versions

This is an early-stage portfolio project. Security fixes are applied to the
latest release on the default branch only.

| Version | Supported |
|---|---|
| 0.1.x (latest) | ✅ |
| < 0.1.0 | ❌ |

## Reporting a vulnerability

Please report suspected vulnerabilities privately rather than opening a public
issue. Use GitHub's **[Report a vulnerability](https://github.com/trentmilam/agentic-rag/security/advisories/new)**
(Security → Advisories) form, or email **298508156+trentmilam@users.noreply.github.com**.

Include enough detail to reproduce (affected file/endpoint, inputs, and observed
vs. expected behavior). You can expect an initial acknowledgment within a few
days; please allow reasonable time for a fix before any public disclosure.

## Scope notes

- This project runs entirely locally: it fetches a public corpus over HTTPS at
  build time and serves queries with no LLM and no network at query time. It has
  no authentication surface, no secrets, and no server listening on a network port
  (the MCP server speaks over stdio to a local client).
- The corpus is fetched from `rfc-editor.org` and `iana.org`; this project
  redistributes none of it.
