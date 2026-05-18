# -*- coding: utf-8 -*-
"""
=====================================================================
 Adobe Acrobat DC (中文版) - PDF 批量删除水印自动化脚本
---------------------------------------------------------------------
 技术栈: pywinauto (backend="uia") + 原生快捷键混合操控
 适配:   Windows 10/11 + Adobe Acrobat Pro DC (中文界面)
 作者:   RPA 自动化模板
=====================================================================

【运行前必做的环境调整】(避坑指南)
    打开 Acrobat DC -> 编辑 -> 首选项 -> 一般
    取消勾选 "打开没有文档的应用程序时显示主页屏幕"
    保证 Acrobat 启动后是纯净灰色背景, Ctrl+O 才能 100% 唤出文件框。

【依赖安装】
    pip install pywinauto pillow comtypes

【极客备注 - 关于 win32com.client (Acrobat OLE/COM) 的可行性】
    Adobe Acrobat Pro DC 暴露了 COM 接口 (AcroExch.App / AcroExch.PDDoc /
    AcroExch.AVDoc), 可以通过 win32com.client.Dispatch("AcroExch.App") 实现
    无 UI 控制。但是 —— "删除水印" 这个动作 Acrobat 并没有直接暴露在 COM 的
    一级方法里, 它是 Acrobat JavaScript (JSObject) 层的 watermarkRemove() 方法。
    可行思路:
        app  = win32com.client.Dispatch("AcroExch.App")
        pdf  = win32com.client.Dispatch("AcroExch.PDDoc")
        pdf.Open(path)
        jso  = pdf.GetJSObject()
        jso.removeWatermarks()     # JS 层方法, 无界面交互, 真正的静默批处理
        pdf.Save(1, path)
        pdf.Close()
    优点: 完全无 UI、速度快 10 倍以上、不怕窗口被遮挡。
    缺点: 需要 Acrobat Pro (非 Reader)、要启用 JSObject、对加密 PDF 仍会弹窗。
    本脚本采用 pywinauto 方案, 是因其与中文界面控件天然契合且易于 inspect 调试。
=====================================================================
"""

import os
import sys
import time
import logging
import traceback
from pathlib import Path

from pywinauto.application import Application
from pywinauto.keyboard import send_keys
from pywinauto.timings import wait_until, TimeoutError as PwaTimeoutError
from pywinauto import findwindows


# =====================================================================
# 【可配置变量区】—— 请用 Inspect.exe / UISpy 微调以下名称
# =====================================================================

# ---------- 路径配置 ----------
INPUT_DIR        = r"./input"      # 待处理 PDF 所在文件夹 (支持中文/空格), 改成你的实际路径
LOG_FILE         = r"./run.log"    # 日志文件路径

# ---------- Acrobat 可执行文件路径 (如不在 PATH 中, 请填绝对路径) ----------
ACROBAT_EXE      = r"C:\Program Files\Adobe\Acrobat DC\Acrobat\Acrobat.exe"

# ---------- 窗口标题关键字 (用正则模糊匹配, 兼容不同文件名后缀) ----------
ACROBAT_MAIN_TITLE_RE = r".*Adobe Acrobat.*"        # Acrobat 主窗口

# ---------- 右侧工具栏 / 菜单中的中文按钮名称 ----------
BTN_EDIT_PDF       = "编辑 PDF"        # 右侧工具栏: 进入编辑模式
BTN_WATERMARK      = "水印"            # 顶部子菜单: 水印
BTN_REMOVE         = "删除"            # 水印 -> 下拉项: 删除
BTN_CONFIRM_YES    = "是"              # 确认弹窗的 "是" / 也可能是 "确定" "OK"
BTN_CONFIRM_OK     = "确定"            # 备用确认按钮文本

# ---------- 超时配置 (秒) ----------
TIMEOUT_APP_START     = 30   # Acrobat 启动超时
TIMEOUT_FILE_OPEN     = 60   # 单个 PDF 打开超时
TIMEOUT_CONTROL_READY = 20   # 控件可见 / 可点击超时
TIMEOUT_SAVE          = 60   # 保存超时
POLL_INTERVAL         = 0.5  # 轮询间隔


# =====================================================================
# 【日志初始化】—— 同时输出到控制台与文件, 强制 UTF-8 防止中文乱码
# =====================================================================

def init_logger():
    """初始化日志系统, 控制台 + 文件双路输出, 全程 UTF-8."""
    # 保证 Windows 控制台能输出中文
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    logger = logging.getLogger("AcrobatRPA")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台 handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # 文件 handler (UTF-8)
    Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger


log = init_logger()


# =====================================================================
# 【工具函数区】
# =====================================================================

def scan_pdf_files(folder: str):
    """扫描指定文件夹下所有 .pdf 文件, 返回绝对路径列表 (支持中文)."""
    folder_path = Path(folder)
    if not folder_path.is_dir():
        raise FileNotFoundError(f"输入文件夹不存在: {folder}")
    pdfs = sorted(
        [str(p.resolve()) for p in folder_path.iterdir()
         if p.is_file() and p.suffix.lower() == ".pdf"]
    )
    log.info(f"共扫描到 {len(pdfs)} 个 PDF 文件待处理")
    return pdfs


def launch_acrobat():
    """启动 Acrobat DC 并返回 Application + 主窗口对象."""
    log.info("正在启动 Adobe Acrobat DC ...")
    try:
        app = Application(backend="uia").start(ACROBAT_EXE)
    except Exception:
        # 如果已经在运行, 直接 connect
        log.warning("启动失败, 尝试连接已运行的 Acrobat 实例 ...")
        app = Application(backend="uia").connect(title_re=ACROBAT_MAIN_TITLE_RE,
                                                 timeout=TIMEOUT_APP_START)

    # 动态等待主窗口出现 (不用硬 sleep)
    main_win = app.window(title_re=ACROBAT_MAIN_TITLE_RE)
    main_win.wait("visible ready", timeout=TIMEOUT_APP_START)
    main_win.set_focus()
    log.info(f"Acrobat 主窗口已就绪: {main_win.window_text()}")
    return app, main_win


def open_pdf_via_dialog(main_win, pdf_path: str):
    """通过 Ctrl+O 调出原生打开对话框, 输入中文路径并打开."""
    log.info(f"打开文件: {pdf_path}")
    main_win.set_focus()

    # 发送 Ctrl+O
    send_keys("^o")

    # 等待 "打开" 对话框出现 (Windows 通用文件选择对话框)
    # 中文版标题通常为 "打开"
    open_dlg = None
    deadline = time.time() + TIMEOUT_CONTROL_READY
    while time.time() < deadline:
        try:
            handles = findwindows.find_windows(title_re=r"^(打开|Open)$",
                                               class_name="#32770")
            if handles:
                app2 = Application(backend="uia").connect(handle=handles[0])
                open_dlg = app2.window(handle=handles[0])
                if open_dlg.exists() and open_dlg.is_visible():
                    break
        except Exception:
            pass
        time.sleep(POLL_INTERVAL)

    if open_dlg is None:
        raise PwaTimeoutError("未能捕获到 '打开' 对话框")

    open_dlg.set_focus()

    # 文件名输入框: 通用文件对话框中名为 "文件名(N):" / "File name:"
    # 用 child_window 通过控件类型 Edit 兜底
    edit = open_dlg.child_window(class_name="Edit", found_index=0)
    edit.wait("enabled", timeout=TIMEOUT_CONTROL_READY)
    edit.set_edit_text("")          # 清空, 防止追加
    edit.set_edit_text(pdf_path)    # 直接灌入中文绝对路径

    # 回车确认 (比点击 "打开" 按钮更稳)
    send_keys("{ENTER}")

    # 等待对话框消失 + 主窗口标题包含文件名
    file_stem = Path(pdf_path).stem
    deadline = time.time() + TIMEOUT_FILE_OPEN
    while time.time() < deadline:
        try:
            if not open_dlg.exists():
                # 进一步确认 Acrobat 标题栏包含文件名 (说明 PDF 加载完成)
                title_now = main_win.window_text()
                if file_stem in title_now or ".pdf" in title_now.lower():
                    log.info(f"PDF 已加载: {title_now}")
                    return
        except Exception:
            # 对话框句柄失效 = 已关闭, 也算成功
            title_now = main_win.window_text()
            if file_stem in title_now or ".pdf" in title_now.lower():
                return
        time.sleep(POLL_INTERVAL)

    raise PwaTimeoutError(f"打开 PDF 超时: {pdf_path}")


def click_control_by_name(parent_win, name: str, timeout: int = TIMEOUT_CONTROL_READY):
    """
    在父窗口中查找指定 name 的可点击控件并点击.
    优先 Button, 再退化为任何带该 name 的元素 (菜单项 / 工具条按钮).
    """
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        # 尝试多种控件类型
        for ctrl_type in (None, "Button", "MenuItem", "ListItem", "Text"):
            try:
                kwargs = {"title": name}
                if ctrl_type:
                    kwargs["control_type"] = ctrl_type
                ctrl = parent_win.child_window(**kwargs)
                if ctrl.exists() and ctrl.is_visible():
                    ctrl.wait("enabled", timeout=2)
                    ctrl.click_input()
                    log.info(f"已点击控件: {name}  (control_type={ctrl_type})")
                    return True
            except Exception as e:
                last_err = e
        time.sleep(POLL_INTERVAL)
    raise PwaTimeoutError(f"未能在 {timeout}s 内定位并点击控件: {name} | 最后异常: {last_err}")


def remove_watermark(main_win):
    """执行 右侧 [编辑 PDF] -> [水印] -> [删除] -> 确认弹窗 [是/确定]."""
    # Step 1: 点击右侧工具栏的 "编辑 PDF"
    click_control_by_name(main_win, BTN_EDIT_PDF, timeout=TIMEOUT_CONTROL_READY)

    # Step 2: 编辑模式加载后, 顶部出现 "水印" 菜单按钮
    click_control_by_name(main_win, BTN_WATERMARK, timeout=TIMEOUT_CONTROL_READY)

    # Step 3: 下拉菜单中点击 "删除"
    click_control_by_name(main_win, BTN_REMOVE, timeout=TIMEOUT_CONTROL_READY)

    # Step 4: 处理确认弹窗 ("是否确定永久删除水印")
    # 弹窗可能是 Acrobat 自绘的 Pane, 也可能是系统对话框, 故双重尝试
    deadline = time.time() + TIMEOUT_CONTROL_READY
    confirmed = False
    while time.time() < deadline and not confirmed:
        for btn_name in (BTN_CONFIRM_YES, BTN_CONFIRM_OK, "OK", "Yes"):
            try:
                ctrl = main_win.child_window(title=btn_name, control_type="Button")
                if ctrl.exists() and ctrl.is_visible():
                    ctrl.wait("enabled", timeout=2)
                    ctrl.click_input()
                    log.info(f"确认弹窗已点击: {btn_name}")
                    confirmed = True
                    break
            except Exception:
                continue
        if not confirmed:
            time.sleep(POLL_INTERVAL)

    if not confirmed:
        # 退路: 用回车确认 (默认按钮通常聚焦在 "是")
        log.warning("未找到具名确认按钮, 尝试用 Enter 确认弹窗")
        send_keys("{ENTER}")


def save_and_close(main_win, pdf_path: str):
    """Ctrl+S 保存 -> 等待保存完成 -> Ctrl+W 关闭当前文档."""
    log.info("保存当前 PDF (Ctrl+S) ...")
    main_win.set_focus()
    send_keys("^s")

    # 保存时若是首次, 可能弹 "另存为" 对话框 (覆盖原文件场景一般不会)
    # 这里动态等待: 标题栏不再包含修改标记 (Acrobat 修改时常带 * 号或临时态)
    # 简化策略: 等待主窗口仍处于 ready 状态 + 一个合理短时间
    deadline = time.time() + TIMEOUT_SAVE
    while time.time() < deadline:
        try:
            # 如果弹出 "另存为" 之类的辅助对话框, 直接 Enter 接受默认覆盖
            for handle in findwindows.find_windows(class_name="#32770"):
                try:
                    app2 = Application(backend="uia").connect(handle=handle)
                    dlg = app2.window(handle=handle)
                    title = dlg.window_text()
                    if title in ("另存为", "Save As", "保存"):
                        log.info(f"检测到对话框 [{title}], 回车确认")
                        dlg.set_focus()
                        send_keys("{ENTER}")
                except Exception:
                    pass
            # 主窗口仍存在 = 保存动作已发出
            if main_win.exists() and main_win.is_visible():
                break
        except Exception:
            pass
        time.sleep(POLL_INTERVAL)

    log.info("关闭当前文档 (Ctrl+W) ...")
    main_win.set_focus()
    send_keys("^w")

    # 等待文档关闭: 标题栏不再包含文件名
    stem = Path(pdf_path).stem
    deadline = time.time() + TIMEOUT_CONTROL_READY
    while time.time() < deadline:
        try:
            title_now = main_win.window_text()
            if stem not in title_now:
                log.info("文档已关闭")
                return
        except Exception:
            return
        time.sleep(POLL_INTERVAL)
    log.warning("关闭文档超时, 继续下一个")


def emergency_recover(main_win):
    """卡死时的应急: 连发 ESC 关闭弹窗, 再 Ctrl+W 关闭文档."""
    log.warning("执行应急恢复: 连发 ESC + Ctrl+W")
    try:
        main_win.set_focus()
    except Exception:
        pass
    for _ in range(5):
        send_keys("{ESC}")
        time.sleep(0.3)
    send_keys("^w")
    time.sleep(1)
    # 如果出现 "是否保存更改" 弹窗, 选择不保存 (避免污染原文件) —— 这里改成保存
    # 实际场景按需调整: 默认 Enter = 保存
    send_keys("{ENTER}")
    time.sleep(0.5)


# =====================================================================
# 【主流程】
# =====================================================================

def main():
    log.info("=" * 60)
    log.info("Acrobat DC 批量去水印任务启动")
    log.info("=" * 60)

    pdf_list = scan_pdf_files(INPUT_DIR)
    if not pdf_list:
        log.warning("输入文件夹中没有 PDF, 任务结束")
        return

    app, main_win = launch_acrobat()

    success, failed = 0, 0
    for idx, pdf in enumerate(pdf_list, 1):
        log.info("-" * 60)
        log.info(f"[{idx}/{len(pdf_list)}] 处理: {pdf}")
        try:
            open_pdf_via_dialog(main_win, pdf)
            remove_watermark(main_win)
            save_and_close(main_win, pdf)
            success += 1
            log.info(f"[{idx}/{len(pdf_list)}] 成功 ✔")
        except Exception as e:
            failed += 1
            log.error(f"[{idx}/{len(pdf_list)}] 失败 ✘ : {e}")
            log.error(traceback.format_exc())
            try:
                emergency_recover(main_win)
            except Exception as ee:
                log.error(f"应急恢复也失败: {ee}")
            # 不抛出, 继续下一个
            continue

    log.info("=" * 60)
    log.info(f"任务完成 —— 成功 {success} / 失败 {failed} / 总数 {len(pdf_list)}")
    log.info(f"日志路径: {LOG_FILE}")
    log.info("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.warning("用户中断 (Ctrl+C)")
    except Exception as e:
        log.critical(f"主流程崩溃: {e}")
        log.critical(traceback.format_exc())
        sys.exit(1)
