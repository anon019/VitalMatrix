"""
测试Qwen AI建议生成功能
"""
import asyncio
import sys
from datetime import date

# 添加项目路径
sys.path.insert(0, '/root/health/backend')

from app.database.session import get_db
from app.services.ai_service import AIService
from app.utils.datetime_helper import today_hk
import uuid


async def test_qwen_generation():
    """测试Qwen AI建议生成"""
    print("=" * 80)
    print("测试Qwen AI建议生成")
    print("=" * 80)

    # 用户ID
    user_id = uuid.UUID("d2a97ae6-a89b-4af3-83fc-04ce3ebaf43c")

    # 获取数据库会话
    async for db in get_db():
        ai_service = AIService(db)

        print(f"\n用户ID: {user_id}")
        print(f"日期: {today_hk()}")
        print(f"\n开始生成AI建议...")

        try:
            # 强制重新生成今日建议
            recommendation = await ai_service.regenerate_recommendation(
                user_id=user_id,
                target_date=today_hk(),
                provider_name="qwen"  # 使用Qwen测试
            )

            print(f"\n✅ AI建议生成成功！")
            print(f"Provider: {recommendation.provider}")
            print(f"Model: {recommendation.model}")
            print(f"\n📋 Summary:")
            print(recommendation.summary)
            print(f"\n📅 昨日评价 (Yesterday Review):")
            print(recommendation.yesterday_review)
            print(f"\n💡 今日建议 (Today Recommendation):")
            print(recommendation.today_recommendation)
            print(f"\n📚 健康科普 (Health Education):")
            print(recommendation.health_education)
            print(f"\nTokens使用: {recommendation.prompt_tokens} + {recommendation.completion_tokens} = {recommendation.prompt_tokens + recommendation.completion_tokens}")

        except Exception as e:
            print(f"\n❌ 生成失败: {str(e)}")
            import traceback
            traceback.print_exc()

        break  # 只需要一个会话


if __name__ == "__main__":
    asyncio.run(test_qwen_generation())
