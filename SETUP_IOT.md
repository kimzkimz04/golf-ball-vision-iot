# Golf Ball Vision — ระบบ IoT ตามโฟลว์

ต่อยอดจากโปรเจกต์ตรวจจับลูกกอล์ฟ (ดู [README.md](README.md)) ให้ส่งผลไปเก็บ แจ้งเตือน และแสดงผลบน Dashboard

```
[1] กล้อง ──► [2] OpenCV (ball_detect.py) ──JSON──► Mosquitto  topic: golf/vision/result
                                                     │
                                          [3] Node-RED (Subscribe)
                     ┌───────────────────────────────┼──────────────────────────────┐
              4a. ทุกวินาที                     4c. ไม่ใช่ลูกกอล์ฟ               4b. รวมเป็นชุด
                 InfluxDB  ◄── 6. n8n ดึงสถิติ     Telegram Bot  ◄── 7. รายงานประจำวัน   Google Sheets
                    │           AI สรุป ─────────────────┘
               5a. Grafana  ◄── ZeroTier VPN (ดูจากมือถือ/ที่อื่นได้)
```

| ขั้นในโฟลว์ | ไฟล์ที่เกี่ยวข้อง | เปิดดูที่ |
|---|---|---|
| 1. กล้อง | `camera_stream.py` (เฉพาะโหมด Docker) | http://localhost:8090 |
| 2. OpenCV + Publish JSON | `ball_detect.py`, `utils/mqtt_pub.py`, `Dockerfile` | หน้าต่างภาพ / terminal |
| 2. Mosquitto | `docker/mosquitto/config/mosquitto.conf` | `localhost:1883` |
| 3. Node-RED | `docker/nodered/flows.json` | http://localhost:1880 |
| 4a/5. InfluxDB | (สร้างอัตโนมัติจาก `.env`) | http://localhost:8086 |
| 4b. Google Sheets | `google_sheets/Code.gs` | Google Sheet ของคุณ |
| 4c/7. Telegram | ใน `flows.json` และ workflow n8n | แอป Telegram |
| 5a. Grafana | `docker/grafana/...` | http://localhost:3000 |
| 6. n8n + AI | `docker/n8n/workflows/golf-daily-report.json` | http://localhost:5678 |
| 5. ZeroTier | ติดตั้งบน Windows | http://`<ZeroTier IP>`:3000 |

รหัสผ่านทั้งหมดอยู่ในไฟล์ `.env` (มีอยู่แล้ว สุ่มรหัส InfluxDB/Grafana ให้แล้ว) — **ห้ามอัปขึ้น GitHub**

---

## ขั้นที่ 0: โปรแกรมที่ต้องติดตั้ง (ครั้งเดียว)

| โปรแกรม | ใช้ทำอะไร | ติดตั้ง |
|---|---|---|
| WSL2 | Docker Desktop ต้องใช้ | PowerShell (Run as Administrator): `wsl --install --no-distribution` แล้ว **Restart** |
| Docker Desktop | รัน Mosquitto / Node-RED / InfluxDB / Grafana / n8n | `winget install -e --id Docker.DockerDesktop` |
| ZeroTier One | VPN ดู Dashboard จากที่อื่น | `winget install -e --id ZeroTier.ZeroTierOne` |
| VS Code: Python | กด F5 รัน/ดีบัก | `code --install-extension ms-python.python` |
| Git (ไม่บังคับ) | ส่งงานขึ้น GitHub | `winget install -e --id Git.Git` |

Python 3.12 และ `.venv` (OpenCV 5 + paho-mqtt) ติดตั้งไว้แล้ว ถ้าต้องติดตั้งใหม่:

```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

---

## ขั้นที่ 1: เปิด Docker stack

เปิด Docker Desktop ให้ขึ้นว่า *Engine running* ก่อน แล้วใน terminal ของ VS Code:

```bash
docker compose up -d
```

เช็คว่าขึ้นครบ 5 ตัว (ควรเป็น `running` ทั้งหมด):

```bash
docker compose ps
```

> หรือใน VS Code: `Ctrl+Shift+P` → **Tasks: Run Task** → *Docker: เปิดระบบ IoT*

## ขั้นที่ 2: รันตัวตรวจจับ (เห็นภาพ + เช็คง่ายใน VS Code)

แท็บ **Run and Debug** (`Ctrl+Shift+D`) เลือกแล้วกด ▶ (หรือ F5)

| ตัวเลือก | ใช้ตอนไหน |
|---|---|
| 4. สแกนหากล้อง | ดูชื่อและ index ของกล้องทุกตัว — โปรแกรมเลือกกล้องจากชื่อ `CAMERA_NAME = "RealSense"` ใน `config.py` ถ้าเปลี่ยนกล้องให้แก้ตรงนั้น |
| 1. ตรวจจับลูกกอล์ฟ + ส่ง MQTT | ใช้งานจริงกับกล้อง |
| 3. รีเพลย์ภาพตัวอย่าง samples | ทดสอบทั้งระบบโดยไม่ต้องมีกล้อง (ภาพจริง 28 รูปในโฟลเดอร์ `samples/` วนสลับลูกปกติ/แปลกปลอม) |
| 7. เก็บข้อมูลปรับเกณฑ์ | ย้ายกล้อง/เปลี่ยนแสงแล้ว ต้องเก็บข้อมูลใหม่ (เลือกชื่อลูกจากรายการ) แล้วรัน **8. วิเคราะห์ข้อมูลที่เก็บ** |
| 5. ดูข้อความ MQTT สด ๆ | เปิดคู่กันเพื่อดูว่า JSON ถูกส่งออกไปจริง |

terminal ต้องขึ้น `[MQTT] เชื่อมต่อ localhost:1883 แล้ว` ถ้าขึ้นว่าต่อไม่ได้ = Docker ยังไม่เปิด
(ตัวตรวจจับยังทำงานต่อได้ แค่ไม่มีข้อมูลส่งออก)

ตัวอย่าง JSON ที่ส่ง:

```json
{"type": "status", "device": "cam1", "ts": 1793170000000, "time": "2026-10-28T14:00:00",
 "fps": 14.8, "frames": 15, "golf_count": 2, "reject_count": 1,
 "colors": {"White": 1, "Neon": 1, "Pink": 0}, "reject_reasons": {"wrong color: Orange": 15}}
```

`type: "event"` จะส่งทันทีเมื่อกล้องบันทึกภาพเหตุการณ์ (มีรายละเอียดทุกลูก + ข้อความ + ชื่อไฟล์ภาพ)

## ขั้นที่ 3: Node-RED — http://localhost:1880

flow **Golf Vision IoT** โหลดมาให้แล้ว ใต้แต่ละโหนดจะมีสถานะบอกว่าทำงานไหม

- **4a** แปลงเป็น Line Protocol → เขียน InfluxDB ทุกวินาที
- **4c** ตรวจสิ่งแปลกปลอม → Telegram (เว้นระยะเรื่องเดิม 30 วินาที กันสแปม)
- **4b** รวบรวมเป็นชุด → Google Sheets ทุก 60 วินาที
- โหนด *เช็คผลลัพธ์ HTTP* แสดงจำนวนครั้งที่สำเร็จ ✓ / ล้มเหลว ✗ ของแต่ละปลายทาง

## ขั้นที่ 4: Telegram (ขั้น 4c และ 7)

1. Telegram → ค้นหา **@BotFather** → `/newbot` → ได้ token
2. กด **Start** ที่บอทของเรา 1 ครั้ง
3. ค้นหา **@userinfobot** → พิมพ์อะไรก็ได้ → ได้ chat id
4. ใส่ใน `.env` แล้วสั่งให้ Node-RED กับ n8n อ่านค่าใหม่:

```
TELEGRAM_TOKEN=123456:ABC-xyz...
TELEGRAM_CHAT_ID=123456789
```

```bash
docker compose up -d nodered n8n
```

ทดสอบ: วางลูกปิงปองสีส้ม/ลูกเทนนิสหน้ากล้อง → ต้องมีข้อความ ⚠️ เข้า Telegram

## ขั้นที่ 5: Google Sheets (ขั้น 4b)

ทำตามคอมเมนต์บนสุดของ [google_sheets/Code.gs](google_sheets/Code.gs) แล้วใส่ URL ที่ได้ลง `GSHEET_URL` ใน `.env`
จากนั้น `docker compose up -d nodered` — ข้อมูลจะเข้าแท็บ `detections` ทุก 60 วินาที

## ขั้นที่ 6: Grafana — http://localhost:3000

user `admin` / รหัสอยู่ที่ `GRAFANA_PASSWORD` ใน `.env`
Dashboards → **Golf Vision** → **Golf Ball Vision - Real-time** (เชื่อม InfluxDB ไว้ให้แล้ว รีเฟรชทุก 5 วินาที)

## ขั้นที่ 7: n8n รายงานประจำวันด้วย AI — http://localhost:5678

1. เปิดครั้งแรกให้สร้างบัญชีเจ้าของ (เก็บในเครื่องเรา)
2. workflow ถูกนำเข้าไว้แล้ว ถ้าลบไปหรือแก้ไฟล์ JSON ให้นำเข้าใหม่ด้วย:

```bash
docker compose exec n8n n8n import:workflow --input=/workflows/golf-daily-report.json
```

3. เปิด workflow **Golf Daily Report (AI)** → กด **Execute workflow** เพื่อทดสอบ → ดูผลในโหนดสุดท้าย
4. เปิดสวิตช์ **Active** → ส่งรายงานเข้า Telegram ทุกวัน 18:00

AI เลือกได้ 2 ค่าย ใส่ key ใน `.env` แล้ว `docker compose up -d n8n`
- **Google Gemini:** `GEMINI_API_KEY` (สร้างที่ https://aistudio.google.com/apikey) ถ้ามี key นี้จะใช้ Gemini ก่อน
  ถ้ารุ่นใน `GEMINI_MODEL` เลิกให้บริการ โหนดจะหารุ่น flash ที่ยังใช้ได้ให้เอง
- **Claude:** `ANTHROPIC_API_KEY` (สมัครที่ https://platform.claude.com)

ถ้าไม่ใส่ key เลย หรือเรียก AI ไม่สำเร็จ ระบบจะส่งรายงานตัวเลขแบบไม่ใช้ AI แทน (ดูสาเหตุได้ในช่อง `note` ของโหนดสุดท้าย)

## ขั้นที่ 8: ZeroTier — ดู Dashboard / Node-RED จากมือถือ (Remote Access)

1. สมัคร https://my.zerotier.com → **Create A Network** → ได้ Network ID
2. คอมนี้: ไอคอน ZeroTier ที่ taskbar → **Join New Network** → ใส่ Network ID
3. มือถือ: ลงแอป ZeroTier One → Join network เดียวกัน
4. กลับไปที่ my.zerotier.com → ติ๊ก **Auth** ให้ทั้ง 2 เครื่อง → จด *Managed IP* ของคอม (เช่น `10.147.17.5`)
5. เปิด Firewall ให้พอร์ตของระบบ (PowerShell แบบ **Run as Administrator** ครั้งเดียว):

```bash
netsh advfirewall firewall add rule name="Golf IoT" dir=in action=allow protocol=TCP localport=1880,1883,3000,5678,8086
```

6. มือถือเปิด `http://10.147.17.5:3000` (Grafana), `:1880` (Node-RED), `:5678` (n8n)

> เครื่องนี้ (node `73282a7f3c`) อยู่ใน network `88c5b1f3395d5d99` ได้ IP **10.236.55.129**
> → Grafana http://10.236.55.129:3000 · Node-RED http://10.236.55.129:1880 · n8n http://10.236.55.129:5678

SSH เข้าเครื่องผ่าน ZeroTier (เหมือนสัปดาห์ที่ 9): Settings → System → Optional features → เพิ่ม **OpenSSH Server**
แล้วจากอีกเครื่องใช้ VS Code Remote-SSH ไปที่ `ชื่อผู้ใช้@10.147.17.5`

---

## (ทางเลือก) รัน OpenCV ใน Docker container ตามโฟลว์เป๊ะ ๆ

Docker บน Windows มองไม่เห็นกล้อง USB จึงให้ Windows ส่งภาพเป็นสตรีมให้ container

```bash
docker compose --profile vision up -d --build
```

- ค่าเริ่มต้นจะรีเพลย์ภาพใน `samples/` (`OPENCV_SOURCE=samples` ใน `.env`)
- หยุด container: `docker compose stop opencv` (ไม่งั้นภาพรีเพลย์จะไหลเข้า InfluxDB และแจ้ง Telegram ตลอด)
- ใช้กล้องจริง: รัน **6. สตรีมกล้องให้ OpenCV Container** ใน VS Code
  แล้วแก้ `.env` เป็น `OPENCV_SOURCE=http://host.docker.internal:8090/video` แล้วสั่งคำสั่งข้างบนอีกครั้ง
- ดู log: `docker compose logs -f opencv`
- ระหว่างนี้อย่ารัน `ball_detect.py` บน Windows พร้อมกัน (กล้องเปิดได้ทีละโปรแกรม และข้อมูลจะซ้ำ)

## แก้ปัญหาที่เจอบ่อย

| อาการ | สาเหตุ / วิธีแก้ |
|---|---|
| `[MQTT] ต่อ broker ไม่ได้` | Docker Desktop ยังไม่เปิด หรือ `docker compose ps` ไม่เห็น `golf-mosquitto` |
| เปิดกล้องไม่ได้ | รัน *สแกนหากล้อง* แล้วแก้ `CAMERA_INDEX` / ปิด Zoom, Meet, `camera_stream.py` / Settings → Privacy → Camera |
| Grafana ขึ้น *No data* | ยังไม่มีข้อมูลในช่วงเวลาที่เลือก — รันตัวตรวจจับก่อน / ดูโหนด *เช็คผลลัพธ์ HTTP* ใน Node-RED ว่า InfluxDB ✗ ไหม |
| โหนด Telegram ขึ้นสีเหลือง | ยังไม่ได้ใส่ `TELEGRAM_TOKEN` / `TELEGRAM_CHAT_ID` ใน `.env` หรือแก้แล้วยังไม่ `docker compose up -d nodered` |
| เวลาในชื่อไฟล์ภาพ / CSV ช้าไป 6 ชั่วโมง | ใน `.env` ต้องใช้ชื่อ `TIMEZONE=` ห้ามใช้ `TZ=` เพราะ VS Code โหลด `.env` ตอนกด F5 และ Python บน Windows อ่าน `TZ=Asia/Bangkok` ผิด |
| แก้ `.env` แล้วไม่มีผล | ต้อง `docker compose up -d` อีกครั้ง (container อ่านค่าตอนสร้างเท่านั้น) |
| เปลี่ยน `INFLUX_TOKEN` แล้ว InfluxDB ไม่รับ | token ถูกตั้งตอนสร้างฐานข้อมูลครั้งแรกเท่านั้น ต้องลบข้อมูลเดิม: `docker compose down -v` (ข้อมูลหายหมด) |
