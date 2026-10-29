#!/usr/bin/env python3
"""Phase 1: เปิด Webcam แล้วแสดงภาพแบบ Real-time พร้อม FPS

การใช้งาน:
    python3 camera_test.py                 # ใช้กล้องตาม config.py
    python3 camera_test.py --camera 2      # เลือก index กล้องเอง
    python3 camera_test.py --list          # สแกนดูว่ามีกล้อง index ไหนใช้ได้บ้าง

กด Q หรือ ESC เพื่อออกจากโปรแกรม
"""

import argparse
import os
import sys

# ปิด log เตือนของ OpenCV ตอนไล่เปิดกล้อง index ที่ไม่มีอยู่จริง (ต้องตั้งก่อน import cv2)
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

import cv2

import config
from utils.camera import list_cameras, open_camera, pick_camera, print_camera_error
from utils.draw import draw_text_lines, window_closed
from utils.fps import FPSCounter


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 1: ทดสอบกล้องพร้อมแสดง FPS")
    parser.add_argument("-c", "--camera", type=int, default=None,
                        help=f"index ของกล้อง (ไม่ใส่ = หากล้องที่ชื่อมี '{config.CAMERA_NAME}' "
                             f"ถ้าไม่เจอใช้ index {config.CAMERA_INDEX})")
    parser.add_argument("--width", type=int, default=config.FRAME_WIDTH,
                        help=f"ความกว้างภาพ (ค่าเริ่มต้น: {config.FRAME_WIDTH})")
    parser.add_argument("--height", type=int, default=config.FRAME_HEIGHT,
                        help=f"ความสูงภาพ (ค่าเริ่มต้น: {config.FRAME_HEIGHT})")
    parser.add_argument("--list", action="store_true",
                        help="สแกนหากล้องที่ใช้งานได้ แล้วจบโปรแกรม")
    args = parser.parse_args()

    if args.list:
        list_cameras()
        return 0

    args.camera = pick_camera(args.camera, config.CAMERA_NAME, config.CAMERA_INDEX)
    cap = open_camera(args.camera, args.width, args.height)
    if cap is None:
        print_camera_error(args.camera)
        return 1

    # อ่านค่าจริงที่กล้องให้มา (อาจไม่ตรงกับที่ขอไป)
    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"เปิดกล้อง index {args.camera} สำเร็จ ({actual_w}x{actual_h})")
    print("กด Q หรือ ESC ที่หน้าต่างภาพเพื่อออกจากโปรแกรม")

    fps_counter = FPSCounter(config.FPS_AVG_FRAMES)

    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                print("ERROR: อ่านภาพจากกล้องไม่ได้ (สายหลุด หรือกล้องถูกถอดออก?)",
                      file=sys.stderr)
                break

            fps_counter.update()
            height, width = frame.shape[:2]
            draw_text_lines(frame, [
                f"FPS: {fps_counter.fps:.1f}",
                f"Camera: {args.camera}   Size: {width}x{height}",
                "Press Q or ESC to quit",
            ])
            cv2.imshow(config.WINDOW_NAME, frame)

            # waitKey(1) = รอ 1 ms ต่อเฟรม และเป็นตัวที่ทำให้หน้าต่างวาดภาพออกมาด้วย
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), ord("Q"), 27):  # 27 = ESC
                print("ปิดโปรแกรมตามคำสั่งผู้ใช้")
                break

            # ถ้าผู้ใช้กดปุ่มกากบาทปิดหน้าต่าง ก็ให้จบโปรแกรมเช่นกัน
            if window_closed(config.WINDOW_NAME):
                print("หน้าต่างถูกปิด")
                break

    except KeyboardInterrupt:
        print("\nหยุดด้วย Ctrl+C")

    finally:
        # คืนทรัพยากรเสมอ ไม่ว่าจะจบแบบไหน ไม่งั้นกล้องจะค้างจนเปิดรอบหน้าไม่ได้
        cap.release()
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    sys.exit(main())
