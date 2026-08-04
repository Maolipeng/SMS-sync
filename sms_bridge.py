#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SMS Bridge — private, local-only iPhone Messages notification relay.

Run `python3 sms_bridge.py` and open the local setup page.  The program has no
third-party Python dependencies and never starts a public network listener.
"""
from __future__ import annotations

import argparse
import ctypes
import fcntl
import getpass
import hashlib
import html
import json
import os
import plistlib
import re
import secrets
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from sms_bridge_ui import render_page

APP_NAME = "SMS Bridge"
ROOT = Path(__file__).resolve().parent
MESSAGES_DB = Path.home() / "Library/Messages/chat.db"
DATA_DIR = Path(os.getenv("SMS_BRIDGE_DATA_DIR", Path.home() / "Library/Application Support/SMS Bridge"))
STATE_DB = DATA_DIR / "state.sqlite3"
LOCK_FILE = DATA_DIR / "sms-bridge.lock"
UI_LOCK_FILE = DATA_DIR / "sms-bridge-ui.lock"
# Versioned service name avoids inheriting prototype ACLs that trusted `/usr/bin/security`.
KEYCHAIN_SERVICE = "dev.smsbridge.telegram-bot-token.v1"
LEGACY_KEYCHAIN_SERVICES = ("dev.smsbridge.telegram-bot-token",)
DISCORD_KEYCHAIN_SERVICE = "dev.smsbridge.discord-webhook-url.v1"
LAUNCH_AGENT_LABEL = "dev.smsbridge.service"
LEGACY_LAUNCH_AGENT_LABELS = ("com.local.sms-bridge",)
POLL_SECONDS = 3
PAIRING_TTL_SECONDS = 10 * 60
MAX_MESSAGE_LENGTH = 3500
MAX_PREVIEW_LENGTH = 1800
MAX_ATTRIBUTED_BODY_BYTES = 1024 * 1024
MAX_REQUEST_BYTES = 8 * 1024
MAX_TELEGRAM_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_DISCORD_RESPONSE_BYTES = 512 * 1024
MAX_DISCORD_MESSAGE_LENGTH = 1900
MAX_SMS_REPLY_LENGTH = 1000
REPLY_TARGET_TTL_SECONDS = 7 * 24 * 60 * 60
MAX_REPLY_TARGETS = 500
CSRF_TOKEN = secrets.token_urlsafe(32)
APPLE_MESSAGES_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)
ERR_SEC_SUCCESS = 0
ERR_SEC_DUPLICATE_ITEM = -25299
ERR_SEC_ITEM_NOT_FOUND = -25300
CODE_RE = re.compile(r"(?<!\d)(?:\d[\s-]?){4,8}(?!\d)")
KEYWORD_RE = re.compile(r"\b(?:code|verification|verify|otp|passcode|security|pin)\b|验证码|校验码|动态码", re.I)
PICKUP_CONTEXT_RE = re.compile(r"取件码|收件码|提货码|驿站|代收点|取包裹|领取包裹")
PICKUP_EXPLICIT_RE = re.compile(
    r"(?:取件码|收件码|提货码)\s*(?:是|为|[:：])?\s*"
    r"((?:\d{1,4}(?:-\d{1,6}){1,3})|(?:\d{4,10}))(?!\d)"
)
PICKUP_VOUCHER_RE = re.compile(
    r"凭\s*((?:\d{1,4}(?:-\d{1,6}){1,3})|(?:\d{4,10}))\s*(?:到|至|前往)"
)
SHORT_CODE_BLOCKLIST_RE = re.compile(
    r"订单|余额|快递|取件|金额|支付|消费|账单|尾号|电话|手机号|"
    r"会议|房间|门牌|工号|编号|日期|时间|航班|车次"
)
FORWARD_MODES = ("strict", "smart", "all")
STOP = threading.Event()
TOKEN_CACHE_LOCK = threading.Lock()
TOKEN_LOAD_LOCK = threading.Lock()
AUTHORIZATION_LOCK = threading.RLock()
TOKEN_CACHE_UNSET = object()
TOKEN_CACHE: str | None | object = TOKEN_CACHE_UNSET
DISCORD_CACHE_LOCK = threading.Lock()
DISCORD_LOAD_LOCK = threading.Lock()
DISCORD_WEBHOOK_CACHE: str | None | object = TOKEN_CACHE_UNSET


class BridgeError(RuntimeError):
    """An expected, user-safe error message."""


class TransientTelegramError(BridgeError):
    """A retryable Telegram transport failure."""


class TransientProviderError(BridgeError):
    """A retryable notification-provider transport failure."""


class MessagesAccessError(BridgeError):
    """Messages could not be read in the current macOS responsibility chain."""


def stop_handler(_signum: int, _frame: object) -> None:
    STOP.set()


class State:
    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        os.chmod(DATA_DIR, 0o700)
        legacy_state = ROOT / "state.sqlite3"
        # One-time migration for pre-0.1 prototypes; never run in tests/custom dirs.
        if "SMS_BRIDGE_DATA_DIR" not in os.environ and not STATE_DB.exists() and legacy_state.exists():
            shutil.copy2(legacy_state, STATE_DB)
        self.lock = threading.Lock()
        self.conn = sqlite3.connect(STATE_DB, check_same_thread=False)
        self.conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        # A reply target contains only a telephone number and expiry, never SMS
        # content.  It lets a quoted Telegram notification be routed once.
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS telegram_reply_targets "
            "(message_id INTEGER PRIMARY KEY, recipient TEXT NOT NULL, expires_at INTEGER NOT NULL)"
        )
        self.conn.commit()
        os.chmod(STATE_DB, 0o600)

    def get(self, key: str) -> str | None:
        with self.lock:
            row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return str(row[0]) if row else None

    def set(self, key: str, value: str) -> None:
        with self.lock:
            self.conn.execute("INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
            self.conn.commit()

    def delete(self, key: str) -> None:
        with self.lock:
            self.conn.execute("DELETE FROM settings WHERE key = ?", (key,))
            self.conn.commit()

    def save_reply_target(self, message_id: int, recipient: str) -> None:
        expires_at = int(time.time()) + REPLY_TARGET_TTL_SECONDS
        with self.lock:
            self.conn.execute("DELETE FROM telegram_reply_targets WHERE expires_at <= ?", (int(time.time()),))
            self.conn.execute(
                "INSERT INTO telegram_reply_targets(message_id, recipient, expires_at) VALUES (?, ?, ?) "
                "ON CONFLICT(message_id) DO UPDATE SET recipient = excluded.recipient, expires_at = excluded.expires_at",
                (message_id, recipient, expires_at),
            )
            self.conn.execute(
                "DELETE FROM telegram_reply_targets WHERE message_id IN "
                "(SELECT message_id FROM telegram_reply_targets ORDER BY expires_at DESC LIMIT -1 OFFSET ?)",
                (MAX_REPLY_TARGETS,),
            )
            self.conn.commit()

    def take_reply_target(self, message_id: int) -> str | None:
        """Return a live target once; consuming it prevents duplicate SMS sends."""
        with self.lock:
            self.conn.execute("DELETE FROM telegram_reply_targets WHERE expires_at <= ?", (int(time.time()),))
            row = self.conn.execute(
                "SELECT recipient FROM telegram_reply_targets WHERE message_id = ?", (message_id,)
            ).fetchone()
            if row:
                self.conn.execute("DELETE FROM telegram_reply_targets WHERE message_id = ?", (message_id,))
            self.conn.commit()
        return str(row[0]) if row else None

    def clear_reply_targets(self) -> None:
        with self.lock:
            self.conn.execute("DELETE FROM telegram_reply_targets")
            self.conn.commit()

    def secure_clear(self) -> None:
        """Remove local authorization state and scrub deleted SQLite pages."""
        with self.lock:
            self.conn.execute("PRAGMA secure_delete = ON")
            self.conn.execute("DELETE FROM settings")
            self.conn.commit()
            self.conn.execute("VACUUM")


STATE = State()


class SingleInstance:
    """An advisory lock for one independently managed process role."""

    def __init__(self, path: Path = LOCK_FILE, message: str | None = None) -> None:
        self.handle = None
        self.path = path
        self.message = message or "转发引擎已在运行。"

    def __enter__(self) -> "SingleInstance":
        self.handle = open(self.path, "a+", encoding="utf-8")
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.handle.close()
            raise BridgeError(self.message) from exc
        self.handle.seek(0)
        self.handle.truncate()
        self.handle.write(str(os.getpid()))
        self.handle.flush()
        return self

    def __exit__(self, *_args: object) -> None:
        if self.handle:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()


def keychain_frameworks() -> tuple[ctypes.CDLL, ctypes.CDLL]:
    """Load and type the small Keychain API surface used by this app."""
    security = ctypes.CDLL(
        "/System/Library/Frameworks/Security.framework/Versions/Current/Security"
    )
    core_foundation = ctypes.CDLL(
        "/System/Library/Frameworks/CoreFoundation.framework/Versions/Current/CoreFoundation"
    )
    uint32 = ctypes.c_uint32
    void_p = ctypes.c_void_p
    security.SecKeychainFindGenericPassword.argtypes = [
        void_p, uint32, void_p, uint32, void_p,
        ctypes.POINTER(uint32), ctypes.POINTER(void_p), ctypes.POINTER(void_p),
    ]
    security.SecKeychainFindGenericPassword.restype = ctypes.c_int32
    security.SecKeychainAddGenericPassword.argtypes = [
        void_p, uint32, void_p, uint32, void_p, uint32, void_p, ctypes.POINTER(void_p),
    ]
    security.SecKeychainAddGenericPassword.restype = ctypes.c_int32
    security.SecKeychainItemModifyAttributesAndData.argtypes = [
        void_p, void_p, uint32, void_p,
    ]
    security.SecKeychainItemModifyAttributesAndData.restype = ctypes.c_int32
    security.SecKeychainItemFreeContent.argtypes = [void_p, void_p]
    security.SecKeychainItemFreeContent.restype = ctypes.c_int32
    core_foundation.CFRelease.argtypes = [void_p]
    return security, core_foundation


def read_keychain_secret_uncached(service_name: str, description: str) -> str | None:
    """Perform one native Keychain lookup without exposing the stored value."""
    security, core_foundation = keychain_frameworks()
    void_p = ctypes.c_void_p
    service = service_name.encode("utf-8")
    account = getpass.getuser().encode("utf-8")
    service_buffer = ctypes.create_string_buffer(service)
    account_buffer = ctypes.create_string_buffer(account)
    password_length = ctypes.c_uint32()
    password_data = void_p()
    item = void_p()
    status = security.SecKeychainFindGenericPassword(
        None,
        len(service),
        ctypes.cast(service_buffer, void_p),
        len(account),
        ctypes.cast(account_buffer, void_p),
        ctypes.byref(password_length),
        ctypes.byref(password_data),
        ctypes.byref(item),
    )
    if status == ERR_SEC_SUCCESS:
        try:
            value = ctypes.string_at(password_data, password_length.value).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise BridgeError(f"钥匙串中的{description}不是有效文本，请重新保存。") from exc
        finally:
            if password_data:
                security.SecKeychainItemFreeContent(None, password_data)
            if item:
                core_foundation.CFRelease(item)
        return value
    if item:
        core_foundation.CFRelease(item)
    if status != ERR_SEC_ITEM_NOT_FOUND:
        raise BridgeError(f"无法读取 macOS 钥匙串（错误 {status}）。请确认登录钥匙串已解锁。")
    return None


def read_keychain_token_uncached() -> str | None:
    """Perform one native Telegram credential lookup."""
    token = read_keychain_secret_uncached(KEYCHAIN_SERVICE, " Bot Token")
    if token is None and os.getenv("SMS_BRIDGE_ALLOW_ENV_TOKEN") == "1":
        return os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or None
    return token


def keychain_token() -> str | None:
    """Read once per process, avoiding repeated authorization prompts."""
    global TOKEN_CACHE
    with TOKEN_CACHE_LOCK:
        if TOKEN_CACHE is not TOKEN_CACHE_UNSET:
            return TOKEN_CACHE if isinstance(TOKEN_CACHE, str) else None
    with TOKEN_LOAD_LOCK:
        # HTTP status polling and the relay thread can arrive here concurrently.
        with TOKEN_CACHE_LOCK:
            if TOKEN_CACHE is not TOKEN_CACHE_UNSET:
                return TOKEN_CACHE if isinstance(TOKEN_CACHE, str) else None
        token = read_keychain_token_uncached()
        with TOKEN_CACHE_LOCK:
            TOKEN_CACHE = token
        return token


def save_keychain_secret(service_name: str, value: str, description: str) -> None:
    """Write a secret through Security.framework so it never enters argv."""
    if not value or len(value) > 2048 or any(ord(char) < 32 for char in value):
        raise BridgeError(f"{description}格式无效。")
    security, core_foundation = keychain_frameworks()
    uint32 = ctypes.c_uint32
    void_p = ctypes.c_void_p
    service = service_name.encode("utf-8")
    account = getpass.getuser().encode("utf-8")
    secret = value.encode("utf-8")
    service_buffer = ctypes.create_string_buffer(service)
    account_buffer = ctypes.create_string_buffer(account)
    secret_buffer = ctypes.create_string_buffer(secret)
    item = void_p()
    status = security.SecKeychainFindGenericPassword(
        None,
        len(service),
        ctypes.cast(service_buffer, void_p),
        len(account),
        ctypes.cast(account_buffer, void_p),
        None,
        None,
        ctypes.byref(item),
    )
    if status == ERR_SEC_SUCCESS:
        try:
            status = security.SecKeychainItemModifyAttributesAndData(
                item, None, len(secret), ctypes.cast(secret_buffer, void_p)
            )
        finally:
            if item:
                core_foundation.CFRelease(item)
    elif status == ERR_SEC_ITEM_NOT_FOUND:
        status = security.SecKeychainAddGenericPassword(
            None,
            len(service),
            ctypes.cast(service_buffer, void_p),
            len(account),
            ctypes.cast(account_buffer, void_p),
            len(secret),
            ctypes.cast(secret_buffer, void_p),
            None,
        )
    if status not in (ERR_SEC_SUCCESS, ERR_SEC_DUPLICATE_ITEM):
        raise BridgeError(f"无法保存到 macOS 钥匙串（错误 {status}）。请确认登录钥匙串已解锁。")


def save_keychain_token(token: str) -> None:
    """Store the Telegram token and refresh its process-local cache."""
    if len(token) > 512:
        raise BridgeError("Bot Token 格式无效。")
    save_keychain_secret(KEYCHAIN_SERVICE, token, "Bot Token")
    global TOKEN_CACHE
    with TOKEN_CACHE_LOCK:
        TOKEN_CACHE = token


def delete_keychain_service(service_name: str) -> None:
    """Delete one named local credential without exposing its value."""
    security, core_foundation = keychain_frameworks()
    void_p = ctypes.c_void_p
    security.SecKeychainItemDelete.argtypes = [void_p]
    security.SecKeychainItemDelete.restype = ctypes.c_int32
    service = service_name.encode("utf-8")
    account = getpass.getuser().encode("utf-8")
    service_buffer = ctypes.create_string_buffer(service)
    account_buffer = ctypes.create_string_buffer(account)
    item = void_p()
    status = security.SecKeychainFindGenericPassword(
        None,
        len(service),
        ctypes.cast(service_buffer, void_p),
        len(account),
        ctypes.cast(account_buffer, void_p),
        None,
        None,
        ctypes.byref(item),
    )
    if status == ERR_SEC_ITEM_NOT_FOUND:
        return
    if status != ERR_SEC_SUCCESS:
        raise BridgeError(f"无法访问 macOS 钥匙串（错误 {status}）。")
    try:
        status = security.SecKeychainItemDelete(item)
    finally:
        if item:
            core_foundation.CFRelease(item)
    if status != ERR_SEC_SUCCESS:
        raise BridgeError(f"无法删除钥匙串凭据（错误 {status}）。")


def delete_keychain_token() -> None:
    """Delete current and prototype credentials, then clear the memory cache."""
    # Remove prototype ACLs first; cancellation leaves the current credential intact.
    for service_name in (*LEGACY_KEYCHAIN_SERVICES, KEYCHAIN_SERVICE):
        delete_keychain_service(service_name)
    global TOKEN_CACHE
    with TOKEN_CACHE_LOCK:
        TOKEN_CACHE = None


def discord_webhook_url() -> str | None:
    """Read the optional Discord Webhook URL once per process."""
    global DISCORD_WEBHOOK_CACHE
    with DISCORD_CACHE_LOCK:
        if DISCORD_WEBHOOK_CACHE is not TOKEN_CACHE_UNSET:
            return DISCORD_WEBHOOK_CACHE if isinstance(DISCORD_WEBHOOK_CACHE, str) else None
    with DISCORD_LOAD_LOCK:
        with DISCORD_CACHE_LOCK:
            if DISCORD_WEBHOOK_CACHE is not TOKEN_CACHE_UNSET:
                return DISCORD_WEBHOOK_CACHE if isinstance(DISCORD_WEBHOOK_CACHE, str) else None
        value = read_keychain_secret_uncached(DISCORD_KEYCHAIN_SERVICE, " Discord Webhook URL")
        with DISCORD_CACHE_LOCK:
            DISCORD_WEBHOOK_CACHE = value
        return value


def save_discord_webhook_url(value: str) -> None:
    save_keychain_secret(DISCORD_KEYCHAIN_SERVICE, value, "Discord Webhook URL")
    global DISCORD_WEBHOOK_CACHE
    with DISCORD_CACHE_LOCK:
        DISCORD_WEBHOOK_CACHE = value


def delete_discord_webhook_url() -> None:
    delete_keychain_service(DISCORD_KEYCHAIN_SERVICE)
    global DISCORD_WEBHOOK_CACHE
    with DISCORD_CACHE_LOCK:
        DISCORD_WEBHOOK_CACHE = None
    STATE.delete("discord_enabled")
    STATE.delete("provider_cursor_discord")


def configure_bot_token(token: str) -> None:
    """Validate and store a token, invalidating authorization tied to any old bot."""
    telegram(token, "getMe")
    with AUTHORIZATION_LOCK:
        save_keychain_token(token)
        unpair()
        STATE.delete("telegram_update_offset")


def require_token() -> str:
    token = keychain_token()
    if not token:
        raise BridgeError("请先在本机设置页保存 Telegram Bot Token。")
    return token


def telegram(token: str, method: str, payload: dict | None = None, retries: int = 3) -> dict:
    """Call the Bot API without ever exposing its token or response body in errors."""
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                raw = response.read(MAX_TELEGRAM_RESPONSE_BYTES + 1)
                if len(raw) > MAX_TELEGRAM_RESPONSE_BYTES:
                    raise BridgeError("Telegram 响应异常过大，已安全中止。")
                body: dict = json.loads(raw)
            if body.get("ok"):
                return body
            # A malformed request/token will not become valid by retrying.
            raise BridgeError("Telegram 拒绝了请求。请检查 Bot Token 或机器人设置。")
        except urllib.error.HTTPError as exc:
            if 400 <= exc.code < 500 and exc.code != 429:
                raise BridgeError("Telegram 拒绝了请求。请检查 Bot Token 或机器人设置。") from exc
            reason = f"HTTP {exc.code}"
        except (urllib.error.URLError, TimeoutError) as exc:
            reason = "网络连接失败"
        except json.JSONDecodeError as exc:
            reason = "Telegram 返回了无效响应"
        if attempt + 1 < retries:
            time.sleep(2 ** attempt)
    raise TransientTelegramError(f"Telegram 暂时不可用（{reason}），稍后会自动重试。")


def send_telegram(token: str, chat_id: str, text: str, *, copy_text: str | None = None) -> dict:
    # Never slice rendered HTML: doing so can leave an entity or closing tag broken.
    if len(html.unescape(re.sub(r"</?[^>]+>", "", text))) > MAX_MESSAGE_LENGTH:
        raise BridgeError("通知内容过长，已安全拒绝发送。")
    payload: dict = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if copy_text:
        payload["reply_markup"] = {
            "inline_keyboard": [[{
                "text": "📋 复制验证码",
                "copy_text": {"text": copy_text[:256]},
            }]]
        }
    return telegram(token, "sendMessage", payload)


def normalize_discord_webhook_url(value: str) -> str:
    """Accept only Discord's canonical HTTPS webhook endpoint (SSRF defense)."""
    try:
        parsed = urllib.parse.urlsplit(value.strip())
        port = parsed.port
    except ValueError as exc:
        raise BridgeError("Discord Webhook URL 格式无效。") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname != "discord.com"
        or parsed.username
        or parsed.password
        or port not in (None, 443)
        or parsed.query
        or parsed.fragment
        or not re.fullmatch(r"/api/webhooks/\d{6,24}/[A-Za-z0-9._-]{20,256}", parsed.path)
    ):
        raise BridgeError("只接受 https://discord.com/api/webhooks/... 格式的官方 Discord Webhook URL。")
    return urllib.parse.urlunsplit(("https", "discord.com", parsed.path, "", ""))


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Never follow provider redirects with a credential-bearing URL."""

    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


def discord_webhook_request(
    webhook_url: str,
    payload: dict | None = None,
    *,
    retries: int = 3,
) -> dict:
    """Validate or execute a Discord webhook without leaking its URL in errors."""
    canonical = normalize_discord_webhook_url(webhook_url)
    target = canonical if payload is None else canonical + "?wait=true"
    request = urllib.request.Request(
        target,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "SMS-Bridge/0.1",
        },
        method="POST" if payload is not None else "GET",
    )
    opener = urllib.request.build_opener(NoRedirectHandler())
    for attempt in range(retries):
        try:
            with opener.open(request, timeout=15) as response:
                raw = response.read(MAX_DISCORD_RESPONSE_BYTES + 1)
                if len(raw) > MAX_DISCORD_RESPONSE_BYTES:
                    raise BridgeError("Discord 响应异常过大，已安全中止。")
                if not raw:
                    return {"ok": True}
                body = json.loads(raw)
            if payload is None and not isinstance(body, dict):
                raise BridgeError("Discord Webhook 返回了无效响应。")
            return body if isinstance(body, dict) else {"ok": True}
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403, 404):
                raise BridgeError("Discord Webhook 无效或已被删除，请重新复制 URL。") from exc
            if 400 <= exc.code < 500 and exc.code != 429:
                raise BridgeError("Discord 拒绝了通知，请检查 Webhook 设置。") from exc
            reason = f"HTTP {exc.code}"
        except (urllib.error.URLError, TimeoutError):
            reason = "网络连接失败"
        except json.JSONDecodeError:
            reason = "Discord 返回了无效响应"
        if attempt + 1 < retries:
            time.sleep(2 ** attempt)
    raise TransientProviderError(f"Discord 暂时不可用（{reason}），稍后会自动重试。")


def configure_discord_webhook(value: str) -> None:
    """Validate before storing, then enable only for future messages."""
    canonical = normalize_discord_webhook_url(value)
    discord_webhook_request(canonical, retries=1)
    with AUTHORIZATION_LOCK:
        save_discord_webhook_url(canonical)
        STATE.set("discord_enabled", "1")
        STATE.set("provider_cursor_discord", STATE.get("last_rowid") or "0")


def discord_enabled() -> bool:
    return STATE.get("discord_enabled") == "1"


def set_discord_enabled(enabled: bool) -> None:
    if enabled and not discord_webhook_url():
        raise BridgeError("请先保存 Discord Webhook URL。")
    with AUTHORIZATION_LOCK:
        STATE.set("discord_enabled", "1" if enabled else "0")
        if enabled:
            STATE.set("provider_cursor_discord", STATE.get("last_rowid") or "0")


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def create_pairing() -> str:
    if STATE.get("paired_chat_id"):
        raise BridgeError("当前已有已配对私聊；请先解除配对再更换接收者。")
    token = require_token()
    username = telegram(token, "getMe")["result"].get("username")
    if not username:
        raise BridgeError("请先在 @BotFather 为机器人设置 username。")
    raw = secrets.token_urlsafe(32)
    STATE.set("pairing_token_hash", token_hash(raw))
    STATE.set("pairing_expires_at", str(int(time.time()) + PAIRING_TTL_SECONDS))
    return f"https://t.me/{username}?start={raw}"


def pairing_valid(raw: str) -> bool:
    expected = STATE.get("pairing_token_hash")
    expires_at = int(STATE.get("pairing_expires_at") or "0")
    return bool(expected) and secrets.compare_digest(expected, token_hash(raw)) and time.time() < expires_at


def unpair() -> None:
    with AUTHORIZATION_LOCK:
        STATE.delete("paired_chat_id")
        STATE.delete("paired_chat_name")
        STATE.delete("pairing_token_hash")
        STATE.delete("pairing_expires_at")
        STATE.clear_reply_targets()


def launch_agent_plist() -> str:
    """Render the per-user service definition; it deliberately contains no secrets."""
    # TCC Full Disk Access is path-sensitive for command-line tools. Resolve the
    # launcher symlink so launchd uses the exact executable users authorize.
    runtime_executable = str(Path(sys.executable).resolve())
    definition = {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": [runtime_executable, str(Path(__file__).resolve()), "run"],
        "WorkingDirectory": str(ROOT),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Background",
        "ThrottleInterval": 15,
        "StandardOutPath": str(DATA_DIR / "sms-bridge.log"),
        "StandardErrorPath": str(DATA_DIR / "sms-bridge.error.log"),
    }
    return plistlib.dumps(definition, fmt=plistlib.FMT_XML, sort_keys=False).decode("utf-8")


def install_launch_agent() -> None:
    """Install a current-user service without placing secrets in its plist."""
    if not keychain_token() and not (discord_webhook_url() and discord_enabled()):
        raise BridgeError("请先配置至少一个通知渠道，再安装自动启动服务。")
    for legacy_label in LEGACY_LAUNCH_AGENT_LABELS:
        remove_launch_agent(legacy_label)
    label = LAUNCH_AGENT_LABEL
    path = Path.home() / "Library/LaunchAgents" / f"{label}.plist"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".plist.tmp")
    temporary_path.write_text(launch_agent_plist(), encoding="utf-8")
    os.chmod(temporary_path, 0o600)
    temporary_path.replace(path)
    uid = str(os.getuid())
    subprocess.run(["/bin/launchctl", "bootout", f"gui/{uid}/{label}"], capture_output=True)
    result = subprocess.run(["/bin/launchctl", "bootstrap", f"gui/{uid}", str(path)], text=True, capture_output=True)
    if result.returncode:
        raise BridgeError("无法安装开机启动：" + (result.stderr.strip() or "请在 Terminal 中重新尝试。"))


def remove_launch_agent(label: str) -> None:
    path = Path.home() / "Library/LaunchAgents" / f"{label}.plist"
    subprocess.run(["/bin/launchctl", "bootout", f"gui/{os.getuid()}/{label}"], capture_output=True)
    if path.exists():
        path.unlink()


def uninstall_launch_agent() -> None:
    for label in (LAUNCH_AGENT_LABEL, *LEGACY_LAUNCH_AGENT_LABELS):
        remove_launch_agent(label)


def reset_local_configuration() -> None:
    """Remove authorization, credential, service registration, and local logs."""
    STOP.set()
    # Ask Keychain first so a cancelled authorization does not leave a half-reset service.
    with AUTHORIZATION_LOCK:
        delete_keychain_token()
        delete_discord_webhook_url()
        uninstall_launch_agent()
        STATE.secure_clear()
    for log_name in ("sms-bridge.log", "sms-bridge.error.log"):
        log_path = DATA_DIR / log_name
        if log_path.exists():
            log_path.unlink()
    runtime_dir = DATA_DIR / "runtime"
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir)
    for partial_runtime in DATA_DIR.glob("runtime.build.*"):
        if partial_runtime.is_dir():
            shutil.rmtree(partial_runtime)
    scrub_legacy_configuration()
    # SQLite and advisory-lock files contain no data after secure_clear(), but
    # removing them makes reset a literal clean slate. Open file descriptors
    # remain valid until this short-lived process exits.
    for local_path in (STATE_DB, LOCK_FILE, UI_LOCK_FILE):
        if local_path.exists():
            local_path.unlink()
    try:
        DATA_DIR.rmdir()
    except OSError:
        # Keep an unknown/user-created file rather than deleting it.
        pass


def scrub_legacy_configuration(root: Path = ROOT) -> None:
    """Remove credential/state artifacts used by pre-Keychain prototypes."""
    legacy_state = root / "state.sqlite3"
    if legacy_state.exists() or legacy_state.is_symlink():
        if not legacy_state.is_symlink():
            try:
                with sqlite3.connect(legacy_state) as legacy:
                    legacy.execute("PRAGMA secure_delete = ON")
                    table = legacy.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='settings'"
                    ).fetchone()
                    if table:
                        legacy.execute("DELETE FROM settings")
                        legacy.commit()
                        legacy.execute("VACUUM")
            except sqlite3.Error:
                pass
        legacy_state.unlink(missing_ok=True)
    for suffix in ("-journal", "-shm", "-wal"):
        Path(str(legacy_state) + suffix).unlink(missing_ok=True)

    legacy_env = root / ".env"
    if legacy_env.is_file() and not legacy_env.is_symlink():
        retained = [
            line for line in legacy_env.read_text(encoding="utf-8").splitlines()
            if not re.match(
                r"^\s*(?:export\s+)?"
                r"(?:TELEGRAM_BOT_TOKEN|TELEGRAM_CHAT_ID|DISCORD_WEBHOOK_URL)\s*=",
                line,
            )
        ]
        meaningful = [line for line in retained if line.strip() and not line.lstrip().startswith("#")]
        if meaningful:
            temporary = legacy_env.with_suffix(".env.sms-bridge-reset")
            temporary.write_text("\n".join(retained) + "\n", encoding="utf-8")
            os.chmod(temporary, 0o600)
            temporary.replace(legacy_env)
        else:
            legacy_env.unlink()
    for legacy_log in ("sms-bridge.log", "sms-bridge.error.log"):
        (root / legacy_log).unlink(missing_ok=True)


def doctor() -> dict:
    """Run safe diagnostics; values intentionally contain no secret or SMS data."""
    checks: dict[str, dict[str, str | bool]] = {}
    checks["stateDirectory"] = {"ok": DATA_DIR.exists() and os.access(DATA_DIR, os.W_OK), "detail": str(DATA_DIR)}
    checks["pythonExecutable"] = {"ok": True, "detail": sys.executable}
    messages_ok, messages_detail = messages_access_status()
    checks["messages"] = {"ok": messages_ok, "detail": messages_detail}
    try:
        token = keychain_token()
        keychain_error = ""
    except BridgeError as exc:
        token, keychain_error = None, str(exc)
    checks["keychain"] = {
        "ok": bool(token),
        "detail": "Bot Token 已保存在钥匙串" if token else (keychain_error or "尚未保存 Bot Token"),
    }
    if token:
        try:
            bot = telegram(token, "getMe", retries=1)["result"]
            checks["telegram"] = {"ok": True, "detail": f"已连接 @{bot.get('username') or 'bot'}"}
        except BridgeError as exc:
            checks["telegram"] = {"ok": False, "detail": str(exc)}
    else:
        checks["telegram"] = {"ok": False, "detail": "需要先设置 Bot Token"}
    try:
        webhook = discord_webhook_url()
        discord_error = ""
    except BridgeError as exc:
        webhook, discord_error = None, str(exc)
    if webhook:
        try:
            discord_webhook_request(webhook, retries=1)
            checks["discord"] = {
                "ok": True,
                "detail": "Webhook 可用并已启用" if discord_enabled() else "Webhook 可用但当前停用",
            }
        except BridgeError as exc:
            checks["discord"] = {"ok": False, "detail": str(exc)}
    else:
        checks["discord"] = {"ok": False, "detail": discord_error or "未配置（可选）"}
    label = LAUNCH_AGENT_LABEL
    agent = Path.home() / "Library/LaunchAgents" / f"{label}.plist"
    loaded = subprocess.run(
        ["/bin/launchctl", "print", f"gui/{os.getuid()}/{label}"],
        text=True,
        capture_output=True,
    )
    legacy_agents = [
        legacy
        for legacy in LEGACY_LAUNCH_AGENT_LABELS
        if (Path.home() / "Library/LaunchAgents" / f"{legacy}.plist").exists()
    ]
    checks["launchAgent"] = {
        "ok": agent.exists() and loaded.returncode == 0,
        "detail": (
            "已安装并加载；设置页关闭后由后台服务接管"
            if agent.exists() and loaded.returncode == 0
            else "配置文件存在但服务未加载，请重新安装"
            if agent.exists()
            else "检测到旧版常驻任务；重新安装或 reset 会自动清理"
            if legacy_agents
            else "未安装（可选）"
        ),
    }
    return checks


def replyable_sms_recipient(value: str) -> str | None:
    """Normalize only a phone/short-code destination; email/iMessage is excluded."""
    candidate = re.sub(r"[\s().-]", "", value)
    if re.fullmatch(r"\+?[1-9]\d{4,19}", candidate):
        return candidate
    return None


def valid_sms_reply_text(value: str) -> str | None:
    reply_text = value.strip()
    if not reply_text or len(reply_text) > MAX_SMS_REPLY_LENGTH or "\x1f" in reply_text or "\x00" in reply_text:
        return None
    return reply_text


def send_sms_reply(recipient: str, reply_text: str) -> None:
    """Ask the local Messages app to send one SMS without exposing text in argv/logs."""
    normalized = replyable_sms_recipient(recipient)
    if not normalized:
        raise BridgeError("这条通知的发件人不是可回复的短信号码。")
    reply_text = valid_sms_reply_text(reply_text)
    if reply_text is None:
        raise BridgeError(f"短信回复必须是 1–{MAX_SMS_REPLY_LENGTH} 个字符的纯文本。")

    # Keep the recipient and reply out of command arguments and process output.
    # The temporary file lives in the owner-only state directory and is removed
    # immediately after Messages has read it.
    payload_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=DATA_DIR, delete=False) as payload:
            payload_path = Path(payload.name)
            os.chmod(payload_path, 0o600)
            payload.write(normalized + "\x1f" + reply_text)
        script = '''on run argv
    set payloadText to read (POSIX file (item 1 of argv)) as «class utf8»
    set AppleScript's text item delimiters to character id 31
    set recipient to text item 1 of payloadText
    set replyText to text item 2 of payloadText
    tell application "Messages"
        set smsService to first service whose service type is SMS
        set smsBuddy to buddy recipient of smsService
        send replyText to smsBuddy
    end tell
end run'''
        result = subprocess.run(
            ["/usr/bin/osascript", "-l", "AppleScript", "-e", script, str(payload_path)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BridgeError("无法调用 macOS「信息」发送短信；请确认本机可正常发送短信。") from exc
    finally:
        if payload_path:
            payload_path.unlink(missing_ok=True)
    if result.returncode:
        # AppleScript diagnostics can include user content, so do not surface it.
        raise BridgeError("短信未发送。请打开「信息」确认已登录，并在系统设置中允许 SMS Bridge 自动化控制「信息」。")


def process_bot_updates(token: str) -> None:
    offset = int(STATE.get("telegram_update_offset") or "0")
    updates = telegram(token, "getUpdates", {"offset": offset, "timeout": 0}).get("result", [])
    for update in updates:
        with AUTHORIZATION_LOCK:
            if STOP.is_set():
                return
            next_offset = str(int(update["update_id"]) + 1)
            message = update.get("message") or {}
            chat, text = message.get("chat") or {}, str(message.get("text") or "")
            chat_id = str(chat.get("id") or "")
            # Never pair a group/channel, even if its link token leaks.
            if text.startswith("/start ") and chat.get("type") == "private" and pairing_valid(text.split(maxsplit=1)[1]):
                STATE.set("paired_chat_id", chat_id)
                STATE.set("paired_chat_name", str(chat.get("first_name") or chat.get("username") or "Telegram 私聊"))
                STATE.delete("pairing_token_hash")
                STATE.delete("pairing_expires_at")
                send_telegram(token, chat_id, "✅ <b>SMS Bridge 已配对</b>\n此私聊现在可以安全接收验证码通知。")
            elif text.split("@", 1)[0] == "/status" and chat_id == STATE.get("paired_chat_id"):
                send_telegram(token, chat_id, "✅ <b>SMS Bridge 正在运行</b>\n此私聊已配对。")
            elif text.split("@", 1)[0] == "/unpair" and chat_id == STATE.get("paired_chat_id"):
                unpair()
                send_telegram(token, chat_id, "🔓 已解除配对。需要重新配对才能接收验证码。")
            elif chat.get("type") == "private" and chat_id == STATE.get("paired_chat_id") and text.strip():
                quoted = message.get("reply_to_message") or {}
                quoted_id = quoted.get("message_id")
                if not isinstance(quoted_id, int):
                    send_telegram(token, chat_id, "请引用一条 SMS Bridge 通知后，再输入要发送的短信内容。")
                elif valid_sms_reply_text(text) is None:
                    send_telegram(token, chat_id, f"短信回复必须是 1–{MAX_SMS_REPLY_LENGTH} 个字符的纯文本。")
                else:
                    recipient = STATE.take_reply_target(quoted_id)
                    if not recipient:
                        send_telegram(token, chat_id, "该通知不能再回复：它可能已过期、不是短信通知，或已经使用过。")
                    else:
                        # Consume the target before confirmation: Telegram can retry
                        # an update after a network fault, but an SMS must never send twice.
                        send_sms_reply(recipient, text)
                        STATE.set("telegram_update_offset", next_offset)
                        try:
                            send_telegram(token, chat_id, "✅ 短信已交给 macOS「信息」发送。")
                        except BridgeError:
                            pass
                        continue
            # Store only after the update was fully handled; transient send failures retry.
            STATE.set("telegram_update_offset", next_offset)


def fetch_messages(after: int) -> list[sqlite3.Row]:
    try:
        with sqlite3.connect(f"file:{MESSAGES_DB}?mode=ro", uri=True, timeout=5) as db:
            db.row_factory = sqlite3.Row
            return db.execute("""SELECT m.ROWID AS rowid,m.text,m.attributedBody,m.date,COALESCE(h.id,'') AS sender
                FROM message m LEFT JOIN handle h ON h.ROWID=m.handle_id
                WHERE m.ROWID>? AND m.is_from_me=0
                  AND (m.text IS NOT NULL OR m.attributedBody IS NOT NULL)
                ORDER BY m.ROWID""", (after,)).fetchall()
    except (OSError, sqlite3.Error) as exc:
        raise MessagesAccessError(
            "无法读取 Messages 数据库；请检查“信息”同步和完全磁盘访问权限。"
        ) from exc


def latest_rowid() -> int:
    try:
        with sqlite3.connect(f"file:{MESSAGES_DB}?mode=ro", uri=True, timeout=5) as db:
            return int(db.execute("SELECT COALESCE(MAX(ROWID),0) FROM message").fetchone()[0])
    except (OSError, sqlite3.Error) as exc:
        raise MessagesAccessError(
            "无法读取 Messages 数据库；请检查“信息”同步和完全磁盘访问权限。"
        ) from exc


def decode_attributed_body(blob: object) -> str | None:
    """Decode the NSString payload used by modern Messages typedstreams."""
    if not isinstance(blob, bytes) or not blob or len(blob) > MAX_ATTRIBUTED_BODY_BYTES:
        return None
    marker = b"NSString"
    cursor = blob.find(marker)
    if cursor < 0:
        return None
    cursor += len(marker)
    # Observed NSAttributedString archives encode a five-byte object reference
    # before the typed integer containing the UTF-8 byte length.
    if cursor + 6 > len(blob):
        return None
    prefix = blob[cursor:cursor + 5]
    if not (
        prefix[0] == 0x01
        and prefix[2] == 0x84
        and prefix[3] == 0x01
        and prefix[4] == 0x2B
    ):
        return None
    cursor += 5
    lead = blob[cursor]
    cursor += 1
    if lead <= 0x7F:
        length = lead
    elif lead == 0x81 and cursor + 2 <= len(blob):
        length = int.from_bytes(blob[cursor:cursor + 2], "little")
        cursor += 2
    elif lead == 0x82 and cursor + 4 <= len(blob):
        length = int.from_bytes(blob[cursor:cursor + 4], "little")
        cursor += 4
    elif lead == 0x83 and cursor + 8 <= len(blob):
        length = int.from_bytes(blob[cursor:cursor + 8], "little")
        cursor += 8
    else:
        return None
    if length <= 0 or length > MAX_ATTRIBUTED_BODY_BYTES or cursor + length > len(blob):
        return None
    try:
        return blob[cursor:cursor + length].decode("utf-8")
    except UnicodeDecodeError:
        return None


def message_text(message: sqlite3.Row) -> str | None:
    value = message["text"]
    if isinstance(value, str) and value:
        return value
    return decode_attributed_body(message["attributedBody"])


def parse_otp(text: str, *, allow_compact: bool = False) -> str | None:
    # Pickup messages often contain both a pickup code and a tracking-number
    # suffix. Prefer an explicitly labelled or "凭 … 到" pickup code so the
    # unrelated suffix is never copied.
    pickup_match = PICKUP_EXPLICIT_RE.search(text)
    if not pickup_match and PICKUP_CONTEXT_RE.search(text):
        pickup_match = PICKUP_VOUCHER_RE.search(text)
    if pickup_match:
        return pickup_match.group(1)

    matches = list(CODE_RE.finditer(text))
    if not matches:
        return None
    if KEYWORD_RE.search(text):
        return re.sub(r"[\s-]", "", matches[0].group(0))
    if not allow_compact:
        return None

    compact = text.strip()
    match = matches[0]
    non_code = compact[:match.start()] + compact[match.end():]
    is_safe_compact_shape = (
        len(compact) <= 32
        and len(matches) == 1
        and (match.start() == 0 or match.end() == len(compact))
        and not re.search(r"[A-Za-z]", non_code)
        and not re.search(r"https?://|www\.", compact, re.I)
        and not SHORT_CODE_BLOCKLIST_RE.search(compact)
    )
    return re.sub(r"[\s-]", "", match.group(0)) if is_safe_compact_shape else None


def service_name(text: str) -> str:
    for name, pattern in (
        ("Google", r"\bgoogle\b"),
        ("Apple", r"\bapple\b|apple id"),
        ("OpenAI", r"\bopenai\b|chatgpt"),
        ("Microsoft", r"\bmicrosoft\b"),
        ("哔哩哔哩", r"哔哩哔哩|bilibili"),
    ):
        if re.search(pattern, text, re.I): return name
    return "验证码"


def code_label(text: str) -> str:
    return "取件码" if PICKUP_CONTEXT_RE.search(text) else "验证码"


def format_code(code: str) -> str:
    # Keep the visual code contiguous. Telegram overlays its own copy icon on
    # <pre> blocks on some mobile clients, which can cover a spaced final digit.
    return code


def message_time_label(raw_date: object | None) -> str:
    """Convert Apple's 2001 epoch (usually nanoseconds) to local HH:MM."""
    if raw_date is None:
        return datetime.now().astimezone().strftime("%H:%M")
    try:
        seconds = float(raw_date)
        if abs(seconds) > 10_000_000_000:
            seconds /= 1_000_000_000
        return (APPLE_MESSAGES_EPOCH + timedelta(seconds=seconds)).astimezone().strftime("%H:%M")
    except (TypeError, ValueError, OverflowError):
        return datetime.now().astimezone().strftime("%H:%M")


def preview_enabled() -> bool:
    return STATE.get("notification_include_preview") == "1"


def set_preview_enabled(enabled: bool) -> None:
    STATE.set("notification_include_preview", "1" if enabled else "0")


def forward_mode() -> str:
    value = STATE.get("forward_mode") or "strict"
    return value if value in FORWARD_MODES else "strict"


def set_forward_mode(value: str) -> None:
    if value not in FORWARD_MODES:
        raise BridgeError("转发规则无效。")
    STATE.set("forward_mode", value)


@dataclass(frozen=True)
class OutboundNotification:
    """Provider-neutral notification data; secrets and message text are not persisted."""

    label: str
    service: str
    sender: str
    received_at: str
    code: str | None = None
    original: str | None = None
    test: bool = False


def build_notification(
    text: str,
    sender: str,
    *,
    received_at: str | None = None,
    test: bool = False,
    code: str | None = None,
    full_message: bool = False,
) -> OutboundNotification:
    code = code or (None if full_message else parse_otp(text))
    if not code and not full_message:
        raise BridgeError("消息中未找到验证码。")
    return OutboundNotification(
        label="收到新消息" if full_message else code_label(text),
        service="" if full_message else service_name(text),
        sender=(sender or "未知发件人")[:256],
        received_at=received_at or datetime.now().astimezone().strftime("%H:%M"),
        code=code,
        original=text[:MAX_PREVIEW_LENGTH] if full_message or preview_enabled() else None,
        test=test,
    )


def render_telegram_notification(notification: OutboundNotification) -> str:
    safe_sender = html.escape(notification.sender)
    time_label = html.escape(notification.received_at)
    icon = "🧪" if notification.test else "✉️"
    service_suffix = (
        ""
        if notification.service in ("", "验证码")
        else f" · {html.escape(notification.service)}"
    )
    if notification.code:
        body = (
            f"{icon}  <b>{html.escape(notification.label)}{service_suffix}</b>\n\n"
            f"🔐  <b>{html.escape(format_code(notification.code))}</b>\n\n\n"
            f"<b>来自</b>  {safe_sender}\n"
            f"<b>时间</b>  <code>{time_label}</code>"
        )
    else:
        body = (
            f"{icon}  <b>{safe_sender}</b>  ·  <code>{time_label}</code>\n\n"
            f"<b>{html.escape(notification.label)}</b>"
        )
    if notification.test:
        body += "\n\n<i>模拟通知 · 不是真实短信</i>"
    if notification.original is not None:
        preview = html.escape(notification.original)
        body += "\n\n<b>短信原文</b>（点击展开）\n<blockquote expandable>" + preview + "</blockquote>"
    return body


def discord_escape(value: str) -> str:
    """Escape Discord Markdown while allowed_mentions blocks actual pings."""
    return re.sub(r"([\\`*_{}\[\]()<>#+.!|>~-])", r"\\\1", value)


def render_discord_notification(notification: OutboundNotification) -> str:
    icon = "🧪" if notification.test else "✉️"
    service_suffix = (
        ""
        if notification.service in ("", "验证码")
        else f" · {discord_escape(notification.service)}"
    )
    if notification.code:
        body = (
            f"{icon} **{discord_escape(notification.label)}{service_suffix}**\n\n"
            f"# 🔐 {discord_escape(format_code(notification.code))}\n\n"
            f"**来自**  {discord_escape(notification.sender)}\n"
            f"**时间**  `{discord_escape(notification.received_at)}`"
        )
    else:
        body = (
            f"{icon} **{discord_escape(notification.label)}**\n\n"
            f"**来自**  {discord_escape(notification.sender)}\n"
            f"**时间**  `{discord_escape(notification.received_at)}`"
        )
    if notification.test:
        body += "\n\n*模拟通知 · 不是真实短信*"
    if notification.original is not None:
        remaining = max(0, MAX_DISCORD_MESSAGE_LENGTH - len(body) - 20)
        escaped = discord_escape(notification.original)[:remaining].rstrip("\\")
        quoted = "\n".join("> " + line for line in escaped.splitlines() or [""])
        body += "\n\n**短信原文**\n" + quoted
    if len(body) > MAX_DISCORD_MESSAGE_LENGTH:
        raise BridgeError("Discord 通知内容过长，已安全拒绝发送。")
    return body


def format_notification(
    text: str,
    sender: str,
    *,
    received_at: str | None = None,
    test: bool = False,
    code: str | None = None,
) -> str:
    """Backward-compatible Telegram renderer used by the public helpers/tests."""
    return render_telegram_notification(
        build_notification(
            text,
            sender,
            received_at=received_at,
            test=test,
            code=code,
        )
    )


def format_message_notification(
    text: str,
    sender: str,
    *,
    received_at: str | None = None,
) -> str:
    return render_telegram_notification(
        build_notification(
            text,
            sender,
            received_at=received_at,
            full_message=True,
        )
    )


class NotificationProvider:
    provider_id = ""
    display_name = ""

    def send(self, notification: OutboundNotification) -> None:
        raise NotImplementedError


@dataclass(frozen=True)
class TelegramProvider(NotificationProvider):
    token: str
    chat_id: str
    provider_id = "telegram"
    display_name = "Telegram"

    def send(self, notification: OutboundNotification) -> int | None:
        response = send_telegram(
            self.token,
            self.chat_id,
            render_telegram_notification(notification),
            copy_text=notification.code,
        )
        message_id = response.get("result", {}).get("message_id") if isinstance(response, dict) else None
        return message_id if isinstance(message_id, int) else None


@dataclass(frozen=True)
class DiscordWebhookProvider(NotificationProvider):
    webhook_url: str
    provider_id = "discord"
    display_name = "Discord"

    def send(self, notification: OutboundNotification) -> None:
        discord_webhook_request(
            self.webhook_url,
            {
                "content": render_discord_notification(notification),
                "username": APP_NAME,
                "allowed_mentions": {"parse": []},
            },
        )


def active_notification_providers() -> list[NotificationProvider]:
    providers: list[NotificationProvider] = []
    token = keychain_token()
    chat_id = STATE.get("paired_chat_id")
    if token and chat_id:
        providers.append(TelegramProvider(token, chat_id))
    if discord_enabled():
        webhook = discord_webhook_url()
        if not webhook:
            raise BridgeError("Discord 已启用但 Webhook URL 不存在，请重新配置或停用。")
        providers.append(DiscordWebhookProvider(webhook))
    return providers


def provider_delivery_key(provider_id: str) -> str:
    return f"provider_cursor_{provider_id}"


def send_test_notification(provider_id: str | None = None) -> list[str]:
    notification = build_notification(
        "Your Google verification code is 482913.",
        "+1 555 010 1234",
        test=True,
    )
    if provider_id == "telegram":
        token, chat = keychain_token(), STATE.get("paired_chat_id")
        providers: list[NotificationProvider] = (
            [TelegramProvider(token, chat)] if token and chat else []
        )
    elif provider_id == "discord":
        webhook = discord_webhook_url()
        providers = [DiscordWebhookProvider(webhook)] if webhook else []
    elif provider_id in (None, "all"):
        providers = active_notification_providers()
    else:
        raise BridgeError("未知的通知渠道。")
    if not providers:
        raise BridgeError("所选通知渠道尚未完成配置。")
    delivered: list[str] = []
    with AUTHORIZATION_LOCK:
        for provider in providers:
            provider.send(notification)
            delivered.append(provider.provider_id)
    return delivered


def bridge_loop() -> None:
    retry_delay = 0
    while not STOP.wait(retry_delay):
        try:
            token = keychain_token()
            if token: process_bot_updates(token)
            if STATE.get("last_rowid") is None:
                # Start at "now": installation must never dump historical messages.
                STATE.set("last_rowid", str(latest_rowid()))
            cursor = int(STATE.get("last_rowid") or "0")
            messages = fetch_messages(cursor)
            STATE.set("messages_readable", "1")
            STATE.set("messages_checked_at", str(int(time.time())))
            mode = forward_mode()
            for message in messages:
                rowid = int(message["rowid"])
                text = message_text(message)
                if not text:
                    STATE.set("last_rowid", str(rowid))
                    continue
                code = parse_otp(text, allow_compact=mode in ("smart", "all"))
                should_forward = bool(code) or mode == "all"
                if should_forward:
                    with AUTHORIZATION_LOCK:
                        if STOP.is_set():
                            return
                        providers = active_notification_providers()
                        received_at = message_time_label(message["date"])
                        notification = build_notification(
                            text,
                            str(message["sender"]),
                            received_at=received_at,
                            code=code,
                            full_message=not bool(code),
                        )
                        for provider in providers:
                            delivery_key = provider_delivery_key(provider.provider_id)
                            if int(STATE.get(delivery_key) or "0") >= rowid:
                                continue
                            provider_result = provider.send(notification)
                            if isinstance(provider, TelegramProvider) and isinstance(provider_result, int):
                                recipient = replyable_sms_recipient(str(message["sender"]))
                                if recipient:
                                    STATE.save_reply_target(provider_result, recipient)
                            STATE.set(delivery_key, str(rowid))
                            STATE.set(
                                f"last_forwarded_at_{provider.provider_id}",
                                str(int(time.time())),
                            )
                        if providers:
                            STATE.set("last_forwarded_at", str(int(time.time())))
                STATE.set("last_rowid", str(rowid))
            STATE.delete("last_error")
            retry_delay = POLL_SECONDS
        except (MessagesAccessError, sqlite3.Error) as exc:
            STATE.set("messages_readable", "0")
            STATE.set("messages_checked_at", str(int(time.time())))
            STATE.set("last_error", str(exc)[:180])
            retry_delay = min(max(POLL_SECONDS, retry_delay * 2), 300)
        except (OSError, BridgeError, ValueError) as exc:
            STATE.set("last_error", str(exc)[:180])
            retry_delay = min(max(POLL_SECONDS, retry_delay * 2), 300)
        except Exception:
            # Keep the relay alive without leaking private message content into logs/state.
            STATE.set("last_error", "内部错误；请运行 `sms_bridge.py doctor` 进行诊断。")
            retry_delay = min(max(POLL_SECONDS, retry_delay * 2), 300)


def messages_access_status() -> tuple[bool, str]:
    """Combine direct UI access with a recent result from the background relay."""
    direct = MESSAGES_DB.exists() and os.access(MESSAGES_DB, os.R_OK)
    checked_at = int(STATE.get("messages_checked_at") or "0")
    recent_background = (
        STATE.get("messages_readable") == "1"
        and checked_at >= int(time.time()) - max(30, POLL_SECONDS * 4)
    )
    if direct:
        return True, "Messages 数据库可读取"
    if recent_background:
        return True, "后台服务已验证 Messages 数据库可读取"
    return False, "无法读取 Messages 数据库；请检查同步、专用运行时权限和后台服务"


def status() -> dict:
    pair_expires = int(STATE.get("pairing_expires_at") or "0")
    paired = bool(STATE.get("paired_chat_id"))
    try:
        configured = bool(keychain_token())
        keychain_error = ""
    except BridgeError as exc:
        configured, keychain_error = False, str(exc)
    try:
        discord_configured = bool(discord_webhook_url())
        discord_error = ""
    except BridgeError as exc:
        discord_configured, discord_error = False, str(exc)
    messages_readable, _messages_detail = messages_access_status()
    discord_active = discord_configured and discord_enabled()
    return {
        "configured": configured,
        "messagesReadable": messages_readable,
        "paired": paired,
        "pairedName": STATE.get("paired_chat_name") or ("Telegram 私聊" if paired else ""),
        "pairingActive": pair_expires > time.time(),
        "pairingRemaining": max(0, pair_expires - int(time.time())),
        "showOriginal": preview_enabled(),
        "forwardMode": forward_mode(),
        "discordConfigured": discord_configured,
        "discordEnabled": discord_active,
        "hasActiveProvider": bool((configured and paired) or discord_active),
        "providers": {
            "telegram": {
                "configured": configured,
                "enabled": paired,
                "ready": bool(configured and paired),
            },
            "discord": {
                "configured": discord_configured,
                "enabled": discord_active,
                "ready": discord_active,
            },
        },
        "lastError": keychain_error or discord_error or STATE.get("last_error") or "",
        "lastForwardedAt": int(STATE.get("last_forwarded_at") or "0"),
    }


PAGE = render_page(CSRF_TOKEN)


class Handler(BaseHTTPRequestHandler):
    server_version = "SMSBridge"
    sys_version = ""

    def log_message(self, *_args: object) -> None: pass
    def local_origin(self) -> str | None:
        """Return the one valid origin, rejecting DNS-rebinding Host headers."""
        expected_host = f"127.0.0.1:{self.server.server_port}"
        if self.headers.get("Host", "") != expected_host:
            return None
        return f"http://{expected_host}"
    def security_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.send_header("Content-Security-Policy", f"default-src 'none'; connect-src 'self'; img-src data:; style-src 'unsafe-inline'; script-src 'nonce-{CSRF_TOKEN}'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
    def respond(self, code: int, value: dict) -> None:
        raw = json.dumps(value, ensure_ascii=False).encode(); self.send_response(code); self.send_header("Content-Type", "application/json; charset=utf-8"); self.security_headers(); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_GET(self) -> None:
        if self.local_origin() is None:
            self.respond(HTTPStatus.BAD_REQUEST, {"error": "无效的本机 Host。"})
            return
        if self.path == "/":
            raw = PAGE.encode(); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.security_headers(); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
        elif self.path == "/api/status": self.respond(200, status())
        elif self.path == "/api/doctor": self.respond(200, doctor())
        else: self.respond(404, {"error": "未找到"})
    def do_POST(self) -> None:
        try:
            expected_origin = self.local_origin()
            if expected_origin is None:
                self.respond(HTTPStatus.BAD_REQUEST, {"error": "无效的本机 Host。"})
                return
            supplied_csrf = self.headers.get("X-SMS-Bridge-CSRF", "")
            if self.headers.get("Origin") != expected_origin or not secrets.compare_digest(supplied_csrf, CSRF_TOKEN):
                self.respond(HTTPStatus.FORBIDDEN, {"error": "本机设置页拒绝了跨站请求。"})
                return
            if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
                self.respond(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "请求格式无效。"})
                return
            size = int(self.headers.get("Content-Length", "0"))
            if size < 0 or size > MAX_REQUEST_BYTES:
                self.respond(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "请求过大。"})
                return
            data = json.loads(self.rfile.read(size) or b"{}")
            if self.path == "/api/token":
                value = str(data.get("token", "")).strip()
                if len(value) < 20 or ":" not in value: raise RuntimeError("请输入完整的 Bot Token。")
                configure_bot_token(value); self.respond(200, {"ok": True})
            elif self.path == "/api/discord":
                value = str(data.get("webhookUrl", "")).strip()
                configure_discord_webhook(value)
                self.respond(200, {"ok": True})
            elif self.path == "/api/pair": self.respond(200, {"url": create_pairing()})
            elif self.path == "/api/test":
                delivered = send_test_notification(str(data.get("provider") or "all"))
                self.respond(200, {"ok": True, "providers": delivered})
            elif self.path == "/api/discord/remove":
                with AUTHORIZATION_LOCK:
                    delete_discord_webhook_url()
                self.respond(200, {"ok": True})
            elif self.path == "/api/settings":
                if "showOriginal" in data:
                    value = data["showOriginal"]
                    if not isinstance(value, bool):
                        raise BridgeError("showOriginal 必须是 true 或 false。")
                    set_preview_enabled(value)
                if "forwardMode" in data:
                    set_forward_mode(str(data["forwardMode"]))
                if "discordEnabled" in data:
                    value = data["discordEnabled"]
                    if not isinstance(value, bool):
                        raise BridgeError("discordEnabled 必须是 true 或 false。")
                    set_discord_enabled(value)
                if not {"showOriginal", "forwardMode", "discordEnabled"}.intersection(data):
                    raise BridgeError("没有可更新的设置。")
                self.respond(200, {
                    "ok": True,
                    "showOriginal": preview_enabled(),
                    "forwardMode": forward_mode(),
                    "discordEnabled": discord_enabled(),
                })
            elif self.path == "/api/unpair": unpair(); self.respond(200, {"ok": True})
            elif self.path == "/api/install":
                install_launch_agent()
                self.respond(200, {"ok": True})
                # Release the single-instance lock so launchd can take over cleanly.
                threading.Timer(2, STOP.set).start()
            elif self.path == "/api/reset":
                reset_local_configuration()
                self.respond(200, {"ok": True})
                threading.Timer(2, STOP.set).start()
            else: self.respond(404, {"error": "未找到"})
        except (RuntimeError, ValueError) as exc: self.respond(400, {"error": str(exc)})
        except Exception: self.respond(500, {"error": "发生未知错误，请查看本机诊断信息。"})


def serve(open_browser: bool) -> None:
    relay_instance: SingleInstance | None = None
    try:
        relay_instance = SingleInstance()
        relay_instance.__enter__()
    except BridgeError:
        # A LaunchAgent/CLI relay already owns the engine; the UI can still manage it.
        relay_instance = None
    if relay_instance:
        thread = threading.Thread(target=bridge_loop, daemon=True)
        thread.start()
    server = None
    for port in range(8765, 8776):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    if server is None:
        if relay_instance:
            relay_instance.__exit__()
        raise BridgeError("本机设置页端口不可用，请关闭其他 SMS Bridge 窗口后重试。")
    url = f"http://127.0.0.1:{server.server_port}"
    STATE.set("ui_port", str(server.server_port))
    server.timeout = 1
    print(f"{APP_NAME} 正在运行：{url}", flush=True)
    if open_browser: webbrowser.open(url)
    try:
        while not STOP.is_set():
            server.handle_request()
    finally:
        STATE.delete("ui_port")
        server.server_close()
        if relay_instance:
            relay_instance.__exit__()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="本机 iPhone 验证码 → Telegram / Discord 通知工具",
        epilog="不带命令时启动本机设置页；所有敏感配置只保留在本机。",
    )
    commands = parser.add_subparsers(dest="command", metavar="命令")
    ui = commands.add_parser("ui", help="启动本机设置页（默认）")
    ui.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    commands.add_parser("init", help="在终端隐藏输入并安全保存 Bot Token")
    commands.add_parser("run", help="仅运行转发服务，不启动设置页")
    commands.add_parser("pair", help="生成 10 分钟有效的一次性 Telegram 配对链接")
    commands.add_parser("status", help="显示不含敏感信息的本机状态")
    commands.add_parser("doctor", help="检查权限、钥匙串、通知渠道和常驻服务")
    test_command = commands.add_parser("test", help="向已启用渠道发送测试通知")
    test_command.add_argument(
        "--provider",
        choices=("all", "telegram", "discord"),
        default="all",
        help="测试全部、Telegram 或 Discord（默认：all）",
    )
    commands.add_parser("unpair", help="解除当前 Telegram 私聊授权")
    config = commands.add_parser("config", help="查看或修改通知显示选项")
    config.add_argument("--show-original", choices=("on", "off"), help="是否在所有已启用渠道中附带完整原文")
    config.add_argument("--mode", choices=FORWARD_MODES, help="转发规则：strict、smart 或 all")
    discord_command = commands.add_parser("discord", help="配置 Discord Webhook 通知")
    discord_actions = discord_command.add_subparsers(dest="discord_action", metavar="操作")
    discord_actions.add_parser("set", help="隐藏输入并保存 Webhook URL")
    discord_actions.add_parser("test", help="发送一条 Discord 模拟通知")
    discord_actions.add_parser("enable", help="启用已保存的 Discord Webhook")
    discord_actions.add_parser("disable", help="暂时停用 Discord Webhook")
    discord_actions.add_parser("remove", help="删除 Discord Webhook 凭据")
    discord_actions.add_parser("status", help="显示 Discord 脱敏状态")
    commands.add_parser("install", help="安装当前用户登录后自动启动服务")
    commands.add_parser("uninstall", help="移除当前用户的自动启动服务")
    reset = commands.add_parser("reset", help="删除渠道凭据、配对、状态和常驻服务")
    reset.add_argument("--yes", action="store_true", help="确认永久删除本机 SMS Bridge 配置")
    args = parser.parse_args()
    signal.signal(signal.SIGINT, stop_handler); signal.signal(signal.SIGTERM, stop_handler)
    command = args.command or "ui"
    if command == "ui":
        ui_instance = SingleInstance(UI_LOCK_FILE, "本机设置页已在运行。")
        try:
            ui_instance.__enter__()
        except BridgeError:
            existing_port = STATE.get("ui_port") or ""
            if existing_port.isdigit() and 1 <= int(existing_port) <= 65535:
                existing_url = f"http://127.0.0.1:{existing_port}"
                if not getattr(args, "no_browser", False):
                    webbrowser.open(existing_url)
                print(f"{APP_NAME} 设置页已在运行：{existing_url}")
                return
            raise
        try:
            serve(not getattr(args, "no_browser", False))
        finally:
            ui_instance.__exit__()
    elif command == "init":
        token = getpass.getpass("Telegram Bot Token（输入不会显示）: ").strip()
        configure_bot_token(token)
        print("Bot Token 已安全保存到 macOS 钥匙串；旧配对（如有）已解除。")
    elif command == "run":
        with SingleInstance():
            print(f"{APP_NAME} 正在后台监听；按 Ctrl-C 停止。", flush=True)
            bridge_loop()
    elif command == "pair":
        print(create_pairing())
    elif command == "status":
        print(json.dumps(status(), ensure_ascii=False, indent=2))
    elif command == "doctor":
        print(json.dumps(doctor(), ensure_ascii=False, indent=2))
    elif command == "test":
        delivered = send_test_notification(args.provider)
        print("测试通知已发送：" + "、".join(delivered))
    elif command == "unpair":
        unpair(); print("已解除 Telegram 配对。")
    elif command == "config":
        if args.show_original:
            set_preview_enabled(args.show_original == "on")
        if args.mode:
            set_forward_mode(args.mode)
        print(json.dumps({
            "showOriginal": preview_enabled(),
            "forwardMode": forward_mode(),
        }, ensure_ascii=False, indent=2))
    elif command == "discord":
        action = args.discord_action or "status"
        if action == "set":
            webhook = getpass.getpass("Discord Webhook URL（输入不会显示）: ").strip()
            configure_discord_webhook(webhook)
            print("Discord Webhook 已验证、保存到 macOS 钥匙串并启用。")
        elif action == "test":
            send_test_notification("discord")
            print("Discord 测试通知已发送。")
        elif action == "enable":
            set_discord_enabled(True)
            print("Discord Webhook 已启用；只转发之后收到的新消息。")
        elif action == "disable":
            set_discord_enabled(False)
            print("Discord Webhook 已停用，凭据仍保存在钥匙串。")
        elif action == "remove":
            with AUTHORIZATION_LOCK:
                delete_discord_webhook_url()
            print("Discord Webhook 已从钥匙串删除。")
        elif action == "status":
            configured = bool(discord_webhook_url())
            print(json.dumps({
                "configured": configured,
                "enabled": configured and discord_enabled(),
            }, ensure_ascii=False, indent=2))
    elif command == "install":
        install_launch_agent(); print("已安装登录后自动启动服务。")
    elif command == "uninstall":
        uninstall_launch_agent(); print("已移除登录后自动启动服务。")
    elif command == "reset":
        if not args.yes:
            raise BridgeError("此操作会永久删除本机配置。确认后请重新运行：sms_bridge.py reset --yes")
        reset_local_configuration()
        print("已删除通知渠道凭据、Telegram 配对、本机状态、日志和常驻服务。")
        print("请另行撤销 Telegram Token、删除 Discord 服务端 Webhook，并移除专用 Python 的完全磁盘访问权限。")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except BridgeError as exc:
        print(f"SMS Bridge：{exc}", file=sys.stderr)
        sys.exit(1)
