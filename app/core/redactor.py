"""리댁션 + 메타데이터 제거 + 저장 후 검증 (명세 §4.5).

원칙:
- 사각형을 덮는 건 파괴가 아니다 — apply_redactions 만이 파괴다.
- 스캔 PDF 는 images=PDF_REDACT_IMAGE_PIXELS 가 실제 파괴를 담당하는 유일한 인자다.
- 원본은 절대 덮어쓰지 않는다. incremental=False 로 새 파일 저장.
- 검증이 기능의 일부다: 저장본을 다시 열어 확인하고 결과를 돌려준다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import fitz

from .. import config
from . import coords

Point = tuple[float, float]

# 페이지별 선택: rect 는 fitz.Rect, polygon 은 [(x,y), ...] — 모두 PDF point
Selection = fitz.Rect | list


@dataclass
class RedactionReport:
    ok: bool
    dst_path: str
    pages_redacted: int
    leftover_text: dict[int, str] = field(default_factory=dict)  # page_no -> 남은 텍스트
    metadata_left: dict = field(default_factory=dict)
    xmp_left: bool = False

    def summary(self) -> str:
        if self.ok:
            return (f"OK — {self.pages_redacted}개 페이지 리댁션, "
                    f"잔여 텍스트 0건, 메타데이터 없음\n→ {self.dst_path}")
        parts = []
        if self.leftover_text:
            parts.append(f"⚠ 잔여 텍스트 발견: {self.leftover_text}")
        if self.metadata_left:
            parts.append(f"⚠ 메타데이터 잔존: {self.metadata_left}")
        if self.xmp_left:
            parts.append("⚠ XMP 잔존")
        return "\n".join(parts) or "⚠ 알 수 없는 실패"


def _to_rect(sel: Selection) -> fitz.Rect:
    """폴리곤은 bbox 로 근사 — 넘치게 지운다 = 안전한 방향."""
    if isinstance(sel, fitz.Rect):
        return fitz.Rect(sel)
    return coords.polygon_bbox(sel)


def redact(src_path: str, selections: dict[int, list[Selection]], dst_path: str,
           password: str | None = None,
           fill: tuple = config.REDACT_FILL_COLOR) -> RedactionReport:
    """selections: {page_no: [Rect | polygon, ...]} (PDF point)."""
    if dst_path == src_path:
        raise ValueError("원본 덮어쓰기 금지 — 다른 경로를 지정하라")

    doc = fitz.open(src_path)
    try:
        if doc.needs_pass:
            if not password or not doc.authenticate(password):
                raise PermissionError("암호를 풀 수 없는 문서는 리댁션할 수 없다")

        # 1) 잔여정보 일괄 정리 (첨부·JS·폼필드·주석·XMP 등)
        doc.scrub()

        # 2) 리댁션 — 페이지당 apply_redactions 는 한 번만 (§9)
        rect_map: dict[int, list[fitz.Rect]] = {}
        for page_no, sels in selections.items():
            rects = [coords.clamp_rect(_to_rect(s), doc[page_no].rect) for s in sels]
            rects = [r for r in rects if not r.is_empty]
            if rects:
                rect_map[page_no] = rects

        for page_no, rects in rect_map.items():
            page = doc[page_no]
            for r in rects:
                page.add_redact_annot(r, fill=fill)
            page.apply_redactions(
                images=fitz.PDF_REDACT_IMAGE_PIXELS,       # 스캔본 파괴의 핵심
                graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
                text=fitz.PDF_REDACT_TEXT_REMOVE,
            )

        # 3) 남은 주석·링크 제거 + 메타데이터 제거
        for page in doc:
            for annot in list(page.annots() or []):
                page.delete_annot(annot)
            for link in list(page.get_links()):
                page.delete_link(link)
        doc.set_metadata({})
        doc.del_xml_metadata()

        # 4) 새 파일 저장 — 증분 저장하면 원본이 파일 안에 남는다
        doc.save(dst_path, garbage=4, clean=True, deflate=True,
                 incremental=False, encryption=fitz.PDF_ENCRYPT_NONE)
    finally:
        doc.close()

    return _verify(dst_path, rect_map)


def _verify(dst_path: str, rect_map: dict[int, list[fitz.Rect]]) -> RedactionReport:
    """저장본을 다시 열어 (a) 리댁션 영역 텍스트 0건 (b) 메타데이터 0 을 확인 (§4.5)."""
    doc = fitz.open(dst_path)
    try:
        leftover: dict[int, str] = {}
        for page_no, rects in rect_map.items():
            page = doc[page_no]
            for r in rects:
                txt = page.get_text("text", clip=r).strip()
                if txt:
                    leftover[page_no] = leftover.get(page_no, "") + txt
        meta_left = {k: v for k, v in (doc.metadata or {}).items()
                     if v and k not in ("format", "encryption")}
        xmp_left = False
        try:
            xmp = doc.get_xml_metadata()
            xmp_left = bool(xmp and xmp.strip())
        except Exception:
            pass
        ok = not leftover and not meta_left and not xmp_left
        return RedactionReport(ok=ok, dst_path=dst_path,
                               pages_redacted=len(rect_map),
                               leftover_text=leftover,
                               metadata_left=meta_left, xmp_left=xmp_left)
    finally:
        doc.close()
