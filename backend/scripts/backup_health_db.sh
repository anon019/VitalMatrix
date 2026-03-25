#!/bin/bash
# Health Database Backup Script
# 每日自动备份 PostgreSQL 数据库到本地，并上传到 Google Drive

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$BACKEND_DIR/backups}"
DB_NAME="${DB_NAME:-health_db}"
PG_DUMP_USER="${PG_DUMP_USER:-postgres}"
DATE=$(date +%Y-%m-%d)
TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/health_db_${DATE}.sql"
LOG_FILE="${LOG_FILE:-$BACKUP_DIR/backup.log}"
KEEP_DAYS="${KEEP_DAYS:-30}"

mkdir -p "$BACKUP_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "========== 开始备份 =========="

log "正在备份数据库 ${DB_NAME}..."
if command -v sudo &> /dev/null; then
    sudo -u "$PG_DUMP_USER" pg_dump "$DB_NAME" > "$BACKUP_FILE"
else
    pg_dump "$DB_NAME" > "$BACKUP_FILE"
fi

BACKUP_SIZE=$(ls -lh "$BACKUP_FILE" | awk '{print $5}')
log "备份完成: ${BACKUP_FILE} (${BACKUP_SIZE})"

log "正在压缩备份文件..."
gzip -f "$BACKUP_FILE"
COMPRESSED_FILE="${BACKUP_FILE}.gz"
COMPRESSED_SIZE=$(ls -lh "$COMPRESSED_FILE" | awk '{print $5}')
log "压缩完成: ${COMPRESSED_FILE} (${COMPRESSED_SIZE})"

if command -v rclone &> /dev/null && rclone listremotes | grep -q "gdrive:"; then
    log "正在上传到 Google Drive..."
    rclone copy "$COMPRESSED_FILE" gdrive:HealthBackups/ --progress
    log "云端上传完成"
else
    log "警告: rclone 未配置，跳过云端备份"
fi

log "清理 ${KEEP_DAYS} 天前的本地备份..."
find "$BACKUP_DIR" -name "health_db_*.sql.gz" -mtime +${KEEP_DAYS} -delete
REMAINING=$(ls -1 "$BACKUP_DIR" | wc -l)
log "本地保留 ${REMAINING} 个备份文件"

log "========== 备份完成 =========="
echo ""
