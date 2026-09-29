"""Phase 3: แยกว่าเป็น "ลูกกอล์ฟ" หรือ "ไม่ใช่ลูกกอล์ฟ"

ใช้ 2 สัญญาณร่วมกัน เพราะสัญญาณเดียวไม่พอ:

  1. พื้นผิว (texture) - ลูกกอล์ฟมีหลุมเล็ก ๆ ทั่วลูก ทำให้ความสว่างกระเพื่อม
     ถี่ ๆ ส่วนลูกปิงปองเรียบสนิท และลูกเทนนิสมีขนฟูที่ดูเนียนกว่าหลุมกอล์ฟ
     วัดด้วยความแปรปรวนของ Laplacian ซึ่งไวต่อการเปลี่ยนความสว่างระยะสั้น

  2. ขนาด (รัศมี) - ลูกเทนนิสใหญ่กว่าลูกกอล์ฟชัดเจน (67 มม. เทียบกับ 42.7 มม.)
     ใช้ได้เมื่อระยะจากกล้องถึงลูกบอลคงที่เท่านั้น

หมายเหตุ: ลูกปิงปอง (40 มม.) ขนาดเกือบเท่าลูกกอล์ฟ จึงต้องพึ่งพื้นผิวเป็นหลัก
"""

import cv2
import numpy as np


def _ball_crop(frame, x: int, y: int, r: int, size: int = 128):
    """ตัดเนื้อในลูกบอลแล้วย่อให้เท่ากันทุกลูก คืนค่า (ภาพที่ย่อแล้ว, หน้ากากวงกลม)

    ที่ต้องย่อให้เท่ากันก่อน เพราะลูกที่อยู่ใกล้กล้องมีพิกเซลมากกว่า
    ถ้าไม่ย่อจะเทียบค่ากันไม่ได้
    """
    inner = max(4, int(r * 0.7))
    h, w = frame.shape[:2]
    x0, x1 = max(0, x - inner), min(w, x + inner)
    y0, y1 = max(0, y - inner), min(h, y + inner)
    if x1 - x0 < 8 or y1 - y0 < 8:
        return None, None

    crop = cv2.resize(frame[y0:y1, x0:x1], (size, size), interpolation=cv2.INTER_AREA)
    mask = np.zeros((size, size), np.uint8)
    cv2.circle(mask, (size // 2, size // 2), int(size * 0.47), 255, -1)
    return crop, mask


def texture_score(frame, x: int, y: int, r: int, size: int = 128) -> float:
    """วัดความ "ขรุขระ" ของผิวลูกบอล ยิ่งมากยิ่งมีลวดลายถี่"""
    crop, mask = _ball_crop(frame, x, y, r, size)
    if crop is None:
        return 0.0
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F)[mask > 0].var())


def ball_features(frame, x: int, y: int, r: int, size: int = 128):
    """วัดคุณสมบัติผิวลูกบอลหลายตัวพร้อมกัน ไว้ใช้หาสัญญาณที่แยกลูกบอลได้

    ตัวที่วัด:
      texture      - ความขรุขระ (ความแปรปรวนของ Laplacian) หลุมลูกกอล์ฟควรสูง
      edge_density - สัดส่วนพิกเซลที่เป็นขอบ ลายหลุมทำให้มีขอบเยอะ
      bright_frac  - สัดส่วนพิกเซลที่สว่างจัด ลูกผิวมันเงาจะมีจุดสะท้อนแสงเด่น
      v_std        - การกระจายของความสว่าง ลูกผิวด้านจะไล่เฉดนุ่มกว่าลูกผิวมัน
    """
    crop, mask = _ball_crop(frame, x, y, r, size)
    if crop is None:
        return {"texture": 0.0, "edge_density": 0.0, "bright_frac": 0.0, "v_std": 0.0}

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    value = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)[:, :, 2]
    inside = mask > 0
    total = max(1, int(np.count_nonzero(mask)))

    edges = cv2.Canny(gray, 50, 150)
    v = value[inside].astype(float)

    return {
        "texture": float(cv2.Laplacian(gray, cv2.CV_64F)[inside].var()),
        "edge_density": float(np.count_nonzero(cv2.bitwise_and(edges, mask)) / total),
        "bright_frac": float((v >= 245).mean()),
        "v_std": float(v.std()),
    }


def is_golf_ball(frame, x: int, y: int, r: int, min_texture: float,
                 radius_range=None, texture=None):
    """ตัดสินว่าวงกลมนี้เป็นลูกกอล์ฟหรือไม่

    คืนค่า (เป็นลูกกอล์ฟหรือไม่, เหตุผล, คะแนนพื้นผิว)
    ส่ง texture ที่วัดไว้แล้วเข้ามาได้ จะได้ไม่ต้องวัดซ้ำ
    """
    if texture is None:
        texture = texture_score(frame, x, y, r)

    if radius_range is not None:
        lo, hi = radius_range
        if r < lo:
            return False, "too small", texture
        if r > hi:
            return False, "too big", texture

    if texture < min_texture:
        # ผิวเรียบเกินกว่าจะเป็นลูกกอล์ฟที่มีหลุมทั่วลูก
        return False, "too smooth", texture

    return True, "ok", texture
