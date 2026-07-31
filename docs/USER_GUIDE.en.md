# SMS Bridge User Guide

This guide is written for first-time notification-channel users. Experienced users can jump to the CLI section.

> SMS Bridge handles authentication codes. Telegram bot chats and Discord channels are not end-to-end encrypted private storage; messages pass through the selected provider's infrastructure. Use the relay only if you accept that boundary.

## 1. Prerequisites

You need:

- a Mac with Python 3.10 or newer;
- a Mac and iPhone signed in to the same Apple Account;
- iPhone messages visible in the Mac Messages app;
- at least one destination: a dedicated Telegram bot, or a Discord Incoming Webhook in a private channel;
- two-step verification on the relevant platform accounts.

Send an ordinary test SMS to the iPhone and confirm that it appears in Messages on the Mac. SMS Bridge cannot bypass Apple sync or access content that has not reached the Mac.

## 2. Create a dedicated Telegram bot

1. Open the official `@BotFather` account in Telegram.
2. Send `/newbot` and follow its prompts.
3. Copy the Bot Token. Never include it in a screenshot, issue, chat, or Git repository.
4. If it has been exposed, use `/revoke` in `@BotFather` immediately.

Do not run another bot framework against the same Bot Token: multiple `getUpdates` consumers can steal updates from one another.

### Optional Discord Webhook

Create or select a private Discord text channel, open Channel Settings → Integrations → Webhooks, create a webhook, and copy its URL into SMS Bridge. Treat the URL as a password. SMS Bridge accepts only canonical `https://discord.com/api/webhooks/...` endpoints, refuses redirects, and disables user, role, and `@everyone` mentions.

## 3. Graphical setup

1. Download and extract the project source.
2. Double-click `SMS Bridge.command`.
3. On first run, the launcher creates an owner-only Python runtime dedicated to SMS Bridge, then opens a loopback-only setup page.
4. Complete at least one destination: save and pair Telegram, or validate and save a Discord Webhook URL.
5. Allow Keychain access only for the Python/SMS Bridge process you launched. Each configured credential may need one approval after a first run or executable-path change; the process caches it in memory.
6. Test each provider separately or test all enabled providers.
7. Verify the sender, code, and simulated-message marker.
8. Install background startup.

The setup page closes after installation so the per-user LaunchAgent can take over. It needs no administrator access and contains no provider credential.

### Which Full Disk Access entry should I choose?

Open System Settings → Privacy & Security → Full Disk Access:

- Prefer the dedicated executable at `~/Library/Application Support/SMS Bridge/runtime/bin/python3.10` (the minor version can differ).
- “Background Python” in the diagnostics dialog shows the exact path.
- Do not grant a general-purpose Python interpreter Full Disk Access: unrelated scripts using it could inherit that access.
- Advanced users who bypass the launcher must choose whether to authorize Terminal/iTerm or their own dedicated interpreter.

Quit the relevant application completely and relaunch SMS Bridge after granting access. macOS does not allow the project to grant this permission silently.

If the dedicated `python3.10` is enabled but a setup page launched from an unauthorized Terminal still reports missing access, do not broaden Terminal access. Finish Token setup and private-chat pairing, then install background startup. The LaunchAgent uses the authorized real `python3.10` path. Reopen the setup page after a few seconds to see the background relay's verified result.

## 4. Notification contents

By default a notification emphasizes the code before the full sender identifier and received time. Telegram uses a bold line and native copy button while avoiding mobile code-block overlays; Discord uses a large Markdown heading. The notification excludes the full message body and attachments.

Enabling “Include original message” sends the source text as a collapsed-by-default, expandable quotation, but SMS Bridge still creates no local OTP history. Long previews are safely bounded without cutting Telegram HTML markup.

Three forwarding rules are available:

- **Strict OTP (default):** requires OTP context such as `code`, `verification`, `OTP`, or `验证码` plus a 4–8 digit sequence. It also recognizes explicitly labelled pickup/collection codes and patterns such as “凭 3-7-2468 到驿站”, preferring that code over a tracking-number suffix.
- **Smart OTP:** additionally accepts short Chinese messages with one numeric sequence at the beginning or end, while excluding common order, balance, payment, phone, meeting, and identifier phrases.
- **All received text:** forwards ordinary SMS and iMessage text. Messages without an OTP are sent with their original text to every enabled provider, so this mode must be enabled deliberately.

False positives and missed messages remain possible; this is not a guaranteed-delivery service.

## 5. CLI

CLI-only setup reads the Token without echoing it or placing it in process arguments:

```zsh
python3 sms_bridge.py init
python3 sms_bridge.py pair
python3 sms_bridge.py test
python3 sms_bridge.py discord set
python3 sms_bridge.py discord test
python3 sms_bridge.py install
```

Other commands:

```zsh
python3 sms_bridge.py status
python3 sms_bridge.py doctor
python3 sms_bridge.py run
python3 sms_bridge.py config --show-original on
python3 sms_bridge.py config --show-original off
python3 sms_bridge.py config --mode strict
python3 sms_bridge.py config --mode smart
python3 sms_bridge.py config --mode all
python3 sms_bridge.py test --provider telegram
python3 sms_bridge.py test --provider discord
python3 sms_bridge.py discord status
python3 sms_bridge.py discord enable
python3 sms_bridge.py discord disable
python3 sms_bridge.py discord remove
python3 sms_bridge.py unpair
python3 sms_bridge.py uninstall
python3 sms_bridge.py reset --yes
```

`uninstall` removes only background startup and retains provider configuration. `reset --yes` permanently removes Telegram and Discord Keychain credentials, pairing, local state, logs, dedicated runtime, LaunchAgent, and fields/state/logs left by old prototypes. It cannot revoke the Telegram token, delete the server-side Discord Webhook, or remove the macOS Full Disk Access record.

## 6. Routine security operations

- Exposed Token: use `/revoke` in `@BotFather`, then rerun `init` or save the replacement in the setup page. Saving a new Token invalidates the old pairing.
- Lost Telegram device: terminate that Telegram session, revoke the Bot Token, and pair again.
- Exposed Discord Webhook: delete or regenerate it in Discord, then save the replacement locally.
- Mac transfer or service: revoke the Token in `@BotFather`, remove the dedicated `python3` entry from System Settings → Privacy & Security → Full Disk Access, then run `reset --yes`.
- Pause forwarding: run `uninstall`; use `run` for temporary foreground operation.
- macOS or Python upgrade: rerun `doctor` and verify Messages, Keychain, Telegram, and LaunchAgent.

## 7. Data locations

- dedicated Python runtime: `~/Library/Application Support/SMS Bridge/runtime`, used only for this tool;
- Bot Token and Discord Webhook URL: macOS Keychain at rest; cached in current-process memory and released when that process exits;
- paired chat ID, per-provider delivery cursors, and preferences: `~/Library/Application Support/SMS Bridge/state.sqlite3`;
- background logs: the same directory; logs are designed not to contain Tokens, OTPs, or message bodies;
- Messages database: queried directly through SQLite `mode=ro`; no persistent copy is created;
- OTP history: not retained.

The setup page binds only to `127.0.0.1`. Never expose it through a tunnel, reverse proxy, port-forward, or public sharing tool.

## 8. Troubleshooting

### Test notification works, but a new message is not forwarded

Confirm that it appears in the Mac Messages app and contains both an OTP keyword and a 4–8 digit sequence. Run `doctor` to check database access.

### `doctor` cannot read Messages

Grant Full Disk Access to the terminal or Python executable that actually runs the bridge. Quit it completely and restart. Do not change `chat.db` filesystem permissions.

### Keychain prompts keep appearing

Confirm the expected Python path. After a Python upgrade or path change, macOS may treat it as a different program. Save the Token again from the interactive setup page and choose Always Allow only on the trusted prompt.

### Background startup does not forward

Run `doctor`. If the LaunchAgent is not loaded, run `uninstall` and install it again from the setup page. The background Python executable also needs Full Disk Access.

### Telegram rejects the Token

Do not post it in an issue. Revoke it in `@BotFather`, save the replacement, and pair again.

### Discord test fails

Confirm the URL comes from the target private channel's Integrations → Webhooks page. If it was deleted or exposed, regenerate it in Discord; never paste the complete URL into an issue.

## 9. Upgrading

```zsh
python3 sms_bridge.py uninstall
# update or replace the source files
python3 sms_bridge.py doctor
python3 sms_bridge.py install
```

Read `CHANGELOG.md` before upgrading. See the [threat model](THREAT_MODEL.en.md) for security boundaries and residual risks.
