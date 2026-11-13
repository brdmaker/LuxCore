#!/usr/bin/env python3
"""Regenerate screen.png and decal.png for the device example (needs Pillow and DejaVu fonts)."""
import math
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans{}.ttf"

W, H = 640, 360
im = Image.new("RGB", (W, H), (8, 12, 20))
d = ImageDraw.Draw(im)
d.text((30, 20), "SPINDLE 12000 rpm", font=ImageFont.truetype(FONT.format("-Bold"), 44), fill=(90, 200, 255))
d.text((30, 80), "Load 42 %   Temp 38 C", font=ImageFont.truetype(FONT.format(""), 24), fill=(200, 220, 230))
d.line([(30 + i * 5, 300 - 60 * math.sin(i / 9) - i * 0.4) for i in range(116)], fill=(80, 255, 140), width=4)
d.rectangle([30, 130, 610, 330], outline=(60, 80, 100), width=2)
im.save(os.path.join(HERE, "screen.png"))

logo = Image.new("RGBA", (512, 128), (0, 0, 0, 0))
ImageDraw.Draw(logo).text((14, 6), "SAMPLE", font=ImageFont.truetype(FONT.format("-Bold"), 100),
                          fill=(235, 235, 235, 255))
logo.save(os.path.join(HERE, "decal.png"))
