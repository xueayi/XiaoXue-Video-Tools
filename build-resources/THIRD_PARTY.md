# macOS 包的第三方组件

- 小雪工具箱源码：MIT，https://github.com/xueayi/XiaoXue-Video-Tools
- PyQt6 / Qt：PyQt6 使用 GPLv3 或商业许可，Qt 及依赖许可文件随各框架收集。https://www.riverbankcomputing.com/software/pyqt/
- 原片预览使用 Qt Multimedia 自带的 FFmpeg 动态库（当前本机构建为 7.1.5，LGPLv2.1-or-later），与压制导出用的独立 FFmpeg 不同。随 PyQt6 更新时需重新核对其版本和许可。https://doc.qt.io/qt-6/qtmultimedia-index.html
- FFmpeg / ffprobe：本构建为 GPLv3-or-later；具体版本、来源及归档 SHA256 见本目录 media-build.json，编译器许可证输出见 FFmpeg-license.txt。
- 媒体构建与源码脚本：https://git.martin-riedl.de/ffmpeg/build-script
- FFmpeg 源码：https://git.ffmpeg.org/ffmpeg.git （对应 n9.0.2）
- x264：https://code.videolan.org/videolan/x264
- x265：https://bitbucket.org/multicoreware/x265_git
- libass：https://github.com/libass/libass

Python、Pillow、requests、qtawesome 等的版权和许可见各自发行包。此文件不改变任何第三方组件的许可。
