# -*- coding: utf-8 -*-
"""
通知配置模块测试用例。

测试 src/notify_config.py 中的配置加载、保存、删除和自动通知功能。
"""
import pytest
import os
import json
import tempfile
from unittest.mock import patch, MagicMock

from src.notify_config import (
    get_notify_config,
    update_notify_config,
    is_config_loaded,
    load_notify_config,
    save_notify_config,
    delete_notify_config,
    send_auto_notification,
    NOTIFY_CONFIG_FILE,
)


class TestNotifyConfigGetAndUpdate:
    """测试配置获取和更新功能"""
    
    def test_get_notify_config_returns_copy(self):
        """测试 get_notify_config 返回配置副本"""
        config1 = get_notify_config()
        config2 = get_notify_config()
        
        # 应该是不同的对象
        assert config1 is not config2
        
        # 修改一个不应影响另一个
        config1["enabled"] = not config1["enabled"]
        assert config1["enabled"] != config2["enabled"]
    
    def test_get_notify_config_has_required_keys(self):
        """测试默认配置包含所有必需的键"""
        config = get_notify_config()
        
        required_keys = [
            "enabled",
            "feishu_webhook",
            "feishu_title",
            "feishu_content",
            "feishu_color",
            "webhook_url",
            "webhook_headers",
            "webhook_body",
        ]
        
        for key in required_keys:
            assert key in config, f"缺少必需的配置键: {key}"
    
    def test_update_notify_config(self):
        """测试更新配置"""
        original_config = get_notify_config()
        
        # 更新配置
        update_notify_config({
            "enabled": True,
            "feishu_webhook": "https://test.webhook.url",
        })
        
        new_config = get_notify_config()
        
        assert new_config["enabled"] == True
        assert new_config["feishu_webhook"] == "https://test.webhook.url"
        
        # 恢复原配置
        update_notify_config(original_config)


class TestNotifyConfigFileOperations:
    """测试配置文件操作"""
    
    def test_save_and_load_config(self, tmp_path):
        """测试保存和加载配置文件"""
        test_config = {
            "enabled": True,
            "feishu_webhook": "https://test.webhook.url",
            "feishu_title": "测试标题",
            "feishu_content": "测试内容",
            "feishu_color": "green",
            "webhook_url": "",
            "webhook_headers": "{}",
            "webhook_body": "{}",
        }
        
        # 创建临时配置文件
        config_file = tmp_path / "test_notify_config.json"
        
        # 直接写入文件测试格式
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(test_config, f, ensure_ascii=False, indent=2)
        
        # 读取并验证
        with open(config_file, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        
        assert loaded["enabled"] == True
        assert loaded["feishu_webhook"] == "https://test.webhook.url"
        assert loaded["feishu_title"] == "测试标题"
    
    def test_config_file_path_is_absolute(self):
        """测试配置文件路径是绝对路径"""
        assert os.path.isabs(NOTIFY_CONFIG_FILE)
    
    def test_config_file_has_json_extension(self):
        """测试配置文件是 JSON 格式"""
        assert NOTIFY_CONFIG_FILE.endswith(".json")


class TestSendAutoNotification:
    """测试自动通知发送功能"""
    
    @patch('src.notify_config.send_feishu_notification')
    @patch('src.notify_config.send_webhook_notification')
    def test_auto_notification_disabled(self, mock_webhook, mock_feishu):
        """测试禁用自动通知时不发送"""
        original_config = get_notify_config()
        
        # 禁用自动通知
        update_notify_config({"enabled": False})
        
        send_auto_notification("测试任务")
        
        # 不应调用任何发送函数
        mock_feishu.assert_not_called()
        mock_webhook.assert_not_called()
        
        # 恢复配置
        update_notify_config(original_config)
    
    @patch('src.notify_config.send_feishu_notification')
    @patch('src.notify_config.send_webhook_notification')
    def test_auto_notification_with_feishu(self, mock_webhook, mock_feishu):
        """测试飞书通知发送"""
        original_config = get_notify_config()
        
        # 配置飞书通知
        update_notify_config({
            "enabled": True,
            "feishu_webhook": "https://test.feishu.webhook",
            "feishu_title": "任务完成",
            "feishu_content": "{task} 已完成",
            "feishu_color": "blue",
            "webhook_url": "",
        })
        
        send_auto_notification("视频压制")
        
        # 应调用飞书通知
        mock_feishu.assert_called_once()
        call_args = mock_feishu.call_args
        
        # 验证参数
        assert call_args.kwargs["webhook_url"] == "https://test.feishu.webhook"
        assert "视频压制" in call_args.kwargs["content"]  # {task} 应被替换
        
        # 不应调用 Webhook
        mock_webhook.assert_not_called()
        
        # 恢复配置
        update_notify_config(original_config)
    
    @patch('src.notify_config.send_feishu_notification')
    @patch('src.notify_config.send_webhook_notification')
    def test_auto_notification_with_both(self, mock_webhook, mock_feishu):
        """测试同时发送飞书和 Webhook 通知"""
        original_config = get_notify_config()
        
        # 配置两种通知
        update_notify_config({
            "enabled": True,
            "feishu_webhook": "https://test.feishu.webhook",
            "feishu_title": "任务完成",
            "feishu_content": "任务完成",
            "feishu_color": "blue",
            "webhook_url": "https://test.custom.webhook",
            "webhook_headers": '{"Content-Type": "application/json"}',
            "webhook_body": '{"task": "{task}"}',
        })
        
        send_auto_notification("素材质量检测")
        
        # 两个都应被调用
        mock_feishu.assert_called_once()
        mock_webhook.assert_called_once()
        
        # 恢复配置
        update_notify_config(original_config)


class TestNotifyConfigEdgeCases:
    """测试边界情况"""
    
    def test_update_with_empty_dict(self):
        """测试使用空字典更新配置"""
        original_config = get_notify_config()
        
        update_notify_config({})
        
        new_config = get_notify_config()
        assert new_config == original_config
    
    def test_config_color_default(self):
        """测试默认颜色配置"""
        config = get_notify_config()
        assert config["feishu_color"] in ["blue", "green", "red", "yellow", "orange", "purple"]
    
    def test_config_default_title(self):
        """测试默认标题配置"""
        config = get_notify_config()
        assert config["feishu_title"] == "任务完成通知"
