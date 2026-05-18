# Acrobat 自动化踩坑记录

记录定位过程曲折、根因反直觉的 bug，避免重蹈覆辙。

---

## 1. "去水印"按钮在 UIA 树里时有时无 (2026-05)

### TL;DR

Acrobat 右侧工具栏按钮的 UIA 暴露是**惰性**的——脚本调用 `descendants(Button, title="去水印")` 在 Acrobat 内部"未触发重画"时返回 0 个候选，看起来像按钮不存在，但**屏幕上肉眼是看得见的**。

**解法**：找按钮失败 ~2 秒后，主动发 `Ctrl+K` 打开 Acrobat 首选项 → 立即 `Esc` 关闭。这个"模态对话框开关"事件会强制 Acrobat 重画主窗口 + 重新枚举控件，按钮就被注入 UIA 树了。

实现：`acrobat_gui_min.py::AcrobatWorker._toggle_preferences_dialog()`，在 `_click_visible_button()` 失败循环里每 4 轮（~2s）调用一次。

---

### 现象

```
[..] 定位按钮: '去水印' (mode=exact) ...
[..]   找到 0 个候选, 筛选可见的 ...
[..]   找到 0 个候选, 筛选可见的 ...        ← 持续 30s 都是 0
[..]   找到 0 个候选, 筛选可见的 ...
[..] 失败阶段: click_remove_watermark | 未能定位到可见的 '去水印' 按钮
```

四个关键事实，缺一就走错方向：

1. **同一个 PDF 多次跑，时成时败**——不是文件内容问题
2. **失败时屏幕右侧"去水印"四个字肉眼可见**——按钮在 UI 上确实存在
3. **inspect.exe 鼠标移过去时，按钮属性"突然显示出来"**——按钮的 UIA 节点是被某个事件按需生成的
4. **手动打开"编辑→首选项→一般"再关闭，按钮 100% 重现**——证实了事件触发机制的存在

inspect 抓到的"空容器态"长这样：
```
窗格 '右侧工具窗格'
  ClassName: AVL_AVView          ← Acrobat View Library, Adobe 自绘组件
  Patterns: 只有 LegacyIAccessible
  Children: (无)                  ← 子按钮全部缺失
```

而"有按钮态"下，同一个 AVL_AVView 容器里会有 `Button{title='去水印'}` 等子节点。

---

### 误判过的方向（按发生顺序）

| 假设 | 怎么排除的 |
|---|---|
| Acrobat 升级到了"新版 Acrobat 体验" UI | 用户检查版本号还是旧版；而且"开关首选项"如果是新 UI 是不会让按钮变出来的 |
| 主窗口尺寸太小，按钮被虚拟化滚动隐藏 | 全屏后仍失败，AVScrollView 高度从 335 涨到 825 也找不到 |
| 用户跑的是已处理过的 `Removed_*.pdf`，Acrobat 走快速路径 | 原始 PDF 也复现，跟文件状态无关 |
| 重启后磁盘缓存失效，加载慢 | 重启后才出现是巧合（重启刚好触发了 Acrobat 后台更新的 UI 微调） |
| 加载 PDF 时"底部页码进度条"消失了是关联现象 | 实测是独立的 UI 简化，跟按钮注入无关 |

**最有迷惑性的误判**：把"页码进度条消失"和"按钮找不到"关联起来，怀疑 Acrobat 升级。实际上它俩是同时期发生但完全独立的两件事。教训：**只信能 100% 复现的证据**。

---

### 尝试过但失败的修复

每次都打包测试，记录效果：

| 修复方案 | 强度 | 实测效果 |
|---|---|---|
| 主窗口 maximize | 几乎无 | 仍失败。证明不是空间问题 |
| 鼠标 hover 到 task pane + 滚轮上下滚 | 弱事件 | 仍失败。Acrobat 不响应纯鼠标事件 |
| `taskbar.set_focus() → main_win.set_focus()` 切焦点 | 中等事件 | 仍失败。set_focus 在已经是前台时不触发 WM_ACTIVATE |
| `Ctrl+K` 开首选项 → `Esc` 关 | **重事件** | **100% 有效** |

强度分级符合 Win32 消息的实际触发：
- `WM_MOUSEMOVE` / `WM_MOUSEWHEEL`：Acrobat 把它们当普通滚动事件，不重画工具栏
- `WM_SETFOCUS` 单独触发：不算 "activate"，Acrobat 不重画
- `WM_ACTIVATE`（真模态对话框开关）：Acrobat 必须响应（焦点真切走过又真回来），借机重新枚举所有可见控件

---

### 最终修复

`acrobat_gui_min.py::AcrobatWorker._toggle_preferences_dialog()`：

```python
def _toggle_preferences_dialog(self) -> bool:
    try:
        self.main_win.set_focus()
    except Exception:
        pass
    send_keys("^k")           # Ctrl+K → Acrobat 首选项对话框
    time.sleep(0.6)            # 等对话框真正渲染好
    send_keys("{ESC}")         # Esc → 关闭 (等价于 Cancel)
    time.sleep(0.4)            # 等 WM_ACTIVATE 处理 + 主窗口重画
    return True
```

调用点（`_click_visible_button()` 失败循环内）：

```python
if len(candidates) == 0:
    empty_streak += 1
    if empty_streak % 4 == 0:    # POLL_INTERVAL=0.5s, 每 4 轮 ≈ 2s
        ok = self._toggle_preferences_dialog()
        self.log(f"  [刺激] 第 {empty_streak} 轮空, 开关首选项 ...")
```

同时把 `_click_visible_button()` 默认超时从 20s 提到 90s（给足重试时间）。

副作用：失败时 Acrobat 首选项窗口会一闪而过约 0.8s。视觉上有抖动，但换来稳定性。

---

### 给未来调试者的经验

1. **Acrobat 的 UIA 暴露不是静态的**——同样的窗口、同样的 `descendants` 查询，不同时刻结果不同。不要假设"控件存在就一定能查到"。

2. **`AVL_AVView` 是 Adobe 自绘容器**，UIA 树里它的子节点是按需注入的。如果只看到这个类名而没有子按钮，**不代表 UI 上真没东西**，先用 inspect 鼠标 hover 验证一下。

3. **触发 Acrobat 重新枚举控件的"重事件"**：
   - ✅ 真实模态对话框开关（Ctrl+K + Esc 是最便宜的）
   - ✅ 最小化 + 还原主窗口（视觉副作用大）
   - ❌ set_focus（在已经前台时是 no-op）
   - ❌ 鼠标移动/滚轮（普通事件，Acrobat 不响应）

4. **打包测试要用真实的 PDF**。开发机上的 PDF 跟生产 PDF（已处理过 / 含复杂水印层）行为可能不一样。但归根到底，本 bug 跟 PDF 内容**无关**，只跟 Acrobat 自身状态有关。

5. **"重启电脑后才出现的问题"不一定是重启导致的**——Adobe 可能在重启时静默推送了某个微小的 UI 更新，但这个更新跟你看到的 bug 现象**未必有直接因果**。本案就是这样。

---

### 相关提交

- `a9f20d2` fix(refocus): 切焦点到任务栏 — **方案 C，实测无效**
- `8b53f15` fix(prefs-toggle): Ctrl+K / Esc 开关首选项 — **方案 A，最终采用**
