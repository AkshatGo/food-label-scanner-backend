"""Reflow detected grid cells for OCR without inventing rows or values."""

import numpy as np
from PIL import Image


def table_variants(image, cv2):
    """Detect ruled tables in either polarity and remove their grid borders.

    Each cell keeps its row and column position. Stretching condensed print
    horizontally helps Tesseract on packaging fonts; cell-local thresholds
    preserve white lettering on colored, unevenly lit backgrounds.
    """
    if cv2 is None:
        return
    image = image.copy()
    image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
    gray = np.asarray(image.convert("L"))
    height, width = gray.shape
    if min(height, width) < 200:
        return
    # High-saturation yellow/orange panels (common on Indian packets) form a
    # clean connected region after orientation correction. OCR'ing that region
    # avoids the glossy front artwork and keeps the full nutrition table.
    rgb = np.asarray(image.convert("RGB"))
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    color_mask = cv2.inRange(hsv, np.array([10, 55, 45]), np.array([45, 255, 255]))
    components, _, stats, _ = cv2.connectedComponentsWithStats(color_mask)
    for x, y, w, h, area in sorted(stats[1:], key=lambda s: s[4], reverse=True)[:8]:
        if area < width * height * .08 or w < width * .25 or h < height * .18:
            continue
        crop = gray[max(0, y-8):min(height, y+h+8), max(0, x-8):min(width, x+w+8)]
        crop = cv2.resize(crop, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        yield Image.fromarray(crop)
        break
    for light_ink in (True, False):
        ink = gray if light_ink else 255 - gray
        mask = cv2.adaptiveThreshold(ink, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY, 51, -8)
        horizontal = cv2.morphologyEx(mask, cv2.MORPH_OPEN,
                                     np.ones((1, max(80, width // 9)), np.uint8))
        vertical = cv2.morphologyEx(mask, cv2.MORPH_OPEN,
                                   np.ones((max(25, height // 50), 1), np.uint8))
        # Horizontal rules define the row bands. Keeping vertical rules out
        # of contour discovery avoids splitting each band into tiny glyph
        # contours on glossy packaging.
        grid = cv2.dilate(horizontal, np.ones((65, 5), np.uint8))
        contours, hierarchy = cv2.findContours(grid, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        if hierarchy is None:
            continue
        cells = []
        for index, contour in enumerate(contours):
            x, y, w, h = cv2.boundingRect(contour)
            if (width * .075 < w < width * .8
                    and 20 <= h <= height * .08):
                cells.append((x, y, w, h))
        if not 8 <= len(cells) <= 120:
            continue
        rows = []
        for box in sorted(cells, key=lambda b: b[1]):
            if rows and abs(box[1] - rows[-1][0][1]) < box[3] * .4:
                rows[-1].append(box)
            else:
                rows.append([box])
        rows = [sorted(row) for row in rows if 2 <= len(row) <= 5]
        if len(rows) < 4:
            continue
        # Bound the assembled canvas independently of source dimensions.
        scale = min(1.5, 1800 / (max(sum(b[2] for b in row) for row in rows) * 2))
        rendered = []
        for row in rows:
            tiles = []
            for column, (x, y, w, h) in enumerate(row):
                crop = ink[y:y+h, x+3:x+w-3]
                crop = cv2.resize(crop, None, fx=2*scale, fy=scale,
                                  interpolation=cv2.INTER_CUBIC)
                threshold, _ = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
                # Higher thresholds separate thick, blurred letter strokes.
                if column == 0 or h > 50:
                    threshold += (float(crop.max()) - threshold) * .35
                tile = cv2.threshold(crop, threshold, 255, cv2.THRESH_BINARY_INV)[1]
                tiles.append(tile)
            rendered.append(tiles)
        row_heights = [max(tile.shape[0] for tile in row) + 30 for row in rendered]
        canvas_width = max(sum(tile.shape[1] + 35 for tile in row) for row in rendered) + 20
        canvas = np.full((sum(row_heights) + 20, canvas_width), 255, np.uint8)
        top = 20
        for tiles, row_height in zip(rendered, row_heights):
            left = 20
            for tile in tiles:
                h, w = tile.shape
                canvas[top:top+h, left:left+w] = tile
                left += w + 35
            top += row_height
        yield Image.fromarray(canvas)
