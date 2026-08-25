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
        # 故浏览器端 flags=0，由浏览器/CSS 负责缩放。
        # 桌面端：用「离屏 960x640 画布绘制 + 等比 letterbox 放大铺满全屏」替代旧的
        # pygame.SCALED|FULLSCREEN——后者会拉伸形变且非整数倍放大发虚；新方案保持
        # 正确宽高比（黑边留白）、画面锐利，鼠标坐标在事件循环中映射回画布空间。
        self.native_w = SCREEN_WIDTH
        self.native_h = SCREEN_HEIGHT
        self._fit_scale = 1.0
        self._fit_x = 0
        self._fit_y = 0
        self.use_offscreen = False          # 标志：是否走离屏→显示 的放大流程
        if _IN_BROWSER:
            self.screen = self.display = pygame.display.set_mode(
                (SCREEN_WIDTH, SCREEN_HEIGHT), 0)
        else:
            info = pygame.display.Info()
            nw = getattr(info, "current_w", 0) or 0
            nh = getattr(info, "current_h", 0) or 0
            # 取不到真实分辨率（无头/虚拟显示）时回退到窗口模式，避免 set_mode 报错
            if nw > 0 and nh > 0:
                self.native_w, self.native_h = nw, nh
                self.screen = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
                try:
                    self.display = pygame.display.set_mode((nw, nh), pygame.FULLSCREEN)
                except Exception:
                    self.display = pygame.display.set_mode(
                        (SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SCALED)
                    self.screen = self.display
                self.use_offscreen = self.screen is not self.display
            else:
                self.screen = self.display = pygame.display.set_mode(
                    (SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SCALED)
            self._compute_fit()
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

    def _compute_fit(self):
        """计算离屏画布 → 显示分辨率的等比适配矩形（letterbox 居中）。"""
        self._fit_scale = 1.0
        self._fit_x = 0
        self._fit_y = 0
        if not self.use_offscreen:
            return
        sw, sh = SCREEN_WIDTH, SCREEN_HEIGHT
        scale = min(self.native_w / sw, self.native_h / sh)
        if scale <= 0:
            scale = 1.0
        self._fit_scale = scale
        self._fit_w = int(round(sw * scale))
        self._fit_h = int(round(sh * scale))
        self._fit_x = (self.native_w - self._fit_w) // 2
        self._fit_y = (self.native_h - self._fit_h) // 2

    def map_mouse(self, pos):
        """把显示分辨率下的鼠标坐标映射回 960x640 画布坐标（非离屏模式原样返回）。"""
        if not self.use_offscreen:
            return pos
        x = (pos[0] - self._fit_x) / self._fit_scale
        y = (pos[1] - self._fit_y) / self._fit_scale
        return (int(x), int(y))

    def _present(self):
        """提交一帧：离屏模式做等比放大铺满；否则直接 flip。"""
        if not self.use_offscreen:
            pygame.display.flip()
            return
        self.display.fill((0, 0, 0))
        scaled = pygame.transform.smoothscale(
            self.screen, (self._fit_w, self._fit_h))
        self.display.blit(scaled, (self._fit_x, self._fit_y))
        pygame.display.flip()

    def toggle_fullscreen(self):
        """切换全屏 / 窗口模式（F11，浏览器端忽略）。"""
        if _IN_BROWSER:
            return
        if self.use_offscreen:
            # 退出全屏 → 窗口模式（SCALED 放大，鼠标由 SCALED 自动映射）
            self.display = pygame.display.set_mode(
                (SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SCALED)
            self.screen = self.display
            self.use_offscreen = False
            self._compute_fit()
            return
        # 进入全屏：离屏画布 + 等比 letterbox
        info = pygame.display.Info()
        nw = getattr(info, "current_w", 0) or SCREEN_WIDTH
        nh = getattr(info, "current_h", 0) or SCREEN_HEIGHT
        self.native_w, self.native_h = nw, nh
        if nw > 0 and nh > 0:
            self.screen = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
            try:
                self.display = pygame.display.set_mode((nw, nh), pygame.FULLSCREEN)
            except Exception:
                self.display = pygame.display.set_mode(
                    (SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SCALED)
                self.screen = self.display
                self.use_offscreen = False
                self._compute_fit()
                return
            self.use_offscreen = True
        else:
            self.display = pygame.display.set_mode(
                (SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SCALED)
            self.screen = self.display
            self.use_offscreen = False
        self._compute_fit()

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
        # 离屏模式：把鼠标坐标映射回 960x640 画布空间（保证按钮/瞄准命中正确）
        if self.use_offscreen and event.type in (
                pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            event.pos = self.map_mouse(event.pos)
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
            self._present()
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
            self._present()
            await asyncio.sleep(0)  # 让出控制权给事件循环，pygbag 必需


def main():
    game = Game()
    if _IN_BROWSER:
        asyncio.run(game.run_async())
    else:
        game.run()


if __name__ == "__main__":
    main()
