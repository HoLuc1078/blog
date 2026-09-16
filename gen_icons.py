# -*- coding: utf-8 -*-
"""
从 iconfont 项目导出静态 SVG sprite（static/icons.svg）
=====================================================
yc-lain 博客（cnblogs）用的图标来自阿里矢量图标库 iconfont，
页面里那句 <script src="https://at.alicdn.com/t/font_1825850_klax1ao4o6.js">
做的事就是把一整份 <symbol> sprite 塞进 body。这里把它抠出来，写成
static/icons.svg：

  · 编辑器图标选择器直接用 <use href="/static/icons.svg#icon-x"> 引用它
    （整个文件浏览器只下一次，之后走缓存）；
  · 文章页/首页/草稿箱只需要自己那几个图标，由 app.py 的 post_icon_sprites()
    把那几个 <symbol> 内联进页面，不会为了一个图标拉 1.8MB。

顺手做的压缩：路径坐标取整（viewBox 都是 ~1024 见方，图标实际显示只有 20px 上下，
整数坐标的误差 ≈ 0.02px，肉眼看不出），文件因此小三分之一；另外压掉多余空白。
没有引入任何第三方依赖。

用法：
    python gen_icons.py                     # 用默认的 iconfont 地址
    python gen_icons.py <js-url|本地js路径> [输出svg]
"""

import io
import os
import re
import sys
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_URL = "https://at.alicdn.com/t/font_1825850_klax1ao4o6.js"
DEFAULT_OUT = os.path.join(BASE_DIR, "static", "icons.svg")
# iconfont 的 id 统一加前缀，避免和站内自绘图标撞名（两边都有 icon-lizi）
PREFIX = "ic-"

_SYMBOL = re.compile(r"<symbol\b[^>]*>.*?</symbol>", re.S)
_ID = re.compile(r'\bid="([^"]+)"')
_D_ATTR = re.compile(r'(\sd=")([^"]*)(")')
_NUM = re.compile(r"-?\d+\.\d+")
_OLD_PREFIX = re.compile(r"^icon-")


def fetch(url):
    """url 可以是 http(s) 地址，也可以是本地已下好的 js 文件路径。"""
    if re.match(r"^https?://", url):
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read().decode("utf-8", "replace")
    with io.open(url, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def shorten_path(d):
    """路径坐标取整 + 压掉多余空白（1024 视口、实际 20px 显示，误差约 0.02px）。"""

    def fix(m):
        v = round(float(m.group(0)))
        return "0" if v == 0 else str(v)

    d = _NUM.sub(fix, d)
    d = re.sub(r"\s+", " ", d).strip()
    return d


def tidy(symbol):
    def fix_d(m):
        return m.group(1) + shorten_path(m.group(2)) + m.group(3)

    symbol = _D_ATTR.sub(fix_d, symbol)
    symbol = re.sub(r">\s+<", "><", symbol)
    symbol = re.sub(r"\s+", " ", symbol).strip()
    return symbol


def build(js_text):
    symbols = _SYMBOL.findall(js_text)
    out = []
    seen = set()
    for s in symbols:
        m = _ID.search(s)
        if not m:
            continue
        raw = m.group(1)
        name = PREFIX + _OLD_PREFIX.sub("", raw)
        if name in seen:          # 同名只留第一份
            continue
        seen.add(name)
        s = s[:m.start(1)] + name + s[m.end(1):]
        out.append(tidy(s))
    return out


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    dest = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUT
    print("fetching %s ..." % url, flush=True)
    js = fetch(url)
    symbols = build(js)
    if not symbols:
        raise SystemExit("没找到 <symbol>，确认地址是不是 iconfont 的 symbol 项目 js")
    body = "\n".join(symbols)
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">\n'
           "%s\n</svg>\n" % body)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with io.open(dest, "w", encoding="utf-8", newline="\n") as f:
        f.write(svg)
    print("icons: %d" % len(symbols))
    print("bytes: %d -> %s" % (len(svg.encode("utf-8")), dest))


if __name__ == "__main__":
    main()
