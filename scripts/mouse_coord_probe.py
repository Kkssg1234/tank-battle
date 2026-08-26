"""mouse_coord_probe.py — 鼠标坐标实时探针（诊断 + 演示）

解决「系统鼠标位置 ≠ 游戏内鼠标位置」映射对齐问题的可视化工具，复刻坦克大战的
离屏放大(letterbox)渲染管线：

  显示窗口(原生分辨率)  --smoothscale-->  逻辑画布(960x640)
  系统鼠标坐标(屏幕)    --减去窗口偏移-->  窗口内坐标  ==  pygame.mouse.get_pos()
  窗口内坐标            --减偏移/除缩放-->  逻辑坐标(960x640)  ==  游戏内真正使用的坐标

功能：
  1) 实时读取并显示【操作系统真实光标屏幕坐标】(Windows 用 user32.GetCursorPos)。
  2) 实时读取并显示【游戏内鼠标坐标】：
       - pygame.mouse.get_pos() 返回的「窗口内坐标」(显示分辨率空间)
       - 经 map_mouse 映射后的「逻辑坐标」(960x640 画布空间，游戏代码实际使用的)
  3) 计算并显示映射变换(缩放系数 + 偏移)与各项偏差，验证两者是否正确对齐。
  4) 隐藏操作系统原生指针(pygame.mouse.set_visible(False))，仅显示本程序自定义准星，
     避免双重光标；按 H 可临时切换显示系统指针以做对比，ESC 退出。

运行：python scripts/mouse_coord_probe.py
依赖：pygame（系统 Python 即可）。Windows 下可读取真实系统光标坐标；其它平台会优雅降级。
"""
import os
import sys
import ctypes

import pygame

# 与游戏一致的逻辑分辨率
SCREEN_W, SCREEN_H = 960, 640
TITLE = "Mouse Coordinate Probe"


# ---------------- Windows 原生 API（仅 Windows 可用，其余平台优雅降级）----------------
def get_os_cursor_pos():
    """返回操作系统真实光标屏幕坐标 (x, y)，失败返回 None。"""
    try:
        user32 = ctypes.windll.user32

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        pt = POINT()
        if user32.GetCursorPos(ctypes.byref(pt)):
            return (pt.x, pt.y)
    except Exception:
        pass
    return None


def get_window_rect():
    """返回 pygame 窗口在屏幕上的矩形 (left, top, right, bottom)，失败返回 None。"""
    try:
        info = pygame.display.get_wm_info()
        hwnd = info.get("window")
        if not hwnd:
            return None
        user32 = ctypes.windll.user32

        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                        ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

        r = RECT()
        if user32.GetWindowRect(ctypes.byref(r)):
            return (r.left, r.top, r.right, r.bottom)
    except Exception:
        pass
    return None


def get_desktop_size():
    try:
        user32 = ctypes.windll.user32
        return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    except Exception:
        return 1280, 800


def main():
    pygame.init()
    # 用比逻辑分辨率更大的「显示窗口」复现游戏的离屏放大管线（确保缩放被触发，
    # 以免 1:1 显示掩盖坐标偏移 bug）。
    dw, dh = get_desktop_size()
    disp_w = max(1024, min(dw, 1600))
    disp_h = max(768, min(dh, 1000))
    display = pygame.display.set_mode((disp_w, disp_h))
    pygame.display.set_caption(TITLE)
    offscreen = pygame.Surface((SCREEN_W, SCREEN_H))

    # 复刻游戏的 letterbox 等比适配（与 main._compute_fit 同算法）
    scale = min(disp_w / SCREEN_W, disp_h / SCREEN_H)
    fit_w = int(round(SCREEN_W * scale))
    fit_h = int(round(SCREEN_H * scale))
    fit_x = (disp_w - fit_w) // 2
    fit_y = (disp_h - fit_h) // 2

    def map_mouse(pos):
        """窗口(显示)坐标 -> 逻辑(960)坐标，对应游戏的 Game.map_mouse。"""
        x = (pos[0] - fit_x) / scale
        y = (pos[1] - fit_y) / scale
        return (int(x), int(y))

    font = pygame.font.SysFont(None, 22)
    clock = pygame.time.Clock()
    hide_os = True
    pygame.mouse.set_visible(False)  # 默认隐藏系统指针，仅显示自定义准星

    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                return
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    return
                if e.key == pygame.K_h:  # 切换系统指针显隐，方便对比对齐
                    hide_os = not hide_os
                    pygame.mouse.set_visible(not hide_os)

        disp_pos = pygame.mouse.get_pos()        # 窗口(显示)坐标 = get_pos()
        log_pos = map_mouse(disp_pos)           # 逻辑(960)坐标 = 游戏内使用
        os_pos = get_os_cursor_pos()            # 系统真实屏幕坐标
        win_rect = get_window_rect()
        os_in_win = None
        if os_pos and win_rect:
            os_in_win = (os_pos[0] - win_rect[0], os_pos[1] - win_rect[1])

        # ---------------- 离屏绘制（逻辑坐标空间）----------------
        offscreen.fill((18, 22, 30))
        for gx in range(0, SCREEN_W, 64):
            pygame.draw.line(offscreen, (32, 40, 54), (gx, 0), (gx, SCREEN_H))
        for gy in range(0, SCREEN_H, 64):
            pygame.draw.line(offscreen, (32, 40, 54), (0, gy), (SCREEN_W, gy))

        # 自定义准星：画在「逻辑坐标」处（即游戏内鼠标位置），演示对齐
        cx, cy = log_pos
        cc = (120, 200, 255)
        pygame.draw.line(offscreen, cc, (cx - 12, cy), (cx + 12, cy), 2)
        pygame.draw.line(offscreen, cc, (cx, cy - 12), (cx, cy + 12), 2)
        pygame.draw.circle(offscreen, cc, (cx, cy), 3)

        # 文字面板
        lines = []
        lines.append(f"显示窗口分辨率 : {disp_w} x {disp_h}")
        lines.append(f"缩放/偏移     : scale={scale:.3f}  offset=({fit_x},{fit_y})")
        lines.append(f"系统屏幕坐标  : {os_pos}")
        lines.append(f"系统-窗口坐标 : {os_in_win}")
        lines.append(f"pygame 窗口坐标: {disp_pos}   <- get_pos()")
        lines.append(f"映射后逻辑坐标: {log_pos}   <- 游戏内使用")
        if os_in_win is not None:
            d = (os_in_win[0] - disp_pos[0], os_in_win[1] - disp_pos[1])
            lines.append(f"系统vs窗口偏差 : {d}   (应≈0，否则窗口偏移读取异常)")
        d2 = (disp_pos[0] - log_pos[0], disp_pos[1] - log_pos[1])
        lines.append(f"窗口vs逻辑偏差 : {d2}   (缩放导致, map_mouse 已校正)")
        aligned = abs(d2[0]) < 2 and abs(d2[1]) < 2
        lines.append("映射对齐状态  : " + ("OK 自定义准星==系统光标" if aligned else "检查缩放系数"))
        lines.append("")
        lines.append("[H] 显示/隐藏系统指针    [ESC] 退出")
        y = 14
        for ln in lines:
            offscreen.blit(font.render(ln, True, (220, 230, 240)), (14, y))
            y += 26

        # ---------------- 提交：离屏缩放铺满显示窗口 ----------------
        display.fill((0, 0, 0))
        scaled = pygame.transform.smoothscale(offscreen, (fit_w, fit_h))
        display.blit(scaled, (fit_x, fit_y))
        pygame.display.flip()
        clock.tick(60)


if __name__ == "__main__":
    main()
