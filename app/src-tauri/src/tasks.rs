//! 任务执行器: 后台线程顺序执行命令列表, 事件流推送给前端。
//!
//! 事件:
//! - `task-log`      { line: string }           每行输出
//! - `task-progress` ProgressInfo               ffmpeg 进度 (time 行触发)
//! - `task-finished` { ok, name }               整体结束
//!
//! 同一时间只允许一个任务; stop_task 通过 kill 子进程中断。

use std::io::{BufRead, BufReader};
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};

use tauri::{AppHandle, Emitter, State};

use xiaoxue_engine::progress::ProgressParser;

/// 子进程句柄容器 (供 stop_task 杀掉)。
pub struct TaskState(pub Arc<Mutex<Option<Child>>>);

impl Default for TaskState {
    fn default() -> Self {
        Self(Arc::new(Mutex::new(None)))
    }
}

/// 启动任务: 顺序执行 commands 列表。
///
/// `duration_sec`: 可选的总时长 (用于百分比/ETA), 前端可通过 probe 获取。
#[tauri::command]
pub fn start_task(
    app: AppHandle,
    state: State<'_, TaskState>,
    name: String,
    commands: Vec<Vec<String>>,
    duration_sec: Option<f64>,
) -> Result<(), String> {
    if commands.is_empty() {
        return Err("没有可执行的命令".into());
    }
    {
        let mut guard = state.0.lock().unwrap();
        if guard.is_some() {
            return Err("已有任务在运行".into());
        }
    }

    let shared = state.0.clone(); // 与 stop_task 共享同一容器
    let app2 = app.clone();
    std::thread::spawn(move || {
        let killed = Arc::new(std::sync::atomic::AtomicBool::new(false));
        let mut overall_ok = true;

        for (i, cmd) in commands.iter().enumerate() {
            let _ = app2.emit("task-log", format!("[{}/{}] 执行命令:\n{}\n{}", i + 1, commands.len(), cmd.join(" "), "-".repeat(50)));
            let spawn = Command::new(&cmd[0])
                .args(&cmd[1..])
                .stdout(Stdio::inherit())
                .stderr(Stdio::piped())
                .spawn();

            let mut child = match spawn {
                Ok(c) => c,
                Err(e) => {
                    let _ = app2.emit("task-log", format!("[错误] 无法启动: {e}\n"));
                    overall_ok = false;
                    break;
                }
            };
            let stderr = child.stderr.take();
            *shared.lock().unwrap() = Some(child);

            let mut parser = ProgressParser::new();
            if let Some(d) = duration_sec {
                parser.set_duration(d);
            }
            if let Some(stderr) = stderr {
                for line in BufReader::new(stderr)
                    .lines()
                    .map_while(Result::ok)
                {
                    let _ = app2.emit("task-log", line.clone());
                    if let Some(info) = parser.feed_line(&line) {
                        let _ = app2.emit("task-progress", info);
                    }
                }
            }

            // 回收子进程 (若未被 stop_task 取走)
            let code = {
                let mut guard = shared.lock().unwrap();
                match guard.as_mut() {
                    Some(c) => c.wait().ok().and_then(|s| s.code()).unwrap_or(-1),
                    None => -1, // 已被 stop_task 取走并终止
                }
            };
            if code != 0 {
                let reason = if killed.load(std::sync::atomic::Ordering::Relaxed) {
                    "任务已停止"
                } else {
                    "执行失败"
                };
                let _ = app2.emit("task-log", format!("\n[{reason}] 退出码 {code}\n"));
                overall_ok = false;
                break;
            }
            if killed.load(std::sync::atomic::Ordering::Relaxed) {
                overall_ok = false;
                break;
            }
        }

        let _ = app2.emit("task-finished", serde_json::json!({
            "ok": overall_ok,
            "name": name,
        }));
    });
    Ok(())
}

/// 停止当前任务 (终止子进程)。
#[tauri::command]
pub fn stop_task(state: State<'_, TaskState>) -> Result<(), String> {
    let mut guard = state.0.lock().unwrap();
    if let Some(mut child) = guard.take() {
        let _ = child.kill();
        let _ = child.wait();
        Ok(())
    } else {
        Err("没有正在运行的任务".into())
    }
}
