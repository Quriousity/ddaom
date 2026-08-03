"""골든 샘플 PDF 생성기 (명세 §14).

4종을 생성한다: 텍스트 PDF / 스캔본(이미지만) / 회전 페이지 / 암호화.
내용은 결정적(deterministic) — 같은 실행이면 같은 파일이 나와 골든 테스트가 성립한다.

실행: .venv/bin/python -m tools.make_samples
"""
from __future__ import annotations

import io
import os
import sys

import fitz
from PIL import Image, ImageDraw, ImageFont

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "tests", "samples")

# 한국어 폰트: mac / windows 겸용 탐색
_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",   # macOS
    "C:/Windows/Fonts/malgun.ttf",                          # Windows
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",      # linux CI
]


def _font_path() -> str:
    for p in _FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    raise RuntimeError("한국어 TTF 폰트를 찾을 수 없다")


# 골든 내용 — 테스트가 이 문자열들을 그대로 참조한다
LINES = [
    "세무사 김철수",
    "사업자등록번호 123-45-67890",
    "합계금액 1,234,567원",
    "Tax Report 2026 Annual",
    "계좌번호 110-234-567890",
]
SECRET = "주민등록번호 900101-1234567"  # 리댁션 대상


def make_text_pdf(path: str) -> None:
    """글자층이 있는 PDF. LINES + SECRET 를 실제 텍스트로 삽입."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4 pt
    y = 100
    for line in LINES:
        page.insert_text((72, y), line, fontname="korea", fontsize=14)
        y += 40
    page.insert_text((72, 500), SECRET, fontname="korea", fontsize=14)
    doc.set_metadata({"title": "golden-text", "author": "sample-author",
                      "creator": "make_samples", "producer": "pymupdf"})
    doc.save(path)
    doc.close()


def _render_page_image(width_px: int = 1240, height_px: int = 1754) -> Image.Image:
    """스캔본용 페이지 이미지 (A4 @150dpi)."""
    font = ImageFont.truetype(_font_path(), 28)
    img = Image.new("RGB", (width_px, height_px), "white")
    d = ImageDraw.Draw(img)
    y = 200
    for line in LINES:
        d.text((150, y), line, font=font, fill="black")
        y += 84
    d.text((150, 1040), SECRET, font=font, fill="black")
    return img


def make_scanned_pdf(path: str) -> None:
    """이미지 한 장뿐인 스캔 PDF — 글자층 없음. OCR 폴백·이미지 리댁션 검증용."""
    img = _render_page_image()
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(page.rect, stream=buf.getvalue())
    doc.set_metadata({"title": "golden-scan", "author": "scanner-x"})
    doc.save(path)
    doc.close()


def make_rotated_pdf(path: str) -> None:
    """회전 페이지(90도) — 좌표변환 검증용 (§9: 가장 흔한 버그)."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 100
    for line in LINES:
        page.insert_text((72, y), line, fontname="korea", fontsize=14)
        y += 40
    page.set_rotation(90)
    doc.save(path)
    doc.close()


def make_encrypted_pdf(path: str, password: str = "test123") -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 100), LINES[0], fontname="korea", fontsize=14)
    doc.save(path, encryption=fitz.PDF_ENCRYPT_AES_256,
             owner_pw=password, user_pw=password)
    doc.close()


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    make_text_pdf(os.path.join(OUT, "text.pdf"))
    make_scanned_pdf(os.path.join(OUT, "scan.pdf"))
    make_rotated_pdf(os.path.join(OUT, "rotated.pdf"))
    make_encrypted_pdf(os.path.join(OUT, "encrypted.pdf"))
    print(f"samples -> {OUT}")


if __name__ == "__main__":
    sys.exit(main())
