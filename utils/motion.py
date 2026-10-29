"""Phase 8: รอให้ภาพนิ่งก่อนค่อยนับผล (กันมือที่กำลังวาง/หยิบ/จับลูก)

ทำไมไม่ตรวจหามือด้วยสี: ทดลองกับภาพจริง 145 รูปแล้ว กล้องถ่ายผิวมือออกมาซีด
จนสีเดียวกับโต๊ะไม้ (Cr / S ทับกันเกือบหมด แยกได้ดีสุดแค่ 72%) และการเทียบกับ
ภาพโต๊ะเปล่าก็ได้แค่ 82% เพราะเงาลูกบอลกับแสงที่กล้องปรับเองถูกนับเป็นของแปลกด้วย

สิ่งที่ต่างชัดคือ "มือขยับ" ส่วนลูกที่วางไว้นิ่ง จึงวัดว่าภาพเปลี่ยนไปกี่ % เทียบกับ
เมื่อไม่กี่เฟรมก่อน ถ้าเปลี่ยนเกินเกณฑ์ = มีอะไรกำลังขยับ ให้รอจนนิ่งต่อเนื่องครบเวลาที่ตั้ง

ข้อจำกัด: มือที่วางนิ่งสนิทค้างไว้ในภาพจะไม่ถูกจับได้
"""

import collections
import time

import cv2
import numpy as np


class StillnessGate:
    def __init__(self, compare_frames=5, pixel_diff=20, max_ratio=0.004, still_seconds=1.0):
        self.compare_frames = compare_frames   # เทียบกับภาพเมื่อกี่เฟรมก่อน (ขยับช้า ๆ ก็ยังเห็น)
        self.pixel_diff = pixel_diff           # ความสว่างต่างกันเกินเท่านี้ = พิกเซลนั้นเปลี่ยน
        self.max_ratio = max_ratio             # พิกเซลเปลี่ยนเกินสัดส่วนนี้ = ภาพกำลังขยับ
        self.still_seconds = still_seconds     # ต้องนิ่งต่อเนื่องนานเท่านี้ถึงจะนับผล
        self._history = collections.deque(maxlen=compare_frames)
        self._still_since = None
        self.ratio = 0.0

    def update(self, frame):
        """เรียกทุกเฟรมด้วยภาพต้นฉบับ คืนค่า True ถ้าภาพนิ่งนานพอแล้ว"""
        # ย่อภาพและเบลอก่อนเทียบ ลด noise ของกล้องที่ทำให้พิกเซลกะพริบเองตลอดเวลา
        small = cv2.GaussianBlur(cv2.cvtColor(cv2.resize(frame, (160, 120)),
                                              cv2.COLOR_BGR2GRAY), (5, 5), 0)
        now = time.time()
        if len(self._history) == self.compare_frames:
            diff = cv2.absdiff(small, self._history[0])
            self.ratio = float(np.count_nonzero(diff > self.pixel_diff)) / diff.size
        self._history.append(small)

        if self.ratio > self.max_ratio:
            self._still_since = None
        elif self._still_since is None:
            self._still_since = now
        return self.ready

    @property
    def still_for(self) -> float:
        return 0.0 if self._still_since is None else time.time() - self._still_since

    @property
    def ready(self) -> bool:
        return self._still_since is not None and self.still_for >= self.still_seconds
