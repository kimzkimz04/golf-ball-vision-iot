"""ตัวนับ FPS แบบเฉลี่ยย้อนหลัง (moving average)

เหตุผลที่ต้องเฉลี่ย: ถ้าคำนวณ FPS จากเฟรมเดียว ตัวเลขจะกระพริบจนอ่านไม่ทัน
เราจึงเก็บเวลาที่ใช้ต่อเฟรมย้อนหลังไว้หลาย ๆ ค่า แล้วหาค่าเฉลี่ย
"""

import time
from collections import deque


class FPSCounter:
    def __init__(self, avg_frames: int = 30):
        # deque ที่มี maxlen จะทิ้งค่าเก่าสุดออกเองอัตโนมัติ
        self._durations = deque(maxlen=avg_frames)
        self._last_time = None

    def update(self) -> None:
        """เรียก 1 ครั้งต่อ 1 เฟรม"""
        now = time.perf_counter()
        if self._last_time is not None:
            self._durations.append(now - self._last_time)
        self._last_time = now

    @property
    def fps(self) -> float:
        if not self._durations:
            return 0.0
        avg = sum(self._durations) / len(self._durations)
        return 1.0 / avg if avg > 0 else 0.0
