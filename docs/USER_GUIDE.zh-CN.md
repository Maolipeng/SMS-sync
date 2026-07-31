# SMS Bridge 用户手册

本文面向第一次使用命令行或第一次创建 Telegram Bot 的用户。高级用户可直接阅读文末的 CLI 部分。

> SMS Bridge 会处理登录验证码。Telegram Bot 私聊不是 Telegram「私密聊天」，消息会经过 Telegram 基础设施。请只在你理解并接受这一点时使用；金融、医疗、企业或其他高风险账户可能禁止转发验证码。

## 1. 使用前检查

你需要：

- macOS 设备和 Python 3.10 或更高版本；
- 与 iPhone 登录同一 Apple 账户的 Mac；
- Mac「信息」App 已能看到 iPhone 收到的短信；
- 一个专用于 SMS Bridge 的 Telegram Bot；
- 一个启用了两步验证、只有你能访问的 Telegram 账户。

先给 iPhone 发送一条普通测试短信，确认它出现在 Mac 的「信息」App。SMS Bridge 不会绕过 Apple 同步，也无法读取尚未同步到 Mac 的内容。

## 2. 创建专用 Telegram Bot

1. 在 Telegram 打开官方的 `@BotFather`；
2. 发送 `/newbot`，按提示设置名称和 username；
3. 复制 Bot Token，但不要发给任何人，也不要放进截图、Issue、聊天记录或 Git；
4. 若 Token 曾泄露，在 `@BotFather` 使用 `/revoke` 立即替换。

不要让同一个 Bot 同时被其他机器人框架轮询，否则它们可能争抢 `getUpdates`。

## 3. 图形化安装

1. 下载并解压项目源代码；
2. 双击 `SMS Bridge.command`；
3. 启动器首次运行会创建一份仅供 SMS Bridge 使用、权限为当前用户所有的 Python 运行时，然后浏览器会打开仅本机可访问的设置页；
4. 粘贴 Bot Token 并点击“安全保存”；
5. 如 macOS 弹出钥匙串确认，只在提示的程序是你刚启动的 Python/SMS Bridge 时允许。首次使用或 Python 路径变化时可能需要确认一次；同一进程会在内存中缓存 Token，不会每几秒重复读取钥匙串；
6. 点击“生成配对链接”，在 Telegram 中打开并点击“启动”；
7. 返回设置页，发送模拟测试通知；
8. 确认发件人、验证码和“模拟消息”标识均正确后，点击“安装后台常驻”。

安装后台常驻后设置页会关闭，LaunchAgent 会接管转发。它只属于当前 macOS 用户，不需要管理员权限，也不会把 Token 写入 plist。

### 完全磁盘访问权限该选哪个

前往“系统设置 → 隐私与安全性 → 完全磁盘访问权限”：

- 推荐添加启动器创建的专用可执行文件：`~/Library/Application Support/SMS Bridge/runtime/bin/python3.10`（小版本号以实际为准）；
- 设置页“运行诊断”中的“后台 Python”会显示精确路径；
- 不建议给日常使用的全局 Python 授权，因为其他使用同一解释器的脚本也可能继承完全磁盘访问权限；
- 高级用户若绕过双击入口直接运行源码，需要自行决定为 Terminal/iTerm 或专用解释器授权。

授权后彻底退出对应程序，再重新启动 SMS Bridge。macOS 不允许应用替你静默授予这项权限。

如果专用 `python3.10` 已开启，但从未授权的 Terminal 双击启动时页面仍显示“需要权限”，不要因此给整个 Terminal 扩权。先完成 Token 保存和私聊配对，再点击“安装后台常驻”；LaunchAgent 会直接使用已授权的真实 `python3.10` 路径。等待数秒后重新打开设置页，状态会显示后台服务的实际读取结果。

## 4. 通知内容

默认通知包含：

```text
✉️ +1 555 010 1234 · 17:08

🔐 验证码 · Google

4  8  2  9  1  3

[📋 复制验证码]
```

Telegram 不允许 Bot 自定义真正的卡片字号，但 SMS Bridge 会使用独立粗体行和额外留白突出验证码，避开部分手机端会遮住末位数字的代码块。下方的“复制验证码”按钮复制原始验证码。默认不会发送完整短信正文或附件。开启“附带短信原文”后，原文会以默认折叠、可点击展开的引用块发送，但 SMS Bridge 仍不会建立本地验证码历史。长原文会安全截断，不会破坏 Telegram 消息格式。

转发规则有三档：

- **严格验证码（默认）**：同时包含验证码语义（如 `code`、`verification`、`OTP`、`验证码`）和 4–8 位数字；也识别明确标注的取件码、收件码、提货码，以及“凭 3-7-2468 到驿站”这类格式，并优先于运单尾号；
- **智能验证码**：在严格规则之外，兼容较短、只有一段数字且数字位于开头或结尾的中文短信，同时排除订单、余额、金额、电话、会议等常见误报；
- **所有收到的文本**：转发普通短信和 iMessage；因为普通消息没有验证码可突出，通知会携带原文。此模式可能把私人对话发送到 Telegram，只有明确接受风险后才应开启。

规则仍可能误报或漏报，因此不要把本工具当作保证投递系统。

## 5. CLI

纯终端初始化不会在屏幕或进程参数中显示 Token：

```zsh
python3 sms_bridge.py init
python3 sms_bridge.py pair
python3 sms_bridge.py test
python3 sms_bridge.py install
```

常用命令：

```zsh
python3 sms_bridge.py status
python3 sms_bridge.py doctor
python3 sms_bridge.py run
python3 sms_bridge.py config --show-original on
python3 sms_bridge.py config --show-original off
python3 sms_bridge.py config --mode strict
python3 sms_bridge.py config --mode smart
python3 sms_bridge.py config --mode all
python3 sms_bridge.py unpair
python3 sms_bridge.py uninstall
python3 sms_bridge.py reset --yes
```

`uninstall` 只移除后台常驻，保留配对和 Token。`reset --yes` 会永久删除钥匙串 Token、配对、本机状态、日志、专用运行时、LaunchAgent，以及旧版原型留下的 Telegram `.env` 字段、状态库和日志。它不会替你在 Telegram 撤销 Bot Token，也不能撤销 macOS 的“完全磁盘访问权限”记录。

## 6. 日常安全操作

- Token 泄露：先在 `@BotFather` `/revoke`，再重新运行 `init` 或在设置页保存新 Token；保存新 Token 会自动解除旧配对。
- Telegram 设备丢失：先从 Telegram 终止丢失设备会话，再 `/revoke` Bot Token 并重新配对。
- Mac 转让或送修：先在 `@BotFather` 撤销 Token，在“系统设置 → 隐私与安全性 → 完全磁盘访问权限”中移除专用 `python3`，再运行 `python3 sms_bridge.py reset --yes`。
- 暂停转发：运行 `uninstall`；临时运行可使用 `run`。
- 系统或 Python 升级：重新运行 `doctor`，确认 Messages、钥匙串、Telegram 与 LaunchAgent 均正常。

## 7. 数据保存位置

- 专用 Python 运行时：`~/Library/Application Support/SMS Bridge/runtime`，仅供本工具使用；
- Bot Token：静态存储于 macOS 钥匙串；运行时在当前进程内存中缓存，进程退出即释放；
- 配对 Chat ID、消息游标和显示偏好：`~/Library/Application Support/SMS Bridge/state.sqlite3`；
- 后台日志：同一目录，仅记录运行状态，不应包含 Token、验证码或短信正文；
- Messages 数据库：仅用 SQLite `mode=ro` 直接查询，不创建持久副本；
- 验证码历史：不保存。

本机设置页只监听 `127.0.0.1`。不要把它接入 Cloudflare Tunnel、反向代理、端口转发或公网共享。

## 8. 排障

### 测试通知成功，但新短信没有转发

确认短信已经出现在 Mac「信息」App。没有验证码关键词的短短信可切换到“智能验证码”；确需转发全部普通文本时再选择“所有收到的文本”。运行 `doctor` 检查读取权限。

### `doctor` 提示无法读取 Messages

为实际运行 SMS Bridge 的终端或 Python 可执行文件开启完全磁盘访问权限，彻底退出后重开。不要修改 `chat.db` 的文件权限。

### 钥匙串弹窗反复出现

确认运行的是预期的 Python 路径；若刚升级或切换 Python，macOS 可能把它视为新程序。回到交互式设置页重新保存 Token，并在可信提示中选择“始终允许”。

### 安装后台常驻后没有转发

运行 `doctor`。如 LaunchAgent 未加载，先执行 `uninstall`，再从设置页重新安装。后台 Python 也必须具有完全磁盘访问权限。

### Telegram 返回 Token 错误

不要把 Token 发到 Issue。直接在 `@BotFather` `/revoke`，保存新的 Token 并重新配对。

## 9. 升级

停止后台服务，替换源码，再重新安装：

```zsh
python3 sms_bridge.py uninstall
# 更新或替换项目文件
python3 sms_bridge.py doctor
python3 sms_bridge.py install
```

发布版本升级前请阅读 `CHANGELOG.md`。安全边界与剩余风险见 [威胁建模](THREAT_MODEL.zh-CN.md)。
