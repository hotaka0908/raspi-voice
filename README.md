# AI Necklace - Raspberry Pi 5 音声AIアシスタント

ラズベリーパイ5を使ったウェアラブル音声AIアシスタントの試作プロジェクト。

## 機能

- ボタンを押している間だけ録音（トランシーバー方式）
- OpenAI Whisper APIによる音声認識
- GPT-4o-miniによるAI応答生成
- OpenAI TTSによる音声合成
- systemdによる自動起動
- **Gmail連携**（メール確認・返信・送信）

## ハードウェア

- Raspberry Pi 5
- USBマイク
- USBスピーカー
- プッシュボタン（GPIO5接続）

## 配線

```
ボタンモジュール    ラズパイ5
     S  ─────────  物理ピン29 (GPIO5)
     V  ─────────  物理ピン1  (3.3V)
     G  ─────────  物理ピン6  (GND)
```

## セットアップ

### 1. 依存関係のインストール

```bash
sudo apt-get install -y portaudio19-dev python3-pyaudio python3-lgpio python3-gpiozero

cd ~
mkdir ai-necklace && cd ai-necklace
python3 -m venv --system-site-packages venv
source venv/bin/activate
pip install openai python-dotenv
```

### 2. ファイルの配置

```bash
# ai_necklace.py を ~/ai-necklace/ にコピー
```

### 3. 環境変数の設定

```bash
echo "OPENAI_API_KEY=sk-your-api-key" > ~/.ai-necklace/.env
```

### 4. サービスの設定（自動起動）

```bash
sudo cp ai-necklace.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ai-necklace
sudo systemctl start ai-necklace
```

## 使い方

1. ボタンを押す → 録音開始
2. 話す
3. ボタンを離す → 録音終了 → AI応答

## コマンド

```bash
# ステータス確認
sudo systemctl status ai-necklace

# ログ確認
sudo journalctl -u ai-necklace -f

# 再起動
sudo systemctl restart ai-necklace

# 停止
sudo systemctl stop ai-necklace
```

## 音量調整

```bash
# スピーカー音量
amixer -c 3 set PCM 100%

# マイク音量
amixer -c 2 set Mic 100%
```

## 設定

`ai_necklace.py` の `CONFIG` で変更可能：

| 設定項目 | 説明 | デフォルト |
|---------|------|-----------|
| button_pin | ボタンのGPIOピン | 5 |
| use_button | ボタン操作を使用 | True |
| chat_model | 使用するAIモデル | gpt-4o-mini |
| tts_voice | TTSの声 | nova |
| tts_speed | 読み上げ速度 | 1.2 |

## Gmail機能の設定（オプション）

Gmail機能を使用する場合は追加設定が必要です。

### 1. Google Cloud Console での設定

1. [Google Cloud Console](https://console.cloud.google.com/) にアクセス
2. 新しいプロジェクトを作成
3. **APIとサービス** → **ライブラリ** → 「Gmail API」を検索して有効化
4. **APIとサービス** → **OAuth同意画面** を設定
   - ユーザータイプ: 外部
   - テストユーザーに自分のGmailアドレスを追加
5. **APIとサービス** → **認証情報** → **認証情報を作成** → **OAuthクライアントID**
   - アプリケーションの種類: デスクトップアプリ
6. JSONファイルをダウンロード → `credentials.json` として保存

### 2. ラズパイへの設定

```bash
# Google APIライブラリをインストール
source ~/ai-necklace/venv/bin/activate
pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client

# 認証情報ディレクトリを作成
mkdir -p ~/.ai-necklace

# credentials.json をコピー（PCから）
scp credentials.json hotaka@raspberrypi.local:~/.ai-necklace/

# Gmail版スクリプトを使用
cp ai_necklace_gmail.py ~/ai-necklace/ai_necklace.py
```

### 3. 初回認証（デスクトップ環境が必要）

初回起動時はブラウザ認証が必要です。VNC接続またはモニター接続で実行：

```bash
cd ~/ai-necklace
source venv/bin/activate
python ai_necklace.py
```

ブラウザが開いたらGoogleアカウントで認証。トークンが `~/.ai-necklace/token.json` に保存されます。

### Gmail音声コマンド例

- 「メールを確認して」→ 未読メール一覧
- 「1番目のメールを読んで」→ メール本文を読み上げ
- 「○○からのメールを確認」→ 特定の送信者のメール
- 「○○にメールを送って」→ 新規メール作成
- 「このメールに返信して」→ 返信作成

## ライセンス

MIT License
