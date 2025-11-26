#!/usr/bin/env python3
"""
Gmail認証トークン取得スクリプト
PCで実行してトークンを取得し、ラズパイにコピーする
"""

import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.modify'
]

# 認証情報ファイルのパス
CREDENTIALS_FILE = os.path.expanduser("~/Downloads/client_secret_695911487773-p3hal83smbubij1mjc335ncfqumo29t5.apps.googleusercontent.com.json")
TOKEN_FILE = os.path.join(os.path.dirname(__file__), "token.json")

def main():
    print("Gmail認証を開始します...")
    print(f"認証情報: {CREDENTIALS_FILE}")

    if not os.path.exists(CREDENTIALS_FILE):
        print(f"エラー: {CREDENTIALS_FILE} が見つかりません")
        return

    # 認証フロー実行
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=8080)

    # トークンを保存
    with open(TOKEN_FILE, 'w') as token:
        token.write(creds.to_json())

    print(f"\n認証成功！トークンを保存しました: {TOKEN_FILE}")
    print("\n次のコマンドでラズパイにコピーしてください:")
    print(f"  scp {TOKEN_FILE} hotaka@raspberrypi.local:~/.ai-necklace/")

if __name__ == "__main__":
    main()
