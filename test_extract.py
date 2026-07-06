import json
from app.utils.extractor import ChartExtractor

ext = ChartExtractor()
result = ext.extract("charts/chat1.png")
print(f"Quality: {result.quality_score}")
print(f"Candles found: {len(result.candles)}")
for i, c in enumerate(result.candles[:10]):
    print(f"  {i}: dir={c['direction']} x={c['x']} "
          f"O={c['open']} H={c['high']} L={c['low']} C={c['close']} "
          f"body={c['body']} uw={c['upper_wick']} lw={c['lower_wick']} "
          f"conf={c['confidence']}")
print("...")
for i, c in enumerate(result.candles[-5:], len(result.candles) - 5):
    print(f"  {i}: dir={c['direction']} x={c['x']} "
          f"O={c['open']} H={c['high']} L={c['low']} C={c['close']} "
          f"body={c['body']} uw={c['upper_wick']} lw={c['lower_wick']} "
          f"conf={c['confidence']}")

with open("test_output.json", "w") as f:
    json.dump(result.candles, f, indent=2)
print("\nSaved to test_output.json")
