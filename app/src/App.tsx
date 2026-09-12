import { useEffect, useMemo, useState } from "react";
import {
  FluentProvider,
  Theme,
  webDarkTheme,
  webLightTheme,
  Dropdown,
  Input,
  Option,
  Button,
  Spinner,
} from "@fluentui/react-components";
import {
  VideoRegular,
  MusicNote2Regular,
  ArrowSwapRegular,
  BoxRegular,
  InfoRegular,
  ImageRegular,
  SearchRegular,
  FolderAddRegular,
  EditRegular,
  QuestionCircleRegular,
  WeatherMoonRegular,
  WeatherSunnyRegular,
  PlayFilled,
} from "@fluentui/react-icons";
import {
  appVersion,
  previewEncodeCommand,
  probeMedia,
  qualityPresetNames,
  EncodeOptions,
} from "./lib/engine";
import { ReplaceAudioPage, ExtractAvPage, RemuxPage, FolderPage, RenamePage } from "./pages/task-pages";
import { NotificationPage, HelpPage } from "./pages/misc-pages";

/* ---- 导航定义 (与 Python 版分组一致) ---- */
type PageId =
  | "encode"
  | "probe"
  | "replace_audio"
  | "extract_av"
  | "remux"
  | "folder"
  | "rename"
  | "notification"
  | "help"
  | "placeholder";

const MIGRATING = ["image", "qc"]; // 尚未迁移的页面

const NAV: { section: string; items: { id: PageId | string; label: string; icon: JSX.Element }[] }[] = [
  {
    section: "视频处理",
    items: [
      { id: "encode", label: "视频压制", icon: <VideoRegular /> },
      { id: "replace_audio", label: "音频替换", icon: <MusicNote2Regular /> },
      { id: "extract_av", label: "音视频抽取", icon: <ArrowSwapRegular /> },
    ],
  },
  {
    section: "格式与媒体",
    items: [
      { id: "remux", label: "封装转换", icon: <BoxRegular /> },
      { id: "probe", label: "媒体元数据检测", icon: <InfoRegular /> },
      { id: "image", label: "图片转换", icon: <ImageRegular /> },
    ],
  },
  {
    section: "质量与批量",
    items: [
      { id: "qc", label: "素材质量检测", icon: <SearchRegular /> },
      { id: "folder", label: "文件夹创建", icon: <FolderAddRegular /> },
      { id: "rename", label: "批量重命名", icon: <EditRegular /> },
    ],
  },
  {
    section: "帮助",
    items: [
      { id: "about", label: "关于", icon: <QuestionCircleRegular /> },
    ],
  },
];

export default function App() {
  const [dark, setDark] = useState(false);
  const [page, setPage] = useState<PageId>("encode");
  const [version, setVersion] = useState("…");

  useEffect(() => {
    appVersion().then(setVersion).catch(() => setVersion("?"));
  }, []);

  const fluentTheme: Theme = dark ? webDarkTheme : webLightTheme;

  return (
    <FluentProvider theme={fluentTheme}>
      <div className="shell" data-theme={dark ? "dark" : "light"}>
        <aside className="sidebar">
          <div className="brand">
            <div>
              <div className="brand-title">小雪工具箱</div>
              <div className="brand-version">v{version} · 原生版</div>
            </div>
          </div>
          {NAV.map((group) => (
            <div key={group.section}>
              <div className="nav-section">{group.section}</div>
              {group.items.map((item) => {
                const enabled = !MIGRATING.includes(item.id as string);
                return (
                  <button
                    key={item.id}
                    className={`nav-item${page === item.id ? " active" : ""}`}
                    style={enabled ? undefined : { opacity: 0.45, cursor: "default" }}
                    onClick={() => {
                      if (enabled) setPage(item.id as PageId);
                    }}
                    title={enabled ? undefined : "M3 迁移中, 敬请期待"}
                  >
                    {item.icon}
                    <span>{item.label}</span>
                  </button>
                );
              })}
            </div>
          ))}
          <div className="sidebar-footer">
            <button className="nav-item" onClick={() => setDark(!dark)}>
              {dark ? <WeatherSunnyRegular /> : <WeatherMoonRegular />}
              <span>{dark ? "浅色模式" : "深色模式"}</span>
            </button>
          </div>
        </aside>
        <main className="content">
          <div className="page-column">
            {page === "encode" && <EncodePage />}
            {page === "probe" && <ProbePage />}
            {page === "replace_audio" && <ReplaceAudioPage />}
            {page === "extract_av" && <ExtractAvPage />}
            {page === "remux" && <RemuxPage />}
            {page === "folder" && <FolderPage />}
            {page === "rename" && <RenamePage />}
            {page === "notification" && <NotificationPage />}
            {page === "help" && <HelpPage />}
            {MIGRATING.includes(page as string) && (
              <div className="card">
                <h3 className="card-title">迁移中</h3>
                <p className="card-desc">该页面将在后续阶段移植。</p>
              </div>
            )}
          </div>
        </main>
      </div>
    </FluentProvider>
  );
}

/* ================================================================
   视频压制页 (M2 首个功能页)
   ================================================================ */

const RC_MODES: [string, string | null][] = [
  ["CRF/CQ (恒定质量)", null],
  ["VBR (可变码率)", "vbr"],
  ["CBR (恒定码率)", "cbr"],
  ["2-Pass VBR (两遍编码)", "2pass"],
];

function EncodePage() {
  const [presets, setPresets] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [output, setOutput] = useState("");
  const [preset, setPreset] = useState<string>("");
  const [rcLabel, setRcLabel] = useState("CRF/CQ (恒定质量)");
  const [crf, setCrf] = useState(18);
  const [bitrate, setBitrate] = useState("");
  const [preview, setPreview] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  const rcMode = useMemo(
    () => RC_MODES.find(([label]) => label === rcLabel)?.[1] ?? null,
    [rcLabel],
  );

  useEffect(() => {
    qualityPresetNames()
      .then((names) => {
        setPresets(names);
        if (names.length > 0) setPreset(names[0]);
      })
      .catch(() => setPresets([]));
  }, []);

  const opts: EncodeOptions = useMemo(
    () => ({
      input: input || "input.mp4",
      output: output || "",
      preset_name: preset || null,
      encoder: null,
      crf,
      bitrate: bitrate || null,
      speed_preset: null,
      resolution: null,
      fps: null,
      audio_encoder: "aac",
      audio_bitrate: "192k",
      subtitle_path: null,
      extra_args: null,
      rc_mode: rcMode,
      audio_tracks: "0",
      audio_tracks_custom: "",
      subtitle_tracks: "none",
      subtitle_tracks_custom: "",
    }),
    [input, output, preset, crf, bitrate, rcMode],
  );

  const refreshPreview = async () => {
    setBusy(true);
    try {
      setPreview(await previewEncodeCommand(opts));
    } catch (e) {
      setPreview([String(e)]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div className="card">
        <h3 className="card-title">输入 / 输出</h3>
        <div className="form-row">
          <label className="form-label">输入视频</label>
          <div className="form-control">
            <Input
              placeholder="选择或拖入视频文件"
              value={input}
              onChange={(_, d) => setInput(d.value)}
              style={{ width: "100%" }}
            />
          </div>
        </div>
        <div className="form-row">
          <label className="form-label">输出路径 (可选)</label>
          <div className="form-control">
            <Input
              placeholder="留空自动生成: 输入名_编码器.mp4"
              value={output}
              onChange={(_, d) => setOutput(d.value)}
              style={{ width: "100%" }}
            />
          </div>
        </div>
      </div>

      <div className="card">
        <h3 className="card-title">预设选择</h3>
        <div className="form-row">
          <label className="form-label">质量预设</label>
          <div className="form-control">
            <Dropdown
              selectedOptions={preset ? [preset] : []}
              value={preset}
              onOptionSelect={(_, d) => setPreset(d.optionText ?? "")}
            >
              {presets.map((name) => (
                <Option key={name} text={name} value={name}>
                  {name}
                </Option>
              ))}
            </Dropdown>
          </div>
        </div>
      </div>

      <div className="card">
        <h3 className="card-title">质量与码率</h3>
        <div className="form-row">
          <label className="form-label">码率控制模式</label>
          <div className="form-control">
            <Dropdown
              selectedOptions={[rcLabel]}
              value={rcLabel}
              onOptionSelect={(_, d) => setRcLabel(d.optionText ?? "")}
            >
              {RC_MODES.map(([label]) => (
                <Option key={label} text={label} value={label}>
                  {label}
                </Option>
              ))}
            </Dropdown>
          </div>
        </div>
        {rcMode === null ? (
          <div className="form-row">
            <label className="form-label">质量值 (CRF/CQ)</label>
            <div className="form-control">
              <Input
                type="number"
                value={String(crf)}
                onChange={(_, d) => setCrf(Number(d.value) || 0)}
                style={{ width: "120px" }}
              />
            </div>
          </div>
        ) : (
          <div className="form-row">
            <label className="form-label">目标码率</label>
            <div className="form-control">
              <Input
                placeholder="如 8000k"
                value={bitrate}
                onChange={(_, d) => setBitrate(d.value)}
                style={{ width: "180px" }}
              />
            </div>
          </div>
        )}
      </div>

      <div className="action-row">
        <Button
          appearance="primary"
          icon={<PlayFilled />}
          size="large"
          onClick={refreshPreview}
          disabled={busy}
        >
          预览命令
        </Button>
        {busy && <Spinner size="tiny" />}
      </div>

      {preview.length > 0 && (
        <div className="card">
          <h3 className="card-title">FFmpeg 命令预览</h3>
          <div className="cmd-preview">{preview.join(" ")}</div>
        </div>
      )}
    </div>
  );
}

/* ================================================================
   媒体元数据检测页 (后端已就绪)
   ================================================================ */

function ProbePage() {
  const [path, setPath] = useState("");
  const [result, setResult] = useState<Awaited<ReturnType<typeof import("./lib/engine").probeMedia>> | null>(null);
  const [busy, setBusy] = useState(false);

  const probe = async () => {
    if (!path.trim()) return;
    setBusy(true);
    try {
      setResult(await probeMedia(path.trim()));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div className="card">
        <h3 className="card-title">媒体元数据检测</h3>
        <div className="form-row">
          <label className="form-label">文件路径</label>
          <div className="form-control">
            <Input
              placeholder="视频文件完整路径"
              value={path}
              onChange={(_, d) => setPath(d.value)}
              style={{ width: "100%" }}
            />
          </div>
        </div>
        <div className="action-row">
          <Button appearance="primary" onClick={probe} disabled={busy}>
            {busy ? <Spinner size="extra-tiny" /> : "开始检测"}
          </Button>
        </div>
      </div>
      {result && (
        <div className="card">
          <h3 className="card-title">{result.filename}</h3>
          {result.errors.length > 0 ? (
            result.errors.map((e, i) => (
              <p key={i} className="card-desc">
                [错误] {e}
              </p>
            ))
          ) : (
            <>
              <p className="card-desc">
                容器: {result.format_name} · 时长: {result.duration_sec.toFixed(1)}s
                {result.total_bitrate_kbps > 0 &&
                  ` · 码率: ${result.total_bitrate_kbps} kbps`}
              </p>
              {result.video_streams.map((vs) => (
                <p key={vs.index} className="card-desc">
                  视频流 #{vs.index}: {vs.codec_name} {vs.width}x{vs.height} @{" "}
                  {vs.fps} fps
                </p>
              ))}
              {result.audio_streams.map((au) => (
                <p key={au.index} className="card-desc">
                  音频流 #{au.index}: {au.codec_name} {au.sample_rate}Hz{" "}
                  {au.channels}ch
                </p>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}
