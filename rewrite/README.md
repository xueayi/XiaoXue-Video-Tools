# 小雪工具箱 原生重写路线图 (rewrite/tauri)

> 目标: 用 Tauri 2 (Rust 后端 + React/TypeScript 前端) 重写小雪工具箱,
> 换取 启动 <0.5s / 内存 ~100MB / 壳体积 <20MB / Web 级 UI 上限。
> 业务本质是「ffmpeg 编排器」, Rust 标准库即可覆盖全部编排逻辑。
>
> **范围决定 (2026-09-12): 重写版不包含 Shield (露骨图片识别)**。
> 该功能依赖 imgutils/onnxruntime 的 Python 生态, 移植成本与收益不成比例;
> 需要此功能的用户请继续使用 Python 版 (两版长期并存)。

## 决策记录

| 决策点 | 选择 | 理由 |
|---|---|---|
| 壳框架 | Tauri 2 | 体积/安全性优于 Electron 与 Wails; WebView2 随 Win10+ 系统内置 |
| 前端 | React 18 + TS + Fluent UI React v9 | 与现有 Fluent 设计语言延续, 视觉上限最高 |
| 后端 | 纯 Rust std + serde_json | ffmpeg 编排/ffprobe 解析无需重依赖 |
| 仓库形态 | 与 Python 版同仓库, `engine/` + `app/` 共存 | 逻辑可并行对照迁移, Python 版继续作为生产版本 |
| 热更新 | 单体二进制替换 (M5) | 比 PyInstaller 布局更简单; ffmpeg 目录按需更新 |

## 本地开发前置

```powershell
winget install Rustlang.Rustup        # Rust (GNU 工具链, 免 MSVC)
winget install OpenJS.NodeJS.LTS      # Node 20+
```

## 日常命令

```powershell
# 构建前端 + 运行应用 (窗口直接加载打包好的静态文件)
cd app && npm run build
cd app/src-tauri && cargo run

# 前端热重载开发 (需两个终端)
cd app && npm run dev                          # 终端 1: vite 服务
cd app/src-tauri && cargo run --features ...   # 或
npx tauri dev --config src-tauri/tauri.dev.conf.json   # 挂载 devUrl 覆盖

# 发版打包 (NSIS + 绿色 exe)
cargo install tauri-cli --version "^2"
cd app && npx tauri build
```

> 注意: 主配置不带 devUrl —— 否则 debug 构建的窗口会去连
> localhost:5173, 而 cargo run 单独启动时 vite 并未运行,
> 窗口报 ERR_CONNECTION_REFUSED (实测踩坑)。热重载用
> tauri.dev.conf.json 覆盖。

## 里程碑

### M0 — 引擎 crate 骨架 ✅ (已完成)
- `engine/`: Rust crate, 承载全部可测业务逻辑
- 已移植: 版本比较 (`version.rs`) / ffmpeg 流映射与编码命令构建 (`ffmpeg.rs`)
- CI: `.github/workflows/rewrite.yml` — cargo test + clippy

### M1 — 引擎逻辑补全 ✅ (已完成)
- `ffmpeg.rs`: 音视频抽取命令 / 真 2-Pass 构建 / run_ffmpeg (流式进度回调) /
  run_2pass_encode (临时文件清理)
- `probe.rs`: ffprobe JSON 宽松反序列化 -> MediaInfo / 进程调用 / 报告格式化
- `folder.rs`: TXT 编码解码 (UTF-8/BOM/GBK) / 批量建目录
- `batch.rs`: 批量重命名 (收集/排序/分组编号/三种模式/防覆盖)
- `notify.rs`: 飞书卡片 + Webhook (ureq, 30s 超时)
- `paths.rs`: ffmpeg/ffprobe 定位
- 54 个 cargo 测试全绿, clippy 零警告 (本地 GNU + CI MSVC 双工具链验证)

### M2 — Tauri 壳 + 首个页面 (下一步)

### M2 — Tauri 壳 + 首个页面
- `app/`: Tauri 2 + Vite + React + TS
- 设计系统: Fluent UI React v9, 暗色主题, 沿用现有设计令牌
- 首页: 视频压制 (命令预览/进度/日志 WebSocket 推流)

### M3 — 全功能页面
- 12 个功能页 + 设置 + 更新对话框, 与 Python 版对齐验收

### M4 — 打包与热更新 (进行中)
- 本地 `npx tauri build` 出 NSIS 安装包 + 绿色单体 exe (前端已内嵌)
- 发版工作流: rewrite-release.yml (tag `rw-v*` 触发, prerelease)
- 热更新: 单体 exe 替换模型 (比 PyInstaller 布局简单)

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
| `src/nsfw_detect.py` (Shield) | **不移植** — Python 版独有功能 |
