//! 任务完成通知 (移植自 src/notify.py)。
//!
//! 纯 payload 构建可测; 发送用 ureq (rustls), 30s 超时。

use serde_json::{json, Value};

/// 飞书卡片颜色 (notify.FEISHU_COLORS 常用子集)。
pub const FEISHU_COLORS: &[(&str, &str)] = &[
    ("蓝色 (Blue)", "blue"),
    ("绿色 (Green)", "green"),
    ("红色 (Red)", "red"),
    ("黄色 (Yellow)", "yellow"),
    ("橙色 (Orange)", "orange"),
    ("紫色 (Purple)", "purple"),
    ("灰色 (Grey)", "grey"),
    ("靛蓝 (Indigo)", "indigo"),
];

/// 构建飞书卡片消息 (notify.send_feishu_notification 的 payload 部分)。
pub fn feishu_payload(title: &str, content: &str, color: &str, footer: &str) -> Value {
    json!({
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": true},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": color
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": content}},
                {"tag": "hr"},
                {"tag": "note", "elements": [
                    {"tag": "plain_text", "content": footer}
                ]}
            ]
        }
    })
}

/// 发送飞书通知 (notify.send_feishu_notification)。
///
/// Ok(()) 发送成功; Err(原因) 失败 (URL 为空 / 网络 / 业务码非 0)。
pub fn send_feishu(webhook_url: &str, title: &str, content: &str,
                   color: &str, footer: &str) -> Result<(), String> {
    if webhook_url.is_empty() {
        return Err("飞书 Webhook URL 为空，跳过发送".into());
    }
    let payload = feishu_payload(title, content, color, footer);
    let resp = agent()
        .post(webhook_url)
        .send_json(payload)
        .map_err(|e| format!("网络请求失败: {e}"))?;
    if resp.status() != 200 {
        return Err(format!("HTTP 状态码: {}", resp.status()));
    }
    let result: Value = resp
        .into_json()
        .map_err(|e| format!("响应解析失败: {e}"))?;
    if result["code"] == 0 || result["StatusCode"] == 0 {
        Ok(())
    } else {
        Err(format!("飞书返回错误: {result}"))
    }
}

/// 发送自定义 Webhook POST (notify.send_webhook_notification)。
pub fn send_webhook(url: &str, headers: &[(String, String)],
                    body: &Value) -> Result<(), String> {
    if url.is_empty() {
        return Err("Webhook URL 为空，跳过发送".into());
    }
    let mut req = agent().post(url);
    let mut has_content_type = false;
    for (k, v) in headers {
        if k.eq_ignore_ascii_case("content-type") {
            has_content_type = true;
        }
        req = req.set(k, v);
    }
    if !has_content_type {
        req = req.set("Content-Type", "application/json");
    }
    let resp = req
        .send_json(body.clone())
        .map_err(|e| format!("网络请求失败: {e}"))?;
    let status = resp.status();
    if (200..300).contains(&status) {
        Ok(())
    } else {
        Err(format!("服务器返回非 2xx 状态码: {status}"))
    }
}

fn agent() -> ureq::Agent {
    ureq::AgentBuilder::new()
        .timeout_read(std::time::Duration::from_secs(30))
        .timeout_write(std::time::Duration::from_secs(30))
        .build()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn feishu_payload_shape() {
        let p = feishu_payload("完成", "任务 {task} 已完成", "blue", "小雪工具箱");
        assert_eq!(p["msg_type"], "interactive");
        assert_eq!(p["card"]["header"]["title"]["content"], "完成");
        assert_eq!(p["card"]["header"]["template"], "blue");
        assert_eq!(
            p["card"]["elements"][0]["text"]["content"],
            "任务 {task} 已完成"
        );
        assert_eq!(p["card"]["elements"][2]["elements"][0]["content"],
                   "小雪工具箱");
    }

    #[test]
    fn feishu_empty_url_rejected() {
        assert!(send_feishu("", "t", "c", "blue", "f").is_err());
    }

    #[test]
    fn webhook_empty_url_rejected() {
        assert!(send_webhook("", &[], &json!({})).is_err());
    }

    #[test]
    fn webhook_unreachable_reports_error() {
        // 本机保留端口, 连接必失败 (不依赖外网)
        let err = send_webhook(
            "http://127.0.0.1:1/hook",
            &[],
            &json!({"a": 1}),
        );
        assert!(err.is_err());
    }

    #[test]
    fn feishu_colors_cover_common() {
        assert!(FEISHU_COLORS.iter().any(|(n, c)| *c == "blue" && n.contains("蓝")));
    }
}
