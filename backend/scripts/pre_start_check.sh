#!/bin/bash
# Health Backend 启动前检查脚本
# 确保所有必要的依赖和配置都就绪

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="${LOG_DIR:-$BACKEND_DIR/logs}"
LOG_FILE="${LOG_FILE:-$LOG_DIR/health_backend_precheck.log}"
ENV_FILE="${ENV_FILE:-$BACKEND_DIR/.env}"
VENV_PYTHON="${VENV_PYTHON:-$BACKEND_DIR/venv/bin/python}"

mkdir -p "$LOG_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "========== 启动前检查开始 =========="

# 1. 检查 .env 文件存在
if [ ! -f "$ENV_FILE" ]; then
    log "错误: .env 文件不存在: $ENV_FILE"
    exit 1
fi
log "✓ .env 文件存在"

# 2. 检查关键环境变量
REQUIRED_VARS=(
    "DATABASE_URL"
    "JWT_SECRET_KEY"
    "QWEN_API_KEY"
)
# 注意：如需从外部 EnvironmentFile 注入其他密钥，请确保 systemd / supervisor 已正确加载

for var in "${REQUIRED_VARS[@]}"; do
    if ! grep -q "^${var}=" "$ENV_FILE"; then
        log "错误: 缺少必需的环境变量: $var"
        exit 1
    fi
    value=$(grep "^${var}=" "$ENV_FILE" | cut -d'=' -f2-)
    if [ -z "$value" ]; then
        log "错误: 环境变量 $var 值为空"
        exit 1
    fi
done
log "✓ 关键环境变量已配置"

# 3. 检查 PostgreSQL 连接
if command -v pg_isready &> /dev/null; then
    if pg_isready -h localhost -p 5432 -U health_user -d health_db -q; then
        log "✓ PostgreSQL 数据库可连接"
    else
        log "警告: PostgreSQL 连接失败，服务可能需要重试"
    fi
else
    log "跳过: pg_isready 不可用"
fi

# 4. 检查 Python 虚拟环境
if [ ! -x "$VENV_PYTHON" ]; then
    log "错误: Python 虚拟环境不存在或不可执行: $VENV_PYTHON"
    exit 1
fi
log "✓ Python 虚拟环境正常"

# 5. 快速验证 Python 导入（可选，耗时约2秒）
cd "$BACKEND_DIR"
if "$VENV_PYTHON" -c "from app.main import app" 2>/dev/null; then
    log "✓ Python 应用导入成功"
else
    log "错误: Python 应用导入失败"
    "$VENV_PYTHON" -c "from app.main import app" 2>&1 | tail -10 | tee -a "$LOG_FILE"
    exit 1
fi

log "========== 启动前检查通过 =========="
exit 0
