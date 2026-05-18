# -*- coding: utf-8 -*-
"""
=====================================================================
 Acrobat DC 去水印 - 最小可执行版 (单文件 + tkinter GUI)
---------------------------------------------------------------------
 流程: 选PDF -> 启动Acrobat -> Ctrl+O打开 -> 点右侧"去水印"工具
       -> 处理确认弹窗 -> Ctrl+S保存 -> Ctrl+W关闭
=====================================================================
"""

import os
import sys
import time
import threading
import traceback
import queue
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from pywinauto.application import Application
from pywinauto.keyboard import send_keys
from pywinauto.timings import TimeoutError as PwaTimeoutError
from pywinauto import findwindows


# =====================================================================
# 【可配置变量】—— 用 inspect.exe 确认后微调
# =====================================================================

ACROBAT_EXE           = r"C:\Program Files (x86)\Adobe\Acrobat DC\Acrobat\Acrobat.exe"
ACROBAT_MAIN_TITLE_RE = r".*Adobe Acrobat.*"   # 仅供日志/兜底使用
ACROBAT_WINDOW_CLASS  = "AcrobatSDIWindow"     # 主窗口的 Win32 类名 (跨架构稳定, 优先用这个 connect)

# 右侧工具栏的"去水印"工具名称 (用 inspect 确认实际显示名)
BTN_REMOVE_WATERMARK  = "去水印"

# "去水印"工具面板里的"动作列表"按钮
BTN_ACTION_LIST_RE    = r"^动作列表"

# 弹出的"动作列表"窗口标题
DLG_ACTION_LIST_TITLE = "动作列表"

# 用户默认水印文字 (GUI 输入框的默认值, 用户可修改)
DEFAULT_WATERMARK_TEXT = "示例水印"

# Acrobat 执行动作时弹出的进度面板文字
ACTION_PROGRESS_TEXT  = "运行动作列表"
TIMEOUT_ACTION_RUN    = 300  # 动作执行最长等待 (秒), 大 PDF 可能慢

# 确认弹窗按钮 (中文Acrobat一般是"是"/"确定")
BTN_CONFIRM_YES       = "是"
BTN_CONFIRM_OK        = "确定"

# 超时 (秒)
TIMEOUT_APP_START     = 30
TIMEOUT_FILE_OPEN     = 60
TIMEOUT_CONTROL_READY = 20
TIMEOUT_SAVE          = 60
POLL_INTERVAL         = 0.5


# =====================================================================
# 【核心自动化逻辑】—— 与 GUI 解耦, 通过 log_func 回调输出日志
# =====================================================================

class AcrobatWorker:
    """封装 Acrobat 操作, 日志通过回调输出到 GUI."""

    def __init__(self, log_func):
        self.log = log_func
        self.app = None
        self.main_win = None

    # ---------- 启动 / 连接 Acrobat ----------
    def launch(self):
        self.log(f"启动 Acrobat: {ACROBAT_EXE}")
        if not Path(ACROBAT_EXE).is_file():
            raise FileNotFoundError(f"找不到 Acrobat 可执行文件: {ACROBAT_EXE}")

        try:
            Application(backend="uia").start(ACROBAT_EXE)
            self.log("Acrobat.exe 已调用 (launcher 进程可能已退出, 接下来等待真正的主窗口)")
        except Exception as e:
            self.log(f"start() 异常 (可能已有实例运行): {e}")

        self.log(f"等待主窗口出现 (按 class_name={ACROBAT_WINDOW_CLASS}, 最多 {TIMEOUT_APP_START}s) ...")
        deadline = time.time() + TIMEOUT_APP_START
        self.app = None
        last_err = None
        attempt = 0
        while time.time() < deadline:
            attempt += 1

            try:
                hs = findwindows.find_windows(class_name=ACROBAT_WINDOW_CLASS)
            except Exception as e:
                hs = []
                last_err = e
            if not hs:
                if attempt % 3 == 1:
                    self.log(f"  尝试 #{attempt}: 还没找到 AcrobatSDIWindow HWND, 等待 ...")
                time.sleep(1)
                continue

            self.log(f"  尝试 #{attempt}: 找到 HWND={hex(hs[0])}, 调用 UIA connect ...")
            try:
                self.app = Application(backend="uia").connect(handle=hs[0], timeout=2)
                self.log(f"  已 connect 到 Acrobat 进程, PID={self.app.process}")
                break
            except Exception as e:
                last_err = e
                self.log(f"  尝试 #{attempt}: UIA connect 失败 ({type(e).__name__}: {e}), 重试")
                time.sleep(1)

        if self.app is None:
            raise RuntimeError(
                f"等待 Acrobat 主窗口超时: {last_err}. "
                f"建议: 双击 kill_acrobat.bat 清干净所有 Adobe 进程后重试."
            )

        self.main_win = self.app.window(class_name=ACROBAT_WINDOW_CLASS)
        self.main_win.wait("visible ready", timeout=TIMEOUT_APP_START)
        self.log(f"主窗口标题: {self.main_win.window_text()}")

        try:
            self.main_win.set_focus()
            self.log("已 set_focus")
        except Exception as e:
            self.log(f"[警告] set_focus 失败: {e}")

        time.sleep(1.5)
        for _ in range(2):
            send_keys("{ESC}")
            time.sleep(0.3)
        self.log("Acrobat 启动准备完成 ✓")

    # ---------- Ctrl+O 打开 PDF ----------
    def open_pdf(self, pdf_path: str):
        pdf_path = os.path.normpath(pdf_path)
        self.log(f"准备打开 (规范化后): {pdf_path}")

        try:
            self.main_win.set_focus()
            self.log("open_pdf: set_focus 成功")
        except Exception as e:
            self.log(f"[警告] open_pdf set_focus 失败: {e}")

        time.sleep(0.3)
        self.log("发送 Ctrl+O ...")
        send_keys("^o")

        self.log(f"等待 '打开' 对话框 (最多 {TIMEOUT_CONTROL_READY}s) ...")
        open_dlg = None
        deadline = time.time() + TIMEOUT_CONTROL_READY
        while time.time() < deadline:
            try:
                handles = findwindows.find_windows(
                    title_re=r"^(打开|Open)$", class_name="#32770", process=self.app.process
                )
                if handles:
                    self.log(f"捕获到对话框句柄: {handles[0]}")
                    app2 = Application(backend="uia").connect(handle=handles[0])
                    open_dlg = app2.window(handle=handles[0])
                    if open_dlg.exists() and open_dlg.is_visible():
                        break
            except Exception as e:
                self.log(f"[调试] 查找对话框异常: {e}")
            time.sleep(POLL_INTERVAL)

        if open_dlg is None:
            raise PwaTimeoutError(
                "未捕获到 '打开' 对话框 — Ctrl+O 可能没被 Acrobat 接收。"
            )
        self.log("'打开' 对话框已出现 ✓")

        try:
            open_dlg.set_focus()
            self.log("对话框已 set_focus")
        except Exception as e:
            self.log(f"[警告] 对话框 set_focus 失败: {e}")

        self.log("定位文件名 Edit 控件 ...")
        edit = open_dlg.child_window(class_name="Edit", found_index=0)
        edit.wait("enabled", timeout=TIMEOUT_CONTROL_READY)
        self.log("Edit 控件已就绪, 写入路径 ...")

        try:
            edit.set_edit_text("")
            edit.set_edit_text(pdf_path)
            self.log("路径已写入 (set_edit_text)")
        except Exception as e:
            self.log(f"[警告] set_edit_text 失败 ({e}), 改用 type_keys 输入")
            edit.click_input()
            send_keys("^a")
            send_keys("{DEL}")
            from pywinauto.keyboard import send_keys as sk
            sk(pdf_path, with_spaces=True)

        self.log("发送 ENTER 确认 ...")
        send_keys("{ENTER}")

        RENDER_BUFFER = 2.0
        self.log(f"等待 '打开' 对话框关闭 + {RENDER_BUFFER}s 渲染缓冲 ...")
        deadline = time.time() + TIMEOUT_FILE_OPEN
        last_progress = 0
        dialog_closed_at = None
        while time.time() < deadline:
            try:
                dlg_alive = open_dlg.exists()
            except Exception:
                dlg_alive = False

            if not dlg_alive:
                if dialog_closed_at is None:
                    dialog_closed_at = time.time()
                    self.log("'打开' 对话框已关闭, 等待渲染 ...")
                elif time.time() - dialog_closed_at >= RENDER_BUFFER:
                    self.log("PDF 已加载 ✓")
                    return
            else:
                try:
                    err_handles = findwindows.find_windows(class_name="#32770", process=self.app.process)
                    for h in err_handles:
                        if h == open_dlg.handle:
                            continue
                        try:
                            from pywinauto.controls.hwndwrapper import HwndWrapper
                            sub = HwndWrapper(h)
                            sub_title = sub.window_text()
                            if sub_title and sub_title not in ("打开", "Open"):
                                self.log(f"[!] 检测到子对话框: title={sub_title!r}")
                        except Exception:
                            pass
                except Exception:
                    pass

            if time.time() - last_progress > 3:
                self.log(f"  [等待中] 对话框={'存活' if dlg_alive else '已关'}")
                last_progress = time.time()

            time.sleep(POLL_INTERVAL)
        raise PwaTimeoutError(f"打开 PDF 超时: {pdf_path}")

    # ---------- 通用: 真实坐标鼠标点击 (用 pywinauto.mouse, 内部走 SendInput) ----------
    def _raw_mouse_click(self, rect, label="", double=False):
        """
        点击 rect 中心. 用 pywinauto.mouse (SendInput) 而不是 mouse_event,
        SendInput 是新 API, 对 Qt 等非标准 UI 框架的兼容性远好于 mouse_event.
        double=True 时双击 (TreeItem 偶尔需要).
        """
        from pywinauto import mouse
        import ctypes
        cx = (rect.left + rect.right) // 2
        cy = (rect.top + rect.bottom) // 2
        # 先用 SetCursorPos 把鼠标挪过去, 触发 hover 状态
        ctypes.windll.user32.SetCursorPos(cx, cy)
        time.sleep(0.1)
        if double:
            mouse.double_click(button="left", coords=(cx, cy))
        else:
            mouse.click(button="left", coords=(cx, cy))
        self.log(f"  [raw_mouse] {label} {'双击' if double else '点击'}坐标 ({cx},{cy})")

    # ---------- 通用: 安全点击 (invoke 优先 + 重试) ----------
    def _safe_click(self, ctrl, label="", retries=2, force_mouse=False):
        last_err = None
        for attempt in range(1, retries + 2):
            if not force_mouse:
                try:
                    ctrl.invoke()
                    self.log(f"  [click] {label} invoke 成功 (尝试 {attempt})")
                    return
                except AttributeError:
                    pass   
                except Exception as e:
                    last_err = e
                    self.log(f"  [click] {label} invoke 失败 ({e}), 改用鼠标")

            try:
                ctrl.click_input()
                self.log(f"  [click] {label} click_input 成功 (尝试 {attempt})")
                return
            except Exception as e:
                last_err = e
                self.log(f"  [click] {label} click_input 失败 ({e})")

            if attempt <= retries:
                time.sleep(0.5)

        raise PwaTimeoutError(f"点击失败 ({label}, 已尝试 {retries + 1} 次): {last_err}")

    # ---------- 主动"刺激"右侧 task pane, 让 Acrobat 把按钮重新注入 UIA 树 ----------
    def _poke_right_task_pane(self) -> bool:
        """
        Acrobat 右侧工具窗格 (AVL_AVView) 在 UIA 上有两种态:
          - "有按钮态": descendants(Button, title='去水印') 能找到
          - "空容器态": 只有一个空 Pane (Name='右侧工具窗格' / 'AVScrollView'),
                       descendants 返回 0
        Acrobat 自己在这两种态间切换, 我们不能从 UIA 直接判断当前在哪态.
        但实测: 鼠标 hover 到面板上 + 滚动一下, 大概率能让 Acrobat 切回"有按钮态".
        本方法找到右侧 task pane 容器, 模拟 hover + 滚轮触发重画.
        成功触发返回 True, 没找到面板返回 False.
        """
        try:
            from pywinauto import mouse
            panes = self.main_win.descendants(control_type="Pane")
            for p in panes:
                try:
                    cn = p.element_info.class_name or ""
                    name = p.element_info.name or ""
                    # 匹配 Acrobat 右侧工具栏的容器 (多个名字都可能, 看 Acrobat 版本)
                    if cn == "AVL_AVView" and (
                        "工具" in name or "TaskPane" in name
                        or name == "AVScrollView" or name == "右侧工具窗格"
                    ):
                        rect = p.rectangle()
                        if rect.width() <= 0 or rect.height() <= 0:
                            continue
                        cx = (rect.left + rect.right) // 2
                        cy = (rect.top + rect.bottom) // 2
                        # 移到中心 (不点击, 避免误触发 Acrobat 工具)
                        mouse.move(coords=(cx, cy))
                        time.sleep(0.2)
                        # 上下各滚一次, 触发 Acrobat 重新渲染列表
                        mouse.scroll(coords=(cx, cy), wheel_dist=-2)
                        time.sleep(0.15)
                        mouse.scroll(coords=(cx, cy), wheel_dist=2)
                        return True
                except Exception:
                    pass
        except Exception:
            pass
        return False

    # ---------- 通用: 找一个可见的 Button 并点击 ----------
    def _click_visible_button(self, title=None, title_re=None, label_for_log=None,
                              timeout=90):
        """
        timeout 默认提到 90s. 原因: Acrobat 右侧 task pane 的 UIA 暴露是惰性的,
        20s 经常等不到按钮注入. 实测 90s 配合 _poke_right_task_pane 刺激, 成功率高得多.
        """
        import re
        label = label_for_log or title or title_re
        self.log(f"定位按钮: '{label}' (mode={'regex' if title_re else 'exact'}, timeout={timeout}s) ...")

        regex = re.compile(title_re) if title_re else None
        deadline = time.time() + timeout
        last_err = None
        empty_streak = 0   # 连续多少轮 descendants 返回 0

        while time.time() < deadline:
            try:
                if title is not None:
                    candidates = self.main_win.descendants(
                        control_type="Button", title=title
                    )
                else:
                    all_buttons = self.main_win.descendants(control_type="Button")
                    candidates = []
                    for b in all_buttons:
                        try:
                            n = b.element_info.name or ""
                            if regex.search(n):
                                candidates.append(b)
                        except Exception:
                            pass

                self.log(f"  找到 {len(candidates)} 个候选, 筛选可见的 ...")

                for idx, c in enumerate(candidates):
                    try:
                        rect = c.rectangle()
                        visible = c.is_visible()
                        offscreen = False
                        try:
                            offscreen = bool(c.element_info.element.CurrentIsOffscreen)
                        except Exception:
                            pass
                        c_name = ""
                        try:
                            c_name = c.element_info.name
                        except Exception:
                            pass
                        self.log(
                            f"  候选[{idx}]: name={c_name!r}, visible={visible}, "
                            f"offscreen={offscreen}, size={rect.width()}x{rect.height()}"
                        )
                        if visible and not offscreen and rect.width() > 0 and rect.height() > 0:
                            self._safe_click(c, label=f"'{label}'(候选[{idx}])")
                            self.log(f"已点击: '{label}' (候选[{idx}], name={c_name!r})")
                            return
                    except Exception as e:
                        self.log(f"  候选[{idx}] 检查失败: {e}")

                # 0 个候选 = Acrobat 右侧 task pane 处于"空容器态". 每 ~2s 主动刺激一次.
                if len(candidates) == 0:
                    empty_streak += 1
                    if empty_streak % 4 == 0:   # POLL_INTERVAL=0.5s, 4 轮 ≈ 2s
                        poked = self._poke_right_task_pane()
                        self.log(f"  [刺激] 第 {empty_streak} 轮空, hover+滚轮 task pane "
                                 f"(命中={poked}), 等 Acrobat 重画 ...")
                        time.sleep(1.0)
                else:
                    empty_streak = 0
            except Exception as e:
                last_err = e
                self.log(f"  [调试] descendants 查询异常: {e}")
            time.sleep(POLL_INTERVAL)

        raise PwaTimeoutError(f"未能定位到可见的 '{label}' 按钮 | 最后异常: {last_err}")

    # ---------- 点击右侧工具栏的"去水印" ----------
    def click_remove_watermark(self):
        self._click_visible_button(title=BTN_REMOVE_WATERMARK)

    # ---------- 点击"动作列表"按钮 ----------
    def click_action_list(self):
        self._click_visible_button(title_re=BTN_ACTION_LIST_RE,
                                   label_for_log="动作列表")

    # ---------- 在"动作列表"窗口中找指定名字的 TreeItem ----------
    def _find_action_dialog_and_tree_item(self, watermark_text):
        deadline = time.time() + TIMEOUT_CONTROL_READY
        last_err = None
        while time.time() < deadline:
            try:
                # 强制限定 PID，绝不跨进程
                handles = findwindows.find_windows(title=DLG_ACTION_LIST_TITLE, process=self.app.process)
                if handles:
                    app2 = Application(backend="uia").connect(handle=handles[0])
                    dlg = app2.window(handle=handles[0])
                    all_items = dlg.descendants(control_type="TreeItem")
                    for it in all_items:
                        try:
                            if (it.element_info.name or "") == watermark_text:
                                return dlg, it, all_items
                        except Exception:
                            pass
                    raise PwaTimeoutError(
                        f"在'动作列表'中找不到 TreeItem 名称='{watermark_text}'."
                    )
            except PwaTimeoutError:
                raise
            except Exception as e:
                last_err = e
            time.sleep(POLL_INTERVAL)
        raise PwaTimeoutError(f"等待'动作列表'窗口超时. 最后异常: {last_err}")

    # ---------- 单击选中指定名字的树项目 ----------
    def select_action_item(self, watermark_text):
        """
        关键: 动作列表是 Qt 窗口, UIA invoke 是 stub - invoke 报"成功"但只让 item 高亮,
        不会真触发"选中", 导致后面"开始"按钮一直 disable.
        必须用 ctypes 真实鼠标点击, 才能让 Qt 收到完整选中事件.
        """
        self.log(f"等待'{DLG_ACTION_LIST_TITLE}'窗口并选中 TreeItem='{watermark_text}' ...")
        dlg, item, all_items = self._find_action_dialog_and_tree_item(watermark_text)
        self.log(f"  找到'动作列表'窗口, 共 {len(all_items)} 个 TreeItem, 已定位目标")
        # 把动作列表窗口提前台
        try:
            dlg.set_focus()
            time.sleep(0.3)
        except Exception as e:
            self.log(f"  [警告] 动作列表 set_focus 失败: {e}")
        # 直接真实鼠标点击 TreeItem 中心
        rect = item.rectangle()
        self._raw_mouse_click(rect, label=f"TreeItem '{watermark_text}'")
        self.log(f"已选中树项目: '{watermark_text}'")
        self._action_dlg = dlg

    # ---------- 进程名查询 (用于过滤误命中浏览器/编辑器等非 Acrobat 进程) ----------
    def _get_proc_name_by_pid(self, pid):
        """通过 PID 反查进程名 (小写). 失败返回空串. 用缓存避免反复系统调用."""
        if not hasattr(self, "_proc_name_cache"):
            self._proc_name_cache = {}
        if pid in self._proc_name_cache:
            return self._proc_name_cache[pid]
        import ctypes
        from ctypes import wintypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        k32 = ctypes.windll.kernel32
        k32.OpenProcess.restype = wintypes.HANDLE
        h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        name = ""
        if h:
            try:
                buf = ctypes.create_unicode_buffer(1024)
                size = wintypes.DWORD(1024)
                if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                    name = os.path.basename(buf.value).lower()
            finally:
                k32.CloseHandle(h)
        self._proc_name_cache[pid] = name
        return name

    def _is_acrobat_pid(self, pid):
        """判断 pid 是否属于 Acrobat 进程家族 (Acrobat.exe / AcroCEF.exe / AcroBroker.exe ...)."""
        if not pid:
            return False
        n = self._get_proc_name_by_pid(pid)
        return ("acro" in n) or ("adobe" in n)

    # ---------- 用 win32 EnumWindows 快速拿到 Acrobat 系列进程的可见顶层 hwnd 列表 ----------
    def _enum_acrobat_hwnds(self):
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL

        result = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def _cb(hwnd, lparam):
            try:
                if not user32.IsWindowVisible(hwnd):
                    return True
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if self._is_acrobat_pid(pid.value):
                    result.append((hwnd, pid.value))
            except Exception:
                pass
            return True

        try:
            user32.EnumWindows(_cb, 0)
        except Exception:
            pass
        return result

    # ---------- 保存按钮状态检测 (动作执行时它会变灰, 完成后恢复) ----------
    def _find_save_button(self):
        """
        在 main_win 里找工具栏的"保存"按钮.
        特征 (来自 inspect): Name='保存', ControlType=Button, Size=24x24, HelpText 含 'Ctrl+S'.
        Acrobat 可能多处有"保存"同名元素 (如菜单), 用 size 过滤工具栏那个.
        """
        try:
            cands = self.main_win.descendants(title="保存", control_type="Button")
        except Exception:
            return None
        for c in cands:
            try:
                if not c.is_visible():
                    continue
                rect = c.rectangle()
                # 工具栏保存按钮稳定 24x24, 给点容错 20-32
                if 20 <= rect.width() <= 32 and 20 <= rect.height() <= 32:
                    return c
            except Exception:
                continue
        # 退路: 没匹配 size 的就返第一个 visible
        for c in cands:
            try:
                if c.is_visible():
                    return c
            except Exception:
                continue
        return None

    def _save_button_enabled(self):
        """返回 True/False/None. None 表示找不到按钮 (无法判定)."""
        btn = self._find_save_button()
        if btn is None:
            return None
        try:
            return bool(btn.is_enabled())
        except Exception:
            try:
                return bool(btn.element_info.enabled)
            except Exception:
                return None

    # ---------- 进度面板检测 (混合策略: hwnd 形状 + UIA Text) ----------
    def _progress_panel_hwnd_present(self, debug=False):
        """
        策略 A (主): 找 class_name='AVL_AVWindow' + size 接近 224x93 的可见窗口.
        这是 GDI 绘制的浮动小面板, hwnd 一定存在, 比 UIA Text 检测靠谱得多.
        Acrobat 其他面板也是这个 class, 用 size 范围过滤.
        """
        try:
            hs = findwindows.find_windows(
                class_name="AVL_AVWindow", visible_only=True
            )
        except Exception:
            return False
        from pywinauto.controls.hwndwrapper import HwndWrapper
        for h in hs:
            try:
                w = HwndWrapper(h)
                rect = w.rectangle()
                # 进度面板典型 size 224x93, 给宽容范围
                if 150 <= rect.width() <= 350 and 60 <= rect.height() <= 150:
                    if debug:
                        self.log(
                            f"  [debug] [策略A] AVL_AVWindow hwnd=0x{h:X} "
                            f"size={rect.width()}x{rect.height()} -> 视为进度面板"
                        )
                    return True
            except Exception:
                continue
        return False

    def _progress_text_present(self, debug=False, max_seconds=2.0):
        """
        组合检测: 优先 hwnd 形状 (快, 100% 可靠), 兜底再用 UIA Text 全局搜.
        """
        # 策略 A: hwnd + class + size (毫秒级, 不依赖 UIA)
        if self._progress_panel_hwnd_present(debug=debug):
            return True

        # 策略 B (兜底): UIA Text 'Acrobat 系列进程窗口' 下找
        start = time.time()
        acro_hwnds = self._enum_acrobat_hwnds()
        if debug:
            self.log(f"  [debug] [策略B] EnumWindows: {len(acro_hwnds)} 个 Acrobat 系列可见窗口")
        for hwnd, pid in acro_hwnds:
            if time.time() - start > max_seconds:
                if debug:
                    self.log(f"  [debug] 单次检测超时 {max_seconds}s, 提前返回")
                return False
            try:
                app = Application(backend="uia").connect(handle=hwnd, timeout=1)
                win = app.window(handle=hwnd)
                elems = win.descendants(
                    title=ACTION_PROGRESS_TEXT, control_type="Text"
                )
                if elems:
                    if debug:
                        wt = ""
                        try:
                            wt = win.window_text()
                        except Exception:
                            pass
                        self.log(f"  [debug] [策略B] 命中: hwnd=0x{hwnd:X} pid={pid} title='{wt}'")
                    return True
            except Exception:
                continue
        return False

    def wait_for_action_done(self, timeout=TIMEOUT_ACTION_RUN):
        """
        简化策略: 直接轮询保存按钮的 enable 状态, 等它变为 True 即视为动作完成.
        进入此方法前 click_start_button 的 verify 已经确认按钮变灰, 所以这里只需等恢复.
        """
        self.log(f"轮询保存按钮 enable 状态 (最多 {timeout}s) ...")
        deadline = time.time() + timeout
        start_t = time.time()
        last_log = 0
        while time.time() < deadline:
            st = self._save_button_enabled()
            if st is True:
                elapsed = int(time.time() - start_t)
                self.log(f"✓ 保存按钮可用, 动作完成 (耗时 {elapsed}s)")
                return
            if time.time() - last_log > 5:
                tag = "找不到按钮" if st is None else "enabled=False"
                self.log(f"  [执行中] 已等待 {int(time.time() - start_t)}s ({tag})")
                last_log = time.time()
            time.sleep(0.5)
        raise PwaTimeoutError(f"动作执行超时 ({timeout}s 内保存按钮未恢复 enable)")

    # ---------- 点击"开始"按钮 (无名图标按钮, trial-and-verify) ----------
    def _collect_start_button_candidates(self):
        candidates = []
        roots = []
        if getattr(self, "_action_dlg", None) is not None:
            roots.append(("动作列表", self._action_dlg))
        try:
            from pywinauto import Desktop
            # 同样限定 PID
            for w in Desktop(backend="uia").windows(process=self.app.process, visible_only=True):
                try:
                    wt = w.window_text() or "(no-title)"
                    if wt == "动作列表":
                        continue
                    roots.append((wt, w))
                except Exception:
                    pass
        except Exception:
            pass

        for label, root in roots:
            try:
                for b in root.descendants(control_type="Button"):
                    try:
                        if (b.element_info.name or "") != "":
                            continue
                        if not b.is_visible():
                            continue
                        try:
                            if bool(b.element_info.element.CurrentIsOffscreen):
                                continue
                        except Exception:
                            pass
                        rect = b.rectangle()
                        if not (30 <= rect.width() <= 80 and 30 <= rect.height() <= 80):
                            continue
                        candidates.append((b, rect, label))
                    except Exception:
                        pass
            except Exception:
                pass

        seen = set()
        unique = []
        for b, rect, label in candidates:
            key = (rect.left, rect.top, rect.right, rect.bottom)
            if key in seen:
                continue
            seen.add(key)
            unique.append((b, rect, label))
        return unique

    def click_start_button(self):
        self.log("定位'开始'按钮 (trial-and-verify 模式) ...")

        gather_deadline = time.time() + 5
        unique = []
        while time.time() < gather_deadline:
            unique = self._collect_start_button_candidates()
            if unique:
                break
            time.sleep(0.5)
        if not unique:
            raise PwaTimeoutError("找不到符合特征的'开始'按钮候选 (无名+30~80px)")

        unique.sort(key=lambda x: x[1].top + x[1].left, reverse=True)
        self.log(f"  共 {len(unique)} 个候选, 按位置排序后挨个 trial:")
        
        # 只取最右下候选 (开始按钮)
        target, rect, label = unique[0]
        cx = (rect.left + rect.right) // 2
        cy = (rect.top + rect.bottom) // 2
        self.log(f"  目标: win='{label}' rect=({rect.left},{rect.top},{rect.right},{rect.bottom}) center=({cx},{cy})")

        # ★ Qt 窗口 (Qt5QWindowToolSaveBits) 的 UIA InvokePattern 经常是 stub,
        # invoke 报成功但不真触发. 所以多管齐下, 每种方式点完都验证一次进度面板.

        def _bring_dlg_front():
            try:
                if getattr(self, "_action_dlg", None) is not None:
                    self._action_dlg.set_focus()
                    time.sleep(0.3)
            except Exception:
                pass

        def _method_invoke():
            target.invoke()

        def _method_enter_after_focus():
            target.set_focus()
            time.sleep(0.2)
            send_keys("{ENTER}")

        def _method_raw_mouse():
            """用 pywinauto.mouse (SendInput) 真实坐标点击, 对 Qt 等兼容性最好."""
            self._raw_mouse_click(rect, label="'开始'按钮")

        def _method_click_input():
            target.click_input()

        # ★ 经实测顺序: ctypes 真实坐标最可靠 (Qt 窗口不响应 UIA invoke + click_input),
        # 把它放第一位避免每次都从前面 3 个无效方式跑过.
        methods = [
            ("ctypes 真实坐标点击",   _method_raw_mouse),
            ("SetFocus + Enter键",    _method_enter_after_focus),
            ("UIA invoke",            _method_invoke),
            ("pywinauto click_input", _method_click_input),
        ]

        for method_name, method_func in methods:
            _bring_dlg_front()
            self.log(f"  >>> 尝试方式: {method_name}")
            try:
                method_func()
            except Exception as e:
                self.log(f"    {method_name} 异常: {e}, 试下一种")
                continue

            # 验证: 5 秒内"进度面板出现"或"保存按钮变灰", 任一为真即算真触发
            verify_deadline = time.time() + 5
            triggered_by = None
            while time.time() < verify_deadline:
                if self._progress_text_present():
                    triggered_by = "进度面板出现"
                    break
                if self._save_button_enabled() is False:
                    triggered_by = "保存按钮变灰"
                    break
                time.sleep(0.3)
            if triggered_by:
                self.log(f"✓ {method_name} 真正触发了动作 (信号: {triggered_by})")
                return
            self.log(f"    {method_name} 未触发任何信号, 试下一种")

        # 4 种都没触发, 不抛错让流程继续, 但明确警告
        self.log("⚠ 4 种点击方式都未触发进度面板. 可能动作执行极快, 或按钮真没被点中.")

    # ---------- 处理确认弹窗 ----------
    def handle_confirm_dialog(self):
        self.log("等待确认弹窗 ...")
        deadline = time.time() + TIMEOUT_CONTROL_READY
        while time.time() < deadline:
            for btn_name in (BTN_CONFIRM_YES, BTN_CONFIRM_OK, "OK", "Yes", "确定"):
                try:
                    # 也可以限定 PID 以防万一
                    ctrl = self.main_win.child_window(
                        title=btn_name, control_type="Button"
                    )
                    if ctrl.exists() and ctrl.is_visible():
                        ctrl.wait("enabled", timeout=2)
                        ctrl.click_input()
                        self.log(f"确认弹窗已点击: {btn_name}")
                        return
                except Exception:
                    continue
            time.sleep(POLL_INTERVAL)

        self.log("未找到具名确认按钮, 用 Enter 兜底")
        send_keys("{ENTER}")

    # ---------- 保存 + 关闭 ----------
    def save_and_close(self, pdf_path: str):
        """
        保存 + 关闭. 全程容错: 大 PDF 动作完成后 main_win 引用可能失效
        (Acrobat 内部 reload), set_focus 会抛 ElementNotFoundError -
        所以所有 main_win 操作都包 silent try, 让快捷键尽力发出去.
        """
        def _silent_set_focus():
            try:
                self.main_win.set_focus()
            except Exception as e:
                self.log(f"[警告] main_win.set_focus 失败 (已忽略): {type(e).__name__}")

        # 1) 优先点击工具栏保存按钮 (invoke 不依赖 set_focus)
        self.log("尝试点击工具栏'保存'按钮 ...")
        btn = self._find_save_button()
        saved = False
        if btn is not None:
            try:
                self._safe_click(btn, label="'保存'按钮")
                saved = True
            except Exception as e:
                self.log(f"[警告] 点击保存按钮失败 ({e})")
        else:
            self.log("[警告] 找不到保存按钮")

        # 2) 没点上 -> Ctrl+S 兜底
        if not saved:
            self.log("Ctrl+S 兜底保存 ...")
            _silent_set_focus()
            try:
                send_keys("^s")
            except Exception as e:
                self.log(f"[警告] send_keys ^s 失败: {e}")

        # 3) 等保存完成 (可能有 '另存为' 对话框, 大文件需要落盘时间)
        time.sleep(1.5)

        # 4) Ctrl+W 关闭文档
        self.log("Ctrl+W 关闭文档 ...")
        _silent_set_focus()
        try:
            send_keys("^w")
        except Exception as e:
            self.log(f"[警告] send_keys ^w 失败: {e}")
        time.sleep(1.0)
        self.log("文档已关闭")

    # ---------- 杀光所有 Adobe 相关进程 (确保下一轮干净环境) ----------
    def kill_acrobat(self):
        import subprocess
        targets = [
            "Acrobat.exe", "AcroCEF.exe", "acrotray.exe",
            "AdobeIPCBroker.exe", "AdobeARM.exe", "acrord32.exe",
            "AcroBroker.exe",
        ]
        killed = []
        for name in targets:
            try:
                r = subprocess.run(
                    ["taskkill", "/F", "/IM", name],
                    capture_output=True, timeout=5,
                )
                if r.returncode == 0:
                    killed.append(name)
            except Exception:
                pass
        if killed:
            self.log(f"✓ 已杀掉 Adobe 进程: {', '.join(killed)}")
        else:
            self.log("  (无 Adobe 进程需要清理)")

    # ---------- 应急恢复 ----------
    def emergency_recover(self):
        self.log("[应急] 连发 ESC + Ctrl+W")
        try:
            self.main_win.set_focus()
        except Exception:
            pass
        for _ in range(5):
            send_keys("{ESC}")
            time.sleep(0.3)
        send_keys("^w")
        time.sleep(0.5)

    # ---------- 一键执行完整流程 ----------
    def run(self, pdf_path: str, watermark_text: str):
        try:
            self.launch()
            self.open_pdf(pdf_path)
            self.click_remove_watermark()
            self.log("等待去水印工具面板渲染 (3s) ...")
            time.sleep(3)
            self.click_action_list()
            self.select_action_item(watermark_text)
            time.sleep(0.5)
            self.click_start_button()
            self.wait_for_action_done()         # 等保存按钮变可用 = 动作完成
            self.save_and_close(pdf_path)       # 点击保存按钮 + Ctrl+W 关闭
            self.log("✓ 当前 PDF 自动化流程全部完成！")
        finally:
            # 无论成功失败, 都杀光 Acrobat 进程, 保证下一轮干净环境
            self.log("清理: 关闭所有 Adobe 进程 ...")
            self.kill_acrobat()


# =====================================================================
# 【tkinter GUI】
# =====================================================================

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Acrobat DC 去水印 - 最小版")
        self.geometry("640x460")

        self.log_queue = queue.Queue()
        self._build_ui()
        self._poll_log_queue()

    def _build_ui(self):
        pad = {"padx": 8, "pady": 6}

        frame_top = ttk.Frame(self)
        frame_top.pack(fill="x", **pad)
        ttk.Label(frame_top, text="PDF 文件:").pack(side="left")
        self.var_path = tk.StringVar()
        ttk.Entry(frame_top, textvariable=self.var_path).pack(
            side="left", fill="x", expand=True, padx=6
        )
        ttk.Button(frame_top, text="选择...", command=self._on_choose).pack(side="left")

        frame_wm = ttk.Frame(self)
        frame_wm.pack(fill="x", **pad)
        ttk.Label(frame_wm, text="水印文字:").pack(side="left")
        self.var_watermark = tk.StringVar(value=DEFAULT_WATERMARK_TEXT)
        ttk.Entry(frame_wm, textvariable=self.var_watermark).pack(
            side="left", fill="x", expand=True, padx=6
        )
        ttk.Label(frame_wm, text="(必须与'动作列表'里的某个动作名一致)").pack(side="left")

        frame_btn = ttk.Frame(self)
        frame_btn.pack(fill="x", **pad)
        self.btn_run = ttk.Button(
            frame_btn, text="开始去水印", command=self._on_run
        )
        self.btn_run.pack(side="left")
        ttk.Button(frame_btn, text="清空日志", command=self._clear_log).pack(side="left", padx=6)

        ttk.Label(self, text="运行日志:").pack(anchor="w", padx=8)
        self.txt_log = tk.Text(self, height=18, wrap="word", state="disabled")
        self.txt_log.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        sb = ttk.Scrollbar(self.txt_log, command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")

    def _on_choose(self):
        path = filedialog.askopenfilename(
            title="选择 PDF 文件",
            filetypes=[("PDF 文件", "*.pdf"), ("所有文件", "*.*")],
        )
        if path:
            self.var_path.set(path)

    def _on_run(self):
        pdf = self.var_path.get().strip().strip('"')
        if not pdf:
            messagebox.showwarning("提示", "请先选择 PDF 文件")
            return
        if not os.path.isfile(pdf):
            messagebox.showerror("错误", f"文件不存在:\n{pdf}")
            return

        watermark = self.var_watermark.get().strip()
        if not watermark:
            messagebox.showwarning("提示", "请输入水印文字 (动作列表中对应的项名)")
            return

        self.btn_run.config(state="disabled")
        self._log("=" * 50)
        self._log(f"开始处理: {pdf}")
        self._log(f"水印文字: {watermark}")

        t = threading.Thread(target=self._worker_thread, args=(pdf, watermark), daemon=True)
        t.start()

    def _worker_thread(self, pdf: str, watermark: str):
        worker = AcrobatWorker(log_func=self._log)
        try:
            worker.run(pdf, watermark)
        except Exception as e:
            self._log(f"✘ 失败: {e}")
            self._log(traceback.format_exc())
            try:
                worker.emergency_recover()
            except Exception:
                pass
        finally:
            self.after(0, lambda: self.btn_run.config(state="normal"))

    def _log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self.log_queue.put(f"[{ts}] {msg}")

    def _poll_log_queue(self):
        try:
            while True:
                line = self.log_queue.get_nowait()
                self.txt_log.config(state="normal")
                self.txt_log.insert("end", line + "\n")
                self.txt_log.see("end")
                self.txt_log.config(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self._poll_log_queue)

    def _clear_log(self):
        self.txt_log.config(state="normal")
        self.txt_log.delete("1.0", "end")
        self.txt_log.config(state="disabled")


# =====================================================================
# 【入口】
# =====================================================================

if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    App().mainloop()