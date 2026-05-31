# Changelog — Section VS Code Extension

All notable changes to the Section VS Code extension are documented
in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.0.0] — 2026-05-28

Initial release. Ships with Section 1.0 (edge coverage).

### Added

- "Section: Scan Selection" — runs `/v1/scan` on the editor
  selection and shows a side-by-side diff with a "Replace" button.
- "Section: Tokenise Selection" — silent companion that replaces
  the selection with the gateway's sanitised text.
- "Section: Toggle Local Proxy" — spawns / stops the
  `section-edge-proxy` child process for IDE-level HTTPS_PROXY
  interception of Copilot CLI, Cursor, Continue, aider, Cline, Zed
  AI, and any other tool that honours the proxy env vars.
- "Section: Sign In" — choice of API key (stored in SecretStorage)
  or OIDC device-code flow (RFC 8628).
- "Section: Open Audit Trail" — opens `/admin/events` in the
  default browser, filtered to the current tenant if known.
- Inline diagnostics for sensitive data in open files, with a
  configurable severity (warning by default) and debounce.
- "Section: Tokenise" code action quick-fix on every diagnostic.
- Activity-bar container with a "Recent Decisions" tree view.
- Status-bar pill showing gateway URL, last decision, and proxy state.

### Security

- API keys and OIDC tokens are stored exclusively in VS Code's
  `SecretStorage`, backed by the OS keychain (Windows Credential
  Manager, macOS Keychain, libsecret on Linux).
- The extension only communicates with the operator-configured
  `section.gateway.url` — no telemetry, no third-party endpoints.
- Every scan + restore call writes an audit row on the gateway,
  tagged `upstream="edge-client"` + `client="vscode"`.
