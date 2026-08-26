"""
各个游戏界面模块
"""
import pygame
import math
import random
from constants import *
from level_config import TOTAL_LEVELS, get_level_config
from ui_utils import (Button, draw_text, draw_bg, draw_corner_logo, draw_panel,
                      draw_glass_panel,
                      draw_tank_icon, draw_card, draw_badge, draw_progress_bar,
                      draw_glow_accent, draw_divider,
                      draw_hearts, draw_lock, draw_shield, draw_warning)
from vfx import draw_glow, draw_vignette
from save_manager import SaveManager, ScoreSystem
from game_world import GameWorld, TwoPlayerGameWorld, CarnivalGameWorld
from controls import ControlState
from level_manager import LevelManager
from powerup import (POWERUP_NAMES, POWERUP_COLORS,
                     POWERUP_DURATION, PERMA_BUFF_THRESHOLD)
from web_download import is_browser, download_save


# ===== 浏览器环境判定（与 save_manager / ui_utils 一致）=====
try:
    import platform as _platform_mod

    _IN_BROWSER = _platform_mod.system() == "Emscripten"
except Exception:
    _IN_BROWSER = False


# ===== 双端存档读写辅助（浏览器/本地通用）=====
# 统一从 Game 持有的存档对象读取，避免在浏览器端反复调用同步 load() 导致进度丢失。
def get_save(game):
    """读取当前存档（优先用 Game 已加载的对象）。"""
    return getattr(game, "save_data", SaveManager.load())


def persist_save(game, data):
    """写回存档（双端通用）：更新内存对象并落盘。"""
    game.save_data = data
    SaveManager.save(data)
    # 浏览器端（wasm）需额外异步保存（platform.storage）
    try:
        import platform as _pm

        if _pm.system() == "Emscripten":
            import asyncio

            asyncio.ensure_future(SaveManager.async_save(data))
    except Exception:
        pass


# ===== 统一操作系统：控制意图构造（人类输入 → ControlState）=====
# 与 EnemyTank.decide_control 共用 ControlState，保证「AI 与人类操作一致」。
def build_p1_control(keys, mouse_down, dragging, drag_start, drag_cur, player):
    """单人/狂欢模式玩家控制：A/D 转向、W/S 沿炮塔前进/后退、鼠标左键开火、
    鼠标短拖瞄准 / 长拖前进（>DRAG_MOVE_THRESHOLD）。"""
    ctrl = ControlState()
    # 键盘转向（A/D 或 方向键左右）
    if keys[pygame.K_a] or keys[pygame.K_LEFT]:
        ctrl.turn -= 1
    if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
        ctrl.turn += 1
    # 键盘油门（W 前进 / S 后退，沿炮塔方向）
    kt = 0
    if keys[pygame.K_w] or keys[pygame.K_UP]:
        kt += 1
    if keys[pygame.K_s] or keys[pygame.K_DOWN]:
        kt -= 1
    ctrl.throttle = kt

    if dragging and player.alive:
        dx = drag_cur[0] - drag_start[0]
        dy = drag_cur[1] - drag_start[1]
        d = math.hypot(dx, dy)
        if d > DRAG_MOVE_THRESHOLD:
            # 长拖：沿炮塔方向前进
            ctrl.throttle = 1
        elif d > DRAG_AIM_DEADZONE:
            # 短拖：炮塔瞄准光标方向（屏蔽键盘转向，避免冲突）
            mx = drag_cur[0] - ARENA_X
            my = drag_cur[1] - ARENA_Y
            ctrl.aim_angle = math.atan2(my - player.y, mx - player.x)
            ctrl.turn = 0

    # 开火：鼠标左键按住（连续，受冷却限制）或 空格/J
    if mouse_down or keys[pygame.K_SPACE] or keys[pygame.K_j]:
        ctrl.fire = True
    return ctrl


def build_p2_control(keys):
    """双人模式玩家 2 控制（纯键盘）：方向键转向/前进后退，右 Shift 开火。"""
    ctrl = ControlState()
    if keys[pygame.K_LEFT]:
        ctrl.turn -= 1
    if keys[pygame.K_RIGHT]:
        ctrl.turn += 1
    kt = 0
    if keys[pygame.K_UP]:
        kt += 1
    if keys[pygame.K_DOWN]:
        kt -= 1
    ctrl.throttle = kt
    if keys[pygame.K_RSHIFT]:
        ctrl.fire = True
    return ctrl


def build_p2_mouse_control(mouse_pos, player, fire):
    """双人模式玩家 2 控制（鼠标）：
    - 以玩家 2 坦克为圆心、P2_MOUSE_RADIUS 为半径的判定圆：
        圆内  → 仅瞄准（炮台转向鼠标方向），不移动（准星显示十字）
        圆外  → 朝鼠标方向移动（炮台同步指向鼠标，即「驶向光标」）（准星显示圈）
    - 左键开火。
    返回 (ControlState, mode)，mode ∈ {'aim','move'} 供准星绘制。"""
    ctrl = ControlState()
    if not player.alive:
        return ctrl, "aim"
    # 屏幕坐标 → 竞技场局部坐标（world 以 ARENA_X/Y 为原点绘制）
    mx = mouse_pos[0] - ARENA_X
    my = mouse_pos[1] - ARENA_Y
    dx = mx - player.x
    dy = my - player.y
    dist = math.hypot(dx, dy)
    if dist <= P2_MOUSE_RADIUS:
        # 圆内：仅瞄准（炮台转向鼠标），屏蔽键盘转向避免冲突
        ctrl.aim_angle = math.atan2(dy, dx)
        ctrl.turn = 0
        ctrl.throttle = 0
        mode = "aim"
    else:
        # 圆外：炮台指向鼠标 + 沿炮塔前进 → 驶向光标
        ctrl.aim_angle = math.atan2(dy, dx)
        ctrl.turn = 0
        ctrl.throttle = 1
        mode = "move"
    if fire:
        ctrl.fire = True
    return ctrl, mode


# P2 判定环缓存（半径/颜色固定的 SRCALPHA 表面，零每帧分配）
_P2_RING_CACHE = {}
def _get_p2_ring(radius, color):
    """返回以坦克为圆心的淡蓝判定环（圆内瞄准 / 圆外移动的分界），缓存复用。"""
    key = (radius, color)
    s = _P2_RING_CACHE.get(key)
    if s is None:
        r = int(radius)
        s = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
        pygame.draw.circle(s, (*color[:3], 55), (r + 1, r + 1), r, width=2)
        _P2_RING_CACHE[key] = s
    return s


class NameField:
    """简易文本输入（pygame 无 IME，仅支持 ASCII/数字；中文需预设默认值）。"""
    def __init__(self, x, y, w, h, label, default=""):
        self.rect = pygame.Rect(x, y, w, h)
        self.label = label
        self.text = default
        self.active = False
        self.max_len = 12

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)
            return self.active
        if event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.key in (pygame.K_RETURN, pygame.K_TAB):
                self.active = False
            else:
                ch = event.unicode
                if ch and ch.isprintable() and ch != " " and len(self.text) < self.max_len:
                    self.text += ch
            return True
        return False

    def draw(self, screen, fonts):
        col = COLOR_CYAN if self.active else COLOR_BTN_BORDER
        pygame.draw.rect(screen, (20, 30, 48), self.rect, border_radius=6)
        pygame.draw.rect(screen, col, self.rect, width=2, border_radius=6)
        draw_text(screen, self.label, self.rect.x, self.rect.y - 22,
                  fonts, FONT_XS, COLOR_LIGHT_GRAY)
        draw_text(screen, self.text + ("|" if self.active else ""),
                  self.rect.x + 10, self.rect.y + (self.rect.h - FONT_S // 2) // 2 - 4,
                  fonts, FONT_M, COLOR_WHITE if self.text else COLOR_GRAY)


class MenuScreen:
    """主菜单界面"""
    def __init__(self, game):
        self.game = game
        self.buttons = []
        self.time = 0
        self.toast = ""          # 下载结果提示气泡
        self.toast_timer = 0.0
        self.download_btn = None
        self._build_buttons()

    def _build_buttons(self):
        cx = SCREEN_WIDTH // 2
        bw, bh = 300, 44
        sy = 280          # 下移 20px 给"选择游戏模式"提示留空间（钢铁洪流紧凑布局）
        gap = 16          # 垂直间距 22 → 16，更紧凑
        self.buttons = [
            Button(cx - bw // 2, sy, bw, bh, "单人闯关模式", FONT_L),
            Button(cx - bw // 2, sy + (bh + gap), bw, bh, "双人合作对抗 AI", FONT_L),
            Button(cx - bw // 2, sy + (bh + gap) * 2, bw, bh, "道具狂欢模式", FONT_L),
            Button(cx - bw // 2, sy + (bh + gap) * 3, bw, bh, "排行榜", FONT_L),
            Button(cx - bw // 2, sy + (bh + gap) * 4, bw, bh, "车库", FONT_L),
            Button(cx - bw // 2, sy + (bh + gap) * 5, bw, bh, "退出游戏", FONT_L),
        ]
        # 网页版：浏览器无法真正「退出」，禁用退出按钮，避免点击后画面冻结
        if _IN_BROWSER:
            self.buttons[-1].disabled = True
        # 网页版专属功能入口：下载存档到本地设备
        if _IN_BROWSER:
            self.download_btn = Button(20, 588, 200, 34,
                                       "下载存档到本地", FONT_S)
        else:
            self.download_btn = None
        # 全屏切换按钮（桌面离屏 letterbox / 网页 Fullscreen API 统一入口）
        self.fullscreen_btn = Button(SCREEN_WIDTH - 104, 16, 92, 32,
                                     "全屏", FONT_S)

    def enter(self):
        self._build_buttons()

    def handle_event(self, event):
        for i, btn in enumerate(self.buttons):
            if btn.handle_event(event):
                if i == 0:
                    self.game.change_state(STATE_LEVEL_SELECT)
                elif i == 1:
                    self.game.change_state(STATE_TWO_PLAYER_SELECT)
                elif i == 2:
                    self.game.change_state(STATE_CARNIVAL)
                elif i == 3:
                    self.game.change_state(STATE_LEADERBOARD)
                elif i == 4:
                    self.game.change_state(STATE_GARAGE)
                elif i == 5:
                    self.game.running = False
                return
        # 网页版：下载存档到本地
        if self.download_btn is not None and self.download_btn.handle_event(event):
            ok = download_save(self.game)
            self.toast = ("存档已下载：tank-battle-save.json"
                         if ok else "当前环境不支持下载")
            self.toast_timer = 3.0
            return
        # 全屏切换（桌面/网页端统一入口）
        if self.fullscreen_btn is not None and self.fullscreen_btn.handle_event(event):
            self.game.toggle_fullscreen_mode()
            return

    def update(self, dt):
        self.time += dt
        # 全屏按钮标签随状态切换（全屏时显示「窗口」，否则「全屏」）
        if self.fullscreen_btn is not None:
            self.fullscreen_btn.text = "窗口" if self.game.is_fullscreen() else "全屏"
        if self.toast_timer > 0:
            self.toast_timer -= dt
            if self.toast_timer <= 0:
                self.toast = ""

    def draw(self, screen, fonts):
        draw_bg(screen)
        cx = SCREEN_WIDTH // 2

        # ---------- 屏幕暗角（边缘压暗，增强纵深）----------
        draw_vignette(screen, 0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, strength=95)

        # ---------- 四角科技括号（白钢 L 形边框，营造机舱框架感）----------
        _m, _L, _t = 14, 28, 3
        _bk = COLOR_BTN_BORDER
        _bw, _bh = SCREEN_WIDTH, SCREEN_HEIGHT
        for (_ox, _oy, _dx, _dy) in [
            (_m, _m, 1, 1), (_bw - _m, _m, -1, 1),
            (_m, _bh - _m, 1, -1), (_bw - _m, _bh - _m, -1, -1),
        ]:
            pygame.draw.line(screen, _bk, (_ox, _oy), (_ox + _dx * _L, _oy), _t)
            pygame.draw.line(screen, _bk, (_ox, _oy), (_ox, _oy + _dy * _L), _t)

        # ---------- 背景装饰：四角钢蓝序号编号（01-04，克制科技感，无扫描线）----------
        _corner_nums = [
            ("01", 24, 24, False, False),
            ("02", SCREEN_WIDTH - 24, 24, True, False),
            ("03", 24, SCREEN_HEIGHT - 24, False, True),
            ("04", SCREEN_WIDTH - 24, SCREEN_HEIGHT - 24, True, True),
        ]
        for _num, _nx, _ny, _right, _bottom in _corner_nums:
            _sx = (SCREEN_WIDTH - 24 - fonts[FONT_XS].size(_num)[0]) if _right else _nx
            _sy = (SCREEN_HEIGHT - 40) if _bottom else _ny
            draw_text(screen, _num, _sx, _sy, fonts, FONT_XS, COLOR_CYAN)

        # 标题 - 静态（极轻微浮动，去掉呼吸明灭，更克制高级）
        title_y = 92 + int(math.sin(self.time * 1.5) * 3)
        # 标题背后极淡钢蓝聚光（冷锻钢蓝，非霓虹）
        draw_glow(screen, cx, title_y, 260, COLOR_CYAN, alpha=18)
        title_font = fonts.get(FONT_XXL, fonts[FONT_M])
        title_surf = title_font.render("坦 克 大 战", True, COLOR_GOLD)
        screen.blit(title_surf, title_surf.get_rect(center=(cx, title_y)))
        # 标题下方 1px 琥珀压线（强调，去呼吸）
        _uwy = title_y + 50
        pygame.draw.line(screen, COLOR_AMBER, (cx - 150, _uwy), (cx + 150, _uwy), 1)

        # 副标题 TANK BATTLE + 两侧钢蓝短横线（去 ◆ 菱形，更克制）
        sub_y = title_y + 70
        sub_font = fonts.get(FONT_L, fonts[FONT_M])
        sub_surf = sub_font.render("TANK BATTLE", True, COLOR_CYAN)
        sub_w = sub_surf.get_width()
        sub_rect = sub_surf.get_rect(center=(cx, sub_y))
        screen.blit(sub_surf, sub_rect)
        for dx in (-(sub_w // 2 + 14), (sub_w // 2 + 14)):
            pygame.draw.line(screen, COLOR_CYAN, (cx + dx - 16, sub_y), (cx + dx + 16, sub_y), 1)

        # 副标题下方静态钢蓝细装饰线
        _ly = sub_y + 30
        pygame.draw.line(screen, COLOR_CYAN, (cx - sub_w // 2 - 24, _ly), (cx + sub_w // 2 + 24, _ly), 1)

        draw_text(screen, "浪尖儿大学生社区 · 竞赛附加题", SCREEN_WIDTH // 2, title_y + 112,
                  fonts, FONT_S, COLOR_LIGHT_GRAY, center=True)

        # 存档信息（卡片条呈现，保留原文案；置于按钮上方，不遮挡标题区）
        save = get_save(self.game)
        info = f"最高通关: 第 {save['highest_level_cleared']} 关   |   累计战斗: {save['total_battles']} 场   |   当前坦克: {save['last_selected_tank']}"
        info_w = 620
        info_x = (SCREEN_WIDTH - info_w) // 2
        draw_card(screen, info_x, 226, info_w, 28, alpha=200)
        draw_text(screen, info, SCREEN_WIDTH // 2, 240,
                  fonts, FONT_S, COLOR_YELLOW, center=True)

        # 按钮组玻璃面板包裹（把 CTA 聚拢成一台「控制台」，与 HUD 玻璃质感统一）
        draw_glass_panel(screen, cx - 180, 258, 360, 374, alpha=150)

        # 按钮组上方提示
        draw_text(screen, "选择游戏模式", SCREEN_WIDTH // 2, 272,
                  fonts, FONT_S, COLOR_LIGHT_GRAY, center=True)

        for btn in self.buttons:
            btn.draw(screen, fonts)
            # hover 按钮右侧白色 ▶ 三角箭头（矢量，跟随 hover，禁用不显示）
            if btn.hovered and not btn.disabled:
                ax = btn.rect.right + 12
                ay = btn.rect.centery
                s3 = 10
                pygame.draw.polygon(screen, COLOR_WHITE, [
                    (ax, ay - s3),
                    (ax + s3, ay),
                    (ax, ay + s3),
                ])

        # 网页版：下载存档入口 + 操作提示
        if self.download_btn is not None:
            self.download_btn.draw(screen, fonts)
            draw_text(screen, "网页版专属：将进度保存为文件下载",
                      232, 604, fonts, FONT_XS, COLOR_LIGHT_GRAY, center=False)

        # 全屏切换按钮（右上角，桌面/网页端统一入口）
        if self.fullscreen_btn is not None:
            self.fullscreen_btn.draw(screen, fonts)

        # 下载结果提示气泡（顶部居中，3 秒后自动消失）
        if self.toast:
            draw_text(screen, self.toast, SCREEN_WIDTH // 2, 44,
                      fonts, FONT_M, COLOR_GREEN, center=True)

        # 底部：1px 分割线 + 版本号
        foot_y = SCREEN_HEIGHT - 40
        pygame.draw.line(screen, (50, 50, 55), (cx - 100, foot_y), (cx + 100, foot_y), 1)
        draw_text(screen, "BUILD 2026.08 · COMPETITION EDITION", 20, SCREEN_HEIGHT - 30,
                  fonts, FONT_XS, COLOR_CYAN)
        draw_corner_logo(screen, fonts)


class LevelSelectScreen:
    """单人闯关选关界面（规范：3 行 5 列网格 + 选中后「开始战斗」）"""
    def __init__(self, game):
        self.game = game
        self.level_buttons = []
        self.selected_level = 1
        self.back_btn = None
        self.start_btn = None
        self._build_buttons()

    def _build_buttons(self):
        self.level_buttons = []
        save = get_save(self.game)
        highest = save["highest_level_cleared"]
        # 默认选中：已解锁的最高关（highest+1，不超上限）
        self.selected_level = max(1, min(highest + 1, TOTAL_LEVELS))
        # 5 列 3 行
        cols, rows = 5, 3
        bw, bh = 120, 80
        start_x = (SCREEN_WIDTH - cols * bw - (cols - 1) * 20) // 2
        start_y = 150
        gap_x, gap_y = bw + 20, bh + 20
        for i in range(TOTAL_LEVELS):
            r, c = i // cols, i % cols
            x = start_x + c * gap_x
            y = start_y + r * gap_y
            level_num = i + 1
            unlocked = level_num <= highest + 1   # 已解锁（highest+1 以内）：亮色可点击
            text = f"第 {level_num} 关"
            btn = Button(x, y, bw, bh, text, FONT_M, disabled=not unlocked)
            self.level_buttons.append((btn, level_num, unlocked))

        self.back_btn = Button(40, SCREEN_HEIGHT - 70, 160, 48, "← 返回菜单", FONT_M)
        self.start_btn = Button(SCREEN_WIDTH // 2 - 110, SCREEN_HEIGHT - 95, 220, 48,
                                "开始战斗", FONT_L)

    def enter(self):
        self._build_buttons()

    def handle_event(self, event):
        if self.back_btn.handle_event(event):
            self.game.change_state(STATE_MENU)
            return
        # 点击已解锁关卡 -> 选中高亮（不直接开始）
        for btn, level_num, unlocked in self.level_buttons:
            if unlocked and btn.handle_event(event):
                self.selected_level = level_num
                return
        # 「开始战斗」-> 进入选中关卡
        if self.start_btn.handle_event(event):
            if self.selected_level <= get_save(self.game)["highest_level_cleared"] + 1:
                self.game.current_level = self.selected_level
                self.game.change_state(STATE_SINGLE_PLAY)
            return

    def update(self, dt):
        pass

    def draw(self, screen, fonts):
        draw_bg(screen)
        save = get_save(self.game)

        # 标题辉光
        draw_glow_accent(screen, SCREEN_WIDTH // 2, 55, "单人闯关模式 - 选择关卡",
                         fonts, FONT_XL, COLOR_GOLD)
        draw_text(screen, f"最高通关: 第 {save['highest_level_cleared']} 关    最高分记录已保存",
                  SCREEN_WIDTH // 2, 100, fonts, FONT_S, COLOR_CYAN, center=True)
        draw_text(screen, "主题: 浪尖儿学生社区 · 难度随关卡递增",
                  SCREEN_WIDTH // 2, 130, fonts, FONT_S, COLOR_WHITE, center=True)

        for btn, level_num, unlocked in self.level_buttons:
            # 选中关卡用金色卡片高亮（替代原纯黄边框）
            if level_num == self.selected_level and unlocked:
                pygame.draw.rect(screen, UI_ACCENT, btn.rect.inflate(6, 6),
                                 width=3, border_radius=UI_RADIUS_LG)
            btn.draw(screen, fonts)
            if not unlocked:
                # 矢量小锁图标（emoji 🔒 在 pygame 中无法渲染）
                draw_lock(screen, btn.rect.right - 26, btn.rect.top + 8, 16, COLOR_GRAY)
            if unlocked:
                key = f"level_{level_num}"
                hs = save["high_scores"].get(key, 0)
                if hs > 0:
                    # 按钮下方显示历史最高分
                    bx, by = btn.rect.centerx, btn.rect.bottom + 4
                    draw_text(screen, f"最高 {hs}", bx, by, fonts, FONT_XS, COLOR_YELLOW, center=True)

        # 底部：当前选中 + 开始战斗
        draw_text(screen, f"已选: 第 {self.selected_level} 关",
                  SCREEN_WIDTH // 2, SCREEN_HEIGHT - 120,
                  fonts, FONT_L, COLOR_GREEN, center=True)
        sel_unlocked = self.selected_level <= save["highest_level_cleared"] + 1
        self.start_btn.disabled = not sel_unlocked
        self.start_btn.draw(screen, fonts)

        # 操作提示
        draw_text(screen, "操作: WASD 移动   空格/J 射击   ESC 返回选关",
                  SCREEN_WIDTH // 2, SCREEN_HEIGHT - 16,
                  fonts, FONT_XS, COLOR_LIGHT_GRAY, center=True)

        self.back_btn.draw(screen, fonts)
        draw_corner_logo(screen, fonts)


class VictoryAnimation:
    """第 15 关通关动画：烟花 + 贺词。"""
    def __init__(self, fonts):
        self.fonts = fonts
        self.time = 0.0
        self.duration = 6.0
        self.particles = []
        self._spawn_timer = 0.0

    def _spawn_firework(self):
        cx = random.randint(150, SCREEN_WIDTH - 150)
        cy = random.randint(110, SCREEN_HEIGHT // 2)
        color = random.choice([COLOR_GOLD, COLOR_RED, COLOR_GREEN,
                               COLOR_BLUE, COLOR_CYAN, COLOR_PURPLE])
        for _ in range(32):
            ang = random.uniform(0, math.tau)
            sp = random.uniform(60, 220)
            self.particles.append({
                "x": cx, "y": cy,
                "vx": math.cos(ang) * sp, "vy": math.sin(ang) * sp,
                "life": 0.0, "max_life": random.uniform(0.8, 1.6),
                "color": color,
            })

    def update(self, dt):
        self.time += dt
        self._spawn_timer -= dt
        if self._spawn_timer <= 0:
            self._spawn_timer = 0.35
            self._spawn_firework()
        for p in self.particles:
            p["life"] += dt
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            p["vy"] += 140 * dt  # 重力
        self.particles = [p for p in self.particles if p["life"] < p["max_life"]]

    def done(self):
        return self.time >= self.duration

    def draw(self, screen, fonts):
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        screen.blit(overlay, (0, 0))
        # 烟花粒子：复用 vfx 辉光缓存绘制，消除每帧新建 Surface 的 GC 抖动
        for p in self.particles:
            t = p["life"] / p["max_life"]
            alpha = int(255 * (1 - t))
            r = max(1, int(3 * (1 - t)))
            draw_glow(screen, p["x"], p["y"], r + 1, p["color"], alpha=alpha)
        draw_text(screen, "恭 喜 通 关 !", SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 70,
                  fonts, FONT_XXL, COLOR_GOLD, center=True)
        draw_text(screen, "你已击败全部 15 关，成为坦克大战王者！",
                  SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2, fonts, FONT_L, COLOR_WHITE, center=True)
        draw_text(screen, "按 回车 / ESC 返回选关", SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 60,
                  fonts, FONT_M, COLOR_CYAN, center=True)


class ResultScreen:
    """结算界面（Pygame 原生绘制）。

    显示得分 / 击毁数 / 用时 / 评价等级（S/A/B/C），以及解锁提示；
    按钮行返回动作字符串（"next" / "retry" / "menu"）供上层处理。
    """
    PW, PH = 500, 380

    def __init__(self, victory, level, score, enemies_killed, time_used,
                 new_unlocks=None, total_battles=None):
        self.victory = victory
        self.level = level
        self.score = score
        self.enemies_killed = enemies_killed
        self.time_used = int(time_used)
        self.grade = ScoreSystem.get_grade(score)
        self.new_unlocks = new_unlocks or []
        self.total_battles = total_battles
        self.show_next = bool(victory) and level < TOTAL_LEVELS
        # 结算动画自计时（首次 draw 才开始，避免创建到显示的延迟）
        self.time = 0.0
        self._t0 = None

        # 按钮（底部居中排布）
        pbw, pbh = 150, 50
        cx = SCREEN_WIDTH // 2
        by = (SCREEN_HEIGHT - self.PH) // 2 + self.PH - 80
        self.next_btn = Button(cx - 235, by, pbw, pbh, "下一关", FONT_M)
        self.retry_btn = Button(cx - 75, by, pbw, pbh, "重试", FONT_M)
        self.menu_btn = Button(cx + 85, by, pbw, pbh, "选关", FONT_M)
        self.next_btn.disabled = not self.show_next

    def draw(self, screen, fonts):
        # 自计时：首次 draw 才开始（结算动画时间轴）
        if self._t0 is None:
            self._t0 = pygame.time.get_ticks()
        self.time = (pygame.time.get_ticks() - self._t0) / 1000.0
        t = self.time
        cx = SCREEN_WIDTH // 2

        # 1) 径向聚光灯遮罩（中心透、边缘暗，聚焦结算面板）
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        screen.blit(overlay, (0, 0))
        draw_vignette(screen, 0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, strength=180)

        pw, ph = self.PW, self.PH
        px = (SCREEN_WIDTH - pw) // 2
        py = (SCREEN_HEIGHT - ph) // 2
        draw_glass_panel(screen, px, py, pw, ph, alpha=245)

        # 2) 胜利标题缩放弹性动画（1.5→1.0 + overshoot）+ 矢量奖杯星（替代 emoji）
        if self.victory:
            title, col = "胜 利 !", COLOR_GOLD
        else:
            title, col = "失 败", COLOR_RED
        if t < 0.5:
            base = 1.5 - t           # 1.5 → 1.0
        else:
            base = 1.0
        overshoot = math.sin(t * 8) * 0.1 * math.exp(-t * 3)
        scale = max(0.5, base + overshoot)
        title_font = fonts.get(FONT_XXL, fonts[FONT_M])
        title_surf = title_font.render(title, True, col)
        if abs(scale - 1.0) > 0.01:
            sw = max(1, int(title_surf.get_width() * scale))
            sh = max(1, int(title_surf.get_height() * scale))
            title_surf = pygame.transform.smoothscale(title_surf, (sw, sh))
        # 矢量奖杯星（标题上方，金色五角星，无 emoji 依赖）
        if self.victory:
            _sr = 14
            _spts = []
            for _i in range(10):
                _ang = -math.pi / 2 + _i * math.pi / 5
                _rr = _sr if _i % 2 == 0 else _sr * 0.45
                _spts.append((cx + math.cos(_ang) * _rr, py + 34 + math.sin(_ang) * _rr))
            pygame.draw.polygon(screen, COLOR_GOLD, _spts)
        screen.blit(title_surf, title_surf.get_rect(center=(cx, py + 52)))

        draw_text(screen, f"第 {self.level} 关", cx, py + 100,
                  fonts, FONT_L, COLOR_CYAN, center=True)

        # 3) 三列卡片式数据（得分 / 击毁 / 用时）
        _cards = [
            ("得分", str(self.score), COLOR_GOLD),
            ("击毁", f"{self.enemies_killed} 辆", COLOR_WHITE),
            ("用时", f"{self.time_used} 秒", COLOR_CYAN),
        ]
        _cw, _ch, _cgap = 138, 70, 18
        _ctot = 3 * _cw + 2 * _cgap
        _csx = cx - _ctot // 2
        _cyy = py + 128
        for _i, (_lbl, _val, _vc) in enumerate(_cards):
            _cxi = _csx + _i * (_cw + _cgap)
            draw_glass_panel(screen, _cxi, _cyy, _cw, _ch, alpha=210)
            draw_text(screen, _val, _cxi + _cw // 2, _cyy + 22,
                      fonts, FONT_L, _vc, center=True)
            draw_text(screen, _lbl, _cxi + _cw // 2, _cyy + 52,
                      fonts, FONT_S, COLOR_LIGHT_GRAY, center=True)

        # 4) 评价
        grade_col = {
            "S": COLOR_GOLD, "A": COLOR_GREEN,
            "B": COLOR_CYAN, "C": COLOR_LIGHT_GRAY,
        }[self.grade]
        draw_text(screen, f"评价 {self.grade}", cx, py + 226,
                  fonts, FONT_XL, grade_col, center=True)

        # 5) 新装备解锁金色横幅（左右滑入动画）
        if self.new_unlocks:
            _name = self.new_unlocks[0]
            _st = min(1.0, t / 0.4)
            _se = 1 - (1 - _st) ** 3            # ease-out cubic
            _bw, _bh = 360, 30
            _bx = cx - _bw // 2 + int((1 - _se) * 240)
            _by = py + 252
            _bs = pygame.Surface((_bw, _bh), pygame.SRCALPHA)
            _bs.fill((COLOR_GOLD[0], COLOR_GOLD[1], COLOR_GOLD[2], 55))
            screen.blit(_bs, (_bx, _by))
            pygame.draw.rect(screen, COLOR_GOLD, (_bx, _by, _bw, _bh),
                             width=1, border_radius=UI_RADIUS_MD)
            # ▶ 矢量三角
            _tx, _ty = _bx + 14, _by + _bh // 2
            pygame.draw.polygon(screen, COLOR_GOLD,
                                [(_tx, _ty - 6), (_tx + 8, _ty), (_tx, _ty + 6)])
            draw_text(screen, f"新装备解锁  {_name}",
                      _bx + _bw // 2 + 6, _by + 4,
                      fonts, FONT_S, COLOR_GOLD, center=True)

        # 按钮行
        self.retry_btn.draw(screen, fonts)
        self.menu_btn.draw(screen, fonts)
        if self.show_next:
            self.next_btn.draw(screen, fonts)

    def handle_event(self, event):
        """检测按钮点击，返回对应动作字符串；无点击返回 None。"""
        if self.next_btn.handle_event(event):
            return "next"
        if self.retry_btn.handle_event(event):
            return "retry"
        if self.menu_btn.handle_event(event):
            return "menu"
        return None


class SinglePlayScreen:
    """单人闯关游戏界面 - 通过 LevelManager 管理关卡进度"""
    def __init__(self, game):
        self.game = game
        self.manager = LevelManager(game.current_level)
        self.world = None
        self.time = 0.0
        self.back_btn = None
        self.result_screen = None       # ResultScreen 实例（结算时创建）
        self.final_victory = False      # 第 15 关通关动画进行中
        self.victory_anim = None
        self.auto_advance_timer = 0.0   # 胜利后自动进入下一关倒计时
        # 鼠标拖拽状态（统一操作系统：短拖瞄准 / 长拖前进 / 左键开火）
        self.dragging = False
        self.drag_start = (0, 0)
        self.drag_cur = (0, 0)
        self.mouse_down = False
        self._build_buttons()

    def _build_buttons(self):
        self.back_btn = Button(SCREEN_WIDTH - 200, SCREEN_HEIGHT - 70, 170, 44,
                               "← 返回选关", FONT_M)

    def _start_level(self):
        """根据当前关卡和存档坦克，通过 LevelManager 初始化 GameWorld"""
        save = get_save(self.game)
        tank_name = save.get("last_selected_tank", "轻型侦察车")
        if tank_name not in save.get("unlocked_tanks", ["轻型侦察车"]):
            tank_name = "轻型侦察车"
        self.manager.current_level = self.game.current_level
        self.world = self.manager.load_level(self.game.current_level, tank_name, self.game.fonts)
        self.result_screen = None
        self.final_victory = False
        self.victory_anim = None
        self.auto_advance_timer = 0.0
        self.time = 0.0

    def enter(self):
        self._start_level()

    # -------------------- 输入 --------------------
    def handle_event(self, event):
        # 鼠标拖拽状态追踪（仅在战斗进行中生效，不干扰结算/返回按钮）
        if self.world is not None and self.result_screen is None and not self.final_victory:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.dragging = True
                self.drag_start = event.pos
                self.drag_cur = event.pos
                self.mouse_down = True
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self.dragging = False
                self.mouse_down = False
            elif event.type == pygame.MOUSEMOTION and self.dragging:
                self.drag_cur = event.pos

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.game.change_state(STATE_LEVEL_SELECT)
                return
            if self.final_victory:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self.game.change_state(STATE_LEVEL_SELECT)
                return
            # 结算状态下快捷键：R 重试，N 下一关
            if self.result_screen is not None:
                if event.key == pygame.K_r:
                    self._start_level()
                    return
                if (event.key == pygame.K_n and self.result_screen.victory
                        and not self.manager.is_last_level()):
                    self._advance()
                    return

        if self.final_victory:
            return

        # 结算界面按钮交互（委托给 ResultScreen）
        if self.result_screen is not None:
            action = self.result_screen.handle_event(event)
            if action == "next":
                self._advance()
                return
            if action == "retry":
                self._start_level()
                return
            if action == "menu":
                self.game.change_state(STATE_LEVEL_SELECT)
                return

        # 游戏中点击返回
        if self.back_btn.handle_event(event):
            self.game.change_state(STATE_LEVEL_SELECT)
            return

    # -------------------- 更新 --------------------
    def update(self, dt):
        self.time += dt

        # 通关动画进行中：只推进动画，冻结战斗
        if self.final_victory and self.victory_anim is not None:
            self.victory_anim.update(dt)
            if self.victory_anim.done():
                self.game.change_state(STATE_LEVEL_SELECT)
            return

        if self.world is None:
            return

        # 每帧轮询键盘 + 鼠标拖拽状态，构造统一 ControlState（与 AI 共用 apply_control）
        keys = pygame.key.get_pressed()
        ctrl = build_p1_control(keys, self.mouse_down, self.dragging,
                                self.drag_start, self.drag_cur, self.world.player)
        self.world.set_input(ctrl)
        self.world.update(dt)

        # 胜利（非末关）：倒计时自动进入下一关（N 可跳过）
        if (self.result_screen is not None and self.result_screen.victory
                and not self.manager.is_last_level()):
            self.auto_advance_timer -= dt
            if self.auto_advance_timer <= 0:
                self._advance()
                return

        # 结算处理（创建 ResultScreen）
        if (self.world.result != GameWorld.RESULT_NONE and
                self.result_screen is None and not self.final_victory):
            self._on_battle_end()

    def _advance(self):
        """推进到下一关（末关不再推进）"""
        if self.manager.is_last_level():
            return
        self.manager.next_level()
        self.game.current_level = self.manager.current_level
        self._start_level()

    def _on_battle_end(self):
        """战斗结束：用 ScoreSystem 计算得分，调用 SaveManager 记录，
        创建 ResultScreen；末关胜利触发通关动画。"""
        result = self.world.result
        level = self.game.current_level
        time_used = self.world.time
        kills = self.world.enemies_killed
        hp = self.world.player.hp
        win = (result == GameWorld.RESULT_WIN)

        # 分数计算（规范 ScoreSystem）
        score = ScoreSystem.calculate(kills, hp, time_used, level)
        self.world.score = score  # 与 HUD 保持一致

        # 记录存档（仅单人模式调用，双人模式不计入）
        save = get_save(self.game)
        old_unlocked = set(save.get("unlocked_tanks", []))
        save = SaveManager.record_battle(save, level, win, score, kills, time_used)
        persist_save(self.game,save)
        new_unlocks = sorted(set(save.get("unlocked_tanks", [])) - old_unlocked)

        # 第 15 关胜利：触发通关动画（替代普通弹窗）
        if win and self.manager.is_last_level():
            self.final_victory = True
            self.victory_anim = VictoryAnimation(self.game.fonts)
            return

        # 普通结算界面
        self.result_screen = ResultScreen(win, level, score, kills, time_used,
                                          new_unlocks, save["total_battles"])
        if win and not self.manager.is_last_level():
            self.auto_advance_timer = 3.0  # 非末关胜利：3 秒后自动进入下一关

    # -------------------- 绘制 --------------------
    def draw(self, screen, fonts):
        draw_bg(screen)
        if self.world is None:
            return

        level = self.game.current_level
        w = self.world
        player = w.player
        tank_name = player.tank_name
        tank_info = TANK_DATA.get(tank_name, TANK_DATA["轻型侦察车"])

        # ---- 游戏世界 ----
        w.draw(screen, ARENA_X, ARENA_Y, fonts)

        # ---- 顶部 HUD（科幻战争终端：玻璃面板） ----
        hud_y = 12

        # 左面板：能量条血量 + 坦克名
        lp_x, lp_y, lp_w, lp_h = 20, hud_y, 260, 60
        draw_glass_panel(screen, lp_x, lp_y, lp_w, lp_h, alpha=200)
        draw_text(screen, "装甲能量", lp_x + 12, lp_y + 8, fonts, FONT_XS, COLOR_LIGHT_GRAY)
        hp_ratio = max(0.0, min(1.0, player.hp / max(1, player.max_hp)))
        bar_x, bar_y, bar_w, bar_h = lp_x + 12, lp_y + 30, 120, 10
        ebar_bg = pygame.Surface((bar_w, bar_h), pygame.SRCALPHA)
        ebar_bg.fill((60, 20, 20))
        screen.blit(ebar_bg, (bar_x, bar_y))
        # 渐变填充（红→金，按血量比例）
        fg_surf = pygame.Surface((bar_w, bar_h), pygame.SRCALPHA)
        for i in range(bar_w):
            t = i / max(1, bar_w)
            r = int(COLOR_RED[0] + (COLOR_GOLD[0] - COLOR_RED[0]) * t)
            g = int(COLOR_RED[1] + (COLOR_GOLD[1] - COLOR_RED[1]) * t)
            b = int(COLOR_RED[2] + (COLOR_GOLD[2] - COLOR_RED[2]) * t)
            fg_surf.fill((r, g, b, 255), (i, 0, 1, bar_h))
        screen.blit(fg_surf, (bar_x, bar_y), (0, 0, int(bar_w * hp_ratio), bar_h))
        pygame.draw.rect(screen, COLOR_BTN_BORDER, (bar_x, bar_y, bar_w, bar_h), width=1, border_radius=3)
        draw_text(screen, f"{max(0, player.hp)}/{player.max_hp}",
                  bar_x + bar_w + 8, bar_y - 2, fonts, FONT_XS, COLOR_WHITE)
        draw_text(screen, tank_name, lp_x + 12, lp_y + 44,
                  fonts, FONT_S, tank_info["color"])

        # 中面板：关卡 + 剩余敌人
        mp_w, mp_h = 240, 60
        mp_x = (SCREEN_WIDTH - mp_w) // 2
        draw_glass_panel(screen, mp_x, hud_y, mp_w, mp_h, alpha=200)
        remaining = w.remaining_enemies()
        draw_text(screen, f"第 {level} 关", mp_x + mp_w // 2, hud_y + 12,
                  fonts, FONT_L, COLOR_CYAN, center=True)
        draw_text(screen, f"剩余 {remaining:02d}",
                  mp_x + mp_w // 2, hud_y + 38, fonts, FONT_S, COLOR_WHITE, center=True)

        # 右面板：得分（右对齐）
        rp_w, rp_h = 200, 60
        rp_x = SCREEN_WIDTH - rp_w - 20
        draw_glass_panel(screen, rp_x, hud_y, rp_w, rp_h, alpha=200)
        draw_text(screen, "得分", rp_x + rp_w - 12, hud_y + 10,
                  fonts, FONT_XS, COLOR_LIGHT_GRAY, center=False)
        score_surf = fonts[FONT_M].render(f"{w.score}", True, COLOR_GOLD)
        screen.blit(score_surf, (rp_x + rp_w - 12 - score_surf.get_width(), hud_y + 26))

        # 底部道具栏（图标 + 进度条，玻璃质感小面板）——叠加版
        active = player.get_active_powerups()
        shield_on = player.shield_active
        if active:
            names = [POWERUP_NAMES.get(t, str(t)) for t in active]
            buff_name = "+".join(names)
            buff_color = COLOR_GOLD if len(active) > 1 else POWERUP_COLORS.get(active[0], COLOR_WHITE)
            remains = [player.powerup_buffs.get(t, 0.0) for t in active]
            timed = [r for r in remains if r < PERMA_BUFF_THRESHOLD]
            if timed:
                remain = max(0.0, min(timed))
                remain_txt = f"{remain:.0f}s"
                ratio = max(0.0, min(1.0, remain / POWERUP_DURATION))
            else:
                remain_txt = "∞"
                ratio = 1.0
        else:
            buff_name, buff_color = "无", COLOR_GRAY
            remain_txt, ratio = "", 0.0
        if shield_on:
            buff_name = (buff_name + " +护盾") if buff_name != "无" else "护盾"

        # 道具图标行（40x40 玻璃小面板 + 14x14 彩色方块 + 细进度条）
        ib_x, ib_y = 20, SCREEN_HEIGHT - 56
        icon_size = 40
        for t in active[:3]:
            draw_glass_panel(screen, ib_x, ib_y, icon_size, icon_size, alpha=200)
            pygame.draw.rect(screen, POWERUP_COLORS.get(t, COLOR_WHITE),
                             (ib_x + 13, ib_y + 13, 14, 14), border_radius=3)
            ib_x += icon_size + 8
        if shield_on:
            draw_glass_panel(screen, ib_x, ib_y, icon_size, icon_size, alpha=200)
            draw_shield(screen, ib_x + 12, ib_y + 11, 16, COLOR_GOLD)
            ib_x += icon_size + 8
        # 名称 + 倒计时条
        text_x = ib_x + 2
        draw_text(screen, f"{buff_name} {remain_txt}".strip(),
                  text_x, ib_y + 4, fonts, FONT_S, buff_color)
        pbar_x, pbar_y, pbar_w, pbar_h = ib_x, ib_y + 26, 100, 6
        pbg = pygame.Surface((pbar_w, pbar_h), pygame.SRCALPHA)
        pbg.fill((40, 40, 50))
        screen.blit(pbg, (pbar_x, pbar_y))
        if ratio > 0:
            cr = int(220 * (1 - ratio)); cg = int(190 * ratio)
            pygame.draw.rect(screen, (cr, cg, 36),
                             (pbar_x, pbar_y, int(pbar_w * ratio), pbar_h), border_radius=3)

        # 关卡主题提示（黑底白字主题）
        draw_text(screen, "关卡主题: 浪尖儿学生社区",
                  SCREEN_WIDTH // 2, 60, fonts, FONT_S,
                  COLOR_WHITE, center=True)

        # 友军伤害提示（中央上部橙红闪烁警告条；矢量三角 warning 图标 + 文本）
        tip_blink = (int(self.time * 4) % 2) == 0
        tip_color = COLOR_ACCENT if tip_blink else COLOR_ORANGE
        tip = FRIENDLY_FIRE_TIP
        tw = fonts[FONT_S].size(tip)[0]
        cx_tip = ARENA_X + ARENA_W // 2
        warn_w = tw + 56
        warn_x = cx_tip - warn_w // 2
        warn_y = ARENA_Y - 20
        warn_surf = pygame.Surface((warn_w, 22), pygame.SRCALPHA)
        warn_surf.fill((tip_color[0], tip_color[1], tip_color[2], 80))
        screen.blit(warn_surf, (warn_x, warn_y))
        pygame.draw.rect(screen, tip_color, (warn_x, warn_y, warn_w, 22), width=1, border_radius=4)
        draw_warning(screen, warn_x + 14, warn_y + 5, 12, tip_color)
        draw_text(screen, tip, cx_tip + 12, warn_y + 11,
                  fonts, FONT_S, tip_color, center=True)

        # 底部按钮 / 操作提示
        self.back_btn.draw(screen, fonts)
        draw_text(screen, "A/D 转向 · W/S 前进后退 · 左键开火 · 拖拽瞄准/前进 · ESC返回选关",
                  SCREEN_WIDTH // 2, SCREEN_HEIGHT - 28,
                  fonts, FONT_S, COLOR_LIGHT_GRAY, center=True)
        draw_corner_logo(screen, fonts)

        # 结算界面（ResultScreen）
        if self.result_screen is not None:
            self.result_screen.draw(screen, fonts)
            # 自动进入下一关倒计时提示（胜利且非末关）
            if self.result_screen.victory and not self.manager.is_last_level():
                remain = max(0, int(self.auto_advance_timer))
                draw_text(screen, f"{remain} 秒后自动进入下一关（按 N 立即继续）",
                          SCREEN_WIDTH // 2, SCREEN_HEIGHT - 60,
                          fonts, FONT_S, COLOR_YELLOW, center=True)

        # 通关动画覆盖（第 15 关）
        if self.final_victory and self.victory_anim is not None:
            self.victory_anim.draw(screen, fonts)


class TwoPlayerSelectScreen:
    """双人模式说明 + 进入设置（双人合作对抗无尽 AI）"""
    def __init__(self, game):
        self.game = game
        self.start_btn = None
        self.back_btn = None
        self._build_buttons()

    def _build_buttons(self):
        cx = SCREEN_WIDTH // 2
        bw, bh = 300, 56
        self.start_btn = Button(cx - bw // 2, 470, bw, bh, "进入对战设置", FONT_L)
        self.back_btn = Button(40, SCREEN_HEIGHT - 80, 160, 48, "← 返回菜单", FONT_M)

    def enter(self):
        pass

    def handle_event(self, event):
        if self.back_btn.handle_event(event):
            self.game.change_state(STATE_MENU)
            return
        if self.start_btn.handle_event(event):
            self.game.change_state(STATE_P2_TANK_SELECT)

    def update(self, dt):
        pass

    def draw(self, screen, fonts):
        draw_bg(screen)

        draw_glow_accent(screen, SCREEN_WIDTH // 2, 64, "双人合作对抗 AI",
                         fonts, FONT_XXL, COLOR_GOLD)
        draw_text(screen, "两名玩家并肩作战，迎击持续生成的无尽敌方坦克",
                  SCREEN_WIDTH // 2, 128, fonts, FONT_M, COLOR_CYAN, center=True)

        # 规则说明
        draw_glass_panel(screen, 100, 180, SCREEN_WIDTH - 200, 270, alpha=200)
        lines = [
            ("玩法", COLOR_GOLD),
            ("· 无尽模式：AI 坦克持续生成，双方阵亡即结束", COLOR_LIGHT_GRAY),
            ("· 实时积分：击毁敌方坦克按归属计入对应玩家", COLOR_LIGHT_GRAY),
            ("· 自定义命名：开局前为两名玩家命名", COLOR_LIGHT_GRAY),
            ("· 积分排行榜：结算成绩进入排行榜", COLOR_LIGHT_GRAY),
            ("", COLOR_LIGHT_GRAY),
            ("操作", COLOR_GOLD),
            ("玩家1（键盘）：A/D 转向 · W/S 前进后退 · 空格/J 开火", COLOR_GREEN),
            ("玩家2（鼠标）：以坦克为圆心，圆内→炮台瞄准 · 圆外→驶向光标 · 左键开火", COLOR_BLUE),
        ]
        ty = 206
        for txt, col in lines:
            draw_text(screen, txt, 130, ty, fonts, FONT_S, col, center=False)
            ty += 24

        self.start_btn.draw(screen, fonts)
        self.back_btn.draw(screen, fonts)
        draw_corner_logo(screen, fonts)


class P2TankSelectScreen:
    """双人模式-玩家 2 选坦克界面：开局前从已解锁坦克中选择并确认出战车辆。
    流程：双人模式选择 → 玩家 2 选车 → 确认后进入对局。"""

    def __init__(self, game):
        self.game = game
        self.tank_buttons = []
        self.selected_idx = 0
        self.confirm_btn = None
        self.back_btn = None
        self.p1_name_field = None
        self.p2_name_field = None
        self._build_buttons()

    def _build_buttons(self):
        save = get_save(self.game)
        self.tank_buttons = []
        n = len(TANK_ORDER)
        gap = 16
        card_h = 250
        card_w = min(200, (SCREEN_WIDTH - 80 - gap * (n - 1)) // n)
        total_w = card_w * n + gap * (n - 1)
        start_x = (SCREEN_WIDTH - total_w) // 2
        y = 180
        for i, name in enumerate(TANK_ORDER):
            x = start_x + i * (card_w + gap)
            btn = Button(x, y, card_w, card_h, "", FONT_M)
            self.tank_buttons.append((btn, name))

        # 默认选中上次 P2 使用的坦克（若已解锁），否则第一辆已解锁坦克
        last = self.game.p2_tank
        unlocked = save.get("unlocked_tanks", [])
        if last in TANK_ORDER and last in unlocked:
            self.selected_idx = TANK_ORDER.index(last)
        else:
            for i, name in enumerate(TANK_ORDER):
                if name in unlocked:
                    self.selected_idx = i
                    break

        # 玩家命名输入框（默认沿用上次设置）
        self.p1_name_field = NameField(110, 92, 320, 36, "玩家 1 名称",
                                       getattr(self.game, "p1_name", "玩家1"))
        self.p2_name_field = NameField(530, 92, 320, 36, "玩家 2 名称",
                                       getattr(self.game, "p2_name", "玩家2"))

        self.confirm_btn = Button(SCREEN_WIDTH // 2 - 95, 498, 190, 48, "确认出战", FONT_L)
        self.back_btn = Button(40, SCREEN_HEIGHT - 70, 160, 48, "← 返回", FONT_M)

    def enter(self):
        self._build_buttons()

    def handle_event(self, event):
        if self.back_btn.handle_event(event):
            self.game.change_state(STATE_TWO_PLAYER_SELECT)
            return
        # 名称输入优先（激活时消费按键事件，避免误触其它控件）
        if self.p1_name_field.handle_event(event):
            return
        if self.p2_name_field.handle_event(event):
            return
        save = get_save(self.game)
        unlocked = save.get("unlocked_tanks", [])
        for i, (btn, name) in enumerate(self.tank_buttons):
            if name in unlocked and btn.handle_event(event):
                self.selected_idx = i
                return
        if self.confirm_btn.handle_event(event):
            name = TANK_ORDER[self.selected_idx]
            if name in unlocked:
                self.game.p1_name = self.p1_name_field.text or "玩家1"
                self.game.p2_name = self.p2_name_field.text or "玩家2"
                self.game.p2_tank = name
                self.game.change_state(STATE_TWO_PLAY)

    def update(self, dt):
        pass

    def draw(self, screen, fonts):
        draw_bg(screen)
        save = get_save(self.game)
        unlocked = save.get("unlocked_tanks", [])

        draw_glow_accent(screen, SCREEN_WIDTH // 2, 44, "对战设置",
                         fonts, FONT_XXL, COLOR_GOLD)
        # 玩家命名
        self.p1_name_field.draw(screen, fonts)
        self.p2_name_field.draw(screen, fonts)
        p1_tank = save.get("last_selected_tank", "轻型侦察车")
        draw_text(screen, f"玩家 1 出战坦克: {p1_tank}（来自车库）", 110, 142,
                  fonts, FONT_XS, COLOR_GREEN, center=False)
        draw_text(screen, "玩家 2 选择出战坦克（已解锁车辆可选）",
                  SCREEN_WIDTH // 2, 160, fonts, FONT_S, COLOR_WHITE, center=True)

        # 坦克卡片
        for i, (btn, name) in enumerate(self.tank_buttons):
            info = TANK_DATA[name]
            is_unlocked = name in unlocked
            is_selected = (i == self.selected_idx)
            x, y, w, h = btn.rect.x, btn.rect.y, btn.rect.w, btn.rect.h
            draw_card(screen, x, y, w, h,
                      highlight=(is_selected and is_unlocked),
                      alpha=235 if is_unlocked else 200)

            # 坦克图标
            icon_size = 68
            icon_x = x + (w - icon_size) // 2
            icon_y = y + 16
            draw_tank_icon(screen, icon_x, icon_y, info["color"],
                           size=icon_size, unlocked=is_unlocked,
                           style=TANK_STYLE_BY_NAME.get(name, TANK_STYLE_STANDARD))

            # 名称
            name_color = info["color"] if is_unlocked else COLOR_GRAY
            draw_text(screen, name, x + w // 2, y + 106,
                      fonts, FONT_M, name_color, center=True)
            # 定位
            draw_text(screen, info["role"], x + w // 2, y + 132,
                      fonts, FONT_XS, COLOR_CYAN if is_unlocked else COLOR_DARK_GRAY,
                      center=True)

            # 属性
            attr_y = y + 156
            # 血量（心形矢量图标，无 emoji 依赖）
            draw_text(screen, "血量", x + 15, attr_y, fonts, FONT_XS,
                      COLOR_RED if is_unlocked else COLOR_DARK_GRAY)
            draw_hearts(screen, x + 15 + 34, attr_y, info["hp"],
                        color=COLOR_RED if is_unlocked else COLOR_DARK_GRAY,
                        size=16, gap=3)
            # 移速
            draw_text(screen, f"移速 {info['speed']}", x + 15, attr_y + 20,
                      fonts, FONT_XS, COLOR_GREEN if is_unlocked else COLOR_DARK_GRAY)
            # 初始道具（彩色圆点 + 名称，避免 emoji 占位）
            dot_color, item_text = None, "无"
            if info["init_item"] == "scatter":
                dot_color, item_text = COLOR_BLUE, "散射弹"
            elif info["init_item"] == "laser":
                dot_color, item_text = COLOR_RED, "激光炮"
            elif info["init_item"] == "bounce_scatter":
                dot_color, item_text = COLOR_GREEN, "弹射+散射"
            draw_text(screen, "道具", x + 15, attr_y + 40, fonts, FONT_XS,
                      COLOR_BLUE if is_unlocked else COLOR_DARK_GRAY)
            if dot_color:
                pygame.draw.circle(screen, dot_color,
                                   (x + 15 + 44, attr_y + 40 + FONT_XS // 2 - 1), 6)
                draw_text(screen, item_text, x + 15 + 56, attr_y + 40, fonts, FONT_XS,
                          COLOR_BLUE if is_unlocked else COLOR_DARK_GRAY)
            else:
                draw_text(screen, item_text, x + 15 + 44, attr_y + 40, fonts, FONT_XS,
                          COLOR_BLUE if is_unlocked else COLOR_DARK_GRAY)

            # 锁定遮罩与解锁条件
            if not is_unlocked:
                mask = pygame.Surface((w, h), pygame.SRCALPHA)
                mask.fill((0, 0, 0, 150))
                screen.blit(mask, (x, y))
                tw = fonts[FONT_M].size("未解锁")[0]
                cx = x + w // 2
                draw_lock(screen, cx - tw // 2 - 22, y + 40 - 8, 16, COLOR_GRAY)
                draw_text(screen, "未解锁", cx, y + 40,
                          fonts, FONT_M, COLOR_GRAY, center=True)
                draw_text(screen, "解锁条件:", x + w // 2, y + 205,
                          fonts, FONT_XS, COLOR_LIGHT_GRAY, center=True)
                draw_text(screen, info["unlock_desc"], x + w // 2, y + 222,
                          fonts, FONT_S, COLOR_YELLOW, center=True)

        # 底部：当前选中 + 确认
        sel_name = TANK_ORDER[self.selected_idx]
        sel_ok = sel_name in unlocked
        sel_color = TANK_DATA[sel_name]["color"] if sel_ok else COLOR_GRAY
        draw_text(screen, f"已选: {sel_name}", SCREEN_WIDTH // 2, 452,
                  fonts, FONT_M, sel_color, center=True)
        self.confirm_btn.disabled = not sel_ok
        self.confirm_btn.draw(screen, fonts)
        self.back_btn.draw(screen, fonts)

        draw_text(screen, "点击卡片选车 · 输入名称 · 确认后进入对局",
                  SCREEN_WIDTH // 2, SCREEN_HEIGHT - 16,
                  fonts, FONT_XS, COLOR_LIGHT_GRAY, center=True)
        draw_corner_logo(screen, fonts)


class TwoPlayScreen:
    """双人模式游戏界面 - 完整实现"""

    def __init__(self, game):
        self.game = game
        self.world = None
        self.time = 0.0
        self.back_btn = None
        self.menu_btn = None
        self.retry_btn = None
        self.leaderboard_btn = None
        self.result_popup = None
        # P2 鼠标控制状态（P2 使用鼠标；P1 仅键盘，不占用鼠标）
        self.mouse_down = False
        self.p2_crosshair_mode = "aim"
        self._build_buttons()

    def _build_buttons(self):
        self.back_btn = Button(SCREEN_WIDTH - 200, SCREEN_HEIGHT - 70, 170, 44,
                               "← 返回选择", FONT_M)
        self.retry_btn = Button(0, 0, 150, 48, "再来一局", FONT_L)
        self.menu_btn = Button(0, 0, 150, 48, "回主菜单", FONT_L)
        self.leaderboard_btn = Button(0, 0, 150, 48, "查看排行榜", FONT_L)

    def _start_game(self):
        """初始化双人合作对抗 AI 世界（无尽）。"""
        save = get_save(self.game)
        t1 = save.get("last_selected_tank", "轻型侦察车")
        if t1 not in save.get("unlocked_tanks", []):
            t1 = "轻型侦察车"
        t2 = self.game.p2_tank if self.game.p2_tank in save.get("unlocked_tanks", []) else "轻型侦察车"
        p1_name = self.game.p1_name or "玩家1"
        p2_name = self.game.p2_name or "玩家2"
        self.world = TwoPlayerGameWorld(p1_name, p2_name, t1, t2, self.game.fonts)
        self.result_popup = None
        self.time = 0.0
        self.mouse_down = False
        self.p2_crosshair_mode = "aim"

    def enter(self):
        self._start_game()

    def handle_event(self, event):
        # P2 鼠标准星：仅追踪左键状态用于开火（鼠标位置由 get_pos 实时读取）
        if self.world is not None and self.result_popup is None:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.mouse_down = True
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self.mouse_down = False

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.game.change_state(STATE_TWO_PLAYER_SELECT)
                return
            if self.result_popup is not None:
                if event.key == pygame.K_r:
                    self._start_game()
                    return
                if event.key == pygame.K_m:
                    self.game.change_state(STATE_MENU)
                    return
                if event.key == pygame.K_l:
                    self.game.change_state(STATE_LEADERBOARD)
                    return

        if self.result_popup is not None:
            if self.retry_btn.handle_event(event):
                self._start_game()
                return
            if self.menu_btn.handle_event(event):
                self.game.change_state(STATE_MENU)
                return
            if self.leaderboard_btn.handle_event(event):
                self.game.change_state(STATE_LEADERBOARD)
                return

        if self.back_btn.handle_event(event):
            self.game.change_state(STATE_TWO_PLAYER_SELECT)
            return

    def update(self, dt):
        self.time += dt
        if self.world is None:
            return

        keys = pygame.key.get_pressed()
        # 玩家 1：键盘（A/D 转向 · W/S 沿炮塔移动 · 空格/J 开火），不占用鼠标
        p1_ctrl = build_p1_control(keys, False, False, (0, 0), (0, 0),
                                   self.world.player1)
        # 玩家 2：鼠标（圆内瞄准 / 圆外移动 · 左键开火）
        mp = pygame.mouse.get_pos()
        p2_ctrl, p2_mode = build_p2_mouse_control(mp, self.world.player2, self.mouse_down)
        self.p2_crosshair_mode = p2_mode
        self.world.set_input(p1_ctrl, p2_ctrl)
        self.world.update(dt)

        # 结算检测（双方阵亡即结束）
        if self.world.result != TwoPlayerGameWorld.RESULT_NONE and self.result_popup is None:
            self._on_game_end()

    def _on_game_end(self):
        """游戏结束：两名玩家阵亡。把双方积分写入「双人合作」排行榜。"""
        save = get_save(self.game)
        for _name, sc in self.world.scores.items():
            save = SaveManager.record_leaderboard(save, _name, sc, "vs_ai")
        persist_save(self.game, save)
        self.result_popup = {
            "scores": dict(self.world.scores),
            "kills": self.world.kills,
            "time": self.world.time,
        }

    def draw(self, screen, fonts):
        draw_bg(screen)
        if self.world is None:
            return

        w = self.world
        p1_name = self.game.p1_name or "玩家1"
        p2_name = self.game.p2_name or "玩家2"

        # ---- 游戏世界 ----
        w.draw(screen, ARENA_X, ARENA_Y, fonts)

        # ---- 顶部 HUD（双积分对称，互不遮挡）----
        hud_y = 18
        p1 = w.player1
        p2 = w.player2
        p1_color = TANK_DATA.get(p1.tank_name, {}).get("color", COLOR_GREEN)
        p2_color = TANK_DATA.get(p2.tank_name, {}).get("color", COLOR_BLUE)

        # 玩家 1 HUD（左上）
        draw_glass_panel(screen, 15, hud_y, 300, 72, alpha=200)
        draw_text(screen, p1_name, 30, hud_y + 8, fonts, FONT_M, p1_color)
        draw_hearts(screen, 30, hud_y + 34, max(0, p1.hp), p1.max_hp,
                    COLOR_RED, size=14, gap=3)
        draw_text(screen, f"得分 {w.scores.get(p1_name, 0)}",
                 170, hud_y + 30, fonts, FONT_S, COLOR_GOLD)

        # 玩家 2 HUD（右上）
        draw_glass_panel(screen, SCREEN_WIDTH - 315, hud_y, 300, 72, alpha=200)
        draw_text(screen, p2_name, SCREEN_WIDTH - 300, hud_y + 8, fonts, FONT_M, p2_color)
        draw_hearts(screen, SCREEN_WIDTH - 300, hud_y + 34, max(0, p2.hp), p2.max_hp,
                    COLOR_RED, size=14, gap=3)
        draw_text(screen, f"得分 {w.scores.get(p2_name, 0)}",
                 SCREEN_WIDTH - 170, hud_y + 30, fonts, FONT_S, COLOR_GOLD)

        # 中间信息（生存时间 + 击毁数）
        ci_w, ci_h = 320, 40
        ci_x = (SCREEN_WIDTH - ci_w) // 2
        draw_glass_panel(screen, ci_x, hud_y + 14, ci_w, ci_h, alpha=200)
        info = f"生存 {int(w.time)}s   |   击毁 {w.kills}"
        draw_text(screen, info, SCREEN_WIDTH // 2, hud_y + 34,
                  fonts, FONT_S, COLOR_CYAN, center=True)

        # 道具栏（左下/右下分别显示）
        self._draw_player_item(screen, p1, 60, SCREEN_HEIGHT - 35, fonts)
        self._draw_player_item(screen, p2, SCREEN_WIDTH - 220, SCREEN_HEIGHT - 35, fonts)

        # 友军伤害提示（中央上部橙红闪烁警告条；矢量三角 warning 图标 + 文本）
        tip_blink = (int(self.time * 4) % 2) == 0
        tip_color = COLOR_ACCENT if tip_blink else COLOR_ORANGE
        tip = FRIENDLY_FIRE_TIP
        tw = fonts[FONT_S].size(tip)[0]
        cx_tip = ARENA_X + ARENA_W // 2
        warn_w = tw + 56
        warn_x = cx_tip - warn_w // 2
        warn_y = ARENA_Y - 20
        warn_surf = pygame.Surface((warn_w, 22), pygame.SRCALPHA)
        warn_surf.fill((tip_color[0], tip_color[1], tip_color[2], 80))
        screen.blit(warn_surf, (warn_x, warn_y))
        pygame.draw.rect(screen, tip_color, (warn_x, warn_y, warn_w, 22), width=1, border_radius=4)
        draw_warning(screen, warn_x + 14, warn_y + 5, 12, tip_color)
        draw_text(screen, tip, cx_tip + 12, warn_y + 11,
                  fonts, FONT_S, tip_color, center=True)

        # 底部操作提示
        draw_text(screen, "P1: A/D 转向·W/S 移动·空格/J 开火   P2: 鼠标(圆内瞄准·圆外移动)·左键开火   ESC返回",
                  SCREEN_WIDTH // 2, SCREEN_HEIGHT - 28,
                  fonts, FONT_S, COLOR_LIGHT_GRAY, center=True)

        self.back_btn.draw(screen, fonts)

        # ---- P2 鼠标控制可视化：判定环 + 模式准星 ----
        if self.result_popup is None and w.player2.alive:
            tsx = ARENA_X + int(w.player2.x)
            tsy = ARENA_Y + int(w.player2.y)
            ring = _get_p2_ring(P2_MOUSE_RADIUS, P2_CROSSHAIR_COLOR)
            screen.blit(ring, (tsx - ring.get_width() // 2, tsy - ring.get_height() // 2))
            mp = pygame.mouse.get_pos()
            col = P2_CROSSHAIR_COLOR
            if self.p2_crosshair_mode == "aim":
                # 圆内：转向/瞄准 → 十字准星
                ln = 11
                pygame.draw.line(screen, col, (mp[0] - ln, mp[1]), (mp[0] + ln, mp[1]), 2)
                pygame.draw.line(screen, col, (mp[0], mp[1] - ln), (mp[0], mp[1] + ln), 2)
                pygame.draw.circle(screen, col, mp, 2)
            else:
                # 圆外：移动 → 圈准星
                pygame.draw.circle(screen, col, mp, 9, width=2)
                pygame.draw.circle(screen, col, mp, 2)

        # 结算弹窗
        if self.result_popup:
            self._draw_result_popup(screen, fonts)

    def _draw_player_item(self, screen, player, x, y, fonts):
        """绘制单个玩家的道具状态（叠加版：显示当前激活集合）"""
        active = player.get_active_powerups()
        shield_on = player.shield_active
        # 玻璃底（约 160x30）
        if active or shield_on:
            gw, gh = 160, 28
            gx = min(x, SCREEN_WIDTH - gw - 4)
            draw_glass_panel(screen, gx, y - 4, gw, gh, alpha=200)
        if not active and not shield_on:
            draw_text(screen, "无", x, y, fonts, FONT_S, COLOR_GRAY)
            return
        parts = []
        for t in active:
            if t in POWERUP_NAMES:
                parts.append(POWERUP_NAMES[t])
            else:
                parts.append(str(t))
        name = "+".join(parts) if parts else ""
        if shield_on:
            name += "+护盾" if name else "护盾"
        # 颜色：叠加用金色，单道具用其本色
        if len(active) > 1:
            color = COLOR_GOLD
        elif active:
            color = POWERUP_COLORS.get(active[0], COLOR_WHITE)
        else:
            color = COLOR_YELLOW
        # 剩余时间：perma 显示 ∞；有混合时附加限时最短剩余
        remains = [player.powerup_buffs.get(t, 0.0) for t in active]
        timed = [r for r in remains if r < PERMA_BUFF_THRESHOLD]
        if timed:
            name += f" {max(0.0, min(timed)):.0f}s"
        else:
            name += " ∞"
        draw_text(screen, name, x, y, fonts, FONT_S, color)

    def _draw_result_popup(self, screen, fonts):
        info = self.result_popup

        # 径向聚光灯遮罩（中心透、边缘暗，聚焦结算）
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        screen.blit(overlay, (0, 0))
        draw_vignette(screen, 0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, strength=170)

        pw, ph = 520, 360
        px, py = (SCREEN_WIDTH - pw) // 2, (SCREEN_HEIGHT - ph) // 2
        draw_glass_panel(screen, px, py, pw, ph, alpha=245)

        # 积分排名（按分数降序）
        ranked = sorted(info["scores"].items(), key=lambda kv: kv[1], reverse=True)
        draw_text(screen, "对局结束 · 积分排行", px + pw // 2, py + 40,
                  fonts, FONT_XXL, COLOR_GOLD, center=True)
        draw_text(screen, f"共击毁 {info['kills']} 辆敌方坦克   生存 {int(info['time'])}s",
                  px + pw // 2, py + 92, fonts, FONT_S, COLOR_LIGHT_GRAY, center=True)

        ry = py + 132
        for i, (nm, sc) in enumerate(ranked):
            col = COLOR_GOLD if i == 0 else (COLOR_CYAN if i == 1 else COLOR_WHITE)
            draw_text(screen, f"第 {i + 1} 名   {nm}", px + 60, ry, fonts, FONT_M, col)
            draw_text(screen, f"{sc} 分", px + pw - 60, ry, fonts, FONT_M, col, center=True)
            ry += 34

        draw_text(screen, "成绩已计入排行榜",
                  px + pw // 2, py + ph - 104, fonts, FONT_S, COLOR_GRAY, center=True)

        # 三个按钮横排（避免垂直重叠导致的误触/遮挡）
        bw, bh = 150, 48
        gap = 20
        total = bw * 3 + gap * 2
        sx = (SCREEN_WIDTH - total) // 2
        by = py + ph - 58
        self.retry_btn.rect.topleft = (sx, by)
        self.menu_btn.rect.topleft = (sx + bw + gap, by)
        self.leaderboard_btn.rect.topleft = (sx + (bw + gap) * 2, by)
        self.retry_btn.draw(screen, fonts)
        self.menu_btn.draw(screen, fonts)
        self.leaderboard_btn.draw(screen, fonts)

        draw_text(screen, "快捷键: R 再来一局   M 回主菜单   L 排行榜",
                  SCREEN_WIDTH // 2, SCREEN_HEIGHT - 28,
                  fonts, FONT_S, COLOR_YELLOW, center=True)

_BLUEPRINT_GRID = None
def _get_blueprint_grid():
    """蓝图网格背景缓存（钢蓝细网格 alpha 30，预烘焙一次复用，零每帧分配）。"""
    global _BLUEPRINT_GRID
    if _BLUEPRINT_GRID is None:
        s = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        gc = (30, 58, 95, 30)
        gs = 32
        for _x in range(0, SCREEN_WIDTH, gs):
            pygame.draw.line(s, gc, (_x, 0), (_x, SCREEN_HEIGHT), 1)
        for _y in range(0, SCREEN_HEIGHT, gs):
            pygame.draw.line(s, gc, (0, _y), (SCREEN_WIDTH, _y), 1)
        _BLUEPRINT_GRID = s
    return _BLUEPRINT_GRID


class GarageScreen:
    """车库界面 - 坦克查看与选择"""
    def __init__(self, game):
        self.game = game
        self.tank_buttons = []
        self.select_btn = None
        self.back_btn = None
        self.selected_idx = 0
        self._build_buttons()

    def _build_buttons(self):
        save = get_save(self.game)
        self.tank_buttons = []
        # 水平排列坦克卡片（按 TANK_ORDER 数量动态计算，避免新增坦克后溢出）
        n = len(TANK_ORDER)
        gap = 16
        card_h = 260
        # 单卡最大 200，但须整体落在屏幕内（左右各留 40 边距）
        card_w = min(200, (SCREEN_WIDTH - 80 - gap * (n - 1)) // n)
        total_w = card_w * n + gap * (n - 1)
        start_x = (SCREEN_WIDTH - total_w) // 2
        y = 140
        for i, name in enumerate(TANK_ORDER):
            x = start_x + i * (card_w + gap)
            btn = Button(x, y, card_w, card_h, "", FONT_M)
            self.tank_buttons.append((btn, name))

        # 默认选中上次使用的坦克
        last = save.get("last_selected_tank", "轻型侦察车")
        if last in TANK_ORDER:
            self.selected_idx = TANK_ORDER.index(last)

        self.select_btn = Button(SCREEN_WIDTH // 2 - 95, 524, 190, 48, "选择出战", FONT_L)
        self.back_btn = Button(40, SCREEN_HEIGHT - 80, 160, 48, "← 返回菜单", FONT_M)

    def enter(self):
        self._build_buttons()

    def handle_event(self, event):
        if self.back_btn.handle_event(event):
            self.game.change_state(STATE_MENU)
            return
        for i, (btn, name) in enumerate(self.tank_buttons):
            save = get_save(self.game)
            unlocked = name in save.get("unlocked_tanks", [])
            if unlocked and btn.handle_event(event):
                self.selected_idx = i
                return
        if self.select_btn.handle_event(event):
            save = get_save(self.game)
            name = TANK_ORDER[self.selected_idx]
            if name in save.get("unlocked_tanks", []):
                persist_save(self.game,SaveManager.select_tank(name))
                self.game.change_state(STATE_MENU)

    def update(self, dt):
        pass

    def draw(self, screen, fonts):
        draw_bg(screen)
        # 蓝图网格背景（卡片后方，钢蓝细网格 alpha 30，预烘焙缓存）
        screen.blit(_get_blueprint_grid(), (0, 0))
        save = get_save(self.game)

        draw_glow_accent(screen, SCREEN_WIDTH // 2, 55, "车 库",
                         fonts, FONT_XXL, COLOR_GOLD)
        draw_text(screen, f"装备库 · 已认证载具 {len(save['unlocked_tanks'])}/{len(TANK_ORDER)}   |   累计战斗 {save['total_battles']} 场   |   最高通关 {save['highest_level_cleared']} 关",
                  SCREEN_WIDTH // 2, 105, fonts, FONT_M, COLOR_AMBER, center=True)

        # 坦克卡片
        for i, (btn, name) in enumerate(self.tank_buttons):
            info = TANK_DATA[name]
            unlocked = name in save.get("unlocked_tanks", [])
            is_selected = (i == self.selected_idx)

            # 卡片底（设计系统：浮起卡片 + 选中金色描边）
            btn.disabled = not unlocked
            x, y, w, h = btn.rect.x, btn.rect.y, btn.rect.w, btn.rect.h
            # 选中发光底座（椭圆，坦克同色 alpha 40）
            if is_selected and unlocked:
                _oc = info["color"]
                _ose = pygame.Surface((w + 20, 40), pygame.SRCALPHA)
                pygame.draw.ellipse(_ose, (_oc[0], _oc[1], _oc[2], 40), _ose.get_rect())
                screen.blit(_ose, (x - 10, y + h - 20))
            draw_card(screen, x, y, w, h, highlight=(is_selected and unlocked), alpha=235 if unlocked else 210)

            # 坦克图标
            icon_size = 72
            icon_x = x + (w - icon_size) // 2
            icon_y = y + 18
            draw_tank_icon(screen, icon_x, icon_y, info["color"], size=icon_size,
                           unlocked=unlocked,
                           style=TANK_STYLE_BY_NAME.get(name, TANK_STYLE_STANDARD))

            # 坦克代号徽章（钢蓝，等宽感，强化辨识；新增装饰，不动逻辑）
            _codes = {"轻型侦察车": "SCOUT-01", "重装突击车": "HEAVY-02",
                      "激光狙击车": "LASER-03", "KZY 终极战车": "KZY-Ω"}
            _code = _codes.get(name, "")
            if _code:
                draw_text(screen, _code, x + w - 8, y + 8, fonts, FONT_XS, COLOR_CYAN, center_x=True)

            # 坦克名称
            name_color = info["color"] if unlocked else COLOR_GRAY
            draw_text(screen, name, x + w // 2, y + 112,
                      fonts, FONT_M, name_color, center=True)

            # 定位
            draw_text(screen, info["role"], x + w // 2, y + 140,
                      fonts, FONT_XS, COLOR_CYAN if unlocked else COLOR_DARK_GRAY, center=True)

            # 属性
            attr_y = y + 165
            # 血量（心形矢量图标，无 emoji 依赖）
            draw_text(screen, "血量", x + 15, attr_y, fonts, FONT_XS,
                      COLOR_RED if unlocked else COLOR_DARK_GRAY)
            draw_hearts(screen, x + 15 + 34, attr_y, info["hp"],
                        color=COLOR_RED if unlocked else COLOR_DARK_GRAY,
                        size=16, gap=3)
            # 移速
            draw_text(screen, f"移速 {info['speed']}", x + 15, attr_y + 20,
                      fonts, FONT_XS, COLOR_GREEN if unlocked else COLOR_DARK_GRAY)
            # 初始道具（彩色圆点 + 名称，避免 emoji 占位）
            dot_color, item_text = None, "无"
            if info["init_item"] == "scatter":
                dot_color, item_text = COLOR_BLUE, "散射弹"
            elif info["init_item"] == "laser":
                dot_color, item_text = COLOR_RED, "激光炮"
            elif info["init_item"] == "bounce_scatter":
                dot_color, item_text = COLOR_GREEN, "弹射+散射"
            draw_text(screen, "道具", x + 15, attr_y + 40, fonts, FONT_XS,
                      COLOR_BLUE if unlocked else COLOR_DARK_GRAY)
            if dot_color:
                pygame.draw.circle(screen, dot_color,
                                   (x + 15 + 44, attr_y + 40 + FONT_XS // 2 - 1), 6)
                draw_text(screen, item_text, x + 15 + 56, attr_y + 40, fonts, FONT_XS,
                          COLOR_BLUE if unlocked else COLOR_DARK_GRAY)
            else:
                draw_text(screen, item_text, x + 15 + 44, attr_y + 40, fonts, FONT_XS,
                          COLOR_BLUE if unlocked else COLOR_DARK_GRAY)

            # 解锁条件 / 锁定遮罩
            if not unlocked:
                # 半透明遮罩
                mask = pygame.Surface((w, h), pygame.SRCALPHA)
                mask.fill((0, 0, 0, 150))
                screen.blit(mask, (x, y))
                # 红色对角线条纹（禁止使用标识，45 度，间隔 8px）
                _stripes = pygame.Surface((w, h), pygame.SRCALPHA)
                for _i in range(-h, w + h, 8):
                    pygame.draw.line(_stripes, (255, 0, 0, 45),
                                     (_i, 0), (_i + h, h), 2)
                screen.blit(_stripes, (x, y))
                tw = fonts[FONT_L].size("未解锁")[0]
                cx = x + w // 2
                draw_lock(screen, cx - tw // 2 - 26, y + 30 - 10, 20, COLOR_GRAY)
                draw_text(screen, "未解锁", cx, y + 30,
                          fonts, FONT_L, COLOR_GRAY, center=True)
                draw_text(screen, "解锁条件:", x + w // 2, y + 210,
                          fonts, FONT_XS, COLOR_LIGHT_GRAY, center=True)
                draw_text(screen, info["unlock_desc"], x + w // 2, y + 228,
                          fonts, FONT_S, COLOR_YELLOW, center=True)
                # 进度条
                cond = info["unlock_condition"]
                progress = 0
                target = 1
                if cond["type"] == "level":
                    progress = min(save["highest_level_cleared"], cond["value"])
                    target = cond["value"]
                elif cond["type"] == "battles":
                    progress = min(save["total_battles"], cond["value"])
                    target = cond["value"]
                pct = progress / target if target > 0 else 0
                bar_x, bar_y, bar_w, bar_h = x + 20, y + 248, w - 40, 10
                draw_progress_bar(screen, bar_x, bar_y, bar_w, bar_h, pct, COLOR_YELLOW)
                draw_text(screen, f"{progress}/{target}", x + w // 2, bar_y + bar_h + 4,
                          fonts, FONT_XS, COLOR_WHITE, center=True)

        # 详情面板
        selected_name = TANK_ORDER[self.selected_idx]
        selected_info = TANK_DATA[selected_name]
        selected_unlocked = selected_name in save.get("unlocked_tanks", [])
        panel_x, panel_y, panel_w, panel_h = 80, 420, SCREEN_WIDTH - 160, 100
        draw_glass_panel(screen, panel_x, panel_y, panel_w, panel_h, alpha=220)
        draw_text(screen, f"{selected_name} - 详细属性",
                  panel_x + 25, panel_y + 15, fonts, FONT_M,
                  selected_info["color"] if selected_unlocked else COLOR_GRAY)
        desc = selected_info["description"]
        draw_text(screen, desc,
                  panel_x + 25, panel_y + 52, fonts, FONT_S,
                  COLOR_LIGHT_GRAY if selected_unlocked else COLOR_DARK_GRAY)
        if not selected_unlocked:
            draw_text(screen, f"解锁条件: {selected_info['unlock_desc']}",
                      panel_x + 25, panel_y + 82, fonts, FONT_S, COLOR_ORANGE)
        else:
            last = save.get("last_selected_tank", "")
            if last == selected_name:
                draw_text(screen, "当前出战坦克",
                          panel_x + panel_w - 200, panel_y + 82, fonts, FONT_S, COLOR_GREEN)
            else:
                draw_text(screen, "↓ 点击下方按钮选为出战坦克",
                          panel_x + panel_w - 230, panel_y + 82, fonts, FONT_S, COLOR_YELLOW)

        # 能力条（血量/火力/机动，3 条横向，坦克同色填充）
        if selected_unlocked:
            _ab_x = panel_x + 440
            _ab_y = panel_y + 14
            _bw, _bhh, _gap = 170, 10, 22
            _sp_map = {"快": 1.0, "中等": 0.6, "慢": 0.35}
            _fp_map = {None: 0.3, "scatter": 0.7, "laser": 0.9, "bounce_scatter": 1.0}
            _stats = [
                ("血量", selected_info["hp"] / 6.0),
                ("火力", _fp_map.get(selected_info["init_item"], 0.3)),
                ("机动", _sp_map.get(selected_info["speed"], 0.5)),
            ]
            _sc = selected_info["color"]
            for _i, (_lbl, _r) in enumerate(_stats):
                _ay = _ab_y + _i * _gap
                draw_text(screen, _lbl, _ab_x, _ay, fonts, FONT_XS, COLOR_LIGHT_GRAY)
                _bx = _ab_x + 40
                _byy = _ay + 2
                pygame.draw.rect(screen, (30, 58, 95), (_bx, _byy, _bw, _bhh), border_radius=2)
                if _r > 0:
                    pygame.draw.rect(screen, _sc,
                                     (_bx, _byy, int(_bw * _r), _bhh), border_radius=2)

        # 选择按钮（未解锁时禁用）
        self.select_btn.disabled = not selected_unlocked
        self.select_btn.draw(screen, fonts)

        self.back_btn.draw(screen, fonts)
        draw_corner_logo(screen, fonts)


class CarnivalScreen:
    """道具狂欢模式（无尽）：大量道具 + 持续生成敌人 + 实时计分。"""

    def __init__(self, game):
        self.game = game
        self.world = None
        self.time = 0.0
        self.back_btn = None
        self.menu_btn = None
        self.retry_btn = None
        self.leaderboard_btn = None
        self.result_popup = None
        # 玩家鼠标拖拽状态（与单人模式统一操作系统）
        self.dragging = False
        self.drag_start = (0, 0)
        self.drag_cur = (0, 0)
        self.mouse_down = False
        self._build_buttons()

    def _build_buttons(self):
        self.back_btn = Button(SCREEN_WIDTH - 200, SCREEN_HEIGHT - 70, 170, 44,
                               "← 返回菜单", FONT_M)
        self.retry_btn = Button(0, 0, 150, 48, "再来一局", FONT_L)
        self.menu_btn = Button(0, 0, 150, 48, "回主菜单", FONT_L)
        self.leaderboard_btn = Button(0, 0, 150, 48, "查看排行榜", FONT_L)

    def _start_game(self):
        save = get_save(self.game)
        tank_name = save.get("last_selected_tank", "轻型侦察车")
        if tank_name not in save.get("unlocked_tanks", ["轻型侦察车"]):
            tank_name = "轻型侦察车"
        self.world = CarnivalGameWorld(tank_name, self.game.fonts)
        self.result_popup = None
        self.time = 0.0
        self.dragging = False
        self.mouse_down = False

    def enter(self):
        self._start_game()

    def handle_event(self, event):
        if self.world is not None and self.result_popup is None:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.dragging = True
                self.drag_start = event.pos
                self.drag_cur = event.pos
                self.mouse_down = True
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self.dragging = False
                self.mouse_down = False
            elif event.type == pygame.MOUSEMOTION and self.dragging:
                self.drag_cur = event.pos

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.game.change_state(STATE_MENU)
                return
            if self.result_popup is not None:
                if event.key == pygame.K_r:
                    self._start_game()
                    return
                if event.key == pygame.K_m:
                    self.game.change_state(STATE_MENU)
                    return
                if event.key == pygame.K_l:
                    self.game.change_state(STATE_LEADERBOARD)
                    return

        if self.result_popup is not None:
            if self.retry_btn.handle_event(event):
                self._start_game()
                return
            if self.menu_btn.handle_event(event):
                self.game.change_state(STATE_MENU)
                return
            if self.leaderboard_btn.handle_event(event):
                self.game.change_state(STATE_LEADERBOARD)
                return

        if self.back_btn.handle_event(event):
            self.game.change_state(STATE_MENU)
            return

    def update(self, dt):
        self.time += dt
        if self.world is None:
            return
        keys = pygame.key.get_pressed()
        ctrl = build_p1_control(keys, self.mouse_down, self.dragging,
                                self.drag_start, self.drag_cur, self.world.player)
        self.world.set_input(ctrl)
        self.world.update(dt)
        if self.world.result != GameWorld.RESULT_NONE and self.result_popup is None:
            self._on_game_end()

    def _on_game_end(self):
        """玩家阵亡：记录到「道具狂欢」排行榜。"""
        save = get_save(self.game)
        name = self.world.player.tank_name
        save = SaveManager.record_leaderboard(save, name, self.world.score, "carnival")
        persist_save(self.game, save)
        self.result_popup = {
            "score": self.world.score,
            "kills": self.world.enemies_killed,
            "time": self.world.time,
        }

    def draw(self, screen, fonts):
        draw_bg(screen)
        if self.world is None:
            return
        w = self.world
        player = w.player
        w.draw(screen, ARENA_X, ARENA_Y, fonts)

        hud_y = 12
        # 左上：血量
        lp_x, lp_y, lp_w, lp_h = 20, hud_y, 260, 60
        draw_glass_panel(screen, lp_x, lp_y, lp_w, lp_h, alpha=200)
        draw_text(screen, "装甲能量", lp_x + 12, lp_y + 8, fonts, FONT_XS, COLOR_LIGHT_GRAY)
        hp_ratio = max(0.0, min(1.0, player.hp / max(1, player.max_hp)))
        bar_x, bar_y, bar_w, bar_h = lp_x + 12, lp_y + 30, 120, 10
        ebar_bg = pygame.Surface((bar_w, bar_h), pygame.SRCALPHA)
        ebar_bg.fill((60, 20, 20))
        screen.blit(ebar_bg, (bar_x, bar_y))
        fg_surf = pygame.Surface((bar_w, bar_h), pygame.SRCALPHA)
        for i in range(bar_w):
            t = i / max(1, bar_w)
            r = int(COLOR_RED[0] + (COLOR_GOLD[0] - COLOR_RED[0]) * t)
            g = int(COLOR_RED[1] + (COLOR_GOLD[1] - COLOR_RED[1]) * t)
            b = int(COLOR_RED[2] + (COLOR_GOLD[2] - COLOR_RED[2]) * t)
            fg_surf.fill((r, g, b, 255), (i, 0, 1, bar_h))
        screen.blit(fg_surf, (bar_x, bar_y), (0, 0, int(bar_w * hp_ratio), bar_h))
        pygame.draw.rect(screen, COLOR_BTN_BORDER, (bar_x, bar_y, bar_w, bar_h), width=1, border_radius=3)
        draw_text(screen, f"{max(0, player.hp)}/{player.max_hp}",
                  bar_x + bar_w + 8, bar_y - 2, fonts, FONT_XS, COLOR_WHITE)
        draw_text(screen, player.tank_name, lp_x + 12, lp_y + 44, fonts, FONT_S,
                  TANK_DATA.get(player.tank_name, {}).get("color", COLOR_WHITE))

        # 中：得分 + 击杀 + 时间
        mp_w, mp_h = 300, 60
        mp_x = (SCREEN_WIDTH - mp_w) // 2
        draw_glass_panel(screen, mp_x, hud_y, mp_w, mp_h, alpha=200)
        draw_text(screen, f"得分 {w.score}   击毁 {w.enemies_killed}",
                  mp_x + mp_w // 2, hud_y + 14, fonts, FONT_L, COLOR_GOLD, center=True)
        draw_text(screen, f"已生存 {int(w.time)}s",
                  mp_x + mp_w // 2, hud_y + 40, fonts, FONT_S, COLOR_CYAN, center=True)

        # 右：增益
        active = player.get_active_powerups()
        shield_on = player.shield_active
        draw_glass_panel(screen, SCREEN_WIDTH - 280, hud_y, 260, 60, alpha=200)
        draw_text(screen, "增益", SCREEN_WIDTH - 268, hud_y + 8, fonts, FONT_XS, COLOR_LIGHT_GRAY)
        if active or shield_on:
            names = [POWERUP_NAMES.get(t, str(t)) for t in active]
            buff_name = "+".join(names) if names else ""
            if shield_on:
                buff_name = (buff_name + " +护盾") if buff_name else "护盾"
            color = COLOR_GOLD if len(active) > 1 else (
                POWERUP_COLORS.get(active[0], COLOR_WHITE) if active else COLOR_YELLOW)
            draw_text(screen, buff_name, SCREEN_WIDTH - 268, hud_y + 32, fonts, FONT_M, color)
        else:
            draw_text(screen, "无", SCREEN_WIDTH - 268, hud_y + 32, fonts, FONT_M, COLOR_GRAY)

        # 底部操作提示
        draw_text(screen, "A/D 转向 · W/S 移动 · 左键开火 · 拖拽瞄准/前进 · ESC返回",
                  SCREEN_WIDTH // 2, SCREEN_HEIGHT - 28, fonts, FONT_S, COLOR_LIGHT_GRAY, center=True)
        self.back_btn.draw(screen, fonts)

        if self.result_popup:
            self._draw_result_popup(screen, fonts)

    def _draw_result_popup(self, screen, fonts):
        info = self.result_popup
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        screen.blit(overlay, (0, 0))
        draw_vignette(screen, 0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, strength=170)
        pw, ph = 520, 360
        px, py = (SCREEN_WIDTH - pw) // 2, (SCREEN_HEIGHT - ph) // 2
        draw_glass_panel(screen, px, py, pw, ph, alpha=245)
        draw_text(screen, "狂欢结束", px + pw // 2, py + 50, fonts, FONT_XXL, COLOR_GOLD, center=True)
        draw_text(screen, f"最终得分 {info['score']}    击毁 {info['kills']} 辆",
                  px + pw // 2, py + 110, fonts, FONT_L, COLOR_LIGHT_GRAY, center=True)
        draw_text(screen, f"生存时间 {int(info['time'])}s",
                  px + pw // 2, py + 150, fonts, FONT_M, COLOR_CYAN, center=True)
        draw_text(screen, "成绩已计入排行榜",
                  px + pw // 2, py + ph - 104, fonts, FONT_S, COLOR_GRAY, center=True)
        bw, bh = 150, 48
        gap = 20
        total = bw * 3 + gap * 2
        sx = (SCREEN_WIDTH - total) // 2
        by = py + ph - 58
        self.retry_btn.rect.topleft = (sx, by)
        self.menu_btn.rect.topleft = (sx + bw + gap, by)
        self.leaderboard_btn.rect.topleft = (sx + (bw + gap) * 2, by)
        self.retry_btn.draw(screen, fonts)
        self.menu_btn.draw(screen, fonts)
        self.leaderboard_btn.draw(screen, fonts)
        draw_text(screen, "快捷键: R 再来一局   M 回主菜单   L 排行榜",
                  SCREEN_WIDTH // 2, SCREEN_HEIGHT - 28, fonts, FONT_S, COLOR_YELLOW, center=True)


class LeaderboardScreen:
    """积分排行榜：展示「道具狂欢」与「双人合作」两类成绩。"""

    def __init__(self, game):
        self.game = game
        self.back_btn = None
        self._build_buttons()

    def _build_buttons(self):
        self.back_btn = Button(40, SCREEN_HEIGHT - 70, 160, 48, "← 返回菜单", FONT_M)

    def enter(self):
        pass

    def handle_event(self, event):
        if self.back_btn.handle_event(event):
            self.game.change_state(STATE_MENU)

    def update(self, dt):
        pass

    def draw(self, screen, fonts):
        draw_bg(screen)
        save = get_save(self.game)
        draw_glow_accent(screen, SCREEN_WIDTH // 2, 56, "积分排行榜",
                         fonts, FONT_XXL, COLOR_GOLD)
        draw_text(screen, "道具狂欢 · 双人合作 成绩排行（各取前 10）",
                  SCREEN_WIDTH // 2, 104, fonts, FONT_S, COLOR_CYAN, center=True)

        carnival = SaveManager.get_leaderboard(save, "carnival")
        vs_ai = SaveManager.get_leaderboard(save, "vs_ai")
        self._draw_board(screen, fonts, "道具狂欢模式", carnival, 80, 150)
        self._draw_board(screen, fonts, "双人合作模式", vs_ai, SCREEN_WIDTH // 2 + 20, 150)

        self.back_btn.draw(screen, fonts)
        draw_corner_logo(screen, fonts)

    def _draw_board(self, screen, fonts, title, entries, x, y):
        w = SCREEN_WIDTH // 2 - 110
        draw_glass_panel(screen, x, y, w, 430, alpha=200)
        draw_text(screen, title, x + w // 2, y + 14, fonts, FONT_M, COLOR_GOLD, center=True)
        pygame.draw.line(screen, COLOR_BTN_BORDER, (x + 16, y + 44), (x + w - 16, y + 44), 1)
        if not entries:
            draw_text(screen, "暂无记录", x + w // 2, y + 120, fonts, FONT_S, COLOR_GRAY, center=True)
            return
        ry = y + 64
        for i, e in enumerate(entries[:10]):
            col = COLOR_GOLD if i == 0 else (COLOR_CYAN if i == 1 else COLOR_WHITE)
            draw_text(screen, f"{i + 1}. {e['name']}", x + 16, ry, fonts, FONT_S, col)
            draw_text(screen, f"{e['score']} 分 · {e.get('date', '')}",
                      x + w - 16, ry, fonts, FONT_XS, col, center=True)
            ry += 34
