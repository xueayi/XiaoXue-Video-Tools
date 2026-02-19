# -*- coding: utf-8 -*-
"""
批量重命名模块测试用例。

测试 src/batch_renamer.py 中的排序功能和关键词提前功能。
"""
import pytest
import os

from src.batch_renamer import (
    RenameConfig,
    get_sorted_files,
    get_files_sorted_by_size,
    batch_rename,
)


class TestGetSortedFiles:
    """测试文件排序功能"""

    @pytest.fixture
    def sample_dir(self, tmp_path):
        """创建包含不同大小和名称的测试文件"""
        files_spec = {
            "banana.png": b"x" * 300,
            "apple.png": b"x" * 100,
            "cherry.png": b"x" * 200,
            "主视觉图_001.png": b"x" * 150,
            "demo.mp4": b"x" * 500,
        }
        for name, content in files_spec.items():
            (tmp_path / name).write_bytes(content)
        return str(tmp_path)

    def test_sort_by_name_asc(self, sample_dir):
        """测试按文件名升序排序"""
        files = get_sorted_files(
            sample_dir, ["png", "mp4"],
            sort_method="name", sort_order="asc",
        )
        names = [os.path.basename(f) for f in files]
        assert names == sorted(names, key=str.lower)

    def test_sort_by_name_desc(self, sample_dir):
        """测试按文件名降序排序"""
        files = get_sorted_files(
            sample_dir, ["png", "mp4"],
            sort_method="name", sort_order="desc",
        )
        names = [os.path.basename(f) for f in files]
        assert names == sorted(names, key=str.lower, reverse=True)

    def test_sort_by_size_asc(self, sample_dir):
        """测试按文件大小升序排序"""
        files = get_sorted_files(
            sample_dir, ["png", "mp4"],
            sort_method="size", sort_order="asc",
        )
        sizes = [os.path.getsize(f) for f in files]
        assert sizes == sorted(sizes)

    def test_sort_by_size_desc(self, sample_dir):
        """测试按文件大小降序排序"""
        files = get_sorted_files(
            sample_dir, ["png", "mp4"],
            sort_method="size", sort_order="desc",
        )
        sizes = [os.path.getsize(f) for f in files]
        assert sizes == sorted(sizes, reverse=True)

    def test_priority_keyword(self, sample_dir):
        """测试关键词提前排序"""
        files = get_sorted_files(
            sample_dir, ["png"],
            sort_method="name", sort_order="asc",
            priority_keyword="主视觉图",
        )
        names = [os.path.basename(f) for f in files]
        # 包含关键词的文件应排在最前面
        assert names[0] == "主视觉图_001.png"

    def test_priority_keyword_with_size_sort(self, sample_dir):
        """测试关键词提前 + 按大小排序组合"""
        files = get_sorted_files(
            sample_dir, ["png"],
            sort_method="size", sort_order="asc",
            priority_keyword="主视觉图",
        )
        names = [os.path.basename(f) for f in files]
        assert names[0] == "主视觉图_001.png"
        # 其余文件仍按大小排序
        remaining_sizes = [os.path.getsize(f) for f in files[1:]]
        assert remaining_sizes == sorted(remaining_sizes)

    def test_empty_keyword_no_effect(self, sample_dir):
        """测试空关键词不影响排序"""
        files_no_kw = get_sorted_files(
            sample_dir, ["png"],
            sort_method="name", sort_order="asc",
            priority_keyword="",
        )
        files_default = get_sorted_files(
            sample_dir, ["png"],
            sort_method="name", sort_order="asc",
        )
        assert files_no_kw == files_default

    def test_compat_alias(self, sample_dir):
        """测试兼容性别名 get_files_sorted_by_size"""
        files = get_files_sorted_by_size(sample_dir, ["png", "mp4"])
        sizes = [os.path.getsize(f) for f in files]
        assert sizes == sorted(sizes)


class TestBatchRenameWithSort:
    """测试批量重命名结合排序功能"""

    @pytest.fixture
    def rename_dir(self, tmp_path):
        """创建用于重命名测试的文件"""
        (tmp_path / "c_image.png").write_bytes(b"x" * 300)
        (tmp_path / "a_image.png").write_bytes(b"x" * 100)
        (tmp_path / "b_image.png").write_bytes(b"x" * 200)
        return str(tmp_path)

    def test_rename_with_name_sort(self, rename_dir, tmp_path):
        """测试按文件名排序后的重命名结果"""
        output_dir = str(tmp_path / "output")
        config = RenameConfig(
            mode="copy_rename",
            output_dir=output_dir,
            target_type="images",
            recursive=False,
            sort_method="name",
            sort_order="asc",
        )
        success, fail, errors = batch_rename(rename_dir, config)
        assert success == 3
        assert fail == 0
        # 按文件名排序: a -> b -> c
        assert os.path.exists(os.path.join(output_dir, "图片_1.png"))
        assert os.path.exists(os.path.join(output_dir, "图片_2.png"))
        assert os.path.exists(os.path.join(output_dir, "图片_3.png"))

    def test_rename_with_priority_keyword(self, tmp_path):
        """测试关键词提前排序后的重命名结果"""
        input_dir = str(tmp_path / "input")
        os.makedirs(input_dir)
        (tmp_path / "input" / "photo_b.png").write_bytes(b"x" * 200)
        (tmp_path / "input" / "主视觉图.png").write_bytes(b"x" * 100)
        (tmp_path / "input" / "photo_a.png").write_bytes(b"x" * 300)

        output_dir = str(tmp_path / "output")
        config = RenameConfig(
            mode="copy_rename",
            output_dir=output_dir,
            target_type="images",
            recursive=False,
            sort_method="name",
            sort_order="asc",
            priority_keyword="主视觉图",
        )
        success, _, _ = batch_rename(input_dir, config)
        assert success == 3
        # 主视觉图应该获得编号 1
        assert os.path.exists(os.path.join(output_dir, "图片_1.png"))
