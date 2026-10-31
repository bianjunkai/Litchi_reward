"""Small inline reward images; no external fetches or executable image formats."""
import base64
import binascii
import re

MAX_IMAGE_BYTES = 96_000
MAX_IMAGE_TEXT = 128_050


def validate_image(value):
    if not isinstance(value, str):
        raise ValueError('奖励图片必须是图片数据')
    if value == '':
        return value
    if len(value) > MAX_IMAGE_TEXT:
        raise ValueError('奖励图片过大，请压缩后重试（最多 96KB）')
    match = re.fullmatch(r'data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/]+={0,2})', value)
    if not match:
        raise ValueError('奖励图片只支持本地 JPG、PNG 或 WebP，不支持网址或 SVG')
    try:
        raw = base64.b64decode(match[2], validate=True)
    except (ValueError, binascii.Error):
        raise ValueError('奖励图片编码无效')
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError('奖励图片最多 96KB')
    valid = {'png':raw.startswith(b'\x89PNG\r\n\x1a\n'),
             'jpeg':raw.startswith(b'\xff\xd8\xff') and raw.endswith(b'\xff\xd9'),
             'webp':raw.startswith(b'RIFF') and raw[8:12] == b'WEBP'}
    if not valid[match[1]]:
        raise ValueError('奖励图片内容与格式不符')
    return value
