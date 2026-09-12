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

export const appVersion = (): Promise<string> => invoke("app_version");

export const qualityPresetNames = (): Promise<string[]> =>
  invoke("quality_preset_names");

export const previewEncodeCommand = (opts: EncodeOptions): Promise<string[]> =>
  invoke("preview_encode_command", { opts });

export const probeMedia = (path: string): Promise<MediaInfo> =>
  invoke("probe_media", { path });
