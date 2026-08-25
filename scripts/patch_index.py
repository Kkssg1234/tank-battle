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

    # 7) 兜底解锁媒体交互，跳过 "等待点击" 阻塞
    #    （音频仍受浏览器自动播放策略约束，首次交互后生效；不影响画面渲染）
    s = s.replace(
        'console.log(__FILE__, "custom_onload")',
        'console.log(__FILE__, "custom_onload")\n'
        "        // 主动解锁媒体交互，跳过 \"等待点击\" 阻塞\n"
        "        try { if (window.MM) { window.MM.UME = true; } } catch(e) { console.warn('UME unlock skip', e); }",
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

    # 10) 预连接 CDN，加速 wasm / 字体首屏加载
    if 'rel="preconnect"' not in s:
        s = s.replace(
            '<link rel="icon"',
            '<link rel="preconnect" href="https://pygame-web.github.io" crossorigin>\n'
            '    <link rel="icon"',
            1,
        )

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
