# PyQt6 图形界面重构方案

## 1. 背景与动机

小雪工具箱原先使用 [Gooey](https://github.com/chriskiehl/Gooey) 框架构建 GUI。Gooey 基于 wxPython，通过装饰 argparse 自动生成界面，开发效率高但定制能力有限：

- 无法自定义控件交互逻辑（如选择"自定义"预设时动态显示/隐藏参数组）
- 无法实现任务进度条、实时日志过滤等高级 UI 功能
- Gooey 项目维护频率低，社区活跃度不高
- 界面样式定制受限于 Gooey 提供的配色参数

迁移到 **PyQt6** 后获得的能力：

- 完全自定义的 UI 布局和控件
- 响应式控件联动（预设选择自动填充参数、模式切换隐藏/显示控件）
- 异步任务管理（QThread + Signal/Slot）
- 实时日志面板（ANSI 颜色渲染）
- 文件拖放支持
- 主题/样式表切换

---

## 2. 设计原则

- **业务逻辑零改动**：`src/executors/`、`src/core.py`、`src/presets.py`、`src/encode_params.py` 等模块完全不变
- **参数契约不变**：各 executor 函数仍接收 `argparse.Namespace` 兼容对象，PyQt 表单收集参数后构造同样结构的对象传入
- **保持侧边栏导航风格**：用户使用习惯不变
- **渐进式迁移**：按模块逐步替换，每一步可独立运行和测试

---

## 3. 重构后的架构

```
┌──────────────────────────────────────────────────────────┐
│                      main.py                             │
│                  (PyQt6 应用入口)                         │
└────────────────────────┬─────────────────────────────────┘
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
   ┌────────────┐  ┌───────────┐  ┌──────────────┐
   │  src/ui/   │  │ executors │  │ notify_config│
   │  (GUI 层)  │  │  (业务)   │  │   (配置)     │
   └─────┬──────┘  └─────┬─────┘  └──────────────┘
         │               │
         └───────┬───────┘
                 ▼
        ┌─────────────────┐
        │  core / presets  │
        │    (核心功能)    │
        └─────────────────┘
```

### 目录结构

```
小雪工具箱/
├── main.py                      # PyQt6 应用入口
├── requirements.txt             # Python 依赖 (PyQt6 替代 Gooey)
├── XiaoXueToolbox.spec          # PyInstaller 打包配置
├── bin/                         # FFmpeg 和 AviSynth 依赖
├── src/
│   ├── gui_config.py            # GUI 配置常量 (窗口尺寸/图标)
│   ├── ui/                      # PyQt6 界面层 (新增)
│   │   ├── __init__.py
│   │   ├── main_window.py       # 主窗口 (侧边栏 + 堆叠页面 + 日志面板)
│   │   ├── sidebar.py           # 侧边栏导航组件
│   │   ├── log_panel.py         # 日志/终端输出面板 (ANSI 颜色)
│   │   ├── task_runner.py       # QThread 异步任务执行器
│   │   ├── base_tab.py          # Tab 页面基类 (通用控件辅助)
│   │   ├── args_builder.py      # argparse.Namespace 兼容参数构建
│   │   ├── theme.py             # QSS 样式表管理
│   │   └── tabs/                # 各功能页面
│   │       ├── __init__.py
│   │       ├── encode_tab.py        # 视频压制
│   │       ├── replace_audio_tab.py # 音频替换
│   │       ├── remux_tab.py         # 封装转换
│   │       ├── qc_tab.py            # 素材质量检测
│   │       ├── extract_av_tab.py    # 音视频抽取
│   │       ├── media_probe_tab.py   # 媒体元数据检测
│   │       ├── image_convert_tab.py # 图片转换
│   │       ├── folder_creator_tab.py# 文件夹创建
│   │       ├── batch_rename_tab.py  # 批量重命名
│   │       ├── shield_tab.py        # 露骨图片识别
│   │       ├── notification_tab.py  # 通知设置
│   │       └── help_tab.py          # 使用说明
│   ├── presets.py               # 编码器/预设配置 (不变)
│   ├── core.py                  # FFmpeg 命令构建 (不变)
│   ├── executors/               # 执行器模块 (不变)
│   └── ...                      # 其余模块 (不变)
└── tests/                       # 测试用例 (不变)
```

---

## 4. 核心组件说明

### 4.1 主窗口 (`main_window.py`)

布局采用 QHBoxLayout（侧边栏 + 右侧区域），右侧使用 QSplitter 上下分割功能页面和日志面板。

```
+------------------------------------------------------------------+
|  菜单栏 (关于 / 帮助文档 / 主页链接)                                |
+----------+-------------------------------------------------------+
|          |                                                       |
|  侧边栏   |              功能页面 (QStackedWidget)                  |
|  导航列表  |              各功能 Tab 的表单控件                      |
| (QListW.) |                                                       |
|          +-------------------------------------------------------+
|          |  [开始执行]  [停止]  [清空日志]          [进度条]        |
|          +-------------------------------------------------------+
|          |              日志输出面板 (QTextEdit)                   |
|          |  支持 ANSI 颜色渲染                                     |
+----------+-------------------------------------------------------+
|  状态栏: 就绪 | v1.9.0                                            |
+------------------------------------------------------------------+
```

### 4.2 异步任务执行 (`task_runner.py`)

继承 `QThread`，在工作线程中运行 executor 函数。通过重定向 `sys.stdout` / `sys.stderr` 到自定义对象，将 `print()` 输出实时转发到日志面板。

关键信号：
- `log_signal(str)` — 日志文本
- `finished_signal(bool, str)` — 任务完成 (成功/失败, 命令名)

### 4.3 参数构建 (`args_builder.py`)

`ArgsNamespace` 类兼容 `argparse.Namespace`，每个 Tab 的 `build_args()` 方法从表单控件收集值，构造此对象传给 executor。

### 4.4 Tab 页面基类 (`base_tab.py`)

提供通用控件创建辅助方法，每个功能页面只需调用辅助方法创建表单并实现 `build_args()`：

| Gooey 控件            | PyQt6 控件                     |
|-----------------------|-------------------------------|
| `FileChooser`         | `FileDropLineEdit` + `QPushButton` (QFileDialog) |
| `FileSaver`           | `FileDropLineEdit` + `QPushButton` (QFileDialog) |
| `DirChooser`          | `FileDropLineEdit` + `QPushButton` (QFileDialog) |
| `MultiFileChooser`    | `FileDropLineEdit(multi)` + `QPushButton` |
| `Dropdown` / `choices`| `QComboBox`                   |
| `BlockCheckbox`       | `QCheckBox`                   |
| `TextField`           | `QLineEdit`                   |
| `Textarea`            | `QPlainTextEdit`              |
| `IntegerField`        | `QSpinBox`                    |

所有文件输入控件均支持 **拖放**（`FileDropLineEdit`）。

### 4.5 控件联动 (视频压制页)

- **预设选择联动**：切换质量预设时自动填充编码器、CRF/CQ 值、速度档位、音频设置
- **码率控制联动**：CRF/CQ 模式时禁用目标码率；VBR/CBR 模式时禁用质量值滑块

---

## 5. 依赖变更

```diff
- Gooey>=1.0.8
+ PyQt6>=6.5.0
  colorama>=0.4.6
  pyinstaller>=6.0.0
  Pillow>=9.0.0
  chardet>=4.0.0
  requests>=2.28.0
  pytest>=7.0.0
```

---

## 6. 变更文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `main.py` | 重写 | 移除 Gooey 装饰器，改为 PyQt6 QApplication 入口 |
| `src/gui_config.py` | 重写 | 移除 Gooey 配置字典，保留图标路径函数 |
| `src/gui_tabs.py` | 废弃 | 功能已迁入 `src/ui/tabs/` 各文件 |
| `src/ui/` (新目录) | 新增 | 全部 PyQt GUI 层代码 |
| `requirements.txt` | 修改 | `Gooey` → `PyQt6` |
| `XiaoXueToolbox.spec` | 修改 | hiddenimports 加入 PyQt6 模块 |
| `README.md` | 修改 | 更新技术栈徽章和描述 |

### 不变的文件

以下文件在重构中完全不变：

- `src/executors/` — 全部执行器
- `src/core.py` / `src/compat_encoder.py` — FFmpeg 命令构建
- `src/presets.py` / `src/encode_params.py` — 预设与参数
- `src/utils.py` / `src/log_utils.py` — 工具函数
- `src/notify.py` / `src/notify_config.py` — 通知模块
- `src/qc.py` / `src/media_probe.py` — 检测模块
- `src/batch_renamer.py` / `src/folder_creator.py` / `src/image_converter.py` — 文件操作
- `src/post_transfer.py` / `src/nsfw_detect.py` / `src/help_texts.py`
- `tests/` — 全部测试文件

---

## 7. PyInstaller 打包注意事项

- `XiaoXueToolbox.spec` 已在 `hiddenimports` 中添加 `PyQt6.QtWidgets`、`PyQt6.QtCore`、`PyQt6.QtGui`
- `console=False` 保持不变（窗口化应用）
- PyQt6 的 plugins 目录会被 PyInstaller 自动识别打包

---

## 8. 风险与应对

| 风险 | 应对策略 |
|------|---------|
| **stdout 捕获** | 通过 `_StreamRedirect` 类在 QThread 中重定向 stdout/stderr 到 signal |
| **子进程管理** | FFmpeg 子进程在 QThread 中执行；点击"停止"时 terminate 线程 |
| **跨平台兼容** | PyQt6 原生跨平台，Windows 高 DPI 通过 Qt 自动处理 |
| **打包体积** | PyQt6 比 wxPython 略大，可通过 PyInstaller `--exclude-module` 优化 |
| **GPL 许可证** | PyQt6 使用 GPL v3 许可；如需商业闭源可改用 PySide6 (LGPL) |

---

## 9. 如何添加新功能 (PyQt6 版)

### 步骤 1：定义预设（如需要）

在 `src/presets.py` 中添加常量（与之前相同）。

### 步骤 2：创建执行器

在 `src/executors/` 中创建执行器文件（与之前相同）。

### 步骤 3：创建 Tab 页面

在 `src/ui/tabs/` 下创建新文件：

```python
# src/ui/tabs/my_feature_tab.py
from ..base_tab import BaseTab
from ..args_builder import ArgsNamespace

class MyFeatureTab(BaseTab):
    def __init__(self, parent=None):
        super().__init__("我的新功能", parent)

        io = self.add_group("输入/输出设置")
        self.input_edit = self.add_file_chooser(
            io, "输入文件", "所有文件 (*.*)",
        )
        self.param_combo = self.add_combo(
            io, "参数", ["选项A", "选项B"], "选项A",
        )
        self.add_stretch()

    def build_args(self):
        return ArgsNamespace(
            command=self.command_name,
            input=self.input_edit.text(),
            my_param=self.param_combo.currentText(),
        )
```

### 步骤 4：注册 Tab

在 `src/ui/tabs/__init__.py` 中导出：

```python
from .my_feature_tab import MyFeatureTab
```

在 `src/ui/main_window.py` 的 `tab_defs` 列表中添加：

```python
("我的新功能", MyFeatureTab(), execute_my_feature),
```

### 步骤 5：添加命令分发

如需自动通知，在 `main_window.py` 的 `_AUTO_NOTIFY_COMMANDS` 集合中添加命令名。

### 步骤 6：编写测试、更新文档

与之前流程相同。
