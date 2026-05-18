# Acrobat 批量去水印

基于 Python + pywinauto 自动化 Adobe Acrobat Pro DC（中文版），批量执行预设的"去水印"动作并保存。

## 功能

- 📁 文件夹扫描 + 列表勾选（默认全选，可单选/全选/全不选/反选）
- 🛡️ 单文件硬超时（默认 300s，UI 可调），超时自动跳过下一个
- 📊 每个 PDF 一份 CSV 报告（成功/失败/超时/跳过 + 耗时 + 失败原因）
- ⏯️ 暂停 / 跳过当前 / 终止 三档控制
- 🚨 连续失败自动暂停提示（3 个同阶段 OR 5 个总数）
- 🔴 顶部红色横幅"勿动鼠标键盘"提示

## 前置要求

- **Windows 10/11**
- **Python 3.8+**（开发用；普通用户下载 exe 不需要装）
- **Adobe Acrobat Pro DC 中文版**（必须装，标准版不行 —— 没有"动作向导"功能）
- 在 Acrobat 中**事先录好动作**：动作名 = 要去除的水印文字（如"示例水印"）
- Acrobat 设置：编辑 → 首选项 → 一般 → 取消勾选"打开没有文档的应用程序时显示主页屏幕"

## 安装

```cmd
git clone <repo_url>
cd Auto_PDF_Handle
pip install -r requirements.txt
```

## 运行

```cmd
python acrobat_batch.py
```

## 打包成 exe

```cmd
build.bat
```
产物在 `dist\Acrobat批量去水印\Acrobat批量去水印.exe`，整个文件夹拷给别人即可（目标机器无需 Python）。

## 文档

- [DESIGN.md](DESIGN.md) - 最小闭环设计文档
- [DESIGN_BATCH.md](DESIGN_BATCH.md) - 批量处理设计文档
- [TECH.md](TECH.md) - 技术细节 + 经典坑速查表（11 条）
- [doc/](doc/) - 用户操作手册 + 开发指南（Word 版）

## 项目结构

```
Auto_PDF_Handle/
├── acrobat_batch.py        # ★ 批量 GUI 入口
├── acrobat_gui_min.py      # 单文件 GUI + 核心 AcrobatWorker
├── build_batch.py          # PyInstaller 打包脚本
├── build.bat               # 打包入口 (调用 build_batch.py)
├── kill_acrobat.bat        # 应急清理: 杀光所有 Adobe 进程
├── requirements.txt
├── DESIGN.md / DESIGN_BATCH.md / TECH.md
└── doc/                    # Word 文档
```

## 核心技术坑（节选）

| 现象 | 真因 | 解决 |
|---|---|---|
| connect Acrobat 超时 30s | 32 位 Acrobat + UIA title_re 查询挂死 | 用 `class_name="AcrobatSDIWindow"` 而非 title_re |
| invoke 报成功但 Acrobat 没反应 | Qt 窗口 InvokePattern 是 stub | 用 SendInput 真实鼠标点击 |
| 进度面板 UIA 检测不到 | UIA Text 树里没有该控件 | 用"保存按钮 IsEnabled"代替 |
| askdirectory() 挂死 | Tk 8.6 在 Win11/中文系统偶发 | 用 win32com Shell.BrowseForFolder 替代 |

完整 11 条坑见 [TECH.md](TECH.md)。

## License

MIT
