import cv2
import numpy as np

img = cv2.imread("charts/chat1.png")
h, w = img.shape[:2]
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

# Pick a known good candle - candle at x=104 had conf 1.0, body from y=516 to y=610
# Let's look around that area
cx = 104   # center x
by_top = 516
by_bot = 610

print(f"Candle at x={cx}, body y=[{by_top},{by_bot}]")
print("Scanning upwards from body top:")
for y in range(by_top, max(0, by_top - 60), -1):
    for dx in range(-4, 5):
        px = img[y, cx+dx]
        if any(c < 200 for c in px):
            print(f"  y={y}, dx={dx}: BGR={px} HSV={hsv[y, cx+dx]} gray={gray[y, cx+dx]}")
            break

print("\nScanning downwards from body bottom:")
for y in range(by_bot, min(h-1, by_bot + 60)):
    for dx in range(-4, 5):
        px = img[y, cx+dx]
        if any(c < 200 for c in px):
            print(f"  y={y}, dx={dx}: BGR={px} HSV={hsv[y, cx+dx]} gray={gray[y, cx+dx]}")
            break

# Also check what the wicks look like more broadly - look at ALL pixel colors in the candle column
print("\nAll non-white pixels in the candle column (x=100-108):")
for y in range(450, 650):
    strip = img[y, 100:109]
    non_white = strip[(strip[:,0] < 200) | (strip[:,1] < 200) | (strip[:,2] < 200)]
    if len(non_white) > 0:
        avg = non_white.mean(axis=0)
        print(f"  y={y}: count={len(non_white)} avg_BGR={avg.round().astype(int)}")
        if len(non_white) < 3:
            print(f"    pixels: {non_white}")
