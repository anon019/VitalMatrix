"""
文件存储服务 - 处理营养照片的上传、长期存储和按餐次删除
"""
import logging
import asyncio
import warnings
from io import BytesIO
from datetime import datetime
from pathlib import Path
from typing import Tuple, Optional
from PIL import Image, ImageOps, UnidentifiedImageError
from app.services.nutrition_errors import InvalidMealImageError

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).parent.parent.parent
DEFAULT_UPLOAD_DIR = BACKEND_ROOT / "uploads" / "nutrition"


class FileStorageService:
    """文件存储服务类"""

    def __init__(self, base_dir: str | None = None):
        """
        初始化文件存储服务

        Args:
            base_dir: 存储根目录
        """
        self.base_dir = Path(base_dir) if base_dir else DEFAULT_UPLOAD_DIR
        self.thumbnail_size = (200, 200)  # 缩略图尺寸
        self.max_image_dimension = 4096
        self.max_image_pixels = 40_000_000

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

            # 只解码一次，同时写出规范化原图和缩略图。
            write_task = asyncio.create_task(asyncio.to_thread(
                self._normalize_and_save_images_sync,
                file_content, original_path, thumbnail_path,
            ))
            try:
                await asyncio.shield(write_task)
            except asyncio.CancelledError:
                # A worker thread cannot be cancelled. Let it finish before cleanup.
                await asyncio.gather(write_task, return_exceptions=True)
                original_path.unlink(missing_ok=True)
                thumbnail_path.unlink(missing_ok=True)
                raise
            except Exception:
                original_path.unlink(missing_ok=True)
                thumbnail_path.unlink(missing_ok=True)
                raise

            logger.info(f"Saved original photo: {original_path}")
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

        except InvalidMealImageError:
            raise
        except Exception as e:
            logger.error(f"Failed to save meal photo: {str(e)}", exc_info=True)
            raise IOError(f"Failed to save meal photo: {str(e)}")

    def _normalize_image_sync(self, file_content: bytes, output_path: Path) -> None:
        """将受支持的输入统一保存为无 EXIF 的 JPEG。"""
        image = self._decode_normalized_image(file_content)
        try:
            image.save(output_path, "JPEG", quality=90, optimize=True)
        finally:
            image.close()

    def _normalize_and_save_images_sync(
        self,
        file_content: bytes,
        original_path: Path,
        thumbnail_path: Path,
    ) -> None:
        """一次解码后同时保存原图和缩略图。"""
        image = self._decode_normalized_image(file_content)
        try:
            image.save(original_path, "JPEG", quality=90, optimize=True)
            thumbnail = image.copy()
            try:
                thumbnail.thumbnail(self.thumbnail_size, Image.Resampling.LANCZOS)
                thumbnail.save(thumbnail_path, "JPEG", quality=85)
            finally:
                thumbnail.close()
        finally:
            image.close()

    def _decode_normalized_image(self, file_content: bytes) -> Image.Image:
        """解码、纠正方向、限制像素并转为 RGB。"""
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(file_content)) as source:
                    if source.format not in {"JPEG", "PNG", "WEBP"}:
                        raise InvalidMealImageError("仅支持 JPEG、PNG 和 WebP 图片")
                    if source.width * source.height > self.max_image_pixels:
                        raise InvalidMealImageError("图片像素过大，最多支持 4000 万像素")

                    image = ImageOps.exif_transpose(source)
                    image.load()
                    if max(image.size) > self.max_image_dimension:
                        image.thumbnail(
                            (self.max_image_dimension, self.max_image_dimension),
                            Image.Resampling.LANCZOS,
                        )

                    if image.mode in ("RGBA", "LA"):
                        background = Image.new("RGB", image.size, "white")
                        alpha = image.getchannel("A")
                        background.paste(image.convert("RGB"), mask=alpha)
                        image = background
                    elif image.mode != "RGB":
                        image = image.convert("RGB")

                    return image
        except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning, OSError) as exc:
            raise InvalidMealImageError("图片文件无效或像素规模不安全") from exc

    async def _generate_thumbnail(self, original_path: Path, thumbnail_path: Path):
        """
        生成缩略图

        Args:
            original_path: 原图路径
            thumbnail_path: 缩略图保存路径
        """
        await asyncio.to_thread(
            self._generate_thumbnail_sync,
            original_path,
            thumbnail_path,
        )

    def _generate_thumbnail_sync(
        self,
        original_path: Path,
        thumbnail_path: Path,
    ) -> None:
        """在线程中执行 Pillow 解码和缩略图编码，避免阻塞事件循环。"""
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
        if not relative_path:
            raise ValueError("媒体路径不能为空")

        path = relative_path
        for prefix in ("/uploads/nutrition/", "uploads/nutrition/"):
            if path.startswith(prefix):
                path = path[len(prefix):]
                break
        path = path.lstrip("/")

        base = self.base_dir.resolve()
        candidate = (base / path).resolve()
        try:
            candidate.relative_to(base)
        except ValueError as exc:
            raise ValueError("媒体路径超出允许目录") from exc
        return candidate

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
        """保留旧调用兼容性，但永久禁用已落库营养照片的按日期清理。

        旧实现只删除图片目录、不删除对应餐次记录，会让历史数据永久指向
        不存在的文件。即使旧脚本或人工命令再次调用，也必须保持为无操作。
        """
        logger.warning(
            "Ignoring cleanup_old_photos(days=%s): nutrition photos are permanent records",
            days,
        )
        return 0

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
