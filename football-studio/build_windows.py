"""Build the standalone x64 EXE with Python 3.10+ and PyInstaller 6."""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    if sys.platform != "win32":
        raise SystemExit("请在 Windows 环境中运行打包脚本。")
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="构建 Touchline Lab 单文件 Windows 应用")
    parser.add_argument("--output", type=Path, default=root, help="可执行程序的输出目录")
    output = parser.parse_args().output.resolve()
    with tempfile.TemporaryDirectory(prefix="touchline-bundle-") as scratch:
        # The skill's workflow.py is independent of the identically named PyPI package.
        (Path(scratch) / "hook-workflow.py").write_text("# No third-party workflow metadata.\n", encoding="utf-8")
        flags = [
            "--onefile", "--windowed", "--name", "TouchlineLab", "--noconfirm",
            "--additional-hooks-dir", scratch,
            "--distpath", str(output), "--specpath", scratch,
            "--workpath", str(Path(scratch) / "work"),
            "--icon", str(root / "static" / "mark.ico"), "--paths", str(root / "engine"),
        ]
        for directory in ("static", "examples", "data"):
            flags.extend(["--add-data", f"{root / directory}{os.pathsep}{directory}"])
        license_file = Path(sys.base_prefix) / "LICENSE.txt"
        if license_file.is_file():
            flags.extend(["--add-data", f"{license_file}{os.pathsep}licenses"])
        subprocess.run([sys.executable, "-m", "PyInstaller", *flags, str(root / "desktop.py")],
                       cwd=root, check=True)


if __name__ == "__main__":
    main()
