"""ฟังก์ชันเกี่ยวกับกล้อง ใช้ร่วมกันทุก Phase

แยกออกมาไว้ที่เดียว จะได้ไม่ต้องเขียนโค้ดเปิดกล้องซ้ำในทุกไฟล์
"""

import glob
import os
import sys
import time

import cv2

# เลือก backend ตามระบบปฏิบัติการ ระบุตรง ๆ จะเปิดเร็วและเสถียรกว่าปล่อยให้ OpenCV เดาเอง
#   Linux   -> V4L2
#   Windows -> DirectShow (MSMF ที่เป็นค่า default บางเครื่องใช้เวลาเปิดกล้องนานมาก)
if sys.platform.startswith("linux"):
    CAMERA_BACKEND = cv2.CAP_V4L2
elif sys.platform == "win32":
    CAMERA_BACKEND = cv2.CAP_DSHOW
else:
    CAMERA_BACKEND = cv2.CAP_ANY

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp")


def camera_names():
    """ชื่อกล้องเรียงตาม index ของ DirectShow (ลำดับเดียวกับที่ OpenCV ใช้) - Windows เท่านั้น

    บน Windows ลำดับ index เปลี่ยนได้หลัง restart หรือเสียบกล้องสลับพอร์ต
    (28 ต.ค. 2026: หลัง restart กล้อง RealSense ย้ายจาก index 2 ไป 0)
    การเลือกจากชื่อจึงทนกว่าการจำเลข index
    """
    if sys.platform != "win32":
        return []
    try:
        from pygrabber.dshow_graph import FilterGraph
        return FilterGraph().get_input_devices()
    except Exception:   # ไม่ได้ลง pygrabber หรืออ่านรายชื่อไม่ได้ -> ใช้เลข index แทน
        return []


def find_camera(name: str):
    """หา index ของกล้องที่ชื่อมีคำว่า name (ไม่สนตัวพิมพ์เล็ก/ใหญ่) คืน None ถ้าไม่เจอ"""
    names = camera_names()
    matches = [i for i, n in enumerate(names) if name.lower() in n.lower()]
    # RealSense มีทั้งช่องภาพสี (RGB) และช่องความลึก (Depth) - เอาช่องภาพสีก่อน
    matches.sort(key=lambda i: "depth" in names[i].lower())
    return matches[0] if matches else None


def pick_camera(index, name: str, fallback_index: int) -> int:
    """เลือก index กล้อง: เลขที่สั่งผ่าน --camera > ชื่อใน config > index สำรองใน config"""
    if index is not None:
        return index
    if name:
        found = find_camera(name)
        if found is not None:
            return found
        print(f"ไม่พบกล้องที่ชื่อมีคำว่า '{name}' - ใช้ index {fallback_index} แทน")
    return fallback_index


def open_camera(index: int, width: int, height: int):
    """เปิดกล้อง คืนค่า VideoCapture ถ้าสำเร็จ, คืน None ถ้าไม่สำเร็จ"""
    cap = cv2.VideoCapture(index, CAMERA_BACKEND)

    # เผื่อกรณีที่ backend ที่เลือกใช้ไม่ได้ ลอง backend default อีกรอบ
    # ยกเว้น Windows: DirectShow กับ MSMF เรียงลำดับกล้องไม่เหมือนกัน
    # ถ้าลองต่อ index เดียวกันอาจได้ "กล้องอีกตัว" มาแทนแบบเงียบ ๆ (เคยได้กล้องโน้ตบุ๊ก)
    if not cap.isOpened() and sys.platform != "win32":
        cap.release()
        cap = cv2.VideoCapture(index)

    if not cap.isOpened():
        return None

    # ขอความละเอียดที่ต้องการ (กล้องราคาประหยัดบางรุ่นอาจไม่รองรับทุกค่า)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return cap


class ImageFolderSource:
    """รีเพลย์ภาพจากโฟลเดอร์ให้ทำตัวเหมือนกล้อง (มี read() / release())

    ใช้ทดสอบทั้งระบบ IoT ได้โดยไม่ต้องเสียบกล้อง และใช้ใน Docker container
    ที่มองไม่เห็นกล้อง USB ของ Windows - ภาพแต่ละรูปจะถูกส่งซ้ำ hold วินาที
    เพื่อให้ EventRecorder เห็นว่า "ฉากนิ่ง" และบันทึกเหตุการณ์ได้เหมือนของจริง
    """

    def __init__(self, folder, fps=15.0, hold=2.0):
        self.paths = sorted(p for p in glob.glob(os.path.join(folder, "*"))
                            if p.lower().endswith(IMAGE_EXTENSIONS))
        self.delay = 1.0 / fps
        self.frames_per_image = max(1, int(hold * fps))
        self._index = 0
        self._shown = 0
        self._image = None

    def isOpened(self):
        return bool(self.paths)

    def read(self):
        if not self.paths:
            return False, None
        if self._image is None or self._shown >= self.frames_per_image:
            self._image = cv2.imread(self.paths[self._index])
            self._index = (self._index + 1) % len(self.paths)   # วนกลับไปรูปแรกเรื่อย ๆ
            self._shown = 0
        self._shown += 1
        time.sleep(self.delay)
        return self._image is not None, None if self._image is None else self._image.copy()

    def release(self):
        pass


class StreamSource:
    """เปิดวิดีโอจาก URL (เช่น MJPEG จาก camera_stream.py) และต่อใหม่เองถ้าหลุด"""

    def __init__(self, url, retry_delay=2.0):
        self.url = url
        self.retry_delay = retry_delay
        self._cap = cv2.VideoCapture(url)

    def isOpened(self):
        return self._cap.isOpened()

    def read(self):
        ok, frame = self._cap.read()
        while not ok:
            print(f"[stream] อ่านภาพจาก {self.url} ไม่ได้ จะลองใหม่ใน {self.retry_delay:.0f} วินาที")
            self._cap.release()
            time.sleep(self.retry_delay)
            self._cap = cv2.VideoCapture(self.url)
            ok, frame = self._cap.read()
        return ok, frame

    def release(self):
        self._cap.release()


def open_source(source: str, width: int, height: int):
    """เปิดแหล่งภาพได้ 4 แบบ คืนค่า (ตัวอ่านภาพ, ชนิด) หรือ (None, ชนิด) ถ้าเปิดไม่ได้

    "2"                            -> กล้อง index 2         ชนิด "camera"
    "snapshots/clean"              -> โฟลเดอร์ภาพ (รีเพลย์)   ชนิด "folder"
    "http://host:8090/video"       -> สตรีมจาก URL          ชนิด "stream"
    "clip.mp4"                     -> ไฟล์วิดีโอ             ชนิด "file"
    """
    if str(source).isdigit():
        return open_camera(int(source), width, height), "camera"
    if os.path.isdir(source):
        folder = ImageFolderSource(source)
        return (folder if folder.isOpened() else None), "folder"
    if "://" in source:
        stream = StreamSource(source)
        return (stream if stream.isOpened() else None), "stream"
    cap = cv2.VideoCapture(source)
    return (cap if cap.isOpened() else None), "file"


def list_cameras(max_index: int = 10) -> None:
    """ไล่เปิดกล้องทีละ index เพื่อดูว่าตัวไหนใช้งานได้จริง"""
    print("กำลังสแกนหากล้อง... (อาจใช้เวลาสักครู่)\n")
    names = camera_names()
    if names:
        print("ชื่อกล้องที่ Windows เห็น (ตั้ง CAMERA_NAME ใน config.py ด้วยคำในชื่อได้):")
        for i, n in enumerate(names):
            print(f"  index {i}: {n}")
        print()
    found = []
    for index in range(max_index):
        cap = cv2.VideoCapture(index, CAMERA_BACKEND)
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
    print("  2. หา index ที่ถูกต้อง:        python camera_test.py --list", file=sys.stderr)
    print("  3. มีโปรแกรมอื่นแย่งใช้กล้องอยู่หรือเปล่า (Zoom / Meet / camera_stream.py)",
          file=sys.stderr)
    print("     กล้อง 1 ตัว เปิดได้ทีละโปรแกรมเท่านั้น", file=sys.stderr)
    if sys.platform == "win32":
        print("  4. Windows: Settings > Privacy & security > Camera", file=sys.stderr)
        print("     ต้องเปิด 'Let desktop apps access your camera'", file=sys.stderr)
    else:
        print("  4. เช็กว่าระบบเห็นกล้องไหม:   ls /dev/video*", file=sys.stderr)
        print("  5. ถ้าขึ้น Permission denied ให้เพิ่มสิทธิ์:", file=sys.stderr)
        print("       sudo usermod -aG video $USER    (แล้ว log out / log in ใหม่)", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
