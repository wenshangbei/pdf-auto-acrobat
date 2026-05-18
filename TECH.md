# Acrobat 去水印自动化 - 技术文档

## 1. 文件结构

```
Auto_PDF_Handle/
├── acrobat_gui_min.py        # ★ 当前主程序 (单文件 + tkinter GUI)
├── acrobat_remove_watermark.py # 早期 CLI 版本 (含 scan_pdf_files, 批量改造可参考)
├── kill_acrobat.bat          # 清理所有 Adobe 进程的应急脚本
├── build.bat                 # PyInstaller 打包脚本 (onedir 模式)
├── DESIGN.md                 # 设计文档
├── TECH.md                   # 本文档
├── dist/                     # PyInstaller 产物
└── build/                    # PyInstaller 中间产物
```

## 2. 关键模块（acrobat_gui_min.py）

### 2.1 顶部可配置常量（约第 28-60 行）

| 常量 | 说明 | 调整时机 |
|---|---|---|
| `ACROBAT_EXE` | Acrobat 可执行文件路径 | 安装位置不同时改 |
| `ACROBAT_WINDOW_CLASS` | 主窗口类名 `AcrobatSDIWindow` | Acrobat 大版本升级可能变 |
| `BTN_REMOVE_WATERMARK` | `"去水印"` | 不同 Acrobat 中文版可能略不同 |
| `BTN_ACTION_LIST_RE` | 正则 `^动作列表` | 兼容 `动作列表 [Alt+Ctrl+A]` 等变体 |
| `DLG_ACTION_LIST_TITLE` | `"动作列表"` 弹窗标题 | 同上 |
| `DEFAULT_WATERMARK_TEXT` | `"示例水印"` GUI 默认值 | 用户偏好 |
| `ACTION_PROGRESS_TEXT` | `"运行动作列表"`（备用检测用，当前不依赖） | - |
| `TIMEOUT_APP_START / FILE_OPEN / CONTROL_READY / SAVE / ACTION_RUN` | 各阶段超时秒数 | 慢机器调大 |

### 2.2 AcrobatWorker 核心方法（按调用顺序）

| 方法 | 行号 | 关键技术点 |
|---|---|---|
| `launch()` | ~77 | 用 `findwindows.find_windows(class_name=...)` 快速查 HWND 再 UIA connect，避免直接 connect 挂死 |
| `open_pdf(path)` | ~140 | `os.path.normpath()` 规范路径分隔符（避免"文件名无效"），`set_edit_text()` 写中文路径 |
| `_safe_click(ctrl, ...)` | ~262 | invoke 优先 → click_input fallback → 重试机制 |
| `_raw_mouse_click(rect, ...)` | ~248 | `SetCursorPos + pywinauto.mouse.click`（SendInput），Qt 窗口必备 |
| `_click_visible_button(...)` | ~289 | 通用：找可见 Button，过滤 offscreen / 无面积，按 title / title_re 匹配 |
| `click_remove_watermark()` | - | 右侧工具栏的"去水印" |
| `click_action_list()` | - | "动作列表" 按钮（正则匹配） |
| `_find_action_dialog_and_tree_item(text)` | ~360 | 在 desktop 顶层找 Qt 弹窗 + 按 Name 找 TreeItem |
| `select_action_item(text)` | ~386 | **真实鼠标**点击 TreeItem（_raw_mouse_click），Qt 窗口必须 |
| `click_start_button()` | ~597 | trial-and-verify 4 种方式：ctypes → SetFocus+Enter → invoke → click_input |
| `_find_save_button()` | ~440 | Name="保存", Button, 24x24（工具栏图标按钮） |
| `_save_button_enabled()` | ~464 | 返回 True/False/None |
| `wait_for_action_done()` | ~553 | 单循环：等保存按钮 enable |
| `save_and_close(path)` | ~742 | 点击保存按钮 + Ctrl+W |
| `kill_acrobat()` | ~782 | taskkill 7 个 Adobe 进程 |

### 2.3 进程相关 helpers（约第 395-435 行）

- `_get_proc_name_by_pid(pid)` — ctypes 调 `QueryFullProcessImageNameW`，带缓存
- `_is_acrobat_pid(pid)` — 进程名含 `acro` 或 `adobe`
- `_enum_acrobat_hwnds()` — `EnumWindows` 快速拿所有 Acrobat 进程的可见顶层 hwnd

## 3. 打包发布

```cmd
双击 build.bat
```

产物：`dist\AcrobatWatermarkRemover\AcrobatWatermarkRemover.exe`（onedir 模式）

**关键 PyInstaller 参数**：
- `--windowed` 不弹黑控制台（tkinter GUI）
- `--collect-all pywinauto` / `--collect-all comtypes` — 抓 UIA 动态生成的包装类
- `--hidden-import tkinter.*` — 显式声明 tkinter 子模块

**分发**：拷贝整个 `dist\AcrobatWatermarkRemover\` 文件夹。目标机器**不需要 Python，但必须装 Acrobat Pro DC**。

## 4. 调试与排错

### 4.1 通用诊断 - `diag.py`
独立诊断脚本，验证 pywinauto 能否 connect 到当前 Acrobat。

```cmd
python diag.py
type diag_out.txt
```

### 4.2 经典坑速查表

| 现象 | 真因 | 解决 |
|---|---|---|
| connect Acrobat 超时 30s | 32 位 Acrobat + UIA title_re 查询挂死 | 用 `class_name="AcrobatSDIWindow"` 而非 title_re |
| Acrobat 启动后立刻卡死 | launcher 进程秒退，原 app 对象 PID 失效 | start() 之后用 EnumWindows 找 HWND 再 connect(handle=...) |
| 打开 PDF 报"文件名无效" | tkinter 路径用 `/`，Acrobat 对话框只认 `\` | `os.path.normpath(pdf_path)` |
| 找按钮报"There are N elements that match" | Acrobat UI 同名按钮多个 | 用 `descendants` 拿全部，按 visible + offscreen + size 过滤 |
| 进度面板检测失败 | UIA Text 树里没有该控件 | 用"保存按钮 IsEnabled"代替 |
| invoke 报成功但 Acrobat 没反应 | Qt 窗口的 InvokePattern 是 stub | 改用 ctypes / pywinauto.mouse 真实鼠标 |
| 点击坐标点不中按钮 | 旧 mouse_event API 对 Qt 失效 | 用 SendInput（pywinauto.mouse.click） |
| 中文输入框输不进文字 | send_keys 走虚拟键码，发不出中文 | win32clipboard 剪贴板 + Ctrl+V |
| 下一轮运行 Acrobat 状态异常 | 上一轮残留进程 | finally 里 `kill_acrobat()` |
| tkinter `askdirectory()` 挂死 (无报错) | Tk 8.6 在 Win11 / 中文系统上偶发卡 modal | 用 `win32com.client.Dispatch("Shell.Application").BrowseForFolder()` 替代; 同时给 Entry 绑 `<Return>` 让用户能粘贴路径按回车扫描作为兜底 |
| 大 PDF 处理完 `save_and_close` 抛 ElementNotFoundError | Acrobat 内部 reload 后原 main_win 包装类指向的窗口已失效, `set_focus()` 抛错 | 所有 `main_win.set_focus()` 包 silent try, 让 Ctrl+S/Ctrl+W 全局快捷键尽力发出去, 不让 save 这一步挂掉整个 worker |

### 4.3 应急清理

如果 Acrobat 卡死、UI 自动化失控：
```cmd
双击 kill_acrobat.bat
```

## 5. 批量化改造指南（下一阶段）

### 5.1 Worker 已就绪
`AcrobatWorker.run(pdf_path, watermark_text)` 已经自带 try/finally + kill_acrobat，**直接循环调用就能批量**。

### 5.2 UI 改造建议

```python
# App._build_ui 新增:
# - 文件夹选择按钮 (askdirectory)
# - 文件列表 (Listbox 或 Treeview) 显示扫描到的 PDF
# - 进度条 (ttk.Progressbar)
# - 当前处理文件名标签
# - "暂停/继续/跳过当前"按钮

# App._worker_thread 改造:
def _worker_thread(self, pdf_list, watermark):
    success, failed = [], []
    for i, pdf in enumerate(pdf_list):
        if self._stop_flag: break
        self._update_progress(i, len(pdf_list), pdf)
        worker = AcrobatWorker(self._log)
        try:
            worker.run(pdf, watermark)
            success.append(pdf)
        except Exception as e:
            failed.append((pdf, str(e)))
            self._log(f"✘ {pdf}: {e}")
    self._show_summary(success, failed)
```

### 5.3 批量必须考虑的边界
- **磁盘空间不足**：Acrobat 保存大 PDF 可能失败，预检剩余空间
- **PDF 已加密 / 损坏**：open_pdf 步骤会卡在密码框，要检测并跳过
- **文件占用**：被其他程序打开的 PDF 会保存失败
- **动作不匹配**：用户输入的水印文字在 Acrobat 动作列表里找不到，整批都会失败 —— 处理前先 dry-run 验证一次
- **超长运行时崩溃**：Acrobat 长时间运行可能内存爆，每 N 个文件主动 kill 重启
- **日志爆量**：每个 PDF 上百行日志，批量时改为只记关键步骤 + 错误详情

### 5.4 性能预估
单 PDF 平均时长（实测）：
- 启动 Acrobat：3-5s
- 打开 PDF：1-3s
- 点击 + 动作执行：2-10s（看 PDF 大小）
- 保存关闭：2-3s
- kill_acrobat：1-2s

**单 PDF 总耗时约 15-30s**。批量 100 个 PDF ≈ 25-50 分钟。
