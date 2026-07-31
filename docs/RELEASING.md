# Release Guide / 发布指南

## English

This project must not be released from a workstation that contains a live provider credential unless the release contents have been independently checked.

1. Start from a clean clone or clean working tree. Do not stage `.env`, SQLite state, logs, screenshots, or exported diagnostics.
2. Run:

   ```zsh
   python3 scripts/release_check.py
   git status --ignored
   ```

3. Run a secret scanner locally and confirm the CI gitleaks workflow will run. Review all matches manually; do not add broad allow rules for credentials.
4. Inspect the generated LaunchAgent definition with `python3 -c 'import sms_bridge; print(sms_bridge.launch_agent_plist())'`. It must not contain any provider credential, chat ID, pairing URL, or OTP. Confirm logs point to `~/Library/Application Support/SMS Bridge`, not the source tree.
5. Test the release on a clean macOS user account: onboarding, Full Disk Access denial/approval, `doctor`, pairing expiry, `/unpair`, temporary network failure, `install`, restart, and `uninstall`.
6. Update `CHANGELOG.md`, tag the exact commit, and attach checksums to any future binary artifacts. Do not publish a binary until its signing and notarization process is documented.
7. Before making the repository public, enable GitHub private vulnerability reporting and replace any repository-specific contact or URL placeholders.

If the token used during development was ever exposed in a chat, terminal capture, issue, commit, or screen recording, revoke it in @BotFather before public release.

## 中文

如果开发工作站中存在仍在使用的通知渠道凭据，未经独立检查不得直接从该工作站发布。

1. 从干净克隆或干净工作区开始。不要暂存 `.env`、SQLite 状态库、日志、截图或导出的诊断信息。
2. 运行：

   ```zsh
   python3 scripts/release_check.py
   git status --ignored
   ```

3. 本地运行 secret 扫描，并确认 CI 的 gitleaks 工作流会执行。人工复核所有命中，不要为凭据添加宽泛的忽略规则。
4. 用 `python3 -c 'import sms_bridge; print(sms_bridge.launch_agent_plist())'` 检查生成的 LaunchAgent。它不得包含 Bot Token、Discord Webhook URL、Chat ID、配对 URL 或验证码；日志路径应位于 `~/Library/Application Support/SMS Bridge`，而不是源码目录。
5. 在干净的 macOS 用户账户测试：引导流程、完全磁盘访问权限拒绝/授予、`doctor`、配对过期、`/unpair`、临时断网、`install`、重启和 `uninstall`。
6. 更新 `CHANGELOG.md`，标记精确提交；未来发布二进制时附带校验和。在记录签名与公证流程前，不要发布二进制包。
7. 仓库公开前启用 GitHub 私密漏洞报告，并补齐仓库专用的安全联系方式或 URL。

若开发期间的 Token 曾出现在聊天、终端录制、Issue、提交或屏幕录像中，请在公开发布前通过 @BotFather 撤销它。
