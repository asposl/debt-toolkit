# -*- coding: utf-8 -*-
"""图片转 PDF（原 file_toolkit.py「公共：图片转 PDF」区，convert.ipynb 血缘）。

被 dedup.py（复制后转图再比对指纹）与 convert_images 命令共用。
"""

from pathlib import Path

from PIL import Image

IMAGE_GLOB_PATTERNS = [
    "**/*.jpg", "**/*.jpeg", "**/*.JPG", "**/*.JPEG",
    "**/*.png", "**/*.PNG", "**/*.jfif", "**/*.JFIF",
]


def _image_to_rgb(image: Image.Image) -> Image.Image:
    """统一转为 RGB；带透明通道的图铺白色背景，防止透明区域变黑。"""
    if image.mode in ("RGBA", "LA", "P"):
        background = Image.new("RGB", image.size, (255, 255, 255))
        if image.mode == "RGBA":
            background.paste(image, mask=image.split()[3])
        else:
            background.paste(image)
        return background
    if image.mode != "RGB":
        return image.convert("RGB")
    return image


def convert_images_in_tree(target_dir: Path, logger):
    """递归把图片转为同名 PDF 并删原图；同名更新的 PDF 则直接删旧图。"""
    image_files, seen = [], set()
    for pattern in IMAGE_GLOB_PATTERNS:
        for found in Path(target_dir).glob(pattern):
            if found not in seen:
                seen.add(found)
                image_files.append(found)

    success_count = fail_count = 0
    for img_path in image_files:
        if not img_path.exists():
            continue
        pdf_path = img_path.with_suffix(".pdf")
        rel_path = img_path.relative_to(target_dir)

        if pdf_path.exists() and pdf_path.stat().st_mtime > img_path.stat().st_mtime:
            logger.info(f"[直接删除] 发现更新的 PDF，已删除旧图: {rel_path}")
            img_path.unlink()
            success_count += 1
            continue
        try:
            with Image.open(img_path) as image:
                _image_to_rgb(image).save(pdf_path, "PDF")
            img_path.unlink()
            logger.info(f"[转换成功] 已将图片转为 PDF 并删除原图: {rel_path}")
            success_count += 1
        except Exception as e:
            logger.error(f"[转换失败] 无法转换文件 {rel_path}: {e}")
            fail_count += 1
    return success_count, fail_count


def cmd_convert_images(args, logger):
    target_dir = Path(args.target)
    if not target_dir.exists():
        logger.error(f"目标目录不存在：{target_dir}")
        return 1
    logger.info("==================== 开始图片转 PDF 任务 ====================")
    logger.info(f"正在扫描并处理目录: {target_dir}")
    success_count, fail_count = convert_images_in_tree(target_dir, logger)
    logger.info("==================== 图片转 PDF 完成 ====================")
    logger.info(f"成功处理: {success_count} 个，失败: {fail_count} 个。")
    return 0 if fail_count == 0 else 1
