import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

export interface TaskProgress {
  frame: number;
  fps: number;
  size_kb: number;
  time_sec: number;
  bitrate_kbps: number;
  speed: number;
  total_duration: number;
  percent: number;
  eta_sec: number;
}

/** 任务执行 Hook: 订阅事件流 + 启动/停止。 */
export function useTask() {
  const [logs, setLogs] = useState<string[]>([]);
  const [progress, setProgress] = useState<TaskProgress | null>(null);
  const [running, setRunning] = useState(false);
  const [ok, setOk] = useState<boolean | null>(null);
  const [runningName, setRunningName] = useState("");

  useEffect(() => {
    const unlisteners: (() => void)[] = [];
    (async () => {
      unlisteners.push(
        await listen<string>("task-log", (e) =>
          setLogs((prev) => [...prev.slice(-2000), e.payload]),
        ),
      );
      unlisteners.push(
        await listen<TaskProgress>("task-progress", (e) =>
          setProgress(e.payload),
        ),
      );
      unlisteners.push(
        await listen<{ ok: boolean; name: string }>("task-finished", (e) => {
          setRunning(false);
          setOk(e.payload.ok);
        }),
      );
    })();
    return () => unlisteners.forEach((u) => u());
  }, []);

  const start = async (
    name: string,
    commands: string[][],
    durationSec?: number | null,
  ): Promise<void> => {
    if (running || commands.length === 0) return;
    setLogs([]);
    setProgress(null);
    setOk(null);
    setRunning(true);
    setRunningName(name);
    try {
      await invoke("start_task", {
        name,
        commands,
        durationSec: durationSec ?? null,
      });
    } catch (e) {
      setRunning(false);
      setLogs((prev) => [...prev, `[错误] ${String(e)}`]);
    }
  };

  const stop = (): void => {
    invoke("stop_task").catch(() => {});
  };

  return { logs, progress, running, ok, runningName, start, stop };
}

export function fmtEta(sec: number): string {
  if (sec < 0) return "--";
  const s = Math.floor(sec);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  return h > 0
    ? `${h}:${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`
    : `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
}
