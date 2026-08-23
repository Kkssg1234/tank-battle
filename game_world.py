"""
GameWorld 游戏世界：整合地图、玩家、敌人、子弹、特效、胜负判定
"""
import math
import pygame
from constants import *
from entities import PlayerTank, EnemyTank
from bullets import (Bullet, update_particles, draw_particles, clear_particles,
                   update_ricochet, draw_ricochet, clear_ricochet)
from map_generator import MapGenerator
from powerup import PowerUpManager
from level_config import get_level_config, LEVEL_ENEMY_COUNTS
from vfx import ScreenShake, draw_glow, draw_explosion, draw_vignette


class Explosion:
    """爆炸特效（技术美术升级版）
    - 辉光底光（复用 vfx 缓存 glow，零每帧分配）
    - 三层火球（白芯-黄中-红外）
    - 冲击波环（扩大淡出的描边圆环）
    - 大爆炸(big=True)在创建时触发屏幕震动（通过 on_big 回调上报给 GameWorld）"""
    def __init__(self, x, y, big=False, on_big=None):
        self.x, self.y = x, y
        self.time = 0.0
        self.duration = EXPLOSION_DURATION * (1.5 if big else 1.0)
        self.big = big
        self.alive = True
        self.on_big = on_big
        if big and callable(on_big):
            on_big(4.0)  # 触发 ≤4px 屏幕震动

    def update(self, dt):
        self.time += dt
        if self.time >= self.duration:
            self.alive = False

    def draw(self, screen, arena_x, arena_y):
        t = self.time / self.duration
        alpha = int(255 * (1 - t))
        cx = int(arena_x + self.x)
        cy = int(arena_y + self.y)
        # 技术美术升级版：预烘焙火球 + 冲击波环，零每帧 Surface 分配
        draw_explosion(screen, cx, cy, t, self.big, alpha=alpha)


class GameWorld:
    """单关游戏世界"""

    # 结果状态
    RESULT_NONE = "none"
    RESULT_WIN = "win"
    RESULT_LOSE = "lose"

    def __init__(self, level, tank_name, fonts):
        self.level = level
        self.tank_name = tank_name
        self.fonts = fonts
        self.result = GameWorld.RESULT_NONE
        self.score = 0
        self.total_enemies = get_level_config(level)["enemy_count"]
        self.enemies_killed = 0
        self.enemies_spawned = 0
        self.spawn_cooldown = 1.2  # 敌人出生间隔
        self.time = 0.0

        # 地图（由 MapGenerator 依据关卡配置生成纯障碍物地图）
        self.game_map = MapGenerator().generate(get_level_config(level), fonts=fonts)

        # 玩家出生点（左下）
        px = (2 + 1) * TILE_SIZE + TILE_SIZE // 2
        py = (TILE_ROWS - 3) * TILE_SIZE + TILE_SIZE // 2
        self.player = PlayerTank(px, py, tank_name)

        # 实体容器
        self.enemies = []
        self.bullets = []
        self.explosions = []

        # 道具系统
        self.powerup_manager = PowerUpManager(self.game_map)
        # 清空粒子（避免跨局残留）
        clear_particles()
        clear_ricochet()

        # 玩家输入状态（每帧外部设置）
        self.input_dx = 0
        self.input_dy = 0
        self.input_fire = False

        # 屏幕震动控制器（大爆炸时触发）
        self.shake = ScreenShake()

        # 敌人生成点列表
        self.enemy_spawn_points = [
            ((2 + 1) * TILE_SIZE + TILE_SIZE // 2,
             2 * TILE_SIZE + TILE_SIZE // 2),
            ((TILE_COLS // 2) * TILE_SIZE + TILE_SIZE // 2,
             2 * TILE_SIZE + TILE_SIZE // 2),
            ((TILE_COLS - 4) * TILE_SIZE + TILE_SIZE // 2,
             2 * TILE_SIZE + TILE_SIZE // 2),
        ]
        self._enemy_spawn_idx = 0

        # 立即生成前1-2个敌人
        self._spawn_initial_enemies()

    # ========= 敌人生成 =========
    def _spawn_initial_enemies(self):
        # 第一关先生成2个，让玩家有时间反应
        first = min(2, self.total_enemies)
        for _ in range(first):
            self._try_spawn_enemy()

    def _try_spawn_enemy(self):
        if self.enemies_spawned >= self.total_enemies:
            return False
        if len(self.enemies) >= 4:  # 同时在场最多4个
            return False
        # 检查生成点是否被占
        for i in range(3):
            x, y = self.enemy_spawn_points[(self._enemy_spawn_idx + i) % 3]
            occupied = False
            for t in [self.player] + self.enemies:
                if not t.alive:
                    continue
                if math.hypot(t.x - x, t.y - y) < TILE_SIZE * 1.1:
                    occupied = True
                    break
            if not occupied:
                enemy = EnemyTank(x, y, self.level)
                self.enemies.append(enemy)
                self.enemies_spawned += 1
                self._enemy_spawn_idx = (self._enemy_spawn_idx + i + 1) % 3
                return True
        return False

    # ========= 输入接口 =========
    def set_input(self, dx, dy, fire):
        self.input_dx = int(dx)
        self.input_dy = int(dy)
        self.input_fire = bool(fire)

    # ========= 主更新 =========
    def update(self, dt):
        self.shake.update(dt)  # 屏幕震动始终推进
        if self.result != GameWorld.RESULT_NONE:
            # 结束后只更新爆炸
            for e in self.explosions:
                e.update(dt)
            self.explosions = [e for e in self.explosions if e.alive]
            update_particles(dt)
            return

        self.time += dt

        # ---- 玩家 ----
        if self.player.alive:
            # 设置朝向
            if self.input_dx != 0 or self.input_dy != 0:
                self.player.set_direction_by_keydir(self.input_dx, self.input_dy)
            # 移动
            self.player.try_move(self.input_dx, self.input_dy,
                                 self.game_map, [self.player] + self.enemies)
            # 射击
            if self.input_fire and self.player.can_fire():
                self._player_fire()

        self.player.update(dt)

        # ---- 道具系统（刷新/拾取/计时）----
        self.powerup_manager.update(dt, [self.player], self.game_map)

        # ---- 敌人 AI ----
        all_tanks = [self.player] + self.enemies
        for enemy in self.enemies:
            if not enemy.alive:
                continue
            action = enemy.ai_step(dt, self.player, self.game_map, all_tanks)
            if action and action[0] == "fire" and enemy.can_fire():
                # 第1关敌人子弹降速（仅第1关），其余关卡与玩家子弹保持原速
                enemy_speed = (BULLET_SPEED * LEVEL1_ENEMY_BULLET_SPEED_MULT
                               if self.level == 1 else BULLET_SPEED) * ENEMY_BULLET_SPEED_MULT
                self.bullets.extend(enemy.shoot(bullet_speed=enemy_speed))
            enemy.update(dt)

        # ---- 生成新敌人 ----
        self.spawn_cooldown -= dt
        if self.spawn_cooldown <= 0:
            self.spawn_cooldown = 2.2 + (self.total_enemies - self.enemies_spawned) * 0.05
            self._try_spawn_enemy()

        # ---- 子弹更新 ----
        all_tanks = [self.player] + self.enemies
        alive_bullets = []
        for b in self.bullets:
            # update() 内部处理移动、墙壁碰撞、边界、坦克碰撞（规范 5 接口）
            # 返回被击中的坦克（未命中返回 None），供外层生成命中特效
            hit = b.update(dt, self.game_map, all_tanks)
            if b.bullet_type == Bullet.LASER and b.beam_mode:
                # 激光：即时光束——发射瞬间贯穿全图，一次性命中沿途坦克
                b._resolve_beam(self.game_map, all_tanks)
                for t in b.beam_hits:
                    self.explosions.append(Explosion(t.x, t.y, big=False))
                b.beam_hits.clear()
            elif hit is not None:
                self.explosions.append(Explosion(hit.x, hit.y, big=False))
            if b.alive:
                alive_bullets.append(b)
        self.bullets = alive_bullets

        # ---- 清理死亡敌人并记分 ----
        remaining = []
        for e in self.enemies:
            if e.alive:
                remaining.append(e)
            else:
                # 记分
                self.enemies_killed += 1
                base_score = 100 + self.level * 20
                self.score += base_score
                self.explosions.append(Explosion(e.x, e.y, big=True, on_big=self.shake.add))
        self.enemies = remaining

        # ---- 玩家死亡 ----
        if not self.player.alive:
            self.explosions.append(Explosion(self.player.x, self.player.y, big=True, on_big=self.shake.add))
            self.result = GameWorld.RESULT_LOSE

        # ---- 胜利判定 ----
        if (self.enemies_killed >= self.total_enemies and
                len(self.enemies) == 0):
            self.result = GameWorld.RESULT_WIN

        # ---- 爆炸更新 ----
        for e in self.explosions:
            e.update(dt)
        self.explosions = [e for e in self.explosions if e.alive]
        update_particles(dt)
        update_ricochet(dt)

    def _player_fire(self):
        """根据当前生效道具发射子弹（逻辑已集中到 Tank.shoot()）"""
        new_bullets = self.player.shoot()
        if new_bullets:
            self.bullets.extend(new_bullets)

    # ========= 统计 =========
    def remaining_enemies(self):
        return (self.total_enemies - self.enemies_killed)

    # ========= 绘制 =========
    def draw(self, screen, arena_x, arena_y, fonts):
        # 屏幕震动：整体偏移竞技场坐标（仅影响本帧绘制，不改逻辑坐标）
        ox, oy = self.shake.offset()
        arena_x += int(ox)
        arena_y += int(oy)
        # 地图
        self.game_map.draw(screen, arena_x, arena_y)

        # 道具箱（绘制在地面之上、坦克之下）
        self.powerup_manager.draw(screen, self.time)

        # 外框（白框，呼应黑底白字主题）
        pygame.draw.rect(screen, ARENA_BORDER,
                         (arena_x, arena_y, ARENA_W, ARENA_H), width=2, border_radius=4)

        # 坦克
        self.player.draw(screen, arena_x, arena_y)
        for e in self.enemies:
            e.draw(screen, arena_x, arena_y)

        # 子弹
        for b in self.bullets:
            b.draw(screen, arena_x, arena_y)

        # 粒子（弹射反弹白点等）
        draw_particles(screen, arena_x, arena_y)
        # 跳弹环形闪光反馈
        draw_ricochet(screen, arena_x, arena_y)

        # 爆炸
        for e in self.explosions:
            e.draw(screen, arena_x, arena_y)

        # 竞技场暗角（vignette）：最后 blit 一次，营造纵深聚焦
        draw_vignette(screen, arena_x, arena_y, ARENA_W, ARENA_H)


class TwoPlayerGameWorld:
    """
    双人游戏世界：支持合作(coop)与对战(vs)两种子模式
    """
    RESULT_NONE = "none"
    RESULT_WIN = "win"        # 合作：全歼敌人
    RESULT_LOSE = "lose"      # 合作：任一玩家死亡
    RESULT_P1_WIN = "p1_win"  # 对战：玩家 2 死亡
    RESULT_P2_WIN = "p2_win"  # 对战：玩家 1 死亡

    def __init__(self, mode, level, tank1_name, tank2_name, fonts):
        """
        mode: "coop" 或 "vs"
        level: 合作模式使用（对战模式忽略，传 1 即可）
        tank1_name, tank2_name: 两个玩家选择的坦克名称
        """
        self.mode = mode
        self.level = level
        self.fonts = fonts
        self.result = TwoPlayerGameWorld.RESULT_NONE
        self.score = 0          # 合作模式共用得分；对战模式显示击杀数
        self.time = 0.0

        # 地图（合作模式用关卡地图，对战模式用第 6 关适中地图）
        if mode == "coop":
            self.game_map = MapGenerator().generate(get_level_config(level), fonts)
            self.total_enemies = LEVEL_ENEMY_COUNTS.get(level, 3) + COOP_EXTRA_ENEMIES
        else:
            # 对战模式：用第 6 关的随机地图生成器（障碍适中）
            self.game_map = MapGenerator().generate(get_level_config(6), fonts)
            self.total_enemies = 0

        self.enemies_killed = 0
        self.enemies_spawned = 0
        self.spawn_cooldown = 1.2

        # 玩家 1 出生左下
        p1x = (2 + 1) * TILE_SIZE + TILE_SIZE // 2
        p1y = (TILE_ROWS - 3) * TILE_SIZE + TILE_SIZE // 2
        self.player1 = PlayerTank(p1x, p1y, tank1_name)

        # 玩家 2 出生右下
        self.player2 = PlayerTank(P2_SPAWN_X, P2_SPAWN_Y, tank2_name)

        self.players = [self.player1, self.player2]

        self.enemies = []
        self.bullets = []
        self.explosions = []

        # 道具系统（对战模式也启用道具箱，增加变数）
        self.powerup_manager = PowerUpManager(self.game_map)
        clear_particles()
        clear_ricochet()

        # 输入状态（外部每帧设置）
        self.p1_input = {"dx": 0, "dy": 0, "fire": False}
        self.p2_input = {"dx": 0, "dy": 0, "fire": False}

        # 屏幕震动控制器（大爆炸时触发）
        self.shake = ScreenShake()

        # 敌人生成点（合作模式）
        if mode == "coop":
            self.enemy_spawn_points = [
                ((2 + 1) * TILE_SIZE + TILE_SIZE // 2, 2 * TILE_SIZE + TILE_SIZE // 2),
                ((TILE_COLS // 2) * TILE_SIZE + TILE_SIZE // 2, 2 * TILE_SIZE + TILE_SIZE // 2),
                ((TILE_COLS - 4) * TILE_SIZE + TILE_SIZE // 2, 2 * TILE_SIZE + TILE_SIZE // 2),
            ]
            self._enemy_spawn_idx = 0
            self._spawn_initial_enemies()

    # ========= 输入接口 =========
    def set_input(self, p1_dx, p1_dy, p1_fire, p2_dx, p2_dy, p2_fire):
        self.p1_input = {"dx": p1_dx, "dy": p1_dy, "fire": p1_fire}
        self.p2_input = {"dx": p2_dx, "dy": p2_dy, "fire": p2_fire}

    # ========= 敌人生成（仅合作模式） =========
    def _spawn_initial_enemies(self):
        first = min(2, self.total_enemies)
        for _ in range(first):
            self._try_spawn_enemy()

    def _try_spawn_enemy(self):
        if self.mode != "coop":
            return False
        if self.enemies_spawned >= self.total_enemies:
            return False
        if len(self.enemies) >= 5:  # 合作模式同时在场最多 5 个
            return False
        for i in range(3):
            x, y = self.enemy_spawn_points[(self._enemy_spawn_idx + i) % 3]
            occupied = False
            for t in self.players + self.enemies:
                if not t.alive:
                    continue
                if math.hypot(t.x - x, t.y - y) < TILE_SIZE * 1.1:
                    occupied = True
                    break
            if not occupied:
                enemy = EnemyTank(x, y, self.level)
                self.enemies.append(enemy)
                self.enemies_spawned += 1
                self._enemy_spawn_idx = (self._enemy_spawn_idx + i + 1) % 3
                return True
        return False

    # ========= 主更新 =========
    def update(self, dt):
        self.shake.update(dt)  # 屏幕震动始终推进
        if self.result != TwoPlayerGameWorld.RESULT_NONE:
            for e in self.explosions:
                e.update(dt)
            self.explosions = [e for e in self.explosions if e.alive]
            update_particles(dt)
            return

        self.time += dt

        all_tanks = self.players + self.enemies

        # ---- 玩家 1 ----
        if self.player1.alive:
            p1 = self.p1_input
            if p1["dx"] != 0 or p1["dy"] != 0:
                self.player1.set_direction_by_keydir(p1["dx"], p1["dy"])
            self.player1.try_move(p1["dx"], p1["dy"], self.game_map, all_tanks)
            if p1["fire"] and self.player1.can_fire():
                self.bullets.extend(self.player1.shoot())
        self.player1.update(dt)

        # ---- 玩家 2 ----
        if self.player2.alive:
            p2 = self.p2_input
            # 鼠标控制：p2_input 中 dx,dy 已经是归一化向量（Screen层计算）
            if abs(p2["dx"]) > 0.01 or abs(p2["dy"]) > 0.01:
                # 设置朝向（4方向）
                target_x = self.player2.x + p2["dx"] * 100
                target_y = self.player2.y + p2["dy"] * 100
                self.player2.set_direction_toward(target_x, target_y)
                self.player2.try_move(p2["dx"], p2["dy"], self.game_map, all_tanks)
            if p2["fire"] and self.player2.can_fire():
                self.bullets.extend(self.player2.shoot())
        self.player2.update(dt)

        # ---- 道具系统（对两个玩家都生效）----
        self.powerup_manager.update(dt, self.players, self.game_map)

        # ---- 敌人 AI（仅合作模式）----
        if self.mode == "coop":
            for enemy in self.enemies:
                if not enemy.alive:
                    continue
                # 敌人追踪最近的存活玩家
                target = self._nearest_alive_player(enemy)
                if target is None:
                    continue
                action = enemy.ai_step(dt, target, self.game_map, all_tanks)
                if action and action[0] == "fire" and enemy.can_fire():
                    enemy_speed = (BULLET_SPEED * LEVEL1_ENEMY_BULLET_SPEED_MULT
                                   if self.level == 1 else BULLET_SPEED)
                    self.bullets.extend(enemy.shoot(bullet_speed=enemy_speed))
                enemy.update(dt)

            # 生成新敌人
            self.spawn_cooldown -= dt
            if self.spawn_cooldown <= 0:
                self.spawn_cooldown = 2.0 + (self.total_enemies - self.enemies_spawned) * 0.05
                self._try_spawn_enemy()

        # ---- 子弹更新（内置碰撞关闭，改用自定义 _check_bullet_vs_tanks）----
        alive_bullets = []
        for b in self.bullets:
            b.update(dt, self.game_map, None)
            if not b.alive:
                continue
            if b.bullet_type == Bullet.LASER and b.beam_mode:
                # 激光：即时光束——一次性命中沿途坦克，不参与逐帧 _check_bullet_vs_tanks
                b._resolve_beam(self.game_map, all_tanks)
                for t in b.beam_hits:
                    self.explosions.append(Explosion(t.x, t.y, big=False))
                b.beam_hits.clear()
            else:
                self._check_bullet_vs_tanks(b)
            if b.alive:
                alive_bullets.append(b)
        self.bullets = alive_bullets

        # ---- 清理死亡敌人并记分（合作模式）----
        if self.mode == "coop":
            remaining = []
            for e in self.enemies:
                if e.alive:
                    remaining.append(e)
                else:
                    self.enemies_killed += 1
                    self.score += 100 + self.level * 20
                    self.explosions.append(Explosion(e.x, e.y, big=True, on_big=self.shake.add))
            self.enemies = remaining

        # ---- 胜负判定 ----
        self._check_game_over()

        # ---- 爆炸更新 ----
        for e in self.explosions:
            e.update(dt)
        self.explosions = [e for e in self.explosions if e.alive]
        update_particles(dt)
        update_ricochet(dt)

    def _nearest_alive_player(self, enemy):
        """返回距离敌人最近的存活玩家"""
        best = None
        best_d = float('inf')
        for p in self.players:
            if p.alive:
                d = math.hypot(p.x - enemy.x, p.y - enemy.y)
                if d < best_d:
                    best_d = d
                    best = p
        return best

    def _check_bullet_vs_tanks(self, bullet):
        """子弹与所有坦克碰撞：players + enemies"""
        # vs 所有玩家（含友军伤害）
        for p in self.players:
            if not p.alive or id(p) in bullet.hit_tanks:
                continue
            if bullet.get_rect().colliderect(p.get_rect()):
                self._apply_bullet_to_tank(bullet, p)
                if not bullet.alive:
                    return
        # vs 敌人（仅合作模式）
        if self.mode == "coop":
            for e in self.enemies:
                if not e.alive or id(e) in bullet.hit_tanks:
                    continue
                if bullet.get_rect().colliderect(e.get_rect()):
                    self._apply_bullet_to_tank(bullet, e)
                    if not bullet.alive:
                        return

    def _apply_bullet_to_tank(self, bullet, tank):
        """处理子弹击中坦克的伤害逻辑（含友军伤害 + 跳弹机制）"""
        # 跳弹：先尝试弹开（不造成伤害，随机偏转，保留杀伤力）
        if bullet.try_ricochet(tank):
            return
        # 跳弹后的子弹（ricocheted=True, owner=None）：不区分敌我，命中任意坦克即造成伤害
        # （含发射者自身 / 友军 / 敌人），满足"保持杀伤力、不区分敌我"需求
        if bullet.ricocheted:
            damaged = tank.take_damage(bullet.damage)
            bullet.alive = False
            if tank.alive and damaged:
                self.explosions.append(Explosion(tank.x, tank.y, big=False))
            return

        # 判定是否应造成伤害
        hit = False

        # 敌人子弹打玩家
        if bullet.owner_type == "enemy" and tank.owner == "player":
            hit = True
        # 玩家子弹打敌人（合作模式）
        elif bullet.owner_type == "player" and tank.owner == "enemy":
            hit = True
        # 玩家子弹打玩家（友军伤害 / 对战模式 / 自伤）
        elif bullet.owner_type == "player" and tank.owner == "player":
            if bullet.owner is tank:
                # 自己打自己：只有弹射弹反弹后才造成伤害
                if bullet.bullet_type == Bullet.BOUNCE:
                    hit = True
                else:
                    return
            else:
                # 打中另一个玩家：对战模式必然伤害；合作模式也伤害（友军伤害开启）
                hit = True

        if not hit:
            return

        damaged = tank.take_damage(bullet.damage)

        if bullet.bullet_type == Bullet.LASER:
            bullet.hit_tanks.add(id(tank))
            if damaged:
                self.explosions.append(Explosion(tank.x, tank.y, big=False))
            bullet.penetration -= 1
            if bullet.penetration <= 0:
                bullet.alive = False
            return

        bullet.alive = False
        if tank.alive and damaged:
            self.explosions.append(Explosion(tank.x, tank.y, big=False))

    def _check_game_over(self):
        """胜负判定"""
        if self.mode == "coop":
            # 任一玩家死亡 = 失败
            if not self.player1.alive or not self.player2.alive:
                dead = self.player1 if not self.player1.alive else self.player2
                self.explosions.append(Explosion(dead.x, dead.y, big=True, on_big=self.shake.add))
                self.result = TwoPlayerGameWorld.RESULT_LOSE
                return
            # 全歼敌人 = 胜利
            if self.enemies_killed >= self.total_enemies and len(self.enemies) == 0:
                self.result = TwoPlayerGameWorld.RESULT_WIN
        else:
            # 对战模式
            if not self.player1.alive and self.player2.alive:
                self.result = TwoPlayerGameWorld.RESULT_P2_WIN
            elif not self.player2.alive and self.player1.alive:
                self.result = TwoPlayerGameWorld.RESULT_P1_WIN
            # 同时死亡（极罕见）：判平局，视为 RESULT_LOSE 或重赛，这里判 RESULT_LOSE
            elif not self.player1.alive and not self.player2.alive:
                self.result = TwoPlayerGameWorld.RESULT_LOSE

    # ========= 统计 =========
    def remaining_enemies(self):
        if self.mode != "coop":
            return 0
        return self.total_enemies - self.enemies_killed

    # ========= 绘制 =========
    def draw(self, screen, arena_x, arena_y, fonts):
        # 屏幕震动：整体偏移竞技场坐标（仅影响本帧绘制，不改逻辑坐标）
        ox, oy = self.shake.offset()
        arena_x += int(ox)
        arena_y += int(oy)
        # 地图
        self.game_map.draw(screen, arena_x, arena_y)
        # 道具箱
        self.powerup_manager.draw(screen, self.time)
        # 外框
        pygame.draw.rect(screen, ARENA_BORDER,
                         (arena_x, arena_y, ARENA_W, ARENA_H), width=2, border_radius=4)
        # 坦克
        for p in self.players:
            p.draw(screen, arena_x, arena_y)
        for e in self.enemies:
            e.draw(screen, arena_x, arena_y)
        # 子弹
        for b in self.bullets:
            b.draw(screen, arena_x, arena_y)
        # 粒子（弹射反弹白点等）
        draw_particles(screen, arena_x, arena_y)
        # 跳弹环形闪光反馈
        draw_ricochet(screen, arena_x, arena_y)
        # 爆炸
        for e in self.explosions:
            e.draw(screen, arena_x, arena_y)
        # 竞技场暗角（vignette）：最后 blit 一次，营造纵深聚焦
        draw_vignette(screen, arena_x, arena_y, ARENA_W, ARENA_H)
