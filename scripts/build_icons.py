"""Render the original geometric LabelLens monogram as install icons."""
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[1] / "app" / "static"
for size in (192, 512):
    image = Image.new("RGB", (512, 512), "#b44028")
    draw = ImageDraw.Draw(image)
    for x, end in ((171, 246), (292, 342)):
        draw.line([(x, 135), (x, 365), (end, 365)], fill="#f7f4ec", width=30, joint="curve")
    draw.ellipse((354, 354, 378, 378), fill="#f7f4ec")
    image.resize((size, size), Image.Resampling.LANCZOS).save(root / f"icon-{size}.png")
