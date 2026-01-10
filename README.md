# 小雪工具箱 (XiaoXue Video Toolbox)

一个简洁实用的视频压制与素材管理工具。基于 Python + Gooey 图形界面，内置 FFmpeg，开箱即用。

**仓库地址**: https://github.com/xueayi/XiaoXue-Video-Tools

---

## 功能一览

### 视频压制

支持 H.264/H.265 编码，内置三档画质预设（均衡/极致/速度），可选字幕烧录。

- **多编码器支持**: CPU (libx264/libx265)、NVIDIA NVENC、Intel QSV、AMD AMF
- **灵活的码率控制**: CRF/CQ 恒定质量、VBR 可变码率、CBR 恒定码率、真 2-Pass 编码
- **硬件加速失败智能提示**: 自动检测 NVENC/QSV/AMF 错误，给出驱动下载链接和解决建议

### 封装转换 (Remux)

容器格式快速转换，不重新编码，保留原始画质。

- **预设格式**: MP4、MKV、MOV、TS、WEBM、MXF、AVI
- **批量处理**: 选择文件夹一键批量转换

### 素材质量检测 (QC)

递归扫描文件夹，检查视频和图片的兼容性与质量。

- **软件兼容性检查**: 检测 MKV/WebM/FLV 等可能导致剪辑软件不兼容的容器格式
- **编码兼容性检查**: 标记 VP9/AV1/Theora 等需要额外解码器的编码
- **图片文件头检测**: 通过读取二进制头魔数（Magic Bytes）检测图片真实格式，发现扩展名与实际格式不匹配的伪装文件（如 .jpg 实际为 PNG）
- **阈值检查**: 最大/最小码率、最大/最小分辨率
- **可配置规则**: 自定义不兼容容器、编码、图片格式列表

### 音频处理

- **音频替换**: 保留视频画面，替换整条音轨
- **音频抽取**: 从视频中提取音频，支持 MP3/AAC/WAV/FLAC 输出

### 图片格式转换

批量图片格式互转，支持 PNG/JPG/WEBP/BMP/GIF/TIFF。

- **质量控制**: JPEG/WEBP 可调节压缩质量 (1-100)
- **递归处理**: 可选保持原目录结构

### 批量文件管理

- **文件夹批量创建**: 从 TXT 文件读取名称列表，批量创建文件夹，自动处理非法字符
- **序列重命名**: 批量按序号重命名图片/视频，支持自定义前缀、起始序号、位数

### 任务通知

任务完成后自动发送通知，避免干等。

- **飞书通知**: 卡片消息，可配置颜色和标题
- **自定义 Webhook**: 支持任意 POST 请求，可编辑 Headers 和 Body

---

## 从发布包运行

在 [Release](https://github.com/xueayi/XiaoXue-Video-Tools/releases) 页面下载打包好的 EXE 文件，直接双击运行即可。

---

## 从源代码运行

### 前置条件：下载 FFmpeg

源代码仓库不包含 FFmpeg 二进制文件，需要手动下载并放入 `bin/` 目录，或安装到系统环境变量中。本项目需要 `ffmpeg.exe` 和 `ffprobe.exe`。

**方式一：下载 GPL 完整版 (推荐，约 200MB，含更多编码器)**
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

### 打包为独立 EXE

```bash
# 安装 PyInstaller
pip install pyinstaller

# 打包
pyinstaller --name "小雪工具箱" --windowed --add-data "bin;bin" main.py

# 产物在 dist/小雪工具箱/ 目录下
```

---

## 编码器支持

| 类型 | 编码器 | 说明 |
|------|--------|------|
| CPU | libx264 / libx265 | 通用，无需显卡 |
| NVIDIA | h264_nvenc / hevc_nvenc | 需要 N 卡 (GTX 10 系及以上) |
| Intel | h264_qsv | 需要 Intel 核显 (6 代及以上) |
| AMD | h264_amf | 需要 AMD 显卡 (RX 400 系及以上) |

**说明**: 硬件编码器需要对应显卡驱动支持。程序会自动检测硬件编码失败，并给出驱动下载链接和切换到 CPU 编码的建议。

---

## 预设说明

| 预设 | 编码器 | 质量值 | 适用场景 |
|------|--------|--------|----------|
| 均衡画质 | libx264 | CRF 18 | 日常视频投稿，画质与体积均衡 |
| 极致画质 | libx264 | CRF 16 | AMV、4K、高动态场景 |
| 速度优先 | h264_nvenc | CQ 23 | NVIDIA 显卡加速，赶稿 |

---

## 目录结构

```
小雪工具箱/
├── main.py              # 主程序入口
├── requirements.txt     # Python 依赖
├── bin/                 # FFmpeg 工具
│   ├── ffmpeg.exe
│   └── ffprobe.exe
└── src/                 # 后端模块
    ├── core.py          # FFmpeg 命令构建、硬件编码错误检测
    ├── qc.py            # 素材质量检测、图片文件头检测逻辑
    ├── presets.py       # 编码器/预设配置
    ├── utils.py         # 工具函数
    ├── gui_tabs.py      # GUI 标签页定义
    ├── notify.py        # 飞书/Webhook 通知模块
    ├── image_converter.py  # 图片格式转换
    ├── folder_creator.py   # 批量文件夹创建
    ├── batch_renamer.py    # 批量序列重命名
    └── help_texts.py    # 使用说明文本
```

---

## 注意事项

1. **中文路径**: 已适配，但建议避免过长或包含特殊字符的路径
2. **字幕编码**: 烧录字幕建议使用 UTF-8 编码的 SRT/ASS 文件
3. **硬件加速**: 如选择 NVENC/QSV/AMF 但硬件不支持，程序会提示切换到 CPU 编码
4. **自动发布**: `git tag v*` 和 `git push origin v*` 可自动触发 GitHub Actions 构建发布

---

## 许可证

本项目代码采用 **MIT License** 开源。

### 第三方组件声明

本软件使用了以下开源组件：

| 组件 | 许可证 | 说明 |
|------|--------|------|
| FFmpeg | LGPL v2.1+ / GPL v2+ | 视频处理核心，详见 [ffmpeg.org/legal](https://ffmpeg.org/legal.html) |
| Gooey | MIT | Python GUI 框架 |
| wxPython | wxWidgets License | GUI 底层组件 |

**FFmpeg 许可证说明**: 本软件随附的 FFmpeg 二进制文件遵循 LGPL/GPL 许可证。如需商业使用，请确保遵守 FFmpeg 的许可条款。FFmpeg 的源代码可从 [ffmpeg.org](https://ffmpeg.org) 获取。
