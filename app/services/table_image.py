"""Reflow detected grid cells for OCR without inventing rows or values.

Indian snack/drink labels frequently print the nutrition table as white
lettering on a saturated (orange/red/green) background with a ruled grid.
Full-frame OCR reads the heading and then loses the rows; the parser then
finds a panel but no values. This module detects the ruled table, removes
its borders, and re-assembles the cells row-by-row on a clean black-on-white
canvas that Tesseract reads reliably. Row order and column order are
preserved so label semantics survive.
"""

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
    for light_ink in (True, False):
        ink = gray if light_ink else 255 - gray
        mask = cv2.adaptiveThreshold(ink, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY, 51, -8)
        horizontal = cv2.morphologyEx(mask, cv2.MORPH_OPEN,
                                      np.ones((1, max(40, width // 11)), np.uint8))
        vertical = cv2.morphologyEx(mask, cv2.MORPH_OPEN,
                                    np.ones((max(15, height // 64), 1), np.uint8))
        grid = cv2.dilate(horizontal | vertical, np.ones((5, 5), np.uint8))
        contours, hierarchy = cv2.findContours(grid, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        if hierarchy is None:
            continue
        cells = []
        for index, contour in enumerate(contours):
            x, y, w, h = cv2.boundingRect(contour)
            if (hierarchy[0][index][3] >= 0 and width * .075 < w < width * .8
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
