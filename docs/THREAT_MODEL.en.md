# Threat Model

SMS Bridge handles OTPs, which are high-value authentication material. This document records the security assumptions for the open-source project. It is not a promise that a compromised Mac, Telegram account, or Apple Account can be made safe by this tool.

## Assets

| Asset | Why it matters | Intended protection |
| --- | --- | --- |
| macOS Messages database | May contain every locally synced conversation | User-granted Full Disk Access; SQLite `mode=ro` queries; no server-side copy |
| Telegram Bot Token | Can read bot updates and send messages as the bot | macOS Keychain at rest; one process-memory cache while running; never rendered, logged, or stored in a plist |
| OTP and sender identifier | May authorize an account or identify a service relationship | In-memory processing; sender is delivered for usability; no relay history |
| Pairing link | Can bind a recipient chat | 256-bit random value, SHA-256 hash only, ten-minute TTL, one use |
| Paired chat ID | Controls notification destination | Local owner-only SQLite state; one private chat only |

## Trust boundaries

1. **macOS and the local user account:** SMS Bridge trusts the user account and its Full Disk Access policy. Malware running as the same user may be able to read the Messages database or relay state. This is outside the application's security boundary.
2. **Apple Messages sync:** The application only sees content that macOS has already synced. It does not bypass iOS sandboxing or Apple Account security.
3. **Telegram:** Telegram Bot API is the only intended outbound network destination. Sending an OTP to Telegram necessarily shares it with Telegram's infrastructure and the paired Telegram account.
4. **Local setup page:** The page binds only to `127.0.0.1`, rejects cross-origin writes, accepts JSON only, and limits request size. It must never be exposed through a tunnel, reverse proxy, port-forward, or browser-sharing tool.

## Threats and controls

| Threat | Control | Residual risk |
| --- | --- | --- |
| A pairing URL is copied or guessed | 256-bit entropy, hash-at-rest, one use, short expiry, private-chat check | Anyone who obtains a valid URL before use can pair; treat it as a credential |
| Bot Token leaks | Keychain storage, secret scanning, no logging; documented rotation | A leaked token remains powerful until revoked in @BotFather |
| A malicious site posts to localhost | Origin and Content-Type validation, loopback binding, size limit | A compromised local browser extension may act with the user’s browser privileges |
| Full Disk Access is granted too broadly | Double-click launcher creates an owner-only dedicated Python runtime; documentation points FDA to it | Any code deliberately executed with that dedicated interpreter inherits its access |
| User enables all-message mode | Disabled by default; UI warns before enabling; destination remains the single paired private chat | Ordinary SMS and iMessage text traverses Telegram infrastructure |
| Two processes forward an OTP twice | Advisory `flock` single-instance lock | A hostile process can remove/ignore a user-level lock |
| Temporary Telegram outage | Bounded retries and exponential loop backoff; cursor advances only after notification succeeds | Delivery is delayed; this tool is not a guaranteed-delivery system |
| Full SMS is disclosed | Parser emits service, code, and sender; full text requires an explicit local opt-in | The code and sender remain sensitive once delivered to Telegram |
| OTP parser matches irrelevant text | Context keyword plus 4–8 digit match | False positives remain possible; future releases should support sender allowlists |

## Non-goals

- End-to-end encryption beyond the platforms selected by the user;
- multi-user, group, or public delivery;
- cloud backup, web history, or forensic message archive;
- operating on a jailbroken iPhone or bypassing Apple permissions;
- a claim that OTP relaying is appropriate for every financial, healthcare, or corporate account.

## Release gates

Before a release: run the test suite and secret scanner; verify that no `.env`, state database, log, pairing URL, OTP, chat ID, or Bot Token is tracked; review changes touching pairing, Keychain, localhost HTTP, or notification rendering; and test `doctor`, `pair`, `test`, `unpair`, and `uninstall` on a clean macOS user account.
