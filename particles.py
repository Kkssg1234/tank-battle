"""
轻量级粒子系统（Round 5）
- Particle: 单个粒子（位置/速度/存活/颜色/半径）
- ParticleSystem: 批量生成、更新、绘制
  · spawn            通用随机方向生成
  · spawn_explosion  爆炸（中心白/黄 → 边缘橙/红渐变）
  · spawn_muzzle_flash 炮口火焰（朝射击方向）
  · spawn_hover_spark   UI 悬停光点（向上飘的白点）
- 另含模块级 ui_particles 单例 + 便捷函数，供界面按钮悬停火花使用。

绘制坐标：draw(screen, arena_x, arena_y) 会把每个粒子坐标加上竞技场偏移，
          使粒子与游戏世界坐标一致；UI 用途传入 arena_x=0, arena_y=0 即可。
"""
import math
import random
import pygame

from constants import DIR_VECTORS, TANK_SIZE


class Particle:
    """单个粒子。color 接受 RGB 或 RGBA；绘制时按 life 比例衰减 alpha。"""

    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "color", "size")

    def __init__(self, x, y, vx, vy, life, color, size):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.life = life
        self.max_life = life
        # 统一为 RGBA，便于按存活比例衰减
        if len(color) == 4:
            self.color = (color[0], color[1], color[2], color[3])
        else:
            self.color = (color[0], color[1], color[2], 255)
        self.size = size


class ParticleSystem:
    def __init__(self):
        self.particles = []

    def clear(self):
        self.particles.clear()

    def spawn(self, x, y, count, color, speed_range, life_range, size_range):
        """批量生成：速度方向随机（0~2π）。"""
        for _ in range(count):
            ang = random.uniform(0.0, 2 * math.pi)
            sp = random.uniform(speed_range[0], speed_range[1])
            vx = math.cos(ang) * sp
            vy = math.sin(ang) * sp
            life = random.uniform(life_range[0], life_range[1])
            size = random.uniform(size_range[0], size_range[1])
            self.particles.append(Particle(x, y, vx, vy, life, color, size))

    def spawn_explosion(self, x, y, color, big=False):
        """爆炸：big=True 20 个，否则 12 个。
        颜色从中心白/黄渐变到边缘橙/红（color 用于边缘色调微调，None 则默认红）。"""
        count = 20 if big else 12
        edge = (255, 90, 50) if color is None else (
            color[0], max(60, int(color[1] * 0.5)), 50)
        for _ in range(count):
            ang = random.uniform(0.0, 2 * math.pi)
            sp = random.uniform(60, 230 if big else 170)
            vx = math.cos(ang) * sp
            vy = math.sin(ang) * sp
            life = random.uniform(0.3, 0.75 if big else 0.5)
            size = random.uniform(2.0, 5.0)
            r = random.random()
            if r < 0.4:
                col = (255, 255, 224)          # 核心：暖白
            elif r < 0.75:
                col = (255, 200, 80)           # 中段：金黄
            else:
                col = edge                     # 边缘：橙红
            self.particles.append(Particle(x, y, vx, vy, life, col, size))

    def spawn_muzzle_flash(self, x, y, direction):
        """炮口火焰：3~5 个橙黄粒子，速度朝向射击方向（direction 0-3）。"""
        dv = DIR_VECTORS.get(direction, (0, -1))
        base_ang = math.atan2(dv[1], dv[0])
        n = random.randint(3, 5)
        for _ in range(n):
            ang = base_ang + random.uniform(-0.45, 0.45)
            sp = random.uniform(80, 190)
            vx = math.cos(ang) * sp
            vy = math.sin(ang) * sp
            life = random.uniform(0.08, 0.18)
            size = random.uniform(2.0, 4.0)
            col = (255, random.randint(180, 235), 60)   # 橙黄
            self.particles.append(Particle(x, y, vx, vy, life, col, size))

    def spawn_hover_spark(self, x, y, color=(255, 255, 255)):
        """UI 悬停光点：1~2 个向上飘的白色小粒子。"""
        n = random.randint(1, 2)
        for _ in range(n):
            vx = random.uniform(-15, 15)
            vy = random.uniform(-55, -25)
            life = random.uniform(0.3, 0.6)
            size = random.uniform(1.5, 3.0)
            self.particles.append(Particle(x, y, vx, vy, life, color, size))

    def update(self, dt):
        """推进位置、衰减 life、移除死亡粒子；并施加轻微空气阻力。"""
        alive = []
        for p in self.particles:
            p.life -= dt
            if p.life <= 0:
                continue
            p.x += p.vx * dt
            p.y += p.vy * dt
            drag = max(0.0, 1.0 - 2.0 * dt)   # 轻微减速
            p.vx *= drag
            p.vy *= drag
            alive.append(p)
        self.particles = alive

    def draw(self, screen, arena_x, arena_y):
        """绘制所有粒子（圆形，按存活比例衰减 alpha）。"""
        for p in self.particles:
            t = p.life / p.max_life if p.max_life > 0 else 0.0
            if t < 0.0:
                t = 0.0
            alpha = int(255 * t)
            if alpha <= 0:
                continue
            r = max(1, int(p.size * (0.5 + 0.5 * t)))
            col = (p.color[0], p.color[1], p.color[2], alpha)
            cx = int(arena_x + p.x)
            cy = int(arena_y + p.y)
            pygame.draw.circle(screen, col, (cx, cy), r)


# ---------------------------------------------------------------------------
# 模块级 UI 粒子单例：供界面按钮悬停火花使用（与游戏世界粒子相互独立）。
# 由主循环每帧 update + draw 到画布（arena_x=0, arena_y=0）。
# ---------------------------------------------------------------------------
ui_particles = ParticleSystem()


def ui_emit_hover_spark(x, y, color=(255, 255, 255)):
    ui_particles.spawn_hover_spark(x, y, color)


def update_ui_particles(dt):
    ui_particles.update(dt)


def draw_ui_particles(screen):
    ui_particles.draw(screen, 0, 0)
