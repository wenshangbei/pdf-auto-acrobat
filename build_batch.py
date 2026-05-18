# -*- coding: utf-8 -*-
"""
PyInstaller 打包脚本 (Python 调用方式, 避免 bat 文件 GBK/UTF-8 编码导致的中文乱码).

用法:
    双击 build.bat  (会自动调用本脚本)
或:
    python build_batch.py
"""
import os
import sys
import shutil
import subprocess

EXE_NAME = "Acrobat批量去水印"
ENTRY_SCRIPT = "acrobat_batch.py"


def clean():
    for d in ("build", "dist"):
        if os.path.isdir(d):
            print(f"清理旧目录: {d}/")
            shutil.rmtree(d, ignore_errors=True)
    for fn in os.listdir("."):
        if fn.endswith(".spec"):
            print(f"清理旧 spec: {fn}")
            os.remove(fn)


def install_deps():
    print(">>> 安装/升级依赖 ...")
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", "-r", "requirements.txt",
    ])


def build():
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--windowed",                       # GUI 程序, 不弹黑控制台
        "--name", EXE_NAME,                 # 中文 exe 名 (Python 列表传参不会被 cmd 编码搞乱)
        "--collect-all", "pywinauto",       # 关键: pywinauto 依赖 comtypes 动态生成的包装类
        "--collect-all", "comtypes",
        "--hidden-import", "tkinter",
        "--hidden-import", "tkinter.ttk",
        "--hidden-import", "tkinter.filedialog",
        "--hidden-import", "tkinter.messagebox",
        "--hidden-import", "win32com.client",
        "--hidden-import", "win32clipboard",
        ENTRY_SCRIPT,
    ]
    print(">>> Running PyInstaller ...")
    print("    " + " ".join(cmd))
    r = subprocess.run(cmd)
    if r.returncode != 0:
        print("\n[FAILED] PyInstaller 打包出错, 请查看上方日志")
        sys.exit(r.returncode)


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    install_deps()
    clean()
    build()
    out_dir = os.path.join("dist", EXE_NAME)
    out_exe = os.path.join(out_dir, f"{EXE_NAME}.exe")
    print()
    print("=" * 60)
    print(f"打包完成 ✓")
    print(f"  产物目录: {os.path.abspath(out_dir)}")
    print(f"  双击运行: {os.path.abspath(out_exe)}")
    print()
    print("  分发说明: 把整个文件夹拷给别人即可,")
    print("           目标机器无需安装 Python (Acrobat Pro DC 必须装).")
    print("=" * 60)


if __name__ == "__main__":
    main()
