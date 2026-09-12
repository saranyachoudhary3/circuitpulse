import cv2
import numpy as np

COLOR_DIGITS = {
    "black": 0,
    "brown": 1,
    "red": 2,
    "orange": 3,
    "yellow": 4,
    "green": 5,
    "blue": 6,
    "violet": 7,
    "gray": 8,
    "white": 9
}

COLOR_MULTIPLIERS = {
    "black": 1,
    "brown": 10,
    "red": 100,
    "orange": 1000,
    "yellow": 10000,
    "green": 100000,
    "blue": 1000000,
    "gold": 0.1,
    "silver": 0.01
}

COLOR_TOLERANCES = {
    "brown": "1%",
    "red": "2%",
    "gold": "5%",
    "silver": "10%"
}

STANDARD_E12 = [
    10, 12, 15, 18, 22, 27, 33, 39, 47, 56, 68, 82,
    100, 120, 150, 180, 220, 270, 330, 390, 470, 560, 680, 820,
    1000, 1200, 1500, 1800, 2200, 2700, 3300, 3900, 4700, 5600, 6800, 8200,
    10000, 12000, 15000, 18000, 22000, 27000, 33000, 39000, 47000, 56000, 68000, 82000,
    100000, 220000, 470000, 1000000
]


def classify_pixel_color(bgr):
    b, g, r = int(bgr[0]), int(bgr[1]), int(bgr[2])
    hsv = cv2.cvtColor(np.uint8([[bgr]]), cv2.COLOR_BGR2HSV)[0][0]
    h, s, v = int(hsv[0]), int(hsv[1]), int(hsv[2])

    if v < 40:
        return "black"
    if s < 30 and v > 190:
        return "white"
    if s < 40 and 55 <= v <= 190:
        return "gray"

    # Red covers hue 0-10 and 160-180
    if (h < 10 or h > 165) and s > 48 and v > 40:
        return "red"
    if 8 <= h <= 25 and v <= 150 and s > 30:
        return "brown"
    if 8 <= h <= 20 and v > 120 and s > 80:
        return "orange"
    if 18 <= h <= 28 and s > 35 and v > 90:
        return "gold"
    if 28 < h <= 38 and s > 60 and v > 115:
        return "yellow"
    if 38 < h <= 85 and s > 50:
        return "green"
    if 85 < h <= 130 and s > 50:
        return "blue"
    if 130 < h <= 165 and s > 50:
        return "violet"

    return "body"


def snap_to_e12(val):
    if val <= 0:
        return 220
    best = min(STANDARD_E12, key=lambda x: abs(x - val))
    return best


def format_ohms(ohms, tol="5%"):
    if ohms < 1000:
        formatted = f"{int(ohms)}Ω"
    elif ohms < 1000000:
        val = ohms / 1000.0
        formatted = f"{val:g}kΩ"
    else:
        val = ohms / 1000000.0
        formatted = f"{val:g}MΩ"

    return f"{formatted} ±{tol}", formatted


class ResistorDecoder:
    def __init__(self):
        pass

    def decode(self, crop):
        if crop is None or crop.shape[0] < 6 or crop.shape[1] < 12:
            return None

        h, w = crop.shape[:2]
        if h > w:
            crop = cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE)
            h, w = crop.shape[:2]

        # Resistor body center strip
        y1, y2 = max(0, int(h * 0.20)), min(h, int(h * 0.80))
        x1, x2 = max(0, int(w * 0.10)), min(w, int(w * 0.90))
        body = crop[y1:y2, x1:x2]

        if body.shape[0] < 3 or body.shape[1] < 8:
            return None

        profile = np.median(body, axis=0)
        column_colors = [classify_pixel_color(col) for col in profile]

        clusters = []
        curr_color = None
        curr_len = 0
        min_cluster = max(2, int(len(column_colors) * 0.03))

        for c in column_colors:
            if c == curr_color:
                curr_len += 1
            else:
                if curr_color and curr_color != "body" and curr_len >= min_cluster:
                    clusters.append((curr_color, curr_len))
                curr_color = c
                curr_len = 1
        if curr_color and curr_color != "body" and curr_len >= min_cluster:
            clusters.append((curr_color, curr_len))

        bands = [c[0] for c in clusters]

        if len(bands) >= 3 and (bands[0] in ["gold", "silver"]):
            bands.reverse()

        if len(bands) < 3:
            return None

        if bands[-1] in COLOR_TOLERANCES:
            tol = COLOR_TOLERANCES[bands[-1]]
            digits_bands = bands[:-1]
        else:
            tol = "5%"
            digits_bands = bands

        if len(digits_bands) >= 2 and digits_bands[0] in COLOR_DIGITS and digits_bands[1] in COLOR_DIGITS:
            d1 = COLOR_DIGITS[digits_bands[0]]
            d2 = COLOR_DIGITS[digits_bands[1]]
            mult_band = digits_bands[2] if len(digits_bands) > 2 else "brown"
            mult = COLOR_MULTIPLIERS.get(mult_band, 10)
            raw_ohms = (d1 * 10 + d2) * mult
            snapped = snap_to_e12(raw_ohms)

            full_label, short_label = format_ohms(snapped, tol)
            return {
                "ohms": snapped,
                "formatted": full_label,
                "raw_value": short_label,
                "bands": bands
            }

        return None
