"""ฟังก์ชันเกี่ยวกับกล้อง ใช้ร่วมกันทุก Phase

แยกออกมาไว้ที่เดียว จะได้ไม่ต้องเขียนโค้ดเปิดกล้องซ้ำในทุกไฟล์
"""

import sys

import cv2


def open_camera(index: int, width: int, height: int):
    """เปิดกล้อง คืนค่า VideoCapture ถ้าสำเร็จ, คืน None ถ้าไม่สำเร็จ"""
    # บน Linux ระบุ backend V4L2 ตรง ๆ จะเปิดเร็วและเสถียรกว่าปล่อยให้ OpenCV เดาเอง
    cap = cv2.VideoCapture(index, cv2.CAP_V4L2)

    if not cap.isOpened():
        # เผื่อกรณีที่ V4L2 ใช้ไม่ได้ ลอง backend default อีกรอบ
        cap.release()
        cap = cv2.VideoCapture(index)

    if not cap.isOpened():
        return None

    # ขอความละเอียดที่ต้องการ (กล้องราคาประหยัดบางรุ่นอาจไม่รองรับทุกค่า)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return cap


def list_cameras(max_index: int = 10) -> None:
    """ไล่เปิดกล้องทีละ index เพื่อดูว่าตัวไหนใช้งานได้จริง"""
    print("กำลังสแกนหากล้อง... (อาจใช้เวลาสักครู่)\n")
    found = []
    for index in range(max_index):
        cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
        if cap.isOpened():
            ok, frame = cap.read()
            if ok and frame is not None:
                h, w = frame.shape[:2]
                print(f"  [ใช้ได้]    index {index}  ->  {w}x{h}")
                found.append(index)
            else:
                # เปิดได้แต่อ่านภาพไม่ออก มักเป็น node ของ metadata ไม่ใช่ภาพวิดีโอ
                print(f"  [เปิดได้แต่ไม่มีภาพ] index {index}")
        cap.release()

    if found:
        print(f"\nกล้องที่ใช้ได้: {found}")
    else:
        print("\nไม่พบกล้องที่ใช้งานได้เลย")


def print_camera_error(index: int) -> None:
    """ข้อความ error ที่บอกวิธีแก้แบบเข้าใจง่าย"""
    print("=" * 60, file=sys.stderr)
    print(f"ERROR: เปิดกล้อง index {index} ไม่ได้", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print("ลองตรวจสอบตามนี้ทีละข้อ:", file=sys.stderr)
    print("  1. เสียบสาย USB ของกล้องแน่นหรือยัง (ถ้าเป็นกล้องแยก)", file=sys.stderr)
    print("  2. เช็กว่าระบบเห็นกล้องไหม:   ls /dev/video*", file=sys.stderr)
    print("  3. หา index ที่ถูกต้อง:        python3 camera_test.py --list", file=sys.stderr)
    print("  4. มีโปรแกรมอื่นแย่งใช้กล้องอยู่หรือเปล่า (Zoom / Meet / Cheese)", file=sys.stderr)
    print("     กล้อง 1 ตัว เปิดได้ทีละโปรแกรมเท่านั้น", file=sys.stderr)
    print("  5. ถ้าขึ้น Permission denied ให้เพิ่มสิทธิ์:", file=sys.stderr)
    print("       sudo usermod -aG video $USER    (แล้ว log out / log in ใหม่)", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
