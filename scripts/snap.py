#!/usr/bin/env python3
"""
把卡片 HTML 截成 PNG：用本机已经装好的 Chrome / Edge / Chromium 的无头模式，不装任何东西。

用法:
  python scripts/snap.py reports/mama-message-card-send.html [--out 卡.png] [--width 390] [--scale 2]
  （render.py --png、compare.py --png 会自动调它）

先让浏览器打开一次量出卡片多高，再按这个高度截图（2 倍清晰度）。找浏览器的顺序：环境变量 MAMA_BROWSER →
Windows 的 Chrome / Edge 默认安装位置 → macOS 的 /Applications → PATH 里的 google-chrome / chromium / microsoft-edge。
卡片页面里没有任何外部资源；启动时关掉了后台联网、同步、扩展和组件更新，用一个用完就删的临时配置目录
（建在输出文件旁边），不碰你自己的浏览器配置。只用标准库。
"""
import argparse
import os
import pathlib
import re
import shutil
import struct
import subprocess
import sys
import time

from _common import setup_utf8

setup_utf8()

FLAGS = ["--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--no-default-browser-check",
         "--disable-background-networking", "--disable-component-update", "--disable-sync", "--disable-extensions",
         "--disable-default-apps", "--disable-features=Translate,MediaRouter", "--metrics-recording-only", "--mute-audio"]
MEASURE_JS = ("<script>(function(){var c=document.querySelector('.card')||document.body;"
              "var r=c.getBoundingClientRect();document.title='MAMA_H='+Math.ceil(r.height+r.top*2)+';';})();</script>")
SHOT_CSS = "<style>html,body{margin:0!important;padding:0!important;display:block!important;background:#EDEDED!important}.card{margin:0!important}</style>"


class SnapError(Exception):
    """截不了图（没装浏览器、浏览器报错）。调用方提示一句，HTML 照样能用。"""


def find_browser():
    env = os.environ.get("MAMA_BROWSER")
    cands = [env] if env else []
    if sys.platform == "win32":
        for base in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")):
            if base:
                cands += [os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"),
                          os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")]
    elif sys.platform == "darwin":
        cands += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                  "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                  "/Applications/Chromium.app/Contents/MacOS/Chromium"]
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "msedge", "chrome"):
        w = shutil.which(name)
        if w:
            cands.append(w)
    return next((c for c in cands if c and os.path.exists(c)), None)


def png_size(path):
    """PNG 的 (宽, 高)，读文件头就行。"""
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise SnapError(f"{path} 不是 PNG")
    return struct.unpack(">II", head[16:24])


def _run(browser, args, timeout):
    try:
        return subprocess.run([browser] + FLAGS + args, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise SnapError(f"浏览器没跑起来（{e}）")


def html_to_png(html_path, png_path, width=390, scale=2, browser=None, timeout=60):
    """卡片 HTML → PNG，返回 png_path。截不了抛 SnapError。"""
    browser = browser or find_browser()
    if not browser:
        raise SnapError("没找到 Chrome / Edge / Chromium（装一个，或者用环境变量 MAMA_BROWSER 指定路径）")
    with open(html_path, encoding="utf-8") as f:
        src = f.read()
    work = os.path.join(os.path.dirname(os.path.abspath(png_path)), ".snap-tmp")
    os.makedirs(work, exist_ok=True)
    try:
        prof = "--user-data-dir=" + os.path.join(work, "profile")
        probe = os.path.join(work, "probe.html")
        shot = os.path.join(work, "shot.html")
        with open(probe, "w", encoding="utf-8", newline="\n") as f:
            f.write(src.replace("</head>", SHOT_CSS + "</head>").replace("</body>", MEASURE_JS + "</body>"))
        with open(shot, "w", encoding="utf-8", newline="\n") as f:
            f.write(src.replace("</head>", SHOT_CSS + "</head>"))
        r = _run(browser, [prof, f"--window-size={width},2000", "--dump-dom", pathlib.Path(probe).as_uri()], timeout)
        m = re.search(r"MAMA_H=(\d+);", r.stdout)
        if not m:
            raise SnapError("量不出卡片高度（浏览器输出：" + (r.stderr or r.stdout).strip()[:120] + "）")
        height = max(200, int(m.group(1)))
        if os.path.exists(png_path):
            os.remove(png_path)
        r = _run(browser, [prof, f"--window-size={width},{height}", f"--force-device-scale-factor={scale}",
                           "--screenshot=" + os.path.abspath(png_path), pathlib.Path(shot).as_uri()], timeout)
        if not os.path.exists(png_path):
            raise SnapError("浏览器没写出图片（" + (r.stderr or r.stdout).strip()[:120] + "）")
        return png_path
    finally:
        for _ in range(5):                       # Windows 上浏览器退出后会多锁一会儿配置目录
            shutil.rmtree(work, ignore_errors=True)
            if not os.path.exists(work):
                break
            time.sleep(0.3)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("html", help="卡片 HTML")
    ap.add_argument("--out", default=None, help="PNG 路径（默认和 HTML 同名）")
    ap.add_argument("--width", type=int, default=390)
    ap.add_argument("--scale", type=int, default=2, help="清晰度倍数")
    a = ap.parse_args()
    out = a.out or os.path.splitext(a.html)[0] + ".png"
    try:
        html_to_png(a.html, out, width=a.width, scale=a.scale)
    except (SnapError, OSError) as e:
        print(f"✗ {e}")
        sys.exit(1)
    w, h = png_size(out)
    print(f"→ {out}（{w}×{h}）")


if __name__ == "__main__":
    main()
