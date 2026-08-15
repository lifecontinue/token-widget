#!/usr/bin/env python3
"""
gen-icons.py — 生成 Token Widget 的托盘图标与 Windows 应用图标。

纯标准库实现（zlib + struct），无需任何第三方依赖。
生成两张图：
  - overlay/assets/tray.png   32x32  RGBA 绿色圆点（托盘常驻图标）
  - overlay/assets/icon.ico   256x256 ICO 绿色圆点（exe / 安装包图标）

用法：
    python scripts/gen-icons.py
从仓库根目录或任意位置运行均可（脚本会自动定位 overlay/assets/）。
"""

import os
import struct
import zlib
import sys


# Token Widget 品牌色：青绿 (#34e3c8)
BRAND = (0x34, 0xE3, 0xC8)


def _rgba(r, g, b, a):
    return bytes([r, g, b, a])


def _png_chunk(typ, data):
    body = typ + data
    return (
        struct.pack(">I", len(data))
        + body
        + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    )


def render_circle(size, radius, edge):
    """渲染一张 RGBA 透明 PNG 的裸像素行（含抗锯齿边缘）。"""
    cx = cy = size / 2.0
    rows = []
    for y in range(size):
        row = b"\x00"  # PNG filter type 0
        for x in range(size):
            d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            if d <= radius:
                row += _rgba(*BRAND, 255)
            elif d <= radius + edge:
                a = int(255 * max(0.0, (radius + edge - d) / edge))
                row += _rgba(*BRAND, a)
            else:
                row += _rgba(0, 0, 0, 0)
        rows.append(row)
    raw = b"".join(rows)
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(raw, 9))
        + _png_chunk(b"IEND", b"")
    )


def make_png(size, radius, edge):
    return render_circle(size, radius, edge)


def make_ico(png_bytes):
    """把单张 PNG 包成 ICO（Windows 可直接用作应用图标）。"""
    # ICO 头：reserved(2) type(2) count(2)
    header = struct.pack("<HHH", 0, 1, 1)
    # 目录项：w(1) h(1) colors(1) reserved(1) planes(2) bpp(2) size(4) offset(4)
    w = h = 0  # 256 在 ICO 目录里用 0 表示
    entry = struct.pack(
        "<BBBBHHII", w, h, 0, 0, 1, 32, len(png_bytes), 6 + 16
    )
    return header + entry + png_bytes


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(here)
    assets_dir = os.path.join(repo_root, "overlay", "assets")
    os.makedirs(assets_dir, exist_ok=True)

    # 托盘图标 32x32
    tray = make_png(32, 12.0, 1.5)
    tray_path = os.path.join(assets_dir, "tray.png")
    with open(tray_path, "wb") as f:
        f.write(tray)

    # 应用图标 256x256
    png256 = make_png(256, 96.0, 4.0)
    ico = make_ico(png256)
    ico_path = os.path.join(assets_dir, "icon.ico")
    with open(ico_path, "wb") as f:
        f.write(ico)

    print("generated:", tray_path, len(tray), "bytes")
    print("generated:", ico_path, len(ico), "bytes")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover
        print("gen-icons failed:", exc, file=sys.stderr)
        sys.exit(1)
