# -*- coding: utf-8 -*-
"""
从 static/bg.jpg 提取「主体色」，供 CSS 变量 / 站点图标使用。
换掉背景图后页面主色会自动跟着变（app.py 按 mtime 缓存）。

做法：缩图 -> 逐像素 HSV -> 按「饱和度×亮度」加权投票找主色相族
     -> 在该色相族内加权平均得到饱和度，再按固定明度档位生成一套深色 UI 配色。
"""
import colorsys
import math


def _clamp(x, a, b):
    return max(a, min(b, x))


def _hex(h, s, l):
    r, g, b = colorsys.hls_to_rgb(h % 1.0, _clamp(l, 0, 1), _clamp(s, 0, 1))
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def _hsla(h, s, l, a):
    return "hsla(%d, %d%%, %d%%, %s)" % (round((h % 1.0) * 360), round(_clamp(s, 0, 1) * 100),
                                         round(_clamp(l, 0, 1) * 100), a)


def analyse(path, bins=24):
    """主色相族：返回 dict(hue, sat, light)；取色失败返回 None。"""
    try:
        from PIL import Image
        img = Image.open(path).convert("RGB")
    except Exception:
        return None
    img.thumbnail((96, 96))
    hist = [0.0] * bins
    sum_s = [0.0] * bins
    sum_v, n = 0.0, 0
    for r, g, b in img.getdata():
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        sum_v += v
        n += 1
        if s < 0.14 or v < 0.12:      # 跳过灰白黑：看着有颜色其实没有
            continue
        w = (s ** 1.6) * (v ** 0.7)
        i = min(bins - 1, int(h * bins))
        hist[i] += w
        sum_s[i] += s * w
    if n == 0:
        return None
    if sum(hist) <= 0:                # 整张图接近灰：给一套低饱和中性紫
        return {"hue": 0.72, "sat": 0.12, "light": sum_v / n}
    peak = max(range(bins), key=lambda i: hist[i])
    hx = hy = wsum = ssum = 0.0
    for i in (peak - 1, peak, peak + 1):   # 峰值附近 3 个桶取加权平均，色相更稳
        j = i % bins
        if hist[j] <= 0:
            continue
        ang = (j + 0.5) / bins * 2 * math.pi
        hx += math.cos(ang) * hist[j]
        hy += math.sin(ang) * hist[j]
        wsum += hist[j]
        ssum += sum_s[j]
    hue = (math.atan2(hy, hx) / (2 * math.pi)) % 1.0
    return {"hue": hue, "sat": (ssum / wsum) if wsum else 0.3, "light": sum_v / n}


def palette(path):
    """整套配色（十六进制 / hsla），取色失败返回 None。"""
    info = analyse(path)
    if not info:
        return None
    h = info["hue"]
    acc_s = _clamp(max(0.55, info["sat"] * 1.9), 0.45, 0.90)     # 主体色（强调色）
    base_s = _clamp(info["sat"] * 1.35, 0.16, 0.42)              # 深色块
    lift = _clamp((info["light"] - 0.45) * 0.25, -0.03, 0.05)    # 底图亮则深色块略提亮
    return {
        "accent": _hex(h, acc_s, 0.63 + lift * 0.4),
        "accent2": _hex(h, acc_s * 0.95, 0.78 + lift * 0.3),
        "accent_deep": _hex(h, acc_s, 0.49 + lift * 0.4),
        "deep": _hex(h, base_s, 0.16 + lift),
        "side": _hex(h, base_s, 0.20 + lift),
        "board": _hex(h, base_s, 0.23 + lift),
        "card": _hex(h, base_s, 0.28 + lift),
        "card_hover": _hex(h, base_s * 0.95, 0.36 + lift),
        "bg": _hex(h, base_s, 0.18 + lift),
        "topbar": _hsla(h, base_s, 0.20 + lift, 0.72),
        "grad": "linear-gradient(160deg, %s 0%%, %s 58%%, %s 100%%)" % (
            _hex(h, base_s, 0.21 + lift), _hex(h, base_s, 0.27 + lift),
            _hex(h + 0.03, base_s, 0.37 + lift)),
    }


def build_css(path):
    """返回 ':root{...}' 形式的 CSS 变量；取色失败返回空串（用内置默认配色）。"""
    p = palette(path)
    if not p:
        return ""
    vals = {
        "--accent": p["accent"],
        "--accent-2": p["accent2"],
        "--accent-deep": p["accent_deep"],
        "--solid-deep": p["deep"],
        "--solid-side": p["side"],
        "--solid-board": p["board"],
        "--solid-card": p["card"],
        "--card-hover": p["card_hover"],
        "--bg-base": p["bg"],
        "--topbar-bg": p["topbar"],
        "--bg-grad": p["grad"],
    }
    return ":root{" + "".join("%s:%s;" % (k, v) for k, v in vals.items()) + "}"
