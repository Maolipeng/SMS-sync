# Changelog

All notable changes are documented in this file.

## 0.1.0 — Unreleased

### Added

- Local onboarding UI, double-click macOS launcher, and full CLI, including secure `init`, `doctor`, `pair`, `test`, `install`, `uninstall`, and `reset`.
- Telegram private-chat pairing with a one-time, short-lived deep link.
- Native macOS Keychain access that keeps credentials out of process arguments, loopback-only UI, single-instance lock, retry/backoff, and release hygiene tests.
- Chinese and English README, user guide, security policy, contribution guide, and threat model.
- Configurable strict OTP, smart OTP, and explicit all-message forwarding rules in both UI and CLI.
- Dependency-free decoding of modern macOS Messages `attributedBody` typedstreams when the legacy `text` column is empty.
- Pickup-code recognition for labelled collection messages and compound codes such as `3-7-2468`, with tracking-number suffixes excluded.
- Provider-neutral notification model with Telegram and Discord renderers.
- Optional Discord Incoming Webhook delivery, setup UI, CLI controls, provider-specific tests, and per-provider retry cursors.

### Security

- Notifications default to a detected service name, OTP, and full sender identifier; full source text remains an explicit opt-in.
- Pairing values are stored only as SHA-256 hashes and group/channel pairing is rejected.
- Long previews are bounded before HTML rendering, preventing broken Telegram markup.
- OTP and pickup-code notifications prioritize a bold, unobstructed code line, retain sender and received time, and provide a native clipboard button.
- Strict OTP remains the default; enabling all-message mode requires an explicit privacy warning because ordinary SMS and iMessage text is transmitted.
- Discord credentials are Keychain-only; webhook URLs are restricted to canonical Discord HTTPS endpoints, redirects and mentions are disabled, and URLs never appear in status or errors.
