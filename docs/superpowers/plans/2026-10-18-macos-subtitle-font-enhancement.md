# Mac 字幕字体兼容增强 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Mac 视频压制页提供字体兼容增强，让指定素材正确使用 Medium/Black 等实际字形，展示缺失/替换情况，并通过同一 FFmpeg/libass 链路检查字幕效果。

**Architecture:** 继续使用现有 FFmpeg/libass；新增字幕分析、字体索引和任务字体准备三个职责明确的后端模块，再接入现有普通/两遍/片段编码。默认直接使用原 ASS 和 `fontsdir`；只有用户设置名称映射时才生成字幕临时副本。字体信息和关键帧检查在后台执行。

**Tech Stack:** Python >=3.12、PyQt6、项目固定的 FFmpeg 9.0.2 / libass 0.17.5、fonttools==4.67.0、pytest、Pillow。fontTools 只读取字体元数据和生成测试字体，首版不修改字体内部名称和轮廓。

**Spec:** [前置可行性评估](/Volumes/WD_SN730/01_dev/XiaoXue/macos-assessment/2026-10-18/subtitle-compat/assessment.md)；本计划中的“素材与实测”和“全局约束”补充用户提供素材后已确定的需求。用户要求本轮交付 plan，尚未开始产品代码实现。

## 素材与实测

测试源目录：`/Volumes/192.168.6.27/local_share/mac兼容性测试文件`。该目录只读使用，所有产物写入项目 build 或本机测试缓存。

| 输入 | 已核实的属性 |
| --- | --- |
| `262_缩混.mp4` | 475060341 字节；H.264/AAC；2160×1080；60fps；368.033333 秒；视频和音频 start_time 均为 0；无色彩标签 |
| `262_缩混.ass` | 117618 字节；UTF-8；PlayRes 2160×1080；6 个样式、65 条 Dialogue；实际使用正文/滚动/标题 3 个样式；字幕范围 16.02–325.48 秒 |
| 字幕布局 | WrapStyle=0；ScaledBorderAndShadow=yes；YCbCr Matrix=None；包含逐字透明度变换、淡入淡出、move、clip、iclip；当前没有行内 fn 覆盖 |
| `09_NotoSerifCJKsc.zip` | 用户提供；含 Black、Regular 等 7 个静态 OTF 字重；Black 成员路径 `OTF/SimplifiedChinese/NotoSerifCJKsc-Black.otf` |
| `MiSans/MiSans 开发下载字重/` | 用户提供的 10 个 TTF 字重；包含 Medium；同目录还有 `__MACOSX`、`._` 附属文件，扫描时排除 |

原 ASS SHA256：`f81528ff9c91b65def18e6a2226468141d2c2234213a4be5860e2a7059001cc3`。

| 用途 | 字体与目标 | SHA256 |
| --- | --- | --- |
| 正文/滚动 | Noto Sans SC Medium；PostScript=NotoSansSC-Medium；OS/2 weight=500 | `7633f5a016d4dd95e685a69633d818aabc4644c4b08e26bd35b1b30c45ed5dda` |
| 标题 | Noto Serif CJK SC Black；PostScript=NotoSerifCJKsc-Black；weight=900 | `0f856ec0ba328cf9660e217fab96157c804d657d7731dd109c37c3979bf27489` |
| 错误字重对照 | Noto Serif CJK SC Regular；weight=400 | `18e4072f01dad3965a72ae8afee7d6dac447c4eb6d454e0084ed5c9c1fc0091f` |
| 用户显式替换测试 | MiSans Medium；PostScript=MiSans-Medium；weight=500 | `93528275ee67039c1daeb2ef700625bcf72abab2d3f97e1b6afae6273b579fc1` |

Sans Medium 原目录缺失，已按用户授权从官方仓库下载到本机测试缓存：
`https://raw.githubusercontent.com/notofonts/noto-cjk/f8d157532fbfaeda587e826d4cd5b21a49186f7c/Sans/SubsetOTF/SC/NotoSansSC-Medium.otf`。

**已完成的规划前探测：** 使用此前 Mac 包内 FFmpeg，原片帧 975 / 1140 / 1500，即 16.25 / 19.00 / 25.00 秒，分别覆盖标题裁切、正文逐字动画和滚动字幕。无配套字体时两个字体都回退到 PingFangSC-Regular，退出码仍为 0；加载字体目录后正确选中 NotoSansSC-Medium 与 NotoSerifCJKsc-Black。已查看 19 秒前后两种输出，标题字形和字重差异明显。

证据目录：`/Volumes/WD_SN730/01_dev/XiaoXue/macos-assessment/2026-10-18/subtitle-compat/user-materials/`，含 inventory.json、font-sources.json、原样/加 fontsdir 的日志与 6 张 PNG。本轮没有进行完整成片压制或 Windows VSFilter 对照。

## Global Constraints

- Python >=3.12；首版产品入口面向 macOS 13+ Apple Silicon，后端纯 Python 测试须在 Windows 运行；保留 Windows 原有 AviSynth/VSFilter 模式。
- 使用项目固定 FFmpeg，不依赖系统 Homebrew FFmpeg 或系统安装字体；不要求安装 AviSynth、VapourSynth 或 Wine。
- 增强默认关闭；ASS/SSA 首版可启用，SRT 沿用现有普通烧录并显示“字体增强暂支持 ASS/SSA”。不把新选项设为旧 `compat_mode=True`。
- 开启增强后默认严格检查：缺字体、字形歧义或可见字符覆盖不足时先阻止导出；用户可明确选择“允许字体替换”，结果必须保留 warnings，不能显示“字体全部匹配”。
- ASS 的 Bold=0 不等于要求字体文件 weight=400：全名字体 Noto Sans SC Medium / Noto Serif CJK SC Black 必须命中其 500 / 900 字形。
- 不改源视频、源 ASS、源字体和共享目录；不安装系统字体；ZIP、字体目录和字幕均复制/准备到可清理的本地任务目录。用户已授权缺失测试字体从网上下载，下载只针对测试缓存，不加入产品启动流程。
- 保留字幕原有文字、时间、样式、分辨率、色彩头、透明度、裁切和动画；禁止全局 force_style=FontName 将所有样式覆盖为同一种字体。
- 普通编码、CPU 两遍和片段重排共用同一份准备结果。保持先按原片时间烧字幕、再截取拼接的顺序。
- 所谓效果预览为可取消的“当前时间点字幕快照”，不是实时效果播放器，不保证 Windows VSFilter 逐像素一致，也不证明压缩后像素一致。
- 本轮只生成计划。执行前重新查看工作区：该 checkout 正有其它功能修改涉及 core/encode_params/encode_tab；按函数和接口合并，保护已有修改，不按旧行号覆盖文件。

## Review Focus

1. 全名字体里的 Medium/Black 与 ASS Bold=0 并存时应选真正字形，不能用 Regular 伪加粗代替。（Task 2、6）
2. 滚动、逐字动画和行内字体切换/样式重置应保留原有时间与文本语义。（Task 1、3、6）
3. 共享卷断开、ZIP/目录混入 AppleDouble 文件、中文与特殊字符路径应给出可读结果并能取消。（Task 2、3、5）
4. 先前异步字体检查或快照在输入/字体被更换后才返回，不应覆盖新状态。（Task 5）
5. 字体准备、两遍第二遍、效果快照失败或取消后应清理临时目录，不能把失效准备结果用于下一次任务。（Task 3、4、5）

## 文件职责与接口约定

| 文件 | 职责 |
| --- | --- |
| 新增 `src/subtitle_document.py` | 只读分析 ASS/SSA、识别正在使用的字体及可见字符；按字体名称局部改写临时副本 |
| 新增 `src/subtitle_fonts.py` | 字体来源展开、TTF/OTF/TTC 元数据索引、匹配与问题报告；不依赖 Qt |
| 新增 `src/subtitle_render.py` | 任务临时目录、纯字幕滤镜构造、字体选择日志汇总、单帧渲染；禁止模块顶层反向导入 core |
| 新增 `src/ui/subtitle_font_panel.py` | 字体来源、匹配表、手动映射、严格/允许替换开关、时间点与快照展示 |
| 新增 `src/ui/subtitle_font_worker.py` | 后台检查/快照任务、TaskContext 取消、代次校验 |
| 修改 `src/encode_params.py`、`src/core.py`、`src/executors/video_executor.py` | 向现有编码链传递字幕渲染配置和准备结果 |
| 修改 `src/ui/tabs/encode_tab.py`、`src/ui/execution_summary.py` | 加入字体面板、参数快照、执行摘要和运行状态 |
| 新增 `tools/validate_subtitle_compat.py` | 固定素材验收，生成匹配报告、关键帧、短片段和校验记录 |
| 新增 `tests/fixtures/subtitle_compat/` | 自制微型 ASS、字体生成 factory 与外部素材 manifest；不提交用户视频或完整字体 |

以下模型均为不可变 dataclass；测试中的同名类型与字段必须保持一致：

- `FontRequest(name: str, bold: int, italic: bool)`：bold 保留 ASS 的 0/-1/数值语义，不提前把带字重的完整名称折算成 family+400。
- `SubtitleAnalysis(path: Path, requests: tuple[FontRequest, ...], codepoints: tuple[tuple[FontRequest, frozenset[int]], ...])`：requests 只涵盖实际使用的样式及覆盖标签，未使用的样式不阻止导出。
- `FontFace(path: Path, index: int, names: tuple[str, ...], full_name: str, postscript_name: str, weight: int, italic: bool, variable: bool, sha256: str)`：index 是 TTC face 下标，单字体为 0。
- `FontBinding(requested_name: str, face: FontFace)`：用户显式替换；由面板显示替换前后名称。
- `FontIssue(code: str, font_name: str, message: str)`；首版 code 固定为 missing、ambiguous、missing_glyph、unsupported、source_unavailable、fallback、unverified。
- `FontReport(matches: tuple[tuple[FontRequest, FontFace], ...], issues: tuple[FontIssue, ...], ready: bool, verified: bool=False)`：matches 关联请求和选中字形；ready 表示具备可验证字体条件。实际匹配由渲染日志确认，未触发全部相关请求时 verified 保持 False；这表示本次仅验证了部分画面，不因未出现的字体而判导出失败。严格模式拒绝实际 mismatch/fallback，不能只依据 verified=False 拒绝。
- `SubtitleFontOptions(enabled: bool=False, sources: tuple[str, ...]=(), bindings: tuple[FontBinding, ...]=(), allow_fallback: bool=False)`。
- `PreparedSubtitle(path: str, fonts_dir: str | None, report: FontReport)`：编码与快照共用；字体文件内容不改名、不改轮廓，复制到平铺目录时只改变磁盘文件名。
- `FontCheckError(ValueError)`：增强严格模式无法准备或验证字体时抛出，转换为 TaskResult.failed，reason=subtitle_fonts。

## Task 1：ASS 分析和不破坏动画的名称映射

**Files:** 新增 src/subtitle_document.py、tests/test_subtitle_document.py、tests/fixtures/subtitle_compat/mixed.ass。

**Interfaces:** 产出 `analyze_subtitle(path: Path) -> SubtitleAnalysis`、`rewrite_font_names(analysis: SubtitleAnalysis, mapping: dict[str, str], output: Path) -> Path`；定义本任务的 FontRequest / SubtitleAnalysis，其它模块直接导入。

- [ ] **Step 1 — 写失败测试：** `test_collect_used_styles_and_inline_fonts` 检查 Style/Dialogue 的 Format 列顺序、Text 中逗号、未使用样式、行内 fn / b / i / r / rStyleName；`test_mapping_preserves_animation_and_timing` 检查 t、fad、move、clip、iclip、硬换行、脚本头、事件时间和非字体文本原样保留，源文件 bytes 不变。
- [ ] **Step 2 — 运行 RED：** `.venv/bin/python -m pytest tests/test_subtitle_document.py -q`；应因新模块/接口不存在而失败。
- [ ] **Step 3 — 实现：** 按 section 和 Format 列解析，覆盖标签用带括号/花括号状态的 tokenizer；只替换 Style.Fontname 和 fn 的名称值。r 恢复当前命名样式，p 绘图内容不作为字体字符检查。无法安全理解的字体变换报告 unsupported，不能正则整段重写或静默删除标签。空 mapping 直接使用原文件，未映射部分保留原字节。
- [ ] **Step 4 — 运行 GREEN：** 上述测试全部通过；对外部素材分析得到 65 Dialogue、6 个定义样式、3 个实际使用样式和 2 个字体请求名称。
- [ ] **Step 5 — 提交：** 只提交本任务文件，提交消息 `feat(subtitle): 分析 ASS 字体并保留动画语义`。

## Task 2：字体来源、字形元数据和精确名称匹配

**Files:** 新增 src/subtitle_fonts.py、tests/test_subtitle_fonts.py、tests/fixtures/subtitle_compat/font_factory.py；修改 requirements.txt、requirements-build-macos.txt。

**Interfaces:** 消费 Task 1 的请求；定义 FontFace / FontBinding / FontIssue / FontReport / SubtitleFontOptions / FontCheckError。产出 `scan_font_sources(sources: tuple[str, ...], cache_dir: Path, cancelled: Callable[[], bool]) -> tuple[FontFace, ...]` 和 `resolve_fonts(analysis: SubtitleAnalysis, faces: tuple[FontFace, ...], bindings: tuple[FontBinding, ...]=()) -> FontReport`。

- [ ] **Step 1 — 写失败测试：** `test_full_name_medium_black_keeps_real_weight` 要求完整名称先于 family 近似匹配，Medium=500、Black=900 且 ASS Bold=0；`test_ttc_face_names_and_index` 区分同 TTC 的不同 face；`test_duplicate_full_name_requires_choice` 不按扫描顺序随机选字体；`test_import_zip_skips_appledouble_and_never_writes_source` 使用目录、ZIP、TTF 混合来源；`test_disconnected_source_cancel_and_invalid_font` 检查损坏字体不拖垮其它字体、取消抛 TaskCancelled、断卷报告 source_unavailable。
- [ ] **Step 2 — 运行 RED：** `.venv/bin/python -m pytest tests/test_subtitle_fonts.py -q`；先确认预期缺失接口失败。
- [ ] **Step 3 — 实现：** 两份 requirements 增加 fonttools==4.67.0。用 TTFont/TTCollection 读取 name IDs 1/2/4/6/16/17、OS/2 weight、italic、cmap、fvar；读取关闭文件句柄。名称只做 Unicode NFC、大小写和首尾空白规范化，不删掉 Medium/Black。显式 binding 优先，其次完整名字/PS 名，再到无歧义 family；静态字体支持，变量字体首版报告 unsupported。ZIP 仅将字体成员展开到本地缓存，忽略 __MACOSX 和 ._；不沿 ZIP 路径写入源目录。字体扫描和哈希分块检查取消；持久化索引和可变字体实例化不进入首版。
- [ ] **Step 4 — 运行 GREEN：** 上述测试通过；手动读取两份 Noto 和 MiSans 元数据，与上文 SHA/PS/weight 一致。缺失 Noto Sans 时只能报告 missing，不能把 MiSans 当作自动等价替换。
- [ ] **Step 5 — 提交：** 只提交本任务文件，消息 `feat(subtitle): 索引字体来源并识别实际字形字重`。

## Task 3：任务字体目录、纯滤镜构造和渲染诊断

**Files:** 新增 src/subtitle_render.py、tests/test_subtitle_render.py。

**Interfaces:** 消费 Task 1/2；定义 PreparedSubtitle。产出 `prepare_subtitle(path: str, options: SubtitleFontOptions) -> ContextManager[PreparedSubtitle]`、`build_subtitle_filter(prepared: PreparedSubtitle) -> str`、`FontSelectionCollector(prepared: PreparedSubtitle)` 的 `feed(line: str) -> None` 与 `report() -> FontReport`。准备时复制内容的 SHA 必须等于索引时 FontFace.sha256；来源已变化则失败并要求重新检查。

- [ ] **Step 1 — 写失败测试：** `test_direct_fontsdir_does_not_rewrite_ass`、`test_explicit_mapping_changes_only_font_names`、`test_two_jobs_do_not_share_temp_files`、`test_cleanup_after_success_failure_cancel`、`test_font_changed_after_scan_is_rejected`、`test_filter_escapes_chinese_spaces_quote_colon_and_comma`、`test_fontselect_failure_cannot_be_reported_as_verified`。日志样例包括本机 observed fontselect 行、路径中逗号、部分字体尚未触发以及不可解析行。
- [ ] **Step 2 — 运行 RED：** `.venv/bin/python -m pytest tests/test_subtitle_render.py -q`。
- [ ] **Step 3 — 实现：** 在 platform_paths().temp_dir 内使用唯一 TemporaryDirectory，平铺复制本次需要的字体，TTC 保留完整集合并记录选中 face。无 mapping 不改写 ASS；有 mapping 时仅把请求名改为选定 face 的完整名称，并显示替换。滤镜由 argv 列表传给进程，不经 shell；统一处理 filename/fontsdir 两层转义。直接名字/PS 名仍有歧义时返回错误，首版不改字体内部名字或拆字形。fontselect 匹配实际 PS/face，采集 fallback 和 missing glyph；未知日志只记 unverified，不能据退出 0 判定匹配。fontselect 的请求数值 400 与文件 weight=500/900 要分别展示。
- [ ] **Step 4 — 运行 GREEN：** 上述单元测试通过；调用固定 FFmpeg 加载准备目录，在合成帧上验证命中两份 Noto；删除 Sans/只留 Serif Regular 的负向样例必须被报告。成功、失败、取消后临时目录均消失，源文件 SHA 不变。
- [ ] **Step 5 — 提交：** 消息 `feat(subtitle): 准备独立字体目录并采集渲染匹配结果`。

## Task 4：接入普通、两遍和片段编码

**Files:** 修改 src/encode_params.py、src/core.py、src/executors/video_executor.py、src/ui/execution_summary.py；新增 tests/test_subtitle_encode.py；扩展 tests/test_encode_params.py、tests/test_clip_export.py。

**Interfaces:** EncodeParams 增加 `subtitle_fonts: SubtitleFontOptions`，解析旧 Args 时用 getattr + 默认关闭。`build_encode_command` / `build_2pass_commands` 末尾新增关键字 `subtitle_render: PreparedSubtitle | None=None`；保留原 subtitle_path 参数。`run_ffmpeg_command` 和 `run_2pass_encode` 新增仅关键字 `on_log: Callable[[str], None] | None=None`，将 collector 接到已有日志通道，打印、进度、取消和错误缓冲仍正常。

- [ ] **Step 1 — 写失败测试：** `test_disabled_keeps_existing_commands`、`test_enhancement_does_not_select_avisynth_mode`、`test_apple_and_cpu_use_same_subtitle_filter`、`test_both_passes_reuse_prepared_subtitle`、`test_clips_render_before_trim_and_keep_source_time`、`test_runtime_font_mismatch_prevents_post_transfer`；加入缺字幕、视频 copy、SRT、不兼容 AviSynth 组合的验证测试。
- [ ] **Step 2 — 运行 RED：** `.venv/bin/python -m pytest tests/test_subtitle_encode.py tests/test_encode_params.py tests/test_clip_export.py -q`。
- [ ] **Step 3 — 实现：** executor 在编码前进入 prepare_subtitle 上下文，并保持到两个 pass 完成；构造滤镜的两个原有分支复用 build_subtitle_filter，片段递归命令也传递 prepared。严格错误返回 reason=subtitle_fonts；允许替换时保留 warnings。实际选择错误在 _post_transfer 之前处理，已生成输出可在 failed.outputs 中保留。debug 不创建持久准备结果、不称字体已验证。增强只影响硬字幕，不改软字幕映射和音轨策略。
- [ ] **Step 4 — 运行 GREEN：** 上述命令全部通过，加跑 tests/test_command_snapshot.py、tests/test_video_executor.py、tests/test_encode_task_result.py。关掉增强时既有命令快照通过；CPU 两遍仍为 TWO_PASS，Apple 质量参数仍用 -q:v，片段仍在源时间轴烧字幕。
- [ ] **Step 5 — 提交：** 仅提交本任务改动，消息 `feat(encode): 将字幕字体增强接入现有编码时间线`；若同文件存在别人未提交修改，使用独立检出或精确暂存，不打包对方修改。

## Task 5：Mac 字体面板与当前时间点效果快照

**Files:** 新增 src/ui/subtitle_font_panel.py、src/ui/subtitle_font_worker.py、tests/ui/test_subtitle_font_panel.py、tests/ui/test_subtitle_font_worker.py、tests/test_subtitle_preview.py；修改 src/ui/tabs/encode_tab.py，扩展 src/subtitle_render.py。

**Interfaces:** `SubtitleFontPanel.options() -> SubtitleFontOptions`、`set_running(bool)`、`set_inputs(video: str, subtitle: str)`、`release()`；暴露 changed 信号。`render_subtitle_preview(input_path: str, source_us: int, prepared: PreparedSubtitle, output: Path, resolution: str | None=None) -> FontReport` 在后台通过当前 TaskContext 的 ProcessRunner 执行，超时 60 秒。worker 返回 `(generation, input_fingerprint, result)`，缓存键包含源字幕/字体内容指纹、时间点、分辨率和 FFmpeg 版本。

- [ ] **Step 1 — 写失败测试：** `test_mac_panel_under_hard_subtitle_and_defaults_off`、`test_args_summary_and_readiness_use_same_options`、`test_missing_and_explicit_fallback_are_visible`、`test_stale_scan_or_preview_is_discarded`、`test_export_and_close_cancel_preview_without_late_ui_write`。后端 `test_preview_at_nonzero_time_keeps_ass_clock` 用 1 秒后才出现的合成字幕确保不会因 input -ss 重置而消失，另测非零起点素材。
- [ ] **Step 2 — 运行 RED：** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ui/test_subtitle_font_panel.py tests/ui/test_subtitle_font_worker.py tests/test_subtitle_preview.py -q`。
- [ ] **Step 3 — 实现面板：** 放在“字幕文件”下，默认折叠/关闭；支持导入字体目录、TTF/OTF/TTC/ZIP、重新检查、请求→实际字形/字重表、显式替换、允许字体替换。Mac 在存在 subtitles 滤镜时显示；Windows 仍显示原兼容模式。SRT/copy 时给出具体禁用原因。build_args 创建不可变 options 快照，prepare_execution 只读准备状态，不在主线程扫描文件；set_running 冻结选项，输入改变清理旧报告。
- [ ] **Step 4 — 实现快照：** 手输原片时间，可从已展开原片预览的 mark_us() 取值；未展开时无需打开播放器也能输入。使用与导出相同的 prepared 和滤镜顺序；首版从原片按原时间顺序解码，在字幕/缩放后选取目标时间第一帧并写 PNG，正确性优先，暂不加会改变 ASS 时钟的快速 seek。显示“字幕效果快照”、实际时间和匹配报告，不称实时或压缩后预览。一次只运行一个任务，新请求取消旧任务并只保留最新请求；关闭/导出前协作取消，finished 前保留 worker 引用。
- [ ] **Step 5 — 运行 GREEN：** 上述测试及 tests/ui/test_encode_page_ia.py、tests/ui/test_encode_avisynth_gate.py 通过。用素材 19 秒和 25 秒验证显示标题/逐字与滚动差异；网络等待和快照期间窗口仍能处理 UI 事件，取消后没有残留 FFmpeg。
- [ ] **Step 6 — 提交：** 消息 `feat(ui): 增加 Mac 字体检查和字幕效果快照`。

## Task 6：固定素材验收、冻结应用验证和文档

**Files:** 新增 tools/validate_subtitle_compat.py、tests/test_subtitle_media.py、tests/fixtures/subtitle_compat/262_manifest.json；扩展 tests/conftest.py、tools/smoke_macos.py、XiaoXueToolbox-macOS.spec（仅在缺失收集时）、README.md、CHANGELOG.md。Wiki 的 Features-Video-Encode / FAQ / 使用手册在实际功能验证通过后再更新。

**Interfaces:** 验收工具参数固定为 `--corpus-root PATH --font-cache PATH --output PATH [--download-missing-fonts]`；生成 manifest.json、font-report.json、source-checksums.json、frames/、outputs/、logs/。manifest 记录输入和字体 SHA、来源、FFmpeg/libass 版本、所选字形、每项 pass/fail/not_run，不用下载成功代替渲染通过。

- [ ] **Step 1 — 写失败测试：** tests/test_subtitle_media.py 使用临时微型字体/ASS，验证字体缺失失败、正确字形成功、两种样式没有被全局覆盖、片段重排保留字幕时间、快照与无损导出同一时间点字幕 ROI 一致。外部素材用例读取 XIAOXUE_SUBTITLE_TEST_ROOT；未配置时显式 skip，已配置但断卷/缺文件时 fail，不能把环境损坏伪装成通过。
- [ ] **Step 2 — 运行 RED：** `.venv/bin/python -m pytest tests/test_subtitle_media.py -q`，明确缺失新入口导致失败。
- [ ] **Step 3 — 实现验收工具：** 按本计划的 manifest 读取原素材和用户字体，只解压选中成员；缺 Sans 时用固定官方 commit URL 下载并校验上文 SHA，缓存命中也校验。排除 AppleDouble。用户素材、Noto/MiSans 全字体不提交 Git；CI 用自制字体生成器，真实素材完整验收在可访问共享卷的本机运行。
- [ ] **Step 4 — 执行下方验收矩阵：** 全部必要正向项 pass、负向项按预期拒绝；Windows 参考帧尚无时明确写 not_run，不能声明与 VSFilter 完全一致。原素材和字体前后 SHA 相同。
- [ ] **Step 5 — 验证冻结应用：** 本机固定媒体运行时构建 .app；导入相同字体目录与 ZIP，检查字体扫描、19 秒快照、Apple 导出、CPU 两遍、取消、重启。干净 HOME 或没有系统安装 Noto 的环境也必须成功，以证明依赖来自任务字体目录。确认 fontTools 被 PyInstaller 收集，必要时仅增加缺失的 hiddenimports。
- [ ] **Step 6 — 回归与文档：** `QT_QPA_PLATFORM=offscreen XIAOXUE_NO_UPDATE_CHECK=1 .venv/bin/python -m pytest -q`，然后完成 Windows 全套 CI 与既有兼容模式回归。文档说明导入字体、严格/允许替换、单帧预览范围；CHANGELOG 更新 Unreleased，不自动 bump/tag/发布。验证完成后提交 `test(subtitle): 验证真实素材字体与打包兼容性`。

## 固定素材验收矩阵

| 项目 | 操作与通过条件 |
| --- | --- |
| 缺字体负向 | 不加载 Noto；检查显示两字体缺失，严格模式在编码前失败；允许替换则必须在报告中显示 PingFang 等真实替换，不写“全部匹配” |
| 正文字重 | 19 秒请求 Noto Sans SC Medium，选中 PS=NotoSansSC-Medium / weight=500；不可回退 PingFang |
| 标题字重 | 16.25 / 19 秒选中 PS=NotoSerifCJKsc-Black / weight=900；只提供 Serif Regular 的测试不得被判为正确 |
| 动画边界 | 16.02、16.25、16.52、17.77、18.00、19.00、23.64、25.00、28.40 秒检查 wipe、逐字淡入、滚动裁切；允许按源 60fps 网格取帧并记录实际 PTS |
| 字体显式映射 | 只将正文/滚动映射 MiSans Medium，标题仍为 Noto Serif Black；记录为用户替换；源 ASS SHA 不变 |
| 原生与映射区别 | 不设置 mapping 时不得改写 ASS；映射只改字体名称，文字/时间/动画/YCbCr Matrix=None 保留 |
| 普通与 CPU 两遍 | 从源 16–29 秒生成独立、源时间已保持的 13 秒测试样本，按现有 UI→executor 路径分别跑 libx264 CRF、libx264 两遍；字幕位置/时序一致，两遍都使用同一准备目录 |
| Apple 编码 | 同一 13 秒样本跑 H.264 VideoToolbox；视频、音频存在，字体匹配报告正确；不要求与 CPU 压缩像素相同 |
| 多段重排 | 原片区间 [23.64,28.41) 然后 [17.77,23.64)，共 10.64 秒，638 个 60fps 采样帧（原片 n=1419..1704 共286帧，再接 n=1067..1418 共352帧；核对实际PTS）；不能把滚动/逐字动画按新片段起点重新开始；音画收尾差 <= 1/60 + 1024/音频采样率 + 0.01 秒 |
| 快照一致性 | 同 FFmpeg、字体、分辨率、源 PTS，比较快照与无损导出帧：标题 ROI (500,720)–(1600,840)、正文/滚动 ROI (380,830)–(1840,1080)；同构建同像素格式下应像素一致，跨平台人工观察且不采用全画面平均误差掩盖字幕差异 |
| 路径与资源 | 原中文共享目录直接读；另测空格、单引号、冒号、逗号路径；ZIP/TTC/OTF/TTF 和 AppleDouble 均按规则处理 |
| 取消与陈旧结果 | 字体导入、快照、第一/第二遍期间取消；两任务临时目录隔离；切换输入后旧结果不显示；共享卷断开给出错误，源文件不变 |
| 完整导出 | 开发中的循环验证使用短样本；全部功能回归后仅做一次 368.033333 秒完整原片导出，核对所有使用样式、有效 A/V 流与时长，避免每步重复压制 475MB 视频 |

13 秒样本固定为源视频 16–29 秒：input -ss 16、-t 13、-c:v ffv1、-c:a pcm_s16le，输出本地 sample-16-29.mkv，保持 2160×1080/60fps。仅供测试的 ASS 副本将每条 Dialogue 的 Start/End 减去 16 秒，其余内容和相对变换标签原样保留；最早字幕原为 16.02 秒，不会出现负时间。记录 offset_us=16000000，快照/帧断言统一转换。绝不改源 ASS 或把测试重定时引入产品输入。多段验收仍直接使用原片。

建议运行命令（实现 Task 6 后）：

```bash
XIAOXUE_SUBTITLE_TEST_ROOT='/Volumes/192.168.6.27/local_share/mac兼容性测试文件' \
QT_QPA_PLATFORM=offscreen XIAOXUE_NO_UPDATE_CHECK=1 \
.venv/bin/python -m pytest tests/test_subtitle_media.py -q

.venv/bin/python tools/validate_subtitle_compat.py \
  --corpus-root '/Volumes/192.168.6.27/local_share/mac兼容性测试文件' \
  --font-cache '/Volumes/WD_SN730/01_dev/XiaoXue/macos-assessment/2026-10-18/subtitle-compat/user-materials/fonts' \
  --output build/subtitle-compat-262 \
  --download-missing-fonts
```

## 首版交付与后续边界

交付为可关闭的 Mac 字体增强、来源/实际字形报告、用户显式字体映射、可取消单帧字幕效果检查，以及普通/两遍/片段/冻结应用的测试证据。6 个任务按顺序在当前会话原生执行更合适：后面各项持续依赖前面确定的字幕请求、字形和准备目录接口。

本计划不包含：VSFilter 的 GDI/MFC 移植、字体二进制改名/重造、可变字体实例化、完整实时字幕播放器、系统级字体安装、自动发布新版本。以后若出现“字体已正确命中但排版/特效仍不符”的样本，再单独评估渲染器差异，避免把这些问题混入字体加载首版。

## 参考与自检

- [fontTools TTFont](https://fonttools.readthedocs.io/en/latest/ttLib/ttFont.html)、[TTCollection](https://fonttools.readthedocs.io/en/latest/ttLib/ttCollection.html)、[name 表](https://fonttools.readthedocs.io/en/latest/ttLib/tables/_n_a_m_e.html)：读取 face、名称和权重，不修改轮廓。
- [libass 与 VSFilter 官方差异说明](https://github.com/libass/libass/wiki/Differences-between-Libass-and-VSFilters)：字体匹配成功不等于全部渲染行为一致。
- 自检：6 个任务覆盖素材准备、解析、字体、任务生命周期、普通/两遍/片段、UI、快照、打包与文档；Review Focus 的 5 项都有对应测试；真实素材验收与通用 CI 测试分开标记，缺少 Windows 参考不冒充已比对。
