# 小雪工具箱 原生重写路线图 (rewrite/tauri)

> 目标: 用 Tauri 2 (Rust 后端 + React/TypeScript 前端) 重写小雪工具箱,
> 换取 启动 <0.5s / 内存 ~100MB / 壳体积 <20MB / Web 级 UI 上限。
> 业务本质是「ffmpeg 编排器」, Rust 标准库即可覆盖全部编排逻辑。

## 决策记录

| 决策点 | 选择 | 理由 |
|---|---|---|
| 壳框架 | Tauri 2 | 体积/安全性优于 Electron 与 Wails; WebView2 随 Win10+ 系统内置 |
| 前端 | React 18 + TS + Fluent UI React v9 | 与现有 Fluent 设计语言延续, 视觉上限最高 |
| 后端 | 纯 Rust std + serde_json | ffmpeg 编排/ffprobe 解析无需重依赖 |
| 仓库形态 | 与 Python 版同仓库, `engine/` + `app/` 共存 | 逻辑可并行对照迁移, Python 版继续作为生产版本 |
| Shield (NSFW) | **最后移植** (M4) | imgutils 预处理管线移植成本高; 期间由 Python 版承担 |
| 热更新 | 单体二进制替换 (M5) | 比 PyInstaller 布局更简单; ffmpeg 目录按需更新 |

## 本地开发前置

```powershell
winget install Rustlang.Rustup        # Rust stable + msvc target
winget install OpenJS.NodeJS.LTS      # Node 20+
# Rust 需要 MSVC Build Tools (VS Installer 勾选 C++ 桌面开发)
```

## 里程碑

### M0 — 引擎 crate 骨架 (本分支已开始)
- `engine/`: 纯 Rust crate, 零第三方依赖, 承载全部可测业务逻辑
- 已移植: 版本比较 (`version.rs`) / ffmpeg 流映射与编码命令构建 (`ffmpeg.rs`)
- CI: `.github/workflows/rewrite.yml` — cargo test + clippy

### M1 — 引擎逻辑补全
- `ffmpeg.rs`: 替换音频/封装/抽取命令, 2-Pass, run_ffmpeg (std::process 流式输出)
- `probe.rs`: ffprobe JSON 解析 -> MediaInfo (serde_json)
- `qc.rs` / `batch.rs` / `image.rs` (image crate) / `notify.rs` (ureq)
- 对齐移植: 每个 Python 测试在 Rust 侧有等价用例

### M2 — Tauri 壳 + 首个页面
- `app/`: Tauri 2 + Vite + React + TS
- 设计系统: Fluent UI React v9, 暗色主题, 沿用现有设计令牌
- 首页: 视频压制 (命令预览/进度/日志 WebSocket 推流)

### M3 — 全功能页面
- 12 个功能页 + 设置 + 更新对话框, 与 Python 版对齐验收

### M4 — Shield 移植决策
- 方案 a: onnxruntime Rust 绑定直跑 anime_rating/censor 两个 ONNX 模型
  (需移植 imgutils 的预处理管线, 工作量最大)
- 方案 b: 首版不带 Shield, Python 版作为 Shield 伴侣工具并存

### M5 — 打包与热更新
- tauri bundler (nsis) + zip 产物; ffmpeg 仍外置 bin/ (体积大头不变, 可后续按需下载)
- 更新器: 替换单体 exe + resources, 复用「备份-替换-重启」模型

## 与 Python 版的对照表

| Python | Rust (engine/) |
|---|---|
| `src/core.py` | `engine/src/ffmpeg.rs` |
| `src/updater.py` 版本比较 | `engine/src/version.rs` |
| `src/media_probe.py` | `engine/src/probe.rs` (M1) |
| `src/qc.py` `batch_renamer.py` `folder_creator.py` | `engine/src/qc.rs` `batch.rs` (M1) |
| `src/image_converter.py` | `engine/src/image.rs` (M1, image crate) |
| `src/notify*.py` | `engine/src/notify.rs` (M1, ureq) |
| `src/ui/**` | `app/src/**` (M2-M3) |
