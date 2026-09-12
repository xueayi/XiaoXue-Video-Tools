import { useState } from "react";
import {
  Button,
  Checkbox,
  Dropdown,
  Input,
  Option,
} from "@fluentui/react-components";
import { FolderRegular } from "@fluentui/react-icons";
import { pickFile, pickFolder, pickFiles, pickSave } from "../lib/dialog";
import {
  batchRename,
  buildExtractAudio,
  buildExtractVideo,
  buildReplaceAudio,
  createFolders,
  planRemux,
} from "../lib/engine";
import { TaskPanel, TaskPlan } from "../components/TaskPanel";

/* ---- 通用行组件 ---- */

interface PathRowProps {
  label: string;
  value: string | string[];
  onChange: (v: string | string[]) => void;
  placeholder?: string;
  isSave?: boolean;
  filters?: { name: string; extensions: string[] }[];
  multi?: boolean;
  directory?: boolean;
}

export function PathRow({
  label,
  value,
  onChange,
  placeholder,
  isSave,
  filters,
  multi,
  directory,
}: PathRowProps) {
  const browse = async () => {
    if (directory) {
      const d = await pickFolder();
      if (d) onChange(d);
    } else if (multi) {
      const f = await pickFiles(filters);
      if (f) onChange(f);
    } else {
      const f = isSave
        ? await pickSave("", filters)
        : await pickFile(filters);
      if (f) onChange(f);
    }
  };
  const text = Array.isArray(value) ? value.join("; ") : value;
  return (
    <div className="form-row">
      <label className="form-label">{label}</label>
      <div className="form-control" style={{ display: "flex", gap: 8 }}>
        <Input
          placeholder={placeholder}
          value={text}
          onChange={(_, d) => onChange(d.value)}
          style={{ flex: 1 }}
        />
        <Button icon={<FolderRegular />} onClick={browse} />
      </div>
    </div>
  );
}

const VIDEO_FILTERS = [
  { name: "视频文件", extensions: ["mp4", "mov", "avi", "mkv", "webm", "ts", "m4v"] },
];

const TRACK_OPTIONS: [string, string][] = [
  ["全部保留", "all"],
  ["仅保留第 1 条 (#0)", "0"],
  ["不保留", "none"],
  ["自定义", "custom"],
];

function TrackDropdown({ value, onChange, kind }: {
  value: string;
  onChange: (v: string) => void;
  kind: string;
}) {
  return (
    <Dropdown
      selectedOptions={[value]}
      value={value}
      onOptionSelect={(_, d) => onChange(d.optionText ?? "")}
    >
      {TRACK_OPTIONS.map(([label, v]) => (
        <Option key={label} text={label} value={v}>
          {label.replace("#0", `${kind} #0`)}
        </Option>
      ))}
    </Dropdown>
  );
}

/* ---- 音频替换 ---- */

export function ReplaceAudioPage() {
  const [video, setVideo] = useState("");
  const [audio, setAudio] = useState("");
  const [output, setOutput] = useState("");
  const [encoder, setEncoder] = useState("aac");
  const [bitrate, setBitrate] = useState("192k");

  const build = async (): Promise<TaskPlan> => {
    const commands = [
      await buildReplaceAudio(video, audio, output, encoder, bitrate),
    ];
    return { name: "音频替换", commands };
  };

  return (
    <div>
      <div className="card">
        <h3 className="card-title">音频替换</h3>
        <p className="card-desc">视频流直接复制，不重新编码；新音频时长建议与视频一致。</p>
        <PathRow label="原始视频" value={video} onChange={(v) => setVideo(String(v))} filters={VIDEO_FILTERS} />
        <PathRow label="新音频文件" value={audio} onChange={(v) => setAudio(String(v))}
          filters={[{ name: "音频文件", extensions: ["m4a", "aac", "mp3", "wav", "flac"] }]} />
        <PathRow label="输出路径" value={output} onChange={(v) => setOutput(String(v))}
          placeholder="留空自动生成: 原名_replaced.mp4" isSave
          filters={[{ name: "视频文件", extensions: ["mp4"] }]} />
        <div className="form-row">
          <label className="form-label">音频编码器</label>
          <div className="form-control" style={{ maxWidth: 240 }}>
            <Dropdown selectedOptions={[encoder]} value={encoder}
              onOptionSelect={(_, d) => setEncoder(d.optionText ?? "aac")}>
              <Option text="AAC (推荐)" value="aac">AAC (推荐)</Option>
              <Option text="复制 (不重新编码)" value="copy">复制 (不重新编码)</Option>
            </Dropdown>
          </div>
        </div>
        {encoder !== "copy" && (
          <div className="form-row">
            <label className="form-label">音频码率</label>
            <div className="form-control" style={{ maxWidth: 240 }}>
              <Input value={bitrate} onChange={(_, d) => setBitrate(d.value)} />
            </div>
          </div>
        )}
      </div>
      <TaskPanel build={build} disabled={!video || !audio} />
    </div>
  );
}

/* ---- 音视频抽取 ---- */

export function ExtractAvPage() {
  const [input, setInput] = useState("");
  const [mode, setMode] = useState("both");
  const [encoder, setEncoder] = useState("aac");
  const [bitrate, setBitrate] = useState("192k");

  const build = async (): Promise<TaskPlan> => {
    const base = input.replace(/\.[^.]+$/, "");
    const commands: string[][] = [];
    if (mode === "both" || mode === "audio") {
      const ext = encoder === "copy" ? ".m4a" : ".m4a";
      commands.push(
        await buildExtractAudio(input, `${base}_audio${ext}`, encoder, bitrate));
    }
    if (mode === "both" || mode === "video") {
      const ext = input.match(/\.[^.]+$/)?.[0] ?? ".mp4";
      commands.push(await buildExtractVideo(input, `${base}_noaudio${ext}`));
    }
    return { name: "音视频抽取", commands };
  };

  return (
    <div>
      <div className="card">
        <h3 className="card-title">音视频抽取</h3>
        <PathRow label="输入视频" value={input}
          onChange={(v) => setInput(String(v))} filters={VIDEO_FILTERS} />
        <div className="form-row">
          <label className="form-label">抽取模式</label>
          <div className="form-control" style={{ maxWidth: 240 }}>
            <Dropdown selectedOptions={[mode]} value={mode}
              onOptionSelect={(_, d) => setMode(d.optionValue ?? "both")}>
              <Option text="仅音频" value="audio">仅音频</Option>
              <Option text="仅视频" value="video">仅视频</Option>
              <Option text="音视频都抽取" value="both">音视频都抽取</Option>
            </Dropdown>
          </div>
        </div>
        {(mode === "both" || mode === "audio") && (
          <div className="form-row">
            <label className="form-label">音频编码器</label>
            <div className="form-control" style={{ maxWidth: 240 }}>
              <Dropdown selectedOptions={[encoder]} value={encoder}
                onOptionSelect={(_, d) => setEncoder(d.optionText ?? "aac")}>
                <Option text="AAC (推荐)" value="aac">AAC (推荐)</Option>
                <Option text="复制 (不重新编码)" value="copy">复制 (不重新编码)</Option>
              </Dropdown>
            </div>
          </div>
        )}
        {(mode === "both" || mode === "audio") && encoder !== "copy" && (
          <div className="form-row">
            <label className="form-label">音频码率</label>
            <div className="form-control" style={{ maxWidth: 240 }}>
              <Input value={bitrate} onChange={(_, d) => setBitrate(d.value)} />
            </div>
          </div>
        )}
      </div>
      <TaskPanel build={build} disabled={!input} />
    </div>
  );
}

/* ---- 封装转换 ---- */

const REMUX_PRESETS: [string, string][] = [
  ["MP4 (H.264 兼容)", ".mp4"],
  ["MKV (多轨封装)", ".mkv"],
  ["MOV (Apple 生态)", ".mov"],
  ["TS (广播传输流)", ".ts"],
  ["WEBM (Web 视频)", ".webm"],
  ["自定义", ""],
];

export function RemuxPage() {
  const [inputs, setInputs] = useState<string[]>([]);
  const [preset, setPreset] = useState("MP4 (H.264 兼容)");
  const [customExt, setCustomExt] = useState("");
  const [outputDir, setOutputDir] = useState("");
  const [overwrite, setOverwrite] = useState(false);
  const [audioTracks, setAudioTracks] = useState("all");
  const [audioCustom, setAudioCustom] = useState("");
  const [subtitleTracks, setSubtitleTracks] = useState("all");
  const [subtitleCustom, setSubtitleCustom] = useState("");

  const build = async (): Promise<TaskPlan> => {
    const ext = preset === "自定义" ? customExt : (REMUX_PRESETS.find(([k]) => k === preset)?.[1] ?? ".mp4");
    const plan = await planRemux({
      inputs, outputDir, extension: ext, overwrite,
      audioTracks: audioTracks === "自定义" ? "custom" : audioTracks === "全部保留" ? "all" : audioTracks === "不保留" ? "none" : audioTracks,
      audioCustom,
      subtitleTracks: subtitleTracks === "自定义" ? "custom" : subtitleTracks === "全部保留" ? "all" : subtitleTracks === "不保留" ? "none" : subtitleTracks,
      subtitleCustom,
    });
    return { name: "封装转换", commands: plan.commands };
  };

  return (
    <div>
      <div className="card">
        <h3 className="card-title">封装转换</h3>
        <p className="card-desc">不重新编码，速度极快。某些编码不兼容某些容器。</p>
        <PathRow label="输入文件 (可多选)" value={inputs} onChange={(v) => setInputs(Array.isArray(v) ? v : [v])}
          multi filters={VIDEO_FILTERS} />
        <div className="form-row">
          <label className="form-label">封装预设</label>
          <div className="form-control" style={{ maxWidth: 320 }}>
            <Dropdown selectedOptions={[preset]} value={preset}
              onOptionSelect={(_, d) => setPreset(d.optionText ?? "")}>
              {REMUX_PRESETS.map(([label]) => (
                <Option key={label} text={label} value={label}>{label}</Option>
              ))}
            </Dropdown>
          </div>
        </div>
        {preset === "自定义" && (
          <div className="form-row">
            <label className="form-label">自定义后缀名</label>
            <div className="form-control" style={{ maxWidth: 240 }}>
              <Input value={customExt} onChange={(_, d) => setCustomExt(d.value)}
                placeholder="如 mkv" />
            </div>
          </div>
        )}
        <PathRow label="输出目录 (可选)" value={outputDir}
          onChange={(v) => setOutputDir(String(v))}
          directory placeholder="留空则在原位置生成" />
        <div className="form-row">
          <label className="form-label">音轨</label>
          <div className="form-control" style={{ maxWidth: 320 }}>
            <TrackDropdown kind="音轨" value={audioTracks} onChange={setAudioTracks} />
          </div>
        </div>
        {audioTracks === "自定义" && (
          <div className="form-row">
            <label className="form-label">音轨编号</label>
            <div className="form-control" style={{ maxWidth: 320 }}>
              <Input value={audioCustom}
                onChange={(_, d) => setAudioCustom(d.value)}
                placeholder="逗号分隔, 如 0,1" />
            </div>
          </div>
        )}
        <div className="form-row">
          <label className="form-label">字幕</label>
          <div className="form-control" style={{ maxWidth: 320 }}>
            <TrackDropdown kind="字幕" value={subtitleTracks} onChange={setSubtitleTracks} />
          </div>
        </div>
        {subtitleTracks === "自定义" && (
          <div className="form-row">
            <label className="form-label">字幕编号</label>
            <div className="form-control" style={{ maxWidth: 320 }}>
              <Input value={subtitleCustom}
                onChange={(_, d) => setSubtitleCustom(d.value)}
                placeholder="逗号分隔, 如 0,2" />
            </div>
          </div>
        )}
        <Checkbox label="覆盖原文件 (转换后删除原文件)" checked={overwrite}
          onChange={(_, d) => setOverwrite(d.checked === true)} />
      </div>
      <TaskPanel build={build} disabled={inputs.length === 0} />
    </div>
  );
}

/* ---- 文件夹创建 ---- */

export function FolderPage() {
  const [txt, setTxt] = useState("");
  const [out, setOut] = useState("");
  const [autoNumber, setAutoNumber] = useState(true);
  const [result, setResult] = useState<string>("");

  const run = async () => {
    const r = await createFolders(txt, out, autoNumber);
    setResult(`成功 ${r.ok} 个, 失败 ${r.fail} 个${r.errors.length ? "\n" + r.errors.join("\n") : ""}`);
  };

  return (
    <div>
      <div className="card">
        <h3 className="card-title">批量创建文件夹</h3>
        <p className="card-desc">TXT 文件每行一个文件夹名称，支持 UTF-8/GBK 编码。</p>
        <PathRow label="TXT 文件" value={txt} onChange={(v) => setTxt(String(v))}
          filters={[{ name: "文本文件", extensions: ["txt"] }]} />
        <PathRow label="输出目录" value={out}
          onChange={(v) => setOut(String(v))} directory
          placeholder="留空则使用 TXT 所在目录" />
        <Checkbox label="自动添加序号前缀" checked={autoNumber}
          onChange={(_, d) => setAutoNumber(d.checked === true)} />
        <div className="action-row">
          <Button appearance="primary" onClick={run} disabled={!txt}>开始创建</Button>
        </div>
        {result && <div className="cmd-preview">{result}</div>}
      </div>
    </div>
  );
}

/* ---- 批量重命名 ---- */

export function RenamePage() {
  const [inputDir, setInputDir] = useState("");
  const [mode, setMode] = useState("rename_in_place");
  const [recursive, setRecursive] = useState(true);
  const [excludeUnderscore, setExcludeUnderscore] = useState(true);
  const [sortBy, setSortBy] = useState("name");
  const [sortOrder, setSortOrder] = useState("asc");
  const [keyword, setKeyword] = useState("");
  const [result, setResult] = useState<string>("");

  const run = async () => {
    const r = await batchRename(inputDir, {
      mode: mode as "in_place" | "copy_rename" | "move_rename",
      output_dir: null,
      target_type: "both",
      image_extensions: ["png", "jpg", "jpeg", "webp"],
      video_extensions: ["mp4", "mov", "mkv"],
      recursive,
      exclude_underscore: excludeUnderscore,
      sort_method: sortBy as "name" | "size",
      sort_order: sortOrder as "asc" | "desc",
      priority_keyword: keyword,
    });
    setResult(`成功 ${r.ok} 个, 失败 ${r.fail} 个${r.errors.length ? "\n" + r.errors.join("\n") : ""}`);
  };

  return (
    <div>
      <div className="card">
        <h3 className="card-title">批量序列重命名</h3>
        <PathRow label="输入目录" value={inputDir}
          onChange={(v) => setInputDir(String(v))} directory />
        <div className="form-row">
          <label className="form-label">重命名模式</label>
          <div className="form-control" style={{ maxWidth: 320 }}>
            <Dropdown selectedOptions={[mode]} value={mode}
              onOptionSelect={(_, d) => setMode(d.optionValue ?? "rename_in_place")}>
              <Option text="原地重命名" value="rename_in_place">原地重命名</Option>
              <Option text="复制后重命名" value="copy_rename">复制后重命名</Option>
              <Option text="移动后重命名" value="move_rename">移动后重命名</Option>
            </Dropdown>
          </div>
        </div>
        <div className="form-row">
          <label className="form-label">排序方式</label>
          <div className="form-control" style={{ maxWidth: 320, display: "flex", gap: 8 }}>
            <Dropdown style={{ flex: 1 }} selectedOptions={[sortBy]} value={sortBy}
              onOptionSelect={(_, d) => setSortBy(d.optionValue ?? "name")}>
              <Option text="按文件名" value="name">按文件名</Option>
              <Option text="按文件大小" value="size">按文件大小</Option>
            </Dropdown>
            <Dropdown style={{ flex: 1 }} selectedOptions={[sortOrder]} value={sortOrder}
              onOptionSelect={(_, d) => setSortOrder(d.optionValue ?? "asc")}>
              <Option text="升序" value="asc">升序</Option>
              <Option text="降序" value="desc">降序</Option>
            </Dropdown>
          </div>
        </div>
        <div className="form-row">
          <label className="form-label">关键词提前</label>
          <div className="form-control" style={{ maxWidth: 320 }}>
            <Input value={keyword} onChange={(_, d) => setKeyword(d.value)}
              placeholder="文件名包含该关键词的文件优先排序 (可选)" />
          </div>
        </div>
        <Checkbox label="递归扫描子目录" checked={recursive}
          onChange={(_, d) => setRecursive(d.checked === true)} />
        <Checkbox label="递归时排除下划线后的文字" checked={excludeUnderscore}
          onChange={(_, d) => setExcludeUnderscore(d.checked === true)} />
        <div className="action-row">
          <Button appearance="primary" onClick={run} disabled={!inputDir}>开始重命名</Button>
        </div>
        {result && <div className="cmd-preview">{result}</div>}
      </div>
    </div>
  );
}
