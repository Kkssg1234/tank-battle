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

    if s == orig:
        print("WARNING: index.html 未发生变化，请检查 pygbag 模板版本")
    else:
        with open(path, "w", encoding="utf-8") as f:
            f.write(s)
        print(f"patched: {path}")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "build/web/index.html"
    patch(target)
