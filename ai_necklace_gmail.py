#!/usr/bin/env python3
"""
AI Necklace - Raspberry Pi 5 スタンドアロン音声AIクライアント（Gmail機能付き）

マイクから音声を録音し、OpenAI Whisper APIで文字起こし、
GPTで応答生成（Gmail操作含む）、OpenAI TTSで音声合成してスピーカーで再生する

ボタン操作: GPIO5に接続したボタンを押している間録音（トランシーバー方式）

Gmail機能:
- 「メールを確認」「メールを読んで」→ 未読メール一覧
- 「○○からのメール」→ 特定の送信者のメール
- 「メールに返信して」→ 返信作成
- 「メールを送って」→ 新規メール作成
"""

import os
import io
import wave
import tempfile
import time
import signal
import sys
import threading
import json
import base64
import re
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

import pyaudio
import numpy as np
from openai import OpenAI
from dotenv import load_dotenv

# Gmail API
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# GPIOライブラリ
try:
    from gpiozero import Button
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    print("警告: gpiozeroが使用できません。ボタン操作は無効です。")

# systemdで実行時にprint出力をリアルタイムで表示するため
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# 環境変数の読み込み
load_dotenv()

# Gmail APIスコープ
GMAIL_SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.modify'
]

# 設定
CONFIG = {
    # オーディオ設定
    "sample_rate": 44100,
    "channels": 1,
    "chunk_size": 1024,
    "max_record_seconds": 30,
    "silence_threshold": 500,

    # デバイス設定
    "input_device_index": None,
    "output_device_index": None,

    # GPIO設定
    "button_pin": 5,
    "use_button": True,

    # AI設定
    "whisper_model": "whisper-1",
    "tts_model": "tts-1",
    "tts_voice": "nova",
    "tts_speed": 1.2,
    "chat_model": "gpt-4o-mini",

    # Gmail設定
    "gmail_credentials_path": os.path.expanduser("~/.ai-necklace/credentials.json"),
    "gmail_token_path": os.path.expanduser("~/.ai-necklace/token.json"),

    # システムプロンプト
    "system_prompt": """あなたは親切なAIアシスタントです。
ユーザーの質問に簡潔に答えてください。
音声で読み上げられるため、1-2文程度の短い応答を心がけてください。
日本語で回答してください。

あなたはGmailの操作も可能です。以下のツールを使用できます:

## 利用可能なツール

1. gmail_list - メール一覧取得
   - query: 検索クエリ（例: "is:unread", "from:xxx@gmail.com"）
   - max_results: 取得件数（デフォルト5）

2. gmail_read - メール本文読み取り
   - message_id: メールID

3. gmail_send - 新規メール送信
   - to: 宛先メールアドレス
   - subject: 件名
   - body: 本文

4. gmail_reply - メール返信
   - message_id: 返信するメールのID
   - body: 返信本文

ツールを使う場合は、以下のJSON形式で応答してください:
{"tool": "ツール名", "params": {パラメータ}}

ツールを使わない通常の応答の場合は、普通にテキストで回答してください。

ユーザーが「メールを確認」「メールを読んで」と言ったら、gmail_listで未読メールを確認してください。
ユーザーが特定のメールの詳細を聞いたら、gmail_readで本文を取得してください。
ユーザーが「メールを送って」と言ったら、宛先・件名・本文を確認してgmail_sendを使ってください。
""",
}

# グローバル変数
running = True
client = None
audio = None
button = None
is_recording = False
record_lock = threading.Lock()
gmail_service = None
conversation_history = []
last_email_list = []  # 直近のメール一覧を保持


def signal_handler(sig, frame):
    """Ctrl+C で終了"""
    global running
    print("\n終了します...")
    running = False


def init_gmail():
    """Gmail API初期化"""
    global gmail_service

    creds = None
    token_path = CONFIG["gmail_token_path"]
    credentials_path = CONFIG["gmail_credentials_path"]

    # トークンファイルが存在する場合は読み込み
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, GMAIL_SCOPES)

    # トークンが無効または存在しない場合は認証フロー
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_path):
                print(f"警告: Gmail認証情報が見つかりません: {credentials_path}")
                print("Gmail機能は無効です。")
                return False

            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_path, GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)

        # トークンを保存
        os.makedirs(os.path.dirname(token_path), exist_ok=True)
        with open(token_path, 'w') as token:
            token.write(creds.to_json())

    try:
        gmail_service = build('gmail', 'v1', credentials=creds)
        print("Gmail API初期化完了")
        return True
    except Exception as e:
        print(f"Gmail API初期化エラー: {e}")
        return False


def gmail_list(query="is:unread", max_results=5):
    """メール一覧を取得"""
    global gmail_service, last_email_list

    if not gmail_service:
        return "Gmail機能が初期化されていません"

    try:
        results = gmail_service.users().messages().list(
            userId='me',
            q=query,
            maxResults=max_results
        ).execute()

        messages = results.get('messages', [])

        if not messages:
            return "該当するメールはありません"

        email_list = []
        last_email_list = []

        for i, msg in enumerate(messages, 1):
            msg_detail = gmail_service.users().messages().get(
                userId='me',
                id=msg['id'],
                format='metadata',
                metadataHeaders=['From', 'Subject', 'Date']
            ).execute()

            headers = {h['name']: h['value'] for h in msg_detail.get('payload', {}).get('headers', [])}

            # 送信者名を抽出
            from_header = headers.get('From', '不明')
            from_match = re.match(r'(.+?)\s*<', from_header)
            from_name = from_match.group(1).strip() if from_match else from_header.split('@')[0]

            email_info = {
                'id': msg['id'],
                'from': from_name,
                'from_email': from_header,  # 返信用に完全なメールアドレスを保持
                'subject': headers.get('Subject', '(件名なし)'),
                'date': headers.get('Date', ''),
            }
            last_email_list.append(email_info)
            print(f"メール保存: ID={msg['id']}, From={from_header}")  # デバッグログ
            email_list.append(f"{i}. {from_name}さんから: {email_info['subject']}")

        return "メール一覧:\n" + "\n".join(email_list)

    except HttpError as e:
        return f"メール取得エラー: {e}"


def gmail_read(message_id):
    """メール本文を読み取り"""
    global gmail_service

    if not gmail_service:
        return "Gmail機能が初期化されていません"

    try:
        msg = gmail_service.users().messages().get(
            userId='me',
            id=message_id,
            format='full'
        ).execute()

        headers = {h['name']: h['value'] for h in msg.get('payload', {}).get('headers', [])}

        # 本文を取得
        body = ""
        payload = msg.get('payload', {})

        if 'body' in payload and payload['body'].get('data'):
            body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
        elif 'parts' in payload:
            for part in payload['parts']:
                if part.get('mimeType') == 'text/plain' and part.get('body', {}).get('data'):
                    body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                    break

        # 長すぎる場合は切り詰め
        if len(body) > 500:
            body = body[:500] + "...(以下省略)"

        from_header = headers.get('From', '不明')
        from_match = re.match(r'(.+?)\s*<', from_header)
        from_name = from_match.group(1).strip() if from_match else from_header

        return f"送信者: {from_name}\n件名: {headers.get('Subject', '(件名なし)')}\n\n本文:\n{body}"

    except HttpError as e:
        return f"メール読み取りエラー: {e}"


def gmail_send(to, subject, body):
    """新規メール送信"""
    global gmail_service

    if not gmail_service:
        return "Gmail機能が初期化されていません"

    try:
        message = MIMEText(body)
        message['to'] = to
        message['subject'] = subject

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

        gmail_service.users().messages().send(
            userId='me',
            body={'raw': raw}
        ).execute()

        return f"{to}にメールを送信しました"

    except HttpError as e:
        return f"メール送信エラー: {e}"


def extract_email_address(email_str):
    """メールアドレス部分を抽出（例: '"名前" <test@example.com>' → 'test@example.com'）"""
    if not email_str:
        return None
    # <email@example.com> 形式からメールアドレスを抽出
    match = re.search(r'<([^>]+)>', email_str)
    if match:
        return match.group(1)
    # @が含まれていればそのまま使用
    if '@' in email_str:
        return email_str.strip()
    return None


def gmail_reply(message_id, body, to_email=None):
    """メール返信"""
    global gmail_service

    if not gmail_service:
        return "Gmail機能が初期化されていません"

    try:
        # 元のメールを取得
        original = gmail_service.users().messages().get(
            userId='me',
            id=message_id,
            format='metadata',
            metadataHeaders=['From', 'Subject', 'Message-ID', 'References', 'Reply-To']
        ).execute()

        headers = {h['name']: h['value'] for h in original.get('payload', {}).get('headers', [])}

        # 返信先（Reply-Toがあればそれを使う、なければFrom）
        to_raw = to_email or headers.get('Reply-To') or headers.get('From', '')
        to = extract_email_address(to_raw)

        if not to:
            return "返信先のメールアドレスが取得できませんでした"

        subject = headers.get('Subject', '')
        if not subject.startswith('Re:'):
            subject = 'Re: ' + subject

        # スレッド情報
        thread_id = original.get('threadId')
        message_id_header = headers.get('Message-ID', '')
        references = headers.get('References', '')

        message = MIMEText(body)
        message['to'] = to
        message['subject'] = subject
        if message_id_header:
            message['In-Reply-To'] = message_id_header
            message['References'] = f"{references} {message_id_header}".strip()

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

        gmail_service.users().messages().send(
            userId='me',
            body={'raw': raw, 'threadId': thread_id}
        ).execute()

        # 送信先の名前を抽出
        to_match = re.match(r'(.+?)\s*<', to)
        to_name = to_match.group(1).strip() if to_match else to.split('@')[0]

        return f"{to_name}さんに返信を送信しました"

    except HttpError as e:
        return f"返信エラー: {e}"


def execute_tool(tool_call):
    """ツール呼び出しを実行"""
    global last_email_list

    tool_name = tool_call.get('tool')
    params = tool_call.get('params', {})

    if tool_name == 'gmail_list':
        return gmail_list(
            query=params.get('query', 'is:unread'),
            max_results=params.get('max_results', 5)
        )
    elif tool_name == 'gmail_read':
        # 番号で指定された場合
        msg_id = params.get('message_id')
        if isinstance(msg_id, int) or (isinstance(msg_id, str) and msg_id.isdigit()):
            idx = int(msg_id) - 1
            if 0 <= idx < len(last_email_list):
                msg_id = last_email_list[idx]['id']
            else:
                return "指定されたメールが見つかりません"
        return gmail_read(msg_id)
    elif tool_name == 'gmail_send':
        return gmail_send(
            to=params.get('to'),
            subject=params.get('subject'),
            body=params.get('body')
        )
    elif tool_name == 'gmail_reply':
        msg_id = params.get('message_id')
        to_email = None
        if isinstance(msg_id, int) or (isinstance(msg_id, str) and msg_id.isdigit()):
            idx = int(msg_id) - 1
            print(f"返信処理: idx={idx}, last_email_list長さ={len(last_email_list)}")  # デバッグログ
            if 0 <= idx < len(last_email_list):
                msg_id = last_email_list[idx]['id']
                to_email = last_email_list[idx].get('from_email')
                print(f"返信先: msg_id={msg_id}, to_email={to_email}")  # デバッグログ
            else:
                return "指定されたメールが見つかりません。先に「メールを確認して」と言ってください。"
        return gmail_reply(msg_id, params.get('body'), to_email)
    else:
        return f"不明なツール: {tool_name}"


def find_audio_device(p, device_type="input"):
    """オーディオデバイスを自動検出"""
    target_names = ["USB PnP Sound", "USB Audio", "USB PnP Audio"]

    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        name = info.get("name", "")

        if device_type == "input" and info.get("maxInputChannels", 0) > 0:
            for target in target_names:
                if target in name:
                    print(f"入力デバイス検出: [{i}] {name}")
                    return i
        elif device_type == "output" and info.get("maxOutputChannels", 0) > 0:
            for target in target_names:
                if target in name:
                    print(f"出力デバイス検出: [{i}] {name}")
                    return i

    if device_type == "input":
        return p.get_default_input_device_info()["index"]
    else:
        return p.get_default_output_device_info()["index"]


def record_audio_while_pressed():
    """ボタンを押している間録音（トランシーバー方式）"""
    global audio, button, is_recording

    input_device = CONFIG["input_device_index"]
    if input_device is None:
        input_device = find_audio_device(audio, "input")

    print("録音中... (ボタンを離すと停止)")

    stream = audio.open(
        format=pyaudio.paInt16,
        channels=CONFIG["channels"],
        rate=CONFIG["sample_rate"],
        input=True,
        input_device_index=input_device,
        frames_per_buffer=CONFIG["chunk_size"]
    )

    frames = []
    max_chunks = int(CONFIG["sample_rate"] / CONFIG["chunk_size"] * CONFIG["max_record_seconds"])

    with record_lock:
        is_recording = True

    for i in range(max_chunks):
        if not running:
            break

        if button and not button.is_pressed:
            print("ボタンが離されました、録音終了")
            break

        data = stream.read(CONFIG["chunk_size"], exception_on_overflow=False)
        frames.append(data)

    with record_lock:
        is_recording = False

    stream.stop_stream()
    stream.close()

    if len(frames) < 5:
        print("録音が短すぎます")
        return None

    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wf:
        wf.setnchannels(CONFIG["channels"])
        wf.setsampwidth(audio.get_sample_size(pyaudio.paInt16))
        wf.setframerate(CONFIG["sample_rate"])
        wf.writeframes(b''.join(frames))

    wav_buffer.seek(0)
    return wav_buffer


def record_audio_auto():
    """自動録音（ボタンなしモード、無音検出で停止）"""
    global audio

    input_device = CONFIG["input_device_index"]
    if input_device is None:
        input_device = find_audio_device(audio, "input")

    print("録音開始... 話しかけてください")

    stream = audio.open(
        format=pyaudio.paInt16,
        channels=CONFIG["channels"],
        rate=CONFIG["sample_rate"],
        input=True,
        input_device_index=input_device,
        frames_per_buffer=CONFIG["chunk_size"]
    )

    frames = []
    silent_chunks = 0
    has_sound = False
    max_chunks = int(CONFIG["sample_rate"] / CONFIG["chunk_size"] * 5)
    silence_duration = 1.5
    silence_chunks_threshold = int(CONFIG["sample_rate"] / CONFIG["chunk_size"] * silence_duration)

    for i in range(max_chunks):
        if not running:
            break

        data = stream.read(CONFIG["chunk_size"], exception_on_overflow=False)
        frames.append(data)

        audio_data = np.frombuffer(data, dtype=np.int16)
        volume = np.abs(audio_data).mean()

        if volume > CONFIG["silence_threshold"]:
            has_sound = True
            silent_chunks = 0
        else:
            silent_chunks += 1

        if has_sound and silent_chunks > silence_chunks_threshold:
            print("無音検出、録音終了")
            break

    stream.stop_stream()
    stream.close()

    if not has_sound:
        print("音声が検出されませんでした")
        return None

    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wf:
        wf.setnchannels(CONFIG["channels"])
        wf.setsampwidth(audio.get_sample_size(pyaudio.paInt16))
        wf.setframerate(CONFIG["sample_rate"])
        wf.writeframes(b''.join(frames))

    wav_buffer.seek(0)
    return wav_buffer


def transcribe_audio(audio_data):
    """音声をテキストに変換（Whisper API）"""
    global client

    print("音声認識中...")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(audio_data.read())
        temp_path = f.name

    try:
        with open(temp_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model=CONFIG["whisper_model"],
                file=audio_file,
                language="ja"
            )
        return transcript.text
    finally:
        os.unlink(temp_path)


def get_ai_response(text):
    """AIからの応答を取得（ツール呼び出し対応）"""
    global client, conversation_history

    print(f"AI処理中... (入力: {text})")

    # 会話履歴に追加
    conversation_history.append({"role": "user", "content": text})

    # 履歴が長くなりすぎたら古いものを削除
    if len(conversation_history) > 10:
        conversation_history = conversation_history[-10:]

    messages = [
        {"role": "system", "content": CONFIG["system_prompt"]}
    ] + conversation_history

    response = client.chat.completions.create(
        model=CONFIG["chat_model"],
        messages=messages,
        max_tokens=500
    )

    ai_response = response.choices[0].message.content

    # ツール呼び出しかチェック（応答内にJSONが含まれているか）
    try:
        # JSON形式のツール呼び出しを検出（応答の中からJSONを抽出）
        # {"tool": "...", "params": {...}} 形式を探す
        json_match = re.search(r'\{"tool":\s*"[^"]+",\s*"params":\s*\{[^}]*\}\}', ai_response)
        if not json_match:
            # シンプルな形式も試す
            json_match = re.search(r'\{[^{}]*"tool"[^{}]*\}', ai_response)
        if json_match:
            json_str = json_match.group()
            tool_call = json.loads(json_str)
            print(f"ツール呼び出し: {tool_call}")

            # ツール実行
            tool_result = execute_tool(tool_call)
            print(f"ツール結果: {tool_result}")

            # ツール結果を含めて再度AIに問い合わせ
            conversation_history.append({"role": "assistant", "content": ai_response})
            conversation_history.append({"role": "user", "content": f"ツール実行結果:\n{tool_result}\n\nこの結果を音声で読み上げるために、簡潔に日本語で要約してください。"})

            messages = [
                {"role": "system", "content": CONFIG["system_prompt"]}
            ] + conversation_history

            summary_response = client.chat.completions.create(
                model=CONFIG["chat_model"],
                messages=messages,
                max_tokens=300
            )

            final_response = summary_response.choices[0].message.content
            conversation_history.append({"role": "assistant", "content": final_response})
            return final_response

    except json.JSONDecodeError:
        pass  # JSONでない場合は通常の応答として処理

    conversation_history.append({"role": "assistant", "content": ai_response})
    return ai_response


def text_to_speech(text):
    """テキストを音声に変換（TTS API）"""
    global client

    print(f"音声合成中... (テキスト: {text[:30]}...)")

    response = client.audio.speech.create(
        model=CONFIG["tts_model"],
        voice=CONFIG["tts_voice"],
        input=text,
        speed=CONFIG["tts_speed"],
        response_format="wav"
    )

    return response.content


def play_audio(audio_data):
    """音声を再生"""
    global audio

    output_device = CONFIG["output_device_index"]
    if output_device is None:
        output_device = find_audio_device(audio, "output")

    print("再生中...")

    wav_buffer = io.BytesIO(audio_data)
    with wave.open(wav_buffer, 'rb') as wf:
        stream = audio.open(
            format=audio.get_format_from_width(wf.getsampwidth()),
            channels=wf.getnchannels(),
            rate=wf.getframerate(),
            output=True,
            output_device_index=output_device
        )

        chunk_size = 1024
        data = wf.readframes(chunk_size)

        while data and running:
            stream.write(data)
            data = wf.readframes(chunk_size)

        stream.stop_stream()
        stream.close()


def process_voice():
    """音声処理のメインフロー"""
    global button

    if CONFIG["use_button"] and button:
        audio_data = record_audio_while_pressed()
    else:
        audio_data = record_audio_auto()

    if audio_data is None:
        return

    text = transcribe_audio(audio_data)
    if not text or text.strip() == "":
        print("テキストが認識できませんでした")
        return

    print(f"\n[あなた] {text}")

    response = get_ai_response(text)
    print(f"[AI] {response}")

    speech_audio = text_to_speech(response)
    play_audio(speech_audio)


def main():
    """メインループ"""
    global running, client, audio, button

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("エラー: OPENAI_API_KEY が設定されていません")
        print(".env ファイルに OPENAI_API_KEY=sk-... を設定してください")
        sys.exit(1)

    client = OpenAI(api_key=api_key)
    audio = pyaudio.PyAudio()

    # Gmail初期化
    gmail_available = init_gmail()

    # ボタン初期化
    if CONFIG["use_button"] and GPIO_AVAILABLE:
        try:
            button = Button(CONFIG["button_pin"], pull_up=True, bounce_time=0.1)
            print(f"ボタン初期化完了: GPIO{CONFIG['button_pin']}")
        except Exception as e:
            print(f"ボタン初期化エラー: {e}")
            print("ボタンなしモードで動作します")
            button = None
            CONFIG["use_button"] = False
    else:
        button = None
        if CONFIG["use_button"]:
            print("GPIOが使用できないため、ボタンなしモードで動作します")
            CONFIG["use_button"] = False

    print("=" * 50)
    print("AI Necklace 起動 (Gmail機能付き)")
    print("=" * 50)
    print(f"Chat Model: {CONFIG['chat_model']}")
    print(f"TTS Voice: {CONFIG['tts_voice']}")
    print(f"Gmail: {'有効' if gmail_available else '無効'}")
    if CONFIG["use_button"]:
        print(f"操作方法: GPIO{CONFIG['button_pin']}のボタンを押している間録音")
    else:
        print("操作方法: 自動録音（無音検出で停止）")
    print("Ctrl+C で終了")
    print("=" * 50)

    if gmail_available:
        print("\nGmailコマンド例:")
        print("  - 「メールを確認して」")
        print("  - 「未読メールを読んで」")
        print("  - 「1番目のメールを読んで」")
        print("  - 「○○にメールを送って」")
        print("=" * 50)

    try:
        if CONFIG["use_button"] and button:
            print("\n--- ボタンを押して話しかけてください ---")
            while running:
                if button.is_pressed:
                    process_voice()
                    if running:
                        print("\n--- ボタンを押して話しかけてください ---")
                time.sleep(0.05)
        else:
            while running:
                print("\n--- 待機中 (話しかけてください) ---")
                process_voice()

    except Exception as e:
        print(f"エラー: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if audio:
            audio.terminate()
        print("終了しました")


if __name__ == "__main__":
    main()
