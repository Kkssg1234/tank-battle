"""
各个游戏界面模块
"""
import pygame
import math
import random
from constants import *
from level_config import TOTAL_LEVELS, get_level_config
from ui_utils import (Button, draw_text, draw_bg, draw_corner_logo, draw_panel,
                      draw_tank_icon, draw_card, draw_badge, draw_progress_bar,
                      draw_glow_accent, draw_divider)
from vfx import draw_glow
from save_manager import SaveManager, ScoreSystem
from game_world import GameWorld, TwoPlayerGameWorld
from level_manager import LevelManager
from powerup import (POWERUP_NAMES, POWERUP_COLORS,
                     POWERUP_DURATION, PERMA_BUFF_THRESHOLD)


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


class MenuScreen:
    """主菜单界面"""
    def __init__(self, game):
        self.game = game
        self.buttons = []
        self.time = 0
        self._build_buttons()

    def _build_buttons(self):
        cx = SCREEN_WIDTH // 2
        bw, bh = 280, 56
        sy = 260
        gap = 22
        self.buttons = [
            Button(cx - bw // 2, sy, bw, bh, "🎮 单人闯关模式", FONT_L),
            Button(cx - bw // 2, sy + bh + gap, bw, bh, "👥 双人模式", FONT_L),
            Button(cx - bw // 2, sy + (bh + gap) * 2, bw, bh, "🚗 车库", FONT_L),
            Button(cx - bw // 2, sy + (bh + gap) * 3, bw, bh, "❌ 退出游戏", FONT_L),
        ]

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
                    self.game.change_state(STATE_GARAGE)
                elif i == 3:
                    self.game.running = False
                return

    def update(self, dt):
        self.time += dt

    def draw(self, screen, fonts):
        draw_bg(screen)

        # 标题 - 浮动动画 + 辉光强调（幅度缩小，避免与下方存档条重叠）
        title_y = 92 + math.sin(self.time * 2) * 4
        draw_glow_accent(screen, SCREEN_WIDTH // 2, title_y, "🎯 坦 克 大 战",
                         fonts, FONT_XXL, COLOR_GOLD)
        draw_text(screen, "TANK BATTLE", SCREEN_WIDTH // 2, title_y + 70,
                  fonts, FONT_L, COLOR_CYAN, center=True)
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

        for btn in self.buttons:
            btn.draw(screen, fonts)

        # 底部版本号
        draw_text(screen, "v1.1.0  Core Playable", 20, SCREEN_HEIGHT - 30,
                  fonts, FONT_XS, COLOR_GRAY)
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
            if not unlocked:
                text = f"🔒 {level_num}"
            btn = Button(x, y, bw, bh, text, FONT_M, disabled=not unlocked)
            self.level_buttons.append((btn, level_num, unlocked))

        self.back_btn = Button(40, SCREEN_HEIGHT - 70, 160, 48, "← 返回菜单", FONT_M)
        self.start_btn = Button(SCREEN_WIDTH // 2 - 110, SCREEN_HEIGHT - 95, 220, 48,
                                "🚀 开始战斗", FONT_L)

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
        draw_glow_accent(screen, SCREEN_WIDTH // 2, 55, "🎮 单人闯关模式 - 选择关卡",
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
        draw_text(screen, "🎉 恭 喜 通 关 !", SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 70,
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

        # 按钮（底部居中排布）
        pbw, pbh = 150, 50
        cx = SCREEN_WIDTH // 2
        by = (SCREEN_HEIGHT - self.PH) // 2 + self.PH - 80
        self.next_btn = Button(cx - 235, by, pbw, pbh, "➡ 下一关", FONT_M)
        self.retry_btn = Button(cx - 75, by, pbw, pbh, "🔄 重试", FONT_M)
        self.menu_btn = Button(cx + 85, by, pbw, pbh, "🏠 选关", FONT_M)
        self.next_btn.disabled = not self.show_next

    def draw(self, screen, fonts):
        # 半透明黑色背景遮罩（alpha 180）
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        screen.blit(overlay, (0, 0))

        pw, ph = self.PW, self.PH
        px = (SCREEN_WIDTH - pw) // 2
        py = (SCREEN_HEIGHT - ph) // 2
        draw_panel(screen, px, py, pw, ph, alpha=245)

        if self.victory:
            title, col = "🎉 胜 利 !", COLOR_GOLD
        else:
            title, col = "💀 失 败", COLOR_RED
        draw_glow_accent(screen, px + pw // 2, py + 50, title,
                         fonts, FONT_XXL, col)
        draw_text(screen, f"第 {self.level} 关", px + pw // 2, py + 112,
                  fonts, FONT_L, COLOR_CYAN, center=True)

        # 数据行
        draw_text(screen, f"得分: {self.score}", px + pw // 2, py + 162,
                  fonts, FONT_M, COLOR_YELLOW, center=True)
        draw_text(screen, f"击毁: {self.enemies_killed} 辆", px + pw // 2, py + 197,
                  fonts, FONT_M, COLOR_WHITE, center=True)
        draw_text(screen, f"用时: {self.time_used} 秒", px + pw // 2, py + 230,
                  fonts, FONT_S, COLOR_LIGHT_GRAY, center=True)
        if self.total_battles is not None:
            draw_text(screen, f"累计战斗: {self.total_battles} 场", px + pw // 2, py + 256,
                      fonts, FONT_S, COLOR_CYAN, center=True)

        # 评价（大字 + 辉光强调）
        grade_col = {
            "S": COLOR_GOLD, "A": COLOR_GREEN,
            "B": COLOR_CYAN, "C": COLOR_LIGHT_GRAY,
        }[self.grade]
        draw_glow_accent(screen, px + pw // 2, py + 272, f"评价 {self.grade}",
                         fonts, FONT_XL, grade_col)

        # 解锁提示（预留：Round 4 传入解锁的坦克名称）
        for i, name in enumerate(self.new_unlocks):
            draw_text(screen, f"🎉 新坦克解锁: {name}",
                      px + pw // 2, py + 305 + i * 22,
                      fonts, FONT_S, COLOR_GREEN, center=True)

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

        # 每帧轮询键盘状态，避免事件式追踪在失焦/连发时丢键
        keys = pygame.key.get_pressed()
        dx, dy = 0, 0
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            dy -= 1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            dy += 1
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            dx -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            dx += 1
        fire = keys[pygame.K_SPACE] or keys[pygame.K_j]
        self.world.set_input(dx, dy, fire)
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

        # ---- 顶部 HUD ----
        hud_y = 20
        # 血量
        hp_hearts = "❤️" * max(0, player.hp)
        if player.hp <= 0:
            hp_hearts = "💀"
        hp_text = f"血量: {hp_hearts}"
        draw_text(screen, hp_text, 60, hud_y + 8, fonts, FONT_M, COLOR_RED)

        # 当前坦克
        draw_text(screen, f"🚗 {tank_name}", 280, hud_y + 8,
                  fonts, FONT_M, tank_info["color"])

        # 关卡信息 & 剩余敌人
        remaining = w.remaining_enemies()
        draw_text(screen, f"🎯 第 {level} 关   👾 剩余 {remaining}",
                  SCREEN_WIDTH // 2, hud_y + 8, fonts, FONT_M, COLOR_CYAN, center=True)

        # 得分（右对齐）
        score_surf = fonts[FONT_M].render(f"🏆 得分: {w.score}", True, COLOR_YELLOW)
        screen.blit(score_surf, (SCREEN_WIDTH - 20 - score_surf.get_width(), hud_y + 8))

        # 道具栏（左下角：彩色小方块图标 + 名称 + 倒计时条）——叠加版
        active = player.get_active_powerups()
        shield_on = player.shield_active
        if active:
            # 名称拼接（叠加显示 "+" 连接，金色）；单道具用本色
            names = [POWERUP_NAMES.get(t, str(t)) for t in active]
            buff_name = "+".join(names)
            if len(active) > 1:
                buff_color = COLOR_GOLD
            else:
                buff_color = POWERUP_COLORS.get(active[0], COLOR_WHITE)
            # 剩余时间：显示限时道具中最短的；全部 perma 才显示 ∞
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
        # 护盾单独显示（次数型，不计时）；只要 shield_active 为 True 就显示盾牌图标
        if shield_on:
            buff_name = (buff_name + "  🛡") if buff_name != "无" else "🛡护盾"

        # 彩色小方块图标（叠加时画多个色块）
        item_y = SCREEN_HEIGHT - 38
        bar_x, bar_y, bar_w, bar_h = 60, SCREEN_HEIGHT - 14, 140, 7
        if active:
            icon_x = 60
            for t in active[:3]:  # 最多画 3 个色块，避免过长
                pygame.draw.rect(screen, POWERUP_COLORS.get(t, COLOR_WHITE),
                                 (icon_x, item_y, 14, 14), border_radius=3)
                icon_x += 18
            text_x = icon_x + 2
        else:
            text_x = 60
        draw_text(screen, f"{buff_name} {remain_txt}".strip(),
                  text_x, item_y, fonts, FONT_S, buff_color)

        # 倒计时条（绿→红渐变：剩余越多越绿，越少越红）
        pygame.draw.rect(screen, (40, 40, 50), (bar_x, bar_y, bar_w, bar_h), border_radius=3)
        if ratio > 0:
            cr = int(220 * (1 - ratio))   # 红分量：时间越少越红
            cg = int(190 * ratio)          # 绿分量：时间越多越绿
            pygame.draw.rect(screen, (cr, cg, 36),
                             (bar_x, bar_y, int(bar_w * ratio), bar_h), border_radius=3)

        # 关卡主题提示（黑底白字主题）
        draw_text(screen, "💠 关卡主题: 浪尖儿学生社区",
                  SCREEN_WIDTH // 2, 60, fonts, FONT_S,
                  COLOR_WHITE, center=True)

        # 友军伤害提示
        tip_color = COLOR_ORANGE if int(self.time * 2) % 2 == 0 else COLOR_YELLOW
        draw_text(screen, "⚠️ " + FRIENDLY_FIRE_TIP,
                  ARENA_X + ARENA_W // 2, ARENA_Y - 14,
                  fonts, FONT_XS, tip_color, center=True)

        # 底部按钮 / 操作提示
        self.back_btn.draw(screen, fonts)
        draw_text(screen, "WASD移动  空格/J射击  ESC返回选关",
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
    """双人模式子模式选择"""
    def __init__(self, game):
        self.game = game
        self.coop_btn = None
        self.vs_btn = None
        self.back_btn = None
        self._build_buttons()

    def _build_buttons(self):
        cx = SCREEN_WIDTH // 2
        bw, bh = 300, 80
        self.coop_btn = Button(cx - bw // 2, 230, bw, bh, "🤝 合作对抗 AI", FONT_L)
        self.vs_btn = Button(cx - bw // 2, 340, bw, bh, "⚔️  1v1 对战", FONT_L)
        self.back_btn = Button(40, SCREEN_HEIGHT - 80, 160, 48, "← 返回菜单", FONT_M)

    def enter(self):
        pass

    def handle_event(self, event):
        if self.back_btn.handle_event(event):
            self.game.change_state(STATE_MENU)
            return
        if self.coop_btn.handle_event(event):
            self.game.two_mode = "coop"
            self.game.change_state(STATE_P2_TANK_SELECT)
        elif self.vs_btn.handle_event(event):
            self.game.two_mode = "vs"
            self.game.change_state(STATE_P2_TANK_SELECT)

    def update(self, dt):
        pass

    def draw(self, screen, fonts):
        draw_bg(screen)

        draw_glow_accent(screen, SCREEN_WIDTH // 2, 70, "👥 双人模式",
                         fonts, FONT_XXL, COLOR_GOLD)
        draw_text(screen, "选择子模式", SCREEN_WIDTH // 2, 140,
                  fonts, FONT_L, COLOR_CYAN, center=True)

        # 说明
        draw_panel(screen, 120, 460, SCREEN_WIDTH - 240, 110, alpha=200)
        draw_text(screen, "🎮 玩家 1:  WASD 移动 + 空格 射击",
                  160, 490, fonts, FONT_M, COLOR_GREEN)
        draw_text(screen, "🖱️ 玩家 2:  鼠标移动控制方向+位置，左键射击",
                  160, 530, fonts, FONT_M, COLOR_BLUE)
        draw_text(screen, "⚠️  双人模式不计入坦克解锁的战斗场次统计",
                  160, 560, fonts, FONT_S, COLOR_ORANGE)

        self.coop_btn.draw(screen, fonts)
        self.vs_btn.draw(screen, fonts)
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
        y = 150
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

        self.confirm_btn = Button(SCREEN_WIDTH // 2 - 95, 540, 190, 48, "✔ 确认出战", FONT_L)
        self.back_btn = Button(40, SCREEN_HEIGHT - 70, 160, 48, "← 返回模式", FONT_M)

    def enter(self):
        self._build_buttons()

    def handle_event(self, event):
        if self.back_btn.handle_event(event):
            self.game.change_state(STATE_TWO_PLAYER_SELECT)
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
                self.game.p2_tank = name
                self.game.change_state(STATE_TWO_PLAY)

    def update(self, dt):
        pass

    def draw(self, screen, fonts):
        draw_bg(screen)
        save = get_save(self.game)
        unlocked = save.get("unlocked_tanks", [])

        draw_glow_accent(screen, SCREEN_WIDTH // 2, 55, "🚗 玩家 2 · 选择坦克",
                         fonts, FONT_XXL, COLOR_GOLD)
        draw_text(screen, f"已解锁 {len(unlocked)}/{len(TANK_ORDER)}   |   当前模式: {'合作对抗 AI' if self.game.two_mode == 'coop' else '1v1 对战'}",
                  SCREEN_WIDTH // 2, 110, fonts, FONT_S, COLOR_CYAN, center=True)
        draw_text(screen, "请玩家 2 选择出战坦克（已解锁车辆可选）",
                  SCREEN_WIDTH // 2, 135, fonts, FONT_S, COLOR_WHITE, center=True)

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
                           size=icon_size, unlocked=is_unlocked)

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
            hp_hearts = "❤️" * info["hp"]
            draw_text(screen, f"血量 {hp_hearts}", x + 15, attr_y,
                      fonts, FONT_XS, COLOR_RED if is_unlocked else COLOR_DARK_GRAY)
            draw_text(screen, f"移速 {info['speed']}", x + 15, attr_y + 20,
                      fonts, FONT_XS, COLOR_GREEN if is_unlocked else COLOR_DARK_GRAY)
            item_text = "无"
            if info["init_item"] == "scatter":
                item_text = "🔵散射弹"
            elif info["init_item"] == "laser":
                item_text = "🔴激光炮"
            elif info["init_item"] == "bounce_scatter":
                item_text = "🟢🔵弹射+散射"
            draw_text(screen, f"道具 {item_text}", x + 15, attr_y + 40,
                      fonts, FONT_XS, COLOR_BLUE if is_unlocked else COLOR_DARK_GRAY)

            # 锁定遮罩与解锁条件
            if not is_unlocked:
                mask = pygame.Surface((w, h), pygame.SRCALPHA)
                mask.fill((0, 0, 0, 150))
                screen.blit(mask, (x, y))
                draw_text(screen, "🔒 未解锁", x + w // 2, y + 40,
                          fonts, FONT_M, COLOR_GRAY, center=True)
                draw_text(screen, "解锁条件:", x + w // 2, y + 205,
                          fonts, FONT_XS, COLOR_LIGHT_GRAY, center=True)
                draw_text(screen, info["unlock_desc"], x + w // 2, y + 222,
                          fonts, FONT_S, COLOR_YELLOW, center=True)

        # 底部：当前选中 + 确认
        sel_name = TANK_ORDER[self.selected_idx]
        sel_ok = sel_name in unlocked
        sel_color = TANK_DATA[sel_name]["color"] if sel_ok else COLOR_GRAY
        draw_text(screen, f"已选: {sel_name}", SCREEN_WIDTH // 2, 508,
                  fonts, FONT_M, sel_color, center=True)
        self.confirm_btn.disabled = not sel_ok
        self.confirm_btn.draw(screen, fonts)
        self.back_btn.draw(screen, fonts)

        draw_text(screen, "操作提示: 鼠标点击选择车辆，确认后进入对局",
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
        self.result_popup = None
        self._build_buttons()

    def _build_buttons(self):
        self.back_btn = Button(SCREEN_WIDTH - 200, SCREEN_HEIGHT - 70, 170, 44,
                               "← 返回选择", FONT_M)
        self.retry_btn = Button(SCREEN_WIDTH // 2 - 100, SCREEN_HEIGHT // 2 + 80,
                                200, 52, "🔄 再来一局", FONT_L)
        self.menu_btn = Button(SCREEN_WIDTH // 2 - 100, SCREEN_HEIGHT // 2 + 150,
                               200, 52, "🏠 回主菜单", FONT_L)

    def _start_game(self):
        """初始化双人游戏世界"""
        mode = self.game.two_mode  # "coop" 或 "vs"
        # 玩家 1 使用存档选中的坦克；玩家 2 使用选车界面确认的坦克（未解锁则兜底基础车）
        save = get_save(self.game)
        t1 = save.get("last_selected_tank", "轻型侦察车")
        if t1 not in save.get("unlocked_tanks", []):
            t1 = "轻型侦察车"
        t2 = self.game.p2_tank if self.game.p2_tank in save.get("unlocked_tanks", []) else "轻型侦察车"

        level = self.game.current_level if mode == "coop" else 1
        self.world = TwoPlayerGameWorld(mode, level, t1, t2, self.game.fonts)
        self.result_popup = None
        self.time = 0.0

    def enter(self):
        self._start_game()

    def handle_event(self, event):
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

        if self.result_popup is not None:
            if self.retry_btn.handle_event(event):
                self._start_game()
                return
            if self.menu_btn.handle_event(event):
                self.game.change_state(STATE_MENU)
                return

        if self.back_btn.handle_event(event):
            self.game.change_state(STATE_TWO_PLAYER_SELECT)
            return

    def update(self, dt):
        self.time += dt
        if self.world is None:
            return

        # ---- 玩家 1 输入（键盘轮询）----
        keys = pygame.key.get_pressed()
        p1_dx, p1_dy, p1_fire = 0, 0, False
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            p1_dy -= 1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            p1_dy += 1
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            p1_dx -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            p1_dx += 1
        p1_fire = keys[pygame.K_SPACE] or keys[pygame.K_j]

        # ---- 玩家 2 输入（鼠标控制）----
        mouse_pos = pygame.mouse.get_pos()
        mouse_buttons = pygame.mouse.get_pressed()
        p2_fire = mouse_buttons[0]

        p2_dx, p2_dy = 0.0, 0.0
        if self.world.player2.alive:
            # 转换鼠标坐标到竞技场内部坐标
            arena_mx = mouse_pos[0] - ARENA_X
            arena_my = mouse_pos[1] - ARENA_Y
            dx = arena_mx - self.world.player2.x
            dy = arena_my - self.world.player2.y
            dist = math.hypot(dx, dy)
            if dist > MOUSE_CONTROL_DEADZONE:
                p2_dx = dx / dist
                p2_dy = dy / dist

        self.world.set_input(p1_dx, p1_dy, p1_fire, p2_dx, p2_dy, p2_fire)
        self.world.update(dt)

        # 结算检测
        if self.world.result != TwoPlayerGameWorld.RESULT_NONE and self.result_popup is None:
            self._on_game_end()

    def _on_game_end(self):
        """游戏结束，仅显示结算，不写入存档（双人模式不计入解锁）"""
        result = self.world.result
        mode = self.game.two_mode
        self.result_popup = {
            "result": result,
            "mode": mode,
            "score": self.world.score,
        }

    def draw(self, screen, fonts):
        draw_bg(screen)
        if self.world is None:
            return

        w = self.world
        mode_txt = "🤝 合作模式" if w.mode == "coop" else "⚔️  对战模式"

        # ---- 游戏世界 ----
        w.draw(screen, ARENA_X, ARENA_Y, fonts)

        # ---- 顶部 HUD ----
        hud_y = 18

        # 玩家 1 HUD（左上）
        p1 = w.player1
        p1_color = TANK_DATA.get(p1.tank_name, {}).get("color", COLOR_GREEN)
        draw_panel(screen, 15, hud_y, 280, 70, alpha=200)
        draw_text(screen, "🎮 P1", 30, hud_y + 8, fonts, FONT_M, p1_color)
        hp1 = "❤️" * max(0, p1.hp) if p1.alive else "💀"
        draw_text(screen, f"{hp1}  {p1.tank_name}", 30, hud_y + 38, fonts, FONT_S, COLOR_WHITE)

        # 玩家 2 HUD（右上）
        p2 = w.player2
        p2_color = TANK_DATA.get(p2.tank_name, {}).get("color", COLOR_BLUE)
        draw_panel(screen, SCREEN_WIDTH - 295, hud_y, 280, 70, alpha=200)
        draw_text(screen, "🖱️ P2", SCREEN_WIDTH - 280, hud_y + 8, fonts, FONT_M, p2_color)
        hp2 = "❤️" * max(0, p2.hp) if p2.alive else "💀"
        draw_text(screen, f"{hp2}  {p2.tank_name}", SCREEN_WIDTH - 280, hud_y + 38, fonts, FONT_S, COLOR_WHITE)

        # 中间信息
        if w.mode == "coop":
            draw_text(screen, f"{mode_txt}   |   👾 剩余 {w.remaining_enemies()}   |   🏆 得分 {w.score}",
                      SCREEN_WIDTH // 2, hud_y + 22, fonts, FONT_M, COLOR_CYAN, center=True)
        else:
            vs_text = "⚔️  击败对方即获胜！"
            draw_text(screen, f"{mode_txt}   |   {vs_text}",
                      SCREEN_WIDTH // 2, hud_y + 22, fonts, FONT_M, COLOR_ORANGE, center=True)

        # 道具栏（左下/右下分别显示）
        self._draw_player_item(screen, p1, 60, SCREEN_HEIGHT - 35, fonts)
        self._draw_player_item(screen, p2, SCREEN_WIDTH - 220, SCREEN_HEIGHT - 35, fonts)

        # 友军伤害提示
        tip_color = COLOR_ORANGE if int(self.time * 2) % 2 == 0 else COLOR_YELLOW
        draw_text(screen, "⚠️ " + FRIENDLY_FIRE_TIP,
                  ARENA_X + ARENA_W // 2, ARENA_Y - 14,
                  fonts, FONT_XS, tip_color, center=True)

        # 底部操作提示
        draw_text(screen, "P1: WASD+空格   P2: 鼠标移动+左键   ESC返回选择",
                  SCREEN_WIDTH // 2, SCREEN_HEIGHT - 28,
                  fonts, FONT_S, COLOR_LIGHT_GRAY, center=True)

        self.back_btn.draw(screen, fonts)

        # 结算弹窗
        if self.result_popup:
            self._draw_result_popup(screen, fonts)

    def _draw_player_item(self, screen, player, x, y, fonts):
        """绘制单个玩家的道具状态（叠加版：显示当前激活集合）"""
        active = player.get_active_powerups()
        shield_on = player.shield_active
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
            name += "+🛡" if name else "🛡"
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
        result = info["result"]
        mode = info["mode"]

        # 遮罩
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        screen.blit(overlay, (0, 0))

        pw, ph = 500, 320
        px, py = (SCREEN_WIDTH - pw) // 2, (SCREEN_HEIGHT - ph) // 2
        draw_panel(screen, px, py, pw, ph, alpha=245)

        if mode == "coop":
            if result == TwoPlayerGameWorld.RESULT_WIN:
                title, col = "🏆 合作胜利！", COLOR_GOLD
                sub = f"共同击毁 {self.world.enemies_killed} 辆敌坦"
            else:
                title, col = "💀 合作失败", COLOR_RED
                sub = "有玩家被击毁，再接再厉！"
        else:
            if result == TwoPlayerGameWorld.RESULT_P1_WIN:
                title, col = "🎮 玩家 1 获胜！", COLOR_GREEN
                sub = "玩家 2 被击毁"
            elif result == TwoPlayerGameWorld.RESULT_P2_WIN:
                title, col = "🖱️ 玩家 2 获胜！", COLOR_BLUE
                sub = "玩家 1 被击毁"
            else:
                title, col = "💀 双败", COLOR_RED
                sub = "同归于尽！"

        draw_text(screen, title, px + pw // 2, py + 60, fonts, FONT_XXL, col, center=True)
        draw_text(screen, sub, px + pw // 2, py + 120, fonts, FONT_L, COLOR_LIGHT_GRAY, center=True)

        if mode == "coop":
            draw_text(screen, f"🏆 本局得分: {info['score']}",
                      px + pw // 2, py + 170, fonts, FONT_M, COLOR_YELLOW, center=True)

        draw_text(screen, "⚠️ 本局不计入解锁统计",
                  px + pw // 2, py + 210, fonts, FONT_S, COLOR_GRAY, center=True)

        # 两个按钮左右并排（避免垂直重叠导致的误触/遮挡）
        self.retry_btn.rect.centerx = SCREEN_WIDTH // 2 - 110
        self.retry_btn.rect.y = py + ph - 60
        self.menu_btn.rect.centerx = SCREEN_WIDTH // 2 + 110
        self.menu_btn.rect.y = py + ph - 60
        self.retry_btn.draw(screen, fonts)
        self.menu_btn.draw(screen, fonts)

        draw_text(screen, "快捷键: R 再来一局   M 回主菜单",
                  SCREEN_WIDTH // 2, SCREEN_HEIGHT - 28,
                  fonts, FONT_S, COLOR_YELLOW, center=True)

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

        self.select_btn = Button(SCREEN_WIDTH // 2 - 95, 524, 190, 48, "✔ 选择出战", FONT_L)
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
        save = get_save(self.game)

        draw_glow_accent(screen, SCREEN_WIDTH // 2, 55, "🚗 车 库",
                         fonts, FONT_XXL, COLOR_GOLD)
        draw_text(screen, f"已解锁 {len(save['unlocked_tanks'])}/{len(TANK_ORDER)}   |   累计战斗 {save['total_battles']} 场   |   最高通关 {save['highest_level_cleared']} 关",
                  SCREEN_WIDTH // 2, 105, fonts, FONT_S, COLOR_CYAN, center=True)

        # 坦克卡片
        for i, (btn, name) in enumerate(self.tank_buttons):
            info = TANK_DATA[name]
            unlocked = name in save.get("unlocked_tanks", [])
            is_selected = (i == self.selected_idx)

            # 卡片底（设计系统：浮起卡片 + 选中金色描边）
            btn.disabled = not unlocked
            x, y, w, h = btn.rect.x, btn.rect.y, btn.rect.w, btn.rect.h
            draw_card(screen, x, y, w, h, highlight=(is_selected and unlocked), alpha=235 if unlocked else 210)

            # 坦克图标
            icon_size = 72
            icon_x = x + (w - icon_size) // 2
            icon_y = y + 18
            draw_tank_icon(screen, icon_x, icon_y, info["color"], size=icon_size, unlocked=unlocked)

            # 坦克名称
            name_color = info["color"] if unlocked else COLOR_GRAY
            draw_text(screen, name, x + w // 2, y + 112,
                      fonts, FONT_M, name_color, center=True)

            # 定位
            draw_text(screen, info["role"], x + w // 2, y + 140,
                      fonts, FONT_XS, COLOR_CYAN if unlocked else COLOR_DARK_GRAY, center=True)

            # 属性
            attr_y = y + 165
            # 血量
            hp_hearts = "❤️" * info["hp"]
            draw_text(screen, f"血量 {hp_hearts}", x + 15, attr_y,
                      fonts, FONT_XS, COLOR_RED if unlocked else COLOR_DARK_GRAY)
            # 移速
            draw_text(screen, f"移速 {info['speed']}", x + 15, attr_y + 20,
                      fonts, FONT_XS, COLOR_GREEN if unlocked else COLOR_DARK_GRAY)
            # 初始道具
            item_text = "无"
            if info["init_item"] == "scatter":
                item_text = "🔵散射弹"
            elif info["init_item"] == "laser":
                item_text = "🔴激光炮"
            elif info["init_item"] == "bounce_scatter":
                item_text = "🟢🔵弹射+散射"
            draw_text(screen, f"道具 {item_text}", x + 15, attr_y + 40,
                      fonts, FONT_XS, COLOR_BLUE if unlocked else COLOR_DARK_GRAY)

            # 解锁条件 / 锁定遮罩
            if not unlocked:
                # 半透明遮罩
                mask = pygame.Surface((w, h), pygame.SRCALPHA)
                mask.fill((0, 0, 0, 150))
                screen.blit(mask, (x, y))
                draw_text(screen, "🔒 未解锁", x + w // 2, y + 30,
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
        draw_panel(screen, panel_x, panel_y, panel_w, panel_h, alpha=220)
        draw_text(screen, f"📋 {selected_name} - 详细属性",
                  panel_x + 25, panel_y + 15, fonts, FONT_M,
                  selected_info["color"] if selected_unlocked else COLOR_GRAY)
        desc = selected_info["description"]
        draw_text(screen, "📖 " + desc,
                  panel_x + 25, panel_y + 52, fonts, FONT_S,
                  COLOR_LIGHT_GRAY if selected_unlocked else COLOR_DARK_GRAY)
        if not selected_unlocked:
            draw_text(screen, f"🔒 解锁条件: {selected_info['unlock_desc']}",
                      panel_x + 25, panel_y + 82, fonts, FONT_S, COLOR_ORANGE)
        else:
            last = save.get("last_selected_tank", "")
            if last == selected_name:
                draw_text(screen, "✔ 当前出战坦克",
                          panel_x + panel_w - 200, panel_y + 82, fonts, FONT_S, COLOR_GREEN)
            else:
                draw_text(screen, "↓ 点击下方按钮选为出战坦克",
                          panel_x + panel_w - 230, panel_y + 82, fonts, FONT_S, COLOR_YELLOW)

        # 选择按钮（未解锁时禁用）
        self.select_btn.disabled = not selected_unlocked
        self.select_btn.draw(screen, fonts)

        self.back_btn.draw(screen, fonts)
        draw_corner_logo(screen, fonts)
