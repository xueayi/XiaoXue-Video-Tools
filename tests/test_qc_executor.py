# -*- coding: utf-8 -*-
"""
质量检测执行器模块测试用例。

测试 src/executors/qc_executor.py 中的素材质量检测功能。
"""
import pytest
import os
from unittest.mock import patch, MagicMock
from dataclasses import dataclass
from typing import Optional

from src.executors.qc_executor import execute_qc
from src.executors.common import parse_comma_list


@dataclass
class MockQCArgs:
    """模拟 QC 参数对象"""
    scan_dir: str = ""
    report_output: str = ""
    max_bitrate: int = 0
    min_bitrate: int = 0
    max_res_preset: str = "不限制"
    max_res_custom: str = ""
    min_res_preset: str = "不限制"
    min_res_custom: str = ""
    check_pr_video: bool = True
    check_pr_image: bool = True
    custom_containers: str = ""
    custom_codecs: str = ""
    custom_images: str = ""


class TestParseCommaList:
    """测试逗号分隔列表解析"""
    
    def test_parse_empty_string(self):
        """测试空字符串"""
        result = parse_comma_list("")
        assert result == set()
    
    def test_parse_whitespace_only(self):
        """测试仅空白字符"""
        result = parse_comma_list("   ")
        assert result == set()
    
    def test_parse_single_item(self):
        """测试单个项目"""
        result = parse_comma_list("mkv")
        assert result == {"mkv"}
    
    def test_parse_multiple_items(self):
        """测试多个项目"""
        result = parse_comma_list("mkv,webm,flv")
        assert result == {"mkv", "webm", "flv"}
    
    def test_parse_with_spaces(self):
        """测试带空格的项目"""
        result = parse_comma_list(" mkv , webm , flv ")
        assert result == {"mkv", "webm", "flv"}
    
    def test_parse_with_prefix(self):
        """测试添加前缀"""
        result = parse_comma_list("mkv,webm,flv", prefix=".")
        assert result == {".mkv", ".webm", ".flv"}
    
    def test_parse_with_existing_prefix(self):
        """测试已有前缀的项目"""
        result = parse_comma_list(".mkv,webm,.flv", prefix=".")
        assert result == {".mkv", ".webm", ".flv"}
    
    def test_parse_case_insensitive(self):
        """测试大小写转换"""
        result = parse_comma_list("MKV,WebM,FLV")
        assert result == {"mkv", "webm", "flv"}
    
    def test_parse_empty_items(self):
        """测试空项目被过滤"""
        result = parse_comma_list("mkv,,webm,,,flv")
        assert result == {"mkv", "webm", "flv"}


class TestExecuteQC:
    """测试素材质量检测执行器"""
    
    @pytest.fixture
    def mock_scan_dir(self, tmp_path):
        """创建临时扫描目录"""
        scan_dir = tmp_path / "media"
        scan_dir.mkdir()
        
        # 创建一些测试文件
        (scan_dir / "video1.mp4").write_text("fake video 1")
        (scan_dir / "video2.mkv").write_text("fake video 2")
        (scan_dir / "image1.jpg").write_text("fake image 1")
        
        return str(scan_dir)
    
    @patch('src.executors.qc_executor.generate_report')
    @patch('src.executors.qc_executor.scan_directory')
    def test_execute_qc_basic(self, mock_scan, mock_report, mock_scan_dir):
        """测试基本 QC 执行"""
        mock_scan.return_value = []
        mock_report.return_value = "QC Report"
        
        args = MockQCArgs()
        args.scan_dir = mock_scan_dir
        
        execute_qc(args)
        
        mock_scan.assert_called_once()
        mock_report.assert_called_once()
    
    @patch('src.executors.qc_executor.generate_report')
    @patch('src.executors.qc_executor.scan_directory')
    def test_execute_qc_auto_report_path(self, mock_scan, mock_report, mock_scan_dir, capsys):
        """测试自动生成报告路径"""
        mock_scan.return_value = []
        mock_report.return_value = "QC Report"
        
        args = MockQCArgs()
        args.scan_dir = mock_scan_dir
        args.report_output = ""  # 自动生成
        
        execute_qc(args)
        
        # 验证报告路径包含目录和 "QC_报告"
        call_args = mock_report.call_args
        report_path = call_args[0][1]  # 第二个位置参数
        assert "QC_报告" in report_path or mock_scan_dir in report_path
    
    @patch('src.executors.qc_executor.generate_report')
    @patch('src.executors.qc_executor.scan_directory')
    def test_execute_qc_with_resolution_preset(self, mock_scan, mock_report, mock_scan_dir):
        """测试分辨率预设处理"""
        mock_scan.return_value = []
        mock_report.return_value = "QC Report"
        
        args = MockQCArgs()
        args.scan_dir = mock_scan_dir
        args.max_res_preset = "1080P (1920x1080)"
        args.min_res_preset = "720P (1280x720)"
        
        execute_qc(args)
        
        call_kwargs = mock_scan.call_args.kwargs
        assert call_kwargs["max_resolution"] == "1920x1080"
        assert call_kwargs["min_resolution"] == "1280x720"
    
    @patch('src.executors.qc_executor.generate_report')
    @patch('src.executors.qc_executor.scan_directory')
    def test_execute_qc_with_custom_resolution(self, mock_scan, mock_report, mock_scan_dir):
        """测试自定义分辨率"""
        mock_scan.return_value = []
        mock_report.return_value = "QC Report"
        
        args = MockQCArgs()
        args.scan_dir = mock_scan_dir
        args.max_res_preset = "自定义"
        args.max_res_custom = "2560x1440"
        
        execute_qc(args)
        
        call_kwargs = mock_scan.call_args.kwargs
        assert call_kwargs["max_resolution"] == "2560x1440"
    
    @patch('src.executors.qc_executor.generate_report')
    @patch('src.executors.qc_executor.scan_directory')
    def test_execute_qc_with_bitrate(self, mock_scan, mock_report, mock_scan_dir):
        """测试码率阈值"""
        mock_scan.return_value = []
        mock_report.return_value = "QC Report"
        
        args = MockQCArgs()
        args.scan_dir = mock_scan_dir
        args.max_bitrate = 50000
        args.min_bitrate = 1000
        
        execute_qc(args)
        
        call_kwargs = mock_scan.call_args.kwargs
        assert call_kwargs["max_bitrate_kbps"] == 50000
        assert call_kwargs["min_bitrate_kbps"] == 1000
    
    @patch('src.executors.qc_executor.generate_report')
    @patch('src.executors.qc_executor.scan_directory')
    def test_execute_qc_with_custom_containers(self, mock_scan, mock_report, mock_scan_dir):
        """测试自定义容器兼容性规则"""
        mock_scan.return_value = []
        mock_report.return_value = "QC Report"
        
        args = MockQCArgs()
        args.scan_dir = mock_scan_dir
        args.custom_containers = "mkv,webm,flv"
        
        execute_qc(args)
        
        call_kwargs = mock_scan.call_args.kwargs
        assert ".mkv" in call_kwargs["incompatible_containers"]
        assert ".webm" in call_kwargs["incompatible_containers"]
        assert ".flv" in call_kwargs["incompatible_containers"]
    
    @patch('src.executors.qc_executor.generate_report')
    @patch('src.executors.qc_executor.scan_directory')
    def test_execute_qc_with_custom_codecs(self, mock_scan, mock_report, mock_scan_dir):
        """测试自定义编码兼容性规则"""
        mock_scan.return_value = []
        mock_report.return_value = "QC Report"
        
        args = MockQCArgs()
        args.scan_dir = mock_scan_dir
        args.custom_codecs = "vp9,av1,hevc"
        
        execute_qc(args)
        
        call_kwargs = mock_scan.call_args.kwargs
        assert "vp9" in call_kwargs["incompatible_codecs"]
        assert "av1" in call_kwargs["incompatible_codecs"]
        assert "hevc" in call_kwargs["incompatible_codecs"]
    
    @patch('src.executors.qc_executor.generate_report')
    @patch('src.executors.qc_executor.scan_directory')
    def test_execute_qc_pr_checks(self, mock_scan, mock_report, mock_scan_dir):
        """测试 PR 兼容性检测开关"""
        mock_scan.return_value = []
        mock_report.return_value = "QC Report"
        
        args = MockQCArgs()
        args.scan_dir = mock_scan_dir
        args.check_pr_video = False
        args.check_pr_image = True
        
        execute_qc(args)
        
        call_kwargs = mock_scan.call_args.kwargs
        assert call_kwargs["check_pr_video"] == False
        assert call_kwargs["check_pr_image"] == True


class TestQCEdgeCases:
    """测试边界情况"""
    
    @patch('src.executors.qc_executor.generate_report')
    @patch('src.executors.qc_executor.scan_directory')
    def test_execute_qc_no_resolution_limit(self, mock_scan, mock_report, tmp_path):
        """测试不限制分辨率"""
        scan_dir = tmp_path / "media"
        scan_dir.mkdir()
        
        mock_scan.return_value = []
        mock_report.return_value = "QC Report"
        
        args = MockQCArgs()
        args.scan_dir = str(scan_dir)
        args.max_res_preset = "不限制"
        args.min_res_preset = "不限制"
        
        execute_qc(args)
        
        call_kwargs = mock_scan.call_args.kwargs
        assert call_kwargs["max_resolution"] == ""
        assert call_kwargs["min_resolution"] == ""
    
    @patch('src.executors.qc_executor.generate_report')
    @patch('src.executors.qc_executor.scan_directory')
    def test_execute_qc_empty_custom_rules(self, mock_scan, mock_report, tmp_path):
        """测试空的自定义规则"""
        scan_dir = tmp_path / "media"
        scan_dir.mkdir()
        
        mock_scan.return_value = []
        mock_report.return_value = "QC Report"
        
        args = MockQCArgs()
        args.scan_dir = str(scan_dir)
        args.custom_containers = ""
        args.custom_codecs = ""
        args.custom_images = ""
        
        execute_qc(args)
        
        call_kwargs = mock_scan.call_args.kwargs
        # 空规则应为 None
        assert call_kwargs["incompatible_containers"] is None
        assert call_kwargs["incompatible_codecs"] is None
        assert call_kwargs["incompatible_images"] is None
