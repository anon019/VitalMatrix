"""
文件存储服务 - 处理营养照片的上传、存储和清理
"""
import os
import shutil
import uuid
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Tuple, Optional
from PIL import Image
import aiofiles

logger = logging.getLogger(__name__)

# 获取 backend 根目录
BACKEND_ROOT = Path(__file__).parent.parent.parent
DEFAULT_UPLOAD_DIR = BACKEND_ROOT / "uploads" / "nutrition"


class FileStorageService:
    """文件存储服务类"""

    def __init__(self, base_dir: str = None):
        """
        初始化文件存储服务

        Args:
            base_dir: 存储根目录
        """
        self.base_dir = Path(base_dir) if base_dir else DEFAULT_UPLOAD_DIR
        self.thumbnail_size = (200, 200)  # 缩略图尺寸

        # 创建存储目录
        self.base_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"File storage service initialized at: {self.base_dir}")

    def _get_user_dir(self, user_id: str) -> Path:
        """获取用户专属目录"""
        user_dir = self.base_dir / str(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir

    def _get_date_dir(self, user_id: str, date: datetime) -> Path:
        """获取日期目录（用户/年月日）"""
        date_str = date.strftime("%Y%m%d")
        date_dir = self._get_user_dir(user_id) / date_str
        date_dir.mkdir(parents=True, exist_ok=True)
        return date_dir

    async def save_meal_photo(
        self,
        user_id: str,
        meal_id: str,
        file_content: bytes,
        meal_time: datetime,
        file_extension: str = "jpg"
    ) -> Tuple[str, str, str, str]:
        """
        保存餐食照片（原图 + 缩略图）

        Args:
            user_id: 用户ID
            meal_id: 餐次ID
            file_content: 文件二进制内容
            meal_time: 用餐时间
            file_extension: 文件扩展名（默认jpg）

        Returns:
            (原图web路径, 缩略图web路径, 原图绝对路径, 缩略图绝对路径) 元组

        Raises:
            IOError: 文件保存失败
        """
        try:
            # 获取存储目录
            date_dir = self._get_date_dir(user_id, meal_time)

            # 生成文件名
            original_filename = f"{meal_id}_original.{file_extension}"
            thumbnail_filename = f"{meal_id}_thumb.{file_extension}"

            original_path = date_dir / original_filename
            thumbnail_path = date_dir / thumbnail_filename

            # 保存原图
            async with aiofiles.open(original_path, "wb") as f:
                await f.write(file_content)

            logger.info(f"Saved original photo: {original_path}")

            # 生成缩略图
            await self._generate_thumbnail(original_path, thumbnail_path)

            logger.info(f"Saved thumbnail: {thumbnail_path}")

            # 返回Web可访问路径和绝对路径
            relative_original = str(original_path.relative_to(self.base_dir))
            relative_thumbnail = str(thumbnail_path.relative_to(self.base_dir))

            # Web路径（用于API响应和数据库存储）
            web_original = f"/uploads/nutrition/{relative_original}"
            web_thumbnail = f"/uploads/nutrition/{relative_thumbnail}"

            # 绝对路径（用于AI分析等本地文件操作）
            abs_original = str(original_path)
            abs_thumbnail = str(thumbnail_path)

            return web_original, web_thumbnail, abs_original, abs_thumbnail

        except Exception as e:
            logger.error(f"Failed to save meal photo: {str(e)}", exc_info=True)
            raise IOError(f"Failed to save meal photo: {str(e)}")

    async def _generate_thumbnail(self, original_path: Path, thumbnail_path: Path):
        """
        生成缩略图

        Args:
            original_path: 原图路径
            thumbnail_path: 缩略图保存路径
        """
        try:
            with Image.open(original_path) as img:
                # 转换RGBA到RGB（避免PNG透明通道问题）
                if img.mode in ("RGBA", "LA", "P"):
                    img = img.convert("RGB")

                # 生成缩略图（保持宽高比）
                img.thumbnail(self.thumbnail_size, Image.Resampling.LANCZOS)

                # 保存缩略图
                img.save(thumbnail_path, "JPEG", quality=85)

            logger.debug(f"Generated thumbnail: {thumbnail_path}")

        except Exception as e:
            logger.error(f"Failed to generate thumbnail: {str(e)}", exc_info=True)
            raise

    def get_absolute_path(self, relative_path: str) -> Path:
        """
        将相对路径转换为绝对路径

        Args:
            relative_path: 相对于base_dir的路径

        Returns:
            绝对路径
        """
        return self.base_dir / relative_path

    def delete_meal_photos(self, original_path: str, thumbnail_path: Optional[str] = None):
        """
        删除餐食照片

        Args:
            original_path: 原图相对路径
            thumbnail_path: 缩略图相对路径（可选）
        """
        try:
            # 删除原图
            abs_original = self.get_absolute_path(original_path)
            if abs_original.exists():
                abs_original.unlink()
                logger.info(f"Deleted original photo: {abs_original}")

            # 删除缩略图
            if thumbnail_path:
                abs_thumbnail = self.get_absolute_path(thumbnail_path)
                if abs_thumbnail.exists():
                    abs_thumbnail.unlink()
                    logger.info(f"Deleted thumbnail: {abs_thumbnail}")

        except Exception as e:
            logger.error(f"Failed to delete photos: {str(e)}", exc_info=True)

    def cleanup_old_photos(self, days: int = 30) -> int:
        """
        清理超过指定天数的照片

        Args:
            days: 保留天数（默认30天）

        Returns:
            删除的文件数量
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        deleted_count = 0

        try:
            # 遍历所有用户目录
            for user_dir in self.base_dir.iterdir():
                if not user_dir.is_dir():
                    continue

                # 遍历日期目录
                for date_dir in user_dir.iterdir():
                    if not date_dir.is_dir():
                        continue

                    try:
                        # 解析日期目录名（YYYYMMDD）
                        dir_date = datetime.strptime(date_dir.name, "%Y%m%d")

                        # 如果超过保留期限，删除整个目录
                        if dir_date < cutoff_date:
                            shutil.rmtree(date_dir)
                            deleted_count += 1
                            logger.info(f"Deleted old directory: {date_dir}")

                    except ValueError:
                        # 目录名不符合日期格式，跳过
                        logger.warning(f"Invalid date directory name: {date_dir.name}")
                        continue

            logger.info(f"Cleanup completed. Deleted {deleted_count} directories.")
            return deleted_count

        except Exception as e:
            logger.error(f"Failed to cleanup old photos: {str(e)}", exc_info=True)
            return deleted_count

    def get_storage_stats(self) -> dict:
        """
        获取存储统计信息

        Returns:
            统计信息字典
        """
        total_size = 0
        file_count = 0

        try:
            for file_path in self.base_dir.rglob("*"):
                if file_path.is_file():
                    total_size += file_path.stat().st_size
                    file_count += 1

            return {
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "file_count": file_count,
                "storage_path": str(self.base_dir)
            }

        except Exception as e:
            logger.error(f"Failed to get storage stats: {str(e)}")
            return {
                "total_size_mb": 0,
                "file_count": 0,
                "storage_path": str(self.base_dir),
                "error": str(e)
            }


# 全局单例实例
_file_storage_instance = None


def get_file_storage() -> FileStorageService:
    """获取文件存储服务单例"""
    global _file_storage_instance
    if _file_storage_instance is None:
        _file_storage_instance = FileStorageService()
    return _file_storage_instance
