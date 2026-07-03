# LINE Quiz-Answer Bot

ส่งรูปคำถามเชาว์/ปริศนา หรือพิมพ์คำถามเข้าไลน์ บอทจะอ่านโจทย์ด้วย Gemini แล้วตอบคำตอบสั้นๆ กลับทันที

## 1. สร้าง LINE Channel

1. เข้า [LINE Developers Console](https://developers.line.biz/console/) → สร้าง Provider (ถ้ายังไม่มี)
2. สร้าง Channel ประเภท **Messaging API**
3. ไปที่แท็บ **Basic settings** → คัดลอก **Channel secret**
4. ไปที่แท็บ **Messaging API** → กด Issue เพื่อสร้าง **Channel access token**
5. ในหน้า Messaging API: ปิด **Auto-reply messages** และ **Greeting messages** (ที่ manager.line.biz)

## 2. ขอ Gemini API Key

ไปที่ [Google AI Studio](https://aistudio.google.com/apikey) → สร้าง API key

## 3. Deploy บน Railway

1. Push โฟลเดอร์นี้ขึ้น GitHub repo ใหม่
2. เข้า [Railway](https://railway.app) → New Project → Deploy from GitHub repo → เลือก repo นี้
3. ไปที่ Variables ใส่ค่าตามนี้:

| ตัวแปร | ค่า |
|---|---|
| `LINE_CHANNEL_SECRET` | จากขั้นตอนที่ 1 |
| `LINE_CHANNEL_ACCESS_TOKEN` | จากขั้นตอนที่ 1 |
| `GEMINI_API_KEY` | จากขั้นตอนที่ 2 |
| `GEMINI_MODEL` | `gemini-2.5-flash` (ค่าเริ่มต้น ไม่ต้องใส่ก็ได้) |
| `GEMINI_FALLBACK_MODEL` | `gemini-2.5-flash-lite` (ค่าเริ่มต้น ไม่ต้องใส่ก็ได้) |

4. กด Deploy รอจน build เสร็จ
5. ไปที่ Settings → Networking → กด **Generate Domain** เพื่อเอา public URL

## 4. ตั้งค่า Webhook

1. กลับไปที่ LINE Developers Console → แท็บ Messaging API
2. ใส่ **Webhook URL** เป็น `https://YOUR-DOMAIN.up.railway.app/webhook`
3. กด **Verify** ให้ขึ้นสีเขียว
4. เปิด toggle **Use webhook**

## 5. ทดสอบ

เพิ่มบอทเป็นเพื่อนผ่าน QR code ในหน้า Messaging API แล้วส่งรูปคำถามเชาว์เข้าไปได้เลย

---

## ข้อควรระวัง (จากประสบการณ์จริง)

- **ห้ามใช้ `gemini-2.0-flash`** — โมเดลนี้ถูกปลดระวางไปแล้ว (2026-06-01) ใช้ `gemini-2.5-flash` แทน ถ้า error `503/404 ... models/<name>:generateContent` ให้เช็คตัวแปร `GEMINI_MODEL`
- ใช้ SDK ใหม่ `google-genai` (`from google import genai`) เท่านั้น ห้ามติดตั้ง/import `google-generativeai` ตัวเก่าปนกัน — จะทำให้ handler รูปภาพ error เงียบๆ (บอทรับรูปแต่ไม่ตอบ)
- Procfile ใช้ `--workers 1 --threads 4` เท่านั้น (ป้องกันปัญหาถ้าในอนาคตเพิ่ม background job)
- ถ้า Webhook ขึ้น 400: เช็คว่า `LINE_CHANNEL_SECRET` เป็นค่า hex ไม่ใช่ Channel ID ที่เป็นตัวเลข
- หลังแก้ค่าตัวแปรใน Railway ต้องกด **Deploy** ใหม่ ไม่งั้น container จะยังใช้ค่าเก่าอยู่

## โครงสร้างไฟล์

```
quiz-bot/
├── app.py            # Flask app + webhook handler
├── gemini_solver.py  # อ่านรูป + ตอบคำถามด้วย Gemini Vision (พร้อม retry/fallback)
├── requirements.txt
├── Procfile
├── railway.toml
└── .env.example
```
