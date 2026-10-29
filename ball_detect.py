#!/usr/bin/env python3
"""Phase 2: ตรวจจับวัตถุทรงกลมจากภาพกล้องแบบ Real-time

ยังไม่แยกว่าเป็นลูกกอล์ฟหรือไม่ - ขั้นนี้แค่หา "ของกลม ๆ" ให้เจอก่อน
การแยกลูกกอล์ฟกับลูกอื่นจะทำใน Phase 3

การใช้งาน:
    python3 ball_detect.py                  # ใช้กล้องตาม config.py
    python3 ball_detect.py --camera 0       # เลือก index กล้องเอง
    python3 ball_detect.py --tune           # เปิดแถบเลื่อนปรับค่าแบบสด ๆ
    python3 ball_detect.py --alt            # ใช้อัลกอริทึมที่รัศมีแม่นกว่า
    python3 ball_detect.py --source snapshots/clean   # รีเพลย์ภาพแทนกล้อง (ทดสอบระบบ IoT)
    python3 ball_detect.py --headless       # ไม่เปิดหน้าต่าง (ใช้ใน Docker container)
    python3 ball_detect.py --no-mqtt        # ไม่ส่งผลไป MQTT broker

ผลการตรวจจับจะถูกส่งเป็น JSON ไปที่ MQTT topic golf/vision/result (ดู config.py)

ปุ่มลัดระหว่างใช้งาน:
    Q / ESC = ออก   S = บันทึกภาพ   D = ดูภาพขอบ   C = ดูค่าสีจริงของลูกบอลที่ใช้ประมวลผล
"""

import argparse
import os
import sys
from collections import Counter
from datetime import datetime

os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

import cv2

import config
from utils.camera import camera_names, list_cameras, open_source, pick_camera, print_camera_error
from utils.ball_classifier import ball_features, is_golf_ball
from utils.color_classifier import classify_color, color_scores
from utils.detector import (draw_verified, find_circles, preprocess, preprocess_saturation,
                            verify_circles)
from utils.draw import draw_text_lines, window_closed
from utils.fps import FPSCounter
from utils.motion import StillnessGate
from utils.mqtt_pub import ResultPublisher
from utils.recorder import DataCollector, EventRecorder, SessionStats

# ชื่อหน้าต่างต้องเป็นภาษาอังกฤษล้วน! Qt ของ OpenCV 5 หาหน้าต่างที่ชื่อมีภาษาไทย
# ไม่เจอ ทำให้ createTrackbar พังด้วย error "NULL window handler"
TUNE_WINDOW = "Tuning Panel"
DEBUG_WINDOW = "Debug: Canny edges used for verification"


def create_tuning_window():
    """สร้างแถบเลื่อนสำหรับปรับค่าแบบเห็นผลทันที"""
    cv2.namedWindow(TUNE_WINDOW, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(TUNE_WINDOW, 480, 260)
    # createTrackbar ต้องการ callback แต่เราจะอ่านค่าเองทุกเฟรม เลยใส่ฟังก์ชันว่างไว้
    nothing = lambda _value: None
    cv2.createTrackbar("blur (odd)", TUNE_WINDOW, config.BLUR_KERNEL, 31, nothing)
    cv2.createTrackbar("minDist", TUNE_WINDOW, config.HOUGH_MIN_DIST, 300, nothing)
    cv2.createTrackbar("param1", TUNE_WINDOW, config.HOUGH_PARAM1, 300, nothing)
    cv2.createTrackbar("param2", TUNE_WINDOW, config.HOUGH_PARAM2, 200, nothing)
    cv2.createTrackbar("minRadius", TUNE_WINDOW, config.MIN_RADIUS, 300, nothing)
    cv2.createTrackbar("maxRadius", TUNE_WINDOW, config.MAX_RADIUS, 400, nothing)
    # เก็บเป็นเปอร์เซ็นต์ เพราะ trackbar รับได้แต่จำนวนเต็ม
    cv2.createTrackbar("support %", TUNE_WINDOW, int(config.MIN_SUPPORT * 100), 100, nothing)


def read_tuning_values():
    """อ่านค่าปัจจุบันจากแถบเลื่อนทั้งหมด"""
    return {
        "blur_kernel": cv2.getTrackbarPos("blur (odd)", TUNE_WINDOW),
        # minDist ห้ามเป็น 0 ไม่งั้น OpenCV จะ error
        "min_dist": max(1, cv2.getTrackbarPos("minDist", TUNE_WINDOW)),
        "param1": max(1, cv2.getTrackbarPos("param1", TUNE_WINDOW)),
        "param2": max(1, cv2.getTrackbarPos("param2", TUNE_WINDOW)),
        "min_radius": cv2.getTrackbarPos("minRadius", TUNE_WINDOW),
        "max_radius": cv2.getTrackbarPos("maxRadius", TUNE_WINDOW),
        "min_support": cv2.getTrackbarPos("support %", TUNE_WINDOW) / 100.0,
    }


def save_snapshot(frame) -> str:
    """บันทึกภาพปัจจุบันไว้ดูย้อนหลัง ตั้งชื่อไฟล์ตามเวลา"""
    os.makedirs("snapshots", exist_ok=True)
    path = f"snapshots/{datetime.now():%Y%m%d_%H%M%S}.jpg"
    cv2.imwrite(path, frame)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 2: ตรวจจับวัตถุทรงกลม")
    parser.add_argument("-c", "--camera", type=int, default=None,
                        help=f"index ของกล้อง (ไม่ใส่ = หากล้องที่ชื่อมี '{config.CAMERA_NAME}' "
                             f"ถ้าไม่เจอใช้ index {config.CAMERA_INDEX})")
    parser.add_argument("--width", type=int, default=config.FRAME_WIDTH)
    parser.add_argument("--height", type=int, default=config.FRAME_HEIGHT)
    parser.add_argument("--tune", action="store_true",
                        help="เปิดหน้าต่างแถบเลื่อนสำหรับปรับค่าแบบสด ๆ")
    parser.add_argument("--alt", action="store_true",
                        help="ใช้ HOUGH_GRADIENT_ALT (รัศมีแม่นกว่า แต่ช้ากว่า)")
    parser.add_argument("--list", action="store_true",
                        help="สแกนหากล้องที่ใช้งานได้ แล้วจบโปรแกรม")
    parser.add_argument("--no-capture", action="store_true",
                        help="ปิดการบันทึกภาพอัตโนมัติ")
    parser.add_argument("--collect", metavar="ชื่อลูกบอล",
                        help="โหมดเก็บข้อมูลสำหรับปรับเกณฑ์ เช่น --collect golf_white "
                             "จะจดค่าทุกเฟรมลง CSV โดยไม่เก็บภาพ")
    parser.add_argument("--source", metavar="แหล่งภาพ",
                        help="ใช้แทน --camera: โฟลเดอร์ภาพ (เช่น snapshots/clean), "
                             "URL สตรีม (เช่น http://localhost:8090/video) หรือไฟล์วิดีโอ")
    parser.add_argument("--headless", action="store_true",
                        help="ไม่เปิดหน้าต่างแสดงผล (สำหรับรันใน Docker / server)")
    parser.add_argument("--no-mqtt", action="store_true",
                        help="ไม่ส่งผลการตรวจจับไปที่ MQTT broker")
    args = parser.parse_args()

    if args.list:
        list_cameras()
        return 0

    if args.headless and args.tune:
        parser.error("--tune ต้องมีหน้าต่าง ใช้คู่กับ --headless ไม่ได้")

    if not args.source:
        args.camera = pick_camera(args.camera, config.CAMERA_NAME, config.CAMERA_INDEX)
    source = args.source if args.source else str(args.camera)
    cap, source_kind = open_source(source, args.width, args.height)
    if cap is None:
        if source_kind == "camera":
            print_camera_error(args.camera)
        else:
            print(f"ERROR: เปิดแหล่งภาพ '{source}' ไม่ได้ (เป็น{source_kind}ที่ไม่มีภาพ/เข้าถึงไม่ได้)",
                  file=sys.stderr)
        return 1

    method = "alt" if args.alt else "classic"
    print(f"เปิดแหล่งภาพ '{source}' ({source_kind}) สำเร็จ (อัลกอริทึม: {method})")
    if source_kind == "camera":
        names = camera_names()
        if args.camera < len(names):
            print(f"กล้องที่ใช้: {names[args.camera]}")
    if args.headless:
        print("โหมด headless: ไม่มีหน้าต่าง กด Ctrl+C เพื่อหยุด")
    else:
        print("ปุ่มลัด:  Q/ESC = ออก   S = บันทึกภาพ   D = ดูภาพขอบ   C = ดูค่าสีจริง")

    if args.tune:
        create_tuning_window()
        print("เปิดโหมดปรับค่า: เลื่อนแถบแล้วดูผลที่หน้าต่างภาพได้ทันที")

    # ค่าเริ่มต้นจาก config.py ถ้าเปิด --tune จะถูกแทนที่ด้วยค่าจากแถบเลื่อนทุกเฟรม
    params = {
        "blur_kernel": config.BLUR_KERNEL,
        "min_dist": config.HOUGH_MIN_DIST,
        "param1": config.HOUGH_PARAM1,
        "param2": config.HOUGH_PARAM2,
        "min_radius": config.MIN_RADIUS,
        "max_radius": config.MAX_RADIUS,
        "min_support": config.MIN_SUPPORT,
    }

    fps_counter = FPSCounter(config.FPS_AVG_FRAMES)
    show_debug = False
    stats = SessionStats()

    collector = None
    if args.collect:
        collector = DataCollector(config.COLLECT_CSV, args.collect)
        print(f"โหมดเก็บข้อมูล: กำลังจดค่าของ '{args.collect}' ลง {config.COLLECT_CSV}")
        print("วางลูกบอลหน้ากล้องค้างไว้สัก 10 วินาที แล้วกด Q")

    recorder = None
    if not args.no_capture and not args.collect:
        capture_dir, capture_csv = config.CAPTURE_DIR, config.CAPTURE_CSV
        if source_kind == "folder":
            # รีเพลย์อยู่ - แยกผลไปเก็บที่อื่น ไม่ให้ปนกับภาพต้นฉบับ
            capture_dir, capture_csv = config.REPLAY_CAPTURE_DIR, config.REPLAY_CAPTURE_CSV
            os.makedirs(os.path.dirname(capture_csv), exist_ok=True)
        recorder = EventRecorder(capture_dir, capture_csv,
                                 config.CAPTURE_COOLDOWN, config.CAPTURE_STABLE_FRAMES,
                                 config.CAPTURE_SAVE_CLEAN)
        print(f"บันทึกภาพอัตโนมัติ: เปิด (เก็บที่ {capture_dir}/ บันทึกผลลง {capture_csv})")

    publisher = None
    if config.MQTT_ENABLED and not args.no_mqtt and not args.collect:
        publisher = ResultPublisher(config.MQTT_HOST, config.MQTT_PORT, config.MQTT_TOPIC,
                                    config.MQTT_STATUS_TOPIC, config.DEVICE_ID,
                                    config.MQTT_INTERVAL, config.GOLF_COLORS)
        print(f"ส่ง MQTT: เปิด (broker {config.MQTT_HOST}:{config.MQTT_PORT} "
              f"topic {config.MQTT_TOPIC})")

    # ภาพต้องนิ่งก่อนถึงจะนับผล - ไม่ใช้ในโหมด --collect เพราะตอนเก็บข้อมูลตั้งใจเลื่อนลูกไปมา
    gate = None
    if config.STILLNESS_ENABLED and not args.collect:
        gate = StillnessGate(config.MOTION_COMPARE_FRAMES, config.MOTION_PIXEL_DIFF,
                             config.MOTION_MAX_RATIO, config.STILL_SECONDS)
        print(f"รอภาพนิ่ง: เปิด (ต้องไม่มีอะไรขยับ {config.STILL_SECONDS:.1f} วินาที "
              f"ก่อนบันทึก/ส่งผล)")

    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                if source_kind == "file":
                    print("วิดีโอจบแล้ว")
                else:
                    print("ERROR: อ่านภาพจากกล้องไม่ได้ (สายหลุด หรือกล้องถูกถอดออก?)",
                          file=sys.stderr)
                break

            # เก็บภาพต้นฉบับไว้ก่อนวาดทับ เวลากด S จะได้ภาพสะอาดไว้ใช้ทดสอบ/จูนต่อ
            clean_frame = frame.copy()

            # มีอะไรขยับอยู่ (เช่น มือกำลังวางลูก) = ยังไม่นับผลเฟรมนี้
            ready = gate.update(clean_frame) if gate is not None else True

            if args.tune:
                params = read_tuning_values()

            channels = [preprocess(frame, params["blur_kernel"])]
            if config.DETECT_ON_SATURATION:
                channels.append(preprocess_saturation(frame, params["blur_kernel"]))
            # หาวงกลมในทุกช่องภาพแล้วรวมกัน วงที่ซ้ำกันจะถูกรวมใน verify_circles
            raw = []
            for channel in channels:
                raw += find_circles(
                    channel, dp=config.HOUGH_DP, min_dist=params["min_dist"],
                    param1=params["param1"], param2=params["param2"],
                    min_radius=params["min_radius"], max_radius=params["max_radius"],
                    method=method)
            # กรองวงที่ขอบจริงไม่รองรับ และรวมวงที่ซ้อนกันให้เหลือวงเดียว
            circles, edges = verify_circles(channels, raw, params["param1"],
                                            params["min_support"])

            # ตัดสินว่าเป็นลูกกอล์ฟไหม ถ้าใช่ค่อยบอกสี
            labels, detections = [], []
            for (x, y, r, support) in circles:
                feats = ball_features(clean_frame, x, y, r)
                golf, reason, texture = is_golf_ball(
                    clean_frame, x, y, r, config.GOLF_MIN_TEXTURE,
                    config.GOLF_RADIUS_RANGE, texture=feats["texture"])
                # วัดสีทุกกรณี เพราะสีเป็นตัวแยกลูกปิงปองออกจากลูกกอล์ฟ
                color, ratio, hsv = classify_color(
                    clean_frame, x, y, r, config.COLOR_RANGES,
                    config.MIN_COLOR_RATIO)

                # ขนาดผ่านแล้วยังไม่พอ สีต้องเป็นสีของลูกกอล์ฟด้วย
                # ลูกปิงปองสีส้มมีขนาดเท่าลูกกอล์ฟเป๊ะ ตัดออกได้ด้วยสีเท่านั้น
                if golf and color not in config.GOLF_COLORS:
                    golf, reason = False, f"wrong color: {color}"

                if golf:
                    labels.append(f"Golf Ball - {color} {ratio:.0%}")
                else:
                    labels.append(f"Not Golf Ball ({reason})")
                detections.append({"golf": golf, "color": color, "reason": reason,
                                   "radius": r, "texture": texture,
                                   "support": support, "hsv": hsv, **feats})

            golf_count = sum(1 for d in detections if d["golf"])
            reject_count = len(detections) - golf_count

            fps_counter.update()
            draw_verified(frame, circles, labels)
            # แจกแจงสีให้เห็นบนจอ เวลามีลูกบอลหลายลูกพร้อมกัน
            by_color = Counter(d["color"] for d in detections if d["golf"])
            breakdown = " ".join(f"{c}:{n}" for c, n in sorted(by_color.items()))

            # สถิติ / กราฟ / บันทึกภาพ นับเฉพาะตอนภาพนิ่งแล้ว
            # ไม่งั้นลูกที่มือบังครึ่งลูกจะถูกนับเป็น "สิ่งแปลกปลอม" ทุกครั้งที่หยิบจับ
            if ready:
                stats.update(detections)
                if publisher is not None:
                    publisher.update(detections, fps_counter.fps)
            draw_text_lines(frame, [
                f"FPS: {fps_counter.fps:.1f}   Circles: {len(circles)}/{len(raw)}",
                f"Golf Ball: {golf_count} [{breakdown or '-'}]   Rejected: {reject_count}",
                "Q=quit  S=save  D=debug  C=calibrate color",
            ])
            if gate is not None:
                if ready:
                    status, color = "Scene still - counting", (0, 255, 0)
                elif gate.ratio > gate.max_ratio:
                    status, color = f"Moving ({gate.ratio:.1%}) - not counting", (0, 0, 255)
                else:
                    status = f"Waiting {gate.still_for:.1f}/{gate.still_seconds:.1f}s"
                    color = (0, 200, 255)
                draw_text_lines(frame, [status], origin=(10, 120), color=color)

            if collector is not None and collector.log(detections):
                # แสดงความคืบหน้าเป็นระยะ จะได้รู้ว่าเก็บได้พอหรือยัง
                if collector.count % 25 < len(detections):
                    print(f"   เก็บข้อมูลแล้ว {collector.count} แถว "
                          f"(พื้นผิวล่าสุด {detections[0]['texture']:.1f})")

            # บันทึกอัตโนมัติ - ตัวบันทึกจะตัดสินเองว่าเฟรมนี้ควรเก็บไหม
            if recorder is not None and ready:
                saved_path, message = recorder.update(frame, detections, clean_frame)
                if saved_path:
                    stats.events += 1
                    print(f"[{datetime.now():%H:%M:%S}] {message}")
                    print(f"             บันทึกภาพ: {saved_path}")
                    if publisher is not None:
                        publisher.event(detections, message, saved_path)

            if args.headless:
                continue

            cv2.imshow(config.DETECT_WINDOW_NAME, frame)
            if show_debug:
                # แสดงภาพขอบที่ใช้ตรวจสอบ จะเห็นเลยว่าทำไมวงไหนผ่านหรือไม่ผ่าน
                cv2.imshow(DEBUG_WINDOW, edges)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), ord("Q"), 27):
                print("ปิดโปรแกรมตามคำสั่งผู้ใช้")
                break
            if key in (ord("s"), ord("S")):
                print(f"บันทึกภาพแล้ว: {save_snapshot(clean_frame)}")
            if key in (ord("c"), ord("C")):
                if circles:
                    x, y, r, _ = circles[0]
                    scores = color_scores(clean_frame, x, y, r, config.COLOR_RANGES)
                    _, _, hsv = classify_color(clean_frame, x, y, r,
                                               config.COLOR_RANGES,
                                               config.MIN_COLOR_RATIO)
                    feats = ball_features(clean_frame, x, y, r)
                    golf, reason, texture = is_golf_ball(
                        clean_frame, x, y, r, config.GOLF_MIN_TEXTURE,
                        config.GOLF_RADIUS_RANGE, texture=feats["texture"])
                    print(f"             ขอบ={feats['edge_density']:.3f}  "
                          f"จุดสะท้อนแสง={feats['bright_frac']:.3f}  "
                          f"กระจายความสว่าง={feats['v_std']:.1f}")
                    print(f"[calibrate] ลูกที่ใหญ่ที่สุด r={r}  ค่า HSV ที่วัดได้ = {hsv}")
                    print(f"             พื้นผิว = {texture:.1f} "
                          f"(เกณฑ์ลูกกอล์ฟ >= {config.GOLF_MIN_TEXTURE})"
                          f" -> {'ลูกกอล์ฟ' if golf else 'ไม่ใช่ลูกกอล์ฟ (' + reason + ')'}")
                    for cname, cratio in sorted(scores.items(), key=lambda kv: -kv[1]):
                        print(f"             {cname:<8} ตรงกับช่วงสีนี้ {cratio:.0%}")
                else:
                    print("[calibrate] ยังไม่เจอลูกบอลในภาพ")
            if key in (ord("d"), ord("D")):
                show_debug = not show_debug
                if not show_debug:
                    cv2.destroyWindow(DEBUG_WINDOW)

            if window_closed(config.DETECT_WINDOW_NAME):
                print("หน้าต่างถูกปิด")
                break

    except KeyboardInterrupt:
        print("\nหยุดด้วย Ctrl+C")

    finally:
        cap.release()
        if not args.headless:
            cv2.destroyAllWindows()
        if publisher is not None:
            publisher.close()
        if collector is not None:
            print(f"เก็บข้อมูลของ '{collector.label}' ได้ทั้งหมด {collector.count} แถว "
                  f"-> {collector.csv_path}")
        else:
            summary = stats.report()
            print("\n" + summary)
            # เขียนลงไฟล์ด้วย เผื่อ terminal ถูกปิดไปก่อนหรือมองไม่ทัน
            with open(config.SUMMARY_FILE, "a", encoding="utf-8") as f:
                f.write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}]\n{summary}\n")
            print(f"(สรุปนี้ถูกบันทึกไว้ใน {config.SUMMARY_FILE} ด้วย)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
