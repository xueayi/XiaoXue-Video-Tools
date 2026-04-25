# -*- coding: utf-8 -*-
"""功能页面 Tab 模块。"""

from .help_tab import HelpTab
from .folder_creator_tab import FolderCreatorTab
from .remux_tab import RemuxTab
from .image_convert_tab import ImageConvertTab
from .batch_rename_tab import BatchRenameTab
from .extract_av_tab import ExtractAvTab
from .replace_audio_tab import ReplaceAudioTab
from .qc_tab import QcTab
from .media_probe_tab import MediaProbeTab
from .notification_tab import NotificationTab
from .encode_tab import EncodeTab
from .shield_tab import ShieldTab

__all__ = [
    "HelpTab",
    "FolderCreatorTab",
    "RemuxTab",
    "ImageConvertTab",
    "BatchRenameTab",
    "ExtractAvTab",
    "ReplaceAudioTab",
    "QcTab",
    "MediaProbeTab",
    "NotificationTab",
    "EncodeTab",
    "ShieldTab",
]
