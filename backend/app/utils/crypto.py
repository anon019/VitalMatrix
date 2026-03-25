"""
加密工具模块

用于加密/解密敏感数据（如 OAuth Token）
使用 Fernet 对称加密（基于 AES-128-CBC）
"""
import os
import base64
import hashlib
from typing import Optional
from cryptography.fernet import Fernet
from sqlalchemy import Text
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import TypeDecorator


def _get_encryption_key() -> bytes:
    """
    从环境变量获取或生成加密密钥

    使用 JWT_SECRET_KEY 派生加密密钥，确保：
    1. 不需要额外配置新的环境变量
    2. 密钥足够安全（来自已有的安全密钥）
    """
    secret = os.getenv("JWT_SECRET_KEY", "")
    if not secret:
        raise ValueError("JWT_SECRET_KEY not configured")

    # 使用 SHA256 派生 32 字节密钥，然后 base64 编码为 Fernet 格式
    key_bytes = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(key_bytes)


_fernet: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    """获取 Fernet 实例（单例）"""
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_get_encryption_key())
    return _fernet


def encrypt_token(plaintext: Optional[str]) -> Optional[str]:
    """
    加密 token

    Args:
        plaintext: 明文 token

    Returns:
        加密后的 base64 字符串，如果输入为 None 则返回 None
    """
    if plaintext is None:
        return None

    fernet = _get_fernet()
    encrypted = fernet.encrypt(plaintext.encode())
    return encrypted.decode()


def decrypt_token(ciphertext: Optional[str]) -> Optional[str]:
    """
    解密 token

    Args:
        ciphertext: 加密的 base64 字符串

    Returns:
        解密后的明文 token，如果输入为 None 则返回 None
    """
    if ciphertext is None:
        return None

    try:
        fernet = _get_fernet()
        decrypted = fernet.decrypt(ciphertext.encode())
        return decrypted.decode()
    except Exception:
        # 如果解密失败（可能是旧的明文数据），直接返回原值
        # 这样可以兼容迁移期间的旧数据
        return ciphertext


class EncryptedText(TypeDecorator):
    """
    SQLAlchemy TypeDecorator for encrypted text fields.

    Automatically encrypts on write and decrypts on read.
    Backward compatible with existing plaintext data.
    """
    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Optional[str], dialect: Dialect) -> Optional[str]:
        """Encrypt before storing in database."""
        return encrypt_token(value)

    def process_result_value(self, value: Optional[str], dialect: Dialect) -> Optional[str]:
        """Decrypt after loading from database."""
        return decrypt_token(value)
