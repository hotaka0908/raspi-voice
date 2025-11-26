#!/bin/bash
# Gmail機能セットアップスクリプト

echo "=== Gmail機能セットアップ ==="

# 仮想環境をアクティベート
cd ~/ai-necklace
source venv/bin/activate

# Google API ライブラリをインストール
echo "Google API ライブラリをインストール中..."
pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client

# 認証情報ディレクトリを作成
mkdir -p ~/.ai-necklace

echo ""
echo "=== セットアップ完了 ==="
echo ""
echo "次のステップ:"
echo "1. Google Cloud Console でOAuth認証情報を作成"
echo "2. credentials.json を ~/.ai-necklace/ にコピー"
echo "3. 初回起動時にブラウザで認証（デスクトップ環境が必要）"
echo ""
echo "認証情報の配置:"
echo "  scp credentials.json hotaka@raspberrypi.local:~/.ai-necklace/"
echo ""
