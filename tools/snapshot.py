#!/usr/bin/env python3
"""
把 examples/reports/ 下的三个 HTML 出成 PNG，放进 docs/img/，给 README 用。

需要 playwright（可选依赖，主流程不需要它）：
  pip install playwright
用本机已装的 Chrome（channel="chrome"），不下载浏览器。没有 Chrome 就 `python -m playwright install chromium` 再把 --channel 设为空。
没装 playwright：脚本会告诉你用浏览器打开 HTML 手动截图。

用法（仓库根目录）:
  python tools/snapshot.py                       # examples/reports → docs/img
  python tools/snapshot.py --reports reports --out docs/img --scale 2 --channel chrome

产出:
  docs/img/card-send.png    发给她的卡（只截卡片本身）
  docs/img/card-bill.png    亲情账单卡
  docs/img/report.png       完整报告（整页）
  docs/img/report-top.png   报告首屏（README 里用）
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from _common import setup_utf8  # noqa: E402

setup_utf8()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reports", default=os.path.join(ROOT, "examples", "reports"))
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "img"))
    ap.add_argument("--scale", type=int, default=2, help="设备像素比，2 = 高清")
    ap.add_argument("--channel", default="chrome", help="chrome / msedge / 空字符串（用 playwright 自带的 chromium）")
    ap.add_argument("--top-height", type=int, default=1500, help="report-top.png 截多高（CSS 像素）")
    a = ap.parse_args()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("没装 playwright。两个办法：\n  1) pip install playwright，再跑一次\n  2) 用浏览器打开 examples/reports/ 下的三个 HTML，手动截图放到 docs/img/")
        sys.exit(1)

    os.makedirs(a.out, exist_ok=True)
    files = {
        "card-send": os.path.join(a.reports, "mama-message-card-send.html"),
        "card-bill": os.path.join(a.reports, "mama-message-card-bill.html"),
        "report": os.path.join(a.reports, "mama-message-report.html"),
    }
    for k, p in files.items():
        if not os.path.exists(p):
            print(f"找不到 {p}，先跑 scripts/render.py")
            sys.exit(1)

    with sync_playwright() as pw:
        kw = {"channel": a.channel} if a.channel else {}
        try:
            browser = pw.chromium.launch(**kw)
        except Exception as e:
            print(f"启动浏览器失败：{e}\n本机没有 Chrome 的话：python -m playwright install chromium，然后 --channel \"\"")
            sys.exit(1)
        ctx = browser.new_context(viewport={"width": 760, "height": 1200}, device_scale_factor=a.scale, locale="zh-CN")
        page = ctx.new_page()
        for k in ("card-send", "card-bill"):
            page.goto("file:///" + os.path.abspath(files[k]).replace("\\", "/"))
            page.wait_for_timeout(400)
            page.locator("article.card").screenshot(path=os.path.join(a.out, f"{k}.png"))
            print(f"→ {os.path.join(a.out, k + '.png')}")
        page.goto("file:///" + os.path.abspath(files["report"]).replace("\\", "/"))
        page.wait_for_timeout(600)
        page.screenshot(path=os.path.join(a.out, "report.png"), full_page=True)
        print(f"→ {os.path.join(a.out, 'report.png')}")
        page.screenshot(path=os.path.join(a.out, "report-top.png"), clip={"x": 0, "y": 0, "width": 760, "height": a.top_height})
        print(f"→ {os.path.join(a.out, 'report-top.png')}")
        browser.close()


if __name__ == "__main__":
    main()
