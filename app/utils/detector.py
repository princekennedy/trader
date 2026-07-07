import os

try:
    import cv2
except ImportError:
    cv2 = None

import numpy as np

MODEL_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models", "yolo26n.pt")

_model = None
_model_loaded = False


def load_model():
    global _model, _model_loaded
    if _model_loaded:
        return _model
    if not os.path.isfile(MODEL_PATH):
        _model_loaded = True
        return None
    try:
        from ultralytics import YOLO
        _model = YOLO(MODEL_PATH)
    except Exception:
        _model = None
    _model_loaded = True
    return _model


def detect_objects(image: np.ndarray, conf: float = 0.25) -> list:
    model = load_model()
    if model is None:
        return []
    results = model(image, conf=conf, verbose=False)
    detections = []
    if results and len(results) > 0:
        boxes = results[0].boxes
        if boxes is not None:
            for i in range(len(boxes)):
                x1, y1, x2, y2 = boxes.xyxy[i].tolist()
                conf_val = float(boxes.conf[i])
                cls_id = int(boxes.cls[i])
                label = model.names.get(cls_id, "unknown")
                detections.append({
                    "label": label,
                    "confidence": round(conf_val, 3),
                    "bbox": [round(x1), round(y1), round(x2), round(y2)],
                })
    return detections


def detect_on_bytes(image_data: bytes, conf: float = 0.25) -> list:
    if cv2 is None:
        return []
    arr = np.frombuffer(image_data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return []
    return detect_objects(img, conf=conf)
