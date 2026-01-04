"""手动同步 Oura 数据并重新生成 AI 建议

使用方法:
    USER_ID=your-user-id python scripts/manual_sync.py
"""
import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date
from app.services.oura_sync import OuraSyncService
from app.services.ai_service import AIService
from app.db.session import async_session

# 从环境变量读取用户ID
USER_ID = os.environ.get("USER_ID", "")

async def sync_and_regenerate():
    if not USER_ID:
        print("错误: 请设置 USER_ID 环境变量")
        print("使用方法: USER_ID=your-user-id python scripts/manual_sync.py")
        sys.exit(1)

    async with async_session() as session:
        # 1. 同步 Oura 数据
        print("="*60)
        print("1. 同步 Oura 数据...")
        print("="*60)
        oura_service = OuraSyncService(session)
        result = await oura_service.sync_user_data(USER_ID, days=3, force=True)
        print(f"同步结果: {result}")

        # 2. 重新生成 AI 建议
        print("\n" + "="*60)
        print("2. 重新生成今日 AI 建议...")
        print("="*60)
        ai_service = AIService(session)
        rec = await ai_service.generate_daily_recommendation(USER_ID, date.today())
        print(f"AI 建议已生成: {rec.summary if rec else '失败'}")

        await session.commit()
        print("\n✅ 完成！")

if __name__ == "__main__":
    asyncio.run(sync_and_regenerate())
