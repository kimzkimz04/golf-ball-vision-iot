# OpenCV Container (ขั้นที่ 2 ในโฟลว์) - ตรวจจับลูกกอล์ฟแบบไม่มีหน้าต่าง แล้วส่งผลไป MQTT
#   docker compose --profile vision up -d --build
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    OPENCV_LOG_LEVEL=ERROR

WORKDIR /app

# image slim ไม่มีข้อมูลเขตเวลา ถ้าไม่ลง tzdata ตั้ง TZ=Asia/Bangkok ไปก็ยังเป็นเวลา UTC
# (ชื่อไฟล์ภาพและช่อง "time" ใน MQTT จะช้าไป 7 ชั่วโมง)
RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

# ใช้ opencv-python-headless เพราะใน container ไม่มีจอ (ไม่ต้องลง libGL / Qt)
COPY requirements-docker.txt .
RUN pip install --no-cache-dir -r requirements-docker.txt

COPY config.py ball_detect.py ./
COPY utils ./utils
# ภาพตัวอย่าง 28 รูปจากระยะกล้องปัจจุบัน สำหรับโหมดรีเพลย์ (OPENCV_SOURCE=samples)
COPY samples ./samples

CMD ["python", "-u", "ball_detect.py", "--headless", "--source", "samples"]
