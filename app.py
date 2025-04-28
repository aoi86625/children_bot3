import os
import io
import base64
import openai
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageMessage
from google.cloud import vision

# Flaskアプリ
app = Flask(__name__)

# LINE環境変数
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# OpenAI APIキー
openai.api_key = os.getenv("OPENAI_API_KEY")

# 🔥【追加】base64からVision認証キーを復元
encoded_key = os.getenv('GOOGLE_CREDENTIALS_BASE64')
if encoded_key:
    decoded_key = base64.b64decode(encoded_key)
    with open('service_account.json', 'wb') as f:
        f.write(decoded_key)
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'service_account.json'

# Vision APIクライアント
vision_client = vision.ImageAnnotatorClient()

# OpenAI呼び出し関数
def call_openai_for_printer_text(ocr_text):
    system_prompt = """
あなたは、学校から配布された各種プリント（時間割表、行事予定表、持ち物リスト、連絡事項）をOCR結果から解析し、適切なジャンル分類と情報整理を行う専門家です。

【目的】
OCRから得られたテキストを読み取り、
- 「時間割表」
- 「行事予定」
- 「持ち物リスト」
- 「連絡文書」
のいずれかに分類し、それぞれに応じたJSON形式に変換してください。

【手順】
1. テキストを読んでプリント種別を推定してください。
2. 推定した種別に応じて、以下のフォーマットでJSONを作成してください。
3. 分類できない場合は「プリント種別: 不明」としてください。

【出力形式例】
● 時間割表
{
  "プリント種別": "時間割表",
  "時間割": [
    {"曜日": "月曜日", "時間": "8:30", "教科": "国語"}
  ]
}
● 行事予定
{
  "プリント種別": "行事予定",
  "行事一覧": [
    {"日付": "2025-05-15", "内容": "遠足"}
  ]
}
● 持ち物リスト
{
  "プリント種別": "持ち物リスト",
  "持ち物一覧": [
    {"持ち物": "水筒", "備考": ""}
  ]
}
● 連絡文書
{
  "プリント種別": "連絡文書",
  "タイトル": "5月のお知らせ",
  "本文要約": "..."
}

【注意】
- OCR誤認識はできる範囲で推測補正してください
- 出力は必ず日本語のJSON形式のみで、説明文は不要です
"""

    user_prompt = f"以下はOCRで読み取ったプリントのテキストです。\n\n{ocr_text}\n\nこれを上記ルールに従って構造化してください。"

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.2
    )

    structured_json = response['choices'][0]['message']['content']
    return structured_json

# LINEのWebhookエンドポイント
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

# 画像受信→OCR→OpenAI→返信
@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    message_content = line_bot_api.get_message_content(event.message.id)
    image_bytes = io.BytesIO(message_content.content)

    # OCR（Vision API）
    image = vision.Image(content=image_bytes.getvalue())
    response = vision_client.text_detection(image=image)
    texts = response.text_annotations

    # OCR結果を取り出す
    if texts:
        detected_text = texts[0].description.strip()
    else:
        detected_text = "文字が検出できませんでした。"

    # OCRテキストをOpenAIに渡して、構造化JSONを取得
    try:
        structured_data = call_openai_for_printer_text(detected_text)
    except Exception as e:
        structured_data = f"OpenAI APIリクエストエラー: {str(e)}"

    # LINEに返信（今回は構造化結果をそのまま返す）
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=structured_data[:2000])  # LINE文字制限に合わせて最大2000文字
    )

# サーバー起動設定
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host="0.0.0.0", port=port)
