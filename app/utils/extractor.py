try:
    import cv2
except ImportError:
    cv2 = None

import numpy as np
from dataclasses import dataclass, field
from typing import Optional
from scipy.signal import find_peaks


@dataclass
class ExtractionResult:
    symbol: str = ""
    timeframe: str = ""
    candles: list = field(default_factory=list)
    quality_score: float = 0.0


class ChartExtractor:
    GREEN_LOWER = np.array([70, 60, 60])
    GREEN_UPPER = np.array([100, 255, 255])
    RED_LOWER1 = np.array([0, 60, 60])
    RED_UPPER1 = np.array([10, 255, 255])
    RED_LOWER2 = np.array([170, 60, 60])
    RED_UPPER2 = np.array([180, 255, 255])

    def __init__(self, price_base: float = 100.0, price_variation: float = 0.10):
        self.price_base = price_base
        self.price_variation = price_variation

    def extract(self, image_path: str) -> ExtractionResult:
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Cannot read image: {image_path}")
        return self._process(img)

    def extract_from_bytes(self, data: bytes) -> ExtractionResult:
        arr = np.frombuffer(data, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Cannot decode image from bytes")
        return self._process(img)

    def extract_from_array(self, img: np.ndarray) -> ExtractionResult:
        return self._process(img)

    def _process(self, img: np.ndarray) -> ExtractionResult:
        result = ExtractionResult()
        h, w = img.shape[:2]
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        green_mask = cv2.inRange(hsv, self.GREEN_LOWER, self.GREEN_UPPER)
        red_mask = cv2.inRange(hsv, self.RED_LOWER1, self.RED_UPPER1)
        red_mask |= cv2.inRange(hsv, self.RED_LOWER2, self.RED_UPPER2)
        combined = (green_mask > 0) | (red_mask > 0)

        candles = self._find_candles(combined, green_mask, red_mask, h, w)
        if not candles:
            return result

        self._assign_ohlc(candles)
        self._normalize_prices(candles)
        result.candles = candles
        result.quality_score = self._compute_quality(candles)
        return result

    def _find_candles(self, combined, green_mask, red_mask, h, w):
        top_margin = int(h * 0.06)

        col_density = np.zeros(w, dtype=np.int32)
        for x in range(0, w):
            col_density[x] = np.sum(combined[top_margin:, x])

        density_smooth = np.convolve(col_density, np.ones(5) / 5, mode="same")

        min_height = np.max(density_smooth) * 0.08
        min_distance = max(5, w // 200)

        peaks, properties = find_peaks(
            density_smooth,
            height=min_height,
            distance=min_distance,
            prominence=min_height * 0.5,
        )

        if len(peaks) == 0:
            peaks = [np.argmax(density_smooth)]

        typical_spacing = int(np.median(np.diff(peaks))) if len(peaks) > 1 else 11

        candles = []
        for px in peaks:
            half_w = max(typical_spacing // 2, 4)
            x_start = max(0, px - half_w)
            x_end = min(w - 1, px + half_w)

            green_px = np.sum(green_mask[:, x_start:x_end + 1])
            red_px = np.sum(red_mask[:, x_start:x_end + 1])
            direction = "bullish" if green_px >= red_px else "bearish"

            y_min = h
            y_max = 0
            for y in range(top_margin, h):
                if np.any(combined[y, x_start:x_end + 1]):
                    if y < y_min:
                        y_min = y
                    y_max = y

            if y_max <= y_min or y_max - y_min < 3:
                continue

            col_counts = {}
            for y in range(y_min, y_max + 1):
                cc = int(np.sum(combined[y, x_start:x_end + 1]))
                if cc > 0:
                    col_counts[y] = cc

            body_top = y_max
            body_bot = y_min
            for y, cc in col_counts.items():
                if cc >= 4:
                    if y < body_top:
                        body_top = y
                    if y > body_bot:
                        body_bot = y

            if body_top > body_bot:
                body_top = y_min
                body_bot = y_max

            total_area = sum(col_counts.values())
            avg_body_width = np.mean([
                cc for cc in col_counts.values() if cc >= 4
            ]) if any(cc >= 4 for cc in col_counts.values()) else 1

            total_length = y_max - y_min
            body_length = body_bot - body_top
            confidence = min(1.0, body_length / 200.0) * min(1.0, avg_body_width / 7.0)

            candles.append({
                "direction": direction,
                "x": int(px),
                "body_top": body_top,
                "body_bottom": body_bot,
                "body_height": body_length,
                "wick_top": y_min,
                "wick_bottom": y_max,
                "width": int(x_end - x_start + 1),
                "area": int(total_area),
                "confidence": round(confidence, 3),
            })

        candles.sort(key=lambda c: c["x"])

        edge_margin = int(w * 0.02)
        valid_x_range = (edge_margin, w - edge_margin)

        candles = [
            c for c in candles
            if valid_x_range[0] < c["x"] < valid_x_range[1]
            and c["wick_bottom"] - c["wick_top"] > 5
            and c["confidence"] > 0.05
        ]

        return candles

    def _assign_ohlc(self, candles):
        for c in candles:
            bt = c["body_top"]
            bb = c["body_bottom"]
            wt = c["wick_top"]
            wb = c["wick_bottom"]
            if c["direction"] == "bullish":
                o, cl = bb, bt
            else:
                o, cl = bt, bb
            c["open"] = float(o)
            c["close"] = float(cl)
            c["high"] = float(wt)
            c["low"] = float(wb)
            c["body"] = float(abs(bb - bt))
            c["upper_wick"] = float(abs(bt - wt))
            c["lower_wick"] = float(abs(wb - bb))

    def _normalize_prices(self, candles):
        if not candles:
            return
        px_all = []
        for c in candles:
            px_all.extend([c["high"], c["low"], c["open"], c["close"]])
        px_min = min(px_all)
        px_max = max(px_all)
        px_rng = px_max - px_min if px_max != px_min else 1
        pb = self.price_base
        pr = pb * self.price_variation

        for c in candles:
            for k in ("high", "low", "open", "close"):
                ratio = (c[k] - px_min) / px_rng
                c[k] = round(pb + pr * (1.0 - ratio), 2)
            c["body"] = round(abs(c["close"] - c["open"]), 2)
            c["upper_wick"] = round(
                abs(c["high"] - max(c["open"], c["close"])), 2
            )
            c["lower_wick"] = round(
                abs(min(c["open"], c["close"]) - c["low"]), 2
            )

    def _compute_quality(self, candles):
        if not candles:
            return 0.0
        confs = [c["confidence"] for c in candles]
        avg_conf = float(np.mean(confs))
        coverage = min(1.0, len(candles) / 80.0)
        return round(avg_conf * 0.5 + coverage * 0.5, 2)
