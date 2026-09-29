"""Phase 5: บันทึกภาพอัตโนมัติเมื่อตรวจเจอ พร้อมจดบันทึกลงไฟล์ CSV

ปัญหาที่ต้องแก้: กล้องส่งภาพ ~15 เฟรมต่อวินาที ถ้าบันทึกทุกเฟรมที่เจอลูกบอล
จะได้ภาพซ้ำกันวินาทีละ 15 รูป จึงใช้ 2 กติกาคุมไว้

  1. ต้องเจอ "ฉากเดิม" ติดกันหลายเฟรม ถึงจะยอมบันทึก (กันภาพที่กะพริบไปมา)
  2. ต้องเว้นระยะเวลาจากภาพก่อนหน้า (cooldown)

และจะบันทึกใหม่ทันทีถ้า "ฉาก" เปลี่ยนไป เช่น จาก 1 ลูกเป็น 2 ลูก
หรือเปลี่ยนจากลูกกอล์ฟเป็นลูกเทนนิส
"""

import csv
import os
import time
from datetime import datetime

import cv2


def describe(detections):
    """สรุปผลการตรวจจับเป็นข้อความสั้น ๆ สำหรับแจ้งผู้ใช้"""
    golf = [d for d in detections if d["golf"]]
    rejected = [d for d in detections if not d["golf"]]

    parts = []
    if golf:
        colors = ", ".join(d["color"] for d in golf)
        parts.append(f"เจอลูกกอล์ฟ {len(golf)} ลูก: {colors}")
    if rejected:
        reasons = ", ".join(sorted({d["reason"] for d in rejected}))
        parts.append(f"ปฏิเสธสิ่งแปลกปลอม {len(rejected)} ชิ้น (ไม่ใช่ลูกกอล์ฟ: {reasons})")
    return "  |  ".join(parts) if parts else "ไม่เจออะไร"


def _signature(detections):
    """ลายเซ็นของฉาก ใช้เทียบว่าภาพเปลี่ยนไปจากเดิมหรือยัง

    สนใจแค่ "เจอลูกกอล์ฟสีอะไรกี่ลูก และปฏิเสธไปกี่ชิ้น" ไม่สนตำแหน่ง
    เพราะลูกบอลขยับนิดหน่อยไม่ควรนับเป็นฉากใหม่
    """
    golf = tuple(sorted(d["color"] for d in detections if d["golf"]))
    rejected = tuple(sorted(d["reason"] for d in detections if not d["golf"]))
    return (golf, rejected)


def _filename(detections) -> str:
    """ตั้งชื่อไฟล์ให้อ่านแล้วรู้เลยว่าภาพนั้นเจออะไร"""
    golf = [d for d in detections if d["golf"]]
    rejected = [d for d in detections if not d["golf"]]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    parts = [stamp]
    if golf:
        colors = "-".join(sorted(d["color"].lower() for d in golf))
        parts.append(f"golf{len(golf)}_{colors}")
    if rejected:
        reasons = "-".join(sorted({d["reason"].replace(" ", "") for d in rejected}))
        parts.append(f"reject{len(rejected)}_{reasons}")
    return "_".join(parts) + ".jpg"


class EventRecorder:
    """ตัดสินใจว่าเฟรมไหนควรเก็บไว้ แล้วบันทึกภาพ + จดลง CSV"""

    def __init__(self, out_dir="snapshots", csv_path="detections.csv",
                 cooldown=3.0, stable_frames=5, save_clean=True):
        self.out_dir = out_dir
        self.save_clean = save_clean
        self.csv_path = csv_path
        self.cooldown = cooldown
        self.stable_frames = stable_frames

        self._pending = None        # ลายเซ็นฉากที่กำลังรอให้นิ่ง
        self._streak = 0            # เจอฉากนี้ติดกันมากี่เฟรมแล้ว
        self._last_saved = None     # ลายเซ็นของภาพล่าสุดที่บันทึกไป
        self._last_time = 0.0

    def update(self, frame, detections, clean_frame=None):
        """เรียกทุกเฟรม คืนค่า (path ของภาพที่บันทึก, ข้อความแจ้ง) หรือ (None, None)

        frame       = ภาพที่มีกรอบและป้ายกำกับแล้ว ใช้เป็นหลักฐานว่าโปรแกรมเห็นอะไร
        clean_frame = ภาพต้นฉบับไม่มีอะไรวาดทับ เก็บไว้ใช้วัดค่าย้อนหลัง
        """
        signature = _signature(detections)

        # ไม่เจออะไรเลย = รีเซ็ตทุกอย่าง รอบหน้าที่เจอจะได้บันทึกทันที
        if not detections:
            self._pending, self._streak, self._last_saved = None, 0, None
            return None, None

        if signature == self._pending:
            self._streak += 1
        else:
            self._pending, self._streak = signature, 1

        if self._streak < self.stable_frames:
            return None, None
        if signature == self._last_saved and time.time() - self._last_time < self.cooldown:
            return None, None

        os.makedirs(self.out_dir, exist_ok=True)
        path = os.path.join(self.out_dir, _filename(detections))
        # ชื่อไฟล์ละเอียดถึงระดับวินาที ถ้าเกิด 2 เหตุการณ์ในวินาทีเดียวกัน
        # และอธิบายเหมือนกัน ต้องเติมเลขต่อท้าย ไม่งั้นภาพเก่าจะถูกเขียนทับ
        if os.path.exists(path):
            stem, ext = os.path.splitext(path)
            index = 2
            while os.path.exists(f"{stem}_{index}{ext}"):
                index += 1
            path = f"{stem}_{index}{ext}"
        cv2.imwrite(path, frame)

        # เก็บภาพต้นฉบับแยกไว้ด้วย เพราะจุดแดงกับกรอบที่วาดทับ
        # ทำให้วัดค่าพื้นผิวจากภาพที่มีป้ายกำกับได้ผลเพี้ยนไปมาก
        if self.save_clean and clean_frame is not None:
            clean_dir = os.path.join(self.out_dir, "clean")
            os.makedirs(clean_dir, exist_ok=True)
            cv2.imwrite(os.path.join(clean_dir, os.path.basename(path)), clean_frame)

        self._last_saved, self._last_time = signature, time.time()
        self._write_csv(path, detections)
        return path, describe(detections)

    def _write_csv(self, path, detections):
        """จดบันทึกลง CSV เอาไว้ทำสรุปผลหรือใส่รายงานทีหลัง"""
        write_rows(self.csv_path, detections, label="-", image_path=path)


# คอลัมน์ของไฟล์บันทึก ใช้ร่วมกันทั้งโหมดปกติและโหมดเก็บข้อมูล
CSV_HEADER = ["เวลา", "ของจริง", "ผลตัดสิน", "สี/เหตุผล", "รัศมี",
              "คะแนนพื้นผิว", "ความหนาแน่นขอบ", "จุดสะท้อนแสง", "การกระจายความสว่าง",
              "คะแนนขอบ", "H", "S", "V", "ไฟล์ภาพ"]


def write_rows(csv_path, detections, label="-", image_path="-"):
    """เขียนผลการตรวจจับลง CSV หนึ่งแถวต่อหนึ่งลูก"""
    new_file = not os.path.exists(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(CSV_HEADER)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for d in detections:
            h, s_, v = d.get("hsv", (0, 0, 0))
            writer.writerow([
                now, label,
                "Golf Ball" if d["golf"] else "Not Golf Ball",
                d["color"] if d["golf"] else d["reason"],
                d["radius"], f"{d['texture']:.1f}",
                f"{d.get('edge_density', 0):.4f}", f"{d.get('bright_frac', 0):.4f}",
                f"{d.get('v_std', 0):.1f}",
                f"{d['support']:.2f}", h, s_, v, image_path,
            ])


class DataCollector:
    """โหมดเก็บข้อมูลสำหรับหาเกณฑ์ใหม่

    ต่างจาก EventRecorder ตรงที่บันทึก "ทุกเฟรมที่เจอ" ลง CSV โดยไม่เก็บภาพ
    เพราะเป้าหมายคือได้ตัวเลขเยอะ ๆ ของลูกบอลที่รู้อยู่แล้วว่าเป็นอะไร
    """

    def __init__(self, csv_path, label):
        self.csv_path = csv_path
        self.label = label
        self.count = 0

    def log(self, detections):
        if not detections:
            return 0
        write_rows(self.csv_path, detections, label=self.label)
        self.count += len(detections)
        return len(detections)
