"""
UI工具模块 - 按钮、文字绘制、背景渲染等通用UI组件
"""
import os
import math
import random

import pygame
from constants import *
from particles import ui_emit_hover_spark


class Button:
    """通用按钮类"""
    def __init__(self, x, y, width, height, text, font_size=FONT_M,
                 color=COLOR_BTN, hover_color=COLOR_BTN_HOVER,
                 text_color=COLOR_WHITE, border_color=COLOR_BTN_BORDER,
                 disabled=False, disabled_color=COLOR_BTN_DISABLED):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.font_size = font_size
        self.color = color
        self.hover_color = hover_color
        self.text_color = text_color
        self.border_color = border_color
        self.disabled = disabled
        self.disabled_color = disabled_color
        self.hovered = False

    def handle_event(self, event):
        """处理事件，返回是否被点击"""
        if self.disabled:
            return False
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                return True
        return False

    def draw(self, screen, fonts):
        """绘制按钮（暗色钢铁科技风：圆角主体 + 顶部内阴影 + hover 外发光 + 文字提亮）"""
        r = self.rect

        # 禁用态：主体色再降 20%（RGB 各分量 ×0.8），文字变暗，不发光
        if self.disabled:
            bg_color = tuple(max(0, int(c * 0.8)) for c in self.disabled_color[:3])
            border_color = tuple(max(0, int(c * 0.8)) for c in COLOR_BTN_BORDER[:3])
            text_color = (110, 110, 115)
            body = r                              # 禁用不抬升
            glow = False
            text_lift = 0
        else:
            # hover 时整体上移 1px（仅视觉，不影响点击区）
            lift = 1 if self.hovered else 0
            bg_color = self.hover_color if self.hovered else self.color
            border_color = COLOR_BTN_BORDER
            text_color = COLOR_AMBER if self.hovered else COLOR_WHITE
            body = r.move(0, -lift)
            glow = self.hovered
            text_lift = lift

        # 1) hover 外描边：单层琥珀包围（去霓虹白光，仅强调描边）
        if glow:
            pad = 2
            g_surf = pygame.Surface((r.width + pad * 2, r.height + pad * 2), pygame.SRCALPHA)
            pygame.draw.rect(g_surf, COLOR_AMBER, g_surf.get_rect(),
                             width=1, border_radius=UI_RADIUS_MD + pad)
            screen.blit(g_surf, (r.x - pad, r.y - pad))
            # 悬停火花（UI 粒子，主循环每帧统一更新/绘制）
            if random.random() < 0.25:
                ui_emit_hover_spark(r.centerx, r.y, COLOR_AMBER)

        # 2) 按钮主体（硬朗圆角）
        pygame.draw.rect(screen, bg_color, body, border_radius=UI_RADIUS_MD)

        # 3) 内高光：按钮内部上方画一条 2px 钢蓝半透明线，模拟凸起边缘
        inner_hi = pygame.Surface((body.width - 6, 2), pygame.SRCALPHA)
        inner_hi.fill((91, 127, 168, 36))
        screen.blit(inner_hi, (body.x + 3, body.y + 2))

        # 4) 描边（hover 转琥珀，否则钢蓝边框）
        pygame.draw.rect(screen, COLOR_AMBER if glow else border_color,
                         body, width=2, border_radius=UI_RADIUS_MD)

        # 5) 文字（hover 时颜色已变为金、且随按钮上移 1px）
        font = fonts.get(self.font_size, fonts[FONT_M])
        text_surf = font.render(self.text, True, text_color)
        text_rect = text_surf.get_rect(centerx=body.centerx, centery=body.centery - text_lift)
        screen.blit(text_surf, text_rect)


def draw_text(screen, text, x, y, fonts, font_size=FONT_M, color=COLOR_WHITE,
              center=False, center_x=False, center_y=False):
    """绘制文字"""
    font = fonts.get(font_size, fonts[FONT_M])
    text_surf = font.render(text, True, color)
    text_rect = text_surf.get_rect()
    if center:
        text_rect.center = (x, y)
    else:
        if center_x:
            text_rect.centerx = x
        else:
            text_rect.x = x
        if center_y:
            text_rect.centery = y
        else:
            text_rect.y = y
    screen.blit(text_surf, text_rect)
    return text_rect


# 背景缓存：每帧重复绘制 640+ 条线代价很高（wasm 浏览器尤其明显），
# 预烘焙一次后每帧仅一次 blit。
_BG_CACHE = None


def draw_bg(screen):
    """绘制暗色钢铁科技风背景（垂直渐变 + 顶部光带 + 角落辉光）。
    背景为静态内容，预烘焙到 _BG_CACHE，每帧只做一次 blit，避免逐帧重绘数百条线。"""
    global _BG_CACHE
    if _BG_CACHE is None:
        surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        # 1) 垂直渐变底色（上深黑、下略带暖灰，营造钢铁纵深）
        top = UI_BG_DEEP                       # (11,18,32) 深海军蓝
        bot = (16, 26, 46)                    # 底部略亮蓝，强化纵深
        for y in range(SCREEN_HEIGHT):
            t = y / SCREEN_HEIGHT
            c = (int(top[0] + (bot[0] - top[0]) * t),
                 int(top[1] + (bot[1] - top[1]) * t),
                 int(top[2] + (bot[2] - top[2]) * t))
            pygame.draw.line(surf, c, (0, y), (SCREEN_WIDTH, y))

        # 2) 顶部光带（极淡冰蓝高光，强化视觉焦点，不抢主体）
        band = pygame.Surface((SCREEN_WIDTH, 6), pygame.SRCALPHA)
        band.fill((COLOR_CYAN[0], COLOR_CYAN[1], COLOR_CYAN[2], 22))
        surf.blit(band, (0, 0))

        # 3) 网格线（极淡钢灰，几乎不可见，呼应金属面板）
        grid_size = 40
        grid_col = (22, 36, 58)               # 极淡钢蓝网格
        for x in range(0, SCREEN_WIDTH, grid_size):
            pygame.draw.line(surf, grid_col, (x, 0), (x, SCREEN_HEIGHT), 1)
        for y in range(0, SCREEN_HEIGHT, grid_size):
            pygame.draw.line(surf, grid_col, (0, y), (SCREEN_WIDTH, y), 1)

        # 4) 装饰性边框光点（冰蓝点阵，呼应科技风，降低亮度避免浮夸）
        for i in range(0, SCREEN_WIDTH, 80):
            pygame.draw.circle(surf, COLOR_CYAN, (i, 8), 2)
            pygame.draw.circle(surf, COLOR_CYAN, (i, SCREEN_HEIGHT - 9), 2)
        for i in range(0, SCREEN_HEIGHT, 80):
            pygame.draw.circle(surf, COLOR_CYAN, (8, i), 2)
            pygame.draw.circle(surf, COLOR_CYAN, (SCREEN_WIDTH - 9, i), 2)

        _BG_CACHE = surf
    screen.blit(_BG_CACHE, (0, 0))


def draw_corner_logo(screen, fonts):
    """绘制角落的浪尖儿大学生社区字样"""
    draw_text(screen, "浪尖儿大学生社区", SCREEN_WIDTH - 20, SCREEN_HEIGHT - 30,
              fonts, FONT_S, COLOR_CYAN, center=False)
    # 手动右对齐
    font = fonts[FONT_S]
    text_surf = font.render("浪尖儿大学生社区", True, COLOR_CYAN)
    w = text_surf.get_width()
    screen.blit(text_surf, (SCREEN_WIDTH - w - 15, SCREEN_HEIGHT - 35))


def load_fonts():
    """加载字体（双端兼容）。

    浏览器（pygbag / wasm）环境：使用随包打包的 assets/simhei.ttf（黑体，含简体中文），
    保证界面中文正常显示。本地环境：优先系统字体，找不到再回退。
    """
    # 判断是否处于浏览器环境
    in_browser = False
    try:
        import platform as _platform_mod

        if _platform_mod.system() == "Emscripten":
            in_browser = True
    except Exception:
        in_browser = False

    fonts = {}
    sizes = [FONT_XS, FONT_S, FONT_M, FONT_L, FONT_XL, FONT_XXL]

    # 定位中文字体文件（双端通用，做多路径回退）：
    # - 本地端：优先项目根 assets/simhei.ttf，其次脚本同目录
    # - 浏览器端（pygbag 把项目根打进 assets/ 子目录）：
    #     __file__ 指向 assets/main.py，故字体真实路径为 assets/assets/simhei.ttf
    try:
        here = os.path.dirname(os.path.abspath(__file__))
    except Exception:
        here = "."
    font_candidates_paths = [
        os.path.join(here, "assets", "simhei.ttf"),   # 本地: 脚本同目录/assets
        os.path.join(here, "simhei.ttf"),             # 本地: 脚本同目录
        os.path.join(here, "..", "assets", "simhei.ttf"),  # 浏览器: assets/main.py -> 包根/assets
        os.path.join("assets", "assets", "simhei.ttf"),     # 浏览器: 相对包根
        os.path.join("assets", "simhei.ttf"),               # 浏览器: 相对包根(平铺)
    ]

    def _find_cn_font():
        for p in font_candidates_paths:
            try:
                if os.path.exists(p):
                    return p
            except Exception:
                continue
        return None

    cn_font = _find_cn_font()

    if in_browser:
        # 网页端：直接尝试用打包内的中文字体路径加载（不依赖 exists 判断，
        # 因为 wasm 虚拟文件系统下 os.path.exists 可能不可靠）
        browser_font_paths = [
            "assets/assets/simhei.ttf",   # pygbag 把项目根打进 assets/，故字体在 assets/assets/
            "assets/simhei.ttf",
            cn_font if cn_font else "assets/assets/simhei.ttf",
        ]
        loaded = False
        chosen = None
        for fp in browser_font_paths:
            try:
                # 先用第一个 size 试加载，确认路径有效
                pygame.font.Font(fp, sizes[0])
                chosen = fp
                loaded = True
                break
            except Exception:
                continue
        for size in sizes:
            try:
                fonts[size] = pygame.font.Font(chosen, size) if chosen else pygame.font.SysFont(None, size)
            except Exception:
                fonts[size] = pygame.font.SysFont(None, size)
        return fonts

    # 本地端：优先系统字体，回退到打包内的 simhei.ttf，再回退内置字体
    font_candidates = [
        "microsoftyahei", "msyh", "simhei", "simsun", "kaiti",
        "Microsoft YaHei", "SimHei", "SimSun", "KaiTi", "arial"
    ]
    selected_font = None
    for name in font_candidates:
        try:
            path = pygame.font.match_font(name)
            if path:
                selected_font = path
                break
        except Exception:
            continue
    if not selected_font and cn_font:
        selected_font = cn_font

    for size in sizes:
        if selected_font:
            try:
                fonts[size] = pygame.font.Font(selected_font, size)
            except Exception:
                fonts[size] = pygame.font.SysFont(None, size)
        else:
            fonts[size] = pygame.font.SysFont(None, size)
    return fonts


def draw_panel(screen, x, y, width, height, alpha=220):
    """绘制半透明面板（设计系统升级版：卡片层次 + 顶部高光 + 阴影 + 描边）"""
    # 1) 底部阴影
    sh = pygame.Surface((width, height), pygame.SRCALPHA)
    pygame.draw.rect(sh, (0, 0, 0, 90), sh.get_rect(), border_radius=UI_RADIUS_LG)
    screen.blit(sh, (x, y + 4))
    # 2) 主体（半透明卡片底色）
    panel_surf = pygame.Surface((width, height), pygame.SRCALPHA)
    panel_surf.fill((UI_CARD[0], UI_CARD[1], UI_CARD[2], alpha))
    screen.blit(panel_surf, (x, y))
    # 3) 顶部高光条
    hi = pygame.Surface((width - 8, max(3, height // 10)), pygame.SRCALPHA)
    pygame.draw.rect(hi, (91, 127, 168, 22), hi.get_rect(), border_radius=UI_RADIUS_SM)
    screen.blit(hi, (x + 4, y + 3))
    # 4) 描边
    pygame.draw.rect(screen, UI_CARD_BORDER, (x, y, width, height),
                     width=2, border_radius=UI_RADIUS_LG)


def draw_glass_panel(screen, x, y, w, h, alpha=200):
    """绘制玻璃拟态面板（暗色钢铁风）：圆角半透明底色 + 顶部高光 + 底部暗边 + 1px 细描边。"""
    # 1) 圆角矩形底色（RGBA，使用 COLOR_PANEL_BG 的 RGB 与传入 alpha）
    base = COLOR_PANEL_BG
    body_surf = pygame.Surface((w, h), pygame.SRCALPHA)
    body_surf.fill((base[0], base[1], base[2], alpha))
    screen.blit(body_surf, (x, y))

    # 2) 顶部 1px 钢蓝高光线
    hi = pygame.Surface((w - 2, 1), pygame.SRCALPHA)
    hi.fill((91, 127, 168, 50))
    screen.blit(hi, (x + 1, y))

    # 3) 底部 1px 暗边
    dark = pygame.Surface((w - 2, 1), pygame.SRCALPHA)
    dark.fill((0, 0, 0, 80))
    screen.blit(dark, (x + 1, y + h - 1))

    # 4) 外框 1px 细线（白钢边框）
    pygame.draw.rect(screen, COLOR_BTN_BORDER, (x, y, w, h),
                     width=1, border_radius=UI_RADIUS_MD)


def draw_tank_icon(screen, x, y, color, size=48, unlocked=True, style=TANK_STYLE_STANDARD):
    """绘制简易坦克图标（剪影），按 style 与游戏内 Sprite 同步差异化。"""
    cx, cy = x + size // 2, y + size // 2
    if not unlocked:
        color = COLOR_DARK_GRAY

    # 车身尺寸风格化（仅视觉，不改动任何逻辑/碰撞）
    if style == TANK_STYLE_SCOUT:
        body_w, body_h = int(size * 0.62), int(size * 0.52)
    elif style == TANK_STYLE_HEAVY:
        body_w, body_h = int(size * 0.82), int(size * 0.40)
    else:
        body_w, body_h = int(size * 0.70), int(size * 0.45)
    body_y = cy - body_h // 2 + int(size * 0.08)
    body_rect = pygame.Rect(cx - body_w // 2, body_y, body_w, body_h)

    # 履带（上下两条）
    track_h = int(size * 0.12)
    track_color = COLOR_DARK_GRAY if unlocked else (40, 40, 40)
    for ty in (body_y - track_h, body_y + body_h):
        pygame.draw.rect(screen, track_color,
                         (cx - body_w // 2 - int(size * 0.05), ty,
                          body_w + int(size * 0.1), track_h), border_radius=3)

    # 车身主体
    pygame.draw.rect(screen, color, body_rect, border_radius=4)

    # 侧边装甲条纹（深 30%）
    stripe = (int(color[0] * 0.70), int(color[1] * 0.70), int(color[2] * 0.70))
    inset = max(2, int(size * 0.06))
    pygame.draw.line(screen, stripe,
                     (body_rect.left + inset, body_rect.top + body_h * 0.30),
                     (body_rect.left + inset, body_rect.bottom - body_h * 0.30), 2)
    pygame.draw.line(screen, stripe,
                     (body_rect.right - inset, body_rect.top + body_h * 0.30),
                     (body_rect.right - inset, body_rect.bottom - body_h * 0.30), 2)

    # KZY：车身金色 2px 描边
    if style == TANK_STYLE_KZY:
        pygame.draw.rect(screen, COLOR_GOLD, body_rect, width=2, border_radius=4)

    # 炮塔
    turret_r = int(size * 0.18)
    tcx, tcy = cx, cy - int(size * 0.05)
    pygame.draw.circle(screen, color, (tcx, tcy), turret_r)

    # 炮塔风格化细节
    if style == TANK_STYLE_HEAVY:
        rec_w, rec_h = int(size * 0.22), int(size * 0.15)
        pygame.draw.rect(screen, (int(color[0] * 0.70), int(color[1] * 0.70), int(color[2] * 0.70)),
                         (tcx - rec_w // 2, tcy - turret_r - rec_h + int(size * 0.04), rec_w, rec_h),
                         border_radius=2)
    elif style == TANK_STYLE_SNIPER:
        qu = max(2, int(turret_r * 0.5))
        pygame.draw.line(screen, (235, 235, 240), (tcx - qu, tcy), (tcx + qu, tcy), 1)
        pygame.draw.line(screen, (235, 235, 240), (tcx, tcy - qu), (tcx, tcy + qu), 1)
    elif style == TANK_STYLE_KZY:
        t = turret_r * 0.8
        pygame.draw.polygon(screen, COLOR_GOLD, [
            (tcx, tcy - t), (tcx + t * 0.86, tcy + t * 0.5), (tcx - t * 0.86, tcy + t * 0.5),
        ])

    # 炮管（按风格定长/粗）
    if style == TANK_STYLE_SCOUT:
        barrel_w, barrel_h = int(size * 0.07), int(size * 0.42)
    elif style == TANK_STYLE_HEAVY:
        barrel_w, barrel_h = int(size * 0.16), int(size * 0.22)
    elif style == TANK_STYLE_SNIPER:
        barrel_w, barrel_h = int(size * 0.10), int(size * 0.48)
    else:
        barrel_w, barrel_h = int(size * 0.08), int(size * 0.35)
    pygame.draw.rect(screen, color,
                     (tcx - barrel_w // 2, tcy - barrel_h,
                      barrel_w, barrel_h), border_radius=2)


# ===========================================================================
# 矢量图标（2026-08-24）：用 pygame 形状绘制，避免依赖 emoji 字形
# pygame 使用 Monochrome 字体，emoji（❤️/💀/🎮…）在网页/本地均无法渲染，
# 会留下空格占位。这些图标保证双端一致显示。
# ===========================================================================
def draw_heart(screen, x, y, size, color, filled=True, width=2):
    """在 (x,y) 为左上角、size×size 区域内绘制心形。filled=False 为空心（空血槽）。"""
    s = size
    lobe_r = s * 0.25
    cy = y + s * 0.33
    cx1 = x + s * 0.25
    cx2 = x + s * 0.75
    tip_x = x + s * 0.5
    tip_y = y + s
    if filled:
        pygame.draw.circle(screen, color, (cx1, cy), lobe_r)
        pygame.draw.circle(screen, color, (cx2, cy), lobe_r)
        pygame.draw.polygon(screen, color, [(x, cy), (x + s, cy), (tip_x, tip_y)])
    else:
        pygame.draw.circle(screen, color, (cx1, cy), lobe_r, width=width)
        pygame.draw.circle(screen, color, (cx2, cy), lobe_r, width=width)
        pygame.draw.polygon(screen, color, [(x, cy), (x + s, cy), (tip_x, tip_y)], width=width)


def draw_hearts(screen, x, y, count, max_count=None, color=COLOR_RED,
                size=18, gap=4, empty_color=(90, 100, 130)):
    """绘制一排心形血槽：count 个实心 + (max_count-count) 个空心。"""
    total = max_count if max_count is not None else count
    total = max(total, count)
    for i in range(total):
        hx = x + i * (size + gap)
        if i < count:
            draw_heart(screen, hx, y, size, color, filled=True)
        else:
            draw_heart(screen, hx, y, size, empty_color, filled=False)


def draw_lock(screen, x, y, size, color):
    """在 (x,y) 为左上角绘制小锁图标（未解锁提示）。"""
    bw, bh = size, int(size * 0.78)
    bx, by = x, y + int(size * 0.22)
    pygame.draw.rect(screen, color, (bx, by, bw, bh), border_radius=3)
    sh = int(size * 0.55)
    pygame.draw.arc(screen, color, (x + (size - sh) // 2, by - sh // 2, sh, sh),
                    math.radians(180), math.radians(360),
                    width=max(2, size // 10))
    pygame.draw.circle(screen, (0, 0, 0), (x + size // 2, by + bh // 2),
                       max(1, size // 12))


def draw_shield(screen, x, y, size, color):
    """在 (x,y) 为左上角绘制小盾牌图标（护盾道具）。"""
    w = size
    h = int(size * 1.15)
    pts = [
        (x + w // 2, y),
        (x + w, y + h * 0.30),
        (x + w * 0.82, y + h),
        (x + w // 2, y + h * 0.82),
        (x + w * 0.18, y + h),
        (x, y + h * 0.30),
    ]
    pygame.draw.polygon(screen, color, pts)
    pygame.draw.circle(screen, (0, 0, 0), (x + w // 2, y + h * 0.45),
                       max(1, size // 10))


def draw_warning(screen, x, y, size, color):
    """在 (x,y) 为左上角绘制三角警告图标（友军伤害提示）。"""
    pts = [(x + size // 2, y), (x + size, y + size), (x, y + size)]
    pygame.draw.polygon(screen, color, pts)
    pygame.draw.rect(screen, (0, 0, 0), (x + size // 2 - 1, y + size * 0.32,
                                         2, size * 0.34), border_radius=1)
    pygame.draw.circle(screen, (0, 0, 0), (x + size // 2, y + size * 0.82), 1)


# ===========================================================================
# 设计系统组件（2026-08-23 美术优化新增）
# ===========================================================================
def draw_card(screen, x, y, width, height, highlight=False, alpha=235):
    """绘制卡片（浮起表面层）：底色 + 顶部高光 + 阴影 + 描边。
    highlight=True 时用金色强调描边（选中态）。"""
    # 底部阴影
    sh = pygame.Surface((width, height), pygame.SRCALPHA)
    pygame.draw.rect(sh, (0, 0, 0, 100), sh.get_rect(), border_radius=UI_RADIUS_LG)
    screen.blit(sh, (x, y + 5))
    # 主体
    card = pygame.Surface((width, height), pygame.SRCALPHA)
    card.fill((UI_CARD[0], UI_CARD[1], UI_CARD[2], alpha))
    screen.blit(card, (x, y))
    # 顶部高光条
    hi = pygame.Surface((width - 8, max(3, height // 10)), pygame.SRCALPHA)
    pygame.draw.rect(hi, (255, 255, 255, 26), hi.get_rect(), border_radius=UI_RADIUS_SM)
    screen.blit(hi, (x + 4, y + 3))
    # 描边（选中金色 / 常规柔和蓝）
    border = UI_CARD_BORDER_HI if highlight else UI_CARD_BORDER
    pygame.draw.rect(screen, border, (x, y, width, height),
                     width=2 if not highlight else 3, border_radius=UI_RADIUS_LG)


def draw_badge(screen, x, y, text, fonts, bg, fg, font_size=FONT_XS):
    """绘制胶囊型徽章（左对齐起点 x, y 为左上角）。返回徽章宽度。"""
    font = fonts.get(font_size, fonts[FONT_XS])
    text_surf = font.render(text, True, fg)
    pad_x, pad_y = 10, 4
    w = text_surf.get_width() + pad_x * 2
    h = text_surf.get_height() + pad_y * 2
    rect = pygame.Rect(x, y, w, h)
    pygame.draw.rect(screen, bg, rect, border_radius=h // 2)
    pygame.draw.rect(screen, fg, rect, width=1, border_radius=h // 2)
    screen.blit(text_surf, (x + pad_x, y + pad_y))
    return w


def draw_progress_bar(screen, x, y, width, height, ratio, color, bg=None):
    """绘制进度条。ratio∈[0,1]。bg 为槽底色（默认深底）。"""
    ratio = max(0.0, min(1.0, ratio))
    if bg is None:
        bg = (10, 20, 40)
    # 槽底
    pygame.draw.rect(screen, bg, (x, y, width, height), border_radius=height // 2)
    pygame.draw.rect(screen, UI_CARD_BORDER, (x, y, width, height),
                     width=1, border_radius=height // 2)
    # 填充
    fw = int((width - 4) * ratio)
    if fw > 0:
        pygame.draw.rect(screen, color,
                         (x + 2, y + 2, fw, height - 4),
                         border_radius=max(1, (height - 4) // 2))
        # 填充顶部高光
        hi = pygame.Surface((fw, max(2, (height - 4) // 3)), pygame.SRCALPHA)
        pygame.draw.rect(hi, (255, 255, 255, 50), hi.get_rect(),
                         border_radius=max(1, (height - 4) // 4))
        screen.blit(hi, (x + 2, y + 3))


def draw_glow_accent(screen, cx, cy, text, fonts, font_size, color):
    """绘制带辉光的强调文字（标题用）：先画一层放大半透明底，再画实色字。"""
    font = fonts.get(font_size, fonts[FONT_M])
    # 辉光底（偏移四方向画半透明字，模拟发光）
    glow_surf = font.render(text, True, color)
    glow = pygame.Surface(glow_surf.get_size(), pygame.SRCALPHA)
    glow.blit(glow_surf, (0, 0))
    glow.set_alpha(UI_GLOW_ALPHA)
    for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2)]:
        r = glow_surf.get_rect(center=(cx, cy))
        screen.blit(glow, r.move(dx, dy).topleft)
    # 实色字
    text_surf = font.render(text, True, color)
    text_rect = text_surf.get_rect(center=(cx, cy))
    screen.blit(text_surf, text_rect)


def draw_divider(screen, x, y, width, color=None):
    """绘制分隔线（柔和）。"""
    if color is None:
        color = UI_CARD_BORDER
    pygame.draw.line(screen, color, (x, y), (x + width, y), 1)
