# SMS Bridge

SMS Bridge is a local macOS utility that relays one-time passcodes received by an iPhone (and synced through Apple Messages to a Mac) to a paired Telegram private chat, a Discord private-channel webhook, or both.

It is designed for personal use: local-first, single-recipient, and intentionally narrow.

## What it does

```text
iPhone receives an SMS/iMessage
        ↓ Apple Messages sync
Mac running SMS Bridge
        ↓ notification providers
Telegram private chat / Discord private channel
```

It does **not** expose a public web server, host your messages, support groups, or retain OTP history.

## Requirements

- macOS and Python 3.10+;
- iPhone and Mac signed in to the same Apple Account, with Messages sync enabled;
- at least one destination: a Telegram bot created with [@BotFather](https://t.me/BotFather), or a Discord Incoming Webhook in a private channel.

Before using the relay, make sure the test SMS is visible in the Mac Messages app. The recommended launcher creates a dedicated Python runtime for SMS Bridge. Grant Full Disk Access to that runtime at System Settings → Privacy & Security → Full Disk Access; advanced CLI users who bypass the launcher must authorize the executable they actually run.

## Quick start

Download and extract the source, then double-click `SMS Bridge.command`. Terminal users can enter the project directory and run `python3 sms_bridge.py`.

The launcher creates an owner-only, dedicated Python runtime under `~/Library/Application Support/SMS Bridge/runtime`; grant Full Disk Access to that runtime rather than a general-purpose Python installation. The local onboarding page opens at `http://127.0.0.1:8765` (or the next available local port). It guides you through Telegram pairing, optional Discord Webhook setup, and test delivery.

macOS may still deny direct Messages access to a setup page launched by an unauthorized Terminal because Terminal remains the responsible process. You do not need to broaden Terminal access: after Token setup and pairing, install background startup. The LaunchAgent uses the authorized, resolved `python3.10` path and reports its verified access back to the setup page.

The pairing link is random, valid for ten minutes, and single-use. It can pair only a Telegram `private` chat.

## CLI

```zsh
python3 sms_bridge.py ui
python3 sms_bridge.py init
python3 sms_bridge.py run
python3 sms_bridge.py doctor
python3 sms_bridge.py pair
python3 sms_bridge.py status
python3 sms_bridge.py test
python3 sms_bridge.py test --provider discord
python3 sms_bridge.py unpair
python3 sms_bridge.py install
python3 sms_bridge.py uninstall
python3 sms_bridge.py reset --yes
python3 sms_bridge.py config --show-original on
python3 sms_bridge.py config --mode strict
python3 sms_bridge.py config --mode smart
python3 sms_bridge.py config --mode all
python3 sms_bridge.py discord set
python3 sms_bridge.py discord test
python3 sms_bridge.py discord enable
python3 sms_bridge.py discord disable
python3 sms_bridge.py discord remove
```

`run` is intended for `launchd`, `tmux`, or other process supervisors. `doctor` reports safe diagnostics only—never an OTP, message body, pairing URL, Bot Token, or Discord Webhook URL.

## Privacy and security defaults

- Telegram Bot Token and Discord Webhook URL are stored at rest in macOS Keychain and cached only in process memory while running. Environment-token fallback is development-only and Telegram-only.
- Runtime state is stored under `~/Library/Application Support/SMS Bridge` with owner-only permissions.
- The local setup server binds to loopback only and rejects cross-origin POST requests.
- One advisory lock prevents two relay instances from consuming updates or forwarding the same OTP twice. Per-provider delivery cursors avoid duplicating a successful destination when another destination temporarily fails.
- Notifications include a detected service name, OTP or pickup code, and full sender identifier (phone number or email), but not the full SMS text or attachments by default. Pickup messages prefer the collection code over a tracking-number suffix.
- New installations use strict OTP matching. Smart OTP mode accepts constrained compact Chinese code messages. All-message mode explicitly forwards ordinary SMS and iMessage text and therefore carries substantially higher privacy risk.
- Full message text is an explicit opt-in in the local UI or with `config --show-original on`; it is sent to every enabled provider, read from Messages at forwarding time, and not kept as relay history.
- Discord accepts only canonical `https://discord.com/api/webhooks/...` URLs, disables mentions, and refuses credential-bearing redirects.
- Telegram commands: `/status` and `/unpair` are accepted only from the paired private chat.

Read [SECURITY.md](SECURITY.md) and the detailed [threat model](docs/THREAT_MODEL.en.md) before self-hosting or contributing. If a Bot Token or Discord Webhook URL has ever been posted in a chat, issue tracker, screenshot, or commit, revoke the Token in @BotFather or regenerate the Webhook immediately.

## Development

```zsh
python3 -m unittest discover -s tests -v
```

See the detailed [English user guide](docs/USER_GUIDE.en.md), [Chinese user guide](docs/USER_GUIDE.zh-CN.md), [CONTRIBUTING.md](CONTRIBUTING.md), and the [release guide](docs/RELEASING.md). The repository is licensed under [MIT](LICENSE).
