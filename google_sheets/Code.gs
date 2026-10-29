/**
 * @OnlyCurrentDoc
 * ^ ขอสิทธิ์เฉพาะ Sheet ที่ผูกกับสคริปต์นี้ ไม่ใช่ทุก Sheet ในบัญชี
 *   (Web app ตั้งเป็น Anyone + รันในนามเรา ถ้าไม่จำกัดไว้ สคริปต์จะมีสิทธิ์แก้ทุก Sheet ที่เรามี)
 */

/**
 * ขั้นที่ 4b: รับข้อมูลเป็นชุด (Batch) จาก Node-RED แล้วบันทึกลง Google Sheets
 *
 * วิธีติดตั้ง (เหมือนสัปดาห์ที่ 10):
 *   1. สร้าง Google Sheet ใหม่ -> Extensions > Apps Script
 *   2. ลบโค้ดเดิม วางไฟล์นี้ทั้งไฟล์ แล้วกด Save
 *   3. Deploy > New deployment > เลือกชนิด Web app
 *        Execute as: Me      Who has access: Anyone
 *   4. ก๊อป URL ที่ได้ (https://script.google.com/macros/s/xxxx/exec)
 *      ไปใส่ GSHEET_URL ในไฟล์ .env แล้วสั่ง docker compose up -d nodered
 *
 * Node-RED ส่งมาแบบนี้:
 *   { "sheet": "detections", "rows": [[เวลา, กล้อง, ประเภท, ...], ...] }
 */

const HEADER = ['เวลา', 'กล้อง', 'ประเภท', 'ลูกกอล์ฟ', 'แปลกปลอม',
                'ขาว', 'นีออน', 'ชมพู', 'สาเหตุที่ปฏิเสธ', 'ข้อความ', 'ไฟล์ภาพ'];

function doPost(e) {
  const data = JSON.parse(e.postData.contents);
  const rows = data.rows || [];
  if (rows.length === 0) return reply({ ok: true, added: 0 });

  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const name = data.sheet || 'detections';
  const sheet = ss.getSheetByName(name) || ss.insertSheet(name);

  if (sheet.getLastRow() === 0) {
    sheet.appendRow(HEADER);
    sheet.getRange(1, 1, 1, HEADER.length).setFontWeight('bold');
    sheet.setFrozenRows(1);
  }

  // เขียนทีเดียวทั้งชุด เร็วกว่า appendRow ทีละแถวมาก
  sheet.getRange(sheet.getLastRow() + 1, 1, rows.length, rows[0].length).setValues(rows);
  return reply({ ok: true, added: rows.length });
}

// เปิด URL ในเบราว์เซอร์เพื่อเช็คว่า deploy สำเร็จ
function doGet() {
  return reply({ ok: true, message: 'Golf Vision Sheets endpoint is running' });
}

function reply(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
