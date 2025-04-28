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

# 🔥base64からVision認証キーを復元
encoded_key = os.getenv('GOOGLE_CREDENTIALS_BASE64')
if encoded_key:
    decoded_key = base64.b64decode(encoded_key)
    with open('service_account.json', 'wb') as f:
        f.write(decoded_key)
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'service_account.json'

# Vision APIクライアント
vision_client = vision.ImageAnnotatorClient()

# OpenAI呼び出し関数（持ち物リスト柔軟対応版）
def call_openai_for_printer_text(ocr_text):
    system_prompt = """
あなたは、学校から配布された各種プリント（時間割表、行事予定表、持ち物リスト、連絡事項）をOCR結果から解析し、正確に分類・整理する専門家です。

【目的】
OCRから得られたテキストを読み取り、
- 「時間割表」
- 「行事予定」
- 「持ち物リスト」
- 「連絡文書」
のいずれかに分類し、それぞれに応じたJSON形式に変換してください。

【特に重要な整理ルール】
- 「時間割表」と「持ち物リスト」が混ざっていても、正しく分離してください。
- 「時間割表」は、曜日・時間・教科の3情報を含むものを収集してください。
- 「持ち物リスト」は、曜日別に必要な持ち物が記載されている場合、曜日ごとに整理してください。
- 曜日情報がない場合は「共通」として扱い、"共通"キーにまとめてください。

【出力形式例】
{
  "プリント種別": "時間割表",
  "時間割": [
    {"曜日": "月曜日", "時間": "8:30", "教科": "国語"},
    {"曜日": "月曜日", "時間": "8:50", "教科": "国語"}
  ],
  "持ち物リスト": {
    "月曜日": ["たいそうふく", "うわぐつ", "エプロン"],
    "共通": ["ふでばこ", "れんらくぶくろ", "給食セット", "ハンカチ", "ティッシュ", "水筒"]
  }
}

【注意点】
- 出力は必ず日本語のJSON形式のみとし、追加説明や文章は不要です。
- OCR誤認識があっても可能な限り推測補正してください。
- JSONのキー名・構造は必ず上記例に厳密に従ってください。
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
