"""
存档管理系统（子 Prompt 3.4 修订版）
====================================
提供：
  - SaveManager  ：JSON 本地存档读写、战斗记录、坦克解锁判定
  - ScoreSystem  ：分数计算与评级（S/A/B/C）

设计要点：
  - 仅单人模式调用 SaveManager.record_battle()，双人模式不计入 total_battles。
  - record_battle() 只负责「更新数据」，调用方需自行 SaveManager.save() 落盘，
    与子 Prompt 3.4 的集成示例保持一致。
  - check_unlocks() 是 Round 4 坦克解锁的数据基础：依据 highest_level_cleared /
    total_battles 自动计算已解锁坦克，record_battle() 内部会应用它。
"""
import json
import os

from constants import TOTAL_LEVELS

# 判断是否在浏览器（pygbag / wasm）环境运行。
# platform.storage 提供异步浏览器端持久化；本地运行则用本地文件。
try:
    import platform

    _IN_BROWSER = platform.system() == "Emscripten"
except Exception:
    _IN_BROWSER = False

if _IN_BROWSER:
    import asyncio

    SAVE_FILE = "save.json"  # 浏览器中使用相对路径（platform.storage 托管）
else:
    SAVE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "save.json")

# 默认坦克（与车库 TANK_DATA 保持一致，使用中文名）
DEFAULT_UNLOCKED = ["轻型侦察车"]
DEFAULT_TANK = "轻型侦察车"

# 排行榜单局上限（仅保留最高分前若干）
LEADERBOARD_MAX = 10

# 坦克解锁阈值（Round 4 扩展点；record_battle 自动应用）
# (坦克名, 判定类型 "level"|"battles", 阈值)
UNLOCK_RULES = [
    ("重装突击车", "level", 5),
    ("激光狙击车", "level", 10),
    ("KZY 终极战车", "battles", 100),
    ("跳弹游骑兵", "battles", 50),
]


class SaveManager:
    """JSON 本地存档管理（静态方法，无状态）。"""

    @staticmethod
    def _default():
        """构造一份全新的默认存档（含 1..15 关最高分占位）。"""
        return {
            "highest_level_cleared": 0,    # 0 = 未通关任何关
            "total_battles": 0,            # 累计单人战斗场次（无论胜负）
            "high_scores": {f"level_{i}": 0 for i in range(1, TOTAL_LEVELS + 1)},
            "unlocked_tanks": list(DEFAULT_UNLOCKED),
            "last_selected_tank": DEFAULT_TANK,
            "leaderboard": [],           # 排行榜：[{name, score, mode, date}]
        }

    @staticmethod
    def load():
        """加载存档（本地同步版）；不存在或损坏时自动重建默认存档（不报错崩溃）。"""
        if not os.path.exists(SAVE_FILE):
            data = SaveManager._default()
            SaveManager.save(data)
            return data

        try:
            with open(SAVE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("存档根节点不是对象")
        except Exception:
            # 存档损坏：重建默认并写回，避免后续读取持续报错
            data = SaveManager._default()
            try:
                SaveManager.save(data)
            except Exception:
                pass
            return data

        # 合并缺省字段（兼容旧存档）
        merged = SaveManager._default()
        merged.update(data)
        data = merged

        # 确保 1..15 关最高分占位齐全
        if not isinstance(data.get("high_scores"), dict):
            data["high_scores"] = {}
        for i in range(1, TOTAL_LEVELS + 1):
            k = f"level_{i}"
            if k not in data["high_scores"]:
                data["high_scores"][k] = 0

        # 确保坦克列表非空
        if not data.get("unlocked_tanks"):
            data["unlocked_tanks"] = list(DEFAULT_UNLOCKED)
        if not data.get("last_selected_tank"):
            data["last_selected_tank"] = DEFAULT_TANK
        return data

    @staticmethod
    async def async_load():
        """加载存档（异步版）：浏览器走 platform.storage，本地走同步 load()。"""
        if _IN_BROWSER:
            try:
                data = await platform.storage.get(SAVE_FILE)
                if data is None:
                    data = SaveManager._default()
                    await SaveManager.async_save(data)
                    return data
                if isinstance(data, str):
                    data = json.loads(data)
                if not isinstance(data, dict):
                    raise ValueError("存档根节点不是对象")
            except Exception:
                data = SaveManager._default()
                try:
                    await SaveManager.async_save(data)
                except Exception:
                    pass
                return data

            # 合并缺省字段（兼容旧存档）
            merged = SaveManager._default()
            merged.update(data)
            data = merged
            if not isinstance(data.get("high_scores"), dict):
                data["high_scores"] = {}
            for i in range(1, TOTAL_LEVELS + 1):
                k = f"level_{i}"
                if k not in data["high_scores"]:
                    data["high_scores"][k] = 0
            if not data.get("unlocked_tanks"):
                data["unlocked_tanks"] = list(DEFAULT_UNLOCKED)
            if not data.get("last_selected_tank"):
                data["last_selected_tank"] = DEFAULT_TANK
            return data
        # 本地：直接复用同步实现
        return SaveManager.load()

    @staticmethod
    def save(data):
        """原子写入存档（本地同步版）：先写临时文件再 os.replace 覆盖。"""
        try:
            tmp = SAVE_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, SAVE_FILE)
        except Exception as e:
            print(f"存档写入失败: {e}")

    @staticmethod
    async def async_save(data):
        """写入存档（异步版）：浏览器走 platform.storage，本地走同步 save()。"""
        if _IN_BROWSER:
            try:
                await platform.storage.put(
                    SAVE_FILE, json.dumps(data, ensure_ascii=False, indent=2)
                )
            except Exception as e:
                print(f"存档写入失败: {e}")
            return
        # 本地：直接复用同步实现
        SaveManager.save(data)

    @staticmethod
    def record_battle(data, level, victory, score, enemies_killed, time_used):
        """记录一场单人战斗结果，原地修改并返回 data。

        注意：本方法只更新内存中的数据，调用方需自行 SaveManager.save() 落盘。
        - total_battles 每次 +1（无论胜负）。
        - 胜利时更新 highest_level_cleared 与 high_scores（取最大值）。
        - 自动应用坦克解锁（check_unlocks / _apply_unlocks）。
        """
        data["total_battles"] = int(data.get("total_battles", 0)) + 1
        if victory:
            data["highest_level_cleared"] = max(
                int(data.get("highest_level_cleared", 0)), int(level))
            key = f"level_{level}"
            scores = data.setdefault("high_scores", {})
            old = int(scores.get(key, 0))
            if score > old:
                scores[key] = score
        # 应用坦克解锁（Round 4 扩展点）
        SaveManager._apply_unlocks(data)
        return data

    @staticmethod
    def check_unlocks(data):
        """返回给定存档应解锁的全部坦克名（幂等，供 UI 显示解锁进度）。
        Round 4 可在此扩展更多解锁条件。"""
        unlocked = set(data.get("unlocked_tanks", []))
        unlocked.add(DEFAULT_TANK)
        highest = int(data.get("highest_level_cleared", 0))
        battles = int(data.get("total_battles", 0))
        for name, kind, val in UNLOCK_RULES:
            if kind == "level" and highest >= val:
                unlocked.add(name)
            elif kind == "battles" and battles >= val:
                unlocked.add(name)
        return sorted(unlocked)

    @staticmethod
    def _apply_unlocks(data):
        """依据当前进度刷新 unlocked_tanks（去重、保留顺序）。"""
        data["unlocked_tanks"] = SaveManager.check_unlocks(data)

    @staticmethod
    def record_leaderboard(data, name, score, mode):
        """记录一条排行榜成绩（name/score/mode），原地修改并返回 data。
        按分数降序保留前 LEADERBOARD_MAX 条。调用方需自行 SaveManager.save() 落盘。"""
        from datetime import datetime
        board = data.setdefault("leaderboard", [])
        entry = {
            "name": (name or "无名")[:12],
            "score": int(score),
            "mode": mode,   # "carnival" / "vs_ai"
            "date": datetime.now().strftime("%Y-%m-%d"),
        }
        board.append(entry)
        board.sort(key=lambda e: e["score"], reverse=True)
        data["leaderboard"] = board[:LEADERBOARD_MAX]
        SaveManager._apply_unlocks(data)
        return data

    @staticmethod
    def get_leaderboard(data, mode=None):
        """返回排行榜（可选按 mode 过滤），按分数降序。"""
        board = data.get("leaderboard", [])
        if mode:
            board = [e for e in board if e.get("mode") == mode]
        return sorted(board, key=lambda e: e["score"], reverse=True)

    @staticmethod
    def select_tank(tank_name):
        """选择出战坦克（仅在已解锁时生效），并落盘（本地同步版）。"""
        data = SaveManager.load()
        if tank_name in data.get("unlocked_tanks", []):
            data["last_selected_tank"] = tank_name
            SaveManager.save(data)
        return data

    @staticmethod
    async def async_select_tank(tank_name):
        """选择出战坦克（异步版，浏览器/本地通用）。"""
        data = await SaveManager.async_load()
        if tank_name in data.get("unlocked_tanks", []):
            data["last_selected_tank"] = tank_name
            await SaveManager.async_save(data)
        return data


class ScoreSystem:
    """分数计算与评级（子 Prompt 3.4 规范）。"""

    @staticmethod
    def calculate(enemies_killed, remaining_hp, time_used, level):
        base = enemies_killed * 100
        hp_bonus = remaining_hp * 200
        time_bonus = max(0, int(60 - time_used)) * 10  # 60 秒内通关奖励
        level_bonus = level * 50
        return base + hp_bonus + time_bonus + level_bonus

    @staticmethod
    def get_grade(score):
        if score >= 3000:
            return "S"
        if score >= 2000:
            return "A"
        if score >= 1000:
            return "B"
        return "C"
