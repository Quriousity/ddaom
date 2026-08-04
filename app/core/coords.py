"""좌표 변환 — 모든 좌표 산술은 이 모듈만 거친다 (명세 §4.1).

좌표계 4종:
  1. PDF point (72dpi, PyMuPDF 좌상단 원점, 회전 반영된 표시 공간 = page.rect 기준)
  2. 렌더 픽셀 (zoom 배율)  — 씬 좌표와 동일하게 쓴다 (씬 = 렌더 픽셀)
  3. Qt 뷰 좌표             — Qt 의 mapToScene/mapFromScene 이 담당
  4. crop 픽셀              — OCR 입력 이미지 기준. dpi 배율 + crop 원점 오프셋

선택 영역은 항상 PDF point 로 저장한다. 화면·이미지 좌표는 표시용 임시값.
"""
from __future__ import annotations

import fitz

Point = tuple[float, float]


# --- 씬(=렌더 픽셀) <-> PDF point ---

def scene_to_pdf_rect(x0: float, y0: float, x1: float, y1: float, zoom: float) -> fitz.Rect:
    """씬 사각형 -> PDF point 사각형. 씬은 page.rect * zoom 공간이다."""
    inv = 1.0 / zoom
    r = fitz.Rect(x0 * inv, y0 * inv, x1 * inv, y1 * inv)
    r.normalize()
    return r


def pdf_to_scene_rect(rect: fitz.Rect, zoom: float) -> tuple[float, float, float, float]:
    return rect.x0 * zoom, rect.y0 * zoom, rect.x1 * zoom, rect.y1 * zoom


def scene_to_pdf_point(x: float, y: float, zoom: float) -> Point:
    return x / zoom, y / zoom


def pdf_to_scene_point(x: float, y: float, zoom: float) -> Point:
    return x * zoom, y * zoom


def scene_to_pdf_polygon(pts: list[Point], zoom: float) -> list[Point]:
    return [scene_to_pdf_point(x, y, zoom) for x, y in pts]


# --- PDF point <-> crop 픽셀 (OCR 입출력) ---

def pdf_len_to_crop_px(length_pt: float, dpi: int) -> float:
    return length_pt * dpi / 72.0


def crop_px_to_pdf(x_px: float, y_px: float, clip: fitz.Rect, dpi: int,
                   pad_px: int = 0) -> Point:
    """OCR 결과(crop 픽셀, 패딩 포함) -> PDF point.

    crop 이미지는 clip 영역을 dpi 로 렌더한 뒤 pad_px 만큼 흰 패딩을 두른 것이다.
    """
    scale = 72.0 / dpi
    return (clip.x0 + (x_px - pad_px) * scale,
            clip.y0 + (y_px - pad_px) * scale)


def crop_polygon_to_pdf(poly_px: list[Point], clip: fitz.Rect, dpi: int,
                        pad_px: int = 0) -> list[Point]:
    return [crop_px_to_pdf(x, y, clip, dpi, pad_px) for x, y in poly_px]


def pdf_to_crop_polygon(poly_pt: list[Point], clip: fitz.Rect, dpi: int,
                        pad_px: int = 0) -> list[Point]:
    """PDF point 폴리곤 -> crop 픽셀 폴리곤 (마스킹용)."""
    scale = dpi / 72.0
    return [((x - clip.x0) * scale + pad_px, (y - clip.y0) * scale + pad_px)
            for x, y in poly_pt]


# --- 폴리곤 유틸 ---

def polygon_bbox(pts: list[Point]) -> fitz.Rect:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return fitz.Rect(min(xs), min(ys), max(xs), max(ys))


def point_in_polygon(x: float, y: float, pts: list[Point]) -> bool:
    """ray casting. 명세 §4.3 — 단어 중심점 판정에 사용."""
    inside = False
    n = len(pts)
    j = n - 1
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > y) != (yj > y):
            x_cross = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < x_cross:
                inside = not inside
        j = i
    return inside


EMPTY = fitz.Rect(0, 0, 0, 0)


def clamp_rect(rect: fitz.Rect, bounds: fitz.Rect) -> fitz.Rect:
    """페이지 밖으로 나간 선택을 페이지 안으로 자른다. 겹치는 곳이 없으면 빈 사각형.

    ⚠ 자른 뒤에 normalize() 를 부르면 안 된다. 페이지 밖 선택은 자르고 나면
    x0 > x1 이 되는데, normalize() 가 좌표를 맞바꿔 '페이지 안의 엉뚱한 사각형'으로
    되살려 놓는다. 그 사각형은 아무것도 지우지 않으면서 검증은 통과한다
    (지운 줄 알았는데 그대로인 파일이 저장된다 — 이 도구에서 가장 나쁜 실패다).
    """
    r = fitz.Rect(rect)
    r.normalize()   # 뒤집어 그린 드래그를 바로잡는 건 자르기 '전'이다
    r = fitz.Rect(max(r.x0, bounds.x0), max(r.y0, bounds.y0),
                  min(r.x1, bounds.x1), min(r.y1, bounds.y1))
    if r.x0 >= r.x1 or r.y0 >= r.y1:
        return fitz.Rect(EMPTY)
    return r
