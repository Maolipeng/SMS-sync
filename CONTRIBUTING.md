# Contributing / 贡献指南

## English

Contributions are welcome, but privacy and safety outrank convenience. Do not add cloud storage, public listeners, group delivery, or message-history retention without an explicit threat-model update and security review.

Before opening a pull request:

```zsh
python3 -m unittest discover -s tests -v
python3 -m py_compile sms_bridge.py
```

Use synthetic, redacted message fixtures only. Never commit `.env`, `state.sqlite3`, logs, pairing links, Telegram Chat IDs, Bot Tokens, or screenshots containing OTPs. Keep user-visible errors free of SMS content and credentials.

## 中文

欢迎贡献，但隐私与安全优先于便利性。没有明确威胁建模更新和安全审查时，请不要加入云端存储、公开监听器、群组投递或短信历史留存。

提交 PR 前请运行上面的测试。只能使用合成、脱敏的消息样本；绝不能提交 `.env`、`state.sqlite3`、日志、配对链接、Telegram Chat ID、Bot Token 或含验证码的截图。面向用户的错误信息不得包含短信内容或凭据。
