#!/bin/bash
# Wi-Fi自動接続設定スクリプト
# スマホのテザリング情報を設定してラズパイが自動接続できるようにする

echo "=========================================="
echo "Wi-Fi自動接続設定"
echo "=========================================="
echo ""

# スマホのテザリング情報を入力
read -p "スマホのWi-Fi名（SSID）を入力: " SSID
read -sp "パスワードを入力: " PASSWORD
echo ""

# 優先度を設定（複数のWi-Fiがある場合に備えて）
read -p "優先度（数字が大きいほど優先、デフォルト99）: " PRIORITY
PRIORITY=${PRIORITY:-99}

echo ""
echo "設定内容:"
echo "  SSID: $SSID"
echo "  優先度: $PRIORITY"
echo ""

# NetworkManagerで接続設定
echo "Wi-Fi接続を設定中..."
sudo nmcli connection add \
    type wifi \
    con-name "Tethering_${SSID}" \
    ifname wlan0 \
    ssid "$SSID" \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.psk "$PASSWORD" \
    connection.autoconnect yes \
    connection.autoconnect-priority $PRIORITY

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ Wi-Fi設定が完了しました"
    echo ""
    echo "接続を試行中..."
    sudo nmcli connection up "Tethering_${SSID}"

    # 接続確認
    sleep 3
    if ping -c 3 8.8.8.8 > /dev/null 2>&1; then
        echo ""
        echo "✓ インターネット接続成功！"
        echo ""
        echo "現在のIPアドレス:"
        hostname -I
    else
        echo ""
        echo "⚠ 接続できませんでした。以下を確認してください:"
        echo "  1. スマホのテザリングがONになっているか"
        echo "  2. SSIDとパスワードが正しいか"
        echo "  3. ラズパイがテザリングの範囲内にあるか"
    fi
else
    echo ""
    echo "✗ 設定に失敗しました"
    exit 1
fi

echo ""
echo "=========================================="
echo "自動再接続の設定"
echo "=========================================="
echo ""
echo "Wi-Fiが切断された場合、自動的に再接続するサービスを有効にします。"
echo "詳細は wifi_monitor.sh と wifi-monitor.service を参照してください。"
echo ""
