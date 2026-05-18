# -*- coding: utf-8 -*-
"""
=====================================================================
 Acrobat 批量去水印 GUI - 基于 acrobat_gui_min.AcrobatWorker
=====================================================================
 功能:
   - 文件夹扫描 + 列表勾选 (默认全选, 可单选/全选/全不选)
   - 单文件硬超时 180s, 超时自动 kill Acrobat 跳下一个
   - 连续 3 个文件同阶段失败 / 5 个总失败 -> 自动暂停提示用户
   - CSV 实时追加报告 (崩溃也不丢)
   - 暂停 / 跳过当前 / 终止控制
   - 顶部红色横幅 "请勿操作鼠标键盘"
=====================================================================
"""

import os
import sys
import csv
import time
import queue
import threading
import traceback
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, List, Callable

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from acrobat_gui_min import AcrobatWorker, DEFAULT_WATERMARK_TEXT


# =====================================================================
# 【配置】
# =====================================================================
PER_FILE_TIMEOUT          = 300   # 单文件硬超时 (秒) - 大 PDF (100MB+) 建议 300-600
CONSECUTIVE_SAME_STAGE    = 3     # 连续同阶段失败 -> 自动暂停
CONSECUTIVE_TOTAL_FAIL    = 5     # 连续失败 (任何阶段) -> 自动暂停
EST_SEC_PER_FILE          = 25    # 预估耗时 (用于开始前提示)

# REPORT_DIR 必须用绝对路径 (相对 exe 或脚本自身).
# 否则 PyInstaller 打包后用户双击 exe 时, cwd 可能是别处, 写报告会 PermissionError.
def _resolve_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

REPORT_DIR = os.path.join(_resolve_base_dir(), "reports")


# =====================================================================
# 【单文件结果】
# =====================================================================
@dataclass
class PdfResult:
    file_path: str
    file_size_kb: int = 0
    status: str = "pending"          # success / failed / skipped / timeout
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    duration_sec: float = 0.0
    error_stage: Optional[str] = None
    error_message: Optional[str] = None


# =====================================================================
# 【批量调度器】(线程安全, 自身在子线程里跑)
# =====================================================================
class BatchRunner:
    def __init__(self,
                 on_log: Callable[[str], None],
                 on_progress: Callable[[int, int, str], None],
                 on_result: Callable[[PdfResult], None],
                 per_file_timeout: int = PER_FILE_TIMEOUT):
        self.on_log = on_log
        self.on_progress = on_progress
        self.on_result = on_result
        self.per_file_timeout = per_file_timeout
        self._stop_flag = False
        self._pause_flag = False
        self._skip_flag = False
        self._current_worker: Optional[AcrobatWorker] = None

    # --- 控制 ---
    def stop(self):         self._stop_flag = True
    def pause(self):        self._pause_flag = True
    def resume(self):       self._pause_flag = False
    def skip_current(self): self._skip_flag = True
    def is_paused(self):    return self._pause_flag

    # --- 主流程 ---
    def run(self, pdf_list: List[str], watermark: str) -> str:
        """串行处理所有 PDF, 返回 CSV 报告路径."""
        report_path = self._create_report_file()
        self.on_log(f"报告文件: {report_path}")
        consecutive_fails: List[PdfResult] = []

        for i, pdf in enumerate(pdf_list):
            if self._stop_flag:
                self.on_log("[终止] 用户停止批量处理")
                break

            # 暂停轮询
            paused_msg_shown = False
            while self._pause_flag and not self._stop_flag:
                if not paused_msg_shown:
                    self.on_log("[暂停中] 等待用户点击'继续' ...")
                    paused_msg_shown = True
                time.sleep(0.5)
            if self._stop_flag:
                break

            self._skip_flag = False
            self.on_progress(i, len(pdf_list), pdf)
            self.on_log(f"\n{'='*60}\n[{i+1}/{len(pdf_list)}] {pdf}\n{'='*60}")

            result = self._run_one_with_timeout(pdf, watermark)
            self._append_csv_row(report_path, i + 1, result)
            self.on_result(result)
            self.on_log(
                f"[{i+1}/{len(pdf_list)}] {result.status.upper()} "
                f"耗时 {result.duration_sec}s"
                + (f" | 失败阶段: {result.error_stage} | {result.error_message}"
                   if result.status != "success" else "")
            )

            # 连续失败判定 -> 自动暂停
            if result.status == "success":
                consecutive_fails.clear()
            else:
                consecutive_fails.append(result)
                if len(consecutive_fails) >= CONSECUTIVE_TOTAL_FAIL:
                    self._pause_flag = True
                    self.on_log(
                        f"\n⚠⚠⚠ 已连续 {CONSECUTIVE_TOTAL_FAIL} 个文件失败! "
                        f"自动暂停, 请检查 Acrobat / 动作配置后点'继续'.\n"
                    )
                elif len(consecutive_fails) >= CONSECUTIVE_SAME_STAGE:
                    last = consecutive_fails[-CONSECUTIVE_SAME_STAGE:]
                    if all(r.error_stage == last[0].error_stage for r in last):
                        self._pause_flag = True
                        self.on_log(
                            f"\n⚠⚠⚠ 已连续 {CONSECUTIVE_SAME_STAGE} 个文件在 "
                            f"'{last[0].error_stage}' 失败! 自动暂停, "
                            f"建议检查 Acrobat UI 是否变化.\n"
                        )

        self.on_log(f"\n报告已保存: {report_path}")
        return report_path

    # --- 单文件执行 + 硬超时 ---
    def _run_one_with_timeout(self, pdf: str, watermark: str) -> PdfResult:
        result = PdfResult(file_path=pdf)
        try:
            result.file_size_kb = max(1, int(os.path.getsize(pdf) / 1024))
        except Exception:
            pass
        result.start_at = datetime.now()

        worker = AcrobatWorker(log_func=self.on_log)
        self._current_worker = worker

        worker_state = {"exc": None, "tb": ""}

        def _target():
            try:
                worker.run(pdf, watermark)
            except Exception as e:
                worker_state["exc"] = e
                worker_state["tb"] = traceback.format_exc()

        t = threading.Thread(target=_target, daemon=True)
        t.start()

        deadline = time.time() + self.per_file_timeout
        early_exit = False
        while t.is_alive():
            if time.time() > deadline:
                result.status = "timeout"
                result.error_stage = "global_timeout"
                result.error_message = f"单文件超过 {self.per_file_timeout}s 未完成"
                self.on_log(f"[硬超时] 触发 {self.per_file_timeout}s 上限, 强杀 Acrobat")
                try: worker.kill_acrobat()
                except Exception: pass
                t.join(timeout=10)
                early_exit = True
                break
            if self._skip_flag:
                result.status = "skipped"
                result.error_stage = "user_skip"
                result.error_message = "用户手动跳过"
                self.on_log("[跳过] 用户跳过当前文件, 强杀 Acrobat")
                try: worker.kill_acrobat()
                except Exception: pass
                t.join(timeout=10)
                early_exit = True
                break
            if self._stop_flag:
                # 整批终止: 当前文件也算作 skipped
                result.status = "skipped"
                result.error_stage = "user_stop"
                result.error_message = "用户终止整批"
                try: worker.kill_acrobat()
                except Exception: pass
                t.join(timeout=10)
                early_exit = True
                break
            time.sleep(0.5)

        # 子线程自然结束 (没超时/skip/stop)
        if not early_exit:
            if worker_state["exc"] is not None:
                result.status = "failed"
                result.error_message = str(worker_state["exc"])[:200]
                result.error_stage = self._guess_stage(worker_state["tb"])
            else:
                result.status = "success"

        result.end_at = datetime.now()
        result.duration_sec = round(
            (result.end_at - result.start_at).total_seconds(), 1
        )

        # 双保险 kill (worker.run 的 finally 已经 kill 一次, 这里再保证一次)
        try: worker.kill_acrobat()
        except Exception: pass

        self._current_worker = None
        return result

    def _guess_stage(self, tb: str) -> str:
        """从 traceback 反推失败发生在哪一步."""
        keywords = [
            "save_and_close", "wait_for_action_done", "click_start_button",
            "select_action_item", "click_action_list", "click_remove_watermark",
            "open_pdf", "launch",
        ]
        for line in reversed(tb.splitlines()):
            for kw in keywords:
                if kw in line:
                    return kw
        return "unknown"

    def _create_report_file(self) -> str:
        Path(REPORT_DIR).mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = str(Path(REPORT_DIR) / f"batch_{ts}.csv")
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerow([
                "序号", "文件路径", "大小KB", "状态",
                "开始时间", "结束时间", "耗时(秒)",
                "失败阶段", "失败原因",
            ])
        return path

    def _append_csv_row(self, path: str, idx: int, r: PdfResult):
        with open(path, "a", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerow([
                idx, r.file_path, r.file_size_kb, r.status,
                r.start_at.strftime("%Y-%m-%d %H:%M:%S") if r.start_at else "",
                r.end_at.strftime("%Y-%m-%d %H:%M:%S") if r.end_at else "",
                r.duration_sec,
                r.error_stage or "",
                r.error_message or "",
            ])


# =====================================================================
# 【GUI】
# =====================================================================
class BatchApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Acrobat 批量去水印")
        self.geometry("960x780")

        self.log_queue = queue.Queue()
        self.ui_queue = queue.Queue()
        self.runner: Optional[BatchRunner] = None
        self.runner_thread: Optional[threading.Thread] = None
        self.pdf_list: List[str] = []
        self.results: List[PdfResult] = []
        self.batch_start_time: Optional[float] = None

        self._build_ui()
        self._poll_queues()

    # --------------------------- UI 构建 ---------------------------
    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}

        # ---- 顶部状态横幅 (始终显示, 切换颜色/文字) ----
        self.banner = tk.Label(
            self, text="✓ 空闲 (可以正常使用电脑)",
            bg="#cccccc", fg="#444444",
            font=("Microsoft YaHei", 11),
        )
        self.banner.pack(side="top", fill="x")

        # ---- 输入文件夹 ----
        f = ttk.Frame(self); f.pack(fill="x", **pad)
        ttk.Label(f, text="输入文件夹:").pack(side="left")
        self.var_folder = tk.StringVar()
        ent = ttk.Entry(f, textvariable=self.var_folder)
        ent.pack(side="left", fill="x", expand=True, padx=6)
        ent.bind("<Return>", self._on_path_enter)   # 按 Enter 直接扫描
        ttk.Button(f, text="选择...", command=self._on_choose_folder).pack(side="left")
        ttk.Button(f, text="扫描", command=self._on_path_enter).pack(side="left", padx=2)

        # ---- 水印文字 + 超时配置 ----
        f = ttk.Frame(self); f.pack(fill="x", **pad)
        ttk.Label(f, text="水印文字:").pack(side="left")
        self.var_watermark = tk.StringVar(value=DEFAULT_WATERMARK_TEXT)
        ttk.Entry(f, textvariable=self.var_watermark, width=20).pack(side="left", padx=6)

        ttk.Label(f, text="单文件超时(秒):").pack(side="left", padx=(20, 0))
        self.var_timeout = tk.StringVar(value=str(PER_FILE_TIMEOUT))
        ttk.Entry(f, textvariable=self.var_timeout, width=6).pack(side="left", padx=4)
        ttk.Label(f, text="(大 PDF 建议 600+)",
                  foreground="#666").pack(side="left")

        # ---- PDF 列表 (Treeview 模拟 CheckListbox) ----
        f = ttk.LabelFrame(self, text="PDF 列表 (点击 ☑/☐ 切换勾选)")
        f.pack(fill="both", expand=False, padx=8, pady=4)

        lf = ttk.Frame(f); lf.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            lf, columns=("size", "status"),
            show="tree headings", selectmode="none", height=7
        )
        self.tree.heading("#0", text="文件")
        self.tree.heading("size", text="大小")
        self.tree.heading("status", text="状态")
        self.tree.column("#0", width=560)
        self.tree.column("size", width=80, anchor="e")
        self.tree.column("status", width=120, anchor="center")
        self.tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(lf, orient="vertical", command=self.tree.yview)
        sb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<Double-Button-1>", lambda e: "break")

        # 状态颜色 tag
        self.tree.tag_configure("success", foreground="#1a8a1a")
        self.tree.tag_configure("failed", foreground="#cc0000")
        self.tree.tag_configure("timeout", foreground="#cc6600")
        self.tree.tag_configure("skipped", foreground="#888888")

        bf = ttk.Frame(f); bf.pack(fill="x")
        ttk.Button(bf, text="全选",  command=self._select_all).pack(side="left")
        ttk.Button(bf, text="全不选", command=self._select_none).pack(side="left", padx=4)
        ttk.Button(bf, text="反选",   command=self._select_invert).pack(side="left")
        self.lbl_summary = ttk.Label(bf, text="未选择文件夹")
        self.lbl_summary.pack(side="right", padx=8)

        # ---- 控制按钮 ----
        f = ttk.Frame(self); f.pack(fill="x", **pad)
        self.btn_start = ttk.Button(f, text="▶ 开始批量处理", command=self._on_start)
        self.btn_start.pack(side="left")
        self.btn_pause = ttk.Button(f, text="⏸ 暂停", command=self._on_pause, state="disabled")
        self.btn_pause.pack(side="left", padx=4)
        self.btn_skip  = ttk.Button(f, text="⏭ 跳过当前", command=self._on_skip, state="disabled")
        self.btn_skip.pack(side="left", padx=4)
        self.btn_stop  = ttk.Button(f, text="⏹ 终止", command=self._on_stop, state="disabled")
        self.btn_stop.pack(side="left", padx=4)

        # ---- 进度 ----
        f = ttk.Frame(self); f.pack(fill="x", **pad)
        self.var_progress = tk.StringVar(value="未开始")
        ttk.Label(f, textvariable=self.var_progress).pack(side="left")
        self.pb = ttk.Progressbar(self, mode="determinate")
        self.pb.pack(fill="x", padx=8)

        # ---- 日志 ----
        ttk.Label(self, text="日志:").pack(anchor="w", padx=8)
        lf = ttk.Frame(self); lf.pack(fill="both", expand=True, padx=8, pady=4)
        self.txt_log = tk.Text(lf, height=14, wrap="word", state="disabled")
        self.txt_log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(lf, command=self.txt_log.yview)
        sb.pack(side="right", fill="y")
        self.txt_log.configure(yscrollcommand=sb.set)

    # --------------------------- 文件夹扫描 ---------------------------
    def _on_choose_folder(self):
        """
        用 Win32 Shell.BrowseForFolder 替代 filedialog.askdirectory.
        原因: Tk 8.6 在 Windows 11 / 中文系统上 askdirectory 偶发挂死.
        Shell.BrowseForFolder 是几十年的老 API, 极其稳定.
        """
        print("[DEBUG] _on_choose_folder 触发, 调用 Shell.BrowseForFolder ...", flush=True)
        self._log("打开文件夹选择 ...")
        folder = None
        try:
            from win32com.client import Dispatch
            shell = Dispatch("Shell.Application")
            # 第1个 0=hWnd, 第3个 0=root (桌面), 第4个 0=BIF_RETURNONLYFSDIRS
            f = shell.BrowseForFolder(0, "选择输入文件夹 (PDF 所在目录)", 0, 0)
            if f is not None:
                folder = f.Self.Path
        except Exception as e:
            print(f"[DEBUG] BrowseForFolder 异常: {e}", flush=True)
            self._log(f"[错误] {e}")
            messagebox.showerror("错误", f"打开文件夹对话框失败:\n{e}\n\n"
                                       "可改为直接在 Entry 框里粘贴路径后按 Enter.")
            return
        print(f"[DEBUG] BrowseForFolder 返回: {folder!r}", flush=True)
        if not folder:
            self._log("已取消选择")
            return
        self.var_folder.set(folder)
        self._scan_folder(folder)

    def _on_path_enter(self, event=None):
        """让用户能直接在 Entry 里输路径按 Enter 扫描, 完全绕过对话框."""
        folder = self.var_folder.get().strip().strip('"')
        if not folder or not Path(folder).is_dir():
            messagebox.showwarning("提示", f"路径无效或不是文件夹:\n{folder}")
            return
        self._scan_folder(folder)

    def _scan_folder(self, folder: str):
        print(f"[DEBUG] 扫描文件夹: {folder}", flush=True)
        self._log(f"扫描文件夹: {folder}")
        self.tree.delete(*self.tree.get_children())
        try:
            self.pdf_list = sorted([
                str(p.resolve()) for p in Path(folder).iterdir()
                if p.is_file() and p.suffix.lower() == ".pdf"
            ])
        except Exception as e:
            self._log(f"[错误] 扫描失败: {e}")
            messagebox.showerror("错误", f"扫描文件夹失败: {e}")
            return
        for p in self.pdf_list:
            try:
                size_kb = max(1, int(os.path.getsize(p) / 1024))
            except Exception:
                size_kb = 0
            self.tree.insert(
                "", "end", iid=p,
                text=f"☑ {Path(p).name}",
                values=(f"{size_kb} KB", ""),
            )
        self._update_summary()
        self._log(f"扫描完成: 共 {len(self.pdf_list)} 个 PDF")
        print(f"[DEBUG] 扫描完成, {len(self.pdf_list)} 个 PDF", flush=True)

    # --------------------------- 勾选交互 ---------------------------
    def _on_tree_click(self, event):
        # 只对 #0 列 (文件名列) 起作用
        region = self.tree.identify_region(event.x, event.y)
        if region != "tree":
            return
        item = self.tree.identify_row(event.y)
        if not item: return
        self._toggle_item(item)

    def _toggle_item(self, iid: str):
        text = self.tree.item(iid, "text")
        if text.startswith("☑"):
            self.tree.item(iid, text="☐" + text[1:])
        elif text.startswith("☐"):
            self.tree.item(iid, text="☑" + text[1:])
        self._update_summary()

    def _select_all(self):
        for iid in self.tree.get_children():
            text = self.tree.item(iid, "text")
            if not text.startswith("☑"):
                self.tree.item(iid, text="☑" + text[1:])
        self._update_summary()

    def _select_none(self):
        for iid in self.tree.get_children():
            text = self.tree.item(iid, "text")
            if text.startswith("☑"):
                self.tree.item(iid, text="☐" + text[1:])
        self._update_summary()

    def _select_invert(self):
        for iid in self.tree.get_children():
            self._toggle_item(iid)

    def _get_checked_pdfs(self) -> List[str]:
        return [iid for iid in self.tree.get_children()
                if self.tree.item(iid, "text").startswith("☑")]

    def _update_summary(self):
        total = len(self.pdf_list)
        checked = len(self._get_checked_pdfs())
        self.lbl_summary.config(text=f"已勾选 {checked} / 共 {total}")

    # --------------------------- 开始 / 控制 ---------------------------
    def _on_start(self):
        watermark = self.var_watermark.get().strip()
        if not watermark:
            messagebox.showwarning("提示", "请输入水印文字"); return
        pdfs = self._get_checked_pdfs()
        if not pdfs:
            messagebox.showwarning("提示", "请至少勾选一个 PDF"); return

        # 解析+验证超时配置
        try:
            timeout_sec = int(self.var_timeout.get().strip())
        except ValueError:
            messagebox.showwarning("提示", "单文件超时必须是整数"); return
        if not (30 <= timeout_sec <= 3600):
            messagebox.showwarning("提示", "单文件超时建议在 30 - 3600 秒之间"); return

        n = len(pdfs)
        est_min = n * EST_SEC_PER_FILE / 60
        ok = messagebox.askokcancel(
            "确认开始",
            f"即将批量处理 {n} 个 PDF, 预计耗时 ≈ {est_min:.1f} 分钟.\n"
            f"单文件硬超时: {timeout_sec}s (超时自动跳过)\n"
            f"\n"
            f"⚠️ 自动化依赖真实鼠标点击, 全程请勿:\n"
            f"   • 移动鼠标 / 点击键盘\n"
            f"   • 切换其他窗口\n"
            f"   • 锁屏 / 进入屏保\n"
            f"\n"
            f"建议先去倒杯水 ☕\n"
            f"\n"
            f"点击「确定」开始, 「取消」放弃."
        )
        if not ok: return

        # 准备
        self.results = []
        self.batch_start_time = time.time()
        # 清空之前的状态列
        for iid in self.tree.get_children():
            self.tree.item(iid, values=(self.tree.set(iid, "size"), ""), tags=())

        self._lock_ui_running(True)
        self.runner = BatchRunner(
            on_log=self._log,
            on_progress=self._on_progress,
            on_result=self._on_result,
            per_file_timeout=timeout_sec,
        )
        self.runner_thread = threading.Thread(
            target=self._run_thread, args=(pdfs, watermark), daemon=True
        )
        self.runner_thread.start()

    def _run_thread(self, pdfs: List[str], watermark: str):
        report_path = None
        try:
            report_path = self.runner.run(pdfs, watermark)
        except Exception as e:
            self._log(f"[严重] BatchRunner 崩溃: {e}")
            self._log(traceback.format_exc())
        self.ui_queue.put(("done", report_path))

    def _on_pause(self):
        if self.runner is None: return
        if self.runner.is_paused():
            self.runner.resume()
            self.btn_pause.config(text="⏸ 暂停")
            self._log("[控制] 已恢复")
        else:
            self.runner.pause()
            self.btn_pause.config(text="▶ 继续")
            self._log("[控制] 已暂停 (当前文件会处理完再停)")

    def _on_skip(self):
        if self.runner is None: return
        if messagebox.askyesno("跳过当前", "跳过当前文件? (会强杀 Acrobat)"):
            self.runner.skip_current()

    def _on_stop(self):
        if self.runner is None: return
        if messagebox.askyesno("终止", "终止整个批量处理?\n(当前文件会被强杀)"):
            self.runner.stop()
            self.runner.skip_current()  # 同时跳过加速退出

    # --------------------------- 回调 (来自子线程, 用 queue 中转) ---------------------------
    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_queue.put(f"[{ts}] {msg}")

    def _on_progress(self, i: int, total: int, pdf: str):
        self.ui_queue.put(("progress", i, total, pdf))

    def _on_result(self, result: PdfResult):
        self.ui_queue.put(("result", result))

    # --------------------------- UI 线程: 消费 queue 更新界面 ---------------------------
    def _poll_queues(self):
        # 日志
        try:
            while True:
                line = self.log_queue.get_nowait()
                self.txt_log.config(state="normal")
                self.txt_log.insert("end", line + "\n")
                self.txt_log.see("end")
                self.txt_log.config(state="disabled")
        except queue.Empty:
            pass

        # UI 事件
        try:
            while True:
                msg = self.ui_queue.get_nowait()
                if msg[0] == "progress":
                    _, i, total, pdf = msg
                    self.pb.config(maximum=total, value=i)
                    elapsed = (time.time() - self.batch_start_time) if self.batch_start_time else 0
                    eta = (elapsed / max(i, 1)) * (total - i) if i > 0 else 0
                    self.var_progress.set(
                        f"{i+1}/{total} | 当前: {Path(pdf).name} "
                        f"| 已用 {int(elapsed)}s | 预计剩余 {int(eta)}s"
                    )
                elif msg[0] == "result":
                    r: PdfResult = msg[1]
                    self.results.append(r)
                    self.pb.config(value=len(self.results))
                    # 更新对应行的状态列 + 颜色
                    try:
                        size_text = self.tree.set(r.file_path, "size")
                        status_text = f"{r.status} ({r.duration_sec}s)"
                        self.tree.item(r.file_path,
                                       values=(size_text, status_text),
                                       tags=(r.status,))
                    except Exception:
                        pass
                elif msg[0] == "done":
                    self._on_batch_done(msg[1])
        except queue.Empty:
            pass

        self.after(150, self._poll_queues)

    # --------------------------- 完成 / UI 锁 ---------------------------
    def _on_batch_done(self, report_path: Optional[str]):
        self._lock_ui_running(False)

        ok = sum(1 for r in self.results if r.status == "success")
        fail = sum(1 for r in self.results if r.status == "failed")
        timeout = sum(1 for r in self.results if r.status == "timeout")
        skipped = sum(1 for r in self.results if r.status == "skipped")
        elapsed = int(time.time() - self.batch_start_time) if self.batch_start_time else 0

        lines = [
            "批量处理完成!\n",
            f"成功: {ok}",
            f"失败: {fail}",
            f"超时: {timeout}",
            f"跳过: {skipped}",
            "",
            f"总耗时: {elapsed // 60} 分 {elapsed % 60} 秒",
            f"报告: {report_path or '(报告生成失败)'}",
        ]
        if fail + timeout > 0:
            lines.append("")
            lines.append("⚠️ 部分文件失败. 可在 CSV 报告中查看详情, 针对失败文件重跑.")
        messagebox.showinfo("完成", "\n".join(lines))

    def _lock_ui_running(self, running: bool):
        st_normal = "disabled" if running else "normal"
        st_running_only = "normal" if running else "disabled"
        self.btn_start.config(state=st_normal)
        self.btn_pause.config(state=st_running_only, text="⏸ 暂停")
        self.btn_skip.config(state=st_running_only)
        self.btn_stop.config(state=st_running_only)

        if running:
            self.banner.config(
                text="🔴 自动化运行中 - 请勿移动鼠标 / 点击键盘 / 切换窗口!",
                bg="#cc0000", fg="white",
                font=("Microsoft YaHei", 12, "bold"),
            )
        else:
            self.banner.config(
                text="✓ 空闲 (可以正常使用电脑)",
                bg="#cccccc", fg="#444444",
                font=("Microsoft YaHei", 11),
            )


# =====================================================================
# 【入口】
# =====================================================================
if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    BatchApp().mainloop()
