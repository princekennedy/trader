_cv2_import_error = None
try:
    import cv2
except Exception as _cv2_exc:
    cv2 = None
    _cv2_import_error = str(_cv2_exc)

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
        if cv2 is None:
            raise RuntimeError(
                "OpenCV (cv2) is not available. "
                f"Import error: {_cv2_import_error}"
            )
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

    def _is_axis_column(self, combined, top_margin, h):
        col_vertical = np.sum(combined[top_margin:, :] > 0, axis=0)
        total_rows = h - top_margin
        vert_ratio = col_vertical / max(total_rows, 1)
        return vert_ratio

    def _find_candles(self, combined, green_mask, red_mask, h, w):
        top_margin = int(h * 0.06)

        col_density = np.zeros(w, dtype=np.int32)
        for x in range(0, w):
            col_density[x] = np.sum(combined[top_margin:, x])

        vert_ratio = self._is_axis_column(combined, top_margin, h)

        density_smooth = np.convolve(col_density, np.ones(5) / 5, mode="same")

        density_smooth[vert_ratio > 0.25] *= 0.1

        edge_zone = int(w * 0.04)
        density_smooth[:edge_zone] *= 0.05
        density_smooth[-edge_zone:] *= 0.05

        min_height = np.max(density_smooth) * 0.08
        min_distance = max(5, w // 200)

        peaks, _ = find_peaks(
            density_smooth,
            height=min_height,
            distance=min_distance,
            prominence=min_height * 0.5,
        )
        if len(peaks) < 2:
            peaks = [np.argmax(density_smooth)] if len(peaks) == 0 else peaks
            typical_spacing = w // 40
        else:
            typical_spacing = int(np.median(np.diff(peaks)))

        min_body_h = max(5, h // 100)

        candles = []
        for px in peaks:
            half_w = max(typical_spacing // 2, 6)
            x_start = max(0, px - half_w)
            x_end = min(w - 1, px + half_w)

            green_px = np.sum(green_mask[:, x_start:x_end + 1])
            red_px = np.sum(red_mask[:, x_start:x_end + 1])

            body_info = self._find_body_region(combined, x_start, x_end, top_margin, h)
            if body_info is None:
                continue

            body_length = body_info["body_bottom"] - body_info["body_top"]
            if body_length < min_body_h:
                continue

            total_length = body_info["wick_bottom"] - body_info["wick_top"]
            width_sep = body_info["max_width"] / max(body_info["wick_max_width"], 1)
            width_clarity = min(1.0, width_sep / 3.0)
            body_ratio = body_length / max(total_length, 1)
            bf = max(0.0, min(1.0, 1.0 - abs(body_ratio - 0.5) * 1.5))
            confidence = round(width_clarity * 0.6 + bf * 0.4, 3)

            candles.append({
                "direction": "bullish" if green_px >= red_px else "bearish",
                "x": px,
                "body_top": body_info["body_top"],
                "body_bottom": body_info["body_bottom"],
                "body_height": body_length,
                "wick_top": body_info["wick_top"],
                "wick_bottom": body_info["wick_bottom"],
                "width": int(x_end - x_start + 1),
                "area": int(body_info["area"]),
                "confidence": confidence,
            })

        if not candles:
            return candles

        candles.sort(key=lambda c: c["x"])
        if len(candles) > 1:
            survivor_spacing = int(np.median(np.diff([c["x"] for c in candles])))
        else:
            survivor_spacing = 15
        merge_gap = max(survivor_spacing, 10)

        kept = [candles[0]]
        for c in candles[1:]:
            if c["x"] - kept[-1]["x"] >= merge_gap:
                kept.append(c)
            elif c["area"] > kept[-1]["area"]:
                kept[-1] = c
        candles = kept

        candles = [
            c for c in candles
            if c["wick_bottom"] - c["wick_top"] > 5
            and c["confidence"] > 0.05
            and c["wick_bottom"] - c["wick_top"] < h * 0.5
        ]

        return candles

    def _find_body_region(self, combined, x_start, x_end, top_margin, h):
        row_widths = np.zeros(h, dtype=np.int32)
        for y in range(top_margin, h):
            row_widths[y] = int(np.sum(combined[y, x_start:x_end + 1]))

        all_positive = np.where(row_widths > 0)[0]
        if len(all_positive) < 3:
            return None

        max_w = float(np.max(row_widths))
        if max_w < 2:
            return None

        sig_rows = row_widths >= 3
        changes = np.diff(np.concatenate(([0], sig_rows.astype(int), [0])))
        starts = np.where(changes == 1)[0]
        ends = np.where(changes == -1)[0]

        if len(starts) == 0:
            return None

        blocks = [(int(s), int(e) - 1) for s, e in zip(starts, ends)]
        blocks.sort(key=lambda b: b[1] - b[0], reverse=True)

        cluster_top, cluster_bot = blocks[0]
        if cluster_bot - cluster_top < 3:
            return None

        profile = row_widths[cluster_top:cluster_bot + 1].astype(np.float64)
        local_max = np.max(profile)
        if local_max < 2:
            return None

        thin_rows = profile[profile < local_max * 0.4]
        wick_max_w = float(np.median(thin_rows)) if len(thin_rows) > 0 else local_max * 0.3

        threshold = max(local_max * 0.45, 2.0)
        body_mask = profile >= threshold
        b_changes = np.diff(np.concatenate(([0], body_mask.astype(int), [0])))
        b_starts = np.where(b_changes == 1)[0]
        b_ends = np.where(b_changes == -1)[0]

        if len(b_starts) == 0:
            mid = len(profile) // 2
            body_top_local = max(0, mid - 1)
            body_bot_local = min(len(profile) - 1, mid + 1)
        else:
            b_regions = [(int(s), int(e) - 1) for s, e in zip(b_starts, b_ends)]
            center = len(profile) // 2
            b_regions.sort(key=lambda r: abs((r[0] + r[1]) // 2 - center))
            best_r = b_regions[0]
            largest = max(b_regions, key=lambda r: r[1] - r[0])
            if best_r[1] - best_r[0] >= (largest[1] - largest[0]) * 0.4:
                body_top_local, body_bot_local = best_r
            else:
                body_top_local, body_bot_local = largest

        body_top = cluster_top + body_top_local
        body_bot = cluster_top + body_bot_local

        if body_top >= body_bot:
            mid = (cluster_top + cluster_bot) // 2
            body_top = max(cluster_top, mid - 1)
            body_bot = min(cluster_bot, mid + 1)

        wick_top = cluster_top
        wick_bot = cluster_bot

        while wick_top > top_margin and row_widths[wick_top - 1] >= 1:
            wick_top -= 1
        while wick_bot + 1 < h and row_widths[wick_bot + 1] >= 1:
            wick_bot += 1

        total_area = int(np.sum(profile))

        return {
            "wick_top": wick_top,
            "wick_bottom": wick_bot,
            "body_top": body_top,
            "body_bottom": body_bot,
            "body_height": body_bot - body_top,
            "max_width": int(local_max),
            "wick_max_width": wick_max_w,
            "area": total_area,
        }

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
        candle_count = len(candles)
        min_good = 20
        max_good = 150
        if candle_count >= max_good:
            coverage = 1.0
        elif candle_count <= min_good:
            coverage = candle_count / max_good
        else:
            coverage = 0.5 + 0.5 * (candle_count - min_good) / (max_good - min_good)
        coverage = min(1.0, coverage)
        body_ratios = [
            abs(c["body_bottom"] - c["body_top"]) / max(c["wick_bottom"] - c["wick_top"], 1)
            for c in candles
        ]
        avg_body_ratio = float(np.mean(body_ratios)) if body_ratios else 0
        body_ratio_score = min(1.0, avg_body_ratio * 3.0)
        return round(avg_conf * 0.5 + coverage * 0.3 + body_ratio_score * 0.2, 2)
