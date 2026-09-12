import { invoke } from "@tauri-apps/api/core";

export interface EncodeOptions {
  input: string;
  output: string;
  preset_name: string | null;
  encoder: string | null;
  crf: number | null;
  bitrate: string | null;
  speed_preset: string | null;
  resolution: string | null;
  fps: number | null;
  audio_encoder: string;
  audio_bitrate: string;
  subtitle_path: string | null;
  extra_args: string | null;
  rc_mode: string | null;
  audio_tracks: string;
  audio_tracks_custom: string;
  subtitle_tracks: string;
  subtitle_tracks_custom: string;
}

export interface StreamInfo {
  index: number;
  codec_name: string;
  profile: string;
  language: string;
  title: string;
  width: number;
  height: number;
  fps: number;
  bitrate_kbps: number;
  sample_rate: number;
  channels: number;
}

export interface MediaInfo {
  path: string;
  filename: string;
  format_name: string;
  duration_sec: number;
  total_bitrate_kbps: number;
  video_streams: StreamInfo[];
  audio_streams: StreamInfo[];
  subtitle_streams: StreamInfo[];
  chapters: { id: number; title: string }[];
  errors: string[];
}

export interface RemuxPlan {
  commands: string[][];
  originals_to_delete: string[];
  outputs: string[];
}

export interface BatchOutcome {
  ok: number;
  fail: number;
  errors: string[];
}

export interface RenameConfig {
  mode: "in_place" | "copy_rename" | "move_rename";
  output_dir: string | null;
  target_type: "images" | "videos" | "both";
  image_extensions: string[];
  video_extensions: string[];
  recursive: boolean;
  exclude_underscore: boolean;
  sort_method: "name" | "size";
  sort_order: "asc" | "desc";
  priority_keyword: string;
}

export const appVersion = (): Promise<string> => invoke("app_version");

export const qualityPresetNames = (): Promise<string[]> =>
  invoke("quality_preset_names");

export const previewEncodeCommand = (opts: EncodeOptions): Promise<string[]> =>
  invoke("preview_encode_command", { opts });

export const probeMedia = (path: string): Promise<MediaInfo> =>
  invoke("probe_media", { path });

export const buildReplaceAudio = (
  video: string, audio: string, output: string,
  audioEncoder: string, audioBitrate: string,
): Promise<string[]> =>
  invoke("build_replace_audio_cmd", {
    video, audio, output, audioEncoder, audioBitrate,
  });

export const buildExtractAudio = (
  input: string, output: string, audioEncoder: string, audioBitrate: string,
): Promise<string[]> =>
  invoke("build_extract_audio_cmd", { input, output, audioEncoder, audioBitrate });

export const buildExtractVideo = (input: string, output: string): Promise<string[]> =>
  invoke("build_extract_video_cmd", { input, output });

export const planRemux = (args: {
  inputs: string[];
  outputDir: string;
  extension: string;
  overwrite: boolean;
  audioTracks: string;
  audioCustom: string;
  subtitleTracks: string;
  subtitleCustom: string;
}): Promise<RemuxPlan> =>
  invoke("plan_remux_cmd", {
    inputs: args.inputs,
    outputDir: args.outputDir,
    extension: args.extension,
    overwrite: args.overwrite,
    audioTracks: args.audioTracks,
    audioCustom: args.audioCustom,
    subtitleTracks: args.subtitleTracks,
    subtitleCustom: args.subtitleCustom,
  });

export const createFolders = (
  txtPath: string, outputDir: string, autoNumber: boolean,
): Promise<BatchOutcome> =>
  invoke("create_folders_cmd", { txtPath, outputDir, autoNumber });

export const batchRename = (
  inputDir: string, config: RenameConfig,
): Promise<BatchOutcome> =>
  invoke("batch_rename_cmd", { inputDir, config });

export const sendFeishu = (
  webhookUrl: string, title: string, content: string, color: string, footer: string,
): Promise<void> =>
  invoke("send_feishu_cmd", {
    webhookUrl, title, content, color, footer,
  });

export const sendWebhook = (
  url: string, headers: [string, string][], body: Record<string, unknown>,
): Promise<void> =>
  invoke("send_webhook_cmd", { url, headers, body });
