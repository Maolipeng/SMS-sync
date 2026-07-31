# SMS Bridge

把同步到 Mac 的 iPhone 验证码，安全地发送到你自己的 Telegram 私聊或 Discord 私密频道。

SMS Bridge 是一个只在本机运行的开源工具：不需要 Docker、域名、服务器或编程知识，也不会开放公网端口。

```text
iPhone 收到验证码
      ↓  Apple「信息」同步
Mac mini（SMS Bridge）
      ↓  Telegram / Discord Provider
你的另一台设备
```

## 三步开始

### 1. 准备

- iPhone 与 Mac 使用同一个 Apple 账户，并在两端开启「信息」同步；
- 先确认 Mac 的「信息」App 已能看到 iPhone 收到的短信；
- 至少准备一个通知渠道：Telegram Bot，或 Discord 私密频道的 Incoming Webhook。

> Bot Token 和 Discord Webhook URL 都属于凭据。请不要发到群聊、截图或提交到 Git。若曾泄露，请立即撤销 Token 或重新生成 Webhook。凭据会保存到 macOS 钥匙串；`.env` 仅供开发测试，默认不会被读取。

### 2. 启动本机设置页

下载并解压项目后，直接双击：

```text
SMS Bridge.command
```

也可以在 iTerm 或 Terminal 进入项目目录并执行 `python3 sms_bridge.py`。浏览器会自动打开 `http://127.0.0.1:8765`。页面会引导你：

1. Telegram：保存 Bot Token并完成一次性私聊配对；
2. Discord：粘贴私密频道的 Webhook URL并验证；
3. 两者可以只启用一个，也可以同时启用；
4. 点击“发送测试通知”。

测试成功后，点击“安装后台常驻”，设置页会关闭并由当前用户的 LaunchAgent 接管；启动配置中不包含任何渠道凭据。

### 3. 如提示权限不足

前往：**系统设置 → 隐私与安全性 → 完全磁盘访问权限**。双击启动器会在 `~/Library/Application Support/SMS Bridge/runtime` 创建仅供本工具使用的 Python 运行时；请添加 `runtime/bin/python3.10`（小版本号以实际为准），而不是给日常使用的全局 Python 扩权。然后彻底退出 SMS Bridge 并重新启动。

macOS 可能仍不允许由未授权 Terminal 直接启动的设置页读取信息数据库，这是“责任进程”机制导致的正常现象。无需给整个 Terminal 扩权：完成 Token 与配对后安装后台常驻，LaunchAgent 会使用已授权的 `python3.10` 实际路径并回写验证结果；重新打开设置页即可看到后台验证状态。

## 默认隐私规则

- 仅监听本机的 `127.0.0.1`，没有公网入口；
- 未授权通知渠道时绝不转发；Telegram 只允许一个私聊，Discord 只使用用户保存的频道 Webhook；
- 配对链接 10 分钟有效且只能使用一次；
- 新安装默认使用“严格验证码”规则；可切换为“智能验证码”或显式启用“所有收到的文本”；
- 通知默认发送“服务名 + 验证码/取件码 + 完整发件人标识（号码或邮箱）”，不发送完整短信正文或附件；取件短信会优先提取取件码，而不是运单尾号；
- “所有收到的文本”会把普通短信与 iMessage 原文发送到所有已启用渠道，属于高隐私风险选项；
- 可在设置页勾选“在通知中显示完整原文”，或用 CLI 显式开启；原文只从本机信息数据库即时读取，不额外保存为历史；
- 验证码不保存为历史记录；Bot Token 与 Discord Webhook URL 静态存储于 macOS 钥匙串，运行期间只在进程内存缓存；
- Discord URL 仅接受官方 `https://discord.com/api/webhooks/...` 形式，发送时禁用 mentions，并拒绝携带凭据的重定向；
- 多渠道投递分别记录脱敏游标；一个渠道临时失败时，不会重复发送已在另一渠道成功投递的同一条消息；
- 运行状态仅保存在 `~/Library/Application Support/SMS Bridge`，目录和数据库只允许当前用户访问；
- 同时启动多个 CLI、设置页或常驻服务时会被单实例锁拒绝，避免重复转发；
- 设置页的写操作只接受同源请求，防止恶意网页在后台替换 Token 或配对聊天；
- 在 Telegram 发送 `/status` 查看状态，发送 `/unpair` 立即解除授权。

## CLI（给熟悉终端的用户）

设置页和 CLI 使用同一份本机状态与钥匙串配置，可按需混用：

```zsh
python3 sms_bridge.py ui          # 启动本机设置页（默认命令）
python3 sms_bridge.py init        # 隐藏输入并保存 Bot Token（纯 CLI 初始化）
python3 sms_bridge.py run         # 仅运行转发服务
python3 sms_bridge.py pair        # 输出一次性 Telegram 配对链接
python3 sms_bridge.py status      # 输出 JSON 格式的脱敏状态
python3 sms_bridge.py doctor      # 检查本机权限、钥匙串、通知渠道与自动启动
python3 sms_bridge.py test        # 给所有已启用渠道发送测试通知
python3 sms_bridge.py test --provider discord
python3 sms_bridge.py unpair      # 解除当前 Telegram 配对
python3 sms_bridge.py install     # 安装当前用户的 LaunchAgent
python3 sms_bridge.py uninstall   # 移除 LaunchAgent
python3 sms_bridge.py reset --yes # 删除渠道凭据、配对、状态、日志、专用运行时和 LaunchAgent
python3 sms_bridge.py config      # 查看通知显示配置
python3 sms_bridge.py config --show-original on   # 在所有已启用渠道中附带原文
python3 sms_bridge.py config --show-original off  # 恢复隐私默认值
python3 sms_bridge.py config --mode strict        # 严格验证码（默认）
python3 sms_bridge.py config --mode smart         # 智能识别短验证码短信
python3 sms_bridge.py config --mode all           # 所有收到的文本（含原文）
python3 sms_bridge.py discord set                  # 隐藏输入并保存 Discord Webhook
python3 sms_bridge.py discord test
python3 sms_bridge.py discord enable
python3 sms_bridge.py discord disable
python3 sms_bridge.py discord remove
python3 sms_bridge.py --help      # 查看命令帮助
```

`run` 适合 `tmux`、`launchd` 或其他进程管理器；它不会开启本地网页。`pair` 的链接只打印到当前终端，不写入日志。请在首次运行和 macOS 升级后执行 `doctor`。

## 常见问题

**为什么没有收到通知？**

先点击设置页中的“发送测试通知”。若测试成功，检查该短信是否包含验证码相关字样（例如 `code`、`verification`、`验证码`）和 4–8 位数字，或包含明确的取件码/收件码；也确认它已经出现在 Mac 的「信息」App。多渠道状态可通过 `status` 或设置页分别检查。

**关闭终端后会怎样？**

如果尚未点击“安装开机启动”，服务会停止。安装后会通过当前用户的 macOS LaunchAgent 自动恢复；如遇完全磁盘访问权限问题，请重新运行设置页并查看状态提示。

**可以发到群组吗？**

Telegram 只允许单个已配对私聊；Discord 则由你创建 Webhook 时选择目标私密频道。建议始终使用只有自己或受信成员可见的目标。

## 开源与安全

完整图形化安装、CLI、权限、升级与排障步骤见 [中文用户手册](docs/USER_GUIDE.zh-CN.md)。安全边界、漏洞报告方式与运营清单见 [SECURITY.md](SECURITY.md) 和 [中文威胁建模](docs/THREAT_MODEL.zh-CN.md)；英文资料见 [README.en.md](README.en.md) 与 [English user guide](docs/USER_GUIDE.en.md)。维护者发布前请遵循双语 [发布指南](docs/RELEASING.md)。欢迎提交 Issue，但不要公开提交 Token、配对链接、验证码或完整日志。
