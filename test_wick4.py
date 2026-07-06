import cv2
import numpy as np

img = cv2.imread("charts/chat1.png")
h, w = img.shape[:2]
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

green_mask = cv2.inRange(hsv, np.array([70, 60, 60]), np.array([100, 255, 255]))
red_mask1 = cv2.inRange(hsv, np.array([0, 60, 60]), np.array([10, 255, 255]))
red_mask2 = cv2.inRange(hsv, np.array([170, 60, 60]), np.array([180, 255, 255]))
red_mask = red_mask1 | red_mask2
combined = (green_mask > 0) | (red_mask > 0)

xs_with_candles = []
for x in range(50, w-50):
    col = combined[:, x]
    if np.any(col[50:]):
        xs_with_candles.append(x)

groups = []
if xs_with_candles:
    current = [xs_with_candles[0]]
    for x in xs_with_candles[1:]:
        if x - current[-1] <= 3:
            current.append(x)
        else:
            groups.append(current)
            current = [x]
    groups.append(current)

for group in groups[:5]:
    x_start = group[0]
    x_end = group[-1]
    cx = (x_start + x_end) // 2
    green_count = np.sum(green_mask[:, x_start:x_end+1])
    red_count = np.sum(red_mask[:, x_start:x_end+1])
    direction = "bullish" if green_count >= red_count else "bearish"

    ys_with_color = []
    for y in range(50, h-50):
        if np.any(combined[y, x_start:x_end+1]):
            ys_with_color.append(y)

    if not ys_with_color:
        continue

    total_top = min(ys_with_color)
    total_bot = max(ys_with_color)

    body_top = total_bot
    body_bot = total_top
    for y in ys_with_color:
        col_count = np.sum(combined[y, x_start:x_end+1])
        if col_count >= 4:
            if y < body_top:
                body_top = y
            if y > body_bot:
                body_bot = y

    if body_top > body_bot:
        body_top = total_top
        body_bot = total_bot

    print(f"Candle x~{cx} ({x_start}-{x_end}): {direction}")
    print(f"  Total: y=[{total_top},{total_bot}] ({(total_bot-total_top)}px)")
    print(f"  Body:  y=[{body_top},{body_bot}] ({(body_bot-body_top)}px)")
    print(f"  Upper: {total_top}->{body_top} ({(body_top-total_top)}px)")
    print(f"  Lower: {body_bot}->{total_bot} ({(total_bot-body_bot)}px)")
    print(f"  Width: {x_end-x_start+1}px")
    print()

print(f"Total groups found: {len(groups)}")
print(f"Sample of group x positions:")
for g in groups[::10]:
    print(f"  {g[0]}-{g[-1]} (center {(g[0]+g[-1])//2})")
