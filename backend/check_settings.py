"""
检查settings配置加载
"""
import sys
sys.path.insert(0, '/root/health/backend')

from app.config import settings

print("=" * 80)
print("Settings配置检查")
print("=" * 80)

print(f"\nAI_PROVIDER: {settings.AI_PROVIDER}")
print(f"QWEN_API_KEY: {settings.QWEN_API_KEY[:20] if settings.QWEN_API_KEY else 'EMPTY'}...")
print(f"DEEPSEEK_API_KEY: {settings.DEEPSEEK_API_KEY[:20] if settings.DEEPSEEK_API_KEY else 'EMPTY'}...")

print("\n" + "=" * 80)

# 测试AIProviderFactory
from app.ai.factory import AIProviderFactory

print("测试AIProviderFactory")
print("=" * 80)

try:
    provider = AIProviderFactory.create("qwen")
    print(f"✅ Qwen Provider创建成功")
    print(f"Provider name: {provider.name}")
    print(f"Provider model: {provider.model}")
    print(f"API Key (前20字符): {provider.api_key[:20] if provider.api_key else 'EMPTY'}...")
except Exception as e:
    print(f"❌ Qwen Provider创建失败: {str(e)}")
