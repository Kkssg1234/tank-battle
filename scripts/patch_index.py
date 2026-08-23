"""
patch_index.py - pygbag 构建后对 index.html 的修正脚本

作用：
1. 设置 autorun=1，让游戏加载完成后自动启动，不再强制等待用户点击才能开始
   （pygbag 默认 autorun=0，会卡在 "MEDIA USER ACTION REQUIRED" 等待手势解锁音频）
2. 移除 allow 属性里浏览器不认识的 'monetization' / 'xr' feature，消除控制台警告
3. 强化 "点击开始" 提示文案，避免用户误以为黑屏

用法：
    python scripts/patch_index.py build/web/index.html
"""

import sys
import re


def patch(path: str) -> None:
    with open(path, encoding="utf-8") as f:
        s = f.read()

    orig = s

    # 1) autorun=0 -> autorun=1 （自动启动游戏）
    s = s.replace('config.autorun = 0', 'config.autorun = 1')
    s = s.replace('"autorun": 0', '"autorun": 1')
    # 兼容 pygbag 不同版本写法
    s = re.sub(r'autorun["\s]*[:=]["\s]*0', 'autorun=1', s)

    # 2) 清理 allow 属性中的无效 feature
    #    原：allow="...; monetization; xr-spatial-tracking; ...; xr; cross-origin-isolated"
    #    浏览器不认识的 feature 会触发 "Unrecognized feature" 警告，需整体移除。
    s = s.replace('monetization; ', '')
    s = s.replace('xr-spatial-tracking; ', '')
    s = s.replace('; xr', '')          # 去掉独立的 '; xr'
    s = s.replace(' xr', '')           # 去掉可能残留的 ' xr'
    s = re.sub(r';\s*;', ';', s)       # 合并多余分号
    s = re.sub(r';\s*$', '', s)        # 去掉结尾分号

    # 3) 让 "请点击" 提示更醒目（若模板里有这段提示）
    s = s.replace(
        "Ready to start ! Please click/touch page",
        "点击页面任意位置开始游戏 / Click anywhere to start",
    )

    # 4) 如果模板用 wait_for_click 阻塞，这里直接跳过阻塞 —— 通过注入 UMENG 解锁
    #    pygbag 在 custom_site() 里 while not UME 等待；我们通过把 UME 提前置位来跳过。
    #    在 custom_onload 末尾注入：window.MM && (window.MM.UME = true)
    s = s.replace(
        "console.log(__FILE__, \"custom_onload\")",
        "console.log(__FILE__, \"custom_onload\")\n"
        "        // 主动解锁媒体交互，跳过 \"等待点击\" 阻塞（音频仍受浏览器自动播放策略约束，点击后生效）\n"
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
