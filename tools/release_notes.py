"""按准确预发布版本提取更新日志，并写入双平台安装包校验和。"""
import argparse
import hashlib
from pathlib import Path
import re


def build_notes(tag: str, changelog: str, assets: Path, repository: str) -> str:
    if not re.fullmatch(r"v\d+\.\d+\.\d+-(?:alpha|beta|rc)(?:\.[0-9A-Za-z-]+)*", tag):
        raise ValueError(f"不是支持的预发布版本号：{tag}")
    version = tag[1:]
    match = re.search(r"^## \[" + re.escape(version) + r"\][^\n]*\n.*?(?=^## \[|\Z)",
                      changelog, re.MULTILINE | re.DOTALL)
    if not match:
        raise ValueError(f"CHANGELOG 缺少准确的版本条目：{version}")
    names = [f"XiaoXueToolbox_{tag}_{platform}.zip" for platform in ("Windows_x64", "macOS_arm64")]
    hashes = []
    for name in names:
        path = assets / name
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"缺少有效安装包：{name}")
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        hashes.append(f"{digest}  {name}")
    base = f"https://github.com/{repository}"
    return (f"## 小雪工具箱 {tag}（预发布）\n\n{match.group(0).strip()}\n\n"
            "### 下载与安装\n\n"
            "- Windows 10/11 x64：下载 Windows_x64.zip，解压后运行小雪工具箱.exe。\n"
            "- macOS 13+ Apple Silicon：下载 macOS_arm64.zip，解压后将小雪工具箱.app 放入应用程序。\n"
            "- 两个平台均内置 FFmpeg/ffprobe；Mac 包为 ad-hoc 签名，尚未进行 Developer ID 公证。\n\n"
            f"[片段功能说明]({base}/blob/{tag}/CLIP_EDITING.md) · "
            f"[完整更新日志]({base}/blob/{tag}/CHANGELOG.md)\n\n"
            "### SHA256 校验和\n\n```\n" + "\n".join(hashes) + "\n```\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--changelog", type=Path, default=Path("CHANGELOG.md"))
    parser.add_argument("--output", type=Path, default=Path("release-notes.md"))
    args = parser.parse_args()
    args.output.write_text(build_notes(args.tag, args.changelog.read_text(encoding="utf-8"),
                                      args.assets, args.repository), encoding="utf-8")


if __name__ == "__main__":
    main()
