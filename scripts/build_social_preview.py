"""Build the GitHub social-preview card (1280x640) in the LabelLens palette.

Output: screenshots/social-preview.png
Upload: repo Settings -> General -> Social preview (manual, one click),
or via the GitHub API if a supported endpoint is available.

Run from the repo root:
    .venv/bin/python scripts/build_social_preview.py
"""

import math
import os

from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 640
PAPER = "#f7f4ec"
PAPER_DIM = "#efe9dc"
INK = "#252a22"
MUTED = "#6b7264"
ACCENT = "#b44028"
LINE = "#d9d2c4"

# First existing path wins (this machine ships Noto CJK; Replit ships DejaVu).
SANS_CANDIDATES = [
    "/usr/share/fonts/NotoSansCJK/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
]
SERIF_CANDIDATES = [
    "/usr/share/fonts/noto-cjk/NotoSerifCJK-Light.ttc",
    "/usr/share/fonts/NotoSansCJK/NotoSansCJK-Regular.ttc",
]


def first_font(paths, size, index=0):
    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size, index=index)
    raise RuntimeError("no usable font found in: " + ", ".join(paths))


def sans(size):
    return first_font(SANS_CANDIDATES, size)


def serif(size):
    return first_font(SERIF_CANDIDATES, size)


def star_points(cx, cy, outer, inner):
    pts = []
    for i in range(10):
        r = outer if i % 2 == 0 else inner
        a = math.pi / 2 + i * math.pi / 5  # start pointing up
        pts.append((cx + r * math.cos(a), cy - r * math.sin(a)))
    return pts


def draw_star(layer, cx, cy, size, fill):
    ImageDraw.Draw(layer).polygon(
        star_points(cx, cy, size, size * 0.42), fill=fill
    )


def spaced(draw, xy, text, font, fill, tracking):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        w = draw.textlength(ch, font=font)
        x += w + tracking


def main():
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)

    # subtle footer band for depth
    d.rectangle([0, H - 118, W, H], fill=PAPER_DIM)
    d.line([0, H - 118, W, H - 118], fill=LINE, width=2)

    # --- logo tile + wordmark -------------------------------------------
    d.rounded_rectangle([80, 66, 152, 138], radius=18, fill=ACCENT)
    f_logo = sans(40)
    tb = d.textbbox((0, 0), "ll", font=f_logo, stroke_width=2)
    d.text(
        (116 - (tb[2] - tb[0]) / 2 - tb[0], 102 - (tb[3] - tb[1]) / 2 - tb[1]),
        "ll",
        font=f_logo,
        fill=PAPER,
        stroke_width=2,
        stroke_fill=PAPER,
    )
    f_word = sans(54)
    d.text((172, 74), "labellens", font=f_word, fill=INK, stroke_width=1, stroke_fill=INK)
    f_tag = serif(26)
    d.text((174, 138), "A little more label literacy.", font=f_tag, fill=MUTED)

    d.line([80, 200, W - 80, 200], fill=LINE, width=2)

    # --- headline --------------------------------------------------------
    f_head = sans(58)
    d.text((80, 244), "Scan any food label.", font=f_head, fill=INK, stroke_width=1, stroke_fill=INK)
    d.text((80, 322), "Get an honest rating in stars.", font=f_head, fill=INK, stroke_width=1, stroke_fill=INK)

    # --- star meter: numeral + 2.5 of 5 stars ----------------------------
    f_num = sans(88)
    d.text((80, 424), "2.5", font=f_num, fill=ACCENT)
    num_w = d.textlength("2.5", font=f_num)

    star_y, star_r = 470, 34
    sx = 80 + num_w + 36
    full = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_star(full, 0, 0, 1, (0, 0, 0, 0))  # warm up nothing; keep layer
    for i in range(5):
        cx = sx + i * (star_r * 2 + 14)
        draw_star(img, cx, star_y, star_r, LINE)  # empty base
        if i < 2:
            draw_star(img, cx, star_y, star_r, ACCENT)  # full
        elif i == 2:  # half: paste left half of an accent star
            overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            draw_star(overlay, cx, star_y, star_r, ACCENT)
            box = (int(cx - star_r - 2), int(star_y - star_r - 2), int(cx), int(star_y + star_r + 2))
            img.paste(overlay.crop(box), (box[0], box[1]), overlay.crop(box))

    f_cap = sans(20)
    spaced(d, (sx, star_y + star_r + 18), "OUT OF 5  ·  DRAFT INR", f_cap, MUTED, 3)

    # --- footer: feature chips + live URL --------------------------------
    f_chip = sans(22)
    chips = ["FSSAI INR ENGINE", "REAL OCR", "OFFLINE-READY PWA", "COMPLIANCE PDF"]
    cx = 80
    for label in chips:
        tw = d.textlength(label, font=f_chip)
        d.rounded_rectangle(
            [cx, H - 82, cx + tw + 36, H - 34], radius=24,
            outline=MUTED, width=2,
        )
        d.text((cx + 18, H - 70), label, font=f_chip, fill=INK)
        cx += tw + 36 + 16

    f_url = sans(30)
    url = "labelens-lbzo.onrender.com"
    uw = d.textlength(url, font=f_url)
    d.text((W - 80 - uw, H - 76), url, font=f_url, fill=ACCENT)

    out = os.path.join("screenshots", "social-preview.png")
    img.save(out)
    print("saved", out, img.size)


if __name__ == "__main__":
    main()
