# Threat Model

SMS Bridge handles OTPs, which are high-value authentication material. This document records the security assumptions for the open-source project. It is not a promise that a compromised Mac, Telegram account, or Apple Account can be made safe by this tool.

## Assets

| Asset | Why it matters | Intended protection |
| --- | --- | --- |
| macOS Messages database | May contain every locally synced conversation | User-granted Full Disk Access; SQLite `mode=ro` queries; no server-side copy |
| Telegram Bot Token | Can read bot updates and send messages as the bot | macOS Keychain at rest; one process-memory cache while running; never rendered, logged, or stored in a plist |
| Discord Webhook URL | Anyone holding it can post to the destination channel | macOS Keychain at rest; canonical HTTPS URL only; never rendered, logged, or stored in a plist |
| OTP and sender identifier | May authorize an account or identify a service relationship | In-memory processing; sender is delivered for usability; no relay history |
| Pairing link | Can bind a recipient chat | 256-bit random value, SHA-256 hash only, ten-minute TTL, one use |
| Paired chat ID | Controls notification destination | Local owner-only SQLite state; one private chat only |

## Trust boundaries

1. **macOS and the local user account:** SMS Bridge trusts the user account and its Full Disk Access policy. Malware running as the same user may be able to read the Messages database or relay state. This is outside the application's security boundary.
2. **Apple Messages sync:** The application only sees content that macOS has already synced. It does not bypass iOS sandboxing or Apple Account security.
3. **Notification providers:** outbound targets are limited to configured Telegram Bot API and official Discord Webhook endpoints. Sending an OTP shares it with the selected provider and destination account/channel.
4. **Local setup page:** The page binds only to `127.0.0.1`, rejects cross-origin writes, accepts JSON only, and limits request size. It must never be exposed through a tunnel, reverse proxy, port-forward, or browser-sharing tool.

## Threats and controls

| Threat | Control | Residual risk |
| --- | --- | --- |
| A pairing URL is copied or guessed | 256-bit entropy, hash-at-rest, one use, short expiry, private-chat check | Anyone who obtains a valid URL before use can pair; treat it as a credential |
| Bot Token leaks | Keychain storage, secret scanning, no logging; documented rotation | A leaked token remains powerful until revoked in @BotFather |
| Discord Webhook leaks or enables SSRF | Keychain storage; exact `discord.com` HTTPS path validation; no URL credentials, query, or redirects; URL-free errors | A leaked URL can post until deleted or regenerated in Discord |
| A malicious site posts to localhost | Origin and Content-Type validation, loopback binding, size limit | A compromised local browser extension may act with the user’s browser privileges |
| Full Disk Access is granted too broadly | Double-click launcher creates an owner-only dedicated Python runtime; documentation points FDA to it | Any code deliberately executed with that dedicated interpreter inherits its access |
| User enables all-message mode | Disabled by default; UI warns before enabling; delivery remains limited to user-enabled providers | Ordinary SMS and iMessage text traverses every enabled provider |
| Two processes forward an OTP twice | Advisory `flock` single-instance lock | A hostile process can remove/ignore a user-level lock |
| Temporary provider outage | Bounded retries and exponential loop backoff; per-provider cursor advances only after success | Delivery is delayed; this tool is not a guaranteed-delivery system |
| Partial multi-provider success | A per-provider cursor skips a destination that already succeeded during retry | A platform may accept before its acknowledgement is received, so extreme network failures can still duplicate |
| Full SMS is disclosed | Parser emits service, code, and sender; full text requires an explicit local opt-in | The code and sender remain sensitive once delivered to any provider |
| OTP parser matches irrelevant text | Context keyword plus 4–8 digit match | False positives remain possible; future releases should support sender allowlists |

## Non-goals

- End-to-end encryption beyond the platforms selected by the user;
- multi-user or public delivery; Discord should use a private channel;
- cloud backup, web history, or forensic message archive;
- operating on a jailbroken iPhone or bypassing Apple permissions;
- a claim that OTP relaying is appropriate for every financial, healthcare, or corporate account.

## Release gates

Before a release: run the test suite and secret scanner; verify that no `.env`, state database, log, pairing URL, OTP, chat ID, Bot Token, or Discord Webhook URL is tracked; review changes touching providers, pairing, Keychain, localhost HTTP, or rendering; and test `doctor`, provider setup, `test`, `unpair`, and `uninstall` on a clean macOS account.
