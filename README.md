# AI Necklace - Raspberry Pi 5 音声AIアシスタント

ラズベリーパイ5を使ったウェアラブル音声AIアシスタントの試作プロジェクト。

## 機能

- ボタンを押している間だけ録音（トランシーバー方式）
- OpenAI Whisper APIによる音声認識
- GPT-4o-miniによるAI応答生成
- OpenAI TTSによる音声合成
- systemdによる自動起動
- **Gmail連携**（メール確認・返信・送信）
- **アラーム機能**（時刻指定で音声通知）
- **カメラ機能**（GPT-4o Visionで画像認識）
- **写真付きメール送信**（撮影した写真をメールで送信・返信）
- **Wi-Fi自動切り替え**（家のWi-Fi ↔ iPhoneテザリング）
- **音声メッセージ機能**（スマホとラズパイ間で双方向の音声メッセージ送受信）

## ハードウェア

- Raspberry Pi 5
- USBマイク
- USBスピーカー
- プッシュボタン（GPIO5接続）
- CSIカメラ（IMX500等、オプション）

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

### 基本操作

1. ボタンを押す → 録音開始
2. 話す
3. ボタンを離す → 録音終了 → AI応答

### 外出先での使用（スマホテザリング）

スマホのテザリングを使って外でも利用できます。

**詳細な設定手順**: [TETHERING_SETUP.md](TETHERING_SETUP.md) を参照

**簡単な使い方**:
1. スマホのテザリングをON
2. ラズパイの電源をON（自動的にテザリングに接続）
3. ボタンを押して話しかける

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

# スクリプトをコピー
scp ai_necklace.py hotaka@raspberrypi.local:~/ai-necklace/
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

## アラーム機能

アラーム機能は追加設定なしで使用できます。アラームは `~/.ai-necklace/alarms.json` に保存され、再起動後も保持されます。

### アラーム音声コマンド例

- 「7時にアラームをセットして」→ アラーム設定
- 「アラームを確認して」→ アラーム一覧表示
- 「アラームを削除して」→ アラーム削除

## カメラ機能（オプション）

CSIカメラ（IMX500等）を接続すると、GPT-4o Visionによる画像認識が利用できます。

### カメラ音声コマンド例

- 「写真を撮って」→ 撮影して説明
- 「何が見える？」→ 周囲を認識して説明
- 「これは何？」→ 目の前の物体を説明
- 「目の前にあるものを教えて」→ 画像認識

### 写真付きメール送信

- 「さっきの人に写真を送って」→ 直前にやり取りしたメール相手に写真を撮影して送信
- 「このメールに写真付きで返信して」→ メールに写真を添付して返信

## Wi-Fi自動切り替え

家のWi-Fiが見つからない場合、自動的にiPhoneテザリングを探して接続します。

### 設定済みのネットワーク

| ネットワーク | 優先度 | 用途 |
|-------------|--------|------|
| preconfigured | 100 | 家のWi-Fi（優先） |
| Tethering_hotaka | 10 | iPhoneテザリング（フォールバック） |

### 動作

- 30秒ごとにWi-Fi接続状態をチェック
- 未接続の場合、利用可能なネットワークをスキャン
- 優先度の高いネットワークに自動接続

### ログ確認

```bash
cat /var/log/wifi_monitor.log
```

## 音声メッセージ機能

Firebase を使用して、スマホとラズパイ間で双方向の音声メッセージをやり取りできます。
LINEのようなチャットUIで、音声メッセージを自動的にテキストに変換して表示します。

### 仕組み

```
ラズパイ ←→ Firebase (Realtime DB + Storage) ←→ スマホ (PWA)
```

- **ラズパイ → スマホ**: OpenAI Whisper APIで音声をテキスト変換
- **スマホ → ラズパイ**: Web Speech API（ブラウザ）で音声をテキスト変換

### 機能

- LINEライクなチャットUI（トークリスト → チャット画面）
- 音声メッセージの自動テキスト変換・表示
- テキストをタップで音声再生
- 新着メッセージの通知音
- 未読バッジ表示

### セットアップ

1. **Firebase プロジェクト作成**
   - [Firebase Console](https://console.firebase.google.com/) でプロジェクト作成
   - Realtime Database を有効化
   - Cloud Storage を有効化
   - Webアプリを追加して設定情報を取得

2. **セキュリティルール設定**

   Realtime Database ルール:
   ```json
   {
     "rules": {
       "messages": {
         ".read": true,
         ".write": true,
         ".indexOn": ["timestamp"]
       }
     }
   }
   ```

   Storage ルール:
   ```
   rules_version = '2';
   service firebase.storage {
     match /b/{bucket}/o {
       match /audio/{allPaths=**} {
         allow read, write: if true;
       }
     }
   }
   ```

3. **設定ファイルの作成**

   ラズパイ用（`firebase_voice_config.py`）:
   ```python
   FIREBASE_CONFIG = {
       "apiKey": "YOUR_API_KEY",
       "authDomain": "YOUR_PROJECT_ID.firebaseapp.com",
       "databaseURL": "https://YOUR_PROJECT_ID-default-rtdb.firebasedatabase.app",
       "projectId": "YOUR_PROJECT_ID",
       "storageBucket": "YOUR_PROJECT_ID.firebasestorage.app",
   }
   ```

   スマホ用（`voice-messenger-web/firebase-config.js`）:
   ```javascript
   export default {
       apiKey: "YOUR_API_KEY",
       authDomain: "YOUR_PROJECT_ID.firebaseapp.com",
       databaseURL: "https://YOUR_PROJECT_ID-default-rtdb.firebasedatabase.app",
       projectId: "YOUR_PROJECT_ID",
       storageBucket: "YOUR_PROJECT_ID.firebasestorage.app"
   };
   ```

4. **スマホ用Webアプリのデプロイ**

   ```bash
   cd voice-messenger-web
   firebase login
   firebase deploy --only hosting
   ```

### 音声コマンド例

**ラズパイ → スマホ:**
- 「スマホにメッセージを送って」→「了解です。押しながら話してください。」→ 録音開始、ボタンを離すと送信

**スマホ → ラズパイ:**
- チャット画面で録音ボタンを押しながら話す → ラズパイで自動再生

### Webアプリ URL

デプロイ後: `https://[プロジェクトID].web.app`

## ライセンス

MIT License
