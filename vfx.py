"""
技术美术 VFX 工具模块
================================
集中提供「预烘焙 + 零每帧分配」的视觉增强能力，供 entities / bullets / game_world 复用：

  - get_glow / draw_glow      : 径向渐变辉光精灵缓存（粒子、子弹辉光、爆炸、枪口火光共用）
  - shade                     : 颜色明暗工具（坦克渐变 / 描边高光）
  - ScreenShake               : 屏幕震动控制器（大爆炸时调用）
  - get_tank_sprite / draw_tank : 坦克 Sprite 预烘焙（渐变车身高光 + 投影 + 描边 + 炮管），按 颜色×方向 缓存

性能纪律（本条线强制）：
  * 任何「每帧重复绘制」的圆/光晕都必须走缓存 glow / 直接描边，禁止每帧新建 Surface。
  * 坦克只烘焙一次（≤ 5 车 × 4 方向 = 20 个 surface），之后纯 blit。
"""
import math
import random
import pygame
from constants import TANK_SIZE, COLOR_GOLD
from constants import (
    TANK_STYLE_STANDARD, TANK_STYLE_SCOUT, TANK_STYLE_HEAVY,
    TANK_STYLE_SNIPER, TANK_STYLE_KZY,
)

# 坦克 Sprite 留白（投影 + 炮管超出车身所需 padding）
TANK_PAD = 7

# ---------------------------------------------------------------------------
# 颜色工具
# ---------------------------------------------------------------------------
def shade(color, factor):
    """返回 color 乘以 factor 后的 RGB（>1 提亮，<1 压暗），上限 255。"""
    return (
        min(255, max(0, int(color[0] * factor))),
        min(255, max(0, int(color[1] * factor))),
        min(255, max(0, int(color[2] * factor))),
    )


# ---------------------------------------------------------------------------
# 辉光精灵缓存（径向渐变，预烘焙一次后无限复用）
# ---------------------------------------------------------------------------
_GLOW_CACHE = {}


def get_glow(radius, color):
    """返回预烘焙的径向渐变辉光 surface（中心亮、边缘透明）。
    按 (radius, rgb) 缓存，避免每帧新建 Surface 造成 GC 抖动。"""
    r = int(radius)
    if r < 1:
        r = 1
    key = (r, color[0], color[1], color[2])
    surf = _GLOW_CACHE.get(key)
    if surf is not None:
        return surf
    size = r * 2 + 2
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    cx = r + 1
    # 从外向内叠加，形成平滑径向衰减
    for i in range(r, 0, -1):
        t = 1.0 - i / r
        a = int(255 * (t ** 1.6))
        pygame.draw.circle(surf, (color[0], color[1], color[2], a), (cx, cx), i)
    _GLOW_CACHE[key] = surf
    return surf


def draw_glow(screen, x, y, radius, color, alpha=255):
    """在屏幕坐标 (x, y) 以辉光方式绘制一个点。alpha<255 时临时调暗并立即复位，
    不影响缓存 surface（单线程顺序绘制安全）。"""
    if radius < 1:
        return
    surf = get_glow(radius, color)
    prev = surf.get_alpha()
    if alpha != 255:
        surf.set_alpha(alpha)
    screen.blit(surf, (int(x - radius - 1), int(y - radius - 1)))
    if alpha != 255:
        surf.set_alpha(prev)


# ---------------------------------------------------------------------------
# 屏幕震动
# ---------------------------------------------------------------------------
class ScreenShake:
    """轻量屏幕震动：大爆炸时 add()，每帧 update(dt)，draw 时取 offset() 偏移竞技场。
    幅度受预算约束（调用方传 mag≤4），0.3s 内指数衰减。"""

    def __init__(self, max_mag=4.0, dur=0.30):
        self.t = dur
        self.dur = dur
        self.mag = 0.0
        self.max_mag = max_mag

    def add(self, mag, dur=None):
        mag = min(mag, self.max_mag)
        if dur is not None:
            self.dur = dur
        # 取更强的一次，并重置计时
        if mag >= self.mag:
            self.mag = mag
            self.t = 0.0

    def update(self, dt):
        if self.t < self.dur:
            self.t += dt
        else:
            self.mag = 0.0

    def offset(self):
        if self.mag <= 0:
            return (0.0, 0.0)
        k = 1.0 - (self.t / self.dur)
        if k < 0:
            k = 0.0
        ang = random.uniform(0, math.tau)
        m = self.mag * (0.4 + 0.6 * k)  # 末段更弱
        return (math.cos(ang) * m, math.sin(ang) * m)


# ---------------------------------------------------------------------------
# 坦克 Sprite 预烘焙（渐变车身高光 + 投影 + 描边 + 炮管）
# ---------------------------------------------------------------------------
_TANK_CACHE = {}

# 方向 -> 炮管绘制函数参数 (dx, dy) 偏移
_DIR_BARREL = {
    0: (0, -1),   # 上
    1: (1, 0),    # 右
    2: (0, 1),    # 下
    3: (-1, 0),   # 左
}


def get_tank_sprite(color, direction, frame=0, style=TANK_STYLE_STANDARD):
    """预烘焙一辆坦克 surface（含 TANK_PAD 留白），按 (color, direction, frame, style) 缓存。
    frame∈{0,1}：履带齿纹偏移两帧，形成履带滚动动画（静止时固定用 frame=0）。
    style：视觉风格标识（scout/heavy/sniper/kzy/standard），仅改变外形/炮管/炮塔细节装饰，
           不改动碰撞尺寸 TANK_SIZE。
    表面为 SRCALPHA，绘制时直接 blit 到屏幕对应位置。"""
    key = (color, direction, frame & 1, style)
    surf = _TANK_CACHE.get(key)
    if surf is not None:
        return surf

    S = TANK_SIZE + TANK_PAD * 2
    half = TANK_SIZE // 2
    cx = cy = S // 2
    surf = pygame.Surface((S, S), pygame.SRCALPHA)

    # 1) 投影（底部椭圆，半透明黑）
    pygame.draw.ellipse(surf, (0, 0, 0, 90),
                        (cx - half - 1, cy + half - 4, TANK_SIZE + 2, 12))

    # ---- 车身尺寸风格化（仅视觉，不碰 TANK_SIZE 碰撞框）----
    # scout 瘦长、heavy 宽大、其余标准；高度随宽度联动保持居中
    if style == TANK_STYLE_SCOUT:
        body_w = TANK_SIZE - 10
        body_h = TANK_SIZE - 6
    elif style == TANK_STYLE_HEAVY:
        body_w = TANK_SIZE - 0          # 撑满可用宽
        body_h = TANK_SIZE - 16
    else:
        body_w = TANK_SIZE - 4
        body_h = TANK_SIZE - 12
    body_top = cy - body_h // 2
    body_rect = pygame.Rect(cx - body_w // 2, body_top, body_w, body_h)

    # 2) 履带（上下两条深灰带 + 齿纹）；KZY 用锯齿细节
    track_color = (35, 35, 45)
    track_h = 8
    for ty in (cy - half - 2, cy + half - track_h + 2):
        pygame.draw.rect(surf, track_color,
                         (cx - half - 3, ty, TANK_SIZE + 6, track_h), border_radius=3)
    phase = 3 if (frame & 1) else 0
    if style == TANK_STYLE_KZY:
        # 锯齿履带：每段三角形齿（机械锯齿感）
        for i in range(-half + phase, half, 6):
            tcol = (70, 70, 84)
            for (ax, ay_top, ay_bot) in [
                (cx + i, cy - half - 2, cy - half + track_h + 2),
                (cx + i, cy + half - track_h - 2, cy + half + 2),
            ]:
                tri = [(ax, ay_top), (ax + 3, ay_top), (ax + 1, (ay_top + ay_bot) // 2)]
                pygame.draw.polygon(surf, tcol, tri)
                tri2 = [(ax, ay_bot), (ax + 3, ay_bot), (ax + 1, (ay_top + ay_bot) // 2)]
                pygame.draw.polygon(surf, tcol, tri2)
    else:
        for i in range(-half + phase, half, 6):
            pygame.draw.line(surf, (60, 60, 72),
                             (cx + i, cy - half - 1), (cx + i, cy - half + track_h + 1), 1)
            pygame.draw.line(surf, (60, 60, 72),
                             (cx + i, cy + half - track_h + 1), (cx + i, cy + half + 2), 1)

    # 3) 车身：垂直渐变（顶亮底暗）
    top_f = 1.30
    bot_f = 0.70
    for yy in range(body_rect.top, body_rect.bottom):
        f = top_f + (bot_f - top_f) * (yy - body_rect.top) / max(1, body_h)
        pygame.draw.line(surf, shade(color, f),
                         (body_rect.left, yy), (body_rect.right - 1, yy))
    # 车身描边（KZY 用金色 2px 描边）
    if style == TANK_STYLE_KZY:
        pygame.draw.rect(surf, COLOR_GOLD, body_rect, width=2, border_radius=4)
    else:
        pygame.draw.rect(surf, (0, 0, 0), body_rect, width=2, border_radius=4)
    # 顶部一条高光（金属反光）
    pygame.draw.line(surf, shade(color, 1.5),
                     (body_rect.left + 3, body_rect.top + 2),
                     (body_rect.right - 4, body_rect.top + 2), 2)

    # 3b) 所有坦克：侧边装甲条纹（2px，颜色比主体深 30%）
    stripe_color = shade(color, 0.70)
    inset = 3
    pygame.draw.line(surf, stripe_color,
                     (body_rect.left + inset, body_rect.top + body_h * 0.30),
                     (body_rect.left + inset, body_rect.bottom - body_h * 0.30), 2)
    pygame.draw.line(surf, stripe_color,
                     (body_rect.right - inset, body_rect.top + body_h * 0.30),
                     (body_rect.right - inset, body_rect.bottom - body_h * 0.30), 2)

    # 4) 炮塔（径向高光：底圆 + 左上偏移亮圆）
    turret_r = int(TANK_SIZE * 0.30)
    pygame.draw.circle(surf, shade(color, 0.9), (cx, cy), turret_r)
    pygame.draw.circle(surf, (0, 0, 0), (cx, cy), turret_r, width=1)
    pygame.draw.circle(surf, shade(color, 1.4),
                       (cx - turret_r * 0.3, cy - turret_r * 0.3),
                       max(2, int(turret_r * 0.55)))
    # 风格化炮塔细节
    if style == TANK_STYLE_HEAVY:
        # 炮塔上方小型矩形（机枪/传感器）
        rec_w, rec_h = 10, 7
        pygame.draw.rect(surf, shade(color, 0.7),
                         (cx - rec_w // 2, cy - turret_r - rec_h + 2, rec_w, rec_h),
                         border_radius=2)
        pygame.draw.rect(surf, (0, 0, 0),
                         (cx - rec_w // 2, cy - turret_r - rec_h + 2, rec_w, rec_h),
                         width=1, border_radius=2)
    elif style == TANK_STYLE_SNIPER:
        # 炮塔白色 1px 十字准星线（仅水平 + 垂直短线段，不冲出炮塔）
        qu = max(2, int(turret_r * 0.5))
        pygame.draw.line(surf, (235, 235, 240), (cx - qu, cy), (cx + qu, cy), 1)
        pygame.draw.line(surf, (235, 235, 240), (cx, cy - qu), (cx, cy + qu), 1)
    elif style == TANK_STYLE_KZY:
        # 炮塔上三角标志（▲）金色
        t = turret_r * 0.8
        pygame.draw.polygon(surf, COLOR_GOLD, [
            (cx, cy - t),
            (cx + t * 0.86, cy + t * 0.5),
            (cx - t * 0.86, cy + t * 0.5),
        ])

    # 5) 炮管（按方向）；风格化长度/粗细
    if style == TANK_STYLE_SCOUT:
        bw, bh = 4, 20          # 细长
    elif style == TANK_STYLE_HEAVY:
        bw, bh = 9, 12          # 粗短
    elif style == TANK_STYLE_SNIPER:
        bw, bh = 6, 24          # 极长
    else:
        bw, bh = 6, 16
    d = _DIR_BARREL.get(direction, (0, -1))
    barrel_color = shade(color, 0.85)
    if d[1] != 0:  # 上/下
        sign = d[1]
        by = cy - bh - 2 if sign < 0 else cy + 2
        br = pygame.Rect(cx - bw // 2, by, bw, bh)
    else:  # 左/右
        sign = d[0]
        bx = cx - bh - 2 if sign < 0 else cx + 2
        br = pygame.Rect(bx, cy - bw // 2, bh, bw)
    pygame.draw.rect(surf, barrel_color, br, border_radius=2)
    pygame.draw.rect(surf, (0, 0, 0), br, width=1, border_radius=2)

    _TANK_CACHE[key] = surf
    return surf


def draw_tank(screen, sx, sy, color, direction, hit_flash=0.0, anim_frame=0,
              style=TANK_STYLE_STANDARD):
    """在屏幕坐标 (sx, sy)（坦克中心点）绘制预烘焙坦克 Sprite。
    hit_flash∈[0,1]：命中时叠加白光脉冲；anim_frame：履带滚动动画帧（0/1）。
    style：视觉风格标识（仅视觉，不影响碰撞）。"""
    surf = get_tank_sprite(color, direction, anim_frame, style)
    S = surf.get_width()
    screen.blit(surf, (int(sx - S // 2), int(sy - S // 2)))
    if hit_flash > 0:
        a = int(min(1.0, hit_flash) * 200)
        draw_glow(screen, sx, sy, TANK_SIZE * 0.55, (255, 255, 255), alpha=a)


# ---------------------------------------------------------------------------
# 爆炸精灵缓存（火球三层 + 冲击波环，预烘焙后缩放 blit，零每帧分配）
# ---------------------------------------------------------------------------
_EXPLOSION_CACHE = {}


def get_explosion_sprite(big):
    """预烘焙一张最大尺寸的爆炸火球贴图（白芯-黄中-红外三层），按 big 缓存。
    绘制时按当前半径缩放并整体调 alpha。"""
    key = bool(big)
    surf = _EXPLOSION_CACHE.get(key)
    if surf is not None:
        return surf
    max_r = 26 if big else 18
    size = max_r * 2 + 2
    cx = size // 2
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    for rad, col in [
        (max(2, int(max_r * 0.30)), (255, 255, 255)),
        (max(2, int(max_r * 0.65)), (255, 210, 40)),
        (max(2, int(max_r)), (255, 90, 40)),
    ]:
        pygame.draw.circle(surf, col, (cx, cx), rad)
    _EXPLOSION_CACHE[key] = surf
    return surf


_RING_CACHE = {}


def get_ring(max_r):
    """预烘焙一张最大尺寸的冲击波圆环贴图（浅色描边），按 max_r 缓存。
    绘制时按当前半径缩放并整体调 alpha。"""
    key = int(max_r)
    surf = _RING_CACHE.get(key)
    if surf is not None:
        return surf
    size = max_r * 2 + 2
    cx = size // 2
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.circle(surf, (255, 240, 200, 255), (cx, cx), max_r, width=4)
    _RING_CACHE[key] = surf
    return surf


def draw_explosion(screen, sx, sy, t, big, alpha=255):
    """绘制一枚爆炸（火球 + 冲击波环）。t∈[0,1] 进度，big 决定尺寸。
    火球底光 + 预烘焙火球缩放 + 冲击波环，全程零每帧 Surface 分配。"""
    max_r = 26 if big else 18
    draw_glow(screen, sx, sy, max_r * (0.3 + t * 0.7) + 8, (255, 150, 60),
              alpha=int(alpha * 0.6))

    # 火球：按当前半径缩放预烘焙贴图（缓存 surface 只调 alpha，不新建）
    r = int(max_r * (0.3 + t * 0.7))
    sprite = get_explosion_sprite(big)
    prev = sprite.get_alpha()
    if alpha != 255:
        sprite.set_alpha(alpha)
    scale = (r * 2 + 2) / sprite.get_width()
    if scale > 0:
        scaled = pygame.transform.smoothscale(
            sprite,
            (max(2, int(sprite.get_width() * scale)),
             max(2, int(sprite.get_height() * scale))))
        screen.blit(scaled, (int(sx - scaled.get_width() // 2),
                              int(sy - scaled.get_height() // 2)))
    if alpha != 255:
        sprite.set_alpha(prev)

    # 冲击波环（中段出现，迅速扩散淡出）
    if t > 0.15:
        wr = int(max_r * 1.4 * t)
        wa = int(180 * (1 - t))
        ring = get_ring(max_r * 1.4)
        rprev = ring.get_alpha()
        if wa != 255:
            ring.set_alpha(wa)
        scale2 = (wr * 2 + 2) / ring.get_width()
        if scale2 > 0:
            rscaled = pygame.transform.smoothscale(
                ring,
                (max(2, int(ring.get_width() * scale2)),
                 max(2, int(ring.get_height() * scale2))))
            screen.blit(rscaled, (int(sx - rscaled.get_width() // 2),
                                  int(sy - rscaled.get_height() // 2)))
        if wa != 255:
            ring.set_alpha(rprev)


# ---------------------------------------------------------------------------
# 竞技场暗角（vignette）：预烘焙一次，每帧最后 blit 一次，营造纵深聚焦
# ---------------------------------------------------------------------------
_VIGNETTE_CACHE = {}


def get_vignette(w, h, strength=110, radius_scale=1.0):
    """预烘焙竞技场暗角贴图（四角渐暗、中心亮，视觉引导聚焦中心）。
    采用「从外到内逐层圆环」绘制（width=step，非实心圆）：
      - 最外环 alpha 最高（边缘最暗），向中心逐层递减到透明；
      - 半径覆盖到四角（radius_scale=1.0 默认包住矩形四角），
        避免旧版实心圆叠加导致「四角透明、边缘中点反而最暗」的反向效果。
    按 (w, h) 缓存。绘制时以 (0,0) 对齐 blit 即可（调用方自行偏移到竞技场坐标）。"""
    key = (int(w), int(h), int(strength))
    surf = _VIGNETTE_CACHE.get(key)
    if surf is not None:
        return surf
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    cx, cy = w // 2, h // 2
    max_d = math.hypot(cx, cy) * radius_scale
    if max_d < 1:
        max_d = 1.0
    step = 2
    for r in range(int(max_d), 0, -step):
        d = r / max_d  # 1=边缘 0=中心
        a = int(strength * (d ** 1.8))  # 边缘最暗，向中心平滑衰减
        if a <= 0:
            continue
        pygame.draw.circle(surf, (0, 0, 0, a), (cx, cy), r, width=step)
    _VIGNETTE_CACHE[key] = surf
    return surf


def draw_vignette(screen, ax, ay, w, h, strength=110):
    """在屏幕坐标 (ax, ay) 起绘制一张竞技场暗角（仅一次 blit）。"""
    surf = get_vignette(w, h, strength)
    screen.blit(surf, (int(ax), int(ay)))
