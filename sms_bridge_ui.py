"""Dependency-free local onboarding UI for SMS Bridge."""

from __future__ import annotations

import html
import json


def render_page(csrf_token: str) -> str:
    nonce = html.escape(csrf_token, quote=True)
    csrf_json = json.dumps(csrf_token)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>SMS Bridge · 本机设置</title>
  <style>
    :root {{
      --ink: #17201c;
      --muted: #69736e;
      --paper: #f4f0e7;
      --surface: rgba(255, 253, 248, .86);
      --surface-strong: #fffdf8;
      --line: rgba(23, 32, 28, .14);
      --line-strong: rgba(23, 32, 28, .28);
      --green: #176b4b;
      --green-soft: #dcecdf;
      --orange: #d9673e;
      --orange-soft: #f7dfd4;
      --shadow: 0 24px 70px rgba(36, 45, 39, .10);
      --radius: 22px;
    }}

    * {{ box-sizing: border-box; }}
    html {{ min-width: 320px; background: var(--paper); }}
    body {{
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      font-family: "Avenir Next", "PingFang SC", "Hiragino Sans GB", sans-serif;
      background:
        radial-gradient(circle at 12% 4%, rgba(255,255,255,.95) 0 11rem, transparent 33rem),
        radial-gradient(circle at 92% 15%, rgba(212,232,217,.75), transparent 29rem),
        linear-gradient(145deg, #f7f3ea 0%, #efe9de 100%);
    }}
    body::before {{
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      opacity: .22;
      background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 180 180' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.10'/%3E%3C/svg%3E");
    }}

    button, input {{ font: inherit; }}
    button {{ -webkit-tap-highlight-color: transparent; }}
    a {{ color: var(--green); text-underline-offset: 3px; }}

    .shell {{ width: min(1120px, calc(100% - 40px)); margin: 0 auto; padding: 42px 0 68px; }}
    .topbar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 24px;
      padding: 0 4px 30px;
      border-bottom: 1px solid var(--line-strong);
    }}
    .brand {{ display: flex; align-items: center; gap: 14px; }}
    .brand-mark {{
      display: grid;
      place-items: center;
      width: 46px;
      aspect-ratio: 1;
      border-radius: 15px;
      color: #fff;
      background: var(--ink);
      box-shadow: 0 10px 24px rgba(23,32,28,.18);
    }}
    .brand-mark svg {{ width: 22px; height: 22px; }}
    .brand-name {{ margin: 0; font: 700 18px/1 "Avenir Next", sans-serif; letter-spacing: -.02em; }}
    .brand-caption {{ margin: 5px 0 0; color: var(--muted); font-size: 12px; letter-spacing: .08em; text-transform: uppercase; }}
    .status-pill {{
      display: inline-flex;
      align-items: center;
      gap: 9px;
      min-height: 38px;
      padding: 0 14px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: rgba(255,255,255,.54);
      color: var(--muted);
      font-size: 13px;
      font-weight: 700;
      backdrop-filter: blur(12px);
    }}
    .status-dot {{ width: 8px; height: 8px; border-radius: 50%; background: #b9a99e; box-shadow: 0 0 0 4px rgba(185,169,158,.16); }}
    .status-pill[data-state="ready"] {{ color: var(--green); border-color: rgba(23,107,75,.23); background: rgba(220,236,223,.70); }}
    .status-pill[data-state="ready"] .status-dot {{ background: #21a16e; box-shadow: 0 0 0 4px rgba(33,161,110,.13); }}

    .hero {{ display: grid; grid-template-columns: minmax(0, 1.45fr) minmax(260px, .55fr); gap: 48px; padding: 62px 4px 48px; align-items: end; }}
    .eyebrow {{ display: inline-flex; gap: 9px; align-items: center; margin-bottom: 17px; color: var(--green); font-size: 12px; font-weight: 800; letter-spacing: .14em; text-transform: uppercase; }}
    .eyebrow::before {{ content: ""; width: 26px; height: 1px; background: currentColor; }}
    h1 {{ margin: 0; max-width: 760px; font: 700 clamp(44px, 7vw, 76px)/.98 "Iowan Old Style", "Songti SC", Georgia, serif; letter-spacing: -.045em; }}
    .hero-copy {{ max-width: 680px; margin: 25px 0 0; color: #505b55; font-size: 17px; line-height: 1.8; }}
    .privacy-note {{ padding: 22px; border-left: 3px solid var(--green); background: rgba(255,255,255,.35); }}
    .privacy-note strong {{ display: block; margin-bottom: 7px; font: 700 15px "Iowan Old Style", "Songti SC", serif; }}
    .privacy-note p {{ margin: 0; color: var(--muted); font-size: 13px; line-height: 1.65; }}

    .layout {{ display: grid; grid-template-columns: minmax(0, 1fr) 300px; gap: 20px; align-items: start; }}
    .steps {{ display: grid; gap: 16px; }}
    .card {{
      position: relative;
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: var(--surface);
      box-shadow: 0 1px 0 rgba(255,255,255,.8) inset;
      backdrop-filter: blur(15px);
      animation: rise .5s both;
    }}
    .card:nth-child(2) {{ animation-delay: .06s; }}
    .card:nth-child(3) {{ animation-delay: .12s; }}
    .card-body {{ padding: 27px 28px 29px; }}
    .step-head {{ display: flex; align-items: flex-start; gap: 17px; margin-bottom: 22px; }}
    .step-number {{
      flex: 0 0 auto;
      display: grid;
      place-items: center;
      width: 34px;
      height: 34px;
      border: 1px solid var(--line-strong);
      border-radius: 50%;
      color: var(--muted);
      font: 700 12px "Avenir Next", sans-serif;
    }}
    .step-title {{ margin: 1px 0 5px; font: 700 22px/1.2 "Iowan Old Style", "Songti SC", Georgia, serif; letter-spacing: -.015em; }}
    .step-copy {{ margin: 0; color: var(--muted); font-size: 13px; line-height: 1.65; }}
    .field-label {{ display: block; margin-bottom: 8px; color: var(--ink); font-size: 12px; font-weight: 800; letter-spacing: .04em; }}
    .field-row {{ display: flex; gap: 10px; }}
    .token-input {{
      min-width: 0;
      flex: 1;
      height: 48px;
      border: 1px solid var(--line-strong);
      border-radius: 13px;
      padding: 0 15px;
      color: var(--ink);
      background: rgba(255,255,255,.80);
      outline: none;
      font: 500 14px ui-monospace, SFMono-Regular, Menlo, monospace;
      transition: border .18s, box-shadow .18s;
    }}
    .token-input:focus {{ border-color: var(--green); box-shadow: 0 0 0 4px rgba(23,107,75,.10); }}
    .btn {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      min-height: 44px;
      border: 1px solid transparent;
      border-radius: 12px;
      padding: 0 17px;
      cursor: pointer;
      color: white;
      background: var(--ink);
      font-size: 13px;
      font-weight: 800;
      transition: transform .16s, box-shadow .16s, background .16s;
    }}
    .btn:hover {{ transform: translateY(-1px); box-shadow: 0 8px 18px rgba(23,32,28,.14); }}
    .btn:active {{ transform: translateY(0); }}
    .btn:focus-visible {{ outline: 3px solid rgba(23,107,75,.25); outline-offset: 2px; }}
    .btn-secondary {{ color: var(--ink); border-color: var(--line-strong); background: rgba(255,255,255,.62); }}
    .btn-green {{ background: var(--green); }}
    .btn-danger {{ color: #9b3d28; border-color: rgba(217,103,62,.25); background: var(--orange-soft); }}
    .btn[disabled] {{ cursor: wait; opacity: .55; transform: none; box-shadow: none; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 9px; margin-top: 18px; }}
    .inline-note {{ min-height: 20px; margin: 10px 0 0; color: var(--green); font-size: 12px; }}
    .provider-meta {{ display: flex; flex-wrap: wrap; align-items: center; gap: 9px; margin-bottom: 16px; }}
    .provider-badge {{ display: inline-flex; align-items: center; min-height: 25px; padding: 0 9px; border: 1px solid var(--line); border-radius: 999px; color: var(--muted); background: rgba(255,255,255,.55); font-size: 10px; font-weight: 800; letter-spacing: .06em; text-transform: uppercase; }}
    .provider-badge[data-state="ready"] {{ color: var(--green); border-color: rgba(23,107,75,.22); background: var(--green-soft); }}

    .pair-link {{ display: none; margin-top: 18px; padding: 16px 17px; border: 1px solid rgba(23,107,75,.20); border-radius: 14px; background: var(--green-soft); }}
    .pair-link[data-visible="true"] {{ display: block; }}
    .pair-link small {{ display: block; margin-bottom: 7px; color: var(--green); font-weight: 800; }}
    .pair-link a {{ word-break: break-all; font-size: 13px; }}

    .switch-row {{ display: flex; justify-content: space-between; align-items: center; gap: 24px; padding: 18px 0 0; }}
    .switch-copy strong {{ display: block; margin-bottom: 5px; font-size: 14px; }}
    .switch-copy span {{ display: block; max-width: 560px; color: var(--muted); font-size: 12px; line-height: 1.55; }}
    .rule-row {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(210px, 290px); gap: 20px; align-items: center; padding-top: 4px; }}
    .rule-copy strong {{ display: block; margin-bottom: 5px; font-size: 14px; }}
    .rule-copy span {{ display: block; color: var(--muted); font-size: 12px; line-height: 1.55; }}
    .rule-select {{ width: 100%; min-height: 44px; border: 1px solid var(--line-strong); border-radius: 12px; padding: 0 12px; color: var(--ink); background: rgba(255,255,255,.78); font-family: inherit; font-size: 13px; font-weight: 700; }}
    .rule-warning {{ margin: 9px 0 0; color: #9b3d28; font-size: 11px; line-height: 1.5; }}
    .switch {{ position: relative; flex: 0 0 auto; width: 48px; height: 28px; }}
    .switch input {{ position: absolute; width: 1px; height: 1px; opacity: 0; }}
    .switch-track {{ position: absolute; inset: 0; cursor: pointer; border: 1px solid var(--line-strong); border-radius: 999px; background: #ddd6cb; transition: .2s; }}
    .switch-track::after {{ content: ""; position: absolute; width: 20px; height: 20px; left: 3px; top: 3px; border-radius: 50%; background: white; box-shadow: 0 2px 7px rgba(23,32,28,.22); transition: .2s; }}
    .switch input:checked + .switch-track {{ border-color: var(--green); background: var(--green); }}
    .switch input:checked + .switch-track::after {{ transform: translateX(20px); }}
    .switch input:focus-visible + .switch-track {{ outline: 3px solid rgba(23,107,75,.20); outline-offset: 2px; }}

    .side {{ position: sticky; top: 20px; display: grid; gap: 16px; }}
    .side-card {{ border: 1px solid var(--line); border-radius: var(--radius); padding: 24px; background: rgba(255,253,248,.70); }}
    .side-title {{ margin: 0 0 18px; font: 700 18px "Iowan Old Style", "Songti SC", Georgia, serif; }}
    .checks {{ display: grid; gap: 14px; }}
    .check {{ display: grid; grid-template-columns: 10px 1fr; gap: 11px; align-items: start; }}
    .check-dot {{ width: 8px; height: 8px; margin-top: 5px; border-radius: 50%; background: #c4b9ad; }}
    .check[data-ok="true"] .check-dot {{ background: #21a16e; box-shadow: 0 0 0 4px rgba(33,161,110,.11); }}
    .check strong {{ display: block; font-size: 13px; }}
    .check span {{ display: block; margin-top: 3px; color: var(--muted); font-size: 11px; line-height: 1.45; }}
    .principles {{ margin: 0; padding: 0; list-style: none; display: grid; gap: 12px; }}
    .principles li {{ display: flex; gap: 10px; color: var(--muted); font-size: 12px; line-height: 1.5; }}
    .principles li::before {{ content: "—"; color: var(--green); font-weight: 900; }}

    .toast {{
      position: fixed;
      z-index: 10;
      left: 50%;
      bottom: 28px;
      max-width: min(430px, calc(100% - 32px));
      transform: translate(-50%, 16px);
      padding: 13px 17px;
      border-radius: 13px;
      color: #fff;
      background: var(--ink);
      box-shadow: var(--shadow);
      opacity: 0;
      pointer-events: none;
      transition: .22s;
      font-size: 13px;
    }}
    .toast[data-visible="true"] {{ opacity: 1; transform: translate(-50%, 0); }}
    .toast[data-kind="error"] {{ background: #943b29; }}

    dialog {{ width: min(620px, calc(100% - 30px)); border: 1px solid var(--line); border-radius: var(--radius); padding: 0; color: var(--ink); background: var(--surface-strong); box-shadow: var(--shadow); }}
    dialog::backdrop {{ background: rgba(20,27,23,.38); backdrop-filter: blur(4px); }}
    .dialog-head {{ display: flex; justify-content: space-between; align-items: center; padding: 22px 24px; border-bottom: 1px solid var(--line); }}
    .dialog-head h2 {{ margin: 0; font: 700 21px "Iowan Old Style", "Songti SC", serif; }}
    .icon-btn {{ border: 0; cursor: pointer; color: var(--muted); background: transparent; font-size: 24px; }}
    .diagnostics {{ display: grid; gap: 10px; padding: 20px 24px 25px; }}
    .diag {{ display: flex; align-items: start; justify-content: space-between; gap: 20px; padding: 13px 0; border-bottom: 1px solid var(--line); }}
    .diag:last-child {{ border: 0; }}
    .diag strong {{ font-size: 13px; }}
    .diag span {{ max-width: 65%; color: var(--muted); text-align: right; font-size: 12px; line-height: 1.5; }}

    @keyframes rise {{ from {{ opacity: 0; transform: translateY(10px); }} to {{ opacity: 1; transform: translateY(0); }} }}
    @media (max-width: 900px) {{
      .hero, .layout {{ grid-template-columns: 1fr; }}
      .hero {{ gap: 28px; padding-top: 46px; }}
      .privacy-note {{ max-width: 620px; }}
      .side {{ position: static; grid-template-columns: 1fr 1fr; }}
    }}
    @media (max-width: 640px) {{
      .shell {{ width: min(100% - 24px, 1120px); padding-top: 20px; }}
      .topbar {{ align-items: flex-start; }}
      .brand-caption {{ display: none; }}
      .hero {{ padding: 39px 2px 34px; }}
      h1 {{ font-size: 44px; }}
      .hero-copy {{ font-size: 15px; }}
      .layout, .side {{ grid-template-columns: 1fr; }}
      .card-body, .side-card {{ padding: 22px 20px; }}
      .field-row {{ flex-direction: column; }}
      .field-row .btn {{ width: 100%; }}
      .rule-row {{ grid-template-columns: 1fr; }}
      .switch-row {{ align-items: flex-start; }}
    }}
    @media (prefers-reduced-motion: reduce) {{
      *, *::before, *::after {{ scroll-behavior: auto !important; animation-duration: .01ms !important; transition-duration: .01ms !important; }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <header class="topbar">
      <div class="brand">
        <div class="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
            <rect x="5" y="10" width="14" height="10" rx="3"></rect>
            <path d="M8.5 10V7.5a3.5 3.5 0 0 1 7 0V10"></path>
            <circle cx="12" cy="15" r="1.2" fill="currentColor" stroke="none"></circle>
          </svg>
        </div>
        <div>
          <p class="brand-name">SMS Bridge</p>
          <p class="brand-caption">Local authentication relay</p>
        </div>
      </div>
      <div id="statusPill" class="status-pill" data-state="checking">
        <i class="status-dot"></i><span>正在检查</span>
      </div>
    </header>

    <section class="hero">
      <div>
        <div class="eyebrow">Private by architecture</div>
        <h1>验证码，只去<br>你授权的地方。</h1>
        <p class="hero-copy">将 iPhone 同步到 Mac 的验证码转发至你启用的 Telegram 私聊或 Discord 私密频道。所有配置留在本机，没有公网入口，也不建立验证码历史。</p>
      </div>
      <aside class="privacy-note">
        <strong>数据路径一眼可见</strong>
        <p>Messages 数据库 → 本机内存 → 已启用的通知渠道。原文只有在你明确开启时才会发送。</p>
      </aside>
    </section>

    <section class="layout">
      <div class="steps">
        <article class="card">
          <div class="card-body">
            <div class="step-head">
              <span class="step-number">01</span>
              <div>
                <h2 class="step-title">连接 Telegram Bot</h2>
                <p class="step-copy">Token 会写入 macOS 钥匙串；重新保存 Token 会安全地解除旧配对。</p>
              </div>
            </div>
            <label class="field-label" for="token">BOT TOKEN</label>
            <form id="tokenForm" class="field-row">
              <input id="token" class="token-input" type="password" placeholder="123456789:AA…" autocomplete="off" spellcheck="false">
              <button id="saveToken" class="btn" type="submit">安全保存</button>
            </form>
            <p id="tokenNote" class="inline-note" role="status"></p>
          </div>
        </article>

        <article class="card">
          <div class="card-body">
            <div class="step-head">
              <span class="step-number">02</span>
              <div>
                <h2 class="step-title">授权接收私聊</h2>
                <p id="pairText" class="step-copy">生成十分钟有效、仅可使用一次的配对链接。</p>
              </div>
            </div>
            <button id="pair" class="btn btn-green" type="button">生成配对链接</button>
            <div id="pairLink" class="pair-link">
              <small>一次性链接 · 10 分钟内有效</small>
              <a id="pairAnchor" href="#" target="_blank" rel="noreferrer noopener"></a>
            </div>
          </div>
        </article>

        <article class="card">
          <div class="card-body">
            <div class="step-head">
              <span class="step-number">03</span>
              <div>
                <h2 class="step-title">添加 Discord Webhook</h2>
                <p class="step-copy">可选。将通知发送到你自己的 Discord 私密频道，无需运行 Discord Bot。</p>
              </div>
            </div>
            <div class="provider-meta">
              <span id="discordBadge" class="provider-badge">尚未配置</span>
              <span class="step-copy">URL 仅存入 macOS 钥匙串，页面不会再次显示。</span>
            </div>
            <label class="field-label" for="discordWebhook">WEBHOOK URL</label>
            <form id="discordForm" class="field-row">
              <input id="discordWebhook" class="token-input" type="password" placeholder="https://discord.com/api/webhooks/…" autocomplete="off" spellcheck="false">
              <button id="saveDiscord" class="btn" type="submit">验证并保存</button>
            </form>
            <div class="switch-row">
              <div class="switch-copy">
                <strong>启用 Discord 通知</strong>
                <span>重新启用后只接收之后到达的新消息，不补发停用期间的内容。</span>
              </div>
              <label class="switch" aria-label="启用 Discord 通知">
                <input id="discordEnabled" type="checkbox">
                <span class="switch-track"></span>
              </label>
            </div>
            <div class="actions">
              <button id="discordTest" class="btn btn-secondary" type="button">测试 Discord</button>
              <button id="discordRemove" class="btn btn-danger" type="button">移除 Webhook</button>
            </div>
            <p id="discordNote" class="inline-note" role="status"></p>
          </div>
        </article>

        <article class="card">
          <div class="card-body">
            <div class="step-head">
              <span class="step-number">04</span>
              <div>
                <h2 class="step-title">通知与运行</h2>
                <p class="step-copy">通知默认包含验证码和完整发件人标识，便于立即判断来源。</p>
              </div>
            </div>
            <div class="rule-row">
              <div class="rule-copy">
                <strong>转发规则</strong>
                <span id="modeNote">严格验证码：必须同时包含验证码关键词和 4–8 位数字。</span>
              </div>
              <select id="forwardMode" class="rule-select" aria-label="转发规则">
                <option value="strict">严格验证码（默认）</option>
                <option value="smart">智能验证码</option>
                <option value="all">所有收到的文本</option>
              </select>
            </div>
            <p id="modeWarning" class="rule-warning" hidden>“所有收到的文本”会把普通短信和 iMessage 原文发送到所有已启用渠道，请仅在你明确接受该隐私风险时使用。</p>
            <div class="switch-row">
              <div class="switch-copy">
                <strong>附带短信原文</strong>
                <span>开启后，原文会发送至所有已启用渠道；SMS Bridge 仍不会额外保存历史。</span>
              </div>
              <label class="switch" aria-label="附带短信原文">
                <input id="showOriginal" type="checkbox">
                <span class="switch-track"></span>
              </label>
            </div>
            <div class="actions">
              <button id="testPush" class="btn btn-green" type="button">发送测试通知</button>
              <button id="doctor" class="btn btn-secondary" type="button">运行诊断</button>
              <button id="install" class="btn btn-secondary" type="button">安装后台常驻</button>
              <button id="unpair" class="btn btn-danger" type="button">解除配对</button>
              <button id="reset" class="btn btn-danger" type="button">移除全部配置</button>
            </div>
          </div>
        </article>
      </div>

      <aside class="side">
        <section class="side-card">
          <h2 class="side-title">当前状态</h2>
          <div class="checks">
            <div id="checkMessages" class="check"><i class="check-dot"></i><div><strong>Messages 数据库</strong><span>检查中</span></div></div>
            <div id="checkToken" class="check"><i class="check-dot"></i><div><strong>macOS 钥匙串</strong><span>检查中</span></div></div>
            <div id="checkPair" class="check"><i class="check-dot"></i><div><strong>Telegram 私聊</strong><span>检查中</span></div></div>
            <div id="checkDiscord" class="check"><i class="check-dot"></i><div><strong>Discord Webhook</strong><span>检查中</span></div></div>
            <div id="checkService" class="check"><i class="check-dot"></i><div><strong>转发服务</strong><span>本机监听</span></div></div>
          </div>
        </section>
        <section class="side-card">
          <h2 class="side-title">安全边界</h2>
          <ul class="principles">
            <li>只监听 127.0.0.1</li>
            <li>只向你启用的渠道发送</li>
            <li>Token 与 Webhook 仅存钥匙串</li>
            <li>默认不发送短信原文</li>
          </ul>
        </section>
      </aside>
    </section>
  </main>

  <div id="toast" class="toast" role="status" aria-live="polite"></div>
  <dialog id="diagnosticDialog">
    <div class="dialog-head"><h2>本机诊断</h2><button id="closeDialog" class="icon-btn" aria-label="关闭">×</button></div>
    <div id="diagnostics" class="diagnostics"></div>
  </dialog>

  <script nonce="{nonce}">
    const CSRF_TOKEN = {csrf_json};
    const $ = (id) => document.getElementById(id);
    const diagnosticLabels = {{
      stateDirectory: "本机状态目录",
      pythonExecutable: "后台 Python",
      messages: "Messages 数据库",
      keychain: "macOS 钥匙串",
      telegram: "Telegram Bot",
      discord: "Discord Webhook",
      launchAgent: "后台常驻"
    }};
    let toastTimer;

    async function api(path, body) {{
      const options = body === undefined ? {{}} : {{
        method: "POST",
        headers: {{
          "Content-Type": "application/json",
          "X-SMS-Bridge-CSRF": CSRF_TOKEN
        }},
        body: JSON.stringify(body)
      }};
      const response = await fetch("/api/" + path, options);
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "操作失败");
      return result;
    }}

    function toast(message, kind = "success") {{
      clearTimeout(toastTimer);
      $("toast").textContent = message;
      $("toast").dataset.kind = kind;
      $("toast").dataset.visible = "true";
      toastTimer = setTimeout(() => $("toast").dataset.visible = "false", 3200);
    }}

    function setCheck(id, ok, detail) {{
      const element = $(id);
      element.dataset.ok = String(Boolean(ok));
      element.querySelector("span").textContent = detail;
    }}

    async function refresh() {{
      try {{
        const state = await api("status");
        const ready = state.hasActiveProvider && state.messagesReadable;
        $("statusPill").dataset.state = ready ? "ready" : "checking";
        $("statusPill").querySelector("span").textContent = ready ? "已就绪" : "等待设置";
        setCheck("checkMessages", state.messagesReadable, state.messagesReadable ? "已获读取权限" : "待验证：授权专用 Python 后安装后台常驻");
        setCheck("checkToken", state.configured, state.configured ? "Token 已安全保存" : "尚未保存 Token");
        setCheck("checkPair", state.paired, state.paired ? "已配对 · " + state.pairedName : "尚未授权私聊");
        setCheck("checkDiscord", state.discordEnabled, state.discordEnabled ? "Webhook 已启用" : state.discordConfigured ? "已保存 · 当前停用" : "未配置（可选）");
        setCheck("checkService", !state.lastError, state.lastError ? "最近异常：" + state.lastError : "正在本机监听");
        $("discordBadge").dataset.state = state.discordEnabled ? "ready" : "idle";
        $("discordBadge").textContent = state.discordEnabled ? "已启用" : state.discordConfigured ? "已保存 · 已停用" : "尚未配置";
        $("discordEnabled").checked = Boolean(state.discordEnabled);
        $("discordEnabled").disabled = !state.discordConfigured;
        $("discordTest").disabled = !state.discordConfigured;
        $("discordRemove").disabled = !state.discordConfigured;
        $("forwardMode").value = state.forwardMode || "strict";
        const allMessages = state.forwardMode === "all";
        $("modeWarning").hidden = !allMessages;
        $("showOriginal").disabled = allMessages;
        $("modeNote").textContent = state.forwardMode === "smart"
          ? "智能验证码：兼容短中文数字短信，并排除常见订单、金额和号码内容。"
          : allMessages
            ? "所有收到的文本：普通短信与 iMessage 均会携带原文发送。"
            : "严格验证码：必须同时包含验证码关键词和 4–8 位数字。";
        $("showOriginal").checked = Boolean(state.showOriginal);
        $("pairText").textContent = state.paired
          ? "当前已配对到 " + state.pairedName + "。更换接收者前请先解除配对。"
          : state.pairingActive
            ? "配对链接剩余约 " + state.pairingRemaining + " 秒。"
            : "生成十分钟有效、仅可使用一次的配对链接。";
      }} catch (error) {{
        toast(error.message, "error");
      }}
    }}

    async function withBusy(button, work) {{
      button.disabled = true;
      try {{ await work(); }} catch (error) {{ toast(error.message, "error"); }}
      finally {{
        button.disabled = false;
        if (button.id === "discordTest" || button.id === "discordRemove") await refresh();
      }}
    }}

    $("tokenForm").addEventListener("submit", (event) => {{
      event.preventDefault();
      withBusy($("saveToken"), async () => {{
      const token = $("token").value.trim();
      if (!token) throw new Error("请先粘贴 Bot Token");
      $("token").value = "";
      await api("token", {{token}});
      $("tokenNote").textContent = "已保存。为安全起见，旧配对已清除。";
      toast("Bot Token 已存入 macOS 钥匙串");
      await refresh();
      }});
    }});

    $("discordForm").addEventListener("submit", (event) => {{
      event.preventDefault();
      withBusy($("saveDiscord"), async () => {{
        const webhookUrl = $("discordWebhook").value.trim();
        if (!webhookUrl) throw new Error("请先粘贴 Discord Webhook URL");
        $("discordWebhook").value = "";
        await api("discord", {{webhookUrl}});
        $("discordNote").textContent = "Webhook 已验证并启用，只会接收之后到达的新消息。";
        toast("Discord Webhook 已存入 macOS 钥匙串");
        await refresh();
      }});
    }});

    $("discordEnabled").addEventListener("change", async (event) => {{
      try {{
        await api("settings", {{discordEnabled: event.target.checked}});
        toast(event.target.checked ? "Discord 通知已启用" : "Discord 通知已停用");
        await refresh();
      }} catch (error) {{
        event.target.checked = !event.target.checked;
        toast(error.message, "error");
      }}
    }});

    $("discordTest").addEventListener("click", () => withBusy($("discordTest"), async () => {{
      await api("test", {{provider: "discord"}});
      toast("Discord 测试通知已发送");
      await refresh();
    }}));

    $("discordRemove").addEventListener("click", () => withBusy($("discordRemove"), async () => {{
      if (!confirm("从 macOS 钥匙串删除 Discord Webhook URL？Telegram 配置不会受影响。")) return;
      await api("discord/remove", {{}});
      $("discordNote").textContent = "Discord Webhook 已移除。";
      toast("Discord Webhook 已删除");
      await refresh();
    }}));

    $("pair").addEventListener("click", () => withBusy($("pair"), async () => {{
      const result = await api("pair", {{}});
      $("pairAnchor").href = result.url;
      $("pairAnchor").textContent = "在 Telegram 中打开并完成配对";
      $("pairLink").dataset.visible = "true";
      await refresh();
    }}));

    $("showOriginal").addEventListener("change", async (event) => {{
      try {{
        await api("settings", {{showOriginal: event.target.checked}});
        toast(event.target.checked ? "后续通知将附带短信原文" : "已恢复隐私默认值");
      }} catch (error) {{
        event.target.checked = !event.target.checked;
        toast(error.message, "error");
      }}
    }});

    $("forwardMode").addEventListener("change", async (event) => {{
      const previous = (await api("status")).forwardMode || "strict";
      const selected = event.target.value;
      if (selected === "all" && !confirm("“所有收到的文本”会把普通短信和 iMessage 原文发送到所有已启用渠道。确定启用吗？")) {{
        event.target.value = previous;
        return;
      }}
      try {{
        await api("settings", {{forwardMode: selected}});
        toast(selected === "strict" ? "已启用严格验证码规则" : selected === "smart" ? "已启用智能验证码规则" : "已启用所有文本转发", selected === "all" ? "error" : "success");
        await refresh();
      }} catch (error) {{
        event.target.value = previous;
        toast(error.message, "error");
      }}
    }});

    $("testPush").addEventListener("click", () => withBusy($("testPush"), async () => {{
      await api("test", {{}});
      toast("测试通知已发送到所有启用渠道");
    }}));

    $("doctor").addEventListener("click", () => withBusy($("doctor"), async () => {{
      const result = await api("doctor");
      $("diagnostics").replaceChildren(...Object.entries(result).map(([name, value]) => {{
        const row = document.createElement("div");
        row.className = "diag";
        const title = document.createElement("strong");
        title.textContent = diagnosticLabels[name] || name;
        const detail = document.createElement("span");
        detail.textContent = (value.ok ? "✓ " : "○ ") + value.detail;
        row.append(title, detail);
        return row;
      }}));
      $("diagnosticDialog").showModal();
    }}));

    $("closeDialog").addEventListener("click", () => $("diagnosticDialog").close());
    $("install").addEventListener("click", () => withBusy($("install"), async () => {{
      if (!confirm("安装为当前用户登录后自动运行？安装完成后，本设置页会关闭并由后台服务接管。")) return;
      await api("install", {{}});
      toast("后台常驻已安装；本页即将关闭");
    }}));
    $("unpair").addEventListener("click", () => withBusy($("unpair"), async () => {{
      if (!confirm("确定解除当前 Telegram 私聊的授权吗？")) return;
      await api("unpair", {{}});
      $("pairLink").dataset.visible = "false";
      toast("Telegram 私聊已解除配对");
      await refresh();
    }}));
    $("reset").addEventListener("click", () => withBusy($("reset"), async () => {{
      if (!confirm("这会永久删除钥匙串中的渠道凭据、配对、运行状态、日志、专用运行时和后台常驻服务。Telegram Token 撤销、Discord 服务端 Webhook 删除及 macOS 权限需要你另行处理。确定继续吗？")) return;
      await api("reset", {{}});
      toast("本机配置已安全移除；本页即将关闭");
    }}));

    refresh();
    setInterval(refresh, 5000);
  </script>
</body>
</html>"""
