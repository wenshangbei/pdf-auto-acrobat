# -*- coding: utf-8 -*-
"""生成《用户操作手册.docx》"""
from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


CN_FONT = "微软雅黑"


def set_cn_font(run, font_name=CN_FONT):
    """python-docx 设置东亚字体需要直接改 XML."""
    run.font.name = font_name
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    rFonts.set(qn("w:eastAsia"), font_name)
    rFonts.set(qn("w:ascii"), font_name)
    rFonts.set(qn("w:hAnsi"), font_name)


def set_cell_bg(cell, color_hex):
    """给表格 cell 设置背景色."""
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color_hex)
    tcPr.append(shd)


def add_para(doc, text, bold=False, size=11, color=None, style=None):
    p = doc.add_paragraph(style=style) if style else doc.add_paragraph()
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


def add_warning_box(doc, title, body):
    """用单 cell 表格 + 浅红背景模拟警告框."""
    t = doc.add_table(rows=1, cols=1)
    cell = t.rows[0].cells[0]
    set_cell_bg(cell, "FFE5E5")
    # 清掉默认空段落
    cell.paragraphs[0].text = ""
    p1 = cell.paragraphs[0]
    r1 = p1.add_run(f"⚠ {title}")
    r1.bold = True
    r1.font.size = Pt(11)
    r1.font.color.rgb = RGBColor.from_string("CC0000")
    set_cn_font(r1)
    p2 = cell.add_paragraph()
    r2 = p2.add_run(body)
    r2.font.size = Pt(11)
    set_cn_font(r2)
    doc.add_paragraph()  # 间距


def add_tip_box(doc, title, body):
    t = doc.add_table(rows=1, cols=1)
    cell = t.rows[0].cells[0]
    set_cell_bg(cell, "E8F4FF")
    cell.paragraphs[0].text = ""
    p1 = cell.paragraphs[0]
    r1 = p1.add_run(f"💡 {title}")
    r1.bold = True
    r1.font.size = Pt(11)
    r1.font.color.rgb = RGBColor.from_string("0066CC")
    set_cn_font(r1)
    p2 = cell.add_paragraph()
    r2 = p2.add_run(body)
    r2.font.size = Pt(11)
    set_cn_font(r2)
    doc.add_paragraph()


def add_table(doc, header, rows, col_widths_cm=None):
    """添加带表头 + 数据行的表格."""
    t = doc.add_table(rows=1 + len(rows), cols=len(header))
    t.style = "Light Grid Accent 1"
    if col_widths_cm:
        for i, w in enumerate(col_widths_cm):
            for cell in t.columns[i].cells:
                cell.width = Cm(w)
    # 表头
    for i, h in enumerate(header):
        cell = t.rows[0].cells[i]
        cell.text = ""
        run = cell.paragraphs[0].add_run(h)
        run.bold = True
        run.font.size = Pt(11)
        set_cn_font(run)
        set_cell_bg(cell, "D5E8F0")
    # 数据行
    for ri, row in enumerate(rows, start=1):
        for ci, val in enumerate(row):
            cell = t.rows[ri].cells[ci]
            cell.text = ""
            run = cell.paragraphs[0].add_run(str(val))
            run.font.size = Pt(10)
            set_cn_font(run)
    doc.add_paragraph()
    return t


def add_screenshot_placeholder(doc, caption):
    """截图占位符 (留给用户后续插入实际截图)."""
    t = doc.add_table(rows=1, cols=1)
    cell = t.rows[0].cells[0]
    set_cell_bg(cell, "F0F0F0")
    cell.paragraphs[0].text = ""
    p = cell.paragraphs[0]
    p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    r = p.add_run(f"📷 [此处放截图: {caption}]")
    r.italic = True
    r.font.color.rgb = RGBColor.from_string("888888")
    set_cn_font(r)
    doc.add_paragraph()


# ===============================================================
# 开始写文档
# ===============================================================
doc = Document()

# 设置默认字体
style = doc.styles["Normal"]
style.font.name = CN_FONT
style.font.size = Pt(11)
style._element.rPr.rFonts.set(qn("w:eastAsia"), CN_FONT)

# 封面标题
title = doc.add_heading(level=0)
title_run = title.add_run("Acrobat 批量去水印 - 用户操作手册")
set_cn_font(title_run)
title.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER

subtitle = doc.add_paragraph()
subtitle.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
sub_run = subtitle.add_run("版本 1.0  |  适用于 Windows 10/11 + Acrobat Pro DC 中文版")
sub_run.font.size = Pt(11)
sub_run.font.color.rgb = RGBColor.from_string("666666")
set_cn_font(sub_run)

doc.add_paragraph()

# 1. 软件简介
add_heading(doc, "1. 软件简介", level=1)
add_para(doc,
    "本工具用于批量自动化处理 PDF 文件 —— 自动打开 Adobe Acrobat Pro DC，"
    "执行您预先设定好的「去水印」动作，保存后关闭文档，逐个处理整个文件夹下的 PDF。"
)
add_para(doc,
    "适用场景：律所卷宗、合同文档、试卷资料等"
    "需要批量去除嵌入式水印的 PDF 集合。"
)
add_tip_box(doc, "工作原理",
    "本工具通过自动化操控 Acrobat 软件本身完成去水印（相当于自动点鼠标），"
    "并非直接修改 PDF 文件。因此处理效果取决于您在 Acrobat 中预设的去水印动作。"
)

# 2. 前置准备
add_heading(doc, "2. 前置准备", level=1)

add_heading(doc, "2.1 安装 Adobe Acrobat Pro DC", level=2)
add_para(doc, "本工具依赖 Adobe Acrobat 软件。请先确认：")
add_bullet(doc, "已安装 Adobe Acrobat Pro DC（必须是 Pro 版，标准版没有动作向导功能）")
add_bullet(doc, "界面是中文版（按钮文字需要匹配「去水印」「动作列表」「保存」等中文标签）")
add_bullet(doc, "已激活，能正常使用")
add_warning_box(doc, "不要用 Acrobat Reader",
    "Reader（免费版）不支持动作向导，无法运行本工具。必须是 Pro 付费版。"
)

add_heading(doc, "2.2 在 Acrobat 中录制「去水印」动作", level=2)
add_para(doc, "这是关键步骤。本工具会调用 Acrobat 的「动作向导」执行您预先录制好的动作。请按以下步骤录制：")
add_number(doc, "打开 Acrobat Pro DC，任意打开一个含水印的 PDF 文件")
add_number(doc, "点击右侧工具栏的「动作向导」（如果没看到，先点「更多工具」搜索）")
add_number(doc, "点击「创建新动作」")
add_number(doc, "在左侧工具列表里找到「文档处理 → 删除水印」，双击添加到右侧动作步骤")
add_number(doc, "点击右上角「保存」按钮，弹出命名对话框")
add_number(doc, "动作名称必须填写为「水印文字本身」，例如要去掉名字「示例水印」的水印，动作名就填「示例水印」")
add_number(doc, "确认保存。此时您的「动作列表」里就有了一个名为「示例水印」的动作")
add_screenshot_placeholder(doc, "Acrobat 录制动作的界面")
add_warning_box(doc, "动作名 = 水印文字",
    "本工具会根据您输入的水印文字，去 Acrobat 的动作列表里查找同名动作。"
    "所以动作名必须与水印文字完全一致（包括标点、空格、大小写）。"
)

add_heading(doc, "2.3 关闭 Acrobat 启动主页", level=2)
add_para(doc, "Acrobat 启动时默认显示「主页」屏幕，会干扰自动化。请按以下步骤关闭：")
add_number(doc, "打开 Acrobat Pro DC")
add_number(doc, "点击菜单「编辑 → 首选项」")
add_number(doc, "在左侧分类中选择「一般」")
add_number(doc, "找到「打开没有文档的应用程序时显示主页屏幕」选项，取消勾选")
add_number(doc, "点「确定」保存设置")

# 3. 软件安装
add_heading(doc, "3. 软件安装", level=1)
add_para(doc, "如果您拿到的是打包好的 exe 文件夹：")
add_number(doc, "把整个 Acrobat批量去水印 文件夹解压到任意位置（建议桌面）")
add_number(doc, "进入文件夹，找到 Acrobat批量去水印.exe")
add_number(doc, "双击即可运行（首次运行可能被杀毒软件拦截，添加信任即可）")
add_tip_box(doc, "无需安装 Python",
    "exe 已经打包了所有依赖，目标机器只需要装 Adobe Acrobat Pro DC 即可。"
    "拷贝时务必拷整个文件夹，不能只拷 exe 文件。"
)

# 4. 操作步骤
add_heading(doc, "4. 操作步骤", level=1)

add_heading(doc, "步骤 1：启动程序", level=2)
add_para(doc, "双击 Acrobat批量去水印.exe，等待几秒钟主界面弹出。")
add_screenshot_placeholder(doc, "程序主界面截图")

add_heading(doc, "步骤 2：选择 PDF 所在文件夹", level=2)
add_para(doc, "有两种方式：")
add_bullet(doc, "方式一：点「选择...」按钮，从弹出的对话框里选择文件夹")
add_bullet(doc, "方式二：直接在「输入文件夹」文本框里粘贴路径，按 Enter 键或点「扫描」按钮")
add_para(doc, "扫描完成后，下方列表会显示文件夹里所有 PDF（带 ☑ 表示默认勾选）。")

add_heading(doc, "步骤 3：输入水印文字", level=2)
add_para(doc, "在「水印文字」文本框里输入要去除的水印内容，必须与 Acrobat 动作列表里的动作名完全一致。")
add_warning_box(doc, "必须完全一致",
    "例如动作名是「示例水印」，输入「示例水印 」(末尾多个空格) 就找不到。"
    "建议直接从 Acrobat 动作列表里复制粘贴。"
)

add_heading(doc, "步骤 4：设置单文件超时", level=2)
add_para(doc, "在「单文件超时(秒)」框里设置每个 PDF 的最长处理时间，默认 300 秒（5 分钟）。")
add_para(doc, "超过这个时间程序会自动放弃该文件，强制关闭 Acrobat，继续处理下一个。")
add_table(doc,
    ["PDF 大小", "推荐超时值"],
    [
        ["< 50 MB", "180 秒（默认即可）"],
        ["50 - 200 MB", "300 秒（默认值已够）"],
        ["200 - 500 MB", "600 秒"],
        ["> 500 MB", "1200 秒，或手动单独处理"],
    ],
    col_widths_cm=[5, 8],
)

add_heading(doc, "步骤 5：勾选要处理的 PDF", level=2)
add_para(doc, "默认所有 PDF 都已勾选。如果只想处理部分文件，可以：")
add_bullet(doc, "点击文件行的 ☑ / ☐ 切换单个文件的勾选状态")
add_bullet(doc, "点「全选」/「全不选」/「反选」批量操作")

add_heading(doc, "步骤 6：开始批量处理", level=2)
add_para(doc, "点「▶ 开始批量处理」按钮，会弹出二次确认对话框，提醒注意事项。点「确定」后正式开始。")

add_heading(doc, "步骤 7：等待 —— 不要操作电脑", level=2)
add_warning_box(doc, "全程禁止操作鼠标、键盘",
    "本工具靠模拟真实鼠标点击操控 Acrobat。处理期间，您任何鼠标移动、"
    "键盘输入、切换窗口、锁屏的操作都会打断流程导致失败。"
    "建议趁这段时间去倒杯水、看看手机，电脑就让它自己跑。"
)
add_para(doc, "处理过程中：")
add_bullet(doc, "顶部红色横幅会一直显示「自动化运行中」")
add_bullet(doc, "进度条显示当前进度（如 3/12）")
add_bullet(doc, "列表里每个文件处理完会显示状态（success/failed/timeout）")
add_bullet(doc, "日志区实时输出每一步操作")

add_heading(doc, "步骤 8：完成后查看报告", level=2)
add_para(doc, "全部处理完后会弹出汇总弹窗，显示成功/失败/超时数量、总耗时。")
add_para(doc, "详细的报告 CSV 文件位于程序目录下的 reports 子文件夹，可以用 Excel 打开。")
add_screenshot_placeholder(doc, "完成弹窗 + CSV 报告截图")

# 5. 控制按钮
add_heading(doc, "5. 运行中控制按钮", level=1)
add_table(doc,
    ["按钮", "作用", "使用场景"],
    [
        ["⏸ 暂停", "当前文件处理完后停下，不强杀 Acrobat",
         "您临时需要用电脑，等当前文件处理完再停。再点「继续」恢复"],
        ["⏭ 跳过当前", "立即强杀 Acrobat，跳过当前文件继续下一个",
         "某个文件卡住了，不想等超时（300秒），手动放弃"],
        ["⏹ 终止", "停止整个批量处理",
         "整体出问题（比如 Acrobat 不响应），完全终止"],
    ],
    col_widths_cm=[3, 6, 8],
)

# 6. 报告解读
add_heading(doc, "6. 报告解读", level=1)
add_para(doc, "每次运行都会在 reports 目录生成一份 CSV 文件，文件名格式 batch_YYYYMMDD_HHMMSS.csv。")
add_para(doc, "用 Excel 打开，包含以下字段：")
add_table(doc,
    ["字段", "说明"],
    [
        ["序号", "PDF 的处理顺序"],
        ["文件路径", "PDF 的完整路径"],
        ["大小KB", "文件大小（KB）"],
        ["状态", "见下方状态说明"],
        ["开始时间 / 结束时间", "处理的时间点"],
        ["耗时(秒)", "本文件处理用了多少秒"],
        ["失败阶段", "失败时停在哪一步（仅失败时有值）"],
        ["失败原因", "具体错误信息（仅失败时有值）"],
    ],
    col_widths_cm=[4, 11],
)

add_heading(doc, "6.1 状态字段说明", level=2)
add_table(doc,
    ["状态", "含义", "处理建议"],
    [
        ["success", "处理成功，PDF 已保存", "无需处理"],
        ["failed", "Acrobat 报错（界面变化、动作不存在等）",
         "看失败原因，必要时重新录动作或重跑"],
        ["timeout", "超过单文件超时秒数",
         "调高超时参数或手动单独处理大文件"],
        ["skipped", "您手动跳过 / 终止",
         "如有需要单独重跑"],
    ],
    col_widths_cm=[3, 6, 8],
)

add_heading(doc, "6.2 针对失败的文件重跑", level=2)
add_para(doc, "建议步骤：")
add_number(doc, "打开 reports/*.csv，按「状态」列筛选 failed / timeout 的行")
add_number(doc, "把这些文件复制到一个新的文件夹（例如「失败重跑」）")
add_number(doc, "在程序中选择这个新文件夹重新处理")
add_tip_box(doc, "为什么失败可以重跑成功？",
    "很多失败是临时性的（比如刚好那一刻用户动了鼠标、Acrobat 内部状态异常）。"
    "重跑通常能解决大部分。如果同一个文件连续 3 次都失败，再考虑手动处理。"
)

# 7. FAQ
add_heading(doc, "7. 常见问题 FAQ", level=1)

add_heading(doc, "Q1：提示「找不到 TreeItem 名称='xxx'」？", level=2)
add_para(doc, "原因：您在程序里输入的水印文字，在 Acrobat 的动作列表里找不到对应的动作。")
add_para(doc, "排查：")
add_bullet(doc, "打开 Acrobat，点动作向导，查看动作列表里的动作名称")
add_bullet(doc, "确认您输入的文字与动作名完全一致（包括标点、空格、大小写、繁简体）")
add_bullet(doc, "建议直接复制动作名粘贴到程序输入框")

add_heading(doc, "Q2：大 PDF 总是 timeout 怎么办？", level=2)
add_para(doc, "原因：单文件超时设置太短。")
add_para(doc, "解决：")
add_bullet(doc, "把「单文件超时(秒)」从 300 改成 600 或 1200")
add_bullet(doc, "如果文件超过 500MB，建议单独手动处理，不要混在批量里")

add_heading(doc, "Q3：处理中我不小心动了鼠标，怎么办？", level=2)
add_para(doc, "如果导致某个文件失败：")
add_bullet(doc, "本文件会被标记为 failed，但不影响后续文件")
add_bullet(doc, "等批量处理完后，按 6.2 节方法重跑失败的文件即可")

add_heading(doc, "Q4：Acrobat 启动后没反应、程序卡住？", level=2)
add_para(doc, "可能原因：之前的 Acrobat 进程没完全退出。")
add_para(doc, "解决：")
add_bullet(doc, "终止当前批量处理")
add_bullet(doc, "双击 kill_acrobat.bat（在程序目录里），强杀所有 Adobe 进程")
add_bullet(doc, "等几秒后重新启动程序")

add_heading(doc, "Q5：处理后的 PDF 在哪里？", level=2)
add_para(doc, "本工具直接覆盖原文件（节省磁盘空间）。如果您想保留原始版本，请在处理前手动备份。")
add_warning_box(doc, "建议处理前备份",
    "去水印是不可逆操作。建议把原始 PDF 文件夹整个复制一份作为备份，"
    "确保万一有问题可以恢复。"
)

add_heading(doc, "Q6：多大的批量合适？", level=2)
add_para(doc, "经验值：")
add_bullet(doc, "单次批量建议 50 个以内，超过 100 个时 Acrobat 长时间运行容易内存累积")
add_bullet(doc, "大批量建议分批跑，每批之间重启电脑或者至少强杀 Acrobat")

# 结尾
add_heading(doc, "8. 联系方式与反馈", level=1)
add_para(doc, "如果遇到本手册未提及的问题，请联系软件提供方，并附上：")
add_bullet(doc, "reports 目录下对应的 CSV 文件")
add_bullet(doc, "失败截图（如有）")
add_bullet(doc, "Acrobat 版本号和操作系统版本")

doc.add_paragraph()
end = doc.add_paragraph()
end.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
end_run = end.add_run("—— 文档结束 ——")
end_run.font.color.rgb = RGBColor.from_string("999999")
end_run.italic = True
set_cn_font(end_run)


import os as _os
OUT = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "用户操作手册.docx")
doc.save(OUT)
print(f"OK: {OUT}")
