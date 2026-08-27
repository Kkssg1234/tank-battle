"""
patch_index.py - pygbag 构建后对 index.html 的修正脚本

修复项（按顺序）：
1. 注入 <!DOCTYPE html>，消除 Quirks Mode（无 DOCTYPE 会让画布用 quirks 布局，高度塌缩→黑屏）
2. 将 autorun 设为 1（构建完成后自动启动，无需等待点击）
3. 将 ume_block 设为 0（跳过"媒体交互/音频"等待，避免卡在点击提示）
4. 修正可能出现的非法 JS：autorun/ume_block 写成 '=' 分隔（如 autorun=1）
   会变成 "Invalid shorthand property initializer" 语法错误，导致整个 config 块解析失败、
   pygbag 读不到存档/画布尺寸、画布停在 1px→黑屏。统一改回合法的 ' : ' 分隔。
5. 确保 html, body 占满视口，使画布 height:100% 能正确解析
6. 清理 allow 属性里浏览器不认识的 feature（消除控制台警告）
7. 让"请点击"提示文案更友好
8. 网页布局美化：两侧留白区域主题化为深蓝科技风 + 画布辉光边框，消除"空白"观感
9. 生产环境关闭 xtermjs 终端覆盖层，减少 JS 开销与字体请求，加快首屏
10. 预连接 CDN，加速 wasm / 字体加载
11. 保留并自托管 browserfs.min.js（pygbag 的 main.js 依赖全局 window.BrowserFS 挂载文件系统；
    外部 CDN 不可用，改为同源绝对地址并随 vendor/cdn 部署）

用法：
    python scripts/patch_index.py build/web/index.html
"""

import re
import sys


def _clean_allow(s: str) -> str:
    """仅清理 <iframe ... allow="..."> 中的无效 feature，避免误伤其它内容。"""
    def repl(m):
        allow = m.group(1)
        for bad in ("monetization", "xr-spatial-tracking", "xr"):
            # 单词边界式移除，避免误删包含这些子串的合法 token
            allow = re.sub(r"(?<![\w-])" + re.escape(bad) + r"(?![\w-])", "", allow)
        allow = re.sub(r";{2,}", ";", allow)
        allow = re.sub(r"^\s*;", "", allow)
        allow = re.sub(r";\s*$", "", allow)
        return 'allow="%s"' % allow.strip()

    return re.sub(r'allow="([^"]*)"', repl, s)


def patch(path: str) -> None:
    with open(path, encoding="utf-8") as f:
        s = f.read()

    orig = s

    # 0) 自托管 pygbag 运行时：把外部 CDN(pygame-web.github.io) 改写为【同源绝对地址】。
    #    用户网络无法访问该 CDN 时整页会卡在 "Downloading..."；运行时已由 vendor/cdn 随仓库部署。
    #    必须用【绝对】同源地址（而非相对 ./cdn/）：vtx.js 内部用 config.cdn + "../vt/" 拼终端路径，
    #    若 config.cdn 是相对路径，会以 vtx.js 自身位置(cdn/vtx.js)为基准再叠加一层 cdn，
    #    解析成 cdn/cdn/vt/ 导致 xterm 404。绝对地址可避免该相对叠加。
    s = s.replace("https://pygame-web.github.io/cdn/", "https://kkssg1234.github.io/tank-battle/cdn/")
    # 0.1) 兜底：清掉任何残留的裸 pygame-web 主机引用（如 preconnect），统一指向同源根。
    s = s.replace("https://pygame-web.github.io", "https://kkssg1234.github.io/tank-battle")

    # 0.2) browserfs 运行时【必须保留并自托管】，绝不能删。
    #      pygbag 的 cpython312/main.js 启动时会检查全局 window.BrowserFS，缺失则报
    #      "PyMain: BrowserFS not found" 且文件系统无法初始化 → 归档解不出 → 游戏卡死。
    #      模板默认从外部 CDN(pygame-web.github.io) 引 browserfs.min.js，用户网络打不开 → 404；
    #      上面 step 0 已把该外部地址改写为同源绝对地址。本步再修掉模板自带的双斜杠
    #      （cookiecutter.cdn 末尾带 "/"，拼接出 "0.9.3//browserfs.min.js"），确保路径干净可命中。
    #      文件本身由 vendor/cdn/0.9.3/browserfs.min.js 随仓库部署
    #      （CI 的 `cp -r vendor/cdn build/web/cdn` 会把它带进产物）。
    s = s.replace("tank-battle/cdn/0.9.3//browserfs", "tank-battle/cdn/0.9.3/browserfs")

    # 1) 注入 DOCTYPE，消除 Quirks Mode（根因之一：画布高度塌缩导致黑屏）
    if not re.match(r"^\s*<!DOCTYPE", s, re.IGNORECASE):
        s = "<!DOCTYPE html>\n" + s

    # 2) autorun: 无论原模板用 ':' 还是 '='，统一为合法 JS 且启用
    s = re.sub(r"autorun\s*[:=]\s*[01]", "autorun : 1", s)

    # 3) ume_block: 关闭媒体交互阻塞（无需点击即可启动）
    s = re.sub(r"ume_block\s*[:=]\s*[01]", "ume_block : 0", s)

    # 4) html/body 占满视口，画布 height:100% 才能正确解析（防黑屏兜底）
    if "html, body" not in s:
        s = s.replace("<style>", "<style>\n        html, body { height: 100%; }\n", 1)

    # 5) 清理 allow 无效 feature（仅作用于 iframe allow 属性）
    s = _clean_allow(s)

    # 6) 友好提示文案（若模板里有这段提示）
    s = s.replace(
        "Ready to start ! Please click/touch page",
        "点击页面任意位置开始游戏 / Click anywhere to start",
    )

    # 7) 统一游戏归档名：pygbag 的 Python 模板 custom_site() 硬编码用
    #    tank_battle.tar.gz（下划线）解包，而 pythons.js 按 config.archive 去下载/挂载。
    #    若两者不一致（如 config.archive 被写成 tank-battle 连字符），运行时就取不到归档、
    #    main.py 缺失、掉进 REPL、加载遮罩永不消失。这里强制归一为 tank_battle。
    s = re.sub(r'archive\s*:\s*"[^"]*"', 'archive : "tank_battle"', s)

    # 7b) 归一 custom_site() 模板里所有「归档名」引用（bundle / fopen / Loading 文本），
    #     使其与 config.archive(=tank_battle) 及实际挂载的 tank_battle.tar.gz 一致。
    #     关键点：CI 上 GitHub 把仓库目录 slugify 成 tank-battle（连字符），模板据此硬编码
    #     bundle = "tank-battle"、fopen("tank-battle.tar.gz")；而 pythons.js 按 config.archive
    #     挂载的是 tank_battle.tar.gz（下划线）。fopen 用连字符名去开下划线文件 → 文件不存在
    #     → 归档解不出 → main.py 缺失 → 页面永远卡在加载。这里把 bundle、fopen 统一归一为
    #     tank_battle，兼容 中文 / 连字符 / 下划线 三种写法。
    #     注意：绝不能动 URL 中的 /tank-battle/（那是 GitHub Pages 的仓库子路径，必须保留连字符）。
    s = re.sub(r'bundle\s*=\s*"[^"]*"', 'bundle = "tank_battle"', s)
    s = re.sub(r'fopen\("([^"]*)\.tar\.gz"', 'fopen("tank_battle.tar.gz"', s)
    s = re.sub(r'fopen\("([^"]*)\.apk"', 'fopen("tank_battle.apk"', s)
    # 兜底：把零散的连字符归档引用（如 Loading 文本 "from tank-battle.apk"）也归一。
    # 这些子串只出现在模板文本里，不会出现在 /tank-battle/cdn 这种 URL 中，可安全替换。
    s = s.replace("tank-battle.apk", "tank_battle.apk").replace("tank-battle.tar.gz", "tank_battle.tar.gz")
    s = re.sub(r'Folder\s*:\s*\S+', 'Folder  : tank_battle', s)

    # 8) 兜底解锁媒体交互，跳过 "等待点击" 阻塞。
    #    pygbag 的 custom_site() 会 while 等待 platform.window.MM.UME 为真才加载游戏。
    #    用独立的 <script> 轮询设置 window.MM.UME=true，避免侵入 custom_onload 导致语法/运行时错误；
    #    并绑定首次交互兜底。用哨兵注释保证幂等，重复运行不会重复注入。
    if "/*__UME_UNLOCK__*/" not in s:
        s = s.replace(
            "</body>",
            '    <script>\n'
            '    /*__UME_UNLOCK__*/\n'
            '    (function () {\n'
            '      function setUME() { try { if (window.MM) { window.MM.UME = true; } } catch (e) {} }\n'
            '      setUME();\n'
            '      var iv = setInterval(function () { setUME(); if (window.MM && window.MM.UME) clearInterval(iv); }, 200);\n'
            '      ["pointerdown", "keydown", "touchstart", "click"].forEach(function (ev) {\n'
            '        window.addEventListener(ev, setUME, { once: true });\n'
            '      });\n'
            '    })();\n'
            '    </script>\n</body>',
            1,
        )

    # 8) 网页布局美化：将画布两侧的留白区域主题化为深蓝科技风（网格 + 径向渐变），
    #    并为画布添加辉光边框，使 16:9 letterbox 看起来是刻意设计而非“空白”。
    #    说明：固定 16:9 内容无法在非 16:9 视口「无变形且无裁切」地填满，
    #    因此采用用户许可的“美化整体呈现”方案，而非拉伸/裁切画面。
    s = s.replace(
        "background-color:powderblue;",
        "overflow: hidden;\n"
        "            background:\n"
        "              linear-gradient(rgba(80,220,255,0.05) 1px, transparent 1px) 0 0 / 40px 40px,\n"
        "              linear-gradient(90deg, rgba(80,220,255,0.05) 1px, transparent 1px) 0 0 / 40px 40px,\n"
        "              radial-gradient(ellipse at center, #0a1430 0%, #050c23 100%);",
    )
    # 画布辉光边框（pygbag 会把画布按 16:9 居中，边框框住画面）
    s = s.replace(
        "border: 0px none;",
        "border: 0px none;\n            box-shadow: 0 0 40px rgba(80,220,255,0.28);\n            border-radius: 6px;",
        1,
    )

    # 9) 生产环境关闭 xtermjs 终端覆盖层：减少 JS 开销与字体请求，加快首屏
    s = re.sub(r'xtermjs\s*[:=]\s*"[01]"', 'xtermjs : "0"', s)

    # 10) 运行时已自托管，不再预连接外部 CDN（外部 CDN 反而是用户网络打不开的根因），
    #     故此处不再注入 pygame-web 的 preconnect，避免无谓的跨域连接失败日志。

    # 11) 网页端清晰度核心：给画布加最近邻缩放，避免浏览器把 960x640 后备缓冲
    #     双线性拉伸到视口导致模糊（image-rendering 不影响鼠标坐标映射）。
    #     保留 width/height:100% 作为 JS 未生效时的兜底（此时等同旧行为）。
    s = s.replace(
        "background-color: transparent;\n            width: 100%;\n"
        "            height: 100%;\n            z-index: 5;",
        "background-color: transparent;\n"
        "            image-rendering: pixelated;\n"
        "            image-rendering: -moz-crisp-edges;\n"
        "            image-rendering: crisp-edges;\n"
        "            width: 100%;\n"
        "            height: 100%;\n"
        "            z-index: 5;",
        1,
    )

    # 12) 注入 fitCanvas：按 3:2 等比 letterbox 设置画布「显示尺寸」并居中，
    #     位图仍正好填满元素（鼠标映射不变），消除非 3:2 视口下的拉伸变形。
    if "fitCanvas" not in s:
        s = s.replace(
            "</body>",
            '    <script>\n'
            '    // 网页端清晰度：按 3:2 等比 letterbox 设置画布显示尺寸（居中、不变形），\n'
            '    // 配合 canvas 的 image-rendering:pixelated 实现最近邻锐利缩放。\n'
            '    (function(){\n'
            '      function fitCanvas(){\n'
            '        var c = document.getElementById("canvas");\n'
            '        if(!c) return;\n'
            '        var vw = window.innerWidth || document.documentElement.clientWidth;\n'
            '        var vh = window.innerHeight || document.documentElement.clientHeight;\n'
            '        if(!vw || !vh) return;\n'
            '        var ar = 3/2;            // 游戏逻辑分辨率 960x640 = 3:2\n'
            '        var w = vw, h = vw / ar;\n'
            '        if(h > vh){ h = vh; w = vh * ar; }\n'
            '        c.style.width = Math.round(w) + "px";\n'
            '        c.style.height = Math.round(h) + "px";\n'
            '      }\n'
            '      window.addEventListener("resize", fitCanvas);\n'
            '      window.addEventListener("load", fitCanvas);\n'
            '      document.addEventListener("fullscreenchange", fitCanvas);\n'
            '      if(document.readyState === "complete" || document.readyState === "interactive"){\n'
            '        fitCanvas();\n'
            '      } else { window.addEventListener("DOMContentLoaded", fitCanvas); }\n'
            '    })();\n'
            '    </script>\n</body>',
            1,
        )

    if s == orig:
        print("WARNING: index.html 未发生变化，请检查 pygbag 模板版本")
    else:
        with open(path, "w", encoding="utf-8") as f:
            f.write(s)
        print(f"patched: {path}")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "build/web/index.html"
    patch(target)
