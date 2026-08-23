"""
关卡配置表 —— 15 关系统（难度递增，纯障碍物地图）

每个关卡由以下字段描述：
  level        : 关卡序号（1..15）
  enemy_count  : 该关敌人总数
  enemy_speed  : 敌人坦克移速（像素/帧，按 60FPS 换算后直接乘 dt）
  enemy_fire_cd: 敌人开火冷却（秒），越大攻击越稀疏
  extra_walls  : 砖墙数量（可被摧毁的掩体）
  steel_walls  : 钢墙数量（不可摧毁的永久掩体）

难度分三个 Tier：
  Tier 1（1-5 关）  ：基础难度，少量敌人 + 稀疏障碍
  Tier 2（6-10 关） ：中等难度，敌人更多更快、障碍更密
  Tier 3（11-15 关）：高难度，大量高速敌人 + 密集障碍
"""

LEVELS = [
    # ===== Tier 1（基础难度）=====
    {"level": 1,  "enemy_count": 3,  "enemy_speed": 1.5, "enemy_fire_cd": 2.0, "extra_walls": 5,  "steel_walls": 1},
    {"level": 2,  "enemy_count": 4,  "enemy_speed": 1.8, "enemy_fire_cd": 1.8, "extra_walls": 8,  "steel_walls": 1},
    {"level": 3,  "enemy_count": 5,  "enemy_speed": 2.0, "enemy_fire_cd": 1.5, "extra_walls": 10, "steel_walls": 2},
    {"level": 4,  "enemy_count": 6,  "enemy_speed": 2.2, "enemy_fire_cd": 1.5, "extra_walls": 12, "steel_walls": 2},
    {"level": 5,  "enemy_count": 8,  "enemy_speed": 2.5, "enemy_fire_cd": 1.2, "extra_walls": 15, "steel_walls": 2},
    # ===== Tier 2（中等难度）=====
    {"level": 6,  "enemy_count": 5,  "enemy_speed": 2.0, "enemy_fire_cd": 1.5, "extra_walls": 10, "steel_walls": 2},
    {"level": 7,  "enemy_count": 6,  "enemy_speed": 2.2, "enemy_fire_cd": 1.4, "extra_walls": 12, "steel_walls": 2},
    {"level": 8,  "enemy_count": 7,  "enemy_speed": 2.5, "enemy_fire_cd": 1.3, "extra_walls": 15, "steel_walls": 3},
    {"level": 9,  "enemy_count": 8,  "enemy_speed": 2.8, "enemy_fire_cd": 1.2, "extra_walls": 18, "steel_walls": 3},
    {"level": 10, "enemy_count": 10, "enemy_speed": 3.0, "enemy_fire_cd": 1.0, "extra_walls": 20, "steel_walls": 3},
    # ===== Tier 3（高难度）=====
    {"level": 11, "enemy_count": 8,  "enemy_speed": 2.5, "enemy_fire_cd": 1.2, "extra_walls": 15, "steel_walls": 3},
    {"level": 12, "enemy_count": 9,  "enemy_speed": 2.8, "enemy_fire_cd": 1.1, "extra_walls": 18, "steel_walls": 3},
    {"level": 13, "enemy_count": 10, "enemy_speed": 3.0, "enemy_fire_cd": 1.0, "extra_walls": 20, "steel_walls": 4},
    {"level": 14, "enemy_count": 12, "enemy_speed": 3.2, "enemy_fire_cd": 0.9, "extra_walls": 22, "steel_walls": 4},
    {"level": 15, "enemy_count": 15, "enemy_speed": 3.5, "enemy_fire_cd": 0.8, "extra_walls": 25, "steel_walls": 4},
]

TOTAL_LEVELS = len(LEVELS)

# 各关敌人总数查表（双人合作模式：敌人 = 该关 + COOP_EXTRA_ENEMIES）
LEVEL_ENEMY_COUNTS = {lvl["level"]: lvl["enemy_count"] for lvl in LEVELS}


def get_level_config(level):
    """获取关卡配置。超界时夹紧到 [1, TOTAL_LEVELS]，避免非法关卡崩溃。"""
    if level < 1:
        level = 1
    if level > len(LEVELS):
        level = len(LEVELS)
    return LEVELS[level - 1]
