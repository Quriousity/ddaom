"""클립보드 유틸 (명세 §4.4).

Windows 클립보드(CF_DIB)는 알파를 제대로 나르지 못한다 —
클립보드행 이미지는 항상 흰 배경으로 합성한다. 투명 유지는 파일 저장 경로에서만.
"""
from __future__ import annotations

from PIL import Image
from PySide6.QtGui import QGuiApplication, QImage


def set_text(text: str) -> None:
    QGuiApplication.clipboard().setText(text)


def _flatten_white(img: Image.Image) -> Image.Image:
    if img.mode in ("RGBA", "LA", "PA"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.getchannel("A"))
        return bg
    return img.convert("RGB")


def pil_to_qimage(img: Image.Image) -> QImage:
    img = _flatten_white(img)
    data = img.tobytes("raw", "RGB")
    qimg = QImage(data, img.width, img.height, img.width * 3, QImage.Format_RGB888)
    return qimg.copy()  # data 버퍼 수명에서 분리


def set_image(img: Image.Image) -> None:
    QGuiApplication.clipboard().setImage(pil_to_qimage(img))
