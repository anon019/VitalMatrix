"""手动同步 Oura 数据并重新生成 AI 建议

使用方法:
    USER_ID=your-user-id python scripts/manual_sync.py
"""
import asyncio
import os
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.session import AsyncSessionLocal
from app.services.ai_service import AIService
from app.services.oura_sync import OuraSyncService


USER_ID = os.environ.get("USER_ID", "")


async def sync_and_regenerate():
    if not USER_ID:
        print("错误: 请设置 USER_ID 环境变量")
        print("使用方法: USER_ID=your-user-id python scripts/manual_sync.py")
        sys.exit(1)

    user_id = uuid.UUID(USER_ID)

    async with AsyncSessionLocal() as session:
        print("=" * 60)
        print("1. 同步 Oura 数据...")
        print("=" * 60)
        oura_service = OuraSyncService(session)
        result = await oura_service.sync_user_data(user_id, days=3, force=True)
        print(f"同步结果: {result}")

        print("\n" + "=" * 60)
        print("2. 重新生成今日 AI 建议...")
        print("=" * 60)
        ai_service = AIService(session)
        rec = await ai_service.generate_daily_recommendation(user_id, date.today())
        print(f"AI 建议已生成: {rec.summary if rec else '失败'}")

        await session.commit()
        print("\n✅ 完成！")


if __name__ == "__main__":
    asyncio.run(sync_and_regenerate())
