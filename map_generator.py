"""
纯障碍物地图生成器（map_generator）
====================================
依据关卡配置（extra_walls / steel_walls）随机生成砖墙与钢墙，保留钢墙外框
与出生安全区。返回 Map 对象，兼容游戏现有碰撞检测接口：

    get_wall_at(col, row) / in_bounds(col, row)      # 规范指定接口
    get_tile(col, row) / world_to_tile(wx, wy)        # 瓦片查询
    get_tile_rect(col, row) / destroy_tile(col, row)  # 瓦片矩形 / 摧毁
    can_tank_occupy(wx, wy, size)                     # 坦克占位判定
    point_passable_for_bullet(wx, wy)                 # 子弹视线
    bullet_hit_tile(wx, wy, bullet)                   # 子弹命中瓦片
    draw(screen, arena_x, arena_y)                    # 渲染（含背景白字）

注：网格规格与游戏竞技场保持一致（880x400，40px 瓦片，22x10）。
如需切换为 800x600 竞技场，仅需调整 constants.TILE_COLS/TILE_ROWS/ARENA_*，
本模块会自动跟随（GRID_SIZE/COLS/ROWS 由 constants 派生）。
"""
import random
import pygame
from constants import (
    TILE_SIZE, TILE_COLS, TILE_ROWS,
    TILE_EMPTY, TILE_BRICK, TILE_STEEL,
    ARENA_W, ARENA_H, ARENA_BG, ARENA_BG_TEXT, ARENA_GRID, ARENA_BORDER,
    FONT_XXL, COLOR_BRICK, COLOR_STEEL,
)
from level_config import get_level_config


class MapGenerator:
    """纯障碍物地图生成器：每关随机散布砖墙/钢墙，保留钢墙外框与出生安全区。"""

    # 网格规格（由 constants 派生，保证与竞技场一致）
    GRID_SIZE = TILE_SIZE
    COLS = TILE_COLS
    ROWS = TILE_ROWS

    def generate(self, level_config, fonts=None, seed=None):
        """依据关卡配置生成地图，返回 Map 对象。

        level_config : dict，含 "extra_walls"（砖墙数）/"steel_walls"（钢墙数）。
        fonts        : 可选，传给 Map 用于渲染背景白字水印。
        seed         : 可选随机种子；默认按关卡派生，保证同关可复现。
        """
        if seed is None:
            seed = int(level_config.get("level", 1)) * 9973 + 5
        rng = random.Random(seed)

        # 1. 创建空地图（0=空地，1=砖墙，2=钢墙）
        grid = [[TILE_EMPTY for _ in range(self.COLS)] for _ in range(self.ROWS)]

        # 2. 外围钢墙边界（厚度 1 格）
        for c in range(self.COLS):
            grid[0][c] = TILE_STEEL
            grid[self.ROWS - 1][c] = TILE_STEEL
        for r in range(self.ROWS):
            grid[r][0] = TILE_STEEL
            grid[r][self.COLS - 1] = TILE_STEEL

        # 3. 出生安全区（玩家左下 + 敌人上方出生点）
        spawn_safe_zones = self._spawn_safe_zones()

        # 4. 收集内部可放置空格（去掉外框与出生安全区）
        cells = []
        for r in range(1, self.ROWS - 1):
            for c in range(1, self.COLS - 1):
                if self._in_safe_zone(r, c, spawn_safe_zones):
                    continue
                cells.append((c, r))
        rng.shuffle(cells)

        total = len(cells)
        steel = min(int(level_config["steel_walls"]), total)
        extra = min(int(level_config["extra_walls"]), total - steel)

        # 5. 先放钢墙（永久掩体），再放砖墙（可摧毁掩体）
        for i in range(steel):
            c, r = cells[i]
            grid[r][c] = TILE_STEEL
        for i in range(steel, steel + extra):
            c, r = cells[i]
            grid[r][c] = TILE_BRICK

        return Map(grid, self.COLS, self.ROWS, self.GRID_SIZE,
                    fonts=fonts, bg_text=ARENA_BG_TEXT)

    def _spawn_safe_zones(self):
        """出生安全区矩形列表，元素为 (r1, c1, r2, c2) 含端点。

        覆盖：
          - 玩家：左下 3x3
          - 敌人：上方三个出生点各 3x3（与 game_world 的 enemy_spawn_points 对应）
        保证生成障碍物时绝不遮挡出生区，满足验收：出生区无障碍、敌人不与墙重叠。
        """
        zones = [
            (self.ROWS - 4, 2, self.ROWS - 2, 4),   # 玩家：左下（内部 3x3，避开外框钢墙）
        ]
        # 敌人三个出生点列（与 GameWorld.enemy_spawn_points 保持一致）
        enemy_cols = [3, self.COLS // 2, self.COLS - 4]
        for ec in enemy_cols:
            zones.append((1, ec - 1, 3, ec + 1))
        return zones

    def _in_safe_zone(self, r, c, zones):
        for (r1, c1, r2, c2) in zones:
            if r1 <= r <= r2 and c1 <= c <= c2:
                return True
        return False


class Map:
    """地图数据 + 碰撞/渲染。grid[r][c]：0=空地, 1=砖墙, 2=钢墙。"""

    def __init__(self, grid, cols=None, rows=None, tile_size=None,
                 fonts=None, bg_text=ARENA_BG_TEXT):
        self.tiles = grid
        self.cols = cols if cols is not None else len(grid[0])
        self.rows = rows if rows is not None else len(grid)
        self.tile_size = tile_size if tile_size is not None else TILE_SIZE
        self.fonts = fonts
        self.bg_text = bg_text

    # ============ 坐标转换 ============
    def world_to_tile(self, wx, wy):
        """世界像素(竞技场内部坐标) -> (col, row)。越界返回 None"""
        c = int(wx // self.tile_size)
        r = int(wy // self.tile_size)
        if 0 <= c < self.cols and 0 <= r < self.rows:
            return (c, r)
        return None

    def get_tile(self, col, row):
        if 0 <= col < self.cols and 0 <= row < self.rows:
            return self.tiles[row][col]
        return TILE_STEEL  # 越界视为钢墙

    def get_tile_rect(self, col, row):
        ts = self.tile_size
        return pygame.Rect(col * ts, row * ts, ts, ts)

    def destroy_tile(self, col, row):
        """摧毁砖墙（保护外框钢墙与越界）"""
        if 0 < col < self.cols - 1 and 0 < row < self.rows - 1:
            if self.tiles[row][col] == TILE_BRICK:
                self.tiles[row][col] = TILE_EMPTY

    # ============ 规范接口（get_wall_at / in_bounds）============
    def in_bounds(self, col, row):
        """(col, row) 是否在地图范围内"""
        return 0 <= col < self.cols and 0 <= row < self.rows

    def get_wall_at(self, col, row):
        """返回该格瓦片类型：0=空地, 1=砖墙, 2=钢墙；越界返回 None。"""
        if not self.in_bounds(col, row):
            return None
        return self.tiles[row][col]

    # ============ 碰撞 ============
    def can_tank_occupy(self, wx, wy, tank_size):
        """检查坦克中心点(wx,wy)是否能放置（四角瓦片检查）"""
        half = tank_size // 2 - 1
        corners = [
            (wx - half, wy - half),
            (wx + half, wy - half),
            (wx - half, wy + half),
            (wx + half, wy + half),
        ]
        for cx, cy in corners:
            if cx < 0 or cy < 0 or cx >= ARENA_W or cy >= ARENA_H:
                return False
            t = self.world_to_tile(cx, cy)
            if t is None:
                return False
            tile = self.get_tile(t[0], t[1])
            if tile == TILE_BRICK or tile == TILE_STEEL:
                return False
        return True

    def point_passable_for_bullet(self, wx, wy):
        """仅检查点是否在空地上（视线测试）"""
        if wx < 0 or wy < 0 or wx >= ARENA_W or wy >= ARENA_H:
            return False
        t = self.world_to_tile(wx, wy)
        if t is None:
            return False
        tile = self.get_tile(t[0], t[1])
        return tile == TILE_EMPTY

    def bullet_hit_tile(self, wx, wy, bullet):
        """返回被击中瓦片 (tile_type, col, row) 或 None"""
        t = self.world_to_tile(wx, wy)
        if t is None:
            return None
        c, r = t
        tile = self.get_tile(c, r)
        if tile == TILE_EMPTY:
            return None
        return (tile, c, r)

    # ============ 绘制 ============
    def draw(self, screen, arena_x, arena_y):
        """绘制瓦片：黑底 + 白色主题水印 + 掩体。"""
        ts = self.tile_size
        # 纯黑底色
        pygame.draw.rect(screen, ARENA_BG,
                         (arena_x, arena_y, ARENA_W, ARENA_H))
        # 极淡网格，提供空间参照但不抢眼
        for c in range(self.cols + 1):
            pygame.draw.line(screen, ARENA_GRID,
                             (arena_x + c * ts, arena_y),
                             (arena_x + c * ts, arena_y + ARENA_H), 1)
        for r in range(self.rows + 1):
            pygame.draw.line(screen, ARENA_GRID,
                             (arena_x, arena_y + r * ts),
                             (arena_x + ARENA_W, arena_y + r * ts), 1)

        # 背景白字水印（用户已实现样式，保留不受地图生成影响）
        if self.fonts and FONT_XXL in self.fonts:
            font = self.fonts[FONT_XXL]
            tsurf = font.render(self.bg_text, True, (255, 255, 255))
            tsurf.set_alpha(150)
            screen.blit(tsurf, tsurf.get_rect(
                center=(arena_x + ARENA_W // 2, arena_y + ARENA_H // 2)))

        # 瓦片
        for r in range(self.rows):
            for c in range(self.cols):
                t = self.tiles[r][c]
                if t == TILE_EMPTY:
                    continue
                x = arena_x + c * ts
                y = arena_y + r * ts
                if t == TILE_BRICK:
                    self._draw_brick(screen, x, y)
                elif t == TILE_STEEL:
                    self._draw_steel(screen, x, y)

    def _draw_brick(self, screen, x, y):
        s = self.tile_size
        pygame.draw.rect(screen, COLOR_BRICK, (x + 1, y + 1, s - 2, s - 2), border_radius=2)
        half = s // 2
        pygame.draw.line(screen, (80, 40, 25), (x + 1, y + half), (x + s - 1, y + half), 1)
        pygame.draw.line(screen, (80, 40, 25), (x + half, y + 1), (x + half, y + half), 1)
        pygame.draw.line(screen, (80, 40, 25),
                         (x + half // 2, y + half), (x + half // 2, y + s - 1), 1)
        pygame.draw.line(screen, (80, 40, 25),
                         (x + half + half // 2, y + half), (x + half + half // 2, y + s - 1), 1)
        pygame.draw.rect(screen, (100, 55, 35), (x + 1, y + 1, s - 2, s - 2), width=1, border_radius=2)

    def _draw_steel(self, screen, x, y):
        s = self.tile_size
        pygame.draw.rect(screen, COLOR_STEEL, (x + 1, y + 1, s - 2, s - 2), border_radius=3)
        pygame.draw.line(screen, (220, 230, 245), (x + 4, y + 4), (x + s - 5, y + 4), 2)
        pygame.draw.line(screen, (220, 230, 245), (x + 4, y + 4), (x + 4, y + s - 5), 2)
        pygame.draw.line(screen, (80, 88, 100),
                         (x + s - 5, y + 4), (x + s - 5, y + s - 4), 2)
        pygame.draw.line(screen, (80, 88, 100),
                         (x + 4, y + s - 5), (x + s - 4, y + s - 5), 2)
        pygame.draw.circle(screen, (70, 80, 100),
                           (x + s // 2, y + s // 2), 3)
        pygame.draw.rect(screen, (70, 80, 100),
                         (x + 1, y + 1, s - 2, s - 2), width=1, border_radius=3)
