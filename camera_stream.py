#!/usr/bin/env python3
"""ขั้นที่ 1 ในโฟลว์: ส่งภาพจากกล้อง (หน้างาน) ให้ OpenCV Container

ทำไมต้องมีไฟล์นี้: Docker Desktop บน Windows มองไม่เห็นกล้อง USB
จึงให้ Windows เปิดกล้องแล้วปล่อยภาพเป็นสตรีม MJPEG ทาง HTTP
แล้ว container ค่อยดึงภาพจาก http://host.docker.internal:8090/video

การใช้งาน:
    python camera_stream.py                 # ใช้กล้องตาม config.py
    python camera_stream.py --camera 0      # เลือกกล้องเอง
เปิดดูภาพในเบราว์เซอร์ได้ที่ http://localhost:8090
"""

import argparse
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

import cv2

import config
from utils.camera import open_camera, pick_camera, print_camera_error

BOUNDARY = "frame"


class FrameGrabber(threading.Thread):
    """อ่านภาพจากกล้องตลอดเวลา เก็บไว้แค่ภาพล่าสุด (เข้ารหัส JPEG แล้ว)"""

    def __init__(self, cap, quality=85):
        super().__init__(daemon=True)
        self.cap = cap
        self.quality = quality
        self.jpeg = None
        self.lock = threading.Condition()
        self.running = True

    def run(self):
        while self.running:
            ok, frame = self.cap.read()
            if not ok:
                time.sleep(0.1)
                continue
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.quality])
            if ok:
                with self.lock:
                    self.jpeg = buf.tobytes()
                    self.lock.notify_all()

    def wait_frame(self, timeout=2.0):
        with self.lock:
            self.lock.wait(timeout)
            return self.jpeg


def make_handler(grabber):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/":
                body = b'<html><body style="margin:0;background:#111">' \
                       b'<img src="/video" style="max-width:100%"></body></html>'
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path != "/video":
                self.send_error(404)
                return

            self.send_response(200)
            self.send_header("Content-Type", f"multipart/x-mixed-replace; boundary={BOUNDARY}")
            self.end_headers()
            try:
                while True:
                    jpeg = grabber.wait_frame()
                    if jpeg is None:
                        continue
                    self.wfile.write(f"--{BOUNDARY}\r\nContent-Type: image/jpeg\r\n"
                                     f"Content-Length: {len(jpeg)}\r\n\r\n".encode())
                    self.wfile.write(jpeg + b"\r\n")
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass  # ผู้ดูปิดการเชื่อมต่อไปแล้ว

        def log_message(self, fmt, *args):
            print(f"[{self.client_address[0]}] {fmt % args}")

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="สตรีมกล้องเป็น MJPEG ให้ Docker container")
    parser.add_argument("-c", "--camera", type=int, default=None,
                        help=f"index ของกล้อง (ไม่ใส่ = หากล้องที่ชื่อมี '{config.CAMERA_NAME}')")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()
    args.camera = pick_camera(args.camera, config.CAMERA_NAME, config.CAMERA_INDEX)

    cap = open_camera(args.camera, config.FRAME_WIDTH, config.FRAME_HEIGHT)
    if cap is None:
        print_camera_error(args.camera)
        return 1

    grabber = FrameGrabber(cap)
    grabber.start()
    server = ThreadingHTTPServer(("0.0.0.0", args.port), make_handler(grabber))
    print(f"สตรีมกล้อง index {args.camera} ที่ http://localhost:{args.port}/video")
    print(f"ใน Docker ใช้: http://host.docker.internal:{args.port}/video   (Ctrl+C เพื่อหยุด)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nหยุดสตรีม")
    finally:
        grabber.running = False
        server.server_close()
        cap.release()
    return 0


if __name__ == "__main__":
    sys.exit(main())
