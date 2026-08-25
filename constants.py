"""
全局常量配置 - 颜色、尺寸、坦克数据、游戏状态等
"""

# ===== 窗口尺寸 =====
SCREEN_WIDTH = 960
SCREEN_HEIGHT = 640
FPS = 60
TITLE = "坦克大战 - 浪尖儿大学生社区"

# ===== 颜色定义 =====
COLOR_BG = (11, 18, 32)              # 深海军蓝（冷锻钢蓝，非纯黑，带蓝调）
COLOR_BG_GRID = (22, 36, 58)         # 极淡钢蓝网格，几乎不可见
COLOR_MENU_BG = (8, 14, 26)          # 菜单更深海军蓝
COLOR_WHITE = (255, 255, 255)
COLOR_BLACK = (0, 0, 0)
COLOR_GRAY = (120, 120, 120)
COLOR_LIGHT_GRAY = (180, 180, 180)
COLOR_DARK_GRAY = (60, 60, 60)
COLOR_RED = (230, 60, 60)
COLOR_GREEN = (80, 220, 100)
COLOR_BLUE = (70, 140, 255)
COLOR_YELLOW = (255, 210, 60)
COLOR_ORANGE = (255, 150, 50)
COLOR_CYAN = (91, 127, 168)          # 钢蓝（装饰/信息色，去冰蓝荧光）
COLOR_PURPLE = (200, 120, 255)
COLOR_PINK = (255, 120, 180)
COLOR_GOLD = (255, 170, 60)          # 偏橙金，更有金属感
COLOR_AMBER = (232, 165, 71)         # 唯一强调色：琥珀（方案核心强调）

# 按钮颜色
COLOR_BTN = (24, 41, 74)              # 按钮底（钢蓝灰卡片底）
COLOR_BTN_HOVER = (31, 53, 95)        # 悬停提亮（钢蓝）
COLOR_BTN_DISABLED = (16, 24, 40)
COLOR_BTN_BORDER = (91, 127, 168)     # 钢蓝边框（非白钢）

# 发光 / 面板 / 强调（2026-08-25 暗色钢铁科技风）
COLOR_GLOW = (91, 127, 168, 24)       # 按钮外发光基础色（钢蓝，去霓虹白光）
COLOR_PANEL_BG = (19, 32, 58, 235)    # 面板底色（深海军蓝 RGBA）
COLOR_ACCENT = (199, 84, 80)          # 强调色（危险/友军伤害警告，去霓虹橙红）

# ===== UI 设计系统 Token（2026-08-23 美术优化）=====
# 语义表面层：深蓝科技风的层次化背景（由深到浅，营造纵深）
UI_BG_DEEP = (11, 18, 32)           # 最深层底色（深海军蓝）
UI_SURFACE = (19, 32, 58)           # 表面层（面板/底栏底色，深海军蓝）
UI_CARD = (24, 41, 74)              # 卡片层（钢蓝灰浮起元素底色）
UI_CARD_HI = (31, 53, 95)           # 卡片顶部高光（提亮 1 档）
UI_CARD_BORDER = (30, 58, 95)       # 卡片描边（深钢蓝）
UI_CARD_BORDER_HI = (232, 165, 71)  # 卡片选中/强调描边（琥珀）

# 强调色（语义别名，便于统一引用）
UI_ACCENT = (232, 165, 71)          # 主强调（琥珀，标题/选中/进度）
UI_ACCENT_CYAN = (91, 127, 168)     # 高亮钢蓝（副标题/链接/信息）
UI_ACCENT_BTN = (24, 41, 74)        # 按钮底（钢蓝灰）
UI_ACCENT_BTN_HI = (31, 53, 95)     # 按钮 hover 提亮（钢蓝）

# 阴影 / 发光
UI_SHADOW = (0, 0, 0)               # 硬阴影色
UI_SHADOW_ALPHA = 130               # 硬阴影透明度
UI_GLOW_ALPHA = 90                  # 强调发光透明度

# 圆角 / 间距 / 动效（像素）
UI_RADIUS_SM = 2
UI_RADIUS_MD = 3
UI_RADIUS_LG = 4
UI_BTN_LIFT = 2                     # 按钮 hover 抬升像素

# 徽章语义配色（底色 + 前景色成对，胶囊型标签用）
UI_BADGE_SUCCESS_BG = (22, 52, 28)
UI_BADGE_SUCCESS_FG = (80, 220, 100)
UI_BADGE_LOCK_BG = (54, 40, 22)
UI_BADGE_LOCK_FG = (255, 200, 50)
UI_BADGE_INFO_BG = (22, 40, 56)
UI_BADGE_INFO_FG = (80, 220, 255)
UI_BADGE_NEUTRAL_BG = (40, 24, 54)
UI_BADGE_NEUTRAL_FG = (200, 120, 255)
UI_BADGE_DANGER_BG = (54, 22, 22)
UI_BADGE_DANGER_FG = (230, 80, 80)

# 砖墙/钢墙颜色
COLOR_BRICK = (180, 90, 60)
COLOR_STEEL = (140, 150, 170)

# ===== 游戏状态 =====
STATE_MENU = "menu"                  # 主菜单
STATE_LEVEL_SELECT = "level_select"  # 单人-选关界面
STATE_SINGLE_PLAY = "single_play"    # 单人-游戏中
STATE_TWO_PLAYER_SELECT = "two_player_select"  # 双人-子模式选择
STATE_P2_TANK_SELECT = "p2_tank_select"  # 双人-玩家 2 选坦克
STATE_TWO_PLAY = "two_play"          # 双人-游戏中
STATE_GARAGE = "garage"              # 车库
STATE_RESULT = "result"              # 结算界面

# ===== 跳弹机制（2026-08-23）=====
# 子弹击中坦克时按此概率弹开：不发生伤害，飞向随机方向，偏转后保留杀伤力且不区分敌我。
RICOCHET_CHANCE = 0.15          # 跳弹触发概率（低数值，集中可调，便于后续平衡）
RICOCHET_BULLET_COLOR = (255, 175, 70)  # 跳弹子弹专属配色（橙黄），区别于普通黄弹

# ===== 坦克数据 =====
TANK_DATA = {
    "轻型侦察车": {
        "hp": 3,
        "speed": "快",
        "speed_val": 3.5,
        "init_item": None,
        "unlock_desc": "默认解锁",
        "description": "基础坦克，3血高机动，适合走位躲子弹，无初始道具",
        "role": "灵活机动，新手首选",
        "color": COLOR_GREEN,
        "unlock_condition": {"type": "default"}
    },
    "重装突击车": {
        "hp": 5,
        "speed": "中等",
        "speed_val": 2.2,
        "init_item": "scatter",
        "unlock_desc": "通关第 5 关",
        "description": "5血厚实，开局自带散射弹，正面推进能力强",
        "role": "血厚火力覆盖广",
        "color": COLOR_BLUE,
        "unlock_condition": {"type": "level", "value": 5}
    },
    "激光狙击车": {
        "hp": 4,
        "speed": "中等",
        "speed_val": 2.5,
        "init_item": "laser",
        "unlock_desc": "通关第 10 关",
        "description": "4血中等，开局自带激光炮，可穿透钢墙和集群敌人",
        "role": "穿透压制，中距离王者",
        "color": COLOR_RED,
        "unlock_condition": {"type": "level", "value": 10}
    },
    "KZY 终极战车": {
        "hp": 6,
        "speed": "慢",
        "speed_val": 1.8,
        "init_item": "bounce_scatter",
        "unlock_desc": "累计 100 场战斗",
        "description": "6血最高，开局同时持有弹射弹+散射弹（每次射击3发弹射子弹），移速慢但火力恐怖",
        "role": "终极战争机器，复合火力",
        "color": COLOR_GOLD,
        "unlock_condition": {"type": "battles", "value": 100}
    },
    "跳弹游骑兵": {
        "hp": 4,
        "speed": "快",
        "speed_val": 3.5,
        "init_item": None,
        "unlock_desc": "累计 50 场战斗",
        "description": "4血高机动，综合性能略强于初始坦克；跳弹为全游戏通用机制（所有子弹均有概率弹开），本车是攻防兼备的进阶全能坦克",
        "role": "进阶全能 · 略强于初始",
        "color": COLOR_PURPLE,
        "unlock_condition": {"type": "battles", "value": 50}
    }
}

# 坦克列表顺序
TANK_ORDER = ["轻型侦察车", "重装突击车", "激光狙击车", "KZY 终极战车", "跳弹游骑兵"]

# ===== 坦克视觉风格标识（2026-08-25 钢铁科技风差异化）=====
# 仅影响 draw 视觉（车辆外形/炮管/炮塔细节），不改动碰撞框 TANK_SIZE 与任何逻辑。
TANK_STYLE_STANDARD = "standard"   # 通用（敌人、未匹配玩家车）
TANK_STYLE_SCOUT = "scout"         # 轻型侦察车：瘦长、细长炮管
TANK_STYLE_HEAVY = "heavy"         # 重装突击车：宽大、粗短炮管 + 顶部传感器
TANK_STYLE_SNIPER = "sniper"       # 激光狙击车：极长炮管 + 炮塔准星
TANK_STYLE_KZY = "kzy"             # KZY 终极战车：金描边 + 三角标志 + 锯齿履带
TANK_STYLE_BY_NAME = {
    "轻型侦察车": TANK_STYLE_SCOUT,
    "重装突击车": TANK_STYLE_HEAVY,
    "激光狙击车": TANK_STYLE_SNIPER,
    "KZY 终极战车": TANK_STYLE_KZY,
}

# ===== 道具数据 =====
# 注：icon 字段为内部标识（非渲染字形），UI 中道具图标由 screens.py 用 pygame 彩色圆点绘制，
# 不使用 emoji（pygame Monochrome 字体无法渲染 emoji，会留下空格占位）。
ITEM_DATA = {
    "laser": {"name": "激光炮", "icon": "red", "color": COLOR_RED, "desc": "子弹穿透障碍和敌人"},
    "bounce": {"name": "弹射弹", "icon": "green", "color": COLOR_GREEN, "desc": "子弹弹射2次，注意误伤"},
    "scatter": {"name": "散射弹", "icon": "blue", "color": COLOR_BLUE, "desc": "一次发射3发扇形子弹"},
    "shield": {"name": "护盾", "icon": "yellow", "color": COLOR_YELLOW, "desc": "免疫下一次伤害"},
}

# ===== 关卡数量 =====
# TOTAL_LEVELS / LEVELS / get_level_config 统一由 level_config.py 提供（见文件末尾 import）

# ===== 地图 & 战场 =====
# 瓦片大小 (砖墙/钢墙方块大小)
TILE_SIZE = 40
TILE_COLS = 22   # 22 * 40 = 880
TILE_ROWS = 10   # 10 * 40 = 400

# 游戏战斗区域（竞技场）的偏移和尺寸
ARENA_W = TILE_COLS * TILE_SIZE  # 880
ARENA_H = TILE_ROWS * TILE_SIZE  # 400
ARENA_X = (SCREEN_WIDTH - ARENA_W) // 2   # 居中 40
ARENA_Y = 95

# 竞技场背景（黑底白字主题）
ARENA_BG = (0, 0, 0)                  # 纯黑底色
ARENA_BG_TEXT = "浪尖儿学生社区"      # 背景白字内容
ARENA_GRID = (22, 22, 26)            # 极淡网格，避免纯黑死板
ARENA_BORDER = (220, 220, 220)       # 白框，呼应黑底白字

# 瓦片类型
TILE_EMPTY = 0
TILE_BRICK = 1   # 砖墙，可被摧毁
TILE_STEEL = 2   # 钢墙，不可摧毁（激光除外）

# 坦克尺寸
TANK_SIZE = 34

# 方向 (0=上, 1=右, 2=下, 3=左)
DIR_UP = 0
DIR_RIGHT = 1
DIR_DOWN = 2
DIR_LEFT = 3
DIR_VECTORS = {
    DIR_UP: (0, -1),
    DIR_RIGHT: (1, 0),
    DIR_DOWN: (0, 1),
    DIR_LEFT: (-1, 0),
}

# 子弹
BULLET_SIZE = 8
BULLET_SPEED = 360.0          # 像素/秒
PLAYER_FIRE_COOLDOWN = 0.40   # 秒
ENEMY_FIRE_COOLDOWN = 1.1     # 秒
BULLET_DAMAGE = 1

# 激光穿透敌人数量（验收：穿透 3 个敌人后销毁）
LASER_PIERCE_ENEMIES = 3

# 弹射随机化（2026-08-23 道具叠加系统）：弹射不原路返回，方向 = 镜面反射角 ± BOUNCE_SPREAD 随机。
# 数学保证：新方向与入射方向夹角 ≥ 180°-SPREAD（SPREAD=50 → ≥130°），永不沿入射反向弹回。
BOUNCE_SPREAD = 50   # [PLACEHOLDER] 弹射相对镜面反射的随机偏转范围（度），待 playtest 调
BOUNCE_MIN_DEVIATION = 20  # [PLACEHOLDER] 与入射方向的最小偏离下限（度），双重保险防"原路返回"

# 激光直线光束（2026-08-23）：发射瞬间贯穿全图的完整直线
LASER_BEAM_LIFE = 0.28        # 光束可见持续秒数（视觉存在时间）
LASER_BEAM_WIDTH = 6          # 光束主芯宽度
LASER_BEAM_GLOW_WIDTH = 12    # 光束辉光宽度
LASER_BEAM_COLOR = (255, 60, 60)        # 主芯红
LASER_BEAM_CORE_COLOR = (255, 230, 230) # 芯心白
LASER_BEAM_GLOW_COLOR = (255, 90, 70)   # 辉光橙红

# 子弹活动边界（规范指定 800×600，区别于竞技场 880×400）
BULLET_BOUNDS_W = 800
BULLET_BOUNDS_H = 600

# 弹射反弹粒子（验收 4）：白色、半径 2-4 像素、寿命 5 帧（逐帧缩小并淡出）
BOUNCE_PARTICLE_COLOR = (255, 255, 255)
BOUNCE_PARTICLE_MIN_R = 2
BOUNCE_PARTICLE_MAX_R = 4
BOUNCE_PARTICLE_LIFE_FRAMES = 5

# ===== 第1关 AI 难度调优（仅作用于第1关，提升新手操作体验）=====
# 第1关敌人子弹速度 = 基础速度 × 该系数（原速 360px/s 的 60% = 216px/s，弹道更慢、更易躲避）
# 注：第1关敌人攻击间隔由 level_config 的 enemy_fire_cd 直接指定（2.0s），不再使用乘数系数。
LEVEL1_ENEMY_BULLET_SPEED_MULT = 0.6

# 敌人 AI
ENEMY_PATROL_SPEED_FACTOR = 0.7
ENEMY_DETECT_RANGE = 320.0      # 发现玩家距离
ENEMY_CHASE_SPEED_FACTOR = 0.9
ENEMY_PATROL_CHANGE_TIME = 2.5  # 巡逻换方向时间

# ===== 平衡性调整（2026-08-22）：降低整体移速与 AI 强度 =====
# 所有坦克（玩家 + 敌人）基础移速统一下调系数，使操控更平稳、精准
TANK_SPEED_SCALE = 0.80
# AI 敌人强度下调（三项，幅度温和、保留适度挑战）
ENEMY_FIRE_CD_SCALE = 1.30      # 开火冷却放大 → 攻击频率↓
ENEMY_DETECT_SCALE = 0.85       # 侦测/反应距离缩短 → 反应速度↓
ENEMY_AIM_CHANCE = 0.80         # “能开火”时实际开火概率 → 命中率/输出↓
ENEMY_BULLET_SPEED_MULT = 0.85  # 敌人子弹速度系数 → 更易躲避（攻击威胁↓）

# 爆炸特效
EXPLOSION_DURATION = 0.45

# 敌人血量（根据关卡递增）
def get_enemy_hp(level):
    if level <= 3: return 1
    if level <= 7: return 2
    if level <= 11: return 3
    return 4

# ===== 字体大小 =====
FONT_XS = 14
FONT_S = 18
FONT_M = 24
FONT_L = 32
FONT_XL = 48
FONT_XXL = 64

# ===== 提示文字 =====
FRIENDLY_FIRE_TIP = "注意：跳弹会伤到自己！"

# ===== 关卡配置（统一来源）=====
# 关卡数量、敌人数量、难度曲线（移速/攻击间隔/障碍数）全部由 level_config 驱动。
# level_config 不依赖 constants，此处导入无循环导入问题。
# ===== 双人模式常量 =====
P2_SPAWN_X = (TILE_COLS - 4) * TILE_SIZE + TILE_SIZE // 2  # 右下出生点
P2_SPAWN_Y = (TILE_ROWS - 3) * TILE_SIZE + TILE_SIZE // 2
COOP_EXTRA_ENEMIES = 2       # 合作模式比单人同关多 2 个敌人
P2_FIRE_COOLDOWN = 0.40      # 玩家 2 射击冷却（与玩家 1 相同）
MOUSE_CONTROL_DEADZONE = 12  # 鼠标控制死区（像素）

# 玩家 2 默认坦克（双人模式 P2 固定使用，蓝色区分）
P2_TANK_NAME = "轻型侦察车"

from level_config import LEVELS, TOTAL_LEVELS, get_level_config
