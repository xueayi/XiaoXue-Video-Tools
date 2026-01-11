# -*- coding: utf-8 -*-
"""
EncodeParams 数据类和 resolve_encoder_params 函数的单元测试。
每个测试都进行完整的参数验证。
"""
import pytest
import os
from dataclasses import dataclass
from typing import Optional

# 导入被测模块
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.encode_params import (
    EncodeParams,
    EncodeMode,
    resolve_encoder_params,
    print_encode_info,
)
from src.presets import (
    QUALITY_PRESETS,
    ENCODERS,
    AUDIO_ENCODERS,
    RATE_CONTROL_MODES,
)
from src.utils import generate_output_path


class TestEncodeParams:
    """EncodeParams 数据类测试"""
    
    def test_default_values(self):
        """测试默认值"""
        params = EncodeParams(
            input_path="/test/input.mp4",
            output_path="/test/output.mp4",
        )
        # 验证所有默认值
        assert params.input_path == "/test/input.mp4"
        assert params.output_path == "/test/output.mp4"
        assert params.encoder == "libx264"
        assert params.crf is None
        assert params.bitrate is None
        assert params.speed_preset is None
        assert params.rc_mode is None
        assert params.resolution is None
        assert params.fps is None
        assert params.audio_encoder == "copy"
        assert params.audio_bitrate == "192k"
        assert params.subtitle_path is None
        assert params.compat_mode is False
        assert params.extra_args is None
        assert params.dry_run is False
        assert params.is_custom is False
        assert params.preset_name is None
    
    def test_get_encode_mode_normal(self):
        """测试普通模式判断"""
        params = EncodeParams(
            input_path="/test/input.mp4",
            output_path="/test/output.mp4",
        )
        assert params.get_encode_mode() == EncodeMode.NORMAL
        # 验证模式判断不影响其他参数
        assert params.compat_mode is False
        assert params.subtitle_path is None
        assert params.is_custom is False
    
    def test_get_encode_mode_compat(self):
        """测试兼容模式判断"""
        params = EncodeParams(
            input_path="/test/input.mp4",
            output_path="/test/output.mp4",
            subtitle_path="/test/sub.ass",
            compat_mode=True,
        )
        assert params.get_encode_mode() == EncodeMode.COMPAT
        # 验证兼容模式相关参数
        assert params.compat_mode is True
        assert params.subtitle_path == "/test/sub.ass"
    
    def test_get_encode_mode_compat_no_subtitle(self):
        """测试兼容模式但无字幕时应为普通模式"""
        params = EncodeParams(
            input_path="/test/input.mp4",
            output_path="/test/output.mp4",
            compat_mode=True,
        )
        assert params.get_encode_mode() == EncodeMode.NORMAL
        assert params.compat_mode is True
        assert params.subtitle_path is None
    
    def test_get_encode_mode_2pass(self):
        """测试 2-Pass 模式判断"""
        params = EncodeParams(
            input_path="/test/input.mp4",
            output_path="/test/output.mp4",
            is_custom=True,
            rc_mode="2pass",
            bitrate="10M",
        )
        assert params.get_encode_mode() == EncodeMode.TWO_PASS
        # 验证 2-Pass 相关参数
        assert params.is_custom is True
        assert params.rc_mode == "2pass"
        assert params.bitrate == "10M"
    
    def test_get_encode_mode_2pass_no_bitrate(self):
        """测试 2-Pass 模式无码率时应为普通模式"""
        params = EncodeParams(
            input_path="/test/input.mp4",
            output_path="/test/output.mp4",
            is_custom=True,
            rc_mode="2pass",
            bitrate=None,
        )
        assert params.get_encode_mode() == EncodeMode.NORMAL
        assert params.rc_mode == "2pass"
        assert params.bitrate is None


class TestEncodeParamsValidation:
    """EncodeParams 验证逻辑测试"""
    
    def test_validate_input_not_exists(self):
        """测试输入文件不存在"""
        params = EncodeParams(
            input_path="/nonexistent/path.mp4",
            output_path="/test/output.mp4",
        )
        is_valid, msg = params.validate()
        assert is_valid is False
        assert "输入文件不存在" in msg
    
    def test_validate_subtitle_not_exists(self, mock_video_file):
        """测试字幕文件不存在"""
        params = EncodeParams(
            input_path=mock_video_file,
            output_path="/test/output.mp4",
            subtitle_path="/nonexistent/sub.ass",
        )
        is_valid, msg = params.validate()
        assert is_valid is False
        assert "字幕文件不存在" in msg
    
    def test_validate_crf_out_of_range(self, mock_video_file):
        """测试 CRF 超出范围"""
        params = EncodeParams(
            input_path=mock_video_file,
            output_path="/test/output.mp4",
            crf=100,
        )
        is_valid, msg = params.validate()
        assert is_valid is False
        assert "CRF 值超出范围" in msg
    
    def test_validate_crf_boundary_valid(self, mock_video_file):
        """测试 CRF 边界值 (有效)"""
        for crf in [0, 51]:
            params = EncodeParams(
                input_path=mock_video_file,
                output_path="/test/output.mp4",
                crf=crf,
            )
            is_valid, _ = params.validate()
            assert is_valid is True
    
    def test_validate_resolution_invalid_format(self, mock_video_file):
        """测试分辨率格式错误"""
        params = EncodeParams(
            input_path=mock_video_file,
            output_path="/test/output.mp4",
            resolution="1920",
        )
        is_valid, msg = params.validate()
        assert is_valid is False
        assert "分辨率格式错误" in msg
    
    def test_validate_resolution_valid(self, mock_video_file):
        """测试分辨率格式正确"""
        params = EncodeParams(
            input_path=mock_video_file,
            output_path="/test/output.mp4",
            resolution="1920x1080",
        )
        is_valid, _ = params.validate()
        assert is_valid is True
    
    def test_validate_all_valid(self, mock_video_file, mock_subtitle_file):
        """测试所有参数有效"""
        params = EncodeParams(
            input_path=mock_video_file,
            output_path="/test/output.mp4",
            subtitle_path=mock_subtitle_file,
            crf=18,
            resolution="1920x1080",
        )
        is_valid, msg = params.validate()
        assert is_valid is True
        assert msg == ""


class TestResolveEncoderParams:
    """resolve_encoder_params 函数测试 - 完整参数验证"""
    
    def test_preset_mode_full_params(self, base_args):
        """测试预设模式 - 完整参数验证"""
        params = resolve_encoder_params(
            args=base_args,
            quality_presets=QUALITY_PRESETS,
            encoders=ENCODERS,
            audio_encoders=AUDIO_ENCODERS,
            rate_control_modes=RATE_CONTROL_MODES,
            generate_output_path_func=generate_output_path,
        )
        
        # 基本信息
        assert params.is_custom is False
        assert params.preset_name == "【均衡画质】x264常用导出(CRF18)"
        
        # 视频编码参数
        assert params.encoder == "libx264"
        assert params.crf == 18
        assert params.speed_preset == "medium"
        assert params.bitrate is None  # 预设模式无码率
        assert params.rc_mode is None  # 预设模式无码率控制
        
        # 视频输出参数
        assert params.resolution is None  # 预设模式不设置分辨率
        assert params.fps is None  # 预设模式不设置帧率
        
        # 音频参数
        assert params.audio_encoder == "copy"
        assert params.audio_bitrate == "192k"
        
        # 其他参数
        assert params.subtitle_path is None
        assert params.compat_mode is False
        assert params.extra_args is None
        assert params.dry_run is True  # MockArgs 默认 debug_mode=True
        
        # 编码模式
        assert params.get_encode_mode() == EncodeMode.NORMAL
    
    def test_custom_mode_full_params(self, mock_video_file):
        """测试自定义模式 - 完整参数验证"""
        from tests.conftest import MockArgs
        
        args = MockArgs(
            input=mock_video_file,
            preset="自定义 (Custom)",
            encoder="H.264 (CPU - libx264)",
            crf=20,
            speed_preset="slow",
            rate_control="CRF/CQ (恒定质量)",
            video_bitrate="",
            resolution="1920x1080",
            fps=30,
            audio_encoder="AAC (推荐)",
            audio_bitrate="256k",
        )
        
        params = resolve_encoder_params(
            args=args,
            quality_presets=QUALITY_PRESETS,
            encoders=ENCODERS,
            audio_encoders=AUDIO_ENCODERS,
            rate_control_modes=RATE_CONTROL_MODES,
            generate_output_path_func=generate_output_path,
        )
        
        # 基本信息
        assert params.is_custom is True
        assert params.preset_name == "自定义 (Custom)"
        
        # 视频编码参数
        assert params.encoder == "libx264"
        assert params.crf == 20
        assert params.speed_preset == "slow"
        assert params.bitrate is None
        assert params.rc_mode == "crf"
        
        # 视频输出参数
        assert params.resolution == "1920x1080"
        assert params.fps == 30
        
        # 音频参数
        assert params.audio_encoder == "aac"
        assert params.audio_bitrate == "256k"
        
        # 编码模式
        assert params.get_encode_mode() == EncodeMode.NORMAL
    
    def test_auto_output_path(self, base_args):
        """测试自动生成输出路径"""
        base_args.output = ""
        
        params = resolve_encoder_params(
            args=base_args,
            quality_presets=QUALITY_PRESETS,
            encoders=ENCODERS,
            audio_encoders=AUDIO_ENCODERS,
            rate_control_modes=RATE_CONTROL_MODES,
            generate_output_path_func=generate_output_path,
        )
        
        assert params.output_path != ""
        assert params.input_path != params.output_path


class TestCustomModeEncoders:
    """自定义模式 - 不同编码器测试 - 完整参数验证"""
    
    @pytest.mark.parametrize("encoder_name,expected_encoder,expected_preset", [
        ("H.264 (CPU - libx264)", "libx264", "medium"),
        ("H.265/HEVC (CPU - libx265)", "libx265", "medium"),
    ])
    def test_cpu_encoders(self, mock_video_file, encoder_name, expected_encoder, expected_preset):
        """测试 CPU 编码器 - 使用 speed_preset"""
        from tests.conftest import MockArgs
        
        args = MockArgs(
            input=mock_video_file,
            preset="自定义 (Custom)",
            encoder=encoder_name,
            speed_preset="medium",
            crf=18,
        )
        
        params = resolve_encoder_params(
            args=args,
            quality_presets=QUALITY_PRESETS,
            encoders=ENCODERS,
            audio_encoders=AUDIO_ENCODERS,
            rate_control_modes=RATE_CONTROL_MODES,
            generate_output_path_func=generate_output_path,
        )
        
        assert params.encoder == expected_encoder
        assert params.speed_preset == expected_preset
        assert params.crf == 18
        assert params.is_custom is True
        assert params.audio_encoder == "copy"
    
    @pytest.mark.parametrize("encoder_name,expected_encoder", [
        ("H.264 (NVIDIA NVENC)", "h264_nvenc"),
        ("H.265/HEVC (NVIDIA NVENC)", "hevc_nvenc"),
    ])
    def test_nvenc_encoders(self, mock_video_file, encoder_name, expected_encoder):
        """测试 NVENC 编码器 - 使用 nvenc_preset"""
        from tests.conftest import MockArgs
        
        args = MockArgs(
            input=mock_video_file,
            preset="自定义 (Custom)",
            encoder=encoder_name,
            nvenc_preset="p5",
            crf=18,
        )
        
        params = resolve_encoder_params(
            args=args,
            quality_presets=QUALITY_PRESETS,
            encoders=ENCODERS,
            audio_encoders=AUDIO_ENCODERS,
            rate_control_modes=RATE_CONTROL_MODES,
            generate_output_path_func=generate_output_path,
        )
        
        assert params.encoder == expected_encoder
        assert params.speed_preset == "p5"  # NVENC 使用 nvenc_preset
        assert params.crf == 18
        assert params.is_custom is True
    
    @pytest.mark.parametrize("encoder_name,expected_encoder", [
        ("H.264 (Intel QSV)", "h264_qsv"),
        ("H.264 (AMD AMF)", "h264_amf"),
    ])
    def test_other_hw_encoders(self, mock_video_file, encoder_name, expected_encoder):
        """测试其他硬件编码器"""
        from tests.conftest import MockArgs
        
        args = MockArgs(
            input=mock_video_file,
            preset="自定义 (Custom)",
            encoder=encoder_name,
            crf=18,
        )
        
        params = resolve_encoder_params(
            args=args,
            quality_presets=QUALITY_PRESETS,
            encoders=ENCODERS,
            audio_encoders=AUDIO_ENCODERS,
            rate_control_modes=RATE_CONTROL_MODES,
            generate_output_path_func=generate_output_path,
        )
        
        assert params.encoder == expected_encoder
        assert params.is_custom is True


class TestCustomModeRateControl:
    """自定义模式 - 不同码率控制模式测试 - 完整参数验证"""
    
    def test_crf_mode(self, mock_video_file):
        """测试 CRF 模式"""
        from tests.conftest import MockArgs
        
        args = MockArgs(
            input=mock_video_file,
            preset="自定义 (Custom)",
            rate_control="CRF/CQ (恒定质量)",
            crf=20,
            video_bitrate="",
        )
        
        params = resolve_encoder_params(
            args=args,
            quality_presets=QUALITY_PRESETS,
            encoders=ENCODERS,
            audio_encoders=AUDIO_ENCODERS,
            rate_control_modes=RATE_CONTROL_MODES,
            generate_output_path_func=generate_output_path,
        )
        
        assert params.rc_mode == "crf"
        assert params.crf == 20
        assert params.bitrate is None
        assert params.get_encode_mode() == EncodeMode.NORMAL
    
    def test_vbr_mode(self, mock_video_file):
        """测试 VBR 模式"""
        from tests.conftest import MockArgs
        
        args = MockArgs(
            input=mock_video_file,
            preset="自定义 (Custom)",
            rate_control="VBR (可变码率)",
            video_bitrate="10M",
        )
        
        params = resolve_encoder_params(
            args=args,
            quality_presets=QUALITY_PRESETS,
            encoders=ENCODERS,
            audio_encoders=AUDIO_ENCODERS,
            rate_control_modes=RATE_CONTROL_MODES,
            generate_output_path_func=generate_output_path,
        )
        
        assert params.rc_mode == "vbr"
        assert params.bitrate == "10M"
        assert params.get_encode_mode() == EncodeMode.NORMAL
    
    def test_cbr_mode(self, mock_video_file):
        """测试 CBR 模式"""
        from tests.conftest import MockArgs
        
        args = MockArgs(
            input=mock_video_file,
            preset="自定义 (Custom)",
            rate_control="CBR (恒定码率)",
            video_bitrate="8M",
        )
        
        params = resolve_encoder_params(
            args=args,
            quality_presets=QUALITY_PRESETS,
            encoders=ENCODERS,
            audio_encoders=AUDIO_ENCODERS,
            rate_control_modes=RATE_CONTROL_MODES,
            generate_output_path_func=generate_output_path,
        )
        
        assert params.rc_mode == "cbr"
        assert params.bitrate == "8M"
        assert params.get_encode_mode() == EncodeMode.NORMAL
    
    def test_2pass_mode(self, mock_video_file):
        """测试 2-Pass 模式"""
        from tests.conftest import MockArgs
        
        args = MockArgs(
            input=mock_video_file,
            preset="自定义 (Custom)",
            rate_control="2-Pass VBR (两遍编码)",
            video_bitrate="10M",
        )
        
        params = resolve_encoder_params(
            args=args,
            quality_presets=QUALITY_PRESETS,
            encoders=ENCODERS,
            audio_encoders=AUDIO_ENCODERS,
            rate_control_modes=RATE_CONTROL_MODES,
            generate_output_path_func=generate_output_path,
        )
        
        assert params.rc_mode == "2pass"
        assert params.bitrate == "10M"
        assert params.is_custom is True
        assert params.get_encode_mode() == EncodeMode.TWO_PASS
    
    def test_2pass_mode_no_bitrate(self, mock_video_file):
        """测试 2-Pass 模式无码率时回退到普通模式"""
        from tests.conftest import MockArgs
        
        args = MockArgs(
            input=mock_video_file,
            preset="自定义 (Custom)",
            rate_control="2-Pass VBR (两遍编码)",
            video_bitrate="",
        )
        
        params = resolve_encoder_params(
            args=args,
            quality_presets=QUALITY_PRESETS,
            encoders=ENCODERS,
            audio_encoders=AUDIO_ENCODERS,
            rate_control_modes=RATE_CONTROL_MODES,
            generate_output_path_func=generate_output_path,
        )
        
        assert params.rc_mode == "2pass"
        assert params.bitrate is None
        assert params.get_encode_mode() == EncodeMode.NORMAL


class TestCompatMode:
    """兼容模式测试 - 完整参数验证"""
    
    def test_compat_mode_with_subtitle(self, mock_video_file, mock_subtitle_file):
        """测试兼容模式 + 字幕 - 完整验证"""
        from tests.conftest import MockArgs
        
        args = MockArgs(
            input=mock_video_file,
            subtitle=mock_subtitle_file,
            compat_mode=True,
        )
        
        params = resolve_encoder_params(
            args=args,
            quality_presets=QUALITY_PRESETS,
            encoders=ENCODERS,
            audio_encoders=AUDIO_ENCODERS,
            rate_control_modes=RATE_CONTROL_MODES,
            generate_output_path_func=generate_output_path,
        )
        
        # 兼容模式相关
        assert params.compat_mode is True
        assert params.subtitle_path == mock_subtitle_file
        assert params.get_encode_mode() == EncodeMode.COMPAT
        
        # 预设参数 (使用默认预设)
        assert params.is_custom is False
        assert params.encoder == "libx264"
        assert params.crf == 18
        assert params.audio_encoder == "copy"
    
    def test_compat_mode_without_subtitle(self, mock_video_file):
        """测试兼容模式无字幕时回退到普通模式"""
        from tests.conftest import MockArgs
        
        args = MockArgs(
            input=mock_video_file,
            compat_mode=True,
        )
        
        params = resolve_encoder_params(
            args=args,
            quality_presets=QUALITY_PRESETS,
            encoders=ENCODERS,
            audio_encoders=AUDIO_ENCODERS,
            rate_control_modes=RATE_CONTROL_MODES,
            generate_output_path_func=generate_output_path,
        )
        
        assert params.compat_mode is True
        assert params.subtitle_path is None
        assert params.get_encode_mode() == EncodeMode.NORMAL


class TestPresetModes:
    """预设模式测试 - 完整参数验证"""
    
    def test_preset_balanced(self, mock_video_file):
        """测试均衡画质预设"""
        from tests.conftest import MockArgs
        
        args = MockArgs(
            input=mock_video_file,
            preset="【均衡画质】x264常用导出(CRF18)",
        )
        
        params = resolve_encoder_params(
            args=args,
            quality_presets=QUALITY_PRESETS,
            encoders=ENCODERS,
            audio_encoders=AUDIO_ENCODERS,
            rate_control_modes=RATE_CONTROL_MODES,
            generate_output_path_func=generate_output_path,
        )
        
        assert params.is_custom is False
        assert params.encoder == "libx264"
        assert params.crf == 18
        assert params.speed_preset == "medium"
        assert params.audio_encoder == "copy"
        assert params.audio_bitrate == "192k"
    
    def test_preset_quality(self, mock_video_file):
        """测试极致画质预设"""
        from tests.conftest import MockArgs
        
        args = MockArgs(
            input=mock_video_file,
            preset="【极致画质】4K/高动态/AMV",
        )
        
        params = resolve_encoder_params(
            args=args,
            quality_presets=QUALITY_PRESETS,
            encoders=ENCODERS,
            audio_encoders=AUDIO_ENCODERS,
            rate_control_modes=RATE_CONTROL_MODES,
            generate_output_path_func=generate_output_path,
        )
        
        assert params.is_custom is False
        assert params.encoder == "libx264"
        assert params.crf == 16
        assert params.speed_preset == "slow"
        assert params.audio_encoder == "copy"
        assert params.audio_bitrate == "320k"
    
    def test_preset_nvenc_speed(self, mock_video_file):
        """测试 NVENC 速度优先预设"""
        from tests.conftest import MockArgs
        
        args = MockArgs(
            input=mock_video_file,
            preset="【速度优先】NVIDIA 显卡加速",
        )
        
        params = resolve_encoder_params(
            args=args,
            quality_presets=QUALITY_PRESETS,
            encoders=ENCODERS,
            audio_encoders=AUDIO_ENCODERS,
            rate_control_modes=RATE_CONTROL_MODES,
            generate_output_path_func=generate_output_path,
        )
        
        assert params.is_custom is False
        assert params.encoder == "h264_nvenc"
        assert params.crf == 23  # cq 值
        assert params.speed_preset == "p4"
        assert params.audio_encoder == "copy"
        assert params.audio_bitrate == "192k"
    
    def test_preset_nvenc_hq(self, mock_video_file):
        """测试 NVENC 画质优先预设"""
        from tests.conftest import MockArgs
        
        args = MockArgs(
            input=mock_video_file,
            preset="【画质优先】NVIDIA 显卡加速 (HQ)",
        )
        
        params = resolve_encoder_params(
            args=args,
            quality_presets=QUALITY_PRESETS,
            encoders=ENCODERS,
            audio_encoders=AUDIO_ENCODERS,
            rate_control_modes=RATE_CONTROL_MODES,
            generate_output_path_func=generate_output_path,
        )
        
        assert params.is_custom is False
        assert params.encoder == "h264_nvenc"
        assert params.crf == 19  # cq 值
        assert params.speed_preset == "p7"
        assert params.audio_encoder == "copy"
        assert params.audio_bitrate == "320k"
    
    def test_preset_audio_encoder(self, mock_video_file):
        """测试预设模式音频编码器"""
        from tests.conftest import MockArgs
        
        for preset_name in ["【均衡画质】x264常用导出(CRF18)", "【极致画质】4K/高动态/AMV",
                           "【速度优先】NVIDIA 显卡加速", "【画质优先】NVIDIA 显卡加速 (HQ)"]:
            args = MockArgs(
                input=mock_video_file,
                preset=preset_name,
            )
            
            params = resolve_encoder_params(
                args=args,
                quality_presets=QUALITY_PRESETS,
                encoders=ENCODERS,
                audio_encoders=AUDIO_ENCODERS,
                rate_control_modes=RATE_CONTROL_MODES,
                generate_output_path_func=generate_output_path,
            )
            
            # 所有预设默认复制音频
            assert params.audio_encoder == "copy"


class TestNvencPresetOverride:
    """NVENC 预设档位覆盖测试 - 完整参数验证"""
    
    def test_nvenc_preset_override(self, mock_video_file):
        """测试 NVENC 档位覆盖预设默认值"""
        from tests.conftest import MockArgs
        
        args = MockArgs(
            input=mock_video_file,
            preset="【速度优先】NVIDIA 显卡加速",
            nvenc_preset="p7",
        )
        
        params = resolve_encoder_params(
            args=args,
            quality_presets=QUALITY_PRESETS,
            encoders=ENCODERS,
            audio_encoders=AUDIO_ENCODERS,
            rate_control_modes=RATE_CONTROL_MODES,
            generate_output_path_func=generate_output_path,
        )
        
        assert params.encoder == "h264_nvenc"
        assert params.speed_preset == "p7"  # 用户覆盖
        assert params.crf == 23  # 预设 cq 不变
        assert params.is_custom is False
    
    def test_nvenc_preset_default(self, mock_video_file):
        """测试 NVENC 使用预设默认档位"""
        from tests.conftest import MockArgs
        
        args = MockArgs(
            input=mock_video_file,
            preset="【速度优先】NVIDIA 显卡加速",
            nvenc_preset="使用预设默认",
        )
        
        params = resolve_encoder_params(
            args=args,
            quality_presets=QUALITY_PRESETS,
            encoders=ENCODERS,
            audio_encoders=AUDIO_ENCODERS,
            rate_control_modes=RATE_CONTROL_MODES,
            generate_output_path_func=generate_output_path,
        )
        
        assert params.encoder == "h264_nvenc"
        assert params.speed_preset == "p4"  # 预设默认
        assert params.crf == 23
    
    def test_nvenc_preset_no_effect_on_cpu(self, mock_video_file):
        """测试 NVENC 档位对 CPU 预设无效"""
        from tests.conftest import MockArgs
        
        args = MockArgs(
            input=mock_video_file,
            preset="【均衡画质】x264常用导出(CRF18)",
            nvenc_preset="p7",
        )
        
        params = resolve_encoder_params(
            args=args,
            quality_presets=QUALITY_PRESETS,
            encoders=ENCODERS,
            audio_encoders=AUDIO_ENCODERS,
            rate_control_modes=RATE_CONTROL_MODES,
            generate_output_path_func=generate_output_path,
        )
        
        assert params.encoder == "libx264"
        assert params.speed_preset == "medium"  # CPU 预设不受影响
    
    def test_custom_mode_nvenc_preset(self, mock_video_file):
        """测试自定义模式下 NVENC 档位"""
        from tests.conftest import MockArgs
        
        args = MockArgs(
            input=mock_video_file,
            preset="自定义 (Custom)",
            encoder="H.264 (NVIDIA NVENC)",
            nvenc_preset="p5",
            crf=20,
        )
        
        params = resolve_encoder_params(
            args=args,
            quality_presets=QUALITY_PRESETS,
            encoders=ENCODERS,
            audio_encoders=AUDIO_ENCODERS,
            rate_control_modes=RATE_CONTROL_MODES,
            generate_output_path_func=generate_output_path,
        )
        
        assert params.encoder == "h264_nvenc"
        assert params.speed_preset == "p5"
        assert params.crf == 20
        assert params.is_custom is True
    
    def test_custom_mode_nvenc_default(self, mock_video_file):
        """测试自定义模式下 NVENC 默认档位"""
        from tests.conftest import MockArgs
        
        args = MockArgs(
            input=mock_video_file,
            preset="自定义 (Custom)",
            encoder="H.264 (NVIDIA NVENC)",
            nvenc_preset="使用预设默认",
        )
        
        params = resolve_encoder_params(
            args=args,
            quality_presets=QUALITY_PRESETS,
            encoders=ENCODERS,
            audio_encoders=AUDIO_ENCODERS,
            rate_control_modes=RATE_CONTROL_MODES,
            generate_output_path_func=generate_output_path,
        )
        
        assert params.encoder == "h264_nvenc"
        assert params.speed_preset == "p4"  # 默认 p4
        assert params.is_custom is True
