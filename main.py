"""
坦克大战小游戏 - 主入口文件
负责：初始化Pygame、游戏状态管理、主循环、事件分发

双端兼容：
- 本地桌面：同步 run() + 本地文件存档
- 浏览器（pygbag）：异步 main() + platform.storage 存档 + 无全屏标志
"""
import sys
import asyncio
import pygame

from constants import *
from ui_utils import load_fonts
from screens import (
    MenuScreen,
    LevelSelectScreen,
    SinglePlayScreen,
    TwoPlayerSelectScreen,
    TwoPlayScreen,
    P2TankSelectScreen,
    GarageScreen,
)
from save_manager import SaveManager

# 判断是否在浏览器（wasm）环境
try:
    import platform

    _IN_BROWSER = platform.system() == "Emscripten"
except Exception:
    _IN_BROWSER = False


class Game:
    """游戏主控制器"""
    def __init__(self):
        pygame.init()
        pygame.display.set_caption(TITLE)
        # 浏览器（wasm）无软件缩放器，pygbag 的 canvas 后端不支持 pygame.SCALED /
        # RESIZABLE / FULLSCREEN，用了会导致画布渲染到空白离屏表面 → 黑屏。
        # 故浏览器端 flags=0，由浏览器/CSS 负责缩放；桌面端保留全屏+缩放。
        flags = 0 if _IN_BROWSER else (pygame.FULLSCREEN | pygame.SCALED)
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), flags)
        self.clock = pygame.time.Clock()
        self.fonts = load_fonts()

        # 存档对象（本地端同步加载真实存档；浏览器端先取默认，run_async 中异步加载后覆盖）
        self.save_data = SaveManager.load()

        # 运行状态
        self.running = True
        self.state = STATE_MENU
        self.prev_state = None

        # 游戏上下文数据
        self.current_level = 1       # 单人当前关卡
        self.two_mode = "coop"       # 双人模式: coop 或 vs
        self.p2_tank = "轻型侦察车"  # 双人-玩家 2 选定的坦克（开局前在选车界面确认）

        # 各界面对象
        self.screens = {
            STATE_MENU: MenuScreen(self),
            STATE_LEVEL_SELECT: LevelSelectScreen(self),
            STATE_SINGLE_PLAY: SinglePlayScreen(self),
            STATE_TWO_PLAYER_SELECT: TwoPlayerSelectScreen(self),
            STATE_P2_TANK_SELECT: P2TankSelectScreen(self),
            STATE_TWO_PLAY: TwoPlayScreen(self),
            STATE_GARAGE: GarageScreen(self),
        }

    async def load_save(self):
        """异步加载存档（浏览器/本地通用）。"""
        self.save_data = await SaveManager.async_load()
        return self.save_data

    def change_state(self, new_state):
        """切换游戏状态"""
        if new_state == self.state:
            return
        self.prev_state = self.state
        self.state = new_state
        screen = self.screens.get(new_state)
        if screen and hasattr(screen, "enter"):
            screen.enter()

    def toggle_fullscreen(self):
        """切换全屏 / 窗口模式（F11，浏览器端忽略）。"""
        if _IN_BROWSER:
            return
        flags = pygame.FULLSCREEN | pygame.SCALED if getattr(self, "fullscreen", True) else 0
        self.fullscreen = not getattr(self, "fullscreen", True)
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), flags)

    def run(self):
        """主循环（本地同步版）。"""
        # 确保存档文件存在（首次运行自动生成 save.json）
        self.save_data = SaveManager.load()
        self._loop()

    async def run_async(self):
        """主循环（浏览器异步版）。"""
        await self.load_save()
        # 主动隐藏 pygbag 的加载提示框（#infobox，z-index:999999，覆盖全屏）。
        # 该提示框原本在 shell.source(main) 返回后才隐藏，但本游戏主循环是无限循环、
        # shell.source 永不返回，故模板永远不会隐藏它 → 绿框一直挡在画面最上层。
        # 这里在游戏一开始主动隐藏，避免遮挡。
        if _IN_BROWSER:
            try:
                platform.window.infobox.style.display = "none"
            except Exception:
                pass
        await self._loop_async()

    def _event_dispatch(self, event):
        """事件分发（本地与浏览器共用）。"""
        if event.type == pygame.QUIT:
            self.running = False
            return
        # 全局快捷键
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_F11:
                self.toggle_fullscreen()
                return
            mods = pygame.key.get_mods()
            if mods & pygame.KMOD_CTRL and event.key == pygame.K_q:
                if not _IN_BROWSER:
                    self.running = False
                return
        current = self.screens.get(self.state)
        if current and hasattr(current, "handle_event"):
            current.handle_event(event)

    def _loop(self):
        """同步主循环体。"""
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0  # 秒
            for event in pygame.event.get():
                self._event_dispatch(event)
                if not self.running:
                    break
            if not self.running:
                break
            current = self.screens.get(self.state)
            if current and hasattr(current, "update"):
                current.update(dt)
            if current and hasattr(current, "draw"):
                current.draw(self.screen, self.fonts)
            pygame.display.flip()
        pygame.quit()
        sys.exit(0)

    async def _loop_async(self):
        """异步主循环体（pygbag 要求 await asyncio.sleep(0)）。"""
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0  # 秒
            for event in pygame.event.get():
                self._event_dispatch(event)
                if not self.running:
                    break
            if not self.running:
                break
            current = self.screens.get(self.state)
            if current and hasattr(current, "update"):
                current.update(dt)
            if current and hasattr(current, "draw"):
                current.draw(self.screen, self.fonts)
            pygame.display.flip()
            await asyncio.sleep(0)  # 让出控制权给事件循环，pygbag 必需


def main():
    game = Game()
    if _IN_BROWSER:
        asyncio.run(game.run_async())
    else:
        game.run()


if __name__ == "__main__":
    main()
