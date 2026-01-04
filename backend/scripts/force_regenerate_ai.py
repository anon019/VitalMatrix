"""
强制重新生成AI建议（用于测试）

使用方法:
    USER_ID=your-user-id TARGET_DATE=2025-12-04 python scripts/force_regenerate_ai.py
"""
import asyncio
import sys
import os
import uuid

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, datetime

# 必须先导入所有模型以正确配置 SQLAlchemy
import app.models  # 导入所有模型

# 从环境变量读取配置
USER_ID = os.environ.get("USER_ID", "")
TARGET_DATE = os.environ.get("TARGET_DATE", "")

async def main():
    if not USER_ID:
        print("错误: 请设置 USER_ID 环境变量")
        print("使用方法: USER_ID=your-user-id python scripts/force_regenerate_ai.py")
        sys.exit(1)

    from app.database.session import AsyncSessionLocal
    from app.services.ai_service import AIService

    user_id = uuid.UUID(USER_ID)

    # 解析目标日期，默认为今天
    if TARGET_DATE:
        target_date = datetime.strptime(TARGET_DATE, "%Y-%m-%d").date()
    else:
        target_date = date.today()

    print(f"强制重新生成 AI 建议: user_id={user_id}, date={target_date}")

    async with AsyncSessionLocal() as db:
        ai_service = AIService(db)

        # 使用 regenerate 会删除旧记录并生成新的
        recommendation = await ai_service.regenerate_recommendation(
            user_id=user_id,
            target_date=target_date
        )

        print(f"\n✅ AI 建议生成成功!")
        print(f"模型: {recommendation.provider}/{recommendation.model}")
        print(f"摘要: {recommendation.summary}")

if __name__ == "__main__":
    asyncio.run(main())
