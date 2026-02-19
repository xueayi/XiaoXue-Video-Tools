# -*- coding: utf-8 -*-
"""
压制后文件分发模块测试用例。

测试 src/post_transfer.py 中的文件复制和移动功能。
"""
import pytest
import os

from src.post_transfer import transfer_file


class TestTransferFile:
    """测试文件分发功能"""

    @pytest.fixture
    def source_file(self, tmp_path):
        """创建临时源文件"""
        f = tmp_path / "output_video.mp4"
        f.write_bytes(b"fake encoded video content")
        return str(f)

    def test_copy_mode(self, source_file, tmp_path):
        """测试复制模式：源文件应保留"""
        target_dir = str(tmp_path / "target")
        result = transfer_file(source_file, target_dir, mode="copy")

        assert os.path.isfile(result)
        assert os.path.isfile(source_file)  # 源文件仍存在
        assert os.path.basename(result) == "output_video.mp4"

    def test_move_mode(self, source_file, tmp_path):
        """测试移动模式：源文件应消失"""
        target_dir = str(tmp_path / "target")
        result = transfer_file(source_file, target_dir, mode="move")

        assert os.path.isfile(result)
        assert not os.path.isfile(source_file)  # 源文件已被移动

    def test_auto_create_target_dir(self, source_file, tmp_path):
        """测试目标目录不存在时自动创建"""
        target_dir = str(tmp_path / "deep" / "nested" / "target")
        assert not os.path.exists(target_dir)

        result = transfer_file(source_file, target_dir, mode="copy")
        assert os.path.isfile(result)

    def test_avoid_overwrite(self, source_file, tmp_path):
        """测试目标文件已存在时自动重命名"""
        target_dir = str(tmp_path / "target")
        os.makedirs(target_dir)
        # 预先放置同名文件
        existing = os.path.join(target_dir, "output_video.mp4")
        with open(existing, "wb") as f:
            f.write(b"existing file")

        result = transfer_file(source_file, target_dir, mode="copy")
        assert result != existing  # 应该生成不同的文件名
        assert os.path.isfile(existing)  # 原有文件仍存在
        assert os.path.isfile(result)

    def test_source_not_found(self, tmp_path):
        """测试源文件不存在时抛出异常"""
        with pytest.raises(FileNotFoundError):
            transfer_file(
                str(tmp_path / "nonexistent.mp4"),
                str(tmp_path / "target"),
                mode="copy",
            )

    def test_invalid_mode(self, source_file, tmp_path):
        """测试无效分发模式时抛出异常"""
        with pytest.raises(ValueError):
            transfer_file(source_file, str(tmp_path / "target"), mode="invalid")
