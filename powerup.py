"""
道具系统：地图上的道具箱刷新、拾取、生效、计时
- PowerUpBox：场上一个道具箱（30x30 浮动方块）
- PowerUpManager：统一负责刷新、碰撞拾取、给玩家施加/清除 buff、计时
"""
import math
import random
import pygame

from constants import (
    ARENA_X, ARENA_Y, ARENA_W, ARENA_H,
    TILE_SIZE, TILE_COLS, TILE_ROWS, TILE_EMPTY,
    CARNIVAL_MAX_BOXES, CARNIVAL_SPAWN_MIN, CARNIVAL_SPAWN_MAX,
)

# 道具类型常量
POWERUP_NONE = "none"
POWERUP_LASER = "laser"
POWERUP_BOUNCE = "bounce"
POWERUP_SCATTER = "scatter"
POWERUP_SHIELD = "shield"
POWERUP_HEAL = "heal"          # 2026-08-26 新增：恢复道具（即时回血，不入 buff 集合）

# 可被刷出的道具类型（含恢复道具）
POWERUP_TYPES = [POWERUP_LASER, POWERUP_BOUNCE, POWERUP_SCATTER, POWERUP_SHIELD, POWERUP_HEAL]

POWERUP_COLORS = {
    POWERUP_LASER: (255, 0, 0),      # 红
    POWERUP_BOUNCE: (0, 255, 0),     # 绿
    POWERUP_SCATTER: (0, 100, 255),  # 蓝
    POWERUP_SHIELD: (255, 215, 0),   # 金
    POWERUP_HEAL: (140, 240, 150),   # 嫩绿（修复包）
}

POWERUP_NAMES = {
    POWERUP_LASER: "激光炮",
    POWERUP_BOUNCE: "弹射弹",
    POWERUP_SCATTER: "散射弹",
    POWERUP_SHIELD: "护盾",
    POWERUP_HEAL: "修复包",
}

# 道具箱中央显示的首字母
POWERUP_LETTERS = {
    POWERUP_LASER: "L",
    POWERUP_BOUNCE: "B",
    POWERUP_SCATTER: "S",
    POWERUP_SHIELD: "H",
    POWERUP_HEAL: "+",
}

# 道具持续时间（秒）。perma buff（remaining >= PERMA_BUFF_THRESHOLD）不受计时影响
POWERUP_DURATION = 10.0
PERMA_BUFF_THRESHOLD = 999999.0
# 场上同时存在的最大道具箱数量（普通模式）
MAX_BOXES = 3
# 刷新间隔（秒）随机范围（普通模式）
SPAWN_INTERVAL_MIN = 10.0
SPAWN_INTERVAL_MAX = 15.0


class PowerUpBox:
    """场上一个道具箱：彩色方块 + 白色边框 + 上下浮动动画 + 中央首字母"""

    SIZE = 30

    def __init__(self, x, y, powerup_type):
        # (x, y) 为中心点坐标（竞技场内部坐标，0..ARENA_W / 0..ARENA_H）
        self.x = float(x)
        self.y = float(y)
        self.powerup_type = powerup_type
        self.alive = True
        self.phase = random.uniform(0, math.tau)  # 浮动动画相位

    def get_rect(self):
        """返回碰撞矩形（基于基准位置，不随浮动偏移，保证碰撞稳定）"""
        s = PowerUpBox.SIZE
        return pygame.Rect(int(self.x - s // 2), int(self.y - s // 2), s, s)

    def draw(self, screen, time_tick):
        if not self.alive:
            return
        color = POWERUP_COLORS.get(self.powerup_type, (255, 255, 255))
        letter = POWERUP_LETTERS.get(self.powerup_type, "?")
        # 浮动偏移：sin 波，振幅 4px
        float_y = math.sin(time_tick * 2.5 + self.phase) * 4.0
        cx = ARENA_X + self.x
        cy = ARENA_Y + self.y + float_y
        s = PowerUpBox.SIZE
        left = int(cx - s // 2)
        top = int(cy - s // 2)

        # 外发光底色（半透明）
        glow = pygame.Surface((s + 8, s + 8), pygame.SRCALPHA)
        pygame.draw.rect(glow, (color[0], color[1], color[2], 60),
                        (4, 4, s, s), border_radius=6)
        screen.blit(glow, (left - 4, top - 4))

        # 主体方块
        pygame.draw.rect(screen, color, (left, top, s, s), border_radius=6)
        # 高光
        pygame.draw.rect(screen, (255, 255, 255),
                        (left + 3, top + 3, s - 6, 4), border_radius=2)
        # 白色边框
        pygame.draw.rect(screen, (255, 255, 255),
                        (left, top, s, s), width=2, border_radius=6)
        # 中央首字母
        font = pygame.font.SysFont("arial", 18, bold=True)
        ts = font.render(letter, True, (255, 255, 255))
        screen.blit(ts, ts.get_rect(center=(int(cx), int(cy))))


class PowerUpManager:
    """统一管理者：刷新道具箱、处理玩家拾取、维护玩家 buff 计时"""

    def __init__(self, game_map, mode="normal"):
        self.game_map = game_map
        self.active_boxes = []
        # 狂欢模式：道具箱数量与刷新频率大幅提升
        if mode == "carnival":
            self.max_boxes = CARNIVAL_MAX_BOXES
            self.spawn_min = CARNIVAL_SPAWN_MIN
            self.spawn_max = CARNIVAL_SPAWN_MAX
            self.spawn_timer = 2.0
        else:
            self.max_boxes = MAX_BOXES
            self.spawn_min = SPAWN_INTERVAL_MIN
            self.spawn_max = SPAWN_INTERVAL_MAX
            # 首次刷新稍快（6 秒），让玩家很快能看到并体验
            self.spawn_timer = 6.0
        self.spawn_interval = random.uniform(self.spawn_min, self.spawn_max)
        # 保留出生点（避免道具箱刷在玩家/敌人出生处）
        self._reserved = self._compute_reserved_tiles()

    def _compute_reserved_tiles(self):
        """计算需要避开的中心瓦片集合（玩家出生 + 三个敌人出生）"""
        reserved = set()
        # 玩家出生（左下）：与 GameWorld 中 px,py 对应瓦片
        reserved.add((3, TILE_ROWS - 3))
        # 三个敌人出生点（来自 GameWorld.enemy_spawn_points）
        reserved.add((3, 2))
        reserved.add((TILE_COLS // 2, 2))
        reserved.add((TILE_COLS - 4, 2))
        return reserved

    # -------------------- 主更新 --------------------
    def update(self, dt, players, game_map):
        # 1. 刷新计时
        self.spawn_timer -= dt
        if self.spawn_timer <= 0:
            if len(self.active_boxes) < self.max_boxes:
                pos = self._get_random_empty_pos(game_map)
                if pos is not None:
                    ptype = random.choice(POWERUP_TYPES)
                    self.active_boxes.append(PowerUpBox(pos[0], pos[1], ptype))
            self.spawn_timer = random.uniform(self.spawn_min, self.spawn_max)

        # 2. 碰撞拾取
        for box in self.active_boxes:
            if not box.alive:
                continue
            brect = box.get_rect()
            for p in players:
                if not p.alive:
                    continue
                if p.get_rect().colliderect(brect):
                    self._apply_powerup(p, box.powerup_type)
                    box.alive = False
                    break
        self.active_boxes = [b for b in self.active_boxes if b.alive]

        # 3. 玩家道具计时（统一在此管理，避免与实体 update 重复扣时）
        # 2026-08-23 叠加版：遍历 powerup_buffs 集合，各道具独立计时；
        # 到期后若属于初始道具（perma）则恢复为永久，否则移除该修饰符。
        for p in players:
            if not p.powerup_buffs:
                continue
            for ptype in list(p.powerup_buffs.keys()):
                remain = p.powerup_buffs[ptype]
                # 护盾不在此集合；perma buff（>=阈值）不递减
                if not (0 < remain < PERMA_BUFF_THRESHOLD):
                    continue
                p.powerup_buffs[ptype] = remain - dt
                if p.powerup_buffs[ptype] <= 0:
                    # 到期：若属于坦克初始道具（default_powerup 拆解），恢复永久；否则移除
                    if ptype in p._expand_init(p.default_powerup):
                        p.powerup_buffs[ptype] = PERMA_BUFF_THRESHOLD
                    else:
                        del p.powerup_buffs[ptype]

    def _apply_powerup(self, player, ptype):
        """给玩家施加道具：
        - 恢复道具（heal）：即时回血，不经过 buff 集合；
        - 其余道具：走 Tank.apply_powerup（叠加版：加入集合独立计时，不清除其它道具）"""
        if ptype == POWERUP_HEAL:
            player.heal()
            return
        player.apply_powerup(ptype)

    # -------------------- 绘制 --------------------
    def draw(self, screen, time_tick):
        for box in self.active_boxes:
            box.draw(screen, time_tick)

    # -------------------- 工具 --------------------
    def _get_random_empty_pos(self, game_map):
        """在地图空地（非墙、非出生点、不与现有道具箱重叠）随机返回 (x, y)"""
        # 候选瓦片范围（避开最外圈钢墙）
        min_c, max_c = 1, TILE_COLS - 2
        min_r, max_r = 1, TILE_ROWS - 2
        for _ in range(80):
            c = random.randint(min_c, max_c)
            r = random.randint(min_r, max_r)
            # 必须为空地
            if game_map.get_tile(c, r) != TILE_EMPTY:
                continue
            # 避开出生点（含 1 格缓冲）
            if (c, r) in self._reserved:
                continue
            # 与现有道具箱不重叠
            cx = c * TILE_SIZE + TILE_SIZE // 2
            cy = r * TILE_SIZE + TILE_SIZE // 2
            too_close = False
            for box in self.active_boxes:
                if abs(box.x - cx) < TILE_SIZE and abs(box.y - cy) < TILE_SIZE:
                    too_close = True
                    break
            if too_close:
                continue
            return (cx, cy)
        return None
