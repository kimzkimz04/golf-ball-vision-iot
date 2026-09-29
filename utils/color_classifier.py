"""Phase 4: แยกสีของลูกกอล์ฟ (นีออน / ขาว / ชมพู)

หลักการ:
  1. ตัดเอาเฉพาะเนื้อในของลูกบอลออกมา (ไม่เอาขอบ เพราะขอบปนสีพื้นหลัง)
  2. แปลงเป็น HSV ซึ่งแยก "สี" (Hue) ออกจาก "ความสว่าง" (Value) ได้
     ทำให้ทนต่อแสงที่เปลี่ยนไปมากกว่า RGB
  3. นับว่าพิกเซลตกอยู่ในช่วงสีไหนมากที่สุด สีนั้นคือคำตอบ
"""

import cv2
import numpy as np


def ball_mask(shape, x: int, y: int, r: int, inner_ratio: float = 0.7):
    """สร้างหน้ากากวงกลมเฉพาะเนื้อในของลูกบอล

    ใช้แค่ 70% ของรัศมี เพราะขอบลูกบอลมักมีเงาและสีพื้นหลังปนเข้ามา
    """
    mask = np.zeros(shape[:2], np.uint8)
    cv2.circle(mask, (x, y), max(1, int(r * inner_ratio)), 255, -1)
    return mask


def measure_hsv(frame, x: int, y: int, r: int):
    """วัดค่าสีเฉลี่ย (ค่ากลาง) ของลูกบอล คืนค่า (H, S, V)"""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = ball_mask(frame.shape, x, y, r)
    pixels = hsv[mask > 0]
    if pixels.size == 0:
        return (0, 0, 0)
    # ใช้ค่ากลาง (median) ไม่ใช่ค่าเฉลี่ย เพราะทนต่อจุดสะท้อนแสงจ้าได้ดีกว่า
    return tuple(int(v) for v in np.median(pixels, axis=0))


def classify_color(frame, x: int, y: int, r: int, color_ranges, min_ratio: float = 0.25):
    """บอกว่าลูกบอลนี้สีอะไร

    คืนค่า (ชื่อสี, สัดส่วนพิกเซลที่ตรงกับสีนั้น, ค่า HSV ที่วัดได้)
    ถ้าไม่มีสีไหนเข้าเกณฑ์เลย จะคืนชื่อว่า "Unknown"
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = ball_mask(frame.shape, x, y, r)
    total = int(np.count_nonzero(mask))
    if total == 0:
        return "Unknown", 0.0, (0, 0, 0)

    scores = {}
    for name, ranges in color_ranges.items():
        matched = np.zeros(mask.shape, np.uint8)
        # บางสี (เช่นชมพู) คร่อมขอบของวงล้อสี ต้องใช้หลายช่วงรวมกัน
        for lo, hi in ranges:
            matched |= cv2.inRange(hsv, np.array(lo), np.array(hi))
        matched = cv2.bitwise_and(matched, mask)
        scores[name] = np.count_nonzero(matched) / total

    best = max(scores, key=scores.get)
    measured = measure_hsv(frame, x, y, r)
    if scores[best] < min_ratio:
        return "Unknown", scores[best], measured
    return best, scores[best], measured


def color_scores(frame, x: int, y: int, r: int, color_ranges):
    """คืนคะแนนของทุกสี ไว้ใช้ตอนปรับแต่งช่วงสี (โหมด calibrate)"""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = ball_mask(frame.shape, x, y, r)
    total = max(1, int(np.count_nonzero(mask)))
    out = {}
    for name, ranges in color_ranges.items():
        matched = np.zeros(mask.shape, np.uint8)
        for lo, hi in ranges:
            matched |= cv2.inRange(hsv, np.array(lo), np.array(hi))
        out[name] = np.count_nonzero(cv2.bitwise_and(matched, mask)) / total
    return out
