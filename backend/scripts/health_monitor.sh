#!/bin/bash
# Health Backend 服务监控脚本
# 检查服务状态，失败时发送告警并尝试恢复

SERVICE_NAME="health-backend"
API_URL="http://localhost:8000/"
LOG_FILE="/var/log/health_monitor.log"
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

send_telegram_alert() {
    local message="$1"
    if [ -n "$TELEGRAM_BOT_TOKEN" ] && [ -n "$TELEGRAM_CHAT_ID" ]; then
        curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -d "chat_id=${TELEGRAM_CHAT_ID}" \
            -d "text=${message}" \
            -d "parse_mode=HTML" > /dev/null 2>&1
        log "已发送 Telegram 告警"
    fi
}

# 1. 检查 systemd 服务状态
if ! systemctl is-active --quiet "$SERVICE_NAME"; then
    log "警告: $SERVICE_NAME 服务未运行"

    # 尝试启动服务
    log "尝试启动服务..."
    systemctl start "$SERVICE_NAME"
    sleep 5

    if systemctl is-active --quiet "$SERVICE_NAME"; then
        log "✓ 服务已成功启动"
        send_telegram_alert "⚠️ <b>Health Backend 服务告警</b>

服务曾停止，已自动恢复
时间: $(date '+%Y-%m-%d %H:%M:%S')"
    else
        log "错误: 服务启动失败"
        send_telegram_alert "🚨 <b>Health Backend 服务告警</b>

服务启动失败，需要人工干预！
时间: $(date '+%Y-%m-%d %H:%M:%S')

检查命令:
<code>journalctl -u health-backend -n 50</code>"
        exit 1
    fi
fi

# 2. 检查 API 健康状态
response=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "$API_URL" 2>/dev/null)

if [ "$response" != "200" ]; then
    log "警告: API 响应异常 (HTTP $response)"

    # 尝试重启服务
    log "尝试重启服务..."
    systemctl restart "$SERVICE_NAME"
    sleep 10

    response=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "$API_URL" 2>/dev/null)

    if [ "$response" == "200" ]; then
        log "✓ 服务已恢复正常"
        send_telegram_alert "⚠️ <b>Health Backend 服务告警</b>

API 曾无响应，已自动恢复
时间: $(date '+%Y-%m-%d %H:%M:%S')"
    else
        log "错误: 服务恢复失败"
        send_telegram_alert "🚨 <b>Health Backend 服务告警</b>

API 持续无响应 (HTTP $response)
时间: $(date '+%Y-%m-%d %H:%M:%S')

检查命令:
<code>tail -50 /var/log/health_backend.log</code>"
        exit 1
    fi
else
    log "✓ 服务运行正常"
fi

exit 0
