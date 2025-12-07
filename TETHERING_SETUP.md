# スマホテザリングでAI Necklaceを使う設定ガイド

このガイドでは、スマホのテザリングを使ってラズパイを外出先でも使えるようにする設定手順を説明します。

## 📋 事前準備

- Raspberry Pi 5（既にai_necklace.pyがインストール済み）
- スマホ（Wi-Fiテザリング機能付き）
- ラズパイへのSSHまたは直接アクセス

## 🚀 セットアップ手順

### 1. ファイルをラズパイに転送

ラズパイにSSH接続するか、直接操作してファイルを転送します。

```bash
# PCからラズパイにファイルを転送（PCで実行）
scp wifi_config.sh hotaka@raspberrypi.local:~/dev/raspi-voice/
scp wifi_monitor.sh hotaka@raspberrypi.local:~/dev/raspi-voice/
scp wifi-monitor.service hotaka@raspberrypi.local:~/dev/raspi-voice/
scp ai-necklace.service hotaka@raspberrypi.local:~/dev/raspi-voice/

# ラズパイにSSH接続
ssh hotaka@raspberrypi.local
```

### 2. Wi-Fi自動接続を設定

```bash
# raspi-voiceディレクトリに移動
cd ~/dev/raspi-voice

# スクリプトに実行権限を付与
chmod +x wifi_config.sh wifi_monitor.sh

# Wi-Fi設定スクリプトを実行
./wifi_config.sh
```

スクリプトが以下を質問します：
- **スマホのWi-Fi名（SSID）**: スマホのテザリング名を入力
- **パスワード**: テザリングのパスワードを入力
- **優先度**: そのまま Enter（デフォルト99）

### 3. Wi-Fi監視サービスをインストール

```bash
# サービスファイルをシステムディレクトリにコピー
sudo cp wifi-monitor.service /etc/systemd/system/

# サービスを有効化して起動
sudo systemctl daemon-reload
sudo systemctl enable wifi-monitor.service
sudo systemctl start wifi-monitor.service

# 動作確認
sudo systemctl status wifi-monitor.service
```

### 4. ai-necklaceサービスを更新

```bash
# 更新したサービスファイルをシステムディレクトリにコピー
sudo cp ai-necklace.service /etc/systemd/system/

# サービスを再起動
sudo systemctl daemon-reload
sudo systemctl restart ai-necklace.service

# 動作確認
sudo systemctl status ai-necklace.service
```

## ✅ 動作確認

### インターネット接続確認

```bash
# Google DNSにping
ping -c 3 8.8.8.8

# IPアドレス確認
hostname -I
```

### ログ確認

```bash
# Wi-Fi監視ログ
sudo journalctl -u wifi-monitor -f

# AI Necklaceログ
sudo journalctl -u ai-necklace -f

# Wi-Fi監視の詳細ログ
sudo tail -f /var/log/wifi_monitor.log
```

## 🎯 使い方（外出時）

### 起動手順

1. **スマホのテザリングをON**にする
2. **ラズパイの電源をON**にする
3. 約30-60秒待つ（自動的にテザリングに接続）
4. **ボタンを押して話しかける**

### 接続確認方法

ラズパイにLED等のインジケーターがない場合、以下の方法で確認：

```bash
# スマホのテザリング設定画面で「raspberrypi」が接続されているか確認
# または、ラズパイにモニター接続して以下を実行
iwconfig wlan0
```

## 🔧 トラブルシューティング

### Wi-Fiに接続できない

```bash
# 接続状態確認
nmcli connection show

# 手動で接続試行
sudo nmcli connection up "Tethering_<スマホのSSID>"

# NetworkManager再起動
sudo systemctl restart NetworkManager
```

### 自動再接続が動かない

```bash
# Wi-Fi監視サービスのログ確認
sudo journalctl -u wifi-monitor -n 50

# サービス再起動
sudo systemctl restart wifi-monitor.service
```

### AI Necklaceが起動しない

```bash
# エラーログ確認
sudo journalctl -u ai-necklace -n 50

# 手動で起動してエラーを確認
cd ~/ai-necklace
source venv/bin/activate
python ai_necklace.py
```

### テザリングの電波が弱い

- ラズパイをスマホに近づける
- スマホを充電しながら使用（テザリング時はバッテリー消費が多い）
- Wi-Fiドングルを追加（より強力なアンテナ付き）

## 📊 データ通信量の目安

| 操作 | 1回あたりの通信量 |
|------|------------------|
| 音声認識（Whisper API） | 1-2MB / 分 |
| AI応答生成（GPT-4o-mini） | 5-10KB / 回 |
| 音声合成（TTS） | 500KB-1MB / 回 |
| カメラ画像認識 | 200KB-1MB / 回 |
| Gmail確認 | 10-50KB / 回 |

**1時間の使用（頻繁に会話）**: 約50-100MB

## 🔋 バッテリー対策

### ラズパイ用モバイルバッテリー

- **推奨**: 65W以上のUSB-C PDバッテリー
- **容量**: 20,000mAh以上
- **稼働時間**: 約2-4時間

### スマホのバッテリー節約

- 画面の明るさを下げる
- 使わないアプリを終了
- 可能ならモバイルバッテリーで充電しながら使用

## 📱 複数のWi-Fi設定（オプション）

自宅のWi-Fiとテザリングの両方を設定しておくと便利です：

```bash
# 自宅のWi-Fiを追加（優先度を低めに設定）
sudo nmcli connection add \
    type wifi \
    con-name "Home_WiFi" \
    ifname wlan0 \
    ssid "自宅のSSID" \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.psk "自宅のパスワード" \
    connection.autoconnect yes \
    connection.autoconnect-priority 50

# 設定確認
nmcli connection show
```

**優先度の動作**:
- テザリング: 99（最優先）
- 自宅Wi-Fi: 50
→ 両方の電波があるときはテザリングに接続

## 🎓 高度な設定

### 接続チェック間隔の変更

`wifi_monitor.sh`の以下の行を編集：

```bash
CHECK_INTERVAL=30  # 30秒 → 60秒などに変更
```

### リトライ回数の変更

```bash
MAX_RETRY=3  # 3回 → 5回などに変更
```

変更後は以下を実行：

```bash
sudo systemctl restart wifi-monitor.service
```

## 📞 サポート

問題が解決しない場合は、以下の情報と共にissueを作成してください：

```bash
# システム情報を取得
uname -a
cat /etc/os-release

# サービス状態
sudo systemctl status ai-necklace
sudo systemctl status wifi-monitor

# ログ（最新50行）
sudo journalctl -u wifi-monitor -n 50
sudo journalctl -u ai-necklace -n 50
```
