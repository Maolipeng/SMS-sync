## Summary

Describe the change and its user-visible effect.

## Security and privacy

- [ ] No real Bot Token, Discord Webhook URL, OTP, Chat ID, pairing URL, message body, `.env`, state database, or runtime log is included.
- [ ] Changes to pairing, Keychain, localhost HTTP, Messages access, or Telegram rendering include focused tests.
- [ ] Any changed trust boundary or retained data is documented in both threat-model languages.

## Verification

- [ ] `python3 scripts/release_check.py`
- [ ] Manual test used synthetic data only.
