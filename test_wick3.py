import cv2
import numpy as np

img = cv2.imread("charts/chat1.png")
h, w = img.shape[:2]
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

# Create color masks without erosion
green_mask = cv2.inRange(hsv, np.array([70, 60, 60]), np.array([100, 255, 255]))
red_mask1 = cv2.inRange(hsv, np.array([0, 60, 60]), np.array([10, 255, 255]))
red_mask2 = cv2.inRange(hsv, np.array([170, 60, 60]), np.array([180, 255, 255]))
red_mask = cv2.bitwise_or(red_mask1, red_mask2)

# For each column, find connected components of colored pixels (candles)
# A candle = a contiguous vertical run of colored pixels
# The wick = the thin parts (maybe 1-2 px wide) above/below the body
# The body = the thick part (maybe 5-9 px wide)

print("=== Analyzing vertical runs for each candle column ===")
# Get all columns that have candle pixels
for x in range(50, w-50):
    green_run = np.where(green_mask[:, x] > 0)[0]
    red_run = np.where(red_mask[:, x] > 0)[0]
    
    if len(green_run) > 0:
        # Find connected components in this column
        runs = []
        start = green_run[0]
        for i in range(1, len(green_run)):
            if green_run[i] - green_run[i-1] > 2:
                runs.append((start, green_run[i-1]))
                start = green_run[i]
        runs.append((start, green_run[-1]))
        
        if len(runs) >= 1:
            for r in runs:
                length = r[1] - r[0]
                if length > 5:  # meaningful candle
                    print(f"x={x}: green run y=[{r[0]},{r[1]}] len={length}")
    
    if len(red_run) > 0:
        runs = []
        start = red_run[0]
        for i in range(1, len(red_run)):
            if red_run[i] - red_run[i-1] > 2:
                runs.append((start, red_run[i-1]))
                start = red_run[i]
        runs.append((start, red_run[-1]))
        
        if len(runs) >= 1:
            for r in runs:
                length = r[1] - r[0]
                if length > 5:
                    print(f"x={x}: red run y=[{r[0]},{r[1]}] len={length}")

print("\n=== Checking width variation along candle height ===")
for test_x in [64, 104, 120, 152, 200, 300, 400, 500, 600, 700]:
    # For each row, count how many colored pixels in a window around test_x
    for y in range(50, h-50):
        window = green_mask[y, max(0,test_x-15):min(w,test_x+15)]
        if np.any(window > 0):
            width = np.sum(window > 0)
            # Check if width changes dramatically
            if width <= 3:  # thin = wick
                print(f"  x={test_x}: WICK at y={y}, width={width}")
        window_r = red_mask[y, max(0,test_x-15):min(w,test_x+15)]
        if np.any(window_r > 0):
            width = np.sum(window_r > 0)
            if width <= 3:
                print(f"  x={test_x}: RED WICK at y={y}, width={width}")
