# Section JetBrains plugin — changelog

All notable changes to this plugin are documented in this file. The
format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.0.0] - 2026-05-28

### Added
- Initial release of the Section JetBrains plugin.
- "Scan Selection" action and editor popup entry.
- "Tokenise Selection" action — replaces a selection with the gateway's
  sanitised text in a single undoable edit.
- `LocalInspectionTool` that surfaces gateway findings as IDE warnings
  with a "Tokenise" quick-fix, throttled by content-hash cache and
  chunked at 256 kB UTF-8 boundaries.
- Section tool window on the right edge: gateway / sign-in / proxy
  status plus the last decisions and a one-click "Toggle Proxy" button.
- "Sign In" action implementing RFC 8628 OAuth device-code flow.
  Access / refresh tokens stored in the IDE PasswordSafe.
- "Toggle Edge Proxy" action that spawns `section-edge-proxy` as a
  managed child process and kills it cleanly on IDE shutdown.
- Settings panel under **Tools → Section** with API key, OIDC sign-in,
  inspection debounce, proxy autostart, and a "Test connection" button.
- Plain-JUnit test suite covering the gateway client, DTO schema, and
  proxy command construction.
