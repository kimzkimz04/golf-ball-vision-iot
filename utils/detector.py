"""Phase 2: ตรวจจับวัตถุทรงกลมด้วย Hough Circle Transform

หลักการทำงานแบบสั้น ๆ:
  1. แปลงภาพสีเป็นภาพขาวดำ (สีไม่ช่วยในการหาขอบ แถมช้ากว่า)
  2. เบลอภาพเพื่อลด noise ไม่งั้นจะเจอ "วงกลม" ปลอมเต็มไปหมด
  3. ให้ HoughCircles หาขอบที่โค้งเป็นวงกลม แล้วคืนตำแหน่งกับรัศมีมาให้

ยังไม่แยกว่าเป็นลูกกอล์ฟหรือไม่ - เจอกลมอะไรก็ตีกรอบหมด (ค่อยแยกใน Phase 3)
"""

import cv2
import numpy as np

FONT = cv2.FONT_HERSHEY_SIMPLEX


def preprocess(frame, blur_kernel: int = 9):
    """แปลงเป็นภาพขาวดำและเบลอ เตรียมส่งให้ HoughCircles"""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    if blur_kernel >= 3:
        # median blur ลบจุด noise เล็ก ๆ ได้ดีโดยที่ขอบวัตถุยังคมอยู่
        # ต้องเป็นเลขคี่เสมอ ใช้ | 1 บังคับให้เป็นคี่
        gray = cv2.medianBlur(gray, blur_kernel | 1)
    return gray


def preprocess_saturation(frame, blur_kernel: int = 9):
    """ดึงช่องความอิ่มตัวของสี (S ใน HSV) ออกมาเป็นภาพขาวดำ แล้วเบลอแบบเดียวกัน

    ทำไมต้องมี: บนโต๊ะไม้ ลูกชมพูกับเนื้อไม้ "สว่างเท่ากันเป๊ะ" ในภาพขาวดำ
    (วัดได้ 148 กับ 147) ขอบลูกจึงแทบหายไปทั้งลูก แต่ในช่อง S ลูกชมพูได้ 164
    ส่วนไม้ได้แค่ 40 ขอบชัดมาก ใช้หาวงกลมคู่กับภาพขาวดำแล้วรวมผลกัน
    """
    s = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)[:, :, 1]
    if blur_kernel >= 3:
        s = cv2.medianBlur(s, blur_kernel | 1)
    return s


def find_circles(gray, dp=1.2, min_dist=60, param1=100, param2=40,
                 min_radius=10, max_radius=150, method="classic"):
    """หาวงกลมในภาพขาวดำ คืนค่าเป็น list ของ (x, y, radius)

    method="classic" -> HOUGH_GRADIENT  เจอง่าย เร็ว แต่รัศมีคลาดเคลื่อนบ้าง
    method="alt"     -> HOUGH_GRADIENT_ALT  รัศมีแม่นกว่ามาก แต่ช้ากว่าเล็กน้อย
                        (โหมดนี้ param2 คือ "ความกลม" 0.0-1.0 ไม่ใช่ค่า threshold)
    """
    if method == "alt":
        circles = cv2.HoughCircles(
            gray, cv2.HOUGH_GRADIENT_ALT, dp=1.5, minDist=min_dist,
            param1=300, param2=0.85, minRadius=min_radius, maxRadius=max_radius)
    else:
        circles = cv2.HoughCircles(
            gray, cv2.HOUGH_GRADIENT, dp=dp, minDist=min_dist,
            param1=param1, param2=param2,
            minRadius=min_radius, maxRadius=max_radius)

    if circles is None:
        return []

    # ผลลัพธ์มีรูปร่าง (1, N, 3) ต้องดึงชั้นแรกออกมาก่อน
    found = np.round(circles[0]).astype(int)
    # เรียงจากวงใหญ่ไปเล็ก วงใหญ่มักคือวัตถุที่อยู่ใกล้กล้องและเราสนใจที่สุด
    return sorted((tuple(c) for c in found), key=lambda c: c[2], reverse=True)


def draw_circles(frame, circles):
    """วาดกรอบวงกลมและจุดศูนย์กลางลงบนภาพ"""
    for i, (x, y, r) in enumerate(circles, start=1):
        cv2.circle(frame, (x, y), r, (0, 255, 0), 2)      # เส้นรอบวง สีเขียว
        cv2.circle(frame, (x, y), 3, (0, 0, 255), -1)     # จุดศูนย์กลาง สีแดง
        label = f"#{i} r={r}"
        cv2.putText(frame, label, (x - r, y - r - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(frame, label, (x - r, y - r - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1, cv2.LINE_AA)
    return frame


def edge_support(edges, x: int, y: int, r: int, samples: int = 72,
                 tolerance_ratio: float = 0.04) -> float:
    """วัดว่า "ขอบจริง" ในภาพรองรับวงกลมนี้มากแค่ไหน คืนค่า 0.0-1.0

    HoughCircles ตัดสินจากคะแนนสะสมในตาราง ซึ่งบางครั้งให้วงกลมที่ไม่มีอยู่จริง
    (เช่น วงยักษ์ที่คร่อมทั้งภาพ) วิธีเช็กคือเดินไปตามเส้นรอบวงแล้วนับว่า
    มีกี่จุดที่ตรงกับขอบจริงในภาพ ถ้าวงกลมจริง จะมีขอบรองรับเกือบทั้งวง

    ยอมให้ขอบจริงคลาดจากเส้นรอบวงได้ตามสัดส่วนรัศมี (tolerance_ratio)
    เพราะรัศมีที่ HoughCircles ให้มาคลาด 3-5% เสมอ วงเล็ก (r~27) คลาด 1 px
    แต่พอกล้องเข้าใกล้ (r~105) คลาดได้ถึง 4-5 px ถ้าเช็กแค่ ±1 px
    ลูกบอลจริงจะได้คะแนนต่ำจนถูกตัดทิ้ง (ลูกชมพูเหลือ 0.21-0.40)
    """
    theta = np.linspace(0, 2 * np.pi, samples, endpoint=False)
    tol = max(1, int(round(r * tolerance_ratio)))
    h, w = edges.shape

    hit = np.zeros(samples, bool)
    any_inside = False
    for dr in range(-tol, tol + 1):
        xs = np.round(x + (r + dr) * np.cos(theta)).astype(int)
        ys = np.round(y + (r + dr) * np.sin(theta)).astype(int)
        inside = (xs >= 0) & (xs < w) & (ys >= 0) & (ys < h)
        if not inside.any():
            continue
        any_inside = True
        hit[inside] |= edges[ys[inside], xs[inside]] > 0
    if not any_inside:
        return 0.0

    # จุดที่ตกนอกภาพถือว่าไม่มีขอบรองรับ จึงหารด้วยจำนวนจุดทั้งหมด
    return float(np.count_nonzero(hit) / samples)


def suppress_overlaps(circles, overlap_ratio: float = 0.6):
    """ตัดวงกลมที่ซ้อนทับกัน เก็บไว้เฉพาะวงที่คะแนนดีที่สุด

    ลูกบอล 1 ลูกมักถูกจับได้หลายวงซ้อนกัน (วงพอดีลูก กับวงใหญ่เกินจริง)
    ถ้าจุดศูนย์กลางของสองวงอยู่ใกล้กันมาก ให้ถือว่าเป็นวัตถุเดียวกัน
    """
    kept = []
    for circle in sorted(circles, key=lambda c: c[3], reverse=True):
        x, y, r = circle[:3]
        duplicate = False
        for kx, ky, kr, _ in kept:
            distance = np.hypot(x - kx, y - ky)
            if distance < max(r, kr) * overlap_ratio:
                duplicate = True
                break
        if not duplicate:
            kept.append(circle)
    return kept


def verify_circles(images, circles, param1: int = 100, min_support: float = 0.45):
    """กรองวงกลมที่ HoughCircles หามาได้ ให้เหลือเฉพาะวงที่น่าเชื่อถือ

    images = ภาพขาวดำ 1 ภาพ หรือ list ของหลายภาพ (เช่น [ขาวดำ, ช่อง S])
             ถ้าส่งหลายภาพ ขอบจากทุกภาพจะถูกรวมกัน
    คืนค่าเป็น list ของ (x, y, radius, support) เรียงจากคะแนนมากไปน้อย
    """
    if not isinstance(images, (list, tuple)):
        images = [images]
    # ใช้ threshold ชุดเดียวกับที่ HoughCircles ใช้ภายใน จะได้ขอบชุดเดียวกัน
    edges = cv2.Canny(images[0], max(1, param1 // 2), max(2, param1))
    for image in images[1:]:
        edges |= cv2.Canny(image, max(1, param1 // 2), max(2, param1))
    # ขยายขอบเล็กน้อย เผื่อวงกลมที่คำนวณได้เพี้ยนไป 1-2 พิกเซล
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8))

    scored = [(x, y, r, edge_support(edges, x, y, r)) for x, y, r in circles]
    passed = [c for c in scored if c[3] >= min_support]
    return suppress_overlaps(passed), edges


def _outlined_text(frame, text, org, color, scale=0.5):
    cv2.putText(frame, text, org, FONT, scale, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(frame, text, org, FONT, scale, color, 1, cv2.LINE_AA)


def _place_label(x: int, y: int, width: int, height: int, taken, frame_h: int):
    """หาตำแหน่งวางป้ายที่ไม่ทับป้ายอื่น โดยเลื่อนลงทีละบรรทัดจนกว่าจะว่าง

    จำเป็นเมื่อลูกบอลวางชิดกัน ไม่งั้นป้ายจะซ้อนกันจนอ่านไม่ออก
    """
    step = height + 4
    for _ in range(12):
        box = (x, y - height, x + width, y)
        overlap = any(not (box[2] < t[0] or box[0] > t[2] or
                           box[3] < t[1] or box[1] > t[3]) for t in taken)
        if not overlap and y < frame_h - 2:
            taken.append(box)
            return x, y
        y += step
    taken.append((x, y - height, x + width, y))
    return x, min(y, frame_h - 2)


def draw_verified(frame, circles, labels=None):
    """วาดวงกลมพร้อมคะแนนความน่าเชื่อถือ - วงที่คะแนนสูงจะเขียวเข้ม

    labels = ข้อความเพิ่มเติมของแต่ละวง (เช่นสีที่ตรวจได้) จะวาดไว้ใต้วงกลม
    ถ้าป้ายจะทับกัน จะถูกเลื่อนลงอัตโนมัติให้อ่านออกทุกป้าย
    """
    frame_h, frame_w = frame.shape[:2]
    taken = []

    for i, (x, y, r, support) in enumerate(circles, start=1):
        color = (0, 255, 0) if support >= 0.7 else (0, 200, 255)
        cv2.circle(frame, (x, y), r, color, 2)
        cv2.circle(frame, (x, y), 3, (0, 0, 255), -1)

        head = f"#{i} r={r} {support:.0%}"
        (tw, th), _ = cv2.getTextSize(head, FONT, 0.5, 1)
        hx, hy = _place_label(max(0, min(x - r, frame_w - tw)), y - r - 8,
                              tw, th, taken, frame_h)
        _outlined_text(frame, head, (hx, hy), color)

        if labels and i <= len(labels):
            text = f"#{i} {labels[i - 1]}"
            (tw, th), _ = cv2.getTextSize(text, FONT, 0.6, 1)
            lx, ly = _place_label(max(0, min(x - r, frame_w - tw)), y + r + 20,
                                  tw, th, taken, frame_h)
            _outlined_text(frame, text, (lx, ly), (255, 255, 255), scale=0.6)
    return frame
