"""Unit tests for the security-sensitive, dependency-free core."""

import importlib
import os
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

TEST_DIR = tempfile.TemporaryDirectory()
os.environ["SMS_BRIDGE_DATA_DIR"] = TEST_DIR.name
app = importlib.import_module("sms_bridge")


class OtpParserTests(unittest.TestCase):
    @staticmethod
    def attributed_body(text):
        payload = text.encode("utf-8")
        if len(payload) <= 0x7F:
            length = bytes([len(payload)])
        else:
            length = b"\x81" + len(payload).to_bytes(2, "little")
        return (
            b"\x04\x0bstreamtyped"
            + b"NSAttributedString"
            + b"NSString"
            + b"\x01\x95\x84\x01\x2b"
            + length
            + payload
            + b"\x86\x84"
        )

    def test_requires_context_and_code(self):
        self.assertEqual(app.parse_otp("Google verification code: 123 456"), "123456")
        self.assertEqual(app.parse_otp("验证码：1234-56"), "123456")
        self.assertIsNone(app.parse_otp("会议室改到 123456"))
        self.assertIsNone(app.parse_otp("Your verification code is ready"))

    def test_smart_mode_accepts_compact_code_but_blocks_common_false_positives(self):
        self.assertEqual(
            app.parse_otp("本次操作请妥善保管12345", allow_compact=True),
            "12345",
        )
        self.assertIsNone(app.parse_otp("本次操作请妥善保管12345"))
        self.assertIsNone(app.parse_otp("订单123456", allow_compact=True))
        self.assertIsNone(app.parse_otp("Welcome 123456", allow_compact=True))

    def test_pickup_code_is_preferred_over_tracking_suffix(self):
        text = "【示例代收点】凭3-7-2468到示例小区驿站取运单尾号0000包裹"
        self.assertEqual(app.parse_otp(text), "3-7-2468")
        self.assertEqual(app.code_label(text), "取件码")
        rendered = app.format_notification(text, "106900000000000")
        self.assertIn("<b>取件码</b>", rendered)
        self.assertIn("🔐  <b>3-7-2468</b>", rendered)
        self.assertNotIn("🔐  <b>0000</b>", rendered)

    def test_explicit_plain_pickup_code_is_supported(self):
        self.assertEqual(app.parse_otp("您的取件码为583921，请到驿站领取包裹"), "583921")

    def test_all_message_notification_is_bounded_and_escaped(self):
        rendered = app.format_message_notification(
            "<private>普通短信</private>",
            "+1 555 010 1234",
            received_at="17:08",
        )
        self.assertIn("+1 555 010 1234", rendered)
        self.assertIn("17:08", rendered)
        self.assertIn("&lt;private&gt;", rendered)
        self.assertNotIn("<private>", rendered)

    def test_modern_messages_attributed_body_is_decoded(self):
        short = "您的验证码是123456"
        long = "请妥善保管" * 30 + "123456"
        self.assertEqual(app.decode_attributed_body(self.attributed_body(short)), short)
        self.assertEqual(app.decode_attributed_body(self.attributed_body(long)), long)
        self.assertIsNone(app.decode_attributed_body(b"not-a-typedstream"))

    def test_notification_formatting_is_minimal(self):
        self.assertEqual(app.format_code("123456"), "123456")
        self.assertEqual(app.format_code("1234"), "1234")
        self.assertEqual(app.service_name("OpenAI verification code"), "OpenAI")
        self.assertEqual(app.service_name("【哔哩哔哩】验证码 123456"), "哔哩哔哩")
        self.assertEqual(app.service_name("verification code"), "验证码")

    def test_sender_is_visible_and_full_message_is_opt_in(self):
        text = "Google verification code: 123456. Private explanatory text."
        app.set_preview_enabled(False)
        minimal = app.format_notification(text, "+1 555 010 1234")
        self.assertIn("+1 555 010 1234", minimal)
        self.assertIn("🔐  <b>123456</b>", minimal)
        self.assertNotIn("<pre>", minimal)
        self.assertLess(minimal.index("123456"), minimal.index("+1 555 010 1234"))
        self.assertNotIn("Private explanatory text", minimal)
        app.set_preview_enabled(True)
        detailed = app.format_notification(text, "+1 555 010 1234")
        self.assertIn("Private explanatory text", detailed)
        app.set_preview_enabled(False)

    def test_code_line_fits_narrow_mobile_clients(self):
        rendered = app.format_notification(
            "Your verification code is 12345678",
            "sender@example.com",
        )
        self.assertIn("🔐  <b>12345678</b>", rendered)
        self.assertNotIn("<pre>", rendered)

    def test_long_original_keeps_valid_html_without_mid_tag_truncation(self):
        app.set_preview_enabled(True)
        rendered = app.format_notification(
            "Google verification code: 123456. " + "<private>" * 600,
            "sender@example.com",
        )
        self.assertTrue(rendered.endswith("</blockquote>"))
        self.assertLessEqual(
            len(app.html.unescape(app.re.sub(r"</?[^>]+>", "", rendered))),
            app.MAX_MESSAGE_LENGTH,
        )
        app.set_preview_enabled(False)

    def test_test_notification_is_unambiguously_marked(self):
        rendered = app.format_notification(
            "Google verification code: 482913",
            "+1 555 010 1234",
            test=True,
        )
        self.assertIn("🧪", rendered)
        self.assertIn("模拟通知", rendered)

    def test_copy_button_uses_raw_code(self):
        calls = []
        original = app.telegram
        try:
            app.telegram = lambda _token, method, payload=None, **_kwargs: calls.append((method, payload))
            app.send_telegram("token", "chat", "<pre>482913</pre>", copy_text="482913")
        finally:
            app.telegram = original
        payload = calls[0][1]
        self.assertEqual(
            payload["reply_markup"]["inline_keyboard"][0][0]["copy_text"]["text"],
            "482913",
        )

    def test_message_time_handles_seconds_and_nanoseconds(self):
        self.assertEqual(
            app.message_time_label(3600),
            app.message_time_label(3_600_000_000_000),
        )

    def test_discord_renderer_uses_large_heading_and_escapes_mentions(self):
        notification = app.build_notification(
            "Google verification code: 482913. @everyone",
            "sender_*_@example.com",
            test=True,
        )
        rendered = app.render_discord_notification(notification)
        self.assertIn("# 🔐 482913", rendered)
        self.assertIn(r"sender\_\*\_@example\.com", rendered)
        self.assertNotIn("<pre>", rendered)
        self.assertLessEqual(len(rendered), app.MAX_DISCORD_MESSAGE_LENGTH)


class DiscordProviderTests(unittest.TestCase):
    # Keep synthetic credential-shaped fixtures split so secret scanners never
    # learn a copy-pasteable webhook from the repository.
    VALID_URL = (
        "https://discord.com/api/webhooks/"
        + "123456789012345678"
        + "/"
        + "abcdefghijklmnopqrstuvwxyz_ABCD"
    )

    def test_webhook_url_is_canonical_and_rejects_ssrf_shapes(self):
        self.assertEqual(app.normalize_discord_webhook_url(self.VALID_URL), self.VALID_URL)
        invalid = (
            self.VALID_URL + "?thread_id=1",
            self.VALID_URL + "#fragment",
            self.VALID_URL.replace("discord.com", "discord.com.attacker.example"),
            self.VALID_URL.replace("https://", "http://"),
            "https://discord.com@attacker.example/api/webhooks/123456/token-value-that-is-long-enough",
        )
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(app.BridgeError):
                    app.normalize_discord_webhook_url(value)

    def test_discord_provider_disables_mentions(self):
        calls = []
        original = app.discord_webhook_request
        try:
            app.discord_webhook_request = lambda url, payload=None, **kwargs: calls.append((url, payload))
            provider = app.DiscordWebhookProvider(self.VALID_URL)
            provider.send(app.build_notification("验证码 482913", "@everyone"))
        finally:
            app.discord_webhook_request = original
        self.assertEqual(calls[0][1]["allowed_mentions"], {"parse": []})
        self.assertNotIn(self.VALID_URL, calls[0][1]["content"])

    def test_invalid_webhook_is_not_saved(self):
        original_request = app.discord_webhook_request
        original_save = app.save_discord_webhook_url
        saved = []
        try:
            app.discord_webhook_request = lambda *_args, **_kwargs: (_ for _ in ()).throw(
                app.BridgeError("invalid")
            )
            app.save_discord_webhook_url = saved.append
            with self.assertRaises(app.BridgeError):
                app.configure_discord_webhook(self.VALID_URL)
        finally:
            app.discord_webhook_request = original_request
            app.save_discord_webhook_url = original_save
        self.assertEqual(saved, [])


class PairingTests(unittest.TestCase):
    def setUp(self):
        app.STATE.delete("pairing_token_hash")
        app.STATE.delete("pairing_expires_at")
        app.STATE.delete("paired_chat_id")

    def test_pairing_requires_matching_hash_and_unexpired_time(self):
        app.STATE.set("pairing_token_hash", app.token_hash("secret"))
        app.STATE.set("pairing_expires_at", "9999999999")
        self.assertTrue(app.pairing_valid("secret"))
        self.assertFalse(app.pairing_valid("other"))

    def test_expired_pairing_is_rejected(self):
        app.STATE.set("pairing_token_hash", app.token_hash("secret"))
        app.STATE.set("pairing_expires_at", "1")
        self.assertFalse(app.pairing_valid("secret"))

    def test_existing_pair_must_be_removed_before_replacement(self):
        app.STATE.set("paired_chat_id", "123")
        with self.assertRaisesRegex(app.BridgeError, "先解除配对"):
            app.create_pairing()

    def test_group_start_cannot_pair(self):
        calls = []

        def fake_telegram(_token, method, payload=None, **_kwargs):
            calls.append((method, payload))
            if method == "getUpdates":
                return {"result": [{"update_id": 9, "message": {"text": "/start secret", "chat": {"id": -1, "type": "group"}}}]}
            return {"ok": True}

        original = app.telegram
        try:
            app.telegram = fake_telegram
            app.STATE.set("pairing_token_hash", app.token_hash("secret"))
            app.STATE.set("pairing_expires_at", "9999999999")
            app.process_bot_updates("not-a-real-token")
            self.assertIsNone(app.STATE.get("paired_chat_id"))
        finally:
            app.telegram = original


class TokenRotationTests(unittest.TestCase):
    def test_replacing_token_invalidates_pairing_and_update_cursor(self):
        original_telegram = app.telegram
        original_save = app.save_keychain_token
        saved = []
        try:
            app.telegram = lambda _token, method, _payload=None, **_kwargs: (
                {"ok": True, "result": {"username": "synthetic"}} if method == "getMe" else {"ok": True}
            )
            app.save_keychain_token = lambda token: saved.append(token)
            app.STATE.set("paired_chat_id", "42")
            app.STATE.set("paired_chat_name", "Synthetic")
            app.STATE.set("telegram_update_offset", "99")
            app.configure_bot_token("synthetic-token")
            self.assertEqual(saved, ["synthetic-token"])
            self.assertIsNone(app.STATE.get("paired_chat_id"))
            self.assertIsNone(app.STATE.get("telegram_update_offset"))
        finally:
            app.telegram = original_telegram
            app.save_keychain_token = original_save
            app.unpair()
            app.STATE.delete("telegram_update_offset")


class LockTests(unittest.TestCase):
    def test_second_instance_is_rejected(self):
        with app.SingleInstance():
            with self.assertRaises(app.BridgeError):
                with app.SingleInstance():
                    pass

    def test_settings_ui_lock_is_independent_from_relay_lock(self):
        with app.SingleInstance():
            with app.SingleInstance(app.UI_LOCK_FILE):
                pass

    def test_uninstall_removes_current_and_legacy_launch_agents(self):
        original = app.remove_launch_agent
        removed = []
        try:
            app.remove_launch_agent = removed.append
            app.uninstall_launch_agent()
        finally:
            app.remove_launch_agent = original
        self.assertEqual(
            removed,
            [app.LAUNCH_AGENT_LABEL, *app.LEGACY_LAUNCH_AGENT_LABELS],
        )

    def test_launch_agent_definition_runs_relay_without_secrets(self):
        plist = app.launch_agent_plist()
        self.assertIn("<string>run</string>", plist)
        self.assertIn(str(Path(app.sys.executable).resolve()), plist)
        self.assertNotIn("TELEGRAM_BOT_TOKEN", plist)
        self.assertNotIn("DISCORD_WEBHOOK_URL", plist)
        self.assertNotIn("discord.com/api/webhooks", plist)
        self.assertNotIn("AA", plist)
        self.assertIn(str(app.DATA_DIR), plist)
        self.assertNotIn(f"{app.ROOT}/sms-bridge.log", plist)


class KeychainCacheTests(unittest.TestCase):
    def test_concurrent_status_checks_perform_one_keychain_read(self):
        original_reader = app.read_keychain_token_uncached
        original_cache = app.TOKEN_CACHE
        calls = []

        def fake_reader():
            calls.append("read")
            time.sleep(0.05)
            return "synthetic-token"

        try:
            app.read_keychain_token_uncached = fake_reader
            app.TOKEN_CACHE = app.TOKEN_CACHE_UNSET
            results = []
            workers = [threading.Thread(target=lambda: results.append(app.keychain_token())) for _ in range(8)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join()
            self.assertEqual(calls, ["read"])
            self.assertEqual(results, ["synthetic-token"] * 8)
        finally:
            app.read_keychain_token_uncached = original_reader
            app.TOKEN_CACHE = original_cache


class RelayReliabilityTests(unittest.TestCase):
    def test_initial_messages_permission_failure_recovers_without_exit(self):
        original_stop = app.STOP
        original_keychain = app.keychain_token
        original_latest = app.latest_rowid
        original_fetch = app.fetch_messages
        attempts = []

        class BoundedStop:
            def __init__(self):
                self.waits = 0

            def wait(self, _delay):
                self.waits += 1
                return self.waits > 2

            def is_set(self):
                return False

        def flaky_latest():
            attempts.append("read")
            if len(attempts) == 1:
                raise app.BridgeError("permission unavailable")
            return 42

        try:
            app.STATE.delete("last_rowid")
            app.STOP = BoundedStop()
            app.keychain_token = lambda: None
            app.latest_rowid = flaky_latest
            app.fetch_messages = lambda _after: []
            app.bridge_loop()
            self.assertEqual(attempts, ["read", "read"])
            self.assertEqual(app.STATE.get("last_rowid"), "42")
            self.assertIsNone(app.STATE.get("last_error"))
        finally:
            app.STOP = original_stop
            app.keychain_token = original_keychain
            app.latest_rowid = original_latest
            app.fetch_messages = original_fetch
            app.STATE.delete("last_rowid")
            app.STATE.delete("last_error")

    def test_message_cursor_advances_only_after_successful_delivery(self):
        originals = {
            "STOP": app.STOP,
            "keychain_token": app.keychain_token,
            "process_bot_updates": app.process_bot_updates,
            "fetch_messages": app.fetch_messages,
            "send_telegram": app.send_telegram,
        }
        deliveries = []

        class BoundedStop:
            def __init__(self):
                self.waits = 0

            def wait(self, _delay):
                self.waits += 1
                return self.waits > 3

            def is_set(self):
                return False

        def flaky_send(*_args, **_kwargs):
            deliveries.append(app.STATE.get("last_rowid"))
            if len(deliveries) == 1:
                raise app.TransientTelegramError("temporary")

        message = {
            "rowid": 1,
            "text": "Google verification code: 123456",
            "date": 0,
            "sender": "+1 555 010 1234",
        }
        try:
            app.STATE.set("last_rowid", "0")
            app.STATE.set("paired_chat_id", "42")
            app.STOP = BoundedStop()
            app.keychain_token = lambda: "synthetic-token"
            app.process_bot_updates = lambda _token: None
            app.fetch_messages = lambda after: [message] if after < 1 else []
            app.send_telegram = flaky_send
            app.bridge_loop()
            self.assertEqual(deliveries, ["0", "0"])
            self.assertEqual(app.STATE.get("last_rowid"), "1")
        finally:
            for name, value in originals.items():
                setattr(app, name, value)
            app.STATE.delete("last_rowid")
            app.STATE.delete("last_error")
            app.STATE.delete("paired_chat_id")

    def test_revoked_chat_is_rechecked_before_delivery(self):
        originals = {
            "STOP": app.STOP,
            "keychain_token": app.keychain_token,
            "process_bot_updates": app.process_bot_updates,
            "fetch_messages": app.fetch_messages,
            "send_telegram": app.send_telegram,
        }
        deliveries = []

        class BoundedStop:
            def __init__(self):
                self.waits = 0

            def wait(self, _delay):
                self.waits += 1
                return self.waits > 1

            def is_set(self):
                return False

        message = {
            "rowid": 7,
            "text": "Google verification code: 123456",
            "date": 0,
            "sender": "+1 555 010 1234",
        }

        def revoke_before_return(_after):
            app.unpair()
            return [message]

        try:
            app.STATE.set("last_rowid", "6")
            app.STATE.set("paired_chat_id", "42")
            app.STOP = BoundedStop()
            app.keychain_token = lambda: "synthetic-token"
            app.process_bot_updates = lambda _token: None
            app.fetch_messages = revoke_before_return
            app.send_telegram = lambda *_args, **_kwargs: deliveries.append("sent")
            app.bridge_loop()
            self.assertEqual(deliveries, [])
            self.assertEqual(app.STATE.get("last_rowid"), "7")
        finally:
            for name, value in originals.items():
                setattr(app, name, value)
            app.STATE.delete("last_rowid")
            app.STATE.delete("last_error")
            app.STATE.delete("paired_chat_id")

    def test_partial_provider_failure_does_not_duplicate_successful_delivery(self):
        originals = {
            "STOP": app.STOP,
            "keychain_token": app.keychain_token,
            "process_bot_updates": app.process_bot_updates,
            "fetch_messages": app.fetch_messages,
            "active_notification_providers": app.active_notification_providers,
        }
        deliveries = {"first": 0, "second": 0}

        class BoundedStop:
            def __init__(self):
                self.waits = 0

            def wait(self, _delay):
                self.waits += 1
                return self.waits > 3

            def is_set(self):
                return False

        class FakeProvider(app.NotificationProvider):
            def __init__(self, provider_id, fail_once=False):
                self.provider_id = provider_id
                self.fail_once = fail_once

            def send(self, _notification):
                deliveries[self.provider_id] += 1
                if self.fail_once and deliveries[self.provider_id] == 1:
                    raise app.TransientProviderError("temporary")

        providers = [FakeProvider("first"), FakeProvider("second", fail_once=True)]
        message = {
            "rowid": 11,
            "text": "Google verification code: 123456",
            "date": 0,
            "sender": "+1 555 010 1234",
        }
        try:
            app.STATE.set("last_rowid", "10")
            app.STATE.delete("provider_cursor_first")
            app.STATE.delete("provider_cursor_second")
            app.STOP = BoundedStop()
            app.keychain_token = lambda: None
            app.process_bot_updates = lambda _token: None
            app.fetch_messages = lambda after: [message] if after < 11 else []
            app.active_notification_providers = lambda: providers
            app.bridge_loop()
            self.assertEqual(deliveries, {"first": 1, "second": 2})
            self.assertEqual(app.STATE.get("last_rowid"), "11")
        finally:
            for name, value in originals.items():
                setattr(app, name, value)
            app.STATE.delete("last_rowid")
            app.STATE.delete("last_error")
            app.STATE.delete("provider_cursor_first")
            app.STATE.delete("provider_cursor_second")


class LegacyCleanupTests(unittest.TestCase):
    def test_legacy_credentials_state_and_logs_are_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = root / ".env"
            env.write_text(
                "# retained comment\n"
                "TELEGRAM_BOT_TOKEN=123456789:AA-not-a-real-token\n"
                "export TELEGRAM_CHAT_ID=42\n"
                "DISCORD_WEBHOOK_URL=https://example.invalid/private\n"
                "KEEP_THIS=value\n",
                encoding="utf-8",
            )
            with sqlite3.connect(root / "state.sqlite3") as database:
                database.execute("CREATE TABLE settings (key TEXT, value TEXT)")
                database.execute("INSERT INTO settings VALUES ('paired_chat_id', '42')")
            (root / "sms-bridge.log").write_text("old", encoding="utf-8")
            (root / "sms-bridge.error.log").write_text("old", encoding="utf-8")

            app.scrub_legacy_configuration(root)

            self.assertFalse((root / "state.sqlite3").exists())
            self.assertFalse((root / "sms-bridge.log").exists())
            self.assertFalse((root / "sms-bridge.error.log").exists())
            retained = env.read_text(encoding="utf-8")
            self.assertNotIn("TELEGRAM_BOT_TOKEN", retained)
            self.assertNotIn("TELEGRAM_CHAT_ID", retained)
            self.assertNotIn("DISCORD_WEBHOOK_URL", retained)
            self.assertIn("KEEP_THIS=value", retained)


class LocalHttpHardeningTests(unittest.TestCase):
    def setUp(self):
        self.original_keychain_token = app.keychain_token
        self.original_discord_webhook_url = app.discord_webhook_url
        app.keychain_token = lambda: None
        app.discord_webhook_url = lambda: None
        self.server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        app.keychain_token = self.original_keychain_token
        app.discord_webhook_url = self.original_discord_webhook_url

    def test_cross_origin_write_is_rejected(self):
        url = f"http://127.0.0.1:{self.server.server_port}/api/unpair"
        request = urllib.request.Request(
            url,
            data=b"{}",
            headers={"Content-Type": "application/json", "Origin": "https://attacker.example"},
            method="POST",
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with self.assertRaises(urllib.error.HTTPError) as raised:
            opener.open(request)
        self.assertEqual(raised.exception.code, 403)

    def test_dns_rebinding_host_is_rejected_for_reads_and_writes(self):
        url = f"http://127.0.0.1:{self.server.server_port}/"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        read = urllib.request.Request(url, headers={"Host": "attacker.example"})
        with self.assertRaises(urllib.error.HTTPError) as raised:
            opener.open(read)
        self.assertEqual(raised.exception.code, 400)

        write = urllib.request.Request(
            url + "api/settings",
            data=b'{"showOriginal":true}',
            headers={
                "Host": "attacker.example",
                "Content-Type": "application/json",
                "Origin": "http://attacker.example",
                "X-SMS-Bridge-CSRF": app.CSRF_TOKEN,
            },
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as raised:
            opener.open(write)
        self.assertEqual(raised.exception.code, 400)

    def test_setup_page_has_no_cache_and_frame_protection(self):
        url = f"http://127.0.0.1:{self.server.server_port}/"
        response = urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.headers["Cross-Origin-Opener-Policy"], "same-origin")
        self.assertEqual(response.headers["Cross-Origin-Resource-Policy"], "same-origin")
        self.assertIn("camera=()", response.headers["Permissions-Policy"])
        self.assertNotIn("Python", response.headers["Server"])
        csp = response.headers["Content-Security-Policy"]
        page = response.read().decode()
        self.assertIn(f"script-src 'nonce-{app.CSRF_TOKEN}'", csp)
        self.assertIn(f'<script nonce="{app.CSRF_TOKEN}">', page)

    def test_setup_page_exposes_non_sensitive_doctor_action(self):
        url = f"http://127.0.0.1:{self.server.server_port}/api/doctor"
        response = urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url)
        result = __import__("json").loads(response.read())
        self.assertIn("messages", result)
        self.assertNotRegex(__import__("json").dumps(result), r"\d{7,}:AA[A-Za-z0-9_-]{20,}")

    def test_status_never_exposes_discord_webhook_url(self):
        webhook = DiscordProviderTests.VALID_URL
        app.discord_webhook_url = lambda: webhook
        url = f"http://127.0.0.1:{self.server.server_port}/api/status"
        response = urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url)
        body = response.read().decode()
        self.assertNotIn(webhook, body)
        result = __import__("json").loads(body)
        self.assertTrue(result["discordConfigured"])

    def test_settings_write_requires_same_origin(self):
        url = f"http://127.0.0.1:{self.server.server_port}/api/settings"
        request = urllib.request.Request(
            url,
            data=b'{"showOriginal":true}',
            headers={"Content-Type": "application/json", "Origin": "https://attacker.example"},
            method="POST",
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with self.assertRaises(urllib.error.HTTPError) as raised:
            opener.open(request)
        self.assertEqual(raised.exception.code, 403)

    def test_same_origin_settings_write_requires_and_accepts_csrf(self):
        url = f"http://127.0.0.1:{self.server.server_port}/api/settings"
        origin = f"http://127.0.0.1:{self.server.server_port}"
        request = urllib.request.Request(
            url,
            data=b'{"showOriginal":true}',
            headers={
                "Content-Type": "application/json",
                "Origin": origin,
                "X-SMS-Bridge-CSRF": app.CSRF_TOKEN,
            },
            method="POST",
        )
        response = urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request)
        self.assertEqual(response.status, 200)
        self.assertTrue(app.preview_enabled())
        app.set_preview_enabled(False)

    def test_forward_mode_setting_is_validated(self):
        url = f"http://127.0.0.1:{self.server.server_port}/api/settings"
        origin = f"http://127.0.0.1:{self.server.server_port}"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def update(value):
            return opener.open(urllib.request.Request(
                url,
                data=__import__("json").dumps({"forwardMode": value}).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Origin": origin,
                    "X-SMS-Bridge-CSRF": app.CSRF_TOKEN,
                },
                method="POST",
            ))

        try:
            self.assertEqual(update("smart").status, 200)
            self.assertEqual(app.forward_mode(), "smart")
            with self.assertRaises(urllib.error.HTTPError) as raised:
                update("everything")
            self.assertEqual(raised.exception.code, 400)
        finally:
            app.set_forward_mode("strict")

    def test_discord_endpoint_requires_csrf_and_never_echoes_secret(self):
        url = f"http://127.0.0.1:{self.server.server_port}/api/discord"
        origin = f"http://127.0.0.1:{self.server.server_port}"
        webhook = DiscordProviderTests.VALID_URL
        original = app.configure_discord_webhook
        received = []
        app.configure_discord_webhook = received.append
        try:
            request = urllib.request.Request(
                url,
                data=__import__("json").dumps({"webhookUrl": webhook}).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Origin": origin,
                    "X-SMS-Bridge-CSRF": app.CSRF_TOKEN,
                },
                method="POST",
            )
            response = urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request)
            body = response.read().decode()
            self.assertEqual(received, [webhook])
            self.assertNotIn(webhook, body)
        finally:
            app.configure_discord_webhook = original


if __name__ == "__main__":
    unittest.main()
