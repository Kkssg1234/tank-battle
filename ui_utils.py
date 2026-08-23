"""
UI工具模块 - 按钮、文字绘制、背景渲染等通用UI组件
"""
import os

import pygame
from constants import *


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
        """绘制按钮（设计系统升级版：硬阴影 + 顶部高光 + hover 抬升 + 发光描边）"""
        r = self.rect
        # hover 时整体上移（仅视觉，不影响 self.rect 点击区）
        lift = 0 if self.disabled else (UI_BTN_LIFT if self.hovered else 0)

        if self.disabled:
            bg_color = self.disabled_color
            border_color = (60, 60, 75)
        elif self.hovered:
            bg_color = self.hover_color
            border_color = (150, 195, 255)
        else:
            bg_color = self.color
            border_color = self.border_color

        # 1) 底部硬阴影（hover 时加深，制造抬升感）
        if not self.disabled:
            sh_alpha = UI_SHADOW_ALPHA + (50 if self.hovered else 0)
            sh = pygame.Surface((r.width, r.height), pygame.SRCALPHA)
            pygame.draw.rect(sh, (0, 0, 0, sh_alpha), sh.get_rect(), border_radius=UI_RADIUS_MD)
            screen.blit(sh, (r.x, r.y + 4))

        # 2) 按钮主体（hover 上移）
        body = r.move(0, -lift)
        pygame.draw.rect(screen, bg_color, body, border_radius=UI_RADIUS_MD)
        # 3) 顶部高光条（半透明白，制造立体光泽）
        hi_rect = pygame.Rect(body.x + 4, body.y + 3, body.width - 8, max(3, body.height // 4))
        hi_surf = pygame.Surface((hi_rect.width, hi_rect.height), pygame.SRCALPHA)
        pygame.draw.rect(hi_surf, (255, 255, 255, 40), hi_surf.get_rect(),
                         border_radius=UI_RADIUS_SM)
        screen.blit(hi_surf, hi_rect.topleft)
        # 4) 描边
        pygame.draw.rect(screen, border_color, body, width=2, border_radius=UI_RADIUS_MD)
        # 5) 文字
        font = fonts.get(self.font_size, fonts[FONT_M])
        text_surf = font.render(self.text, True, self.text_color)
        text_rect = text_surf.get_rect(center=body.center)
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
    """绘制深蓝色科技风背景（设计系统升级版：垂直渐变 + 顶部光带 + 角落辉光）。
    背景为静态内容，预烘焙到 _BG_CACHE，每帧只做一次 blit，避免逐帧重绘数百条线。"""
    global _BG_CACHE
    if _BG_CACHE is None:
        surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        # 1) 垂直渐变底色（上深下稍亮，营造纵深）
        top = UI_BG_DEEP
        bot = (16, 30, 66)
        for y in range(SCREEN_HEIGHT):
            t = y / SCREEN_HEIGHT
            c = (int(top[0] + (bot[0] - top[0]) * t),
                 int(top[1] + (bot[1] - top[1]) * t),
                 int(top[2] + (bot[2] - top[2]) * t))
            pygame.draw.line(surf, c, (0, y), (SCREEN_WIDTH, y))

        # 2) 顶部光带（一条更亮的横向高光，强化视觉焦点）
        band = pygame.Surface((SCREEN_WIDTH, 6), pygame.SRCALPHA)
        band.fill((COLOR_CYAN[0], COLOR_CYAN[1], COLOR_CYAN[2], 30))
        surf.blit(band, (0, 0))

        # 3) 网格线（更淡，不抢主体）
        grid_size = 40
        grid_col = (14, 26, 56)
        for x in range(0, SCREEN_WIDTH, grid_size):
            pygame.draw.line(surf, grid_col, (x, 0), (x, SCREEN_HEIGHT), 1)
        for y in range(0, SCREEN_HEIGHT, grid_size):
            pygame.draw.line(surf, grid_col, (0, y), (SCREEN_WIDTH, y), 1)

        # 4) 装饰性边框光点（保留原有点阵，呼应科技风）
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
    pygame.draw.rect(hi, (255, 255, 255, 22), hi.get_rect(), border_radius=UI_RADIUS_SM)
    screen.blit(hi, (x + 4, y + 3))
    # 4) 描边
    pygame.draw.rect(screen, UI_CARD_BORDER, (x, y, width, height),
                     width=2, border_radius=UI_RADIUS_LG)


def draw_tank_icon(screen, x, y, color, size=48, unlocked=True):
    """绘制简易坦克图标（剪影）"""
    cx, cy = x + size // 2, y + size // 2
    if not unlocked:
        color = COLOR_DARK_GRAY

    # 坦克车身
    body_w, body_h = int(size * 0.7), int(size * 0.45)
    body_rect = pygame.Rect(cx - body_w // 2, cy - body_h // 2 + int(size * 0.08),
                            body_w, body_h)
    pygame.draw.rect(screen, color, body_rect, border_radius=4)

    # 履带
    track_h = int(size * 0.12)
    pygame.draw.rect(screen, COLOR_DARK_GRAY if unlocked else (40, 40, 40),
                     (cx - body_w // 2 - int(size * 0.05), cy - body_h // 2 + int(size * 0.08) - track_h,
                      body_w + int(size * 0.1), track_h), border_radius=3)
    pygame.draw.rect(screen, COLOR_DARK_GRAY if unlocked else (40, 40, 40),
                     (cx - body_w // 2 - int(size * 0.05), cy + body_h // 2 + int(size * 0.08),
                      body_w + int(size * 0.1), track_h), border_radius=3)

    # 炮塔
    turret_r = int(size * 0.18)
    pygame.draw.circle(screen, color, (cx, cy - int(size * 0.05)), turret_r)

    # 炮管
    barrel_w, barrel_h = int(size * 0.08), int(size * 0.35)
    pygame.draw.rect(screen, color,
                     (cx - barrel_w // 2, cy - int(size * 0.05) - barrel_h,
                      barrel_w, barrel_h), border_radius=2)


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
