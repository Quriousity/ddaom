"""리댁션 + 메타데이터 제거 + 저장 후 검증 (명세 §4.5).

원칙:
- 사각형을 덮는 건 파괴가 아니다 — apply_redactions 만이 파괴다.
- 스캔 PDF 는 images=PDF_REDACT_IMAGE_PIXELS 가 실제 파괴를 담당하는 유일한 인자다.
- 원본은 절대 덮어쓰지 않는다. incremental=False 로 새 파일 저장.
- 검증이 기능의 일부다: 저장본을 다시 열어 확인하고 결과를 돌려준다.
"""
from __future__ import annotations

import os
import stat
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


def save_blocker(dst_path: str) -> str | None:
    """저장을 막을 이유가 있으면 사람이 읽을 진단으로, 없으면 None.

    파괴를 다 해놓고 마지막 저장에서 실패하면 사용자는 이유를 알 수 없다.
    미리 물어보고, 실패한 뒤에도 같은 문장으로 설명한다.

    진단만 돌려준다 — 해결책은 부르는 쪽 맥락에 따라 다르다 (저장 대화상자에선
    "다른 폴더를 고르세요", 파일을 여는 시점엔 "권한을 주고 다시 여세요").
    """
    d = os.path.dirname(os.path.abspath(dst_path)) or "."
    if not os.path.isdir(d):
        return f"폴더가 없습니다:\n{d}"
    if not os.access(d, os.W_OK):
        return f"이 폴더에는 쓸 수 없습니다 (읽기 전용):\n{d}"
    if os.path.exists(dst_path) and not os.access(dst_path, os.W_OK):
        return f"같은 이름의 파일을 덮어쓸 수 없습니다:\n{dst_path}"
    return None


def fixable_dir(dst_path: str) -> str | None:
    """쓰기 권한만 켜면 풀리는 폴더면 그 경로를, 아니면 None.

    내가 소유자여야 chmod 가 먹는다 — 남의 폴더나 읽기전용 볼륨은 손대봐야 소용없다.
    """
    d = os.path.dirname(os.path.abspath(dst_path)) or "."
    if not os.path.isdir(d) or os.access(d, os.W_OK):
        return None
    try:
        if os.stat(d).st_uid != os.getuid():
            return None
    except OSError:
        return None
    return d


def grant_write(dir_path: str) -> None:
    """소유자 쓰기 비트(u+w)만 켠다.

    재귀하지 않고, 다른 사용자·그룹 권한은 건드리지 않는다 — 문제를 푸는 데
    필요한 최소한만 바꾼다.
    """
    mode = os.stat(dir_path).st_mode
    os.chmod(dir_path, mode | stat.S_IWUSR)
    if not os.access(dir_path, os.W_OK):
        raise PermissionError(f"권한을 바꿨지만 여전히 쓸 수 없습니다:\n{dir_path}")


def _save(doc, dst_path: str, **kw) -> None:
    """PyMuPDF 는 저장 실패를 메시지 없는 예외로 흘리기도 한다 (FzErrorSystem
    생성 자체가 TypeError 로 터진다). 무슨 일이 있어도 읽을 수 있는 오류로 바꾼다."""
    try:
        doc.save(dst_path, **kw)
    except Exception as e:
        why = save_blocker(dst_path) or "경로와 디스크 여유 공간을 확인하세요."
        raise OSError(f"저장할 수 없습니다.\n\n{why}\n\n"
                      f"다른 폴더를 골라 다시 시도하세요.\n(원인: {e!r})") from e


def _to_rect(sel: Selection) -> fitz.Rect:
    """폴리곤은 bbox 로 근사 — 넘치게 지운다 = 안전한 방향."""
    if isinstance(sel, fitz.Rect):
        return fitz.Rect(sel)
    return coords.polygon_bbox(sel)


def _plan(doc, selections: dict[int, list[Selection]]) -> dict[int, list[fitz.Rect]]:
    """선택을 페이지별 사각형으로 접는다. 하나라도 못 지우면 시작하지 않는다.

    조용히 버리면 안 된다: 버려진 선택은 파괴되지 않는데, 검증은 '지정한 영역 안의
    잔여'만 보므로 아무 일도 없었던 파일이 OK 로 저장된다.
    """
    if not selections:
        raise ValueError("지울 영역이 없습니다.")
    plan: dict[int, list[fitz.Rect]] = {}
    bad: list[str] = []
    for page_no, sels in selections.items():
        if not (0 <= page_no < doc.page_count):
            bad.append(f"{page_no + 1}쪽은 이 문서에 없습니다")
            continue
        page_rect = doc[page_no].rect
        for i, s in enumerate(sels):
            r = coords.clamp_rect(_to_rect(s), page_rect)
            if r.is_empty:
                bad.append(f"{page_no + 1}쪽 {i + 1}번째 선택이 페이지 밖입니다")
                continue
            plan.setdefault(page_no, []).append(r)
    if bad:
        raise ValueError("지울 수 없는 선택이 있어 중단했습니다 — "
                         "아무것도 저장하지 않았습니다.\n\n" + "\n".join(bad[:10]))
    if not plan:
        raise ValueError("지울 영역이 없습니다.")
    return plan


def _fill_leftover(page, rect: fitz.Rect, fill: tuple) -> str:
    """파괴 영역이 fill 색으로 덮였는가 — 글자층이 없는 스캔본은 이것만이 증거다."""
    clip = coords.clamp_rect(fitz.Rect(rect), page.rect)
    if clip.is_empty:
        return ""
    sample = page.get_pixmap(clip=clip, dpi=36, alpha=False)
    n = sample.width * sample.height
    if n == 0:
        return ""
    expect = tuple(int(c * 255) for c in fill)
    bad = sum(1 for i in range(n)
              if sample.pixel(i % sample.width, i // sample.width) != expect)
    if bad > n * 0.02:   # 2% 초과로 fill 색이 아니면 실패
        return f"파괴 영역에 원본 픽셀 잔존 의심 ({bad}/{n})"
    return ""


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

        # 1) 무엇을 지울지 먼저 확정한다 — 못 지울 선택이 있으면 손대기 전에 멈춘다
        rect_map = _plan(doc, selections)

        # 2) 잔여정보 일괄 정리 (첨부·JS·폼필드·주석·XMP 등)
        doc.scrub()

        # 3) 리댁션 — 페이지당 apply_redactions 는 한 번만 (§9)
        for page_no, rects in rect_map.items():
            page = doc[page_no]
            for r in rects:
                page.add_redact_annot(r, fill=fill)
            applied = page.apply_redactions(
                images=fitz.PDF_REDACT_IMAGE_PIXELS,       # 스캔본 파괴의 핵심
                graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
                text=fitz.PDF_REDACT_TEXT_REMOVE,
            )
            if applied is False:   # 무동작을 조용히 넘기지 않는다
                raise RuntimeError(
                    f"{page_no + 1}쪽 리댁션이 적용되지 않았습니다 — 저장하지 않았습니다.")

        # 4) 남은 주석·링크 제거 + 메타데이터 제거
        for page in doc:
            for annot in list(page.annots() or []):
                page.delete_annot(annot)
            for link in list(page.get_links()):
                page.delete_link(link)
        doc.set_metadata({})
        doc.del_xml_metadata()

        # 5) 새 파일 저장 — 증분 저장하면 원본이 파일 안에 남는다
        _save(doc, dst_path, garbage=4, clean=True, deflate=True,
              incremental=False, encryption=fitz.PDF_ENCRYPT_NONE)
    finally:
        doc.close()

    return _verify(dst_path, rect_map, fill)


def redact_image(src_path: str, selections: dict[int, list[Selection]],
                 dst_path: str,
                 fill: tuple = config.REDACT_FILL_COLOR) -> RedactionReport:
    """이미지 원본 파괴: 메모리 PDF 로 감싸 픽셀 파괴 후 PNG 로 재렌더.

    결과가 평탄한 래스터라 숨은 레이어가 있을 수 없고, 재렌더라 EXIF 등
    메타데이터도 함께 소멸한다.
    """
    if dst_path == src_path:
        raise ValueError("원본 덮어쓰기 금지 — 다른 경로를 지정하라")

    img = fitz.open(src_path)
    pdf_bytes = img.convert_to_pdf()
    img.close()
    doc = fitz.open("pdf", pdf_bytes)
    try:
        rect_map = _plan(doc, selections)
        for page_no, rects in rect_map.items():
            page = doc[page_no]
            for r in rects:
                page.add_redact_annot(r, fill=fill)
            applied = page.apply_redactions(
                images=fitz.PDF_REDACT_IMAGE_PIXELS,
                graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
                text=fitz.PDF_REDACT_TEXT_REMOVE)
            if applied is False:
                raise RuntimeError(
                    f"{page_no + 1}쪽 리댁션이 적용되지 않았습니다 — 저장하지 않았습니다.")
        # 원본 픽셀 해상도로 재렌더 (이미지 dpi 메타데이터에 따라 pt/px 비율이 다르다)
        src_pix = fitz.Pixmap(src_path)
        out_dpi = max(1, round(72 * src_pix.width / doc[0].rect.width))
        src_pix = None
        pix = doc[0].get_pixmap(dpi=out_dpi, alpha=False)
        _save(pix, dst_path)
    finally:
        doc.close()

    # 검증: 결과를 다시 열어 파괴 영역이 fill 색으로 칠해졌는지 확인
    out = fitz.open(dst_path)
    try:
        leftover: dict[int, str] = {}
        page = out[0]
        for r in rect_map.get(0, []):
            msg = _fill_leftover(page, r, fill)
            if msg:
                leftover[0] = msg
        return RedactionReport(ok=not leftover, dst_path=dst_path,
                               pages_redacted=len(rect_map), leftover_text=leftover)
    finally:
        out.close()


def _verify(dst_path: str, rect_map: dict[int, list[fitz.Rect]],
            fill: tuple = config.REDACT_FILL_COLOR) -> RedactionReport:
    """저장본을 다시 열어 (a) 영역 텍스트 0건 (b) 영역이 fill 색 (c) 메타데이터 0 (§4.5).

    (b) 가 없으면 스캔본은 사실상 무검증이다 — 글자층이 없으니 (a) 는 언제나 통과한다.
    """
    doc = fitz.open(dst_path)
    try:
        leftover: dict[int, str] = {}
        for page_no, rects in rect_map.items():
            page = doc[page_no]
            for r in rects:
                txt = page.get_text("text", clip=r).strip()
                if txt:
                    leftover[page_no] = leftover.get(page_no, "") + txt
                px = _fill_leftover(page, r, fill)
                if px:
                    leftover[page_no] = leftover.get(page_no, "") + px
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
