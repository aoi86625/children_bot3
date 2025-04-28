import os
import io
import base64
import json
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageMessage
from google.cloud import vision
import openai

# Flask設定
app = Flask(__name__)

# 環境変数取得
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')
GOOGLE_CREDENTIALS_BASE64 = os.getenv('GOOGLE_CREDENTIALS_BASE64')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# LINE Bot API設定
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# Google Vision API設定
credentials_content = base64.b64decode(GOOGLE_CREDENTIALS_BASE64).decode('utf-8')
with open('temp_google_credentials.json', 'w') as f:
    f.write(credentials_content)
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'temp_google_credentials.json'
vision_client = vision.ImageAnnotatorClient()

# OpenAI API設定
openai.api_key = OPENAI_API_KEY

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

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    message_content = line_bot_api.get_message_content(event.message.id)
    image_bytes = io.BytesIO(message_content.content)

    # OCR実行
    image = vision.Image(content=image_bytes.getvalue())
    response = vision_client.text_detection(image=image)
    texts = response.text_annotations
    if not texts:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="文字が検出できませんでした。"))
        return

    ocr_text = texts[0].description.strip()

    # プロンプト作成
    timetable_prompt = f"""
【指示】
OCRで拾取したテキストを、子供向けの「時間割表」としてキレイに整形して、次のJSON形式で結果を紹介してください
- 書かれている科目をすべて一覧化して作り直す
- OCRテキストにないような変な文字は入れない
- 書かれているようにまとめる

# 入力テキスト
{ocr_text}
"""

    belongings_prompt = f"""
【指示】
OCRで拾取したテキストを、子供向けの「持ち物リスト」として次のJSON形式で結果を紹介してください
- 書かれている持ち物をすべて一覧化
- 言葉のブレは入れない
- OCRテキストにないような変な文字は入れない
- カテゴライズしない

# 入力テキスト
{ocr_text}
"""

    # OpenAI API呼び出し
    timetable_response = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": timetable_prompt}]
    )

    belongings_response = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": belongings_prompt}]
    )

    timetable_data = timetable_response.choices[0].message.content
    belongings_data = belongings_response.choices[0].message.content

    # LINEに返信
    reply_text = f"\u6642\u9593\u5272\u7d50\u679c:\n{timetable_data}\n\n\u6301\u3061\u7269\u7d50\u679c:\n{belongings_data}"
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
