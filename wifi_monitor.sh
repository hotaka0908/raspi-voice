#!/bin/bash
# Wi-Fi接続監視・自動再接続スクリプト
# 接続が切れた場合に自動的に再接続を試みる

LOG_FILE="/var/log/wifi_monitor.log"
CHECK_INTERVAL=30  # チェック間隔（秒）
MAX_RETRY=3        # 最大リトライ回数

# ログ出力関数
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# インターネット接続チェック
check_internet() {
    # Google DNSとCloudflare DNSの両方を試す
    if ping -c 2 -W 3 8.8.8.8 > /dev/null 2>&1 || \
       ping -c 2 -W 3 1.1.1.1 > /dev/null 2>&1; then
        return 0  # 接続OK
    else
        return 1  # 接続NG
    fi
}

# Wi-Fi再接続
reconnect_wifi() {
    local retry_count=0

    log "インターネット接続が切断されました。再接続を試みます..."

    # NetworkManagerを再起動
    log "NetworkManagerを再起動中..."
    sudo systemctl restart NetworkManager
    sleep 5

    while [ $retry_count -lt $MAX_RETRY ]; do
        retry_count=$((retry_count + 1))
        log "再接続試行 ${retry_count}/${MAX_RETRY}..."

        # すべてのWi-Fi接続を試す
        for conn in $(nmcli -t -f NAME connection show | grep -i "tethering\|wifi"); do
            log "接続を試行: $conn"
            sudo nmcli connection up "$conn" > /dev/null 2>&1
            sleep 5

            if check_internet; then
                log "✓ 再接続成功: $conn"
                return 0
            fi
        done

        log "再接続失敗。${CHECK_INTERVAL}秒後に再試行します..."
        sleep $CHECK_INTERVAL
    done

    log "✗ ${MAX_RETRY}回の試行後も再接続できませんでした"
    return 1
}

# メインループ
log "Wi-Fi監視サービスを開始しました"
log "チェック間隔: ${CHECK_INTERVAL}秒"

while true; do
    if ! check_internet; then
        reconnect_wifi

        # 再接続後もダメな場合は、ai-necklaceサービスを再起動
        if ! check_internet; then
            log "ai-necklaceサービスを再起動します..."
            sudo systemctl restart ai-necklace
        fi
    fi

    sleep $CHECK_INTERVAL
done
