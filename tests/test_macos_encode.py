"""Apple 编码器从参数解析到命令的回归。"""
import pytest
from src.core import build_encode_command
from src.encode_params import EncodeParams, resolve_encoder_params
from src.presets import QUALITY_PRESETS, ENCODERS, AUDIO_ENCODERS, RATE_CONTROL_MODES
from src.utils import generate_output_path


@pytest.mark.parametrize('encoder', ['h264_videotoolbox', 'hevc_videotoolbox'])
def test_vt_command_keeps_native_quality_and_speed_without_probe(encoder):
    cmd = build_encode_command('i.mp4', 'o.mp4', encoder=encoder,
                               rc_mode='crf', crf=65, speed_preset='auto')
    assert cmd[cmd.index('-c:v') + 1] == encoder
    assert cmd[cmd.index('-q:v') + 1] == '65'
    assert cmd[cmd.index('-prio_speed') + 1] == 'auto'
    assert '-crf' not in cmd and '-preset' not in cmd


def test_vt_display_name_resolves_to_hardware(custom_args):
    custom_args.encoder = 'H.264 (Apple VideoToolbox)'
    custom_args.crf = 65
    custom_args.speed_preset = 'auto'
    params = resolve_encoder_params(custom_args, QUALITY_PRESETS, ENCODERS,
                                    AUDIO_ENCODERS, RATE_CONTROL_MODES,
                                    generate_output_path)
    assert params.encoder == 'h264_videotoolbox'
    assert params.crf == 65 and params.speed_preset == 'auto'
    assert params.validate() == (True, '')


@pytest.mark.parametrize('quality', [0, 65, 100])
def test_vt_quality_range(mock_video_file, quality):
    params = EncodeParams(mock_video_file, 'o.mp4', encoder='hevc_videotoolbox', crf=quality)
    assert params.validate() == (True, '')


def test_unknown_encoder_is_rejected_instead_of_using_cpu(custom_args):
    custom_args.encoder = 'missing_encoder'
    params = resolve_encoder_params(custom_args, QUALITY_PRESETS, ENCODERS,
                                    AUDIO_ENCODERS, RATE_CONTROL_MODES,
                                    generate_output_path)
    assert params.validate()[0] is False
