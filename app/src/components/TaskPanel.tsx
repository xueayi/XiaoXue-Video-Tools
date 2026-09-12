import { Button, ProgressBar, Spinner } from "@fluentui/react-components";
import { PlayFilled, StopFilled } from "@fluentui/react-icons";
import { fmtEta, useTask } from "../lib/task";

export interface TaskPlan {
  name: string;
  commands: string[][];
  durationSec?: number | null;
}

/**
 * 任务面板: 开始执行 / 停止 / 进度条 / 指标 / 日志终端。
 * 页面只需提供 start(): Promise<TaskPlan>。
 */
export function TaskPanel({
  build,
  disabled,
}: {
  build: () => Promise<TaskPlan>;
  disabled?: boolean;
}) {
  const task = useTask();

  const onExecute = async () => {
    const plan = await build();
    await task.start(plan.name, plan.commands, plan.durationSec ?? null);
  };

  return (
    <div>
      <div className="action-row">
        <Button
          appearance="primary"
          icon={<PlayFilled />}
          size="large"
          disabled={disabled || task.running}
          onClick={onExecute}
        >
          开始执行
        </Button>
        {task.running && (
          <Button
            icon={<StopFilled />}
            size="large"
            appearance="subtle"
            onClick={task.stop}
          >
            停止
          </Button>
        )}
        {task.running && <Spinner size="tiny" label={task.runningName} />}
        {!task.running && task.ok !== null && (
          <span
            style={{
              color: task.ok ? "var(--success)" : "#c42b1c",
              fontWeight: 600,
              alignSelf: "center",
            }}
          >
            {task.ok ? "✓ 执行完成" : "✗ 执行失败"}
          </span>
        )}
      </div>

      {task.running && task.progress && (
        <div style={{ marginBottom: 12 }}>
          <ProgressBar
            shape="rounded"
            value={task.progress.percent > 0 ? task.progress.percent / 100 : undefined}
            thickness="large"
          />
          <div className="task-stats">
            {task.progress.percent > 0 && (
              <span>{task.progress.percent.toFixed(1)}%</span>
            )}
            {task.progress.fps > 0 && <span>{task.progress.fps} fps</span>}
            {task.progress.speed > 0 && <span>{task.progress.speed}x</span>}
            <span>{fmtEta(task.progress.eta_sec)}</span>
          </div>
        </div>
      )}

      <div className="cmd-preview" style={{ maxHeight: 320, overflowY: "auto" }}>
        {task.logs.length === 0
          ? "任务日志将在这里输出…"
          : task.logs.join("\n")}
      </div>
    </div>
  );
}
