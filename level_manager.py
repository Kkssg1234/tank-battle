"""
关卡管理（单人模式）
====================
负责加载关卡、胜负判定与关卡进度推进。single_player（game_world.GameWorld）
构造时即已完成 map / player / enemies 的创建，故 LevelManager 作为编排层，
委托 GameWorld 创建并返回，对外暴露简洁的关卡管理接口。

规范接口：
    LevelManager(start_level=1)
    .load_level(level_num, tank_name, fonts) -> GameWorld
    .check_victory(world) -> bool
    .check_defeat(world)  -> bool
    .is_last_level()      -> bool   # 第 15 关判定（用于通关动画）
    .next_level()         -> int    # 推进到下一关
"""
from constants import TOTAL_LEVELS
from level_config import get_level_config
from game_world import GameWorld


class LevelManager:
    """单人模式关卡管理：当前关卡、状态、加载与进度。"""

    def __init__(self, start_level=1):
        self.current_level = max(1, min(int(start_level), TOTAL_LEVELS))
        self.state = "playing"  # playing / cleared / failed

    def load_level(self, level_num, tank_name, fonts):
        """加载关卡，返回已构建好的 GameWorld 实例。

        GameWorld 内部已依据 level_config 完成：
          - 地图（MapGenerator 生成）
          - 玩家坦克（出生在左下安全区）
          - 敌人坦克（enemy_speed / fire_cd 来自关卡配置，传给 EnemyAI）
        这里额外挂上关卡元信息与计时字段，方便外部读取。"""
        level_num = max(1, min(int(level_num), TOTAL_LEVELS))
        self.current_level = level_num
        self.state = "playing"

        cfg = get_level_config(level_num)
        world = GameWorld(level_num, tank_name, fonts)

        # 兼容规范：附带关卡元信息与计时（供外部读取）
        world.level_config = cfg
        world.start_time = 0.0
        world.kill_count = 0
        return world

    def check_victory(self, world):
        """判定胜利（敌方全灭）。胜利后置状态为 cleared。"""
        won = (world.result == GameWorld.RESULT_WIN)
        if won:
            self.state = "cleared"
        return won

    def check_defeat(self, world):
        """判定失败（玩家阵亡）。失败后置状态为 failed。"""
        lost = (world.result == GameWorld.RESULT_LOSE)
        if lost:
            self.state = "failed"
        return lost

    def is_last_level(self):
        """是否为最后一关（第 15 关），用于触发通关动画。"""
        return self.current_level >= TOTAL_LEVELS

    def next_level(self):
        """推进到下一关（到达末关后不再增加），返回新关卡号。"""
        if self.current_level < TOTAL_LEVELS:
            self.current_level += 1
        return self.current_level
