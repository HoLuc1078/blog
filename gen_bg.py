# -*- coding: utf-8 -*-
"""生成 static/bg.jpg（1920x1080 亮紫→玫红渐变 + 柔和光斑），需 Pillow。"""
import os
import random

from PIL import Image, ImageDraw, ImageFilter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE_DIR, "static", "bg.jpg")
W, H = 1920, 1080

top = (52, 42, 96)
mid = (86, 58, 126)
bot = (150, 74, 122)

img = Image.new("RGB", (W, H))
draw = ImageDraw.Draw(img)
for y in range(H):
    t = y / (H - 1)
    if t < 0.5:
        k = t * 2
        c = tuple(int(a + (b - a) * k) for a, b in zip(top, mid))
    else:
        k = (t - 0.5) * 2
        c = tuple(int(a + (b - a) * k) for a, b in zip(mid, bot))
    draw.line([(0, y), (W, y)], fill=c)

random.seed(42)
glow = Image.new("RGB", (W, H), (0, 0, 0))
gd = ImageDraw.Draw(glow)
colors = [(251, 114, 153), (170, 120, 220), (120, 160, 250), (255, 186, 140), (255, 140, 190)]
for _ in range(18):
    x, y = random.randint(-200, W), random.randint(-200, H)
    r = random.randint(150, 470)
    c = random.choice(colors)
    gd.ellipse([x - r, y - r, x + r, y + r], fill=c)
glow = glow.filter(ImageFilter.GaussianBlur(220))
img = Image.blend(img, glow, 0.55)
img = img.filter(ImageFilter.GaussianBlur(1))

img.save(OUT, quality=88)
print("saved:", OUT)
