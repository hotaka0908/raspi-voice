#!/bin/bash
# MacBook → ラズパイ 自動同期スクリプト

export PATH="/opt/homebrew/bin:$PATH"

LOCAL_DIR="/Users/funahashihotaka/dev/raspi-voice"
REMOTE_USER="hotaka"
REMOTE_HOST="raspberrypi.local"
REMOTE_DIR="/home/hotaka/ai-necklace"

echo "ラズパイへの自動同期を開始します..."
echo "監視対象: $LOCAL_DIR"
echo "同期先: $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR"
echo "停止するには Ctrl+C を押してください"
echo ""

# ファイル変更を監視して同期
fswatch -o "$LOCAL_DIR" --exclude '\.git' --exclude '__pycache__' --exclude '\.pyc$' --exclude 'venv' | while read; do
    echo "$(date '+%Y-%m-%d %H:%M:%S') 変更検出 - 同期中..."
    rsync -avz --exclude '.git' --exclude '__pycache__' --exclude '*.pyc' --exclude 'venv' \
        "$LOCAL_DIR/" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/"

    # サービス再起動（オプション）
    ssh "$REMOTE_USER@$REMOTE_HOST" "sudo systemctl restart ai-necklace" 2>/dev/null
    echo "$(date '+%Y-%m-%d %H:%M:%S') 同期完了 & サービス再起動"
    echo ""
done
