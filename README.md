# 小雪工具箱 (XiaoXue Video Toolbox)

一个简单的的视频压制与素材质量检测工具。基于 Python + Gooey 图形界面，内置 FFmpeg，开箱即用。

## ✨ 功能一览

| 功能 | 说明 |
|------|------|
| **视频压制** | 支持 H.264/H.265 编码，内置三档预设（标准/极致/速度），可选字幕烧录 |
| **音频替换** | 替换视频原有音轨，保留视频画面不变 |
| **转封装** | 容器格式转换 (如 MKV → MP4)，不重新编码，秒速完成 |
| **质量检测** | 递归扫描文件夹，检测 PR 不兼容格式、码率/分辨率阈值，输出报告 |
| **音频抽取** | 从视频中提取音频轨道，支持 MP3/AAC/WAV/FLAC 格式 |

## 从发布包运行

在release页下载打包好的exe文件，直接运行即可。

## 🚀 从源代码运行

### 前置条件：下载 FFmpeg

源代码仓库不包含 FFmpeg 二进制文件，需要手动下载放入 `bin/` 目录。

**方式一：下载 LGPL 精简版 (推荐，约 80MB)**
```powershell
# Windows PowerShell
Invoke-WebRequest -Uri "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-lgpl.zip" -OutFile "ffmpeg.zip"
Expand-Archive -Path "ffmpeg.zip" -DestinationPath "ffmpeg_temp"
New-Item -ItemType Directory -Force -Path "bin"
Copy-Item "ffmpeg_temp\ffmpeg-master-latest-win64-lgpl\bin\ffmpeg.exe" -Destination "bin\"
Copy-Item "ffmpeg_temp\ffmpeg-master-latest-win64-lgpl\bin\ffprobe.exe" -Destination "bin\"
Remove-Item -Recurse -Force "ffmpeg_temp", "ffmpeg.zip"
```

**方式二：下载 GPL 完整版 (约 200MB，含更多编码器)**
- 下载地址：[BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds/releases)
- 选择 `ffmpeg-master-latest-win64-gpl.zip`
- 解压后将 `bin/ffmpeg.exe` 和 `bin/ffprobe.exe` 复制到项目 `bin/` 目录

### 安装依赖并运行

```bash
# 1. 安装 Python 依赖
pip install -r requirements.txt

# 2. 运行程序
python main.py
```

### 方式二：打包为独立 EXE 

```bash
# 安装 PyInstaller
pip install pyinstaller

# 打包
pyinstaller --name "小雪工具箱" --windowed --add-data "bin;bin" main.py

# 产物在 dist/小雪工具箱/ 目录下
```

> 📦 打包后直接使用exe运行即可

## 🎛️ 编码器支持

| 类型 | 编码器 | 说明 |
|------|--------|------|
| **CPU** | libx264 / libx265 | 通用，无需显卡 |
| **NVIDIA** | h264_nvenc / hevc_nvenc | 需要 N 卡 (GTX 10 系及以上) |
| **Intel** | h264_qsv | 需要 Intel 核显 (6 代及以上) |
| **AMD** | h264_amf | 需要 AMD 显卡 (RX 400 系及以上) |

## 📋 预设说明

- **【标准推荐】**：1080P/60FPS，CRF 20，适合日常视频投稿
- **【极致画质】**：保留原始分辨率，CRF 16，适合 AMV/高画质需求
- **【速度优先】**：使用 NVENC 硬件加速，快速出片

## 📁 目录结构

```
小雪工具箱/
├── main.py              # 主程序入口
├── requirements.txt     # Python 依赖
├── bin/                 # FFmpeg 工具
│   ├── ffmpeg.exe
│   └── ffprobe.exe
└── src/                 # 后端模块
    ├── core.py          # FFmpeg 命令构建
    ├── qc.py            # 质量检测逻辑
    ├── presets.py       # 编码器/预设配置
    └── utils.py         # 工具函数
```

## ⚠️ 注意事项

1. **中文路径**：已适配，但建议避免过长或特殊字符
2. **字幕编码**：烧录字幕建议使用 UTF-8 编码的 SRT/ASS 文件
3. **硬件加速**：如选择 NVENC/QSV/AMF 但设备不支持，FFmpeg 会报错
4. **自动化发布**：`git tag v*` 和 `git push origin v*` 可以自动触发 CI/CD 发布

## 📝 许可证

本项目代码采用 **MIT License** 开源。

### 第三方组件声明

本软件使用了以下开源组件：

| 组件 | 许可证 | 说明 |
|------|--------|------|
| **FFmpeg** | LGPL v2.1+ / GPL v2+ | 视频处理核心，详见 [ffmpeg.org/legal](https://ffmpeg.org/legal.html) |
| **Gooey** | MIT | Python GUI 框架 |
| **wxPython** | wxWidgets License | GUI 底层组件 |

> ⚠️ **FFmpeg 许可证说明**：本软件随附的 FFmpeg 二进制文件遵循 LGPL/GPL 许可证。如需商业使用，请确保遵守 FFmpeg 的许可条款。FFmpeg 的源代码可从 [ffmpeg.org](https://ffmpeg.org) 获取。
