"""
游戏实体：坦克基类、玩家坦克、敌人坦克
"""
import math
import random
import pygame
from constants import *
from bullets import Bullet
from vfx import draw_tank
from controls import ControlState, normalize_angle, angle_to_target
from powerup import (
    POWERUP_NONE, POWERUP_LASER, POWERUP_BOUNCE,
    POWERUP_SCATTER, POWERUP_SHIELD, POWERUP_DURATION,
    PERMA_BUFF_THRESHOLD,
)
from level_config import get_level_config


class BaseTank:
    """坦克基类，包含位置、方向、速度、血量、碰撞、绘制"""
    def __init__(self, x, y, color, hp, speed_val, owner="neutral"):
        # 位置（中心点坐标）
        self.x = float(x)
        self.y = float(y)
        self.color = color
        self.hp = hp
        self.max_hp = hp
        self.speed_val = float(speed_val)  # 像素/帧（按60FPS换算，直接乘dt）
        self.owner = owner  # player / enemy / neutral
        # 视觉风格标识（仅影响 draw，不改变碰撞/逻辑）。默认通用，子类/外部按车型赋值。
        self.tank_style = TANK_STYLE_STANDARD

        # 方向
        self.direction = DIR_UP
        # 连续炮塔角（弧度，屏幕坐标：up=-pi/2, right=0, down=pi/2, left=±pi）
        # 操作系统重构核心：转向/移动/开火全部以 turret_angle 为准
        self.turret_angle = -math.pi / 2.0
        self._blocked = False   # 上一帧移动是否被阻挡（供 AI 脱困）

        # 射击冷却
        self.fire_cooldown = 0.0
        self.fire_cooldown_max = PLAYER_FIRE_COOLDOWN if owner == "player" else ENEMY_FIRE_COOLDOWN

        # 状态
        self.alive = True
        self.invulnerable = 0.0  # 无敌时间（秒）
        # 道具系统（2026-08-23 叠加版）：powerup_buffs 为「修饰符集合」——
        # {道具类型: 剩余秒}，每个射击道具独立计时、可叠加组合。
        # 护盾为次数型防御（shield_active），与射击组合无语义交集，刻意独立。
        self.powerup_buffs = {}            # 射击道具集合（laser/bounce/scatter），各自动计时
        self.default_powerup = POWERUP_NONE  # 坦克初始道具（永久）；限时道具到期后恢复至此
        self.shield_active = False           # 护盾是否生效（单独标志，被击中一次后清除）
        self.track_anim = 0.0  # 履带动画计数器
        self.hit_flash = 0.0   # 受击白闪强度（0~1），命中时脉冲，用于视觉反馈

    def get_rect(self):
        """获取碰撞矩形（以坦克尺寸TANK_SIZE为边长）"""
        half = TANK_SIZE // 2
        return pygame.Rect(int(self.x - half), int(self.y - half), TANK_SIZE, TANK_SIZE)

    def is_alive(self):
        """坦克是否存活（供子弹碰撞检测使用）"""
        return self.alive

    def try_move(self, dx, dy, game_map, other_tanks=None):
        """尝试移动，dx/dy 为方向向量（-1/0/1 或归一化向量）。返回是否成功移动。
        2026-08-23 修复：输入方向先归一化——保证任意方向移速恒定（speed_val），
        消除「键盘斜向超速 1.414×」导致的同车不同速（双人 P1 键盘 vs P2 鼠标）。"""
        if not self.alive:
            return False
        speed = self.speed_val
        mag = math.hypot(dx, dy)
        if mag > 1e-6:
            ux, uy = dx / mag, dy / mag
        else:
            ux, uy = 0.0, 0.0
        new_x = self.x + ux * speed
        new_y = self.y + uy * speed
        # 边界/地形碰撞（轴分离：先判 X、再判 Y，Y 用最新的 new_x 判定，
        # 避免斜向撞墙拐角时坦克卡进墙体）
        if not game_map.can_tank_occupy(new_x, self.y, TANK_SIZE):
            new_x = self.x
        if not game_map.can_tank_occupy(new_x, new_y, TANK_SIZE):
            new_y = self.y
        # 与其他坦克碰撞
        if other_tanks:
            half = TANK_SIZE // 2
            new_rect = pygame.Rect(int(new_x - half), int(new_y - half), TANK_SIZE, TANK_SIZE)
            for t in other_tanks:
                if t is self or not t.alive:
                    continue
                if new_rect.colliderect(t.get_rect()):
                    return False
        moved = (new_x != self.x) or (new_y != self.y)
        self.x, self.y = new_x, new_y
        if moved:
            self.track_anim += 0.2
        return moved

    def set_direction_by_keydir(self, dx, dy):
        """根据WASD方向向量设置朝向"""
        if dx == 0 and dy == 0:
            return
        if abs(dx) > abs(dy):
            self.direction = DIR_RIGHT if dx > 0 else DIR_LEFT
        else:
            self.direction = DIR_DOWN if dy > 0 else DIR_UP

    def set_direction_toward(self, tx, ty):
        """根据目标点 (tx, ty) 设置朝向为四方向中的最近轴（双人模式 P2 鼠标控制用）。
        以位移绝对值更大的轴为主方向；位移过小（<0.1px）时不改变朝向。"""
        dx = tx - self.x
        dy = ty - self.y
        if abs(dx) < 0.1 and abs(dy) < 0.1:
            return
        if abs(dx) > abs(dy):
            self.direction = DIR_RIGHT if dx > 0 else DIR_LEFT
        else:
            self.direction = DIR_DOWN if dy > 0 else DIR_UP

    # ============ 连续炮塔角操作系统（2026-08-26）============
    def get_turret_vector(self):
        """返回当前炮塔方向的单位向量 (cos a, sin a)（屏幕坐标）。"""
        return (math.cos(self.turret_angle), math.sin(self.turret_angle))

    def _aim_toward(self, target_angle, dt):
        """把炮塔角向 target_angle 旋转，单帧最多转 TURRET_TURN_SPEED*dt 弧度。"""
        diff = normalize_angle(target_angle - self.turret_angle)
        step = TURRET_TURN_SPEED * dt
        if abs(diff) <= step:
            self.turret_angle = target_angle
        else:
            self.turret_angle += math.copysign(step, diff)

    def _move_along_turret(self, sign, game_map, other_tanks=None):
        """沿炮塔方向前进(sign=+1)/后退(sign=-1)。返回是否成功移动。"""
        vx = math.cos(self.turret_angle) * sign
        vy = math.sin(self.turret_angle) * sign
        moved = self.try_move(vx, vy, game_map, other_tanks)
        self._blocked = (not moved)
        return moved

    def _sync_direction(self):
        """把连续炮塔角映射回最近的四方向，供遗留逻辑/绘制兼容。"""
        a = self.turret_angle % math.tau
        best, bestd = DIR_UP, 1e9
        for d, vec in DIR_VECTORS.items():
            ba = math.atan2(vec[1], vec[0]) % math.tau
            diff = abs(normalize_angle(a - ba))
            if diff < bestd:
                bestd, best = diff, d
        self.direction = best

    def apply_control(self, control, dt, game_map, other_tanks=None):
        """统一应用控制意图（人类与 AI 共用此路径）：
        - turn: 按键旋转（±1）
        - aim_angle: 鼠标/AI 绝对瞄准角
        - throttle: 沿炮塔前进/后退
        不直接处理开火（开火由上层 world 在 can_fire 后调用 shoot），
        保证人类与 AI 的开火判定完全一致。"""
        if not self.alive:
            return
        if control.turn:
            self.turret_angle += control.turn * TURRET_TURN_SPEED * dt
        if control.aim_angle is not None:
            self._aim_toward(control.aim_angle, dt)
        if control.throttle:
            self._move_along_turret(control.throttle, game_map, other_tanks)
        self._sync_direction()

    def heal(self, amount=HEAL_AMOUNT):
        """恢复血量（不超过上限）。"""
        if not self.alive:
            return
        self.hp = min(self.max_hp, self.hp + amount)

    def can_fire(self):
        return self.alive and self.fire_cooldown <= 0.0

    def fire(self):
        """调用后设置冷却，返回炮口位置 + 单位方向向量 + 炮塔角（连续角度）"""
        if not self.can_fire():
            return None
        self.fire_cooldown = self.fire_cooldown_max
        vx = math.cos(self.turret_angle)
        vy = math.sin(self.turret_angle)
        half = TANK_SIZE // 2
        # 炮口略超出坦克碰撞半径，避免子弹出生瞬间误判命中发射者自身
        bx = self.x + vx * (half + 6)
        by = self.y + vy * (half + 6)
        return (bx, by, vx, vy, self.turret_angle)

    def shoot(self, bullet_speed=None):
        """根据当前激活道具集合生成子弹（2026-08-23 叠加版），返回 Bullet 列表。
        叠加规则（修饰符模型）：道具集合中每个修饰符叠加进子弹能力——
          - 激光(LASER)：子弹为激光（纯激光 = 即时光束贯穿；叠加弹射 = 飞行激光撞墙弹射）；
          - 弹射(BOUNCE)：撞墙随机弹射（不原路返回），叠加时使激光失去穿墙、获得弹射；
          - 散射(SCATTER)：发射 3 发扇形（±15°），与激光/弹射任意叠加。
        组合示例：散射激光=3束扇形光束；可弹射激光=飞行激光撞墙随机弹；
        散射+弹射=3发弹射弹；三件套=3束可弹射激光。
        护盾不改变子弹（只保护自身），不参与射击组合。
        内部调用 fire() 设置射击冷却；冷却未就绪时返回空列表。
        bullet_speed 可为单发自定义速度（如第1关敌人降速）。"""
        f = self.fire()
        if f is None:
            return []
        bx, by, vx, vy, _angle = f
        active = self.get_active_powerups()
        speed = bullet_speed if bullet_speed is not None else BULLET_SPEED
        bullets = []

        has_laser = POWERUP_LASER in active
        has_bounce = POWERUP_BOUNCE in active
        has_scatter = POWERUP_SCATTER in active

        # 类型合成：激光 → LASER；弹射 → BOUNCE；纯散射 → SCATTER（保留蓝色视觉）；
        # 能力合成：激光+弹射 → 弹射优先（撞墙弹，不穿墙）；纯激光 → 穿墙
        if has_laser:
            kind = Bullet.LASER
        elif has_bounce:
            kind = Bullet.BOUNCE
        elif has_scatter:
            kind = Bullet.SCATTER
        else:
            kind = Bullet.NORMAL
        pierce_walls = has_laser and not has_bounce
        bounces = has_bounce

        # 数量合成：散射 → 3 发扇形（±15°）；否则单发。基准角取连续炮塔角。
        if has_scatter:
            base = self.turret_angle
            for deg in (-15, 0, 15):
                rad = base + math.radians(deg)
                nvx, nvy = math.cos(rad), math.sin(rad)
                bullets.append(Bullet(bx, by, nvx, nvy, self.owner,
                                      kind=kind, speed=speed, owner=self,
                                      ricochet_chance=RICOCHET_CHANCE,
                                      pierce_walls=pierce_walls, bounces=bounces))
        else:
            bullets.append(Bullet(bx, by, vx, vy, self.owner,
                                  kind=kind, speed=speed, owner=self,
                                  ricochet_chance=RICOCHET_CHANCE,
                                  pierce_walls=pierce_walls, bounces=bounces))

        return bullets

    def take_damage(self, dmg=1, ignore_invulnerable=False):
        """受到伤害，返回是否真正扣血。
        护盾（shield_active）免疫一次伤害，被击中后清除。
        ignore_invulnerable=True 时无视无敌帧（子弹命中友军伤害用，增加策略深度）。"""
        if not self.alive:
            return False
        if self.invulnerable > 0 and not ignore_invulnerable:
            return False
        # 护盾优先抵消（免疫一次伤害）；仅清除护盾状态，
        # 保留当前生效的射击道具（含永久初始道具，不丢失）
        if self.shield_active:
            self.shield_active = False
            self.invulnerable = 0.3
            return False  # 免疫伤害
        self.hp -= dmg
        self.invulnerable = PLAYER_INVULN_TIME   # 受伤害后一段无敌时间
        self.hit_flash = 1.0   # 受击白闪脉冲（draw 层叠加白光）
        if self.hp <= 0:
            self.alive = False
            self.hp = 0
        return True

    # -------------------- 道具系统（2026-08-23 叠加版）--------------------
    def apply_powerup(self, powerup_type):
        """施加道具（叠加版）：射击道具加入/刷新集合，各自独立计时。
        - 护盾为独立状态（次数型），不进入射击集合，仅置位 shield_active；
        - 其余射击道具（激光/弹射/散射）写入 powerup_buffs[type] = POWERUP_DURATION，
          刷新该道具计时但不清除其它已激活道具 —— 支持多道具叠加组合。"""
        if powerup_type == POWERUP_SHIELD:
            self.shield_active = True  # 次数型，不参与射击组合
            return
        self.powerup_buffs[powerup_type] = POWERUP_DURATION

    def get_active_powerup(self):
        """兼容旧接口：返回「最后刷新的」射击道具类型（无则 POWERUP_NONE）。
        叠加系统主用 get_active_powerups()；此方法保留供 HUD 兼容。"""
        active = self.get_active_powerups()
        return active[-1] if active else POWERUP_NONE

    def get_active_powerups(self):
        """返回当前生效的射击道具集合（按激活顺序，去重）。
        - 限时道具：powerup_buffs 中剩余时间 > 0 的；
        - 初始道具：default_powerup 以 PERMA_BUFF_THRESHOLD 记入集合（永久生效）；
        - 返回 list（有序），供 shoot() 组合子弹、HUD 显示叠加。"""
        result = []
        for t, remain in self.powerup_buffs.items():
            if remain > 0 or remain >= PERMA_BUFF_THRESHOLD:
                if t not in result:
                    result.append(t)
        return result

    @staticmethod
    def _expand_init(item):
        """把初始道具标识拆解为叠加集合元素：
        "bounce_scatter"（KZY 复合初始道具）→ [BOUNCE, SCATTER]；其余单元素列表。"""
        if item == "bounce_scatter":
            return [POWERUP_BOUNCE, POWERUP_SCATTER]
        if item:
            return [item]
        return []

    def update(self, dt):
        if self.fire_cooldown > 0:
            self.fire_cooldown -= dt
        if self.invulnerable > 0:
            self.invulnerable -= dt
        if self.hit_flash > 0:
            self.hit_flash = max(0.0, self.hit_flash - dt / 0.18)
        # 注意：道具 buff 的计时统一由 PowerUpManager 负责递减与到期清除，
        # 这里不再处理，避免重复扣时。

    def draw(self, screen, arena_x, arena_y):
        if not self.alive:
            return
        sx = arena_x + self.x
        sy = arena_y + self.y

        # 无敌闪烁（仅隐藏，不绘制）
        if self.invulnerable > 0 and int(self.invulnerable * 20) % 2 == 0:
            return

        # 预烘焙坦克精灵（含渐变 / 投影 / 描边 / 炮管高光），命中时叠加白闪；
        # 履带齿纹按 track_anim 相位切换两帧，形成滚动动画；
        # 以连续炮塔角 angle 绘制（旋转预烘焙精灵，量化缓存、零每帧分配）
        draw_tank(screen, sx, sy, self.color, self.direction, self.hit_flash,
                  anim_frame=int(self.track_anim) & 1, style=self.tank_style,
                  angle=self.turret_angle)

        # 护盾圈（动态绘制，薄环）
        if self.shield_active:
            turret_r = int(TANK_SIZE * 0.32)
            pygame.draw.circle(screen, COLOR_YELLOW, (int(sx), int(sy)),
                               turret_r + 6, width=2)


class PlayerTank(BaseTank):
    """玩家坦克：轻型侦察车/其他选择的坦克"""
    def __init__(self, x, y, tank_name):
        info = TANK_DATA.get(tank_name, TANK_DATA["轻型侦察车"])
        super().__init__(x, y, info["color"], info["hp"],
                         info["speed_val"] * TANK_SPEED_SCALE, owner="player")
        self.tank_name = tank_name
        # 视觉风格：按车型映射到差异化 style（敌人/未匹配车保持 standard）
        self.tank_style = TANK_STYLE_BY_NAME.get(tank_name, TANK_STYLE_STANDARD)
        # 初始道具（持续整局，以 PERMA_BUFF_THRESHOLD 记入叠加集合，永久生效）
        init_item = info.get("init_item")
        self.default_powerup = init_item if init_item else POWERUP_NONE
        for it in self._expand_init(init_item):
            self.powerup_buffs[it] = PERMA_BUFF_THRESHOLD  # 持续整局（永久 buff）


class EnemyTank(BaseTank):
    """敌人坦克：带AI状态机"""
    # AI 状态
    STATE_PATROL = "patrol"
    STATE_CHASE = "chase"
    STATE_WAIT = "wait"

    def __init__(self, x, y, level):
        hp = get_enemy_hp(level)
        cfg = get_level_config(level)
        speed_val = cfg["enemy_speed"] * TANK_SPEED_SCALE
        super().__init__(x, y, (220, 90, 90), hp, speed_val, owner="enemy")
        self.level = level
        self.ai_state = EnemyTank.STATE_PATROL
        self.ai_timer = 0.0
        self.patrol_dir = DIR_DOWN
        self.last_hit_by = None   # 最后命中它的玩家坦克（用于双人 vsAI 计分归属）
        # 第1关攻击频率等全部由 level_config 的 enemy_fire_cd 直接指定
        self.fire_cooldown_max = cfg["enemy_fire_cd"] * ENEMY_FIRE_CD_SCALE
        # 生成点出生保护
        self.invulnerable = 1.2

    def decide_control(self, dt, target, game_map, other_tanks=None):
        """产出 ControlState，与人类输入共用 apply_control —— 实现「AI 操作逻辑与人类一致」。
        - 始终瞄准最近目标（apply_control 会按限速转向）；
        - 距离过远则前进靠近；卡墙则旋转脱困；
        - 对准（角度差小）且有视线、冷却就绪时按概率开火。"""
        ctrl = ControlState()
        if not self.alive or not target.alive:
            return ctrl
        dx = target.x - self.x
        dy = target.y - self.y
        dist = math.hypot(dx, dy)
        desired = math.atan2(dy, dx)          # 屏幕坐标角度
        ctrl.aim_angle = desired               # 瞄准目标
        if dist > ENEMY_AI_KEEP_DIST:
            ctrl.throttle = 1                  # 靠近
        # 卡墙脱困：上一帧想动却没动 → 旋转一下再尝试
        if self._blocked:
            if not hasattr(self, "_unstick"):
                self._unstick = 1.0
            ctrl.turn = self._unstick
            if random.random() < 0.04:
                self._unstick *= -1.0
        # 开火判定：对准 + 视线无阻挡 + 冷却就绪（概率模拟命中率）
        diff = abs(normalize_angle(desired - self.turret_angle))
        if diff < ENEMY_AI_FIRE_CONE and self.can_fire() and random.random() < ENEMY_AIM_CHANCE:
            if self._has_line_of_sight(target, game_map):
                ctrl.fire = True
        return ctrl

    def _has_line_of_sight(self, player, game_map):
        """沿当前炮塔朝向，检查中间是否有钢墙/砖墙阻挡视线。"""
        vx, vy = self.get_turret_vector()
        t = 0.0
        step = 8.0
        max_t = ENEMY_DETECT_RANGE
        while t < max_t:
            cx = self.x + vx * t
            cy = self.y + vy * t
            t += step
            # 到了玩家附近就算通
            if abs(cx - player.x) < TANK_SIZE * 0.5 and abs(cy - player.y) < TANK_SIZE * 0.5:
                return True
            if not game_map.point_passable_for_bullet(cx, cy):
                return False
        return False
