# Security Policy / 安全政策

## English

SMS Bridge processes authentication codes. Treat its host, Telegram Bot Token, paired chat, and local Messages database as sensitive assets.

### Supported versions

Only the latest version on the default branch is supported.

### Reporting a vulnerability

Do **not** open a public issue for a vulnerability involving OTP disclosure, token exposure, pairing bypass, local-server access, or message database access. Use the repository Security tab's private vulnerability report when available. Until that feature or a dedicated security contact is configured, contact the maintainer privately through the repository owner's verified profile. Include reproduction steps, impact, and a safe proof of concept; never include real tokens or OTPs.

### Security boundaries

- The project reads the local `~/Library/Messages/chat.db` only after the user grants macOS Full Disk Access.
- Strict OTP mode is the default. All-message mode deliberately sends ordinary SMS and iMessage text to Telegram and materially expands the disclosed data; enable it only after reviewing the paired destination.
- The only intentional outbound network destination is Telegram's Bot API.
- Telegram is a third party. A notification sent to it is processed by Telegram's infrastructure.
- The local setup page is loopback-only. Do not expose it through a tunnel, reverse proxy, port-forward, or remote desktop sharing session.
- A Bot Token is a credential. Store it at rest in Keychain, rotate it after exposure, and do not put it in source control. The running process necessarily holds one in-memory copy until it exits.

### Operator checklist

1. Use a dedicated Telegram bot and a private chat.
2. Keep macOS, Python, and the project updated.
3. Run `python3 sms_bridge.py doctor` after installation and after OS upgrades.
4. Use `/unpair` or `python3 sms_bridge.py unpair` before transferring or servicing a Mac.
5. Revoke a suspected leaked Bot Token with @BotFather, save the replacement token locally, and pair again.

## 中文

SMS Bridge 会处理验证码。请把运行它的 Mac、Telegram Bot Token、已配对聊天和本地信息数据库都视为敏感资产。

### 支持版本

仅默认分支上的最新版本受支持。

### 漏洞报告

涉及验证码泄露、Token 泄露、配对绕过、本地设置页访问或信息数据库访问的漏洞，**不要**创建公开 Issue。若仓库 Security 页面提供私密漏洞报告，请优先使用；在该功能或专用安全联系方式配置前，请通过仓库所有者已验证的私密联系方式报告。请提供复现步骤、影响和安全 PoC；不要附带真实 Token 或验证码。

### 安全边界

- 用户明确授予 macOS「完全磁盘访问权限」后，项目才会读取本机 `~/Library/Messages/chat.db`。
- 默认使用严格验证码规则。“所有收到的文本”会主动把普通短信和 iMessage 原文发送到 Telegram，显著扩大披露范围；只应在核对接收私聊并明确接受风险后启用。
- 唯一预期的出站网络目标是 Telegram Bot API。
- Telegram 是第三方服务；发送给它的通知会经由 Telegram 基础设施处理。
- 设置页只监听本机回环地址。不要将其暴露给隧道、反向代理、端口转发或远程桌面共享。
- Bot Token 是凭据：静态应保存在钥匙串中，泄露后立刻轮换，绝不提交到源码仓库。运行进程会在退出前保留一份必要的内存副本。

### 运营检查清单

1. 使用专用 Telegram Bot 和私聊。
2. 保持 macOS、Python 与项目更新。
3. 安装后及每次系统升级后运行 `python3 sms_bridge.py doctor`。
4. 转让、送修 Mac 前使用 `/unpair` 或 `python3 sms_bridge.py unpair`。
5. 怀疑 Token 泄露时，在 @BotFather 撤销它，保存新 Token 并重新配对。
