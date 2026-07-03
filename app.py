"""
app.py — LINE Quiz-Answer Bot

Flow:
  User sends a photo of a trivia/riddle question -> bot downloads the image ->
  Gemini Vision reads the question and answers it -> bot replies with the short
  answer as fast as possible (single Gemini call, synchronous reply).
"""
import os
import logging

from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    MessagingApiBlob,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent, ImageMessageContent

from gemini_solver import solve_question_image, solve_question_text

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = Flask(__name__)

LINE_CHANNEL_SECRET = os.environ["LINE_CHANNEL_SECRET"]
LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

HELP_TEXT = (
    "สวัสดีค้าบ ส่งรูปคำถามเชาว์/ปัญหา หรือพิมพ์คำถามมาได้เลย "
    "บอทจะอ่านโจทย์และตอบคำตอบสั้นๆ ให้ทันทีครับ 📸🧠"
)


@app.route("/health", methods=["GET"])
def health():
    return "ok", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK", 200


@handler.add(MessageEvent, message=TextMessageContent)
def handle_text(event):
    text = (event.message.text or "").strip()

    # Simple greetings / empty text -> show the help message instead of
    # sending it to Gemini as a "question".
    if not text or text.lower() in {"hi", "hello", "help", "สวัสดี", "start", "menu"}:
        answer = HELP_TEXT
    else:
        answer = solve_question_text(text)

    with ApiClient(configuration) as api_client:
        MessagingApi(api_client).reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=answer)],
            )
        )


@handler.add(MessageEvent, message=ImageMessageContent)
def handle_image(event):
    message_id = event.message.id

    with ApiClient(configuration) as api_client:
        blob_api = MessagingApiBlob(api_client)
        image_bytes = blob_api.get_message_content(message_id)

        answer = solve_question_image(image_bytes)

        MessagingApi(api_client).reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=answer)],
            )
        )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
