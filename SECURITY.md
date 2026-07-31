# Security Policy / 安全政策

## English

SMS Bridge processes authentication codes. Treat its host, provider credentials, destinations, and local Messages database as sensitive assets.

### Supported versions

Only the latest version on the default branch is supported.

### Reporting a vulnerability

Do **not** open a public issue for a vulnerability involving OTP disclosure, token exposure, pairing bypass, local-server access, or message database access. Use the repository Security tab's private vulnerability report when available. Until that feature or a dedicated security contact is configured, contact the maintainer privately through the repository owner's verified profile. Include reproduction steps, impact, and a safe proof of concept; never include real tokens or OTPs.

### Security boundaries

- The project reads the local `~/Library/Messages/chat.db` only after the user grants macOS Full Disk Access.
- Strict OTP mode is the default. All-message mode deliberately sends ordinary SMS and iMessage text to every enabled provider and materially expands the disclosed data.
- Intentional outbound targets are configured Telegram Bot API and canonical Discord Webhook endpoints.
- Telegram and Discord are third parties. A notification is processed by every enabled provider's infrastructure.
- The local setup page is loopback-only. Do not expose it through a tunnel, reverse proxy, port-forward, or remote desktop sharing session.
- Bot Tokens and Discord Webhook URLs are credentials. Store them at rest in Keychain, rotate/regenerate after exposure, and never put them in source control.

### Operator checklist

1. Use a dedicated Telegram bot/private chat and/or a Discord Webhook restricted to a private channel.
2. Keep macOS, Python, and the project updated.
3. Run `python3 sms_bridge.py doctor` after installation and after OS upgrades.
4. Use `/unpair` or `python3 sms_bridge.py unpair` before transferring or servicing a Mac.
5. Revoke a leaked Bot Token with @BotFather or regenerate a leaked Discord Webhook, then save the replacement locally.

## 中文

SMS Bridge 会处理验证码。请把运行它的 Mac、通知渠道凭据、接收目标和本地信息数据库都视为敏感资产。

### 支持版本

仅默认分支上的最新版本受支持。

### 漏洞报告

涉及验证码泄露、Token 泄露、配对绕过、本地设置页访问或信息数据库访问的漏洞，**不要**创建公开 Issue。若仓库 Security 页面提供私密漏洞报告，请优先使用；在该功能或专用安全联系方式配置前，请通过仓库所有者已验证的私密联系方式报告。请提供复现步骤、影响和安全 PoC；不要附带真实 Token 或验证码。

### 安全边界

- 用户明确授予 macOS「完全磁盘访问权限」后，项目才会读取本机 `~/Library/Messages/chat.db`。
- 默认使用严格验证码规则。“所有收到的文本”会主动把普通短信和 iMessage 原文发送到所有已启用渠道，显著扩大披露范围。
- 预期的出站网络目标仅包括已配置的 Telegram Bot API 和 Discord 官方 Webhook。
- Telegram 和 Discord 都是第三方服务；通知会经由所有启用渠道的基础设施处理。
- 设置页只监听本机回环地址。不要将其暴露给隧道、反向代理、端口转发或远程桌面共享。
- Bot Token 和 Discord Webhook URL 都是凭据：静态应保存在钥匙串中，泄露后立刻轮换或重新生成，绝不提交到源码仓库。

### 运营检查清单

1. 使用专用 Telegram Bot/私聊，和/或只指向 Discord 私密频道的 Webhook。
2. 保持 macOS、Python 与项目更新。
3. 安装后及每次系统升级后运行 `python3 sms_bridge.py doctor`。
4. 转让、送修 Mac 前使用 `/unpair` 或 `python3 sms_bridge.py unpair`。
5. Telegram Token 泄露时在 @BotFather 撤销；Discord Webhook 泄露时在频道设置中删除或重新生成。
