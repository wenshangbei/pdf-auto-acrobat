# -*- coding: utf-8 -*-
import sys
import traceback

import os as _os
LOG = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "diag_out.txt")

def log(msg):
    line = str(msg) + "\n"
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line)

# clean log
open(LOG, "w", encoding="utf-8").close()

log(f"Python: {sys.version}")
log(f"Executable: {sys.executable}")

try:
    from pywinauto.application import Application
    from pywinauto import findwindows
    log("pywinauto imported OK")
except Exception:
    log("pywinauto import FAILED:")
    log(traceback.format_exc())
    raise SystemExit(1)

log("")
log("--- 1. findwindows by title_re ---")
try:
    hs = findwindows.find_windows(title_re=r".*Adobe Acrobat.*")
    log(f"matched handles: {hs}")
except Exception:
    log(traceback.format_exc())

log("")
log("--- 2. Application(uia).connect by title_re ---")
try:
    app = Application(backend="uia").connect(title_re=r".*Adobe Acrobat.*", timeout=5)
    log(f"connect OK, pid={app.process}")
except Exception as e:
    log(f"FAILED: {type(e).__name__}: {e}")

log("")
log("--- 3. Application(win32).connect by title_re ---")
try:
    app = Application(backend="win32").connect(title_re=r".*Adobe Acrobat.*", timeout=5)
    log(f"connect OK, pid={app.process}")
except Exception as e:
    log(f"FAILED: {type(e).__name__}: {e}")

log("")
log("--- 4. connect by class_name AcrobatSDIWindow ---")
try:
    app = Application(backend="uia").connect(class_name="AcrobatSDIWindow", timeout=5)
    log(f"connect OK, pid={app.process}")
except Exception as e:
    log(f"FAILED: {type(e).__name__}: {e}")

log("")
log("--- 5. Direct enum + filter ---")
try:
    all_handles = findwindows.find_windows(visible_only=False)
    log(f"total windows: {len(all_handles)}")
    matched = []
    for h in all_handles:
        try:
            from pywinauto.controls.hwndwrapper import HwndWrapper
            w = HwndWrapper(h)
            t = w.window_text()
            c = w.class_name()
            if "Acrobat" in t or "Acrobat" in (c or ""):
                matched.append((h, t, c))
        except Exception:
            pass
    log(f"Acrobat-related: {len(matched)}")
    for h, t, c in matched[:20]:
        log(f"  HWND=0x{h:X} class={c!r} title={t!r}")
except Exception:
    log(traceback.format_exc())

log("\nDONE")
