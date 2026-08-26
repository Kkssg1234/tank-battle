"""
统一控制接口（2026-08-26 重构核心）

把所有「操作意图」抽象为 ControlState：
  - turn      : -1 / 0 / +1   （A/D 这类按键旋转炮塔，单位由 apply_control 乘速度）
  - aim_angle : float|None      （鼠标拖拽瞄准：目标炮塔角（弧度，屏幕坐标）；None 表示无瞄准输入）
  - throttle  : -1 / 0 / +1      （-1 后退 / +1 前进，沿炮塔方向）
  - fire      : bool             （开火意图）

人类输入层（main.py / screens.py）与 AI（EnemyTank.decide_control）都产出 ControlState，
再由 BaseTank.apply_control() 统一应用 —— 从而保证「AI 操作逻辑与人类玩家保持一致」。

角度约定（与整个项目一致，屏幕 y 轴向下）：
  up   = -pi/2,  right = 0,  down = +pi/2,  left = +pi  (-pi)
  单位方向向量 = (cos a, sin a)
"""
import math


class ControlState:
    __slots__ = ("turn", "aim_angle", "throttle", "fire")

    def __init__(self, turn=0.0, aim_angle=None, throttle=0, fire=False):
        self.turn = turn
        self.aim_angle = aim_angle
        self.throttle = throttle
        self.fire = fire

    def reset(self):
        self.turn = 0.0
        self.aim_angle = None
        self.throttle = 0
        self.fire = False

    def __repr__(self):
        return (f"ControlState(turn={self.turn}, aim={self.aim_angle}, "
                f"thr={self.throttle}, fire={self.fire})")


def normalize_angle(a):
    """把任意角度规整到 (-pi, pi]"""
    a = a % (math.tau)
    if a > math.pi:
        a -= math.tau
    return a


def angle_to_target(from_x, from_y, to_x, to_y):
    """从 (from_x,from_y) 指向 (to_x,to_y) 的屏幕坐标角度（弧度）"""
    return math.atan2(to_y - from_y, to_x - from_x)


def empty_control():
    return ControlState()
