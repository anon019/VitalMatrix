"""
强制重新生成AI建议（用于测试）
"""
import asyncio
import sys
import uuid
sys.path.insert(0, '/root/health/backend')

from datetime import date

# 必须先导入所有模型以正确配置 SQLAlchemy
import app.models  # 导入所有模型

async def main():
    from app.database.session import AsyncSessionLocal
    from app.services.ai_service import AIService

    user_id = uuid.UUID("d2a97ae6-a89b-4af3-83fc-04ce3ebaf43c")
    target_date = date(2025, 12, 4)

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
