#!/usr/bin/env python3
"""ดูข้อความ MQTT ที่วิ่งอยู่ใน broker แบบสด ๆ (ใช้แทน MQTTX ตอนเช็คงาน)

การใช้งาน:
    python tools/mqtt_monitor.py                 # ดูทุกอย่างใต้ golf/#
    python tools/mqtt_monitor.py --events        # ดูเฉพาะ event (ซ่อน status รายวินาที)
    python tools/mqtt_monitor.py --host 10.147.17.5   # ดู broker เครื่องอื่นผ่าน ZeroTier
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paho.mqtt.client as mqtt

import config


def main() -> int:
    parser = argparse.ArgumentParser(description="ดูข้อความ MQTT ของโปรเจกต์ลูกกอล์ฟ")
    parser.add_argument("--host", default=config.MQTT_HOST)
    parser.add_argument("--port", type=int, default=config.MQTT_PORT)
    parser.add_argument("--topic", default="golf/#")
    parser.add_argument("--events", action="store_true", help="ซ่อนข้อความ status รายวินาที")
    args = parser.parse_args()

    def on_connect(client, _userdata, _flags, reason_code, _properties):
        if reason_code.is_failure:
            print(f"ต่อ broker ไม่ได้: {reason_code}")
            return
        print(f"เชื่อมต่อ {args.host}:{args.port} แล้ว กำลังฟัง '{args.topic}' (Ctrl+C เพื่อหยุด)\n")
        client.subscribe(args.topic, qos=1)

    def on_message(_client, _userdata, msg):
        text = msg.payload.decode("utf-8", errors="replace")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            print(f"{msg.topic}  {text}")
            return
        if args.events and data.get("type") == "status":
            return
        if data.get("type") == "status":
            # status ส่งทุกวินาที พิมพ์บรรทัดเดียวพอ จะได้ไม่รก
            colors = " ".join(f"{k}:{v}" for k, v in data.get("colors", {}).items())
            print(f"{data['time']}  status  golf={data['golf_count']} reject={data['reject_count']}"
                  f"  [{colors}]  fps={data['fps']}")
        else:
            print(f"{msg.topic}\n{json.dumps(data, ensure_ascii=False, indent=2)}\n")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect(args.host, args.port, keepalive=30)
    except OSError as e:
        print(f"ERROR: ต่อ {args.host}:{args.port} ไม่ได้ ({e})")
        print("Docker stack เปิดอยู่หรือยัง?  ลองสั่ง: docker compose up -d")
        return 1
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\nหยุดแล้ว")
    return 0


if __name__ == "__main__":
    sys.exit(main())
