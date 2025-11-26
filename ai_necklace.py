#!/usr/bin/env python3
"""
AI Necklace - Raspberry Pi 5 スタンドアロン音声AIクライアント

マイクから音声を録音し、OpenAI Whisper APIで文字起こし、
Claude/GPTで応答生成、OpenAI TTSで音声合成してスピーカーで再生する

ボタン操作: GPIO17に接続したボタンを押している間録音（トランシーバー方式）
"""

import os
import io
import wave
import tempfile
import time
import signal
import sys
import threading
from pathlib import Path

import pyaudio
import numpy as np
from openai import OpenAI
from dotenv import load_dotenv

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

# 設定
CONFIG = {
    # オーディオ設定
    "sample_rate": 44100,  # USBマイクがサポートするレート (44100 or 48000)
    "channels": 1,
    "chunk_size": 1024,
    "max_record_seconds": 30,  # 最大録音時間（ボタン押しっぱなし対策）
    "silence_threshold": 500,  # 無音判定閾値

    # デバイス設定（arecord -l, aplay -l で確認した値）
    "input_device_index": None,  # Noneで自動検出
    "output_device_index": None,  # Noneで自動検出

    # GPIO設定
    "button_pin": 5,  # GPIO5 (物理ピン29)
    "use_button": True,  # ボタン操作を使用するか

    # AI設定
    "whisper_model": "whisper-1",
    "tts_model": "tts-1",
    "tts_voice": "nova",  # alloy, echo, fable, onyx, nova, shimmer
    "tts_speed": 1.2,
    "chat_model": "gpt-4o-mini",  # gpt-4o, gpt-4o-mini, gpt-3.5-turbo

    # システムプロンプト
    "system_prompt": """あなたは親切なAIアシスタントです。
ユーザーの質問に簡潔に答えてください。
音声で読み上げられるため、1-2文程度の短い応答を心がけてください。
日本語で回答してください。""",
}

# グローバル変数
running = True
client = None
audio = None
button = None
is_recording = False
record_lock = threading.Lock()


def signal_handler(sig, frame):
    """Ctrl+C で終了"""
    global running
    print("\n終了します...")
    running = False


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

    # 見つからない場合はデフォルト
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

        # ボタンが離されたら終了
        if button and not button.is_pressed:
            print("ボタンが離されました、録音終了")
            break

        data = stream.read(CONFIG["chunk_size"], exception_on_overflow=False)
        frames.append(data)

    with record_lock:
        is_recording = False

    stream.stop_stream()
    stream.close()

    if len(frames) < 5:  # 短すぎる録音は無視
        print("録音が短すぎます")
        return None

    # WAVデータに変換
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
    max_chunks = int(CONFIG["sample_rate"] / CONFIG["chunk_size"] * 5)  # 5秒
    silence_duration = 1.5
    silence_chunks_threshold = int(CONFIG["sample_rate"] / CONFIG["chunk_size"] * silence_duration)

    for i in range(max_chunks):
        if not running:
            break

        data = stream.read(CONFIG["chunk_size"], exception_on_overflow=False)
        frames.append(data)

        # 音量チェック
        audio_data = np.frombuffer(data, dtype=np.int16)
        volume = np.abs(audio_data).mean()

        if volume > CONFIG["silence_threshold"]:
            has_sound = True
            silent_chunks = 0
        else:
            silent_chunks += 1

        # 音声検出後、無音が続いたら終了
        if has_sound and silent_chunks > silence_chunks_threshold:
            print("無音検出、録音終了")
            break

    stream.stop_stream()
    stream.close()

    if not has_sound:
        print("音声が検出されませんでした")
        return None

    # WAVデータに変換
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

    # 一時ファイルに保存
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
    """AIからの応答を取得"""
    global client

    print(f"AI処理中... (入力: {text})")

    response = client.chat.completions.create(
        model=CONFIG["chat_model"],
        messages=[
            {"role": "system", "content": CONFIG["system_prompt"]},
            {"role": "user", "content": text}
        ],
        max_tokens=200
    )

    return response.choices[0].message.content


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

    # WAVデータを読み込み
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

    # 録音（ボタンモードまたは自動モード）
    if CONFIG["use_button"] and button:
        audio_data = record_audio_while_pressed()
    else:
        audio_data = record_audio_auto()

    if audio_data is None:
        return

    # 音声認識
    text = transcribe_audio(audio_data)
    if not text or text.strip() == "":
        print("テキストが認識できませんでした")
        return

    print(f"\n[あなた] {text}")

    # AI応答生成
    response = get_ai_response(text)
    print(f"[AI] {response}")

    # 音声合成
    speech_audio = text_to_speech(response)

    # 再生
    play_audio(speech_audio)


def main():
    """メインループ"""
    global running, client, audio, button

    # シグナルハンドラ設定
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # APIキー確認
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("エラー: OPENAI_API_KEY が設定されていません")
        print(".env ファイルに OPENAI_API_KEY=sk-... を設定してください")
        sys.exit(1)

    # OpenAIクライアント初期化
    client = OpenAI(api_key=api_key)

    # PyAudio初期化
    audio = pyaudio.PyAudio()

    # ボタン初期化
    if CONFIG["use_button"] and GPIO_AVAILABLE:
        try:
            # pull_up=True: 通常HIGH、押すとLOW（アクティブLOW）
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
    print("AI Necklace 起動")
    print("=" * 50)
    print(f"Chat Model: {CONFIG['chat_model']}")
    print(f"TTS Voice: {CONFIG['tts_voice']}")
    if CONFIG["use_button"]:
        print(f"操作方法: GPIO{CONFIG['button_pin']}のボタンを押している間録音")
    else:
        print("操作方法: 自動録音（無音検出で停止）")
    print("Ctrl+C で終了")
    print("=" * 50)

    try:
        if CONFIG["use_button"] and button:
            # ボタンモード: ボタンが押されたら録音開始
            print("\n--- ボタンを押して話しかけてください ---")
            while running:
                if button.is_pressed:
                    process_voice()
                    if running:
                        print("\n--- ボタンを押して話しかけてください ---")
                time.sleep(0.05)  # CPU負荷軽減
        else:
            # 自動モード: 常時録音待機
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
