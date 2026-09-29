"""ฟังก์ชันเกี่ยวกับการแสดงผลบนหน้าจอ ใช้ร่วมกันทุก Phase"""

import cv2

FONT = cv2.FONT_HERSHEY_SIMPLEX


def draw_text_lines(frame, lines, origin=(10, 30), scale=0.7, color=(0, 255, 0)):
    """วาดข้อความหลายบรรทัด พร้อมขอบดำเพื่อให้อ่านออกทุกพื้นหลัง"""
    x, y = origin
    for text in lines:
        # วาดสีดำหนา ๆ ไว้ข้างหลังก่อน แล้วค่อยวาดสีจริงทับ
        cv2.putText(frame, text, (x, y), FONT, scale, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(frame, text, (x, y), FONT, scale, color, 2, cv2.LINE_AA)
        y += int(30 * scale / 0.7)
    return frame


def window_closed(name: str) -> bool:
    """เช็กว่าหน้าต่างถูกปิดไปแล้วหรือยัง (เช่น ผู้ใช้กดปุ่มกากบาท)

    OpenCV 5 ที่ใช้ Qt จะ "โยน error" ออกมาถ้าหน้าต่างถูกทำลายไปแล้ว
    แทนที่จะคืนค่า 0 เฉย ๆ จึงต้องดักไว้ ไม่งั้นโปรแกรมจะพังตอนกดปิดหน้าต่าง
    """
    try:
        return cv2.getWindowProperty(name, cv2.WND_PROP_VISIBLE) < 1
    except cv2.error:
        return True
