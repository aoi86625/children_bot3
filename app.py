from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageMessage
import os
import io
import openai
import base64
from google.cloud import vision

app = Flask(__name__)

# LINE設定
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# Google Vision設定
credentials_base64 = os.getenv('GOOGLE_APPLICATION_CREDENTIALS_BASE64')
credentials_json_path = "service_account.json"
vision_client = None

if credentials_base64:
    with open(credentials_json_path, "wb") as f:
        f.write(base64.b64decode(credentials_base64))
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_json_path
    vision_client = vision.ImageAnnotatorClient()

# OpenAI設定
openai.api_key = os.getenv('OPENAI_API_KEY')

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
def handle_image_message(event):
    # LINEから画像取得
    message_content = line_bot_api.get_message_content(event.message.id)
    image_bytes = io.BytesIO(message_content.content)

    if vision_client is None:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="OCR設定が正しく行われていません。")
        )
        return

    # Vision APIでOCR
    image = vision.Image(content=image_bytes.getvalue())
    response = vision_client.text_detection(image=image)
    texts = response.text_annotations
    if not texts:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="画像から文字が検出できませんでした。"))
        return

    ocr_text = texts[0].description.strip()
    print("OCR結果:", ocr_text)

    # セクション分割用プロンプト
    section_split_prompt = f"""
あなたはプリントのテキストを整理するアシスタントです。
以下のOCRで取得したテキストを、内容ごとに「自然なセクション」に分割してください。
- 目安となる区切りは「見出し・大きな改行・段落の切れ目」です。
- セクションは「表形式」「リスト形式」「文章形式」のいずれかに分類できる単位にしてください。
- それぞれのセクションに「仮タイトル」をつけてください。（例：「時間割」「持ち物」「行事予定」など）
- セクションの区切りは「---」で表現してください。

# 入力テキスト
{ocr_text}
    """

    try:
        section_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": section_split_prompt}]
        )
        sections_text = section_response.choices[0].message.content
    except Exception as e:
        print("OpenAI APIリクエストエラー:", e)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="エラーが発生しました。後でもう一度試してください。"))
        return

    # 応答（仮） - 分割されたセクションをそのまま返す
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=f"セクション分割結果:\n{sections_text[:4000]}")
    )

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host="0.0.0.0", port=port)
