from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageMessage
import os
import io
import base64
import requests
from google.cloud import vision

# Flaskアプリ
app = Flask(__name__)

# LINEの環境変数
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# Render環境変数から認証情報を復元してファイル保存
if os.getenv('GOOGLE_CREDENTIALS_BASE64'):
    decoded_credentials = base64.b64decode(os.getenv('GOOGLE_CREDENTIALS_BASE64'))
    with open('gcp_credentials.json', 'wb') as f:
        f.write(decoded_credentials)
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'gcp_credentials.json'

# Vision APIクライアント
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
    # テキストメッセージはオウム返し
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=event.message.text)
    )

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    # 画像メッセージを取得
    message_content = line_bot_api.get_message_content(event.message.id)
    image_bytes = io.BytesIO(message_content.content)

    # Vision APIに画像を送ってOCR実行
    image = vision.Image(content=image_bytes.getvalue())
    response = vision_client.text_detection(image=image)
    texts = response.text_annotations

    # OCRで取得したテキストを返信
    if texts:
        detected_text = texts[0].description.strip()
    else:
        detected_text = "文字が検出できませんでした。"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=detected_text)
    )

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host="0.0.0.0", port=port)
