# 坦克大战 - 浪尖儿大学生社区

俯视角坦克射击小游戏，PyGame 实现。单人 15 关闯关 + 双人模式（合作对抗 AI / 1v1 对战），带坦克解锁成长、道具叠加组合与跳弹机制。

## 运行环境

- Python 3.10+
- pygame-ce（推荐 `>= 2.5`，向下兼容 `pygame 2.x`）

安装依赖：

```bash
pip install -r requirements.txt
```

启动游戏（桌面版）：

```bash
python main.py
```

## 操作说明

| 模式 | 玩家 1 | 玩家 2 |
|------|--------|--------|
| 单人 | WASD 移动 / 空格或 J 射击 | — |
| 双人 | WASD + 空格 | 鼠标移动 / 左键射击 |

- `ESC`：返回上一级
- `F11`：切换全屏 / 窗口（桌面版；网页版忽略）
- `Ctrl+Q`：退出（桌面版）

## 游戏特性

- **单人闯关**：15 关难度递增，通关解锁新坦克（5 辆可解锁坦克，进度自动存档）
- **双人模式**：合作对抗 AI / 1v1 对战；玩家 2 可独立选坦克
- **道具叠加**：激光 / 弹射 / 散射可同时叠加组合——散射激光（3 束扇形光束）、可弹射激光、三件套（3 束可弹射激光）等
- **弹射随机化**：弹射不沿入射路径原路返回，方向随机偏转（±50°），增加弹道不确定性
- **护盾**：独立次数型防御，免疫一次伤害

## 项目结构

```
main.py             # 入口与状态机（双端兼容：桌面同步 / 浏览器异步）
screens.py          # 各界面（菜单/选关/车库/双人/结算）
game_world.py       # 单/双人游戏世界与胜负判定
entities.py         # 坦克实体（移动/射击/道具叠加）
bullets.py          # 子弹（激光光束/弹射/跳弹）
powerup.py          # 道具箱刷新与叠加计时
map_generator.py    # 关卡地图生成
level_config.py     # 15 关配置表
save_manager.py     # 存档读写与坦克解锁（双端兼容）
ui_utils.py / vfx.py / constants.py
```

## 存档

存档保存在本地 `save.json`（首次运行自动生成）。包含最高通关、累计战斗、各关最高分、已解锁坦克与当前出战坦克。

## 技术说明

- 帧率 60 FPS，渲染采用预烘焙 Sprite + 缓存辉光，避免每帧 Surface 分配
- 单人模式记录解锁统计；双人模式不计入
- 弹射/跳弹相关数值（`BOUNCE_SPREAD` 等）为调参预留，集中定义在 `constants.py`

## 在线游玩（网页版）

本游戏已通过 [pygbag](https://github.com/pygame-web/pygbag) 打包为 WebAssembly，可直接在浏览器游玩，**无需安装 Python**。

- 部署方式：推送 `main` 分支后，GitHub Actions 自动构建并发布到 GitHub Pages。
- 访问地址：`https://<你的用户名>.github.io/<仓库名>/`
- 首次加载较慢（需下载 Python wasm 运行时），之后会被浏览器缓存。
- 操作与桌面版一致：WASD 移动 / 空格或 J 射击（P1）；鼠标 + 左键（P2）。
- 网页版存档使用浏览器本地存储（`platform.storage`），进度保存在当前浏览器，不与桌面版共用。
- 网页版专属功能「下载存档到本地」：主菜单提供入口，可将当前游戏进度导出为 `tank-battle-save.json` 下载到本机设备（基于 Blob 原生下载，兼容 Chrome / Firefox / Edge / Safari 等主流浏览器；小文件自动回退 data URI）。点击后顶部会显示「存档已下载」提示。

### 网页版 UI / 性能优化（2026-08-24）
- **UI 统一**：所有图标（血量心形、道具色点、锁、护盾、警告三角）均用 pygame 矢量绘制，不再依赖 emoji 字形——emoji 在 pygame（网页/本地）均无法渲染、会留下空格占位；现在网页版与本地版显示完全一致。
- **布局美化**：画布两侧的 letterbox 区域主题化为深蓝科技风（网格 + 径向渐变）并为画布添加青色辉光边框，消除“空白”观感（固定 16:9 内容在非 16:9 视口采用美化方案，不拉伸/裁切画面）。
- **加载提速**：内置中文字体由完整 9.3MB 子集化为仅含游戏用到的 ~1000 个字形（约 229KB，体积减少约 97%），显著缩短首屏下载；生产环境关闭 xtermjs 终端覆盖层、预连接 CDN，进一步加快加载。

### 本地预览网页版

```bash
pip install pygbag
pygbag --build .            # 产物在 build/web/
# 用任意静态服务器打开 build/web/ 即可（如 python -m http.server）
```

### 双端兼容说明

代码已做双端适配，桌面 Python 与浏览器 wasm 均可运行：

- `main.py`：桌面走同步 `run()`，浏览器走异步 `run_async()` + `await asyncio.sleep(0)`
- `save_manager.py`：桌面写本地 `save.json`，浏览器走 `platform.storage` 异步持久化
- `ui_utils.py`：浏览器端字体回退到内置默认字体，避免依赖系统字体路径
- 浏览器端显示标志使用 `flags=0`（不使用 `pygame.SCALED`/`FULLSCREEN`，canvas 后端无软件缩放器，使用会导致黑屏），并在游戏启动后主动隐藏 pygbag 加载提示框
- `web_download.py`：网页版「下载到本地」辅助模块（仅浏览器生效，桌面端安全 no-op）
- 浏览器端自动去除 `FULLSCREEN` 显示标志
