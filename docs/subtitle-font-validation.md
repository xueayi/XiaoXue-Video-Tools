# macOS 字幕字体增强验收

随 `v3.1.0` 发布；`v2.3.0` 及更早版本不包含本功能。

## 使用步骤

在视频压制页选择视频与 ASS/SSA，字幕处理方式选择「内嵌（烧录进画面）」。Mac 探测到 FFmpeg 的 subtitles 滤镜后，可勾选「字体兼容增强」。添加字体目录、字体文件或 ZIP，点击「检查字体」，逐项核对实际字形、字重与来源。修改字幕或字体来源后需要重新检查。

自动匹配遇到同名文件时，选择具体字形；也可将指定字幕字体映射到其他字体。映射只修改任务字幕副本里的样式 Fontname 与行内 `\fn`，保留文字、时间、色彩头、动画和其他样式。默认严格检查；勾选「允许字体替换」可带警告继续，警告会进入任务结果。

输入原片时间或使用原片预览当前帧，再点击「字幕效果快照」。快照按源时间解码并烧录字幕，显示实际取帧时间及输出缩放。它不模拟压缩损失，不是实时效果播放器；某帧未出现的样式不标为实际验证通过。字体检查和快照可取消，切换输入会丢弃过期结果，关闭页面会清理临时资源。

首版限 Mac ASS/SSA 烧录；SRT、软字幕内封、视频流复制、AviSynth、可变字体和变换标签中的字体变化不启用增强。Windows AviSynth/VSFilter 路径保持原有行为。字体匹配通过不代表与 VSFilter 排版、特效逐像素一致。

## 固定素材与字体

测试目录：`/Volumes/192.168.6.27/local_share/mac兼容性测试文件`。整理后的字体在其 `字体整理/` 目录，含四个文件、来源说明和 SHA256SUMS。源视频、ASS 和字体没有被修改，也未安装到系统。

| 文件 | 用途 | 真实字重 |
| --- | --- | --- |
| NotoSansSC-Medium.otf | 正文/滚动原字体 | 500 |
| NotoSerifCJKsc-Black.otf | 标题原字体 | 900 |
| NotoSerifCJKsc-Regular.otf | Regular 对照 | 400 |
| MiSans-Medium.ttf | 用户显式替换对照 | 500 |

Noto Sans 来自固定官方提交，其余来自共享目录。完整来源、成员路径和 SHA256 固定于 `tests/fixtures/subtitle_compat/262_manifest.json`。用户全字体和视频不提交 Git。MiSans 缺少本字幕中的 `・`（U+30FB），因此严格模式下整份字幕映射应被拒绝；允许替换的测试保留缺字警告。

## 2026-10-18 验证结果

- 本机全量回归：1776 通过、4 个仅 Windows 用例跳过；已配置共享目录的外部素材用例实际执行。
- 真实媒体：FFmpeg 9.0.2、libass 0.17.5；9 个动画边界快照通过，19 秒实际命中 Noto Sans Medium / Serif Black，未回退系统字体。
- 13 秒样本分别通过 libx264 CRF、CPU 两遍、Apple VideoToolbox 导出。原片多段重排得到 638 帧，音画收尾在帧/音频样本容差内。
- 完整导出仅运行一次：2160×1080、60fps、22082 帧、368.033333 秒，H.264/AAC 流有效，音视频时长一致，两个字体均实际验证通过。源视频、ASS 和四份缓存字体 SHA256 均保持不变。
- 自制双字体的快照与无损导出帧逐像素相同；重排片段中的淡入按原片时间保持。真实 262 的关键帧已留图供观察，不以整幅平均误差冒充字幕 ROI 比对。
- 自包含 arm64 应用在限制 PATH、未安装系统 Noto 的环境，通过共享目录与原 ZIP 导入、19 秒快照；无需额外 PyInstaller hidden imports。包内 FFmpeg 的 Apple H.264/HEVC/VBR、CPU H.264/HEVC 两遍、片段、字幕、取消、冻结启动与重启烟测通过。
- Windows 全套 CI：待本分支 PR 运行后记录。Windows VSFilter 参考帧未提供，跨渲染器画面对照明确为 `not_run`。

复现：

```bash
QT_QPA_PLATFORM=offscreen XIAOXUE_NO_UPDATE_CHECK=1 \
XIAOXUE_SUBTITLE_TEST_ROOT='/Volumes/192.168.6.27/local_share/mac兼容性测试文件' \
.venv/bin/python -m pytest -q

.venv/bin/python tools/validate_subtitle_compat.py \
  --corpus-root '/Volumes/192.168.6.27/local_share/mac兼容性测试文件' \
  --font-cache '/本地字体缓存' --output build/subtitle-compat-262 \
  --download-missing-fonts

.venv/bin/python tools/smoke_macos.py --app dist/小雪工具箱.app
```

验收工具仅在显式指定 `--download-missing-fonts` 且共享目录/缓存缺失时下载固定的官方 Noto Sans，并校验 SHA256；产品不会自动下载字体。输出包含 manifest、实际字体报告、前后校验和、快照、导出视频和日志。外部素材测试未配置时显式跳过，配置后断卷或缺文件视为失败。

冻结包诊断入口（供构建验收）：

```bash
小雪工具箱.app/Contents/MacOS/XiaoXueToolbox \
  --subtitle-diagnostics '/视频.mp4' --subtitle '/字幕.ass' \
  --font-source '/字体目录或ZIP' --time 19 --report '/报告.json'
```

这个入口在应用进程内运行同一个异步字体面板，输出报告、字幕帧和面板截图，退出码反映是否成功；支持重复传入 `--font-source`。
