"""
子弹系统：普通/激光/弹射/散射
"""
import math
import random
import pygame
from constants import *
from vfx import draw_glow, get_ring


class Bullet:
    """子弹：位置、速度向量、所有者、类型"""
    NORMAL = "normal"
    LASER = "laser"
    BOUNCE = "bounce"
    SCATTER = "scatter"

    def __init__(self, x, y, vx, vy, owner_type, kind=NORMAL, damage=BULLET_DAMAGE,
                 speed=BULLET_SPEED, owner=None, ricochet_chance=0.0,
                 pierce_walls=None, bounces=None, enemy_bounce=False,
                 max_enemy_bounces=ENEMY_BOUNCE_MAX):
        self.x = float(x)
        self.y = float(y)
        # vx, vy 为方向向量（单位向量）
        mag = math.hypot(vx, vy) or 1.0
        self.vx = vx / mag
        self.vy = vy / mag
        # 方向角（度）：与 (vx, vy) 保持同步，供 _calculate_reflection 等角度逻辑使用
        # 运动向量约定为 (cos θ, -sin θ)，故 θ = atan2(-vy, vx)
        self.direction = math.degrees(math.atan2(-self.vy, self.vx))
        # 发射者引用（Tank 实例），用于友军伤害判定；owner_type 由 owner 推导以兼容旧逻辑
        self.owner = owner
        self.owner_type = owner.owner if (owner is not None) else owner_type
        # 子弹类型：normal / laser / bounce / scatter
        self.bullet_type = kind
        self.damage = damage
        self.speed = float(speed)  # 飞行速度（像素/秒），支持每发自定义（如第1关敌人降速）
        self.alive = True
        # 能力修饰（2026-08-23 道具叠加系统）：取代"单一类型"判定——
        # pierce_walls：撞墙是否穿透（激光独有；叠加弹射时失效，改撞墙弹射）
        # bounces：撞墙是否随机弹射（来自弹射道具）
        # beam_mode：即时光束模式（纯激光 = 贯穿全图直线；叠加弹射时退化为飞行激光）
        if pierce_walls is None:
            pierce_walls = (kind == Bullet.LASER and bounces is not True)
        if bounces is None:
            bounces = (kind == Bullet.BOUNCE)
        self.pierce_walls = bool(pierce_walls)
        self.bounces = bool(bounces)
        self.beam_mode = (kind == Bullet.LASER and not self.bounces)
        # 弹射计数：已弹射次数 & 最大弹射次数（仅 bounces=True 才允许弹射）
        self.bounce_count = 0
        self.max_bounces = 2 if self.bounces else 0
        self.penetration = LASER_PIERCE_ENEMIES if kind == Bullet.LASER else 1  # 激光穿透数（验收：命中 3 个敌人后销毁）
        self.hit_tanks = set()  # 激光避免重复伤害同一坦克
        self.radius = BULLET_SIZE // 2 + 1  # 碰撞半径（3.4/3.5 圆-矩形碰撞）
        # 跳弹机制：子弹击中坦克时按 ricochet_chance 概率弹开（不造成伤害、随机偏转、
        # 偏转后保留杀伤力且不区分敌我）。0 表示普通子弹不参与跳弹。
        self.ricochet_chance = float(ricochet_chance)
        self.ricocheted = False   # 是否已发生过跳弹（跳弹后不区分敌我，含发射者自身）
        # 敌人反弹（跳弹游骑兵专属）：命中敌人后弹向其它目标，连锁造成伤害
        self.enemy_bounce = bool(enemy_bounce)
        self.enemy_bounce_count = 0
        self.max_enemy_bounces = int(max_enemy_bounces)
        self.trail = []  # 尾迹
        self.life = 0.0
        # 超时时间：保证慢速子弹也能飞越整个竞技场宽度（ARENA_W / speed + 余量）
        self.max_life = max(4.0, ARENA_W / self.speed + 0.5)

        # 激光直线光束（2026-08-23）：发射瞬间从炮口贯穿全图的完整直线。
        # start 为炮口起点；beam_end 为沿方向与竞技场边界相交的终点；
        # beam_hits 记录被光束命中的坦克（供外层生成命中特效）。
        self.start_x = float(x)
        self.start_y = float(y)
        self.beam_end = None
        self.beam_hits = []
        self._beam_resolved = False

        # 枪口火光（技术美术增强：发射瞬间在炮口生成辉光，复用粒子系统）
        self._spawn_muzzle_flash()

    def update(self, dt, game_map, all_tanks=None):
        """每帧推进子弹。
        规范 5 接口：bullet.update(game_map, all_tanks)
        返回被击中的坦克（未命中/未传入 all_tanks 时返回 None），供外层生成命中特效。"""
        if not self.alive:
            return None
        self.life += dt
        # 激光：即时光束（纯激光，beam_mode=True）——生命周期在此管理（LASER_BEAM_LIFE 后销毁）；
        # 命中判定由 GameWorld 在子弹循环中显式调用 _resolve_beam（传入 all_tanks），
        # 避免双人模式 update(all_tanks=None) 提前 resolve 导致无法命中。
        # 叠加弹射的激光（beam_mode=False）为飞行激光，走下方常规移动/弹射逻辑。
        if self.bullet_type == Bullet.LASER and self.beam_mode:
            if self.life > LASER_BEAM_LIFE:
                self.alive = False
            return None
        if self.life > self.max_life:
            self.alive = False
            return None
        dist = self.speed * dt
        # 分步移动，避免穿墙（按每步不超过 TILE_SIZE/2）
        step_len = max(1.0, TILE_SIZE * 0.45)
        steps = max(1, int(math.ceil(dist / step_len)))
        sub = dist / steps
        for _ in range(steps):
            if not self.alive:
                return None
            nx = self.x + self.vx * sub
            ny = self.y + self.vy * sub

            # 3.1 移动与边界：超出 800×600 边界
            if (nx < 0 or ny < 0 or nx > BULLET_BOUNDS_W or ny > BULLET_BOUNDS_H):
                if self.bounces and self.bounce_count < self.max_bounces:
                    # 弹射子弹：在边界随机弹射（仍计一次弹射，并生成白色粒子）
                    self.bounce_count += 1
                    if nx < 0 or nx > BULLET_BOUNDS_W:
                        # 撞左右边：水平反转基准角 + 随机偏转
                        self.direction = self._random_bounce_angle(
                            (180 - self.direction) % 360, self.direction)
                        nx = max(1.0, min(BULLET_BOUNDS_W - 1.0, nx))
                    if ny < 0 or ny > BULLET_BOUNDS_H:
                        # 撞上下边：垂直反转基准角 + 随机偏转
                        self.direction = self._random_bounce_angle(
                            (-self.direction) % 360, self.direction)
                        ny = max(1.0, min(BULLET_BOUNDS_H - 1.0, ny))
                    self._sync_vector()
                    self.x, self.y = nx, ny
                    self._spawn_bounce_particle()
                    continue
                else:
                    # 普通/激光/散射：出界直接销毁
                    self.alive = False
                    return None

            # 3.2 墙壁碰撞
            wall = game_map.bullet_hit_tile(nx, ny, self)
            if wall is not None:
                tile_type, tile_col, tile_row = wall
                if self.pierce_walls:
                    # 激光（纯激光，无弹射）：穿透所有墙壁，不销毁，继续飞行
                    pass
                elif self.bounces and self.bounce_count < self.max_bounces:
                    # 弹射（含可弹射激光）：随机角度弹射，不原路返回
                    wall_rect = game_map.get_tile_rect(tile_col, tile_row)
                    base_angle = self._reflection_base_angle(wall_rect)
                    self.direction = self._random_bounce_angle(base_angle, self.direction)
                    self._sync_vector()
                    self.bounce_count += 1
                    # 将子弹沿新方向推出 5 像素，防止卡在墙内
                    rad = math.radians(self.direction)
                    self.x += math.cos(rad) * 5
                    self.y += -math.sin(rad) * 5
                    # 反弹点生成白色粒子（验收 4：提醒玩家跳弹轨迹，避免自伤）
                    self._spawn_bounce_particle()
                    # 弹射子弹可击碎砖墙
                    if tile_type == TILE_BRICK:
                        game_map.destroy_tile(tile_col, tile_row)
                    return None
                else:
                    # 普通/散射：撞墙消失（砖墙被击碎，钢墙不可破）
                    if tile_type == TILE_BRICK:
                        game_map.destroy_tile(tile_col, tile_row)
                    self.alive = False
                    return None

            # 记录尾迹 & 更新位置
            self.trail.append((self.x, self.y))
            if len(self.trail) > (5 if self.bullet_type != Bullet.LASER else 15):
                self.trail.pop(0)
            self.x, self.y = nx, ny

        # 3.4 坦克碰撞（友军伤害核心）：命中任何坦克一律扣血，无视无敌帧
        if all_tanks is not None and self.alive:
            return self.collide_tanks(all_tanks)
        return None

    def _reflection_base_angle(self, wall_rect):
        """返回镜面反射的基准角（度）：左右边碰撞 -> 水平反转 (180 - dir)；
        上下边碰撞 -> 垂直反转 (-dir)。随机弹射在此基准角上叠加偏转。"""
        dx = self.x - wall_rect.centerx
        dy = self.y - wall_rect.centery
        if abs(dx) > abs(dy):
            return (180 - self.direction) % 360
        else:
            return (-self.direction) % 360

    def _random_bounce_angle(self, base_angle, incoming_dir):
        """弹射方向随机化（2026-08-23 道具叠加系统）：
        在镜面反射基准角 ± BOUNCE_SPREAD 内均匀随机取新方向，且与入射方向的
        夹角不小于 BOUNCE_MIN_DEVIATION —— 数学上保证新方向偏离入射方向 ≥
        max(180°-SPREAD, MIN_DEVIATION)，永不沿入射路径原路返回。
        取 8 次采样保证可终止；全部失败则回退到基准角（物理反射，仍非原路）。"""
        for _ in range(8):
            new_dir = (base_angle + random.uniform(-BOUNCE_SPREAD, BOUNCE_SPREAD)) % 360
            diff = abs(((new_dir - incoming_dir + 180) % 360) - 180)
            if diff >= BOUNCE_MIN_DEVIATION:
                return new_dir
        return base_angle

    def _sync_vector(self):
        """将 self.direction（度）同步回运动向量 (vx, vy)。
        运动约定：vx = cos θ, vy = -sin θ（屏幕 y 轴向下）。"""
        rad = math.radians(self.direction)
        self.vx = math.cos(rad)
        self.vy = -math.sin(rad)

    def _sync_direction(self):
        """将运动向量 (vx, vy) 同步回方向角 self.direction（度）。
        与 _sync_vector 互逆：θ = atan2(-vy, vx)（屏幕 y 轴向下）。"""
        self.direction = math.degrees(math.atan2(-self.vy, self.vx)) % 360

    def _circle_rect_collision(self, cx, cy, radius, rect):
        """3.5 圆-矩形碰撞检测：计算圆心到矩形最近点的距离，小于半径即碰撞。"""
        closest_x = max(rect.left, min(cx, rect.right))
        closest_y = max(rect.top, min(cy, rect.bottom))
        dx = cx - closest_x
        dy = cy - closest_y
        return (dx * dx + dy * dy) < (radius * radius)

    def _spawn_muzzle_flash(self):
        """技术美术增强：发射瞬间在炮口生成辉光粒子（橙黄），复用粒子系统。
        由 __init__ 调用，坐标为竞技场内部坐标。"""
        ang = math.radians(self.direction)
        mx = self.x + math.cos(ang) * (TANK_SIZE * 0.5 + 4)
        my = self.y - math.sin(ang) * (TANK_SIZE * 0.5 + 4)
        for _ in range(5):
            a = ang + random.uniform(-0.5, 0.5)
            sp = random.uniform(40, 140)
            sx = mx + math.cos(a) * 3
            sy = my - math.sin(a) * 3
            spawn_particle(sx, sy, (255, 230, 140), random.uniform(2, 4),
                           max_life=0.22)

    # ==================== 激光直线光束（2026-08-23）====================
    def _compute_beam_end(self):
        """计算光束终点：从炮口 (start_x, start_y) 沿 (vx, vy) 直线延伸，
        与竞技场边界 [0, ARENA_W]×[0, ARENA_H] 求交（贯穿全图）。"""
        x0, y0 = self.start_x, self.start_y
        vx, vy = self.vx, self.vy
        t = 0.0
        if vx > 0:
            t = max(t, (ARENA_W - x0) / vx)
        elif vx < 0:
            t = max(t, (0.0 - x0) / vx)
        if vy > 0:
            t = max(t, (ARENA_H - y0) / vy)
        elif vy < 0:
            t = max(t, (0.0 - y0) / vy)
        if t <= 0:
            t = 1.0  # 兜底（方向向量异常时）
        return (x0 + vx * t, y0 + vy * t)

    def _segment_hits_tank(self, tank):
        """判断光束线段（炮口→终点）是否经过坦克矩形：
        用坦克中心到线段的最短距离 < 0.75×TANK_SIZE 判定（覆盖矩形对角线方向）。"""
        x0, y0 = self.start_x, self.start_y
        x1, y1 = self.beam_end
        px, py = tank.x, tank.y
        dx, dy = x1 - x0, y1 - y0
        length2 = dx * dx + dy * dy
        if length2 <= 0:
            return False
        t = ((px - x0) * dx + (py - y0) * dy) / length2
        t = max(0.0, min(1.0, t))
        cx, cy = x0 + t * dx, y0 + t * dy
        dist2 = (px - cx) ** 2 + (py - cy) ** 2
        return dist2 < (TANK_SIZE * 0.75) ** 2

    def _resolve_beam(self, game_map, all_tanks):
        """激光即时光束：发射瞬间一次性判定贯穿路径上的坦克。
        - 光束沿直线贯穿整个竞技场（穿透所有墙壁/障碍，原激光语义）；
        - 命中路径上所有坦克，按距炮口由近及远排序，穿透 LASER_PIERCE_ENEMIES 个后停止伤害（保留平衡）；
        - 命中无视无敌帧、保留 hit_tanks 去重；命中列表存入 beam_hits 供外层生成特效。"""
        if self._beam_resolved:
            return  # 幂等：只解析一次（beam_end 由 draw 兜底计算）
        self._beam_resolved = True
        self.beam_end = self._compute_beam_end()
        if all_tanks is None:
            return
        hits = []
        for tank in all_tanks:
            if tank is self.owner:
                # 保持双人规则：激光不自伤（原 _apply_bullet_to_tank 中
                # 自己打自己只有 bounce 才伤，激光不满足）
                continue
            if not tank.is_alive() or id(tank) in self.hit_tanks:
                continue
            if self._segment_hits_tank(tank):
                hits.append(tank)
        hits.sort(key=lambda t: (t.x - self.start_x) ** 2 + (t.y - self.start_y) ** 2)
        for tank in hits[:self.penetration]:
            tank.take_damage(self.damage, ignore_invulnerable=True)
            self.hit_tanks.add(id(tank))
            self.beam_hits.append(tank)

    def _spawn_bounce_particle(self):
        """验收 4：每次反弹在反弹点生成白色临时粒子，提醒玩家注意跳弹轨迹。
        半径 2-4 像素、寿命 5 帧（约 0.083s），逐帧缩小并淡出。"""
        r = random.uniform(BOUNCE_PARTICLE_MIN_R, BOUNCE_PARTICLE_MAX_R)
        spawn_particle(self.x, self.y, BOUNCE_PARTICLE_COLOR, r,
                       max_life=BOUNCE_PARTICLE_LIFE_FRAMES / 60.0)

    def try_ricochet(self, hit_tank=None):
        """子弹击中坦克时尝试触发跳弹。

        触发条件：ricochet_chance > 0 且随机命中阈值（激光不参与跳弹）。
        触发后：
          - 不发生伤害；
          - 飞向全新随机方向（保留速度与杀伤力）；
          - 解除所有者归属并置 ricocheted 标志 → 偏转后不区分敌我（含发射者自身）；
          - 将被弹开的坦克加入 hit_tanks，避免下一帧立即重叠重复触发；
          - 生成火花 + 环形闪光反馈（视觉提示玩家跳弹发生）。
        返回 True 表示发生了跳弹（调用方应跳过伤害判定），否则 False。"""
        if not self.alive or self.bullet_type == Bullet.LASER:
            return False
        if self.ricochet_chance <= 0:
            return False
        if random.random() >= self.ricochet_chance:
            return False
        # 1) 随机新方向（0~359 度）
        self.direction = random.uniform(0, 360)
        self._sync_vector()
        # 2) 跳弹后不区分敌我：解除归属，使双人对战自伤/友伤生效
        self.ricocheted = True
        self.owner = None
        # 3) 防止与当前被弹开的坦克下一帧重叠重复触发
        if hit_tank is not None:
            self.hit_tanks.add(id(hit_tank))
        # 4) 视觉反馈：火花粒子 + 环形闪光
        self._spawn_ricochet_feedback()
        return True

    def _spawn_ricochet_feedback(self):
        """跳弹反馈：火花粒子（橙黄）+ 环形闪光（由 RICOCHET_EFFECTS 驱动）。"""
        # 火花：数枚橙黄小粒子四散
        for _ in range(8):
            ang = random.uniform(0, math.tau)
            sp = random.uniform(60, 200)
            sx = self.x + math.cos(ang) * 4
            sy = self.y + math.sin(ang) * 4
            spawn_particle(sx, sy, RICOCHET_BULLET_COLOR, random.uniform(2, 4),
                           max_life=0.35)
        # 环形闪光（明确提示「弹开」事件）
        spawn_ricochet_effect(self.x, self.y, RICOCHET_BULLET_COLOR)

    def try_deflect(self, tank):
        """防御型反弹（高血量坦克被动）：敌方子弹命中本坦克时，按坦克自身
        deflect_chance 概率将其「弹开」——不发生伤害、方向被镜面反弹脱离坦克并转为中性
        （不区分敌我，且记入 hit_tanks 避免立即重复命中本体）。返回 True 表示被弹开。"""
        if not self.alive or self.ricocheted:
            return False
        chance = getattr(tank, "deflect_chance", 0.0)
        if chance <= 0:
            return False
        # 仅对「敌对子弹」生效：不反弹己方子弹，也不重复反弹已中性的子弹
        if self.owner_type is not None and tank.owner == self.owner_type:
            return False
        if random.random() >= chance:
            return False
        # 反弹方向：沿「坦克→子弹」连线向外弹开（即反射来袭方向）
        ang = math.atan2(-(self.y - tank.y), self.x - tank.x)  # 屏幕坐标：vx=cos, vy=-sin
        self.direction = math.degrees(ang) % 360
        self._sync_vector()
        self.ricocheted = True
        self.owner = None
        self._spawn_ricochet_feedback()
        # 推离坦克，避免重叠重复触发
        self.x += self.vx * (TANK_SIZE * 0.6)
        self.y += self.vy * (TANK_SIZE * 0.6)
        return True

    def handle_enemy_bounce(self, tank, all_tanks=None):
        """敌人反弹（跳弹游骑兵）：命中坦克造成伤害后，重定向飞向最近的其他存活坦克，
        继续飞行；达到最大反弹次数则返回 'dead'（调用方应销毁子弹）。
        返回 'alive'（继续飞行）或 'dead'（应销毁）。"""
        if not self.enemy_bounce:
            return 'dead'
        if self.enemy_bounce_count >= self.max_enemy_bounces:
            return 'dead'
        nxt = None
        best_d = float('inf')
        if all_tanks:
            for t in all_tanks:
                if not t.is_alive() or t is tank or id(t) in self.hit_tanks:
                    continue
                # 不主动撞向同阵营（避免自伤），中性化后方可命中任意目标
                if self.owner_type is not None and t.owner == self.owner_type:
                    continue
                d = (t.x - self.x) ** 2 + (t.y - self.y) ** 2
                if d < best_d:
                    best_d = d
                    nxt = t
        if nxt is not None:
            ang = math.atan2(-(nxt.y - self.y), nxt.x - self.x)
            self.direction = math.degrees(ang) % 360
        else:
            self.direction = random.uniform(0, 360)
        self._sync_vector()
        self.enemy_bounce_count += 1
        self.hit_tanks.add(id(tank))
        # 推离被击中坦克，避免重叠重复命中
        self.x += self.vx * (TANK_SIZE * 0.7)
        self.y += self.vy * (TANK_SIZE * 0.7)
        self._spawn_ricochet_feedback()
        return 'alive'

    def collide_tanks(self, all_tanks):
        """3.4 坦克碰撞（友军伤害核心）。
        子弹击中任何坦克（敌人/队友/自己）一律扣血；子弹命中无视无敌帧（增加策略深度）。
        - 跳弹(ricochet)：命中瞬间按概率弹开（不造成伤害，随机偏转，保留杀伤力、不区分敌我）。
        - 激光(laser)：可穿透，penetration 每命中 -1，<=0 时销毁；hit_tanks 去重避免重复伤害同一坦克。
        - 其他类型：命中即销毁。
        返回被击中的坦克实例（未命中返回 None），供调用方生成命中特效。"""
        if not self.alive:
            return None
        for tank in all_tanks:
            if not tank.is_alive():
                continue
            if id(tank) in self.hit_tanks:
                continue
            if self._circle_rect_collision(self.x, self.y, self.radius, tank.get_rect()):
                # 1) 跳弹（全局随机）：命中瞬间按概率弹开（不造成伤害，随机偏转）
                if self.try_ricochet(tank):
                    return None  # 跳弹后子弹存活并飞向随机方向，交由后续帧继续碰撞
                # 2) 防御反弹（高血量坦克受击）：按自身 deflect_chance 概率将敌方子弹弹开（无伤害）
                if self.try_deflect(tank):
                    return None
                # 3) 跳弹游骑兵：敌人反弹 —— 命中造成伤害后继续飞向其它坦克
                if self.enemy_bounce:
                    tank.take_damage(self.damage, ignore_invulnerable=True)
                    self._spawn_ricochet_feedback()
                    res = self.handle_enemy_bounce(tank, all_tanks)
                    if res == 'dead':
                        self.alive = False
                    return tank  # 命中已登记（供外层生成命中特效），子弹继续存活
                # 4) 关键：无论击中谁（含 owner 自己）都造成伤害，无视无敌帧
                tank.take_damage(self.damage, ignore_invulnerable=True)
                if self.bullet_type == Bullet.LASER:
                    self.hit_tanks.add(id(tank))
                    self.penetration -= 1
                    if self.penetration <= 0:
                        self.alive = False
                else:
                    self.alive = False
                return tank
        return None

    def get_rect(self):
        s = BULLET_SIZE
        return pygame.Rect(int(self.x - s / 2), int(self.y - s / 2), s, s)

    def draw(self, screen, arena_x, arena_y):
        if not self.alive:
            return
        # 激光即时光束：从炮口贯穿全图的完整直线（辉光 + 主芯 + 芯心）
        if self.bullet_type == Bullet.LASER and self.beam_mode:
            if self.beam_end is None:
                self.beam_end = self._compute_beam_end()
            sx = int(arena_x + self.start_x)
            sy = int(arena_y + self.start_y)
            ex = int(arena_x + self.beam_end[0])
            ey = int(arena_y + self.beam_end[1])
            # 辉光底（最宽，半透明白-红渐变：直接画两层粗线模拟）
            pygame.draw.line(screen, (200, 40, 40), (sx, sy), (ex, ey),
                             LASER_BEAM_GLOW_WIDTH)
            # 主芯（亮红）
            pygame.draw.line(screen, LASER_BEAM_COLOR, (sx, sy), (ex, ey),
                             LASER_BEAM_WIDTH)
            # 芯心（亮白，清晰可见）
            pygame.draw.line(screen, LASER_BEAM_CORE_COLOR, (sx, sy), (ex, ey), 2)
            # 炮口与末端高亮点
            pygame.draw.circle(screen, LASER_BEAM_CORE_COLOR, (sx, sy), 5)
            pygame.draw.circle(screen, LASER_BEAM_CORE_COLOR, (ex, ey), 4)
            return
        # 飞行激光（叠加弹射的激光）：画沿运动方向的短光束弹头
        if self.bullet_type == Bullet.LASER:
            sx = int(arena_x + self.x)
            sy = int(arena_y + self.y)
            ex = int(arena_x + self.x - self.vx * 22)
            ey = int(arena_y + self.y - self.vy * 22)
            pygame.draw.line(screen, (200, 40, 40), (ex, ey), (sx, sy),
                             LASER_BEAM_GLOW_WIDTH)
            pygame.draw.line(screen, LASER_BEAM_COLOR, (ex, ey), (sx, sy),
                             LASER_BEAM_WIDTH)
            pygame.draw.line(screen, LASER_BEAM_CORE_COLOR, (ex, ey), (sx, sy), 2)
            return

        # 散射：蓝色
        if self.enemy_bounce:
            color = ENEMY_BOUNCE_COLOR        # 跳弹游骑兵专属紫
        elif self.bullet_type == Bullet.SCATTER:
            color = COLOR_BLUE
        elif self.bullet_type == Bullet.BOUNCE:
            color = COLOR_GREEN
        elif self.owner_type == "player":
            color = COLOR_YELLOW
        else:
            color = (255, 100, 100)

        # 尾迹小点
        for i, (tx, ty) in enumerate(self.trail):
            r = 1 + i // 3
            c_a = max(60, 200 - (len(self.trail) - i) * 18)
            c = (min(255, color[0]), min(255, color[1]), min(255, color[2]))
            pygame.draw.circle(screen, c,
                               (int(arena_x + tx), int(arena_y + ty)), max(1, r - 1))
        # 辉光底光（技术美术增强：发光质感，复用 vfx 缓存）
        draw_glow(screen, arena_x + self.x, arena_y + self.y,
                  BULLET_SIZE // 2 + 6, color, alpha=150)
        # 弹头
        pygame.draw.circle(screen, color,
                           (int(arena_x + self.x), int(arena_y + self.y)),
                           BULLET_SIZE // 2 + 1)
        pygame.draw.circle(screen, COLOR_WHITE,
                           (int(arena_x + self.x), int(arena_y + self.y)), 2)


# ============ 粒子系统（供 3.2 反弹特效 / 3.4 扩展）============
# 采用模块级列表，由 GameWorld 在每帧 update/draw 时统一驱动与渲染。
PARTICLES = []


def clear_particles():
    """清空所有粒子（新关卡开始时调用，避免跨局残留）"""
    PARTICLES.clear()


def spawn_particle(x, y, color, size, max_life=0.35):
    """在 (x, y) 生成一枚粒子（如弹射反弹白点）。坐标使用竞技场内部坐标。
    max_life 可指定自定义寿命（秒），默认 0.35s。"""
    PARTICLES.append({
        "x": float(x), "y": float(y),
        "color": color, "size": float(size),
        "life": 0.0, "max_life": float(max_life),
    })


def update_particles(dt):
    """推进粒子寿命并移除已过期者"""
    for p in PARTICLES:
        p["life"] += dt
    PARTICLES[:] = [p for p in PARTICLES if p["life"] < p["max_life"]]


def draw_particles(screen, arena_x, arena_y):
    """渲染粒子（辉光点，随寿命淡出缩小）。
    技术美术优化：改用 vfx.draw_glow 预烘焙径向渐变，消除每帧新建 Surface 的 GC 抖动。"""
    for p in PARTICLES:
        t = p["life"] / p["max_life"]
        alpha = int(255 * (1 - t))
        r = max(1, int(p["size"] * (1 - 0.5 * t)))
        draw_glow(screen, arena_x + p["x"], arena_y + p["y"], r + 1, p["color"], alpha=alpha)


# ============ 跳弹环形闪光（2026-08-23）============
# 与 PARTICLES 并列，由 GameWorld / TwoPlayerGameWorld 统一驱动与渲染，
# 作为跳弹发生的视觉反馈（明确提示玩家「弹开」事件）。
RICOCHET_EFFECTS = []


def clear_ricochet():
    """清空跳弹闪光（新关卡开始时调用，避免跨局残留）"""
    RICOCHET_EFFECTS.clear()


def spawn_ricochet_effect(x, y, color):
    """在 (x, y) 生成一枚跳弹环形闪光（竞技场内部坐标）。"""
    RICOCHET_EFFECTS.append({
        "x": float(x), "y": float(y),
        "color": color, "life": 0.0, "max_life": 0.30, "max_r": 22.0,
    })


def update_ricochet(dt):
    """推进跳弹闪光寿命并移除已过期者"""
    for e in RICOCHET_EFFECTS:
        e["life"] += dt
    RICOCHET_EFFECTS[:] = [e for e in RICOCHET_EFFECTS if e["life"] < e["max_life"]]


def draw_ricochet(screen, arena_x, arena_y):
    """渲染跳弹环形闪光：随寿命扩大并淡出的橙色圆环。
    技术美术优化：复用 vfx 预烘焙环缓存（按最大半径），零每帧新建 Surface。"""
    for e in RICOCHET_EFFECTS:
        t = e["life"] / e["max_life"]
        alpha = int(220 * (1 - t))
        r = max(2, int(e["max_r"] * t))
        cx = int(arena_x + e["x"])
        cy = int(arena_y + e["y"])
        ring = get_ring(int(e["max_r"]))
        prev = ring.get_alpha()
        if alpha != 255:
            ring.set_alpha(alpha)
        scale = (r * 2 + 2) / ring.get_width()
        if scale > 0:
            scaled = pygame.transform.smoothscale(
                ring, (max(2, int(ring.get_width() * scale)),
                       max(2, int(ring.get_height() * scale))))
            screen.blit(scaled, (int(cx - scaled.get_width() // 2),
                                  int(cy - scaled.get_height() // 2)))
        if alpha != 255:
            ring.set_alpha(prev)
