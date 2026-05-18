# Acrobat 去水印自动化 - 设计文档

## 1. 目标

通过 Python RPA 自动化中文版 Adobe Acrobat Pro DC，对指定 PDF 文件执行 Acrobat 内置的"动作向导（Action Wizard）→ 去水印"动作并保存关闭，最终目标是批量处理。

**当前阶段**：最小闭环已跑通 —— 单文件 + tkinter GUI + 全流程自动化。

## 2. 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│  tkinter GUI (App 类)                                       │
│  - 文件选择框 / 水印文字输入 / 开始按钮 / 日志区            │
│  - 工作线程 (避免阻塞 UI)                                   │
│  - queue 跨线程日志传递                                     │
└────────────────────────┬────────────────────────────────────┘
                         │ run(pdf_path, watermark_text)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  AcrobatWorker (核心自动化)                                  │
│  log_func 回调日志, 与 UI 完全解耦                          │
└─────────────────────────────────────────────────────────────┘
                         │ pywinauto (uia) + win32 + ctypes
                         ▼
                  Adobe Acrobat Pro DC
```

**关键解耦点**：`AcrobatWorker` 接收 `log_func` 回调，不依赖 tkinter。批量化时可以用 CLI / 别的 GUI 替换前端，Worker 完全不动。

## 3. 自动化流程（10 步）

```
1. launch()                  启动 Acrobat / 连接已有实例
2. open_pdf(path)            Ctrl+O 唤起对话框, 输入路径, 回车
3. click_remove_watermark()  右侧工具栏点"去水印"
4. (sleep 3s)                 等工具面板渲染
5. click_action_list()       点"动作列表 [Alt+Ctrl+A]"
6. select_action_item(text)  在弹出窗口里点对应水印文字的 TreeItem
7. click_start_button()      点"开始"按钮 (无名图标按钮)
8. wait_for_action_done()    轮询保存按钮 enable 状态
9. save_and_close(path)      点"保存"按钮 + Ctrl+W 关闭
10. kill_acrobat()           杀光所有 Adobe 进程 (finally 保证执行)
```

## 4. 关键设计决策

### 4.1 为什么用 pywinauto + UIA backend？
- Acrobat 用了 Adobe 自有 UI 框架（部分窗口是 Qt5QWindowToolSaveBits），Win32 backend 找不到大部分子控件
- UIA backend 能下钻到大多数自定义控件

### 4.2 为什么不能 100% 依赖 UIA invoke？
- Acrobat 的 Button 大都声明 `IsInvokePatternAvailable: true`
- **但 Qt 窗口里的按钮/树项目，InvokePattern 经常是 stub —— 报"成功"实际没触发**
- 解决：分类点击策略
  - 主窗口 Button（去水印、动作列表、保存）：invoke 优先（_safe_click）
  - **Qt 窗口控件（TreeItem、开始按钮）：必须真实鼠标 SendInput（_raw_mouse_click）**

### 4.3 为什么用 SendInput 而不是 mouse_event？
- `user32.mouse_event` 是 Win9x 时代 API，对现代 UI 框架（特别是 Qt）的事件路由会丢
- `SendInput`（pywinauto.mouse 底层）能正确触发完整 hover/down/up 序列

### 4.4 为什么用 class_name 而不是 title_re connect Acrobat？
- 64位 Python 控制 32位 Acrobat 时，`Application(uia).connect(title_re=...)` 会 TimeoutError
- 但 `class_name="AcrobatSDIWindow"` 能正常工作（跨架构稳定）

### 4.5 为什么用"保存按钮 enable 状态"判断动作完成？
**之前试过都不可靠**：
- 主窗口标题 → Acrobat MDI 模式，文档名只在标签页，主窗口标题永远是空
- UIA Text 控件 `Name="运行动作列表"` → UIA 树里时有时无，多进程难定位
- AVL_AVWindow class + size 形状检测 → 还行但偶尔被其他面板误判
- **保存按钮 `IsEnabled` 字段 → 100% 可靠，动作中 disable，完成后 enable**

### 4.6 为什么 finally 里要 kill_acrobat？
- Acrobat DC 是单实例机制，残留进程会让下次 launch() 卡死或行为异常
- emergency_recover 的 ESC + Ctrl+W 不能保证完全清干净
- 直接 taskkill 7 个相关进程是最稳的"重置环境"

## 5. 已知限制

| 限制 | 说明 |
|---|---|
| 必须使用 Acrobat Pro DC | 标准版无"动作向导"功能 |
| 中文版 UI 标签 | 按钮名硬编码为中文（"去水印"、"动作列表"、"保存"等） |
| 必须预设动作 | 用户必须事先在 Acrobat 里录好命名等于水印文字的动作 |
| 必须关掉 Acrobat 主页 | 编辑 → 首选项 → 一般 → 取消"打开没有文档的应用程序时显示主页屏幕" |
| 32位 Acrobat × 64位 Python | UIA 跨架构调用有少量功能受限（已用 class_name 等绕过） |
| 屏幕分辨率敏感 | 真实鼠标点击依赖 BoundingRectangle 屏幕坐标，多显示器 / 缩放变化要重测 |

## 6. 批量化扩展点（下一阶段）

1. **Worker 已经解耦**：`AcrobatWorker.run(pdf_path, watermark_text)` 直接循环调用即可
2. **kill_acrobat 已经在 finally**：每个 PDF 处理完都会重置环境
3. **需要增加的**：
   - 文件夹扫描（已在 `acrobat_remove_watermark.py` 早期版本有 `scan_pdf_files`，可复用）
   - 进度条 + 当前文件名展示
   - 失败重试策略（单文件失败不中断整体）
   - 错误清单（哪些文件失败、为什么）
   - 暂停 / 跳过当前文件按钮
