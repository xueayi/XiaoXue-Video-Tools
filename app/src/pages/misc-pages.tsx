import { useState } from "react";
import {
  Button,
  Dropdown,
  Input,
  Option,
  Textarea,
} from "@fluentui/react-components";
import { appVersion, sendFeishu, sendWebhook } from "../lib/engine";

/* ---- 通知设置 ---- */

const FEISHU_COLORS: [string, string][] = [
  ["蓝色", "blue"],
  ["绿色", "green"],
  ["红色", "red"],
  ["黄色", "yellow"],
  ["橙色", "orange"],
  ["紫色", "purple"],
];

export function NotificationPage() {
  const [feishuUrl, setFeishuUrl] = useState("");
  const [title, setTitle] = useState("任务完成通知");
  const [content, setContent] = useState("您的视频处理任务已完成！");
  const [color, setColor] = useState("blue");
  const [webhookUrl, setWebhookUrl] = useState("");
  const [webhookBody, setWebhookBody] = useState('{"message": "任务完成"}');
  const [result, setResult] = useState("");

  const testFeishu = async () => {
    setResult("正在发送飞书通知…");
    try {
      await sendFeishu(feishuUrl, title, content, color, "来自小雪工具箱");
      setResult("✓ 飞书通知发送成功");
    } catch (e) {
      setResult(`✗ ${String(e)}`);
    }
  };

  const testWebhook = async () => {
    setResult("正在发送 Webhook…");
    try {
      let body: Record<string, unknown> = {};
      try {
        body = JSON.parse(webhookBody || "{}");
      } catch {
        setResult("✗ 请求体 JSON 解析失败");
        return;
      }
      await sendWebhook(webhookUrl, [], body);
      setResult("✓ Webhook 发送成功");
    } catch (e) {
      setResult(`✗ ${String(e)}`);
    }
  };

  return (
    <div>
      <div className="card">
        <h3 className="card-title">飞书通知</h3>
        <div className="form-row">
          <label className="form-label">Webhook URL</label>
          <div className="form-control">
            <Input value={feishuUrl} onChange={(_, d) => setFeishuUrl(d.value)}
              placeholder="飞书机器人 Webhook 地址" style={{ width: "100%" }} />
          </div>
        </div>
        <div className="form-row">
          <label className="form-label">卡片标题</label>
          <div className="form-control" style={{ maxWidth: 320 }}>
            <Input value={title} onChange={(_, d) => setTitle(d.value)} />
          </div>
        </div>
        <div className="form-row">
          <label className="form-label">消息内容</label>
          <div className="form-control">
            <Textarea value={content} onChange={(_, d) => setContent(d.value)}
              style={{ minHeight: 80 }} />
          </div>
        </div>
        <div className="form-row">
          <label className="form-label">卡片颜色</label>
          <div className="form-control" style={{ maxWidth: 200 }}>
            <Dropdown selectedOptions={[color]} value={color}
              onOptionSelect={(_, d) => {
                const label = d.optionText ?? "";
                setColor(FEISHU_COLORS.find(([n]) => n === label)?.[1] ?? "blue");
              }}>
              {FEISHU_COLORS.map(([label]) => (
                <Option key={label} text={label} value={label}>{label}</Option>
              ))}
            </Dropdown>
          </div>
        </div>
        <Button appearance="primary" onClick={testFeishu}
          disabled={!feishuUrl}>测试发送</Button>
      </div>

      <div className="card">
        <h3 className="card-title">自定义 Webhook</h3>
        <div className="form-row">
          <label className="form-label">POST URL</label>
          <div className="form-control">
            <Input value={webhookUrl} onChange={(_, d) => setWebhookUrl(d.value)}
              placeholder="自定义 POST 请求地址" style={{ width: "100%" }} />
          </div>
        </div>
        <div className="form-row">
          <label className="form-label">请求体 (JSON)</label>
          <div className="form-control">
            <Textarea value={webhookBody} onChange={(_, d) => setWebhookBody(d.value)}
              style={{ minHeight: 80 }} />
          </div>
        </div>
        <Button appearance="primary" onClick={testWebhook}
          disabled={!webhookUrl}>测试发送</Button>
      </div>

      {result && <div className="card"><div className="cmd-preview">{result}</div></div>}
    </div>
  );
}

/* ---- 使用说明 ---- */

export function HelpPage() {
  const [version] = useState(() => appVersion);
  return (
    <div>
      <div className="card">
        <h3 className="card-title">使用说明</h3>
        <p className="card-desc">
          小雪工具箱原生版 v{typeof version === "string" ? version : ""}
        </p>
        <p className="card-desc">
          当前为 Tauri 原生重写版 (M2 阶段)。视频压制、封装转换、音视频工具、
          批量工具、通知已可用；图片转换与素材质量检测请暂用 Python 版。
        </p>
        <p className="card-desc">
          提示: 兼容模式字幕渲染等高级编码特性将在后续版本对齐 Python 版。
        </p>
        <Button appearance="primary" disabled>打开在线文档 (M4)</Button>
      </div>
    </div>
  );
}
