"""Phase 7: ส่งผลการตรวจจับเป็น JSON ผ่าน MQTT (ขั้นที่ 2 ในโฟลว์ "Publish JSON Result")

ส่ง 2 แบบไปที่ topic เดียวกัน (golf/vision/result) แยกด้วยฟิลด์ "type"

  1. "status" - สรุปทุก ๆ 1 วินาที (ค่าสูงสุดที่เห็นในช่วงนั้น)
     Node-RED เอาไปบันทึกลง InfluxDB -> Grafana วาดกราฟ real-time
  2. "event"  - ส่งทันทีเมื่อ EventRecorder บันทึกภาพ (ฉากเปลี่ยน/นิ่งพอแล้ว)
     Node-RED เอาไปแจ้ง Telegram (ถ้ามีสิ่งแปลกปลอม) และรวบรวมส่ง Google Sheets

ทำไมสถานะใช้ "ค่าสูงสุดในช่วง 1 วินาที" แทนค่าของเฟรมล่าสุด:
กล้องส่ง ~15 เฟรม/วินาที และวงกลมกะพริบหายไปบางเฟรมได้ ถ้าส่งเฟรมล่าสุด
กราฟจะกระโดดขึ้นลงไม่ตรงกับของที่วางอยู่จริง

ถ้า broker ยังไม่เปิด (ยังไม่ได้ docker compose up) โปรแกรมตรวจจับยังทำงานต่อได้ปกติ
แค่ข้อความจะไม่ถูกส่ง และ paho จะพยายามต่อใหม่ให้เองเรื่อย ๆ
"""

import json
import os
import time
from collections import Counter
from datetime import datetime

try:
    import paho.mqtt.client as mqtt
except ImportError:  # ยังไม่ได้ pip install paho-mqtt
    mqtt = None


class ResultPublisher:
    def __init__(self, host, port, topic, status_topic, device_id,
                 interval=1.0, colors=("White", "Neon", "Pink")):
        self.host = host
        self.port = port
        self.topic = topic
        self.status_topic = status_topic
        self.device_id = device_id
        self.interval = interval
        self.colors = colors

        self.connected = False
        self.sent = 0
        self._last_sent = time.time()
        self._reset_window()

        self._client = None
        if mqtt is None:
            print("WARNING: ไม่พบ paho-mqtt จะไม่ส่งข้อมูล MQTT "
                  "(ติดตั้งด้วย: pip install -r requirements.txt)")
            return

        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                             client_id=f"golf-{device_id}-{os.getpid()}")
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        # ถ้าโปรแกรมดับไปแบบไม่ทันบอกลา broker จะประกาศ offline แทนให้ (Last Will)
        client.will_set(status_topic, self._status_payload("offline"), qos=1, retain=True)
        client.reconnect_delay_set(min_delay=1, max_delay=10)
        # connect_async ไม่บล็อก - ถ้า broker ยังไม่เปิด โปรแกรมก็เปิดกล้องต่อได้เลย
        client.connect_async(host, port, keepalive=30)
        client.loop_start()
        self._client = client

    # ------------------------------------------------------------------
    # callback ของ paho (ทำงานใน thread ของ paho ไม่ใช่ thread หลัก)
    # ------------------------------------------------------------------
    def _on_connect(self, client, _userdata, _flags, reason_code, _properties):
        if reason_code.is_failure:
            print(f"[MQTT] ต่อ broker ไม่ได้: {reason_code}")
            return
        self.connected = True
        print(f"[MQTT] เชื่อมต่อ {self.host}:{self.port} แล้ว -> ส่งไปที่ topic '{self.topic}'")
        client.publish(self.status_topic, self._status_payload("online"), qos=1, retain=True)

    def _on_disconnect(self, _client, _userdata, _flags, reason_code, _properties):
        if self.connected:
            print(f"[MQTT] หลุดจาก broker ({reason_code}) กำลังลองต่อใหม่...")
        self.connected = False

    # ------------------------------------------------------------------
    # เรียกจากลูปหลัก
    # ------------------------------------------------------------------
    def update(self, detections, fps):
        """เรียกทุกเฟรม: สะสมค่าไว้ แล้วส่งสรุปเมื่อครบ interval"""
        golf = Counter(d["color"] for d in detections if d["golf"])
        rejects = sum(1 for d in detections if not d["golf"])

        w = self._window
        w["frames"] += 1
        w["golf_count"] = max(w["golf_count"], sum(golf.values()))
        w["reject_count"] = max(w["reject_count"], rejects)
        for color in self.colors:
            w["colors"][color] = max(w["colors"][color], golf.get(color, 0))
        if rejects:
            w["reasons"].update(d["reason"] for d in detections if not d["golf"])

        now = time.time()
        if now - self._last_sent < self.interval:
            return

        payload = self._base("status")
        payload.update({
            "fps": round(fps, 1),
            "frames": w["frames"],
            "golf_count": w["golf_count"],
            "reject_count": w["reject_count"],
            "colors": dict(w["colors"]),
            "reject_reasons": dict(w["reasons"]),
        })
        self._publish(payload, qos=0)
        self._last_sent = now
        self._reset_window()

    def event(self, detections, message, image_path):
        """เรียกเมื่อ EventRecorder บันทึกภาพ: ส่งรายละเอียดทุกลูกทันที"""
        golf = [d for d in detections if d["golf"]]
        rejects = [d for d in detections if not d["golf"]]
        colors = Counter(d["color"] for d in golf)

        if golf and rejects:
            kind = "mixed"
        elif rejects:
            kind = "reject"
        else:
            kind = "golf"

        payload = self._base("event")
        payload.update({
            "kind": kind,
            "golf_count": len(golf),
            "reject_count": len(rejects),
            "colors": {c: colors.get(c, 0) for c in self.colors},
            "rejects": [{"reason": d["reason"], "color": d["color"], "radius": int(d["radius"])}
                        for d in rejects],
            "balls": [{"golf": bool(d["golf"]), "color": d["color"], "radius": int(d["radius"]),
                       "support": round(float(d["support"]), 2)} for d in detections],
            "message": message,
            "image": os.path.basename(image_path) if image_path else None,
        })
        self._publish(payload, qos=1)

    def close(self):
        if self._client is None:
            return
        if self.connected:
            info = self._client.publish(self.status_topic, self._status_payload("offline"),
                                        qos=1, retain=True)
            info.wait_for_publish(timeout=2)
        self._client.loop_stop()
        self._client.disconnect()
        print(f"[MQTT] ส่งข้อมูลไปทั้งหมด {self.sent} ข้อความ")

    # ------------------------------------------------------------------
    def _publish(self, payload, qos):
        if self._client is None or not self.connected:
            return
        # ensure_ascii=False ให้ข้อความภาษาไทยอ่านออกใน MQTTX / Node-RED debug
        self._client.publish(self.topic, json.dumps(payload, ensure_ascii=False), qos=qos)
        self.sent += 1

    def _base(self, msg_type):
        return {
            "type": msg_type,
            "device": self.device_id,
            "ts": int(time.time() * 1000),            # มิลลิวินาที ใช้เป็นเวลาใน InfluxDB
            "time": datetime.now().isoformat(timespec="seconds"),
        }

    def _status_payload(self, state):
        return json.dumps({"device": self.device_id, "state": state,
                           "time": datetime.now().isoformat(timespec="seconds")})

    def _reset_window(self):
        self._window = {"frames": 0, "golf_count": 0, "reject_count": 0,
                        "colors": Counter({c: 0 for c in self.colors}),
                        "reasons": Counter()}
