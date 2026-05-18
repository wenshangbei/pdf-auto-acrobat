# -*- coding: utf-8 -*-
"""生成《开发指南.docx》"""
from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


CN_FONT = "微软雅黑"
CODE_FONT = "Consolas"


def set_cn_font(run, font_name=CN_FONT):
    run.font.name = font_name
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    rFonts.set(qn("w:eastAsia"), font_name)
    rFonts.set(qn("w:ascii"), font_name)
    rFonts.set(qn("w:hAnsi"), font_name)


def set_code_font(run):
    set_cn_font(run, CODE_FONT)


def set_cell_bg(cell, color_hex):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color_hex)
    tcPr.append(shd)


def add_para(doc, text, bold=False, size=11, color=None):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = bold
    run.font.size = Pt(size)
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    set_cn_font(run)
    return p


def add_heading(doc, text, level=1):
    h = doc.add_heading(level=level)
    run = h.add_run(text)
    set_cn_font(run)
    return h


def add_bullet(doc, text):
    p = doc.add_paragraph(style="List Bullet")
    run = p.add_run(text)
    set_cn_font(run)
    return p


def add_number(doc, text):
    p = doc.add_paragraph(style="List Number")
    run = p.add_run(text)
    set_cn_font(run)
    return p


def add_code_block(doc, code):
    """代码块: 单 cell 表格 + 浅灰背景 + 等宽字体."""
    t = doc.add_table(rows=1, cols=1)
    cell = t.rows[0].cells[0]
    set_cell_bg(cell, "F4F4F4")
    cell.paragraphs[0].text = ""
    for i, line in enumerate(code.splitlines()):
        if i == 0:
            p = cell.paragraphs[0]
        else:
            p = cell.add_paragraph()
        run = p.add_run(line if line else " ")
        run.font.size = Pt(10)
        set_code_font(run)
    doc.add_paragraph()


def add_note_box(doc, title, body, color="0066CC", bg="E8F4FF", icon="💡"):
    t = doc.add_table(rows=1, cols=1)
    cell = t.rows[0].cells[0]
    set_cell_bg(cell, bg)
    cell.paragraphs[0].text = ""
    p1 = cell.paragraphs[0]
    r1 = p1.add_run(f"{icon} {title}")
    r1.bold = True
    r1.font.size = Pt(11)
    r1.font.color.rgb = RGBColor.from_string(color)
    set_cn_font(r1)
    p2 = cell.add_paragraph()
    r2 = p2.add_run(body)
    r2.font.size = Pt(11)
    set_cn_font(r2)
    doc.add_paragraph()


def add_warning_box(doc, title, body):
    add_note_box(doc, title, body, color="CC0000", bg="FFE5E5", icon="⚠")


def add_table(doc, header, rows, col_widths_cm=None, code_cols=()):
    """code_cols: 哪些列用代码字体."""
    t = doc.add_table(rows=1 + len(rows), cols=len(header))
    t.style = "Light Grid Accent 1"
    if col_widths_cm:
        for i, w in enumerate(col_widths_cm):
            for cell in t.columns[i].cells:
                cell.width = Cm(w)
    for i, h in enumerate(header):
        cell = t.rows[0].cells[i]
        cell.text = ""
        run = cell.paragraphs[0].add_run(h)
        run.bold = True
        run.font.size = Pt(11)
        set_cn_font(run)
        set_cell_bg(cell, "D5E8F0")
    for ri, row in enumerate(rows, start=1):
        for ci, val in enumerate(row):
            cell = t.rows[ri].cells[ci]
            cell.text = ""
            run = cell.paragraphs[0].add_run(str(val))
            run.font.size = Pt(10)
            if ci in code_cols:
                set_code_font(run)
            else:
                set_cn_font(run)
    doc.add_paragraph()
    return t


# ===============================================================
doc = Document()

style = doc.styles["Normal"]
style.font.name = CN_FONT
style.font.size = Pt(11)
style._element.rPr.rFonts.set(qn("w:eastAsia"), CN_FONT)

# 封面
title = doc.add_heading(level=0)
title_run = title.add_run("Acrobat 批量去水印 - 开发指南")
set_cn_font(title_run)
title.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER

subtitle = doc.add_paragraph()
subtitle.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
sub_run = subtitle.add_run("面向接手开发者 / 后期维护工程师 | 版本 1.0")
sub_run.font.size = Pt(11)
sub_run.font.color.rgb = RGBColor.from_string("666666")
set_cn_font(sub_run)

doc.add_paragraph()

# 1. 项目概览
add_heading(doc, "1. 项目概览", level=1)
add_para(doc,
    "本项目是基于 Python + pywinauto 的 Windows 桌面 RPA 工具，"
    "通过 UI 自动化操控 Adobe Acrobat Pro DC，对 PDF 文件执行预设的「去水印」动作。"
    "采用「单文件 Worker + 批量调度器 + tkinter GUI」三层架构。"
)

add_heading(doc, "1.1 技术栈", level=2)
add_table(doc,
    ["层级", "技术", "用途"],
    [
        ["GUI", "tkinter + ttk", "界面"],
        ["RPA 核心", "pywinauto (UIA backend)", "UI 自动化"],
        ["底层鼠标", "pywinauto.mouse (SendInput)", "Qt 窗口必须用真实鼠标"],
        ["进程管理", "subprocess + taskkill", "Acrobat 清理"],
        ["剪贴板", "win32clipboard", "中文路径粘贴"],
        ["文件夹选择", "win32com Shell.BrowseForFolder", "替代不稳定的 askdirectory"],
        ["报告", "csv 模块", "实时追加报告"],
        ["打包", "PyInstaller (onedir)", "无 Python 环境分发"],
    ],
    col_widths_cm=[3, 6, 8],
    code_cols=[1],
)

add_heading(doc, "1.2 整体流程", level=2)
add_code_block(doc, """┌─────────────────────────────────────────────────┐
│  BatchApp (tkinter GUI)                         │
│  - 文件夹扫描/列表勾选/水印输入/超时配置        │
│  - 子线程跑 BatchRunner, queue 跨线程传日志     │
└────────────────────┬────────────────────────────┘
                     │ runner.run(pdf_list, ...)
                     ▼
┌─────────────────────────────────────────────────┐
│  BatchRunner                                    │
│  - for 循环串行处理 PDF                          │
│  - 子线程跑 worker.run, 主线程 join(timeout)    │
│  - 超时/失败 → kill_acrobat, 写 CSV, 继续       │
└────────────────────┬────────────────────────────┘
                     │ worker.run(pdf, watermark)
                     ▼
┌─────────────────────────────────────────────────┐
│  AcrobatWorker (单文件 10 步)                    │
│  launch → open_pdf → click_remove_watermark     │
│  → click_action_list → select_action_item       │
│  → click_start_button → wait_for_action_done    │
│  → save_and_close → (finally) kill_acrobat      │
└────────────────────┬────────────────────────────┘
                     │ pywinauto + win32 + ctypes
                     ▼
              Adobe Acrobat Pro DC""")

# 2. 代码结构
add_heading(doc, "2. 代码结构", level=1)
add_table(doc,
    ["文件", "用途"],
    [
        ["acrobat_gui_min.py",
         "单文件 GUI + AcrobatWorker 核心类 (最初的 MVP, 现在 import 给批量版用)"],
        ["acrobat_batch.py",
         "批量 GUI (BatchApp) + 调度器 (BatchRunner) + PdfResult 数据类"],
        ["acrobat_remove_watermark.py",
         "早期 CLI 版本 (含 scan_pdf_files, 历史遗留, 未在使用)"],
        ["build.bat",
         "打包入口, 调用 build_batch.py"],
        ["build_batch.py",
         "PyInstaller 打包脚本 (用 Python 调用避免中文 exe 名的 cmd 编码问题)"],
        ["kill_acrobat.bat",
         "应急清理脚本, taskkill 所有 Adobe 系列进程"],
        ["diag.py",
         "诊断脚本, 测试 pywinauto 能否 connect Acrobat"],
        ["requirements.txt", "依赖清单"],
        ["DESIGN.md / DESIGN_BATCH.md / TECH.md", "Markdown 文档 (开发者视角)"],
        ["TROUBLESHOOTING.md", "踩坑记录 (UIA 惰性暴露等), 必读"],
        ["doc/", "本目录, Word 文档 (用户/开发者视角)"],
        ["<输入文件夹>/reports/", "运行时生成的 CSV 报告 (跟输入 PDF 同目录, 不在程序目录)"],
    ],
    col_widths_cm=[5, 11],
    code_cols=[0],
)

# 3. 核心类说明
add_heading(doc, "3. 核心类说明", level=1)

add_heading(doc, "3.1 AcrobatWorker (acrobat_gui_min.py)", level=2)
add_para(doc, "单文件去水印的完整状态机。每个方法对应一个原子步骤。")
add_table(doc,
    ["方法", "职责", "技术要点"],
    [
        ["launch()", "启动/连接 Acrobat",
         "EnumWindows 找 HWND → connect(handle), 避免 launcher 秒退问题"],
        ["open_pdf(path)", "Ctrl+O 打开 PDF",
         "os.path.normpath 修路径分隔符, set_edit_text 写中文路径"],
        ["click_remove_watermark()", "点右侧工具栏「去水印」",
         "_click_visible_button (descendants + visible 过滤)"],
        ["click_action_list()", "点「动作列表」按钮",
         "正则匹配 ^动作列表 兼容 [Alt+Ctrl+A] 后缀"],
        ["select_action_item(text)", "在动作列表窗口里选水印对应的 TreeItem",
         "Qt 窗口必须用 _raw_mouse_click 真实鼠标"],
        ["click_start_button()", "点「开始」按钮 (无名图标)",
         "trial-and-verify 4 种点击方式, 验证保存按钮变灰"],
        ["wait_for_action_done()", "等动作执行完",
         "轮询保存按钮 is_enabled, 等它恢复"],
        ["save_and_close()", "点保存 + Ctrl+W 关闭",
         "main_win.set_focus 全部 silent try (大 PDF 可能失效)"],
        ["kill_acrobat()", "(finally) 杀光所有 Adobe 进程",
         "subprocess + taskkill, 双保险清理"],
    ],
    col_widths_cm=[5, 5, 6],
    code_cols=[0],
)

add_heading(doc, "3.2 BatchRunner (acrobat_batch.py)", level=2)
add_para(doc, "批量调度器。线程安全，自身跑在子线程，对外暴露 pause/resume/skip_current/stop 控制接口。")
add_para(doc, "关键方法：")
add_bullet(doc, "run(pdf_list, watermark, input_folder=None) → 主循环，返回报告路径。"
                "input_folder 决定 reports/ 输出位置（不传则用 pdf_list[0] 的父目录）")
add_bullet(doc, "_run_one_with_timeout(pdf, watermark) → 单文件子线程 + 主线程 join 超时")
add_bullet(doc, "_guess_stage(tb) → 从 traceback 反推失败发生在哪一步")
add_bullet(doc, "_append_csv_row(...) → CSV 实时追加（崩溃也不丢数据）")
add_note_box(doc, "Python 不能从外部 kill 线程",
    "BatchRunner 实现超时的方式是: 在子线程里跑 worker.run, 主线程 t.join(timeout) 等待. "
    "超时后调 worker.kill_acrobat() 让 Acrobat 进程死, 子线程里的 pywinauto 调用就会自然抛错退出. "
    "约 1-3 秒后子线程结束."
)

add_heading(doc, "3.3 BatchApp (acrobat_batch.py)", level=2)
add_para(doc, "tkinter GUI。所有耗时操作都在子线程，主线程通过两个 queue 接收子线程的消息：")
add_table(doc,
    ["Queue", "传递内容", "处理方式"],
    [
        ["log_queue", "字符串日志", "追加到 Text 控件"],
        ["ui_queue", "(progress, i, total, pdf) 或 (result, PdfResult) 或 (done, path)",
         "更新进度条 / 列表行 / 完成弹窗"],
    ],
    col_widths_cm=[3, 8, 5],
    code_cols=[0],
)
add_para(doc, "self.after(150, self._poll_queues) 每 150ms 在主线程检查两个 queue。")

# 4. 关键设计决策
add_heading(doc, "4. 关键设计决策（为什么这么做）", level=1)

add_heading(doc, "4.1 为什么用 pywinauto UIA backend 而不是 win32", level=2)
add_para(doc, "Acrobat 使用 Adobe 自有 UI 框架（包括 Qt5QWindowToolSaveBits），win32 backend 找不到大部分自定义子控件。UIA 能下钻到 UIA 树的所有元素。")

add_heading(doc, "4.2 为什么 Qt 窗口必须用 SendInput 真实鼠标", level=2)
add_para(doc, "Acrobat 的「动作列表」弹窗是 Qt 实现（class=Qt5QWindowToolSaveBits）。Qt 控件虽然在 UIA 中声明 IsInvokePatternAvailable=true, 但 invoke 实现往往是 stub —— UIA 调用返回成功，Qt 端却没真正触发 UI 状态变化。")
add_para(doc, "对策：用 pywinauto.mouse.click(coords=...) 发 SendInput 真实鼠标事件。SendInput 是新 API (Win2K+)，会触发完整的 hover/down/up 事件序列，Qt 能正确响应。")
add_warning_box(doc, "不要用 user32.mouse_event",
    "mouse_event 是 Win9x 时代老 API, 对 Qt 等现代 UI 框架的事件路由不可靠. "
    "实测中 mouse_event 点击 Qt TreeItem 经常不生效, 改 SendInput 后稳定."
)

add_heading(doc, "4.3 为什么用「保存按钮 IsEnabled」作为动作完成信号", level=2)
add_para(doc, "我们尝试过多种判定方式：")
add_table(doc,
    ["方式", "为什么不行"],
    [
        ["主窗口标题包含文件名",
         "Acrobat 是 MDI, 文档名只在标签页, 主窗口标题一直为空"],
        ["UIA Text 控件 Name='运行动作列表'",
         "UIA 树时有时无, 跨进程 (AcroCEF) 不可靠"],
        ["AVL_AVWindow class + size 形状",
         "勉强可用, 但其他面板形状相近, 偶尔误判"],
        ["保存按钮 IsEnabled ✓",
         "100% 可靠: 动作中按钮 disable, 完成后 enable"],
    ],
    col_widths_cm=[6, 10],
    code_cols=[0],
)

add_heading(doc, "4.4 为什么 finally 里 kill_acrobat", level=2)
add_para(doc, "Acrobat DC 是单实例机制，残留进程会让下次 launch() 卡死或行为异常。emergency_recover 的 ESC+Ctrl+W 不能保证清干净。直接 taskkill 7 个 Adobe 系列进程是最稳的「重置环境」。")

add_heading(doc, "4.5 为什么 connect 用 class_name 而不是 title_re", level=2)
add_para(doc, "64 位 Python 控制 32 位 Acrobat 时，Application(uia).connect(title_re=...) 会 TimeoutError，但 class_name='AcrobatSDIWindow' 能正常工作（跨架构稳定）。pywinauto 自己也警告了这个问题。")

add_heading(doc, "4.6 为什么找按钮失败时要主动 Ctrl+K / Esc 开关首选项", level=2)
add_para(doc, "Acrobat 右侧工具栏（AVL_AVView 容器）的子按钮 UIA 节点是「惰性注入」的——"
              "descendants(Button, title='去水印') 在 Acrobat 内部「未触发重画」时返回 0，"
              "看起来像按钮不存在，但屏幕上肉眼是看得见的。同一个 PDF 多次跑，时成时败。")
add_para(doc, "实测的触发器强度阶梯（弱→强）：")
add_bullet(doc, "鼠标 hover + 滚轮 ❌ —— Acrobat 不响应 WM_MOUSEMOVE/WHEEL")
add_bullet(doc, "set_focus 切别的窗口再切回 ❌ —— 已经是前台时 set_focus 是 no-op，不触发 WM_ACTIVATE")
add_bullet(doc, "最小化 + 还原 ✓ —— 触发 WM_ACTIVATE，但窗口会闪")
add_bullet(doc, "Ctrl+K 开首选项 → Esc 关 ✓ —— 真实模态对话框开关，100% 触发 Acrobat 重画 + 重新枚举控件")
add_para(doc, "实现：AcrobatWorker._toggle_preferences_dialog()，在 _click_visible_button() 失败循环里"
              "每 4 轮（POLL_INTERVAL=0.5s × 4 ≈ 2s）调用一次，超时上限 90s。")
add_note_box(doc, "完整诊断过程参见根目录 TROUBLESHOOTING.md",
    "包括 5 个误判方向、4 种修复方案的实测对照表。未来再遇到 "
    "'UI 上看得见但 UIA 查不到' 类问题，直接复用那份文档的诊断路径。"
)

# 5. 经典坑速查表
add_heading(doc, "5. 经典坑速查表", level=1)
add_para(doc, "12 条实战中遇到并解决的坑，按时间倒序：")
add_table(doc,
    ["现象", "真因", "解决"],
    [
        ["找右侧按钮返回 0 候选, 但屏幕能看见",
         "AVL_AVView 容器的子按钮 UIA 注入是惰性的",
         "失败循环里 Ctrl+K + Esc 开关首选项触发 Acrobat 重画 (4.6 节)"],
        ["connect Acrobat 超时 30s",
         "32 位 Acrobat + UIA title_re 查询挂死",
         "用 class_name='AcrobatSDIWindow' 而非 title_re"],
        ["Acrobat 启动后立刻卡死",
         "launcher 进程秒退, 原 app 对象 PID 失效",
         "start() 之后用 EnumWindows 找 HWND 再 connect(handle=...)"],
        ["打开 PDF 报「文件名无效」",
         "tkinter 路径用 /, Acrobat 对话框只认 \\",
         "os.path.normpath(pdf_path)"],
        ["找按钮报 There are N elements match",
         "Acrobat UI 同名按钮多个",
         "用 descendants 拿全部, 按 visible + offscreen + size 过滤"],
        ["进度面板检测失败",
         "UIA Text 树里没有该控件",
         "用「保存按钮 IsEnabled」代替"],
        ["invoke 报成功但 Acrobat 没反应",
         "Qt 窗口 InvokePattern 是 stub",
         "改用 ctypes / pywinauto.mouse 真实鼠标"],
        ["点击坐标点不中按钮",
         "旧 mouse_event API 对 Qt 失效",
         "用 SendInput (pywinauto.mouse.click)"],
        ["中文输入框输不进文字",
         "send_keys 走虚拟键码, 发不出中文",
         "win32clipboard 剪贴板 + Ctrl+V"],
        ["下一轮运行 Acrobat 状态异常",
         "上一轮残留进程",
         "finally 里 kill_acrobat()"],
        ["askdirectory() 挂死无报错",
         "Tk 8.6 在 Win11 / 中文系统偶发卡 modal",
         "用 win32com Shell.BrowseForFolder; Entry 绑 <Return> 作兜底"],
        ["大 PDF 保存阶段抛 ElementNotFoundError",
         "Acrobat 内部 reload 后原 main_win 失效",
         "所有 main_win.set_focus() 包 silent try"],
    ],
    col_widths_cm=[5, 5, 6],
)

# 6. 扩展指南
add_heading(doc, "6. 扩展指南", level=1)

add_heading(doc, "6.1 增加新的动作类型（不仅是去水印）", level=2)
add_para(doc, "如果想支持其他 Acrobat 预设动作（如「OCR」「拆分页面」），只需：")
add_number(doc, "在 Acrobat 中录制对应动作并命名")
add_number(doc, "在 GUI 上让用户选择动作类型 (下拉框)")
add_number(doc, "把 select_action_item 改为参数化, 接收任意动作名")
add_para(doc, "当前 AcrobatWorker 已经把动作名作为 watermark_text 参数传递，技术上无需改动核心流程，只需 UI 加选项。")

add_heading(doc, "6.2 增加新的 UI 元素查找", level=2)
add_para(doc, "调试新元素的标准流程：")
add_number(doc, "用 inspect.exe (Windows SDK 自带) 鼠标悬停目标元素, 看 Name / ControlType / ClassName / BoundingRectangle")
add_number(doc, "判断元素所属窗口: 主窗口 (AcrobatSDIWindow) 还是独立窗口 (如动作列表 Qt)")
add_number(doc, "主窗口元素: 用 _click_visible_button 或 _safe_click")
add_number(doc, "独立 Qt 窗口元素: 必须用 _raw_mouse_click (真实鼠标)")
add_number(doc, "把按钮 Name 提取为顶部配置常量, 方便切换语言/版本")

add_heading(doc, "6.3 适配新版本 Acrobat", level=2)
add_para(doc, "Acrobat 大版本升级（如 DC → 2024）后可能需要调整：")
add_table(doc,
    ["配置项 (acrobat_gui_min.py)", "可能需要改的场景"],
    [
        ["ACROBAT_EXE", "Acrobat 安装路径变化"],
        ["ACROBAT_WINDOW_CLASS", "主窗口类名变化 (查 inspect)"],
        ["BTN_REMOVE_WATERMARK", "中文按钮名变化"],
        ["BTN_ACTION_LIST_RE", "动作列表按钮名变化"],
        ["DLG_ACTION_LIST_TITLE", "弹出窗口标题变化"],
    ],
    col_widths_cm=[7, 9],
    code_cols=[0],
)

add_heading(doc, "6.4 适配英文版 Acrobat", level=2)
add_para(doc, "把以上中文按钮名改成英文对应即可，例如:")
add_table(doc,
    ["中文配置", "英文对应"],
    [
        ["BTN_REMOVE_WATERMARK = \"去水印\"", "= \"Remove Watermark\""],
        ["BTN_ACTION_LIST_RE = r\"^动作列表\"", "= r\"^Action List\""],
        ["DLG_ACTION_LIST_TITLE = \"动作列表\"", "= \"Action List\""],
        ["「保存」按钮名 (代码中硬编码)", "改 _find_save_button 的 title=\"Save\""],
    ],
    col_widths_cm=[8, 8],
    code_cols=[0, 1],
)

# 7. 调试工具
add_heading(doc, "7. 调试工具", level=1)

add_heading(doc, "7.1 diag.py", level=2)
add_para(doc, "诊断 pywinauto 能否正确 connect 当前运行的 Acrobat。当出现「connect 超时」等问题时用它。")
add_code_block(doc, """cd <项目目录>
# 先手动启动 Acrobat 并打开任意 PDF
python diag.py
type diag_out.txt
# 输出会显示 4 种 connect 方式的结果""")

add_heading(doc, "7.2 kill_acrobat.bat", level=2)
add_para(doc, "应急清理所有 Adobe 进程。当 Acrobat 卡死、自动化失控时双击执行。")
add_code_block(doc, """REM 杀以下 7 个进程:
REM Acrobat.exe / AcroCEF.exe / acrotray.exe /
REM AdobeIPCBroker.exe / AdobeARM.exe / acrord32.exe / AcroBroker.exe""")

add_heading(doc, "7.3 inspect.exe (Windows SDK)", level=2)
add_para(doc, "微软官方的 UIA 元素查看工具，可以鼠标悬停看任意控件的属性。下载：")
add_bullet(doc, "搜索「Windows SDK」官方下载, 安装时选「Windows Software Development Kit」")
add_bullet(doc, "安装后 inspect.exe 通常在 C:\\Program Files (x86)\\Windows Kits\\10\\bin\\10.x.x.x\\x64\\")
add_bullet(doc, "运行后用「Watch Focus」模式跟踪键盘焦点, 或者鼠标悬停元素读取 Name/ControlType")

add_heading(doc, "7.4 日志解读", level=2)
add_para(doc, "GUI 日志区里每行都有时间戳和阶段标签：")
add_table(doc,
    ["日志前缀", "含义"],
    [
        ["[click]", "点击操作的执行过程"],
        ["[debug]", "诊断输出, 仅前几次轮询时显示"],
        ["[warning]", "警告但不致命"],
        ["[error]", "捕获的异常"],
        ["[硬超时]", "单文件超时触发"],
        ["[控制]", "用户暂停/继续/跳过操作"],
        ["[终止]", "用户停止整批"],
        ["[等待中]", "正在等某个 UI 状态"],
        ["[执行中]", "动作向导正在运行 (等保存按钮恢复)"],
    ],
    col_widths_cm=[3, 13],
    code_cols=[0],
)

# 8. 打包发布
add_heading(doc, "8. 打包发布流程", level=1)
add_heading(doc, "8.1 打包步骤", level=2)
add_code_block(doc, """cd <项目目录>
# 方式 1: 双击 build.bat
# 方式 2: 命令行
python build_batch.py""")
add_para(doc, "build_batch.py 内部步骤：")
add_number(doc, "pip install -r requirements.txt (确保 PyInstaller 等装好)")
add_number(doc, "清理旧的 build/ 和 dist/ 目录")
add_number(doc, "调 PyInstaller, 产物在 dist\\Acrobat批量去水印\\")

add_heading(doc, "8.2 关键 PyInstaller 参数", level=2)
add_table(doc,
    ["参数", "作用"],
    [
        ["--windowed", "GUI 程序, 不弹黑控制台"],
        ["--name Acrobat批量去水印", "中文 exe 名 (Python 列表传参不会被 cmd 编码乱码)"],
        ["--collect-all pywinauto", "关键: 抓 UIA 动态生成的包装类"],
        ["--collect-all comtypes", "同上"],
        ["--hidden-import tkinter.*", "显式声明 tkinter 子模块"],
        ["--hidden-import win32com.client", "BrowseForFolder 用"],
        ["--hidden-import win32clipboard", "中文路径粘贴用"],
    ],
    col_widths_cm=[8, 8],
    code_cols=[0],
)

add_heading(doc, "8.3 分发说明", level=2)
add_warning_box(doc, "必须拷整个文件夹",
    "dist\\Acrobat批量去水印\\ 里 .exe 旁边的 _internal 文件夹是依赖,不能只拷 .exe. "
    "建议先把整个文件夹打包成 zip 再分发."
)
add_para(doc, "目标机器要求：")
add_bullet(doc, "Windows 10 或 11")
add_bullet(doc, "已安装 Adobe Acrobat Pro DC 中文版（核心依赖）")
add_bullet(doc, "不需要安装 Python (exe 已内嵌)")

# 9. 配置项说明
add_heading(doc, "9. 配置项参考", level=1)

add_heading(doc, "9.1 acrobat_gui_min.py 顶部常量", level=2)
add_table(doc,
    ["常量", "默认值", "调整时机"],
    [
        ["ACROBAT_EXE", "C:\\Program Files (x86)\\...", "Acrobat 装在别处"],
        ["ACROBAT_MAIN_TITLE_RE", "r'.*Adobe Acrobat.*'", "仅日志兜底, 一般不动"],
        ["ACROBAT_WINDOW_CLASS", "AcrobatSDIWindow", "Acrobat 大版本升级"],
        ["BTN_REMOVE_WATERMARK", "去水印", "中文版按钮名变化"],
        ["BTN_ACTION_LIST_RE", "r'^动作列表'", "同上"],
        ["DLG_ACTION_LIST_TITLE", "动作列表", "同上"],
        ["DEFAULT_WATERMARK_TEXT", "示例水印", "默认水印 (GUI 输入框默认值)"],
        ["ACTION_PROGRESS_TEXT", "运行动作列表", "保留备用, 当前未使用"],
        ["TIMEOUT_APP_START", "30", "Acrobat 启动很慢可调大"],
        ["TIMEOUT_FILE_OPEN", "60", "大 PDF 打开很慢可调大"],
        ["TIMEOUT_CONTROL_READY", "20", "控件就绪超时"],
        ["TIMEOUT_SAVE", "60", "保存超时"],
        ["TIMEOUT_ACTION_RUN", "300", "单个动作执行超时"],
        ["POLL_INTERVAL", "0.5", "轮询间隔 (秒)"],
    ],
    col_widths_cm=[6, 5, 5],
    code_cols=[0],
)

add_heading(doc, "9.2 acrobat_batch.py 顶部常量", level=2)
add_table(doc,
    ["常量", "默认值", "说明"],
    [
        ["PER_FILE_TIMEOUT", "300", "单文件硬超时 (秒), UI 可覆盖"],
        ["CONSECUTIVE_SAME_STAGE", "3", "连续同阶段失败 → 自动暂停"],
        ["CONSECUTIVE_TOTAL_FAIL", "5", "连续失败 (任何阶段) → 自动暂停"],
        ["EST_SEC_PER_FILE", "25", "预估单文件耗时 (用于开始前提示)"],
        ["REPORT_SUBDIR", "reports", "CSV 报告子目录名 (实际路径 = <输入文件夹>/REPORT_SUBDIR)"],
    ],
    col_widths_cm=[6, 4, 6],
    code_cols=[0],
)

# 10. 测试建议
add_heading(doc, "10. 测试建议", level=1)
add_para(doc, "改代码后建议按以下顺序测试：")
add_number(doc, "单元: 单文件版 python acrobat_gui_min.py 跑 1 个 PDF, 确认核心 worker 没坏")
add_number(doc, "批量小: python acrobat_batch.py 选 3 个 PDF (大小差异), 确认完整流程")
add_number(doc, "批量大: 选 10+ 个 PDF, 验证 Acrobat 长时间运行的稳定性")
add_number(doc, "异常: 选择不存在的水印名, 验证连续失败的自动暂停机制")
add_note_box(doc, "测试技巧",
    "保留一个'故意会失败的 PDF'（如密码加密的）作为对照, "
    "每次回归测试都跑它, 确认失败处理逻辑没退化."
)

# 结尾
doc.add_paragraph()
end = doc.add_paragraph()
end.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
end_run = end.add_run("—— 文档结束 ——")
end_run.font.color.rgb = RGBColor.from_string("999999")
end_run.italic = True
set_cn_font(end_run)


import os as _os
OUT = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "开发指南.docx")
doc.save(OUT)
print(f"OK: {OUT}")
