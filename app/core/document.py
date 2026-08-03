"""fitz.Document 래퍼 — 열기/렌더/LRU 캐시 (명세 §3, §5)."""
from __future__ import annotations

from collections import OrderedDict

import fitz

from .. import config


class NeedsPassword(Exception):
    pass


class BadPassword(Exception):
    pass


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def is_image_path(path: str) -> bool:
    import os
    return os.path.splitext(path)[1].lower() in IMAGE_EXTS


class Document:
    def __init__(self, path: str, password: str | None = None):
        self.path = path
        self.is_image_source = is_image_path(path)
        if self.is_image_source:
            # 이미지 → 메모리에서 1페이지 PDF 로 감싼다.
            # 페이지 pt 크기는 이미지 dpi 메타데이터에 따른다 (없으면 96dpi 가정
            # → 1px = 0.75pt). 좌표는 항상 page.rect 기준으로 다룰 것.
            img = fitz.open(path)
            pdf_bytes = img.convert_to_pdf()
            img.close()
            self.doc = fitz.open("pdf", pdf_bytes)
        else:
            self.doc = fitz.open(path)
        if self.doc.needs_pass:
            if password is None:
                self.doc.close()
                raise NeedsPassword(path)
            if not self.doc.authenticate(password):
                self.doc.close()
                raise BadPassword(path)
        # (page_no, zoom 1/100 양자화) -> PNG bytes
        self._cache: OrderedDict[tuple[int, int], bytes] = OrderedDict()

    @property
    def page_count(self) -> int:
        return self.doc.page_count

    def page(self, page_no: int) -> fitz.Page:
        return self.doc[page_no]

    def page_rect(self, page_no: int) -> fitz.Rect:
        return self.doc[page_no].rect

    # --- 화면 렌더 (줌 배율, LRU 캐시) ---

    def render_page_png(self, page_no: int, zoom: float) -> bytes:
        key = (page_no, round(zoom * 100))
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        mat = fitz.Matrix(zoom, zoom)
        pix = self.doc[page_no].get_pixmap(matrix=mat, alpha=False)
        png = pix.tobytes("png")
        self._cache[key] = png
        while len(self._cache) > config.PAGE_CACHE_SIZE:
            self._cache.popitem(last=False)
        return png

    # --- 영역 렌더 (dpi 지정, OCR·이미지 추출용. 캐시 없음 — 매번 고품질 재렌더) ---

    def render_clip_png(self, page_no: int, clip: fitz.Rect, dpi: int) -> bytes:
        pix = self.doc[page_no].get_pixmap(clip=clip, dpi=dpi, alpha=False)
        return pix.tobytes("png")

    def render_thumb_png(self, page_no: int, width_px: int) -> bytes:
        rect = self.page_rect(page_no)
        zoom = width_px / max(rect.width, 1)
        pix = self.doc[page_no].get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        return pix.tobytes("png")

    def close(self):
        self._cache.clear()
        self.doc.close()
