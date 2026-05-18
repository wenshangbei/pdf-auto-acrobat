# 批量 PDF 去水印 - 设计文档

## 1. 目标

在现有最小闭环（`AcrobatWorker.run(pdf_path, watermark_text)`）之上，增加批量处理能力，满足三条要求：

1. **每个 PDF 一份独立报告**：成功/失败、耗时、失败原因
2. **单文件失败自动跳过 + 自动清理 Acrobat**，继续下一个，不让一个坏文件拖垮整批
3. **明确告知用户"全程勿动鼠标键盘"**（自动化用真实鼠标点击，期间用户操作会被吞）

## 2. 范围 & 约束

- ✅ 基于现有 Worker 不动，只在外层加 BatchRunner + UI
- ✅ 单进程串行（Acrobat 单实例机制，并行不可行）
- ❌ 不做断点续跑（v1 先做完整跑，断点续跑放 v2）
- ❌ 不做并行队列（同上）

## 3. 用户流程

```
1. 用户选输入文件夹 → 列出所有 PDF
2. 用户填水印文字 (默认"示例水印")
3. 用户点"开始批量处理"
   ↓ 弹出二次确认: "处理将持续约 N 分钟, 全程请勿移动鼠标键盘. 确定吗?"
4. UI 显示:
   - 总进度条 (3/50)
   - 当前文件名
   - 已用时 / 预估剩余
   - 实时日志区
   - "暂停" / "跳过当前" / "终止" 按钮
5. 处理完成后弹出报告窗口:
   - 成功 N / 失败 M / 总耗时
   - 失败清单 (文件名 + 原因)
   - "导出报告 CSV" 按钮
```

## 4. 报告格式

### 4.1 每条 PDF 的记录字段

| 字段 | 类型 | 示例 |
|---|---|---|
| `file_path` | str | `C:\...\卷宗1.pdf` |
| `file_size_kb` | int | `2048` |
| `status` | enum | `success` / `failed` / `skipped` / `timeout` |
| `start_at` | datetime | `2026-05-17 22:30:12` |
| `end_at` | datetime | `2026-05-17 22:30:39` |
| `duration_sec` | float | `27.3` |
| `error_stage` | str / null | `click_start_button` / `wait_for_action_done` / null |
| `error_message` | str / null | `4 种点击方式都未触发进度面板` / null |

### 4.2 内存数据结构

```python
@dataclass
class PdfResult:
    file_path: str
    file_size_kb: int
    status: Literal["success", "failed", "skipped", "timeout"]
    start_at: datetime
    end_at: datetime
    duration_sec: float
    error_stage: str | None = None
    error_message: str | None = None
```

### 4.3 持久化

- **运行中实时追加**：`reports/batch_YYYYMMDD_HHMMSS.csv`（一行一个 PDF）
- 即使整批崩溃也已经有半截报告

### 4.4 CSV 列

```csv
序号,文件路径,文件大小KB,状态,开始时间,结束时间,耗时(秒),失败阶段,失败原因
1,C:\xxx\a.pdf,2048,success,2026-05-17 22:30:12,2026-05-17 22:30:39,27.3,,
2,C:\xxx\b.pdf,5120,failed,2026-05-17 22:30:39,2026-05-17 22:32:09,90.0,click_start_button,4 种点击方式都未触发
3,C:\xxx\c.pdf,800,timeout,...,...,180.0,wait_for_action_done,300s 内保存按钮未恢复
```

## 5. 容错策略

### 5.1 单文件硬超时

防止"某个 PDF 让 Acrobat 卡死、Worker 一直等"拖死整批。**给单文件总耗时设上限**（建议 **180 秒**，可配置）。

实现方案：把 `worker.run(...)` 放到一个 daemon 子线程里跑，主线程用 `Thread.join(timeout=PER_FILE_TIMEOUT)`：

```python
t = threading.Thread(target=worker.run, args=(pdf, watermark), daemon=True)
t.start()
t.join(timeout=PER_FILE_TIMEOUT)
if t.is_alive():
    # 子线程还在跑 → 超时
    result.status = "timeout"
    result.error_stage = "global_timeout"
    worker.kill_acrobat()   # 强杀, 让子线程 UIA 调用快速失败
    # 注意: Python 不能从外部 kill 线程, 但 kill 进程后子线程的 pywinauto 调用会抛错自然退出
```

### 5.2 失败分类

```
launch 失败           → Acrobat 装路径错 / 系统故障 / 上一轮 kill 不彻底
open_pdf 失败         → 文件不存在 / 损坏 / 加密 / 路径含特殊字符
click_remove_watermark → Acrobat 界面变化 / 中文版本不一致
click_action_list 失败 → 同上
select_action_item 失败 → 动作列表里没找到对应水印文字的动作 (用户配置错)
click_start_button 失败 → Qt 窗口未就绪 / 屏幕分辨率变化
wait_for_action_done 超时 → 大 PDF / Acrobat 卡死 / 动作崩溃
save_and_close 失败   → 磁盘满 / 文件被占用 / 权限问题
```

每个阶段抛错时，BatchRunner 捕获 → 写入 `error_stage` + `error_message` → kill_acrobat → 继续下一个。

### 5.3 严重错误判定（提前终止整批）

某些错误说明环境根本不可用，继续跑无意义，应该提示用户后**终止**：

- 连续 3 个文件都在同一阶段失败（比如都在 `click_remove_watermark`）→ UI 变化或 Acrobat 配置错
- 连续 5 个文件都失败 → 环境出大问题
- `select_action_item` 失败 = 动作不存在 → 全部都会同样失败，立刻提示用户检查动作配置

弹窗：「连续 N 个文件在 XX 步失败，建议检查 Acrobat 配置后重试。继续 / 终止？」

### 5.4 Acrobat 清理时机

```
Worker.run() finally 已经 kill_acrobat()  ← 现有逻辑
                ↓
BatchRunner 外层再次 kill_acrobat()         ← 双保险
                ↓
开始处理下一个 PDF (launch 全新 Acrobat)
```

## 6. UI 设计草案

```
┌────────────────────────────────────────────────────────┐
│ 输入文件夹: [C:\....测试卷宗........] [选择...]        │
│ 水印文字:   [示例水印........................]           │
│ ┌─────────────────────────────────────────────────┐    │
│ │ 扫描到 12 个 PDF (双击查看)                    │    │
│ │ ☑ a.pdf  ☑ b.pdf  ☑ c.pdf  ☑ ...                │    │
│ └─────────────────────────────────────────────────┘    │
│ [开始批量处理]  [清空选择]                              │
│                                                         │
│ 进度: ████████░░░░░░░░░░ 5/12 (42%)                    │
│ 当前: 卷宗5.pdf                                         │
│ 已用 02:15  /  预估剩余 03:08                           │
│                                                         │
│ [⏸ 暂停] [⏭ 跳过当前] [⏹ 终止]                          │
│                                                         │
│ ┌─────────────── 实时日志 ───────────────────────┐    │
│ │ [22:35:12] [3/12] 处理 c.pdf ...                │    │
│ │ [22:35:30] ✓ c.pdf 成功 (18.2s)                 │    │
│ │ [22:35:30] [4/12] 处理 d.pdf ...                │    │
│ └─────────────────────────────────────────────────┘    │
└────────────────────────────────────────────────────────┘
```

### 6.1 "全程勿操作"提示放三处

1. **开始前确认弹窗**（最显眼）：
   > ⚠️ 即将开始批量处理 **12 个 PDF**，预计耗时 **约 5 分钟**。
   > 
   > 自动化依赖真实鼠标点击，**全程请勿移动鼠标、勿点击键盘、勿切换窗口**，否则会失败。
   > 
   > 建议：处理时去倒杯水 ☕
   > 
   > [取消] [我知道了，开始]

2. **运行时顶部红色横幅**：
   > 🔴 自动化运行中 - 请勿操作鼠标键盘

3. **失败汇总弹窗**：如果有失败的 PDF，提示"部分失败可能因运行时用户操作导致，可针对失败文件重跑"

## 7. 数据流

```
用户选文件夹
    ↓
scan_pdf_files(folder) → List[str]
    ↓
用户确认 → BatchRunner.start(pdf_list, watermark)
    ↓
for pdf in pdf_list:
    result = PdfResult(file_path=pdf, status="...", ...)
    try:
        # 子线程跑 worker.run, 主线程 join 带超时
        run_with_timeout(worker.run, args=(pdf, watermark), timeout=180)
        result.status = "success"
    except TimeoutError:
        result.status = "timeout"
        kill_acrobat()
    except Exception as e:
        result.status = "failed"
        result.error_stage = locate_failure_stage(e)
        result.error_message = str(e)
    finally:
        result.end_at = now()
        result.duration_sec = (end - start).seconds
        append_csv_row(result)         # 立刻持久化
        ui_update(result)              # UI 进度更新
        kill_acrobat()                 # 双保险清理

# 全部跑完
show_summary(all_results)
export_full_report_button()
```

## 8. 模块设计

```
acrobat_gui_min.py (现有, 不动)
├── AcrobatWorker         ← 单文件 worker, 保持不动

acrobat_batch.py (新建)
├── PdfResult             ← dataclass, 单文件结果
├── BatchRunner           ← 串行调度, 超时控制, 报告持久化
│   ├── run(pdf_list, watermark, on_progress, on_log)
│   ├── pause() / resume() / stop() / skip_current()
│   └── _run_one_with_timeout(pdf)
├── BatchReport           ← 报告聚合 + CSV 导出
└── BatchApp(tk.Tk)       ← 新 UI, 复用 AcrobatWorker
```

## 9. 风险点

| 风险 | 缓解 |
|---|---|
| 单文件超时 180s 不够（大 PDF） | 配置可调，UI 设置项暴露 |
| 用户中途真的去操作了电脑 | 接受现实，让失败的进入失败清单，可单独重跑 |
| 磁盘写满 | 开始前预检空间（剩余 < 输入总大小 × 1.5 时警告） |
| 持续 1+ 小时后 Acrobat / Windows 内存爆 | 每 N 个文件强制 sleep + GC，必要时重启 Python 进程 |
| 失败原因 `str(e)` 太冗长 | 提取关键信息（第一行 / 异常类名），CSV 字段截断到 200 字符 |

## 10. 验收标准

- [ ] 选 10 个 PDF 跑批，至少 9 个成功，1 个失败有清晰报告
- [ ] 单文件硬超时确实生效（用一个故意构造的大 PDF 验证 180s 后跳过）
- [ ] 整批中断后，CSV 报告里已经处理的部分完整可读
- [ ] 失败文件清单可一键导出 CSV
- [ ] UI 红色横幅"勿操作"全程可见
- [ ] 失败后下一个文件能正常开始（kill_acrobat 工作正常）

## 11. 后续 v2 待考虑

- 断点续跑：CSV 已存在时跳过 `status=success` 的
- 失败重试：自动对失败文件再跑一次（不同时间点环境可能不同）
- 调试模式：失败时保存截屏 + UI 树 dump，方便排查
- 多动作支持：一个 PDF 跑多个动作（不只是去水印）
