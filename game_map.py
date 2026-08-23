"""
游戏地图系统（兼容层）
======================
地图生成与碰撞逻辑已迁移至 map_generator.py（MapGenerator / Map）。
此处保留 GameMap 作为历史别名，避免其它模块 from game_map import GameMap 失败。
新代码请直接使用：from map_generator import Map, MapGenerator
"""
from map_generator import Map, MapGenerator

# 历史别名：GameMap == Map（构造方式改为 Map(grid, cols, rows, tile_size, ...)，
# 由 MapGenerator.generate() 返回；不再接受 GameMap(level, fonts) 旧签名）
GameMap = Map

__all__ = ["GameMap", "Map", "MapGenerator"]
