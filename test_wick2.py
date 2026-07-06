import cv2
import numpy as np

img = cv2.imread("charts/chat1.png")
h, w = img.shape[:2]
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

# Check multiple candle x-positions for wick structure
# Find all candle x positions from the extraction
for test_cx in [44, 64, 104, 120, 152, 168, 200, 250, 300, 400, 500, 600, 700, 800]:
    # Find non-white pixels in a column strip
    strip = img[:, max(0,test_cx-4):min(w,test_cx+5)]
    non_white_rows = []
    for y in range(h):
        row = strip[y - (test_cx-4) if test_cx-4 >= 0 else 0]
        # Actually simpler:
        pass
    
    # Just check if there are any non-white, non-green, non-red pixels (potential wicks)
    # in the column above y=200 (top portion of the chart)
    for y in range(0, min(200, h)):
        for dx in range(-3, 4):
            px = test_cx + dx
            if 0 <= px < w:
                b, g, r = img[y, px]
                # Check if it's a dark pixel (potential wick) that's not green or red
                is_green = g > 100 and r < 100 and b < 100
                is_red = r > 150 and g < 100 and b < 100
                is_dark = (b < 100 and g < 100 and r < 100) or (b < 50 and g < 50 and r > 100)
                if is_dark and not is_green and not is_red:
                    print(f"Dark pixel at ({px},{y}): BGR={img[y,px]}")

# Let me check: what do wicks actually look like in the image?
# Let me look at a few columns across the chart for any dark pixels
print("\n=== Finding all dark pixels in the chart area ===")
for y in range(50, h-50):
    for x in range(50, w-50):
        b, g, r = img[y, x]
        # Look for dark gray/black pixels (usually wicks or borders)
        if b < 60 and g < 60 and r < 60:
            print(f"Dark pixel at ({x},{y}): BGR=({b},{g},{r})")
            break  # just find a few
    else:
        continue
    break

# Maybe wicks are the same green/red but just thinner
# Check: scan vertically through a few candle columns and look at the color intensity
print("\n=== Color intensity scan through candle columns ===")
for test_cx in [64, 120, 200, 400]:
    print(f"\nColumn x={test_cx}:")
    in_candle = False
    for y in range(50, h-50):
        b, g, r = img[y, test_cx]
        is_candle_color = (g > 100 and r < 100 and b < 100) or (r > 150 and g < 100)
        if is_candle_color and not in_candle:
            print(f"  START at y={y}: BGR=({b},{g},{r})")
            in_candle = True
        elif not is_candle_color and in_candle:
            print(f"  END at y={y}: BGR=({b},{g},{r})")
            in_candle = False
