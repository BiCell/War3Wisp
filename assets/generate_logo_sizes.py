"""按目标尺寸矢量式重绘 logo，并做二值化后处理，彻底消除小图模糊。

关键：PIL 默认对文字和图形做抗锯齿，会产生灰色半透明像素，小尺寸下糊成一片。
解决：渲染后量化 alpha（>阈值=255 否则=0）+ 量化颜色到固定调色板，得到锐利硬边。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
FONT_PATH = Path(r"C:\Windows\Fonts\arialbd.ttf")
SIZES = (16, 24, 32, 48, 64, 128, 256)

# 调色板（量化目标色，避免灰色软边）
C_ARROW = (252, 0, 0)
C_OUTLINE = (0, 0, 0)
C_KEY_FACE = (255, 255, 255)
C_KEY_HIGHLIGHT = (255, 255, 255)
C_KEY_SHADOW = (160, 160, 160)
C_LETTER = (0, 0, 0)
PALETTE = np.array(
    [C_ARROW, C_OUTLINE, C_KEY_FACE, C_KEY_SHADOW, C_LETTER],
    dtype=np.int16,
)


def _stroke(size: int) -> int:
    if size <= 24:
        return 1
    if size <= 64:
        return 2
    return max(2, round(size / 48))


def _gap(size: int) -> int:
    if size <= 24:
        return 1
    return max(1, round(size * 0.04))


def _bevel(size: int) -> int:
    if size <= 32:
        return 0
    if size <= 64:
        return 1
    return max(2, round(size / 64))


def _font_px(size: int, key_w: int, row_h: int) -> int | None:
    """返回字体像素高度；若按键太小放不下字母则返回 None（跳过字母）。"""
    # 字母高度不超过按键短边的 0.72，且至少需要 6px 才能识别
    max_h = int(min(key_w, row_h) * 0.72)
    if max_h < 6:
        return None
    # 也按整体尺寸给一个合理上限
    caps = {16: 7, 24: 10, 32: 13, 48: 18, 64: 24, 128: 46, 256: 90}
    cap = caps.get(size, 90)
    return min(max_h, cap)


def _quantize(arr: np.ndarray) -> np.ndarray:
    """量化 RGBA：alpha 二值化，RGB 量化到调色板。"""
    out = arr.copy()
    # alpha 二值化：>64 视为不透明
    a = out[:, :, 3]
    out[:, :, 3] = np.where(a > 64, 255, 0).astype(np.uint8)

    # 仅对不透明像素量化 RGB
    rgb = out[:, :, :3].astype(np.int32)
    # 计算每个像素到每个调色板色的距离（用 int32 避免 int16 平方溢出）
    # shape: (h, w, n_palette)
    diff = rgb[:, :, None, :] - PALETTE[None, None, :, :].astype(np.int32)
    dist = (diff * diff).sum(axis=-1)
    nearest = dist.argmin(axis=-1)
    quantized = PALETTE[nearest].astype(np.uint8)
    # 只在 alpha>0 处替换
    mask = out[:, :, 3:4] > 0
    out[:, :, :3] = np.where(mask, quantized, out[:, :, :3])
    return out


def _draw_key(
    img: Image.Image,
    box: tuple[int, int, int, int],
    letter: str,
    outline: int,
    bevel: int,
    font: ImageFont.FreeTypeFont | None,
) -> None:
    draw = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    # 外框（黑）
    draw.rectangle(box, fill=(0, 0, 0, 255))
    ix0, iy0 = x0 + outline, y0 + outline
    ix1, iy1 = x1 - outline, y1 - outline
    # 按键面（白）
    draw.rectangle((ix0, iy0, ix1, iy1), fill=(255, 255, 255, 255))

    if bevel > 0:
        # 右、下阴影（硬边）
        draw.rectangle((ix1 - bevel, iy0, ix1, iy1), fill=C_KEY_SHADOW + (255,))
        draw.rectangle((ix0, iy1 - bevel, ix1, iy1), fill=C_KEY_SHADOW + (255,))

    # 字母（居中）；font 为 None 时跳过（按键太小）
    if font is None:
        return
    bbox = draw.textbbox((0, 0), letter, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    # 用临时图绘制字母再粘贴，裁剪到按键面，防止溢出污染相邻键
    face_w = ix1 - ix0 + 1
    face_h = iy1 - iy0 + 1
    if face_w <= 0 or face_h <= 0:
        return
    tmp = Image.new("RGBA", (face_w, face_h), (0, 0, 0, 0))
    tdraw = ImageDraw.Draw(tmp)
    tdraw.text(
        (-bbox[0] + (face_w - tw) // 2, -bbox[1] + (face_h - th) // 2),
        letter,
        fill=(0, 0, 0, 255),
        font=font,
    )
    img.paste(tmp, (ix0, iy0), tmp)


def _draw_arrow(
    draw: ImageDraw.ImageDraw,
    cx: int,
    top: int,
    bottom: int,
    width: int,
    outline: int,
) -> None:
    head_h = max(3, int((bottom - top) * 0.45))
    shaft_bottom = bottom - head_h
    shaft_w = max(2, int(width * 0.36))
    head_w = width

    # 箭杆（黑框 + 红芯）
    draw.rectangle(
        (cx - shaft_w // 2, top, cx + shaft_w // 2, shaft_bottom),
        fill=(0, 0, 0, 255),
    )
    draw.rectangle(
        (cx - shaft_w // 2 + outline, top + outline, cx + shaft_w // 2 - outline, shaft_bottom),
        fill=C_ARROW + (255,),
    )

    # 箭头（三角，黑框）
    head = [
        (cx, bottom),
        (cx - head_w // 2, shaft_bottom),
        (cx + head_w // 2, shaft_bottom),
    ]
    draw.polygon(head, fill=(0, 0, 0, 255))
    inset = outline
    inner_head = [
        (cx, bottom - inset),
        (cx - head_w // 2 + inset, shaft_bottom),
        (cx + head_w // 2 - inset, shaft_bottom),
    ]
    draw.polygon(inner_head, fill=C_ARROW + (255,))


def render_logo(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    outline = _stroke(size)
    gap = _gap(size)
    bevel = _bevel(size)
    # 减小边距，让按键和字母有更多空间
    pad = max(0, round(size * 0.04))

    content_w = size - 2 * pad
    content_h = size - 2 * pad

    arrow_h = int(content_h * 0.34)
    keys_h = content_h - arrow_h - gap
    row_h = (keys_h - gap) // 2

    # 下排 3 键
    key_w = (content_w - 2 * gap) // 3
    row2_w = 3 * key_w + 2 * gap
    row1_w = 2 * key_w + gap

    base_x = pad + (content_w - row2_w) // 2
    row1_x = pad + (content_w - row1_w) // 2

    keys_top = pad + arrow_h + gap
    row1_y = keys_top
    row2_y = keys_top + row_h + gap

    font_px = _font_px(size, key_w, row_h)
    font = ImageFont.truetype(str(FONT_PATH), font_px) if font_px else None

    # 下排 Z X C
    for i, ch in enumerate("ZXC"):
        x0 = base_x + i * (key_w + gap)
        _draw_key(img, (x0, row2_y, x0 + key_w, row2_y + row_h), ch, outline, bevel, font)

    # 上排 S D
    for i, ch in enumerate("SD"):
        x0 = row1_x + i * (key_w + gap)
        _draw_key(img, (x0, row1_y, x0 + key_w, row1_y + row_h), ch, outline, bevel, font)

    # 箭头
    arrow_w = max(6, int(row1_w * 0.55))
    cx = size // 2
    draw_arrow = ImageDraw.Draw(img)
    _draw_arrow(draw_arrow, cx, pad, pad + arrow_h, arrow_w, outline)

    # 二值化后处理：消除抗锯齿灰色软边
    arr = np.array(img)
    arr = _quantize(arr)
    return Image.fromarray(arr, "RGBA")


def main() -> None:
    sizes_dir = ROOT / "sizes"
    sizes_dir.mkdir(exist_ok=True)

    frames: list[Image.Image] = []
    for size in SIZES:
        img = render_logo(size)
        out = sizes_dir / f"logo_{size}x{size}.png"
        img.save(out, format="PNG")
        frames.append(img)
        print(f"  {out.name}  {size}x{size}  {out.stat().st_size} bytes")

    logo_png = ROOT / "logo.png"
    frames[-1].save(logo_png, format="PNG")
    print(f"Updated {logo_png.name}")

    ico_path = ROOT / "logo.ico"
    # 每个尺寸独立绘制嵌入，避免缩放
    frames[-1].save(
        ico_path,
        format="ICO",
        sizes=[(im.width, im.height) for im in frames],
        append_images=frames[:-1],
    )
    print(f"Updated {ico_path.name}")


if __name__ == "__main__":
    main()
