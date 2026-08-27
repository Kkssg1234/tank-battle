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
    CarnivalScreen,
    LeaderboardScreen,
    GarageScreen,
)
from save_manager import SaveManager
from particles import update_ui_particles, draw_ui_particles

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
        # 桌面端：启动即捕获「真实桌面分辨率」（仅一次）。
        # 关键：之后 toggle 不再调用 pygame.display.Info() 重新读取——
        # 否则从全屏切回窗口(SCALED)后，Info 会返回「窗口尺寸」而非桌面尺寸，
        # 再次进入全屏时会以错误的(变小)分辨率 set_mode，表现为「无法恢复全屏」。
        _dinfo = pygame.display.Info()
        self._desktop_w = int(getattr(_dinfo, "current_w", 0) or SCREEN_WIDTH)
        self._desktop_h = int(getattr(_dinfo, "current_h", 0) or SCREEN_HEIGHT)

        self.native_w = SCREEN_WIDTH
        self.native_h = SCREEN_HEIGHT
        self._fit_scale = 1.0
        self._fit_x = 0
        self._fit_y = 0
        self.use_offscreen = False          # 标志：是否走离屏→显示 的放大流程
        # 持久离屏画布：避免每次 toggle 重新分配 Surface
        self.offscreen = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        if _IN_BROWSER:
            self.screen = self.display = pygame.display.set_mode(
                (SCREEN_WIDTH, SCREEN_HEIGHT), 0)
        else:
            nw, nh = self._desktop_w, self._desktop_h
            # 取不到真实分辨率（无头/虚拟显示）时回退到窗口模式，避免 set_mode 报错
            if nw > 0 and nh > 0:
                self.native_w, self.native_h = nw, nh
                self.screen = self.offscreen
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
        # 界面切换黑屏淡入过渡（剩余秒数；>0 时在每帧最后叠加一层渐隐黑幕）
        self.transition = 0.0

        # 游戏上下文数据
        self.current_level = 1       # 单人当前关卡
        self.two_mode = "coop"       # 双人模式: coop 或 vs
        self.p2_tank = "轻型侦察车"  # 双人-玩家 2 选定的坦克（开局前在选车界面确认）
        self.p1_name = "玩家1"       # 双人模式玩家 1 名称（设置界面可改）
        self.p2_name = "玩家2"       # 双人模式玩家 2 名称（设置界面可改）

        # 各界面对象
        self.screens = {
            STATE_MENU: MenuScreen(self),
            STATE_LEVEL_SELECT: LevelSelectScreen(self),
            STATE_SINGLE_PLAY: SinglePlayScreen(self),
            STATE_TWO_PLAYER_SELECT: TwoPlayerSelectScreen(self),
            STATE_P2_TANK_SELECT: P2TankSelectScreen(self),
            STATE_TWO_PLAY: TwoPlayScreen(self),
            STATE_CARNIVAL: CarnivalScreen(self),
            STATE_LEADERBOARD: LeaderboardScreen(self),
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
        # 切屏时恢复系统鼠标指针（双人模式在游戏进行中会隐藏，避免遗留隐藏状态）
        pygame.mouse.set_visible(True)
        # 触发 0.15s 黑屏淡入过渡（新界面从黑幕中淡现）
        self.transition = 0.15

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
        # 进入全屏：离屏画布 + 等比 letterbox。
        # 使用启动时捕获的真实桌面分辨率（self._desktop_w/_h），
        # 不再调用 display.Info()，避免窗口态后读到错误分辨率。
        nw, nh = self._desktop_w, self._desktop_h
        if nw > 0 and nh > 0:
            self.native_w, self.native_h = nw, nh
            self.screen = self.offscreen
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

    def is_fullscreen(self):
        """返回当前是否处于全屏（供 UI 按钮显示状态）。浏览器端始终返回 False。"""
        if _IN_BROWSER:
            return False
        return self.use_offscreen

    def toggle_web_fullscreen(self):
        """网页端：通过浏览器 Fullscreen API 进入/退出全屏（需用户手势触发）。
        仅在 _IN_BROWSER 下生效；其余平台直接忽略。"""
        if not _IN_BROWSER:
            return
        try:
            doc = platform.window.document
            if getattr(doc, "fullscreenElement", None):
                if doc.exitFullscreen:
                    doc.exitFullscreen()
            else:
                el = doc.documentElement
                if el and el.requestFullscreen:
                    el.requestFullscreen()
        except Exception:
            # 部分浏览器要求 requestFullscreen 必须在同步用户手势内调用，
            # 若被异步事件拦截而失败，用户仍可用浏览器自带全屏（F11 / 控件）。
            pass

    def toggle_fullscreen_mode(self):
        """统一全屏切换入口：网页端走 Fullscreen API，桌面端走离屏 letterbox。
        供界面「全屏」按钮调用。"""
        if _IN_BROWSER:
            self.toggle_web_fullscreen()
        else:
            self.toggle_fullscreen()

    def run(self):
        """主循环（本地同步版）。"""
        # 确保存档文件存在（首次运行自动生成 save.json）
        self.save_data = SaveManager.load()
        self._loop()

    def _hide_infobox(self):
        """隐藏 pygbag 加载提示框（#infobox，默认文案 "Loading, please wait ..."）。

        pygbag 模板在 shell.source(main) 返回后才隐藏该框，但本游戏主循环是无限循环、
        shell.source 永不返回，故必须主动隐藏；否则它会永久盖在画面上。
        优先用 document.getElementById("infobox")（比 window.infobox 命名属性更稳），
        失败再回退到 window.infobox。"""
        if not _IN_BROWSER:
            return
        try:
            doc = platform.window.document
            el = doc.getElementById("infobox") if doc else None
            if el is not None:
                el.style.display = "none"
                return
        except Exception:
            pass
        try:
            ib = getattr(platform.window, "infobox", None)
            if ib is not None:
                ib.style.display = "none"
        except Exception:
            pass

    async def run_async(self):
        """主循环（浏览器异步版）。"""
        try:
            # 1) 进主循环前先隐藏加载遮罩：无论后续存档加载是否顺利，都不再卡在
            #    "Loading, please wait ..."。原先是先 await 存档再隐藏，一旦
            #    platform.storage.get 在浏览器端偶发挂起不返回，遮罩便永久停留。
            self._hide_infobox()
            # 2) 加载存档：浏览器端走 platform.storage，偶发不返回（挂起）。
            #    用超时兜底——超时则退回默认存档，保证游戏一定能启动，
            #    绝不在加载界面卡死（这是之前“一直卡在 Loading”的直接根因）。
            try:
                self.save_data = await asyncio.wait_for(self.load_save(), timeout=3.0)
            except Exception:
                self.save_data = SaveManager._default()
            await self._loop_async()
        except Exception as _err:
            # 即便启动失败也先隐藏加载遮罩，让下面的错误框可见（而非压在 Loading 文字下）。
            self._hide_infobox()
            # 网页端 xtermjs 关闭时 Python traceback 会被丢弃，导致「无声卡死」。
            # 这里把异常直接渲染到页面，便于定位：刷新即可看到具体错误。
            import traceback as _tb
            _msg = "【游戏启动异常】\n" + _tb.format_exc()
            print(_msg, file=sys.stderr)
            if _IN_BROWSER:
                try:
                    _el = platform.window.document.createElement("pre")
                    _el.style.cssText = (
                        "position:fixed;top:0;left:0;right:0;max-height:60%;overflow:auto;"
                        "color:#ff5555;background:#000;white-space:pre-wrap;z-index:9999999;"
                        "font:13px/1.4 monospace;padding:12px;border-bottom:2px solid #ff5555;"
                    )
                    _el.textContent = _msg
                    platform.window.document.body.appendChild(_el)
                except Exception:
                    pass
            raise

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
                # 统一入口：网页端走 Fullscreen API，桌面端走离屏 letterbox
                self.toggle_fullscreen_mode()
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
            # UI 悬停粒子（按钮火花）每帧更新并绘制到画布
            update_ui_particles(dt)
            draw_ui_particles(self.screen)
            # 界面切换黑屏淡入过渡：从黑幕中淡现新界面（约 0.15s）
            if self.transition > 0:
                self.transition = max(0.0, self.transition - dt)
                _fa = int(200 * (self.transition / 0.15))
                _fade = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
                _fade.fill((0, 0, 0, _fa))
                self.screen.blit(_fade, (0, 0))
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
            # UI 悬停粒子（按钮火花）每帧更新并绘制到画布
            update_ui_particles(dt)
            draw_ui_particles(self.screen)
            # 界面切换黑屏淡入过渡：从黑幕中淡现新界面（约 0.15s）
            if self.transition > 0:
                self.transition = max(0.0, self.transition - dt)
                _fa = int(200 * (self.transition / 0.15))
                _fade = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
                _fade.fill((0, 0, 0, _fa))
                self.screen.blit(_fade, (0, 0))
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
