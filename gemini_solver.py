"""
gemini_solver.py
Reads a trivia/quiz-question image and returns a short answer using Gemini Vision.
Single-call design (OCR + reasoning combined) to keep LINE reply latency low.
"""
import os
import time
import logging
from io import BytesIO

from google import genai
from google.genai import types
from PIL import Image

log = logging.getLogger(__name__)

_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

# gemini-2.0-flash was retired 2026-06-01 — use gemini-2.5-flash.
# Kept as env vars so a future model deprecation is a one-click Railway change.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_FALLBACK_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash-lite")

TRANSIENT_MARKERS = [
    "503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED",
    "500", "INTERNAL", "overloaded", "high demand",
]

SOLVE_PROMPT = """\
คุณคือผู้ช่วยตอบคำถามเชาว์/ปัญหาที่ส่งมาเป็นรูปภาพ

ขั้นตอน:
1. อ่านคำถามในรูปภาพให้ครบถ้วน (อาจเป็นคำถามเชาว์ ปริศนา คำถามความรู้ทั่วไป
   คำถามคณิตศาสตร์ หรือคำถามปรนัย)
2. คิดหาคำตอบที่ถูกต้องที่สุด
3. ตอบกลับ "เฉพาะคำตอบสั้นๆ" เท่านั้น ห้ามอธิบายเหตุผลหรือขั้นตอนการคิด
   ห้ามพิมพ์คำถามซ้ำ ห้ามมีคำนำหรือคำลงท้าย

รูปแบบคำตอบ:
- ถ้าเป็นคำถามปรนัย (มีตัวเลือก ก/ข/ค/ง หรือ A/B/C/D) ให้ตอบ "ตัวเลือกที่ถูก + คำตอบ"
  เช่น "ข. กุหลาบ"
- ถ้าเป็นคำถามปลายเปิด ให้ตอบคำตอบตรงๆ สั้นที่สุดเท่าที่จะสั้นได้
- ถ้าอ่านคำถามในรูปไม่ออกหรือไม่มั่นใจในคำตอบ ให้ตอบว่า
  "ขออภัยครับ อ่านคำถามในรูปไม่ชัดเจน รบกวนส่งรูปที่ชัดขึ้นอีกครั้งนะครับ"

ตอบเป็นภาษาไทยเสมอ (ยกเว้นคำตอบที่ควรเป็นภาษาอังกฤษ/ตัวเลขโดยธรรมชาติ เช่น ชื่อเฉพาะ)
ใช้คำลงท้ายแบบผู้ชาย (ครับ) ไม่ใช่ค่ะ/คะ
"""

SOLVE_PROMPT_TEXT = """\
คุณคือผู้ช่วยตอบคำถามเชาว์/ปัญหาที่ส่งมาเป็นข้อความ

ขั้นตอน:
1. อ่านคำถามข้อความด้านล่างให้ครบถ้วน (อาจเป็นคำถามเชาว์ ปริศนา คำถามความรู้ทั่วไป
   คำถามคณิตศาสตร์ หรือคำถามปรนัย)
2. คิดหาคำตอบที่ถูกต้องที่สุด
3. ตอบกลับ "เฉพาะคำตอบสั้นๆ" เท่านั้น ห้ามอธิบายเหตุผลหรือขั้นตอนการคิด
   ห้ามพิมพ์คำถามซ้ำ ห้ามมีคำนำหรือคำลงท้าย

รูปแบบคำตอบ:
- ถ้าเป็นคำถามปรนัย (มีตัวเลือก ก/ข/ค/ง หรือ A/B/C/D) ให้ตอบ "ตัวเลือกที่ถูก + คำตอบ"
  เช่น "ข. กุหลาบ"
- ถ้าเป็นคำถามปลายเปิด ให้ตอบคำตอบตรงๆ สั้นที่สุดเท่าที่จะสั้นได้
- ถ้าไม่มั่นใจในคำตอบ ให้ตอบคำตอบที่น่าจะเป็นไปได้มากที่สุดแบบสั้นๆ

ตอบเป็นภาษาไทยเสมอ (ยกเว้นคำตอบที่ควรเป็นภาษาอังกฤษ/ตัวเลขโดยธรรมชาติ เช่น ชื่อเฉพาะ)
ใช้คำลงท้ายแบบผู้ชาย (ครับ) ไม่ใช่ค่ะ/คะ

คำถาม: {question}
"""


def _generate_with_retry(contents, max_attempts: int = 3):
    """Retry transient Gemini errors (503/429/5xx), then fall back to a lighter model."""
    last_err = None
    for model in [GEMINI_MODEL, GEMINI_FALLBACK_MODEL]:
        for attempt in range(max_attempts):
            try:
                return _client.models.generate_content(model=model, contents=contents)
            except Exception as e:
                last_err = e
                msg = str(e)
                if not any(marker in msg for marker in TRANSIENT_MARKERS):
                    raise
                if attempt < max_attempts - 1:
                    time.sleep(2 * (attempt + 1))
    raise last_err


def solve_question_image(image_bytes: bytes) -> str:
    """Given raw image bytes of a trivia/quiz question, return a short answer string."""
    try:
        img = Image.open(BytesIO(image_bytes))
        if img.mode != "RGB":
            img = img.convert("RGB")
        if max(img.size) > 1600:
            ratio = 1600 / max(img.size)
            img = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=90)

        resp = _generate_with_retry([
            SOLVE_PROMPT,
            types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg"),
        ])
        answer = (resp.text or "").strip()
        return answer if answer else "ขออภัยครับ ไม่สามารถประมวลผลคำถามในรูปนี้ได้ รบกวนลองส่งใหม่อีกครั้งนะครับ"
    except Exception as e:
        log.error(f"Gemini solve error: {e}")
        return "ขออภัยครับ เกิดข้อผิดพลาดระหว่างอ่านรูปภาพ รบกวนลองส่งใหม่อีกครั้งนะครับ"


def solve_question_text(question: str) -> str:
    """Given a plain-text trivia/quiz question, return a short answer string."""
    try:
        prompt = SOLVE_PROMPT_TEXT.format(question=question.strip())
        resp = _generate_with_retry([prompt])
        answer = (resp.text or "").strip()
        return answer if answer else "ขออภัยครับ ไม่สามารถตอบคำถามนี้ได้ รบกวนลองถามใหม่อีกครั้งนะครับ"
    except Exception as e:
        log.error(f"Gemini solve (text) error: {e}")
        return "ขออภัยครับ เกิดข้อผิดพลาดระหว่างประมวลผลคำถาม รบกวนลองใหม่อีกครั้งนะครับ"
