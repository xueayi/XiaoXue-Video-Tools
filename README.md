# 小雪工具箱 (XiaoXue Video Toolbox)

<p align="center">
  <img src="image/小雪工具箱2.png" width="200" alt="小雪工具箱 Logo">
</p>

![Python](https://img.shields.io/badge/Python-3.8+-3776AB?logo=python&logoColor=white)
![FFmpeg](https://img.shields.io/badge/FFmpeg-007808?logo=ffmpeg&logoColor=white)
![Gooey](https://img.shields.io/badge/Gooey-GUI-4B8BBE)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

一个简洁实用的视频压制与素材管理工具。基于 Python + Gooey 图形界面，内置 FFmpeg，开箱即用。

---

## 功能一览

### 视频压制

支持 H.264/H.265 编码，内置四档画质预设，可选字幕烧录。

- **编码器**: CPU (libx264/libx265)、NVIDIA NVENC、Intel QSV、AMD AMF
- **码率控制**: CRF/CQ 恒定质量、VBR 可变码率、CBR 恒定码率、真 2-Pass 编码
- **NVENC 档位**: p1(最快) ~ p7(最慢) 可调
- **Debug 模式**: 仅输出 FFmpeg 命令，不实际执行

### 预设说明

| 预设        | 编码器     | 质量值 | 速度   | 适用场景    |
| ----------- | ---------- | ------ | ------ | ----------- |
| 均衡画质    | libx264    | CRF 18 | medium | 日常投稿    |
| 极致画质    | libx264    | CRF 16 | slow   | AMV/4K      |
| 速度优先    | h264_nvenc | CQ 23  | p4     | NVIDIA 加速 |
| 画质优先 HQ | h264_nvenc | CQ 19  | p7     | N 卡高画质  |

### 字幕兼容模式

当字幕字体显示异常时，可开启兼容模式：

- **便携设计**: 无需安装 AviSynth，解压即用
- **参数复用**: 所有编码参数与普通模式共用
- **自动清理**: 压制完成后自动删除临时文件

```mermaid
flowchart TD
    A[用户选择视频+字幕] --> B{兼容模式?}
    B -- 关闭 --> C[FFmpeg subtitles 滤镜]
    B -- 开启 --> D[临时修改 PATH 环境变量]
    D --> E[生成 .avs 脚本]
    E --> F[FFmpeg 读取 AVS + 原视频音频]
    F --> G[应用用户设置的编码参数]
    G --> H[输出最终视频]
    H --> I[清理临时文件]
```

### 其他功能

- **封装转换**: MP4/MKV/MOV/TS/WEBM/MXF，不重新编码
- **素材质量检测**: 码率/分辨率/兼容性检测，生成报告
- **音频处理**: 音频替换、音频抽取
- **图片转换**: PNG/JPG/WEBP/BMP/GIF/TIFF 互转
- **批量文件管理**: 文件夹批量创建、序列重命名
- **任务通知**: 飞书通知、自定义 Webhook
- **露骨图片识别** *(Shield 增强版)*: B 站过审风险检测，自动打码

---

## 快速开始

### 从发布包运行

在 [Release](https://github.com/xueayi/XiaoXue-Video-Tools/releases) 页面下载：

| 版本                                           | 说明                              |
| ---------------------------------------------- | --------------------------------- |
| `XiaoXueToolbox_vX.X.X_Windows_x64.zip`        | 标准版，体积较小                  |
| `XiaoXueToolbox_vX.X.X_Shield_Windows_x64.zip` | Shield 增强版，含露骨图片识别功能 |

解压后双击 `XiaoXueToolbox.exe` 运行即可。

### 从源代码运行

```bash
# 1. 下载 FFmpeg 并放入 bin/ 目录
# 推荐: https://github.com/BtbN/FFmpeg-Builds/releases

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行程序
python main.py
```

### 运行测试

```bash
# 安装 pytest (已包含在 requirements.txt)
pip install pytest

# 运行所有测试
python -m pytest tests/test_encode_params.py -v --tb=short

# 运行特定测试类
python -m pytest tests/test_encode_params.py::TestNvencPresetOverride -v
```

---

## 目录结构

```
小雪工具箱/
├── main.py              # 主程序入口
├── requirements.txt     # Python 依赖
├── requirements-shield.txt  # Shield 版额外依赖
├── bin/                 # FFmpeg 和 AviSynth 依赖
│   ├── ffmpeg.exe
│   ├── ffprobe.exe
│   ├── AviSynth.dll     # AviSynth 核心
│   ├── LSMASHSource.dll # 视频解码插件
│   └── VSFilter.dll     # 字幕渲染插件
├── src/                 # 后端模块
│   ├── core.py          # FFmpeg 命令构建
│   ├── compat_encoder.py   # 兼容模式 (AviSynth + VSFilter)
│   ├── encode_params.py    # 编码参数数据类
│   ├── presets.py       # 编码器/预设配置
│   ├── qc.py            # 素材质量检测
│   ├── utils.py         # 工具函数
│   ├── gui_tabs.py      # GUI 标签页定义
│   ├── notify.py        # 通知模块
│   ├── nsfw_detect.py   # 露骨图片识别 (Shield)
│   ├── image_converter.py  # 图片格式转换
│   ├── folder_creator.py   # 批量文件夹创建
│   ├── batch_renamer.py    # 批量序列重命名
│   └── help_texts.py    # 使用说明文本
└── tests/               # 测试用例
    ├── conftest.py      # pytest fixtures
    └── test_encode_params.py  # 编码参数测试
```

---

## 许可证

本项目代码采用 **MIT License** 开源。

### 第三方组件声明

| 组件         | 许可证               | 说明                    |
| ------------ | -------------------- | ----------------------- |
| FFmpeg       | LGPL v2.1+ / GPL v2+ | 视频处理核心            |
| AviSynth     | GPL v2+              | 视频处理框架 (兼容模式) |
| LSMASHSource | ISC License          | 视频解码插件            |
| VSFilter     | GPL v2+              | 字幕渲染插件            |
| Gooey        | MIT                  | Python GUI 框架         |
| wxPython     | wxWidgets License    | GUI 底层组件            |

**注意**: 兼容模式使用的 AviSynth、LSMASHSource、VSFilter 均为开源组件。相关源代码可从各自的官方仓库获取。
