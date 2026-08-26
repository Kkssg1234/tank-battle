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
from particles import ParticleSystem
from controls import ControlState


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
        # 轻量级粒子系统（炮口火焰 / 爆炸碎片）
        self.particles = ParticleSystem()

        # 道具系统
        self.powerup_manager = PowerUpManager(self.game_map)
        # 清空粒子（避免跨局残留）
        clear_particles()
        clear_ricochet()

        # 玩家输入状态（每帧外部设置 ControlState）
        self.input_control = ControlState()

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
    def set_input(self, control):
        """外部每帧设置玩家 ControlState（统一控制接口）。"""
        self.input_control = control

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
            # 统一控制接口：apply_control 处理 转向/瞄准/移动；开火单独判定
            self.player.apply_control(self.input_control, dt, self.game_map,
                                     [self.player] + self.enemies)
            if self.input_control.fire and self.player.can_fire():
                self._player_fire()

        self.player.update(dt)

        # ---- 道具系统（刷新/拾取/计时）----
        self.powerup_manager.update(dt, [self.player], self.game_map)

        # ---- 敌人 AI（与人类共用 apply_control，操作逻辑一致）----
        all_tanks = [self.player] + self.enemies
        for enemy in self.enemies:
            if not enemy.alive:
                continue
            ctrl = enemy.decide_control(dt, self.player, self.game_map, all_tanks)
            enemy.apply_control(ctrl, dt, self.game_map, all_tanks)
            if ctrl.fire and enemy.can_fire():
                # 第1关敌人子弹降速（仅第1关），其余关卡与玩家子弹保持原速
                enemy_speed = (BULLET_SPEED * LEVEL1_ENEMY_BULLET_SPEED_MULT
                               if self.level == 1 else BULLET_SPEED) * ENEMY_BULLET_SPEED_MULT
                self.bullets.extend(enemy.shoot(bullet_speed=enemy_speed))
                self._emit_muzzle(enemy)
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
                self.particles.spawn_explosion(e.x, e.y, None, big=True)
        self.enemies = remaining

        # ---- 玩家死亡 ----
        if not self.player.alive:
            self.explosions.append(Explosion(self.player.x, self.player.y, big=True, on_big=self.shake.add))
            self.particles.spawn_explosion(self.player.x, self.player.y, None, big=True)
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
        self.particles.update(dt)

    def _player_fire(self):
        """根据当前生效道具发射子弹（逻辑已集中到 Tank.shoot()）"""
        new_bullets = self.player.shoot()
        if new_bullets:
            self.bullets.extend(new_bullets)
            self._emit_muzzle(self.player)

    def _emit_muzzle(self, tank):
        """在坦克炮口生成炮口火焰粒子（朝连续炮塔方向）。"""
        vx, vy = tank.get_turret_vector()
        half = TANK_SIZE // 2
        mx = tank.x + vx * (half + 6)
        my = tank.y + vy * (half + 6)
        self.particles.spawn_muzzle_flash(mx, my, tank.direction)

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
        # 轻量级粒子（炮口火焰 / 爆炸碎片）
        self.particles.draw(screen, arena_x, arena_y)
        # 跳弹环形闪光反馈
        draw_ricochet(screen, arena_x, arena_y)

        # 爆炸
        for e in self.explosions:
            e.draw(screen, arena_x, arena_y)

        # 竞技场暗角（vignette）：最后 blit 一次，营造纵深聚焦
        draw_vignette(screen, arena_x, arena_y, ARENA_W, ARENA_H)

class CarnivalGameWorld(GameWorld):
    """道具狂欢模式：无尽生存 + 道具刷新量/频率大幅提升 + 实时计分。
    敌人随击杀数递增难度、持续生成（无通关，玩家阵亡即结束）。"""

    def __init__(self, tank_name, fonts):
        # 用第 1 关地图作基底（开阔），敌人难度随击杀递增
        super().__init__(level=1, tank_name=tank_name, fonts=fonts)
        # 狂欢：道具系统切换为高频多量
        self.powerup_manager = PowerUpManager(self.game_map, mode="carnival")
        # 无尽：敌人总数视为无限，持续生成（不会触发通关）
        self.total_enemies = 10 ** 9

    def _spawn_level_for_kills(self):
        # 难度随击杀数缓增（1..12）
        return min(12, 1 + self.enemies_killed // 6)

    def _try_spawn_enemy(self):
        if len(self.enemies) >= 5:
            return False
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
                lvl = self._spawn_level_for_kills()
                enemy = EnemyTank(x, y, lvl)
                self.enemies.append(enemy)
                self.enemies_spawned += 1
                self._enemy_spawn_idx = (self._enemy_spawn_idx + i + 1) % 3
                return True
        return False

    def update(self, dt):
        super().update(dt)
        # 无尽补充：保持场上始终有敌人（极端情况同帧清空时立即补）
        if self.result == GameWorld.RESULT_NONE and len(self.enemies) == 0:
            self._try_spawn_enemy()


class TwoPlayerGameWorld:
    """双人 vs AI（无尽）模式：两名人类玩家合作对抗持续生成的 AI 坦克。
    - 双方独立实时积分（按击杀归属）；
    - 支持自定义命名（p1_name / p2_name）；
    - 排行榜由各界面在结束后写入存档；
    - AI 与人类共用 apply_control，操作逻辑一致。"""

    RESULT_NONE = "none"
    RESULT_LOSE = "lose"   # 双方阵亡即结束（无尽模式无胜利）

    def __init__(self, p1_name, p2_name, tank1_name, tank2_name, fonts):
        self.p1_name = p1_name
        self.p2_name = p2_name
        self.tank1_name = tank1_name
        self.tank2_name = tank2_name
        self.fonts = fonts
        self.result = TwoPlayerGameWorld.RESULT_NONE
        self.time = 0.0
        self.kills = 0   # 累计 AI 击杀数

        # 地图：用第 6 关适中地图
        self.game_map = MapGenerator().generate(get_level_config(6), fonts)
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
        self.particles = ParticleSystem()
        # 双人 vsAI 也享用较多道具，节奏更热闹
        self.powerup_manager = PowerUpManager(self.game_map, mode="carnival")
        clear_particles()
        clear_ricochet()

        # 玩家独立实时积分
        self.scores = {p1_name: 0, p2_name: 0}

        # 输入（外部每帧设置 ControlState）
        self.p1_control = ControlState()
        self.p2_control = ControlState()

        self.shake = ScreenShake()

        # 敌人出生点
        self.enemy_spawn_points = [
            ((2 + 1) * TILE_SIZE + TILE_SIZE // 2, 2 * TILE_SIZE + TILE_SIZE // 2),
            ((TILE_COLS // 2) * TILE_SIZE + TILE_SIZE // 2, 2 * TILE_SIZE + TILE_SIZE // 2),
            ((TILE_COLS - 4) * TILE_SIZE + TILE_SIZE // 2, 2 * TILE_SIZE + TILE_SIZE // 2),
        ]
        self._enemy_spawn_idx = 0
        self._spawn_initial_enemies()

    # ========= 输入接口 =========
    def set_input(self, p1_control, p2_control):
        self.p1_control = p1_control
        self.p2_control = p2_control

    # ========= 敌人生成（无尽） =========
    def _spawn_initial_enemies(self):
        for _ in range(2):
            self._try_spawn_enemy()

    def _try_spawn_enemy(self):
        if len(self.enemies) >= VS_AI_MAX_ENEMIES:
            return False
        lvl = min(12, 1 + self.enemies_killed // 8)   # 难度随击杀增加
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
                enemy = EnemyTank(x, y, lvl)
                self.enemies.append(enemy)
                self.enemies_spawned += 1
                self._enemy_spawn_idx = (self._enemy_spawn_idx + i + 1) % 3
                return True
        return False

    # ========= 主更新 =========
    def update(self, dt):
        self.shake.update(dt)
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
            self.player1.apply_control(self.p1_control, dt, self.game_map, all_tanks)
            if self.p1_control.fire and self.player1.can_fire():
                self.bullets.extend(self.player1.shoot())
                self._emit_muzzle(self.player1)
        self.player1.update(dt)

        # ---- 玩家 2 ----
        if self.player2.alive:
            self.player2.apply_control(self.p2_control, dt, self.game_map, all_tanks)
            if self.p2_control.fire and self.player2.can_fire():
                self.bullets.extend(self.player2.shoot())
                self._emit_muzzle(self.player2)
        self.player2.update(dt)

        # ---- 道具系统（对两名玩家都生效）----
        self.powerup_manager.update(dt, self.players, self.game_map)

        # ---- 敌人 AI（与人类共用 apply_control，操作逻辑一致）----
        for enemy in self.enemies:
            if not enemy.alive:
                continue
            target = self._nearest_alive_player(enemy)
            if target is None:
                continue
            ctrl = enemy.decide_control(dt, target, self.game_map, all_tanks)
            enemy.apply_control(ctrl, dt, self.game_map, all_tanks)
            if ctrl.fire and enemy.can_fire():
                enemy_speed = BULLET_SPEED * ENEMY_BULLET_SPEED_MULT
                self.bullets.extend(enemy.shoot(bullet_speed=enemy_speed))
                self._emit_muzzle(enemy)
            enemy.update(dt)

        # ---- 补充敌人（无尽）----
        self.spawn_cooldown -= dt
        if self.spawn_cooldown <= 0:
            self.spawn_cooldown = VS_AI_SPAWN_COOLDOWN
            self._try_spawn_enemy()

        # ---- 子弹更新 ----
        alive_bullets = []
        for b in self.bullets:
            b.update(dt, self.game_map, None)
            if not b.alive:
                continue
            if b.bullet_type == Bullet.LASER and b.beam_mode:
                b._resolve_beam(self.game_map, all_tanks)
                for t in b.beam_hits:
                    t.last_hit_by = b.owner   # 激光击杀也归属
                    self.explosions.append(Explosion(t.x, t.y, big=False))
                b.beam_hits.clear()
            else:
                self._check_bullet_vs_tanks(b)
            if b.alive:
                alive_bullets.append(b)
        self.bullets = alive_bullets

        # ---- 清理死亡敌人并计分 ----
        remaining = []
        for e in self.enemies:
            if e.alive:
                remaining.append(e)
            else:
                self.enemies_killed += 1
                self.kills += 1
                credit = e.last_hit_by
                if credit in self.players:
                    name = self.p1_name if credit is self.player1 else self.p2_name
                    self.scores[name] += 100
                self.explosions.append(Explosion(e.x, e.y, big=True, on_big=self.shake.add))
                self.particles.spawn_explosion(e.x, e.y, None, big=True)
        self.enemies = remaining

        # ---- 胜负判定 ----
        self._check_game_over()

        # ---- 爆炸更新 ----
        for e in self.explosions:
            e.update(dt)
        self.explosions = [e for e in self.explosions if e.alive]
        update_particles(dt)
        update_ricochet(dt)
        self.particles.update(dt)

    def _nearest_alive_player(self, enemy):
        best = None
        best_d = float('inf')
        for p in self.players:
            if p.alive:
                d = math.hypot(p.x - enemy.x, p.y - enemy.y)
                if d < best_d:
                    best_d = d
                    best = p
        return best

    def _emit_muzzle(self, tank):
        """在坦克炮口生成炮口火焰粒子（朝连续炮塔方向）。"""
        vx, vy = tank.get_turret_vector()
        half = TANK_SIZE // 2
        mx = tank.x + vx * (half + 6)
        my = tank.y + vy * (half + 6)
        self.particles.spawn_muzzle_flash(mx, my, tank.direction)

    def _check_bullet_vs_tanks(self, bullet):
        """子弹与所有坦克碰撞：players + enemies"""
        for p in self.players:
            if not p.alive or id(p) in bullet.hit_tanks:
                continue
            if bullet.get_rect().colliderect(p.get_rect()):
                self._apply_bullet_to_tank(bullet, p)
                if not bullet.alive:
                    return
        for e in self.enemies:
            if not e.alive or id(e) in bullet.hit_tanks:
                continue
            if bullet.get_rect().colliderect(e.get_rect()):
                self._apply_bullet_to_tank(bullet, e)
                if not bullet.alive:
                    return

    def _apply_bullet_to_tank(self, bullet, tank):
        """处理子弹击中坦克的伤害逻辑（含友军伤害 + 跳弹机制 + 击杀归属）"""
        if bullet.try_ricochet(tank):
            return
        if bullet.ricocheted:
            damaged = tank.take_damage(bullet.damage)
            bullet.alive = False
            if tank.alive and damaged:
                self.explosions.append(Explosion(tank.x, tank.y, big=False))
            return

        hit = False
        if bullet.owner_type == "enemy" and tank.owner == "player":
            hit = True
        elif bullet.owner_type == "player" and tank.owner == "enemy":
            hit = True
            tank.last_hit_by = bullet.owner   # 记录击杀归属（双人计分）
        elif bullet.owner_type == "player" and tank.owner == "player":
            if bullet.owner is tank:
                if bullet.bullet_type == Bullet.BOUNCE:
                    hit = True
                else:
                    return
            else:
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
        if not self.player1.alive and not self.player2.alive:
            dead = self.player1 if not self.player1.alive else self.player2
            self.particles.spawn_explosion(dead.x, dead.y, None, big=True)
            self.result = TwoPlayerGameWorld.RESULT_LOSE

    def remaining_enemies(self):
        return 0

    # ========= 绘制 =========
    def draw(self, screen, arena_x, arena_y, fonts):
        ox, oy = self.shake.offset()
        arena_x += int(ox)
        arena_y += int(oy)
        self.game_map.draw(screen, arena_x, arena_y)
        self.powerup_manager.draw(screen, self.time)
        pygame.draw.rect(screen, ARENA_BORDER,
                         (arena_x, arena_y, ARENA_W, ARENA_H), width=2, border_radius=4)
        for p in self.players:
            p.draw(screen, arena_x, arena_y)
        for e in self.enemies:
            e.draw(screen, arena_x, arena_y)
        for b in self.bullets:
            b.draw(screen, arena_x, arena_y)
        draw_particles(screen, arena_x, arena_y)
        self.particles.draw(screen, arena_x, arena_y)
        draw_ricochet(screen, arena_x, arena_y)
        for e in self.explosions:
            e.draw(screen, arena_x, arena_y)
        draw_vignette(screen, arena_x, arena_y, ARENA_W, ARENA_H)
