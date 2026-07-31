# SMS Bridge

把同步到 Mac 的 iPhone 验证码，安全地发送到你自己的 Telegram 私聊。

SMS Bridge 是一个只在本机运行的开源工具：不需要 Docker、域名、服务器或编程知识，也不会开放公网端口。

```text
iPhone 收到验证码
      ↓  Apple「信息」同步
Mac mini（SMS Bridge）
      ↓  已配对的 Telegram 私聊
你的另一台设备
```

## 三步开始

### 1. 准备

- iPhone 与 Mac 使用同一个 Apple 账户，并在两端开启「信息」同步；
- 先确认 Mac 的「信息」App 已能看到 iPhone 收到的短信；
- 在 Telegram 通过 `@BotFather` 创建一个 Bot，并复制它给出的 **Bot Token**。

> Bot Token 类似密码。请不要发到群聊、截图或提交到 Git。若曾泄露，请在 `@BotFather` 使用 `/revoke` 生成新的 Token。Token 会保存到 macOS 钥匙串；`.env` 仅供开发测试，默认不会被读取。

### 2. 启动本机设置页

下载并解压项目后，直接双击：

```text
SMS Bridge.command
```

也可以在 iTerm 或 Terminal 进入项目目录并执行 `python3 sms_bridge.py`。浏览器会自动打开 `http://127.0.0.1:8765`。页面会引导你：

1. 保存 Bot Token（保存至 macOS 钥匙串，而不是项目文件）；
2. 点击“生成配对链接”；
3. 用自己的 Telegram 打开链接，再点击“启动”；
4. 点击“发送测试通知”。

测试成功后，点击“安装后台常驻”，设置页会关闭并由当前用户的 LaunchAgent 接管；启动配置中不包含 Bot Token。

### 3. 如提示权限不足

前往：**系统设置 → 隐私与安全性 → 完全磁盘访问权限**。双击启动器会在 `~/Library/Application Support/SMS Bridge/runtime` 创建仅供本工具使用的 Python 运行时；请添加 `runtime/bin/python3.10`（小版本号以实际为准），而不是给日常使用的全局 Python 扩权。然后彻底退出 SMS Bridge 并重新启动。

macOS 可能仍不允许由未授权 Terminal 直接启动的设置页读取信息数据库，这是“责任进程”机制导致的正常现象。无需给整个 Terminal 扩权：完成 Token 与配对后安装后台常驻，LaunchAgent 会使用已授权的 `python3.10` 实际路径并回写验证结果；重新打开设置页即可看到后台验证状态。

## 默认隐私规则

- 仅监听本机的 `127.0.0.1`，没有公网入口；
- 未配对时绝不转发；只允许一个 Telegram 私聊；
- 配对链接 10 分钟有效且只能使用一次；
- 新安装默认使用“严格验证码”规则；可切换为“智能验证码”或显式启用“所有收到的文本”；
- 通知默认发送“服务名 + 验证码/取件码 + 完整发件人标识（号码或邮箱）”，不发送完整短信正文或附件；取件短信会优先提取取件码，而不是运单尾号；
- “所有收到的文本”会把普通短信与 iMessage 原文发送到 Telegram，属于高隐私风险选项；
- 可在设置页勾选“在通知中显示完整原文”，或用 CLI 显式开启；原文只从本机信息数据库即时读取，不额外保存为历史；
- 验证码不保存为历史记录；Bot Token 静态存储于 macOS 钥匙串，运行期间只在进程内存缓存一次，避免反复授权弹窗；
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
python3 sms_bridge.py doctor      # 检查本机权限、钥匙串、Telegram 与自动启动
python3 sms_bridge.py test        # 给已配对私聊发送测试通知
python3 sms_bridge.py unpair      # 解除当前 Telegram 配对
python3 sms_bridge.py install     # 安装当前用户的 LaunchAgent
python3 sms_bridge.py uninstall   # 移除 LaunchAgent
python3 sms_bridge.py reset --yes # 删除 Token、配对、状态、日志、专用运行时和 LaunchAgent
python3 sms_bridge.py config      # 查看通知显示配置
python3 sms_bridge.py config --show-original on   # 在 Telegram 通知中附带原文
python3 sms_bridge.py config --show-original off  # 恢复隐私默认值
python3 sms_bridge.py config --mode strict        # 严格验证码（默认）
python3 sms_bridge.py config --mode smart         # 智能识别短验证码短信
python3 sms_bridge.py config --mode all           # 所有收到的文本（含原文）
python3 sms_bridge.py --help      # 查看命令帮助
```

`run` 适合 `tmux`、`launchd` 或其他进程管理器；它不会开启本地网页。`pair` 的链接只打印到当前终端，不写入日志。请在首次运行和 macOS 升级后执行 `doctor`。

## 常见问题

**为什么没有收到通知？**

先点击设置页中的“发送测试通知”。若测试成功，检查该短信是否包含验证码相关字样（例如 `code`、`verification`、`验证码`）和 4–8 位数字，或包含明确的取件码/收件码；也确认它已经出现在 Mac 的「信息」App。

**关闭终端后会怎样？**

如果尚未点击“安装开机启动”，服务会停止。安装后会通过当前用户的 macOS LaunchAgent 自动恢复；如遇完全磁盘访问权限问题，请重新运行设置页并查看状态提示。

**可以发到群组吗？**

不可以。验证码敏感，第一版只支持单个 Telegram 私聊。

## 开源与安全

完整图形化安装、CLI、权限、升级与排障步骤见 [中文用户手册](docs/USER_GUIDE.zh-CN.md)。安全边界、漏洞报告方式与运营清单见 [SECURITY.md](SECURITY.md) 和 [中文威胁建模](docs/THREAT_MODEL.zh-CN.md)；英文资料见 [README.en.md](README.en.md) 与 [English user guide](docs/USER_GUIDE.en.md)。维护者发布前请遵循双语 [发布指南](docs/RELEASING.md)。欢迎提交 Issue，但不要公开提交 Token、配对链接、验证码或完整日志。
