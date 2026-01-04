#!/bin/bash
# Health Database Backup Script
# 每日自动备份 PostgreSQL 数据库到本地，并上传到 Google Drive
#
# 使用前请设置环境变量:
#   BACKUP_DIR - 备份目录路径 (默认: ./backups)
#   LOG_DIR - 日志目录路径 (默认: ./backups)

set -e

# 配置 (可通过环境变量覆盖)
BACKUP_DIR="${BACKUP_DIR:-./backups/health_db}"
LOG_DIR="${LOG_DIR:-./backups}"
DB_NAME="health_db"
DATE=$(date +%Y-%m-%d)
TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/health_db_${DATE}.sql"
LOG_FILE="${LOG_DIR}/backup.log"
KEEP_DAYS=30  # 本地保留天数

# 确保目录存在
mkdir -p "$BACKUP_DIR"
mkdir -p "$LOG_DIR"

# 日志函数
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "========== 开始备份 =========="

# 1. 创建 PostgreSQL 备份
log "正在备份数据库 ${DB_NAME}..."
sudo -u postgres pg_dump "$DB_NAME" > "$BACKUP_FILE"

# 检查备份文件大小
BACKUP_SIZE=$(ls -lh "$BACKUP_FILE" | awk '{print $5}')
log "备份完成: ${BACKUP_FILE} (${BACKUP_SIZE})"

# 2. 压缩备份文件
log "正在压缩备份文件..."
gzip -f "$BACKUP_FILE"
COMPRESSED_FILE="${BACKUP_FILE}.gz"
COMPRESSED_SIZE=$(ls -lh "$COMPRESSED_FILE" | awk '{print $5}')
log "压缩完成: ${COMPRESSED_FILE} (${COMPRESSED_SIZE})"

# 3. 上传到 Google Drive（如果 rclone 已配置）
if command -v rclone &> /dev/null && rclone listremotes | grep -q "gdrive:"; then
    log "正在上传到 Google Drive..."
    rclone copy "$COMPRESSED_FILE" gdrive:HealthBackups/ --progress
    log "云端上传完成"
else
    log "警告: rclone 未配置，跳过云端备份"
fi

# 4. 清理旧备份（本地）
log "清理 ${KEEP_DAYS} 天前的本地备份..."
find "$BACKUP_DIR" -name "health_db_*.sql.gz" -mtime +${KEEP_DAYS} -delete
REMAINING=$(ls -1 "$BACKUP_DIR" | wc -l)
log "本地保留 ${REMAINING} 个备份文件"

log "========== 备份完成 =========="
echo ""
