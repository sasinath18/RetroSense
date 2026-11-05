"""Experimental analog dial reader using OpenCV; requires a clear, front-facing circular gauge."""
import math
import cv2
import numpy as np

class GaugeReadError(ValueError):
    pass

def _wrap_delta(angle, start):
    return (angle - start + 360.0) % 360.0

def angle_to_value(pointer_angle, min_value, max_value, start_angle, end_angle):
    """Map an image-coordinate angle onto a calibrated dial sweep."""
    if max_value <= min_value:
        raise GaugeReadError("Maximum value must be greater than minimum value.")
    sweep = _wrap_delta(end_angle, start_angle)
    if sweep < 1 or sweep > 359:
        raise GaugeReadError("Invalid calibration angles.")
    position = _wrap_delta(pointer_angle, start_angle)
    fraction = position / sweep
    if fraction > 1.0:
        raise GaugeReadError("Pointer appears outside the calibrated scale. Check start/end angles.")
    return min_value + fraction * (max_value - min_value)


def read_analog_gauge(image_bytes, min_value, max_value, start_angle=135.0, end_angle=45.0):
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        raise GaugeReadError("Could not decode image. Upload a valid JPG or PNG.")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (9, 9), 1.5)
    h, w = gray.shape
    circles = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, dp=1.2,
        minDist=max(30, min(h, w)//3), param1=120, param2=38,
        minRadius=max(20, min(h, w)//8), maxRadius=min(h, w)//2)
    if circles is None:
        raise GaugeReadError("Gauge dial circle not detected. Use a clear, front-facing image.")
    cx, cy, radius = map(float, sorted(circles[0], key=lambda c:c[2], reverse=True)[0])
    edges = cv2.Canny(gray, 45, 130)
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=max(25,int(radius*.22)),
        minLineLength=max(20,int(radius*.28)), maxLineGap=max(8,int(radius*.08)))
    if lines is None:
        raise GaugeReadError("No pointer-like line detected in the dial.")
    candidates=[]
    for x1,y1,x2,y2 in lines[:,0,:]:
        d1=math.hypot(x1-cx,y1-cy); d2=math.hypot(x2-cx,y2-cy)
        nx,ny,fx,fy=(x1,y1,x2,y2) if d1<d2 else (x2,y2,x1,y1)
        near,far=min(d1,d2),max(d1,d2)
        if near>radius*.23 or far<radius*.35 or far>radius*1.08: continue
        angle=math.degrees(math.atan2(fy-cy,fx-cx))%360
        candidates.append((far-near-near*.3,angle,far))
    if not candidates:
        raise GaugeReadError("Could not isolate a pointer from dial markings. Try a sharper image.")
    _,pointer_angle,pointer_length=max(candidates)
    value = angle_to_value(pointer_angle, min_value, max_value, start_angle, end_angle)
    return {"value":round(value,2),
        "pointer_angle_deg":round(pointer_angle,2),
        "dial":{"center_x":round(cx,1),"center_y":round(cy,1),"radius":round(radius,1)},
        "confidence":"experimental",
        "note":"Baseline Hough-line estimate. Verify against a calibrated reference."}
