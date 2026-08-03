"""영역 텍스트 추출 — 텍스트 레이어 우선, OCR 폴백 (명세 §4.2, §4.3).

핵심 규칙:
- 글자층이 있으면 OCR 을 돌리지 않는다 (돌리면 더 부정확하다).
- OCR 은 전처리(§4.2.1)를 거치고, 한 줄짜리 좁은 영역은 det 을 생략한다(§4.2.2).
- 폴리곤 마스킹은 패딩과 같은 흰색으로 채운다 — 대비선이 생기면 검출기가 오인한다.
"""
from __future__ import annotations

import io
import re

import fitz
import numpy as np
from PIL import Image, ImageDraw

from .. import config
from . import coords
from .document import Document
from .ocr_engine import OCREngine, OCRLine, default_engine

Point = tuple[float, float]


# --- 라인 그룹핑 (§4.2) ---

def group_words_into_lines(words: list[tuple[float, float, float, float, str]]) -> str:
    """(x0, y0, x1, y1, text) 목록 -> 읽기 순서 텍스트.

    y중심으로 라인 그룹핑(임계 = 평균 글자높이 * LINE_GROUP_FACTOR) 후 라인 내 x정렬.
    """
    if not words:
        return ""
    heights = [w[3] - w[1] for w in words]
    avg_h = sum(heights) / len(heights)
    thresh = max(avg_h * config.LINE_GROUP_FACTOR, 1.0)

    items = sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    lines: list[list[tuple[float, float, float, float, str]]] = []
    for w in items:
        yc = (w[1] + w[3]) / 2
        if lines:
            last_yc = sum((x[1] + x[3]) / 2 for x in lines[-1]) / len(lines[-1])
            if abs(yc - last_yc) <= thresh:
                lines[-1].append(w)
                continue
        lines.append([w])
    out = []
    for line in lines:
        line.sort(key=lambda w: w[0])
        out.append(" ".join(w[4] for w in line))
    return "\n".join(out)


def postprocess(text: str) -> str:
    """줄바꿈 정규화 + 하이픈 줄바꿈 병합 (§4.2-4)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    if config.JOIN_HYPHENATED_LINES:
        # 라틴 단어가 하이픈으로 줄바꿈된 경우만 병합 (한국어엔 적용하지 않는다)
        text = re.sub(r"(?<=[A-Za-z])-\n(?=[a-z])", "", text)
    return text.strip()


# --- OCR 전처리 (§4.2.1) ---

def _prepare_ocr_image(png: bytes, polygon_px: list[Point] | None = None
                       ) -> tuple[np.ndarray, int, float]:
    """PNG bytes -> (OCR 입력 ndarray, 적용된 pad_px, 업스케일 배율).

    그레이스케일 -> 폴리곤 흰색 마스킹 -> 흰 패딩 -> 소형 업스케일.
    반환된 pad/scale 은 OCR 폴리곤을 PDF 좌표로 되돌릴 때 필요하다.
    """
    img = Image.open(io.BytesIO(png)).convert("L")

    if polygon_px:
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).polygon([(x, y) for x, y in polygon_px], fill=255)
        white = Image.new("L", img.size, 255)
        img = Image.composite(img, white, mask)  # 폴리곤 밖 = 패딩과 같은 흰색

    pad = config.OCR_PAD_PX
    padded = Image.new("L", (img.width + 2 * pad, img.height + 2 * pad), 255)
    padded.paste(img, (pad, pad))
    img = padded

    scale = 1.0
    if min(img.size) < config.OCR_MIN_SHORT_SIDE + 2 * pad:
        scale = 2.0
        img = img.resize((int(img.width * 2), int(img.height * 2)), Image.LANCZOS)

    rgb = np.array(img.convert("RGB"))
    return rgb, pad, scale


def _ocr_region(doc: Document, page_no: int, clip: fitz.Rect,
                polygon_pt: list[Point] | None, engine: OCREngine
                ) -> tuple[str, list[OCRLine]]:
    png = doc.render_clip_png(page_no, clip, config.OCR_DPI)
    poly_px = (coords.pdf_to_crop_polygon(polygon_pt, clip, config.OCR_DPI)
               if polygon_pt else None)
    img, pad, scale = _prepare_ocr_image(png, poly_px)

    h, w = img.shape[:2]
    # 단일라인 판정: 납작한 비율 + 절대 높이 상한 (넓은 두 줄 영역 오판 방지)
    single = ((h / max(w, 1)) < config.SINGLE_LINE_RATIO
              and h <= config.SINGLE_LINE_MAX_H_PX * scale + 2 * pad)
    lines = engine.run(img, single_line=single)
    if single:
        # 고속 경로 자기검증: 빈손이거나 점수가 낮으면 det 경로로 재시도
        mean_score = (sum(ln.score for ln in lines) / len(lines)) if lines else 0.0
        if mean_score < config.SINGLE_LINE_MIN_SCORE:
            lines = engine.run(img, single_line=False)

    words = [(min(p[0] for p in ln.polygon), min(p[1] for p in ln.polygon),
              max(p[0] for p in ln.polygon), max(p[1] for p in ln.polygon), ln.text)
             for ln in lines]
    return group_words_into_lines(words), lines


# --- 공개 API ---

def extract_text(doc: Document, page_no: int,
                 rect: fitz.Rect | None = None,
                 polygon: list[Point] | None = None,
                 engine: OCREngine | None = None) -> tuple[str, str]:
    """영역 텍스트 추출. rect 또는 polygon(PDF point) 중 하나를 받는다.

    반환: (텍스트, 출처)  출처 = "text-layer" | "ocr"
    """
    if polygon:
        clip = coords.polygon_bbox(polygon)
    elif rect is not None:
        clip = fitz.Rect(rect)
    else:
        raise ValueError("rect or polygon required")
    page = doc.page(page_no)
    clip = coords.clamp_rect(clip, page.rect)
    if clip.is_empty:
        return "", "text-layer"

    # 1) 텍스트 레이어 우선
    words_raw = page.get_text("words", clip=clip)
    words = [(w[0], w[1], w[2], w[3], w[4]) for w in words_raw]
    if polygon:
        # 단어 중심점 point-in-polygon 판정 (§4.3)
        words = [w for w in words
                 if coords.point_in_polygon((w[0] + w[2]) / 2, (w[1] + w[3]) / 2, polygon)]
    joined = "".join(w[4] for w in words)
    if len(joined) >= config.MIN_CHARS_FOR_TEXT_LAYER:
        return postprocess(group_words_into_lines(words)), "text-layer"

    # 2) OCR 폴백
    text, _ = _ocr_region(doc, page_no, clip, polygon, engine or default_engine())
    return postprocess(text), "ocr"


def extract_image(doc: Document, page_no: int,
                  rect: fitz.Rect | None = None,
                  polygon: list[Point] | None = None,
                  dpi: int | None = None,
                  transparent_outside: bool = False) -> Image.Image:
    """영역 이미지 추출 (§4.4). PDF point 영역을 dpi 로 재렌더 — 화면 해상도와 무관."""
    dpi = dpi or config.EXPORT_DPI
    if polygon:
        clip = coords.polygon_bbox(polygon)
    elif rect is not None:
        clip = fitz.Rect(rect)
    else:
        raise ValueError("rect or polygon required")
    page = doc.page(page_no)
    clip = coords.clamp_rect(clip, page.rect)
    if clip.is_empty:
        raise ValueError("selection outside page")

    png = doc.render_clip_png(page_no, clip, dpi)
    img = Image.open(io.BytesIO(png)).convert("RGB")

    if polygon:
        poly_px = coords.pdf_to_crop_polygon(polygon, clip, dpi)
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).polygon([(x, y) for x, y in poly_px], fill=255)
        if transparent_outside:
            rgba = img.convert("RGBA")
            rgba.putalpha(mask)
            return rgba
        white = Image.new("RGB", img.size, (255, 255, 255))
        img = Image.composite(img, white, mask)
    return img
