# -*- coding: utf-8 -*-
"""
通知模块：支持飞书通知和自定义 Webhook 通知。
"""
import json
import requests
from typing import Optional, Dict, Any

from colorama import Fore, Style


# 飞书卡片颜色预设
FEISHU_COLORS = {
    "蓝色 (Blue)": "blue",
    "绿色 (Green)": "green",
    "红色 (Red)": "red",
    "橙色 (Orange)": "orange",
    "紫色 (Purple)": "purple",
    "靛蓝 (Indigo)": "indigo",
    "灰色 (Grey)": "grey",
}


def send_feishu_notification(
    webhook_url: str,
    title: str,
    content: str,
    color: str = "blue",
    footer: str = "来自小雪工具箱",
) -> bool:
    """
    发送飞书机器人卡片消息。

    Args:
        webhook_url: 飞书 Webhook URL
        title: 卡片标题
        content: 消息内容 (支持 lark_md 格式)
        color: 卡片头部颜色 (blue/green/red/orange/purple/indigo/grey)
        footer: 卡片底部备注

    Returns:
        bool: 发送是否成功
    """
    if not webhook_url:
        print(f"{Fore.YELLOW}[警告] 飞书 Webhook URL 为空，跳过发送{Style.RESET_ALL}")
        return False

    # 构建飞书卡片消息
    message = {
        "msg_type": "interactive",
        "card": {
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": title
                },
                "template": color
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": content
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": footer
                        }
                    ]
                }
            ]
        }
    }

    try:
        response = requests.post(
            webhook_url,
            headers={"Content-Type": "application/json"},
            data=json.dumps(message),
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            if result.get("code") == 0 or result.get("StatusCode") == 0:
                print(f"{Fore.GREEN}[成功] 飞书通知发送成功{Style.RESET_ALL}")
                return True
            else:
                print(f"{Fore.RED}[失败] 飞书返回错误: {result}{Style.RESET_ALL}")
                return False
        else:
            print(f"{Fore.RED}[失败] HTTP 状态码: {response.status_code} - {response.text}{Style.RESET_ALL}")
            return False

    except requests.exceptions.Timeout:
        print(f"{Fore.RED}[错误] 请求超时{Style.RESET_ALL}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"{Fore.RED}[错误] 网络请求失败: {str(e)}{Style.RESET_ALL}")
        return False
    except Exception as e:
        print(f"{Fore.RED}[错误] 发送飞书通知时发生异常: {str(e)}{Style.RESET_ALL}")
        return False


def send_webhook_notification(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    body: Optional[Dict[str, Any]] = None,
    headers_json: Optional[str] = None,
    body_json: Optional[str] = None,
) -> bool:
    """
    发送自定义 Webhook POST 请求。

    Args:
        url: POST 请求 URL
        headers: 请求头字典 (优先使用)
        body: 请求体字典 (优先使用)
        headers_json: 请求头 JSON 字符串 (备选)
        body_json: 请求体 JSON 字符串 (备选)

    Returns:
        bool: 发送是否成功
    """
    if not url:
        print(f"{Fore.YELLOW}[警告] Webhook URL 为空，跳过发送{Style.RESET_ALL}")
        return False

    # 解析 Headers
    final_headers = {"Content-Type": "application/json"}
    if headers:
        final_headers.update(headers)
    elif headers_json:
        try:
            parsed_headers = json.loads(headers_json)
            if isinstance(parsed_headers, dict):
                final_headers.update(parsed_headers)
        except json.JSONDecodeError as e:
            print(f"{Fore.RED}[错误] Headers JSON 解析失败: {str(e)}{Style.RESET_ALL}")
            return False

    # 解析 Body
    final_body = body
    if final_body is None and body_json:
        try:
            final_body = json.loads(body_json)
        except json.JSONDecodeError as e:
            print(f"{Fore.RED}[错误] Body JSON 解析失败: {str(e)}{Style.RESET_ALL}")
            return False

    if final_body is None:
        final_body = {}

    try:
        print(f"{Fore.CYAN}[请求] POST {url}{Style.RESET_ALL}")
        print(f"  Headers: {json.dumps(final_headers, ensure_ascii=False)}")
        print(f"  Body: {json.dumps(final_body, ensure_ascii=False)}")

        response = requests.post(
            url,
            headers=final_headers,
            json=final_body,
            timeout=30
        )

        print(f"\n{Fore.CYAN}[响应] 状态码: {response.status_code}{Style.RESET_ALL}")
        
        # 尝试解析 JSON 响应
        try:
            resp_json = response.json()
            print(f"  响应内容: {json.dumps(resp_json, ensure_ascii=False, indent=2)}")
        except:
            print(f"  响应内容: {response.text[:500]}")

        if 200 <= response.status_code < 300:
            print(f"\n{Fore.GREEN}[成功] Webhook 请求发送成功{Style.RESET_ALL}")
            return True
        else:
            print(f"\n{Fore.YELLOW}[警告] 服务器返回非 2xx 状态码{Style.RESET_ALL}")
            return False

    except requests.exceptions.Timeout:
        print(f"{Fore.RED}[错误] 请求超时{Style.RESET_ALL}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"{Fore.RED}[错误] 网络请求失败: {str(e)}{Style.RESET_ALL}")
        return False
    except Exception as e:
        print(f"{Fore.RED}[错误] 发送 Webhook 时发生异常: {str(e)}{Style.RESET_ALL}")
        return False
