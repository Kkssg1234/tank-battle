"""
网页版（pygbag / wasm）「下载到本地」辅助模块
============================================

仅在浏览器（Emscripten）环境生效；桌面端调用会安全 no-op 并返回 False。

实现要点（兼容主流浏览器：Chrome / Firefox / Edge / Safari）：
- 主方案：Blob + URL.createObjectURL 触发原生下载（Safari 同样支持），
  无体积顾虑、体验最稳。
- 兜底方案：data: URI（小文件友好、跨浏览器兼容）；当主方案不可用（如
  window.eval 在某些环境受限）时自动回退。
- 文件名经 ASCII 清洗，避免注入到 JS 字符串字面量。
"""

import base64
import json

try:
    import platform

    _IN_BROWSER = platform.system() == "Emscripten"
except Exception:
    _IN_BROWSER = False


def is_browser():
    """当前是否处于浏览器（wasm）环境。"""
    return _IN_BROWSER


def _safe_filename(name):
    """清洗文件名，仅保留安全字符，避免破坏 JS 字符串/属性。"""
    keep = []
    for ch in name:
        if ch.isalnum() or ch in ("-", "_", ".", " "):
            keep.append(ch)
    out = "".join(keep).strip()
    return out or "download.bin"


def download_bytes(filename, data: bytes):
    """将二进制数据作为文件 filename 下载到用户本地设备。

    返回 True 表示已尝试触发下载；False 表示非浏览器环境或触发失败。
    """
    if not _IN_BROWSER:
        return False
    b64 = base64.b64encode(data).decode("ascii")
    safe_name = _safe_filename(filename)
    # 主方案：Blob + object URL（Safari 也支持），更稳健、无体积顾虑
    try:
        win = platform.window
        js = (
            "(function(){"
            "  var b64 = \"" + b64 + "\";"
            "  var bin = atob(b64);"
            "  var len = bin.length;"
            "  var bytes = new Uint8Array(len);"
            "  for (var i = 0; i < len; i++) { bytes[i] = bin.charCodeAt(i); }"
            "  var blob = new Blob([bytes], {type: 'application/octet-stream'});"
            "  var url = URL.createObjectURL(blob);"
            "  var a = document.createElement('a');"
            "  a.href = url; a.download = \"" + safe_name + "\";"
            "  document.body.appendChild(a); a.click();"
            "  document.body.removeChild(a);"
            "  setTimeout(function() { URL.revokeObjectURL(url); }, 1500);"
            "})();"
        )
        win.eval(js)
        return True
    except Exception:
        # 兜底：data URI（小文件友好，跨浏览器兼容）
        try:
            win = platform.window
            a = win.document.createElement("a")
            a.href = "data:application/octet-stream;charset=utf-8;base64," + b64
            a.download = safe_name
            win.document.body.appendChild(a)
            a.click()
            win.document.body.removeChild(a)
            return True
        except Exception:
            return False


def download_save(game, filename="tank-battle-save.json"):
    """下载当前游戏存档（Game.save_data）为 JSON 文件到本地。

    返回 True 表示已尝试触发下载；False 表示非浏览器环境、或无存档可读。
    """
    if not _IN_BROWSER:
        return False
    try:
        data = json.dumps(
            getattr(game, "save_data", {}), ensure_ascii=False, indent=2
        ).encode("utf-8")
    except Exception:
        return False
    return download_bytes(filename, data)
