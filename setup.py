import sys
import os
from cx_Freeze import setup, Executable

# 确保data目录存在
data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
if not os.path.exists(data_dir):
    os.makedirs(data_dir)
    
# 在data目录中创建一个空的占位文件，确保目录能被正确打包
placeholder_file = os.path.join(data_dir, ".placeholder")
if not os.path.exists(placeholder_file):
    with open(placeholder_file, 'w') as f:
        f.write("# 此文件用于确保data目录被包含在打包中\n")

# 依赖包
build_exe_options = {
    "packages": [
        "os", "flask", "flask_cors", "json", "threading", "webbrowser", 
        "logging", "concurrent.futures", "time", "traceback", "io", "csv",
        "atexit", "sys"
    ],
    "excludes": [],
    "include_files": [
        ("templates/", "templates/"),
        (data_dir, "data/")
    ],
    "include_msvcr": True  # 确保包含必要的Visual C++ 运行库
}

# 目标EXE
base = None
if sys.platform == "win32":
    base = "Win32GUI"  # 使用Windows GUI，不显示控制台

setup(
    name="邮箱API客户端",
    version="1.0",
    description="Outlook邮箱API客户端 - 本地版",
    options={"build_exe": build_exe_options},
    executables=[Executable(
        "main.py", 
        base=base, 
        target_name="邮箱API客户端.exe", 
        icon=None,
        shortcut_name="邮箱API客户端",
        shortcut_dir="DesktopFolder"
    )]
) 