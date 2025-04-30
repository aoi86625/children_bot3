from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageMessage
import os
import io
import base64
import openai
from google.cloud import vision
from usage_counter import can_use_api, increment_usage

# Flaskアプリ
app = Flask(__name__)

# LINEの環境変数
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# OpenAI APIキー
openai.api_key = os.getenv("OPENAI_API_KEY")

# Vision APIクレデンシャルの設定（Base64経由）
encoded_key = os.getenv("GOOGLE_CREDENTIALS_BASE64")
if encoded_key:
    decoded_key = base64.b64decode(encoded_key).decode()
    with open("service_account.json", "w") as f:
        f.write(decoded_key)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "service_account.json"

vision_client = vision.ImageAnnotatorClient()

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except Exception as e:
        print(e)
        abort(400)

    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=event.message.text)
    )

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    if not can_use_api():
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="⚠️ GPTの利用回数が本日の上限（10回）に達しました。明日またご利用ください。")
        )
        return

    # 画像取得
    message_content = line_bot_api.get_message_content(event.message.id)
    image_bytes = io.BytesIO(message_content.content)

    # OCR処理
    image = vision.Image(content=image_bytes.getvalue())
    response = vision_client.text_detection(image=image)
    texts = response.text_annotations

    if not texts:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="OCR設定が正しく行われていません。")
        )
        return

    ocr_text = texts[0].description.strip()

    # OpenAIに送信
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "あなたは学校プリントのOCR結果を理解し、情報構造ごとにセクションを分類・抽出するAIです。表、リスト、テキストなどを見分け、用途ごとに使えるようにJSON形式で返してください。"
                },
                {
                    "role": "user",
                    "content": ocr_text
                }
            ],
            temperature=0.3,
        )
        increment_usage()
        answer = response.choices[0].message.content.strip()
    except Exception as e:
        answer = f"OpenAI APIリクエストエラー: {e}"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=answer)
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
