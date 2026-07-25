import base64
from io import BytesIO
from typing import Tuple
from PIL import Image
import aiohttp

from config import MAX_LONG_SIDE, DOWNLOAD_TIMEOUT


def encode_image(image_data: bytes) -> str:
    """Base64 с ресайзом по MAX_LONG_SIDE, WebP quality=95."""
    with Image.open(BytesIO(image_data)) as im:
        # Конвертация только если режим не совпадает
        if im.mode in ("RGBA", "LA", "P"):
            if im.mode != "RGBA":
                im = im.convert("RGBA")
        elif im.mode != "RGB":
            im = im.convert("RGB")
        
        w, h = im.size
        long_side = max(w, h)
        
        if long_side > MAX_LONG_SIDE:
            scale = MAX_LONG_SIDE / float(long_side)
            new_w, new_h = int(w * scale), int(h * scale)
            im = im.resize((new_w, new_h), Image.Resampling.LANCZOS)
            
        buf = BytesIO()
        im.save(buf, format="WEBP", quality=95, method=6)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode('utf-8')


def create_image_message(encoded_img: str) -> dict:
    """Структура image_url для API."""
    return {
        "type": "image_url", 
        "image_url": {"url": f"data:image/webp;base64,{encoded_img}"}
    }


async def download_image(session: aiohttp.ClientSession, url: str, file_id: str) -> Tuple[str, bytes]:
    """Скачивает изображение по URL. Возвращает (file_id, bytes)."""
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT)) as response:
        if response.status != 200:
            raise Exception(f"HTTP {response.status}")
        
        image_data = await response.read()
        
        if not image_data:
            raise Exception("Пустой файл")
        
        # Валидация: проверка magic bytes (JPEG, PNG, GIF, WebP)
        if not image_data.startswith((
            b'\xff\xd8\xff',      # JPEG
            b'\x89PNG\r\n\x1a\n', # PNG
            b'GIF87a',            # GIF87a
            b'GIF89a',            # GIF89a
            b'RIFF',              # WebP (начинается с RIFF)
        )):
            raise Exception("Файл не является изображением")
        
        # Дополнительная проверка: попытка открыть изображение
        try:
            with Image.open(BytesIO(image_data)) as img:
                img.verify()  # Проверяет целостность
        except Exception as e:
            raise Exception(f"Поврежденное изображение: {e}")
        
        return file_id, image_data
