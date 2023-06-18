import os
import openai
from flask import Flask, request, abort


from linebot import (
    LineBotApi, WebhookHandler
)
from linebot.exceptions import (
    InvalidSignatureError
)
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, TemplateSendMessage, AudioMessage, FollowEvent,
)

app = Flask(__name__)

# 環境変数取得
LINE_CHANNEL_ACCESS_TOKEN = os.environ['LINE_CHANNEL_ACCESS_TOKEN']
LINE_CHANNEL_SECRET = os.environ['LINE_CHANNEL_SECRET']
API_KEY = os.environ['API_KEY']
# api_key = config.Google_API_KEY # GoogleTTS APIキーの設定

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
openai.api_key = API_KEY
# api_key = config.Google_API_KEY # GoogleTTS APIキーの設定


@app.route("/callback", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)

    return 'OK'

# 友達に追加した場合
@handler.add(FollowEvent)
def on_follow(event):
    # メッセージの送信
    line_bot_api.reply_message(
        event.reply_token,
        messages=TextSendMessage(text='友達追加ありがとうございます。こちらは面接対策botです。面接練習と入力してください。')
    )

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    message_id = event.message.id
    text_message: TextMessage = event.message
    if event.reply_token == "00000000000000000000000000000000":
        return

    if text_message.text == "面接練習":
        template = {
            "type": "confirm",
            "text": "①面接官の性別",
            "actions": [
                {"type": "message", "label": "男性", "text": "男性"},
                {"type": "message", "label": "女性", "text": "女性"},
            ],
        }
        message = {"type": "template", "altText": "代替テキスト", "template": template}
        message_list = [
            TextSendMessage(text="ありがとうございます! 面接に必要となる情報を教えてください!①面接官の性別②あなたのプロフィール)"),
            TemplateSendMessage.new_from_json_dict(message),
        ]
        line_bot_api.reply_message(event.reply_token, message_list)

    if text_message.text in {"男性", "女性"}:
        line_bot_api.reply_message(
        event.reply_token, TextSendMessage(text="②プロフィール(例：名前:竹田花子, 性別:女性, 学年:3年生, 学部:情報学部, 志望企業:Google)の入力を行ってください。プロフィール入力後は、ボイスメッセージを使用して面接を行います。終了したい場合は、終了と入力してください。ボイスメッセージで「こんにちわ」と言ってください。")
        )
        return
    
    profiele_file_write(text_message.text)

    if text_message.text == "終了":
        line_bot_api.reply_message(
        event.reply_token, TextSendMessage(text="終了します。")
        )
        os.remove(f"user_profiele/user_profiele.text")
        os.remove(f"interview/interview_log.text")



@handler.add(MessageEvent, message= AudioMessage)
def handle_message(event):
    if event.reply_token == "00000000000000000000000000000000":
        return
    
    # 音声メッセージの場合
    message_id = event.message.id
    user_question = STT_whisper(message_id)
    interview_file_write("user:"+user_question)
    response_text = chatGPT_response(user_question)
    reply_message = TextSendMessage(text=response_text)
    interview_file_write("interviewer:"+response_text)

    # メッセージを返信する
    line_bot_api.reply_message(event.reply_token, reply_message)
    os.remove(f"{message_id}.m4a")

def chatGPT_response(text):

    print("chatGPT_response起動")
    user_character = profiele_file_read()
    interview_log = interview_file_read()
    GPT_character = '''
        あなたは新卒採用を行う面接官です。あなたは日本のIT業界に所属しています。
        性別は女性です。1回返答を受けたら、返す質問は必ず一つにしてください。
        面接の質問内容は５回程会話したら、主題を変更してください。
    '''
    User_character_prompt =f'''
    こちらが面接を受ける人の、プロフィールとなります。このプロフィールを参考に面接を行ってください。
    {user_character}
    '''
    interview_prompt=f'''
    こちらが面接の記録となります。userは面接を受けるユーザーを、interviewerはあなたを示しています。
    以下の記録を参考に面接を行ってください。記録がない場合でもかまわず、面接を行ってください。
    {interview_log}
    '''
    response = openai.ChatCompletion.create(
    model="gpt-3.5-turbo",
    messages=[
        {"role": "system", "content": GPT_character},
        {"role": "system", "content": User_character_prompt},
        {"role": "system", "content": interview_prompt},
        #{"role": "assistant", "content": text},
        {"role": "user", "content": text},
    ],
    )
    response_text = response.choices[0]["message"]["content"].strip()
    print(response_text)
    return response_text

#Whisperで音声を認識してchatGPTに流す
def STT_whisper(message_id):
    print("STT_whisper起動")
    print(message_id)
    message_content = line_bot_api.get_message_content(message_id)
    # 書き込み専用モードでファイルを開く
    with open(f"{message_id}.m4a", 'wb') as fd:
        fd.write(message_content.content)
        audio_path = fd.name
    # 読み込み専用モードでファイルを開く
    with open(f"{message_id}.m4a", "rb") as fd:
        transcript = openai.Audio.transcribe("whisper-1", fd)
        user_question = transcript["text"]
        print(user_question)

    return user_question

def profiele_file_write(file_content):
    with open(f"user_profile/user_profile.text", 'wb') as f:
        f.write(file_content.encode('utf-8'))

def profiele_file_read():
    with open(f"user_profile/user_profile.text", 'rb') as f:
        profiele = f.read()
    return profiele 

def interview_file_write(file_content):
    with open(f"interview/interview_log.text", 'wb') as f:
        f.write(file_content.encode('utf-8'))

def interview_file_read():
    with open(f"interview/interview_log.text", 'rb') as f:
        interview_log = f.read()
    return interview_log


if __name__ == "__main__":
    port = int(os.getenv("PORT"))
    app.run(host="0.0.0.0", port=port)