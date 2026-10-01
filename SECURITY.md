# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 0.1.x (latest) | Yes |
| < 0.1.0 | No |

Fixes go to the latest release on the default branch.

## Reporting a vulnerability

Report privately. Use GitHub's [Report a vulnerability](https://github.com/trentmilam/agentic-rag/security/advisories/new) form, or email **298508156+trentmilam@users.noreply.github.com**.

Include affected file or endpoint, inputs, and observed vs. expected behavior. Acknowledgment within a few days.
Allow reasonable time for a fix before public disclosure.

## Scope

- Runs locally; fetches a public corpus over HTTPS at build time
- No LLM and no network at query time
- No authentication surface, no secrets, no network port (MCP server uses stdio)
- Corpus comes from `rfc-editor.org` and `iana.org`; none of it is redistributed
