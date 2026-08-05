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
    # 잔존 사유는 종류별로 나눠 담는다 — 글자가 남은 것과 픽셀이 안 덮인 것은
    # 원인도 대응도 다르다. 한 자루에 섞으면 픽셀 문제가 '잔여 텍스트'로 보고된다.
    leftover_text: dict[int, list[str]] = field(default_factory=dict)    # page_no -> 남은 글자
    leftover_pixels: dict[int, list[str]] = field(default_factory=dict)  # page_no -> "224/224"
    metadata_left: dict = field(default_factory=dict)
    xmp_left: bool = False
    traces_left: dict[str, int] = field(default_factory=dict)     # 이름 -> 남은 개수
    traces_removed: dict[str, int] = field(default_factory=dict)  # 이름 -> 지운 개수

    def summary(self) -> str:
        if self.ok:
            head = (f"OK — {self.pages_redacted}개 페이지 리댁션, "
                    f"잔여 텍스트 0건, 메타데이터 없음")
            # 무엇을 함께 잃었는지 알린다 — 조용히 사라지는 게 제일 나쁘다
            if self.traces_removed:
                head += "\n함께 제거됨: " + ", ".join(
                    f"{k} {v}개" for k, v in sorted(self.traces_removed.items()))
            return f"{head}\n→ {self.dst_path}"
        parts = []
        if self.leftover_text:
            parts.append("⚠ 파괴 영역에 글자가 남았습니다:")
            for page_no, items in sorted(self.leftover_text.items()):
                parts.append(f"  · {page_no + 1}쪽 — " + " / ".join(items))
        if self.leftover_pixels:
            parts.append("⚠ 파괴 영역이 덮이지 않았습니다 (덮이지 않은 픽셀/전체):")
            for page_no, items in sorted(self.leftover_pixels.items()):
                parts.append(f"  · {page_no + 1}쪽 — " + ", ".join(items))
        if self.metadata_left:
            parts.append(f"⚠ 메타데이터 잔존: {self.metadata_left}")
        if self.xmp_left:
            parts.append("⚠ XMP 잔존")
        for name, n in sorted(self.traces_left.items()):
            parts.append(f"⚠ {name} 잔존: {n}개")
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


def _lib(step: str, fn, *args, **kwargs):
    """PyMuPDF 호출 한 단계 — 라이브러리 원문 오류를 사람이 읽을 문장으로 바꾼다.

    원문만 띄우면(예: "code=7: cannot find object in xref (359 0 R)") 사용자는
    무엇이 실패했는지도, 파일이 저장됐는지도 알 수 없다. 단계 이름과 저장 여부를
    붙이고 원문은 문의용으로 괄호에 남긴다 (_save 와 같은 방식).
    """
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        raise RuntimeError(
            f"{step} 단계에서 문서를 처리하지 못했습니다 — 아무것도 저장하지 않았습니다.\n\n"
            f"이 프로그램이 다루지 못하는 형태의 PDF 일 수 있습니다.\n"
            f"(원인: {e})") from e


def _scrub(doc):
    """잔여정보 일괄 정리(첨부·JS·폼필드·주석·XMP). 실패하면 한 번만 고쳐 재시도한다.

    scrub() 은 xref 를 1번부터 xref_length()-1 까지 훑으며 모든 번호의 객체를 읽는데,
    표에 실리지 않은 번호가 있으면 거기서 죽는다. trailer /Size 는 크게 적어놓고
    xref 구획에서는 일부 번호를 빼먹은 PDF 가 실제로 돌아다닌다. 보기·인쇄에는
    지장이 없어서 사용자에게는 멀쩡한 문서다 — 파괴만 못 하면 곤란하다.

    고치는 방법은 문서를 한 번 다시 쓰는 것이다. 디스크가 아니라 메모리에서 한다 —
    파괴 전 원본을 임시 파일로 떨구면 그것 자체가 유출이다.

    건너뛰지는 않는다: scrub() 은 JS·첨부파일·폼필드를 지우는 실제 파괴 작업이라
    생략하면 잔여물이 남은 파일이 OK 로 저장된다.
    """
    try:
        doc.scrub()
        return doc
    except RuntimeError:
        pass
    buf = _lib("문서 정리", doc.tobytes, garbage=3, clean=True, deflate=True,
               encryption=fitz.PDF_ENCRYPT_NONE)
    fresh = fitz.open("pdf", buf)
    try:
        _lib("잔여정보 제거", fresh.scrub)
    except Exception:
        fresh.close()
        raise
    doc.close()   # 새 문서가 자리 잡은 뒤에 닫는다 (실패했다면 부르는 쪽이 원본을 닫는다)
    return fresh


def _strip_extras(doc) -> None:
    """리댁션 뒤 정리 — 남은 주석·링크와 메타데이터·XMP."""
    for page in doc:
        for annot in list(page.annots() or []):
            page.delete_annot(annot)
        for link in list(page.get_links()):
            page.delete_link(link)
    doc.set_metadata({})
    doc.del_xml_metadata()


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


def _annot_rect(page, rect: fitz.Rect) -> fitz.Rect:
    """표시 좌표 -> 주석 좌표. 회전된 페이지에서만 실제로 달라진다.

    page.rect·get_pixmap·get_text 는 /Rotate 를 반영한 '보이는 대로'의 좌표를 쓰지만,
    주석은 회전 전 좌표로 들어간다. 화면에서 고른 사각형을 그대로 넣으면 엉뚱한 데가
    파괴된다 (180도면 정확히 반대편, 90/270도면 가로세로가 뒤바뀐 자리).

    검증은 표시 좌표 그대로 봐야 하므로 변환은 주석을 다는 이 순간에만 한다.
    """
    if not page.rotation:
        return rect
    r = fitz.Rect(rect) * page.derotation_matrix
    r.normalize()
    return r


def _apply(page, rects: list[fitz.Rect], fill: tuple) -> None:
    """한 페이지의 리댁션 — 주석을 달고 apply_redactions 는 한 번만 (§9)."""
    for r in rects:
        page.add_redact_annot(_annot_rect(page, r), fill=fill)
    applied = _lib(
        f"{page.number + 1}쪽 파괴", page.apply_redactions,
        images=fitz.PDF_REDACT_IMAGE_PIXELS,       # 스캔본 파괴의 핵심
        graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
        text=fitz.PDF_REDACT_TEXT_REMOVE,
    )
    if applied is False:   # 무동작을 조용히 넘기지 않는다
        raise RuntimeError(
            f"{page.number + 1}쪽 리댁션이 적용되지 않았습니다 — 저장하지 않았습니다.")


def _pieceinfo_xrefs(doc) -> list[int]:
    """/PieceInfo 를 가진 객체 전부. 카탈로그·페이지뿐 아니라 폼 XObject 에도 붙는다.

    범위를 좁히면 청소가 닿지 않은 곳을 검증이 잡아 사용자가 손쓸 수 없는 실패가
    난다 — 청소와 검증은 같은 범위를 봐야 한다.
    """
    out = []
    for xref in range(1, doc.xref_length()):
        try:
            if doc.xref_get_key(xref, "PieceInfo")[0] != "null":
                out.append(xref)
        except Exception:
            continue   # 해제된 xref 등 — 읽을 수 없으면 가진 것도 없다
    return out


def _strip_traces(doc) -> dict[str, int]:
    """scrub() 도 garbage=4 도 걷어내지 못하는 흔적을 지우고, 지운 개수를 돌려준다.

    - 책갈피(Outlines): 제목에 이름이 들어가는 일이 흔한데 scrub() 대상이 아니다.
    - /PieceInfo: 편집 프로그램의 비공개 데이터. 참조가 살아 있어 garbage 수집을
      피해 간다. 콘텐츠 스트림이 참조하지 않으므로 지워도 렌더는 그대로다.
    """
    removed: dict[str, int] = {}
    n = len(doc.get_toc(simple=True))
    if n:
        doc.set_toc([])
        removed["책갈피"] = n
    xrefs = _pieceinfo_xrefs(doc)
    for xref in xrefs:
        doc.xref_set_key(xref, "PieceInfo", "null")
    if xrefs:
        removed["PieceInfo"] = len(xrefs)
    return removed


def _leftover_traces(doc) -> dict[str, int]:
    """_strip_traces 가 지웠어야 할 것이 저장본에 남았는가 (같은 범위로 본다)."""
    left: dict[str, int] = {}
    n = len(doc.get_toc(simple=True))
    if n:
        left["책갈피"] = n
    n = len(_pieceinfo_xrefs(doc))
    if n:
        left["PieceInfo"] = n
    return left


def _unfilled(page, rect: fitz.Rect, fill: tuple) -> str:
    """파괴 영역이 fill 색으로 덮였는가 — 글자층이 없는 스캔본은 이것만이 증거다.

    덮이지 않았으면 "224/224" 꼴로, 덮였으면 빈 문자열.
    """
    clip = coords.clamp_rect(fitz.Rect(rect), page.rect)
    if clip.is_empty:
        return ""
    sample = page.get_pixmap(clip=clip, dpi=36, alpha=False)
    w, h = sample.width, sample.height
    # 표본의 바깥 한 겹은 사각형 경계에 걸쳐 있어 바깥 내용과 섞인다. 문서에 남은
    # 것이 아니라 렌더링 경계라서, 온전히 영역 안에 있는 픽셀만 센다. 이걸 세면
    # 제대로 덮인 영역이 테두리만으로 2% 를 넘겨 실패로 뜬다 (작은 영역일수록 심하다).
    x0, y0, x1, y1 = (1, 1, w - 1, h - 1) if w > 2 and h > 2 else (0, 0, w, h)
    n = (x1 - x0) * (y1 - y0)
    if n == 0:
        return ""
    expect = tuple(int(c * 255) for c in fill)
    bad = sum(1 for y in range(y0, y1) for x in range(x0, x1)
              if sample.pixel(x, y) != expect)
    if bad > n * 0.02:   # 2% 초과로 fill 색이 아니면 실패
        return f"{bad}/{n}"
    return ""


def _leftover_text(page, rect: fitz.Rect) -> str:
    """파괴 영역에 남은 글자. 스치기만 한 이웃 줄은 세지 않는다.

    get_text(clip=…) 은 사각형에 조금이라도 걸친 글자를 다 돌려주는데,
    apply_redactions 는 그런 글자를 지우지 않는다. 검증이 파괴보다 엄격하면
    제대로 지워진 문서가 실패로 뜬다 — 줄 간격이 촘촘한 표에서 특히 그렇다.

    글자 중심이 영역 안에 있는 것만 잔존으로 본다 (단어 판정과 같은 규칙, §4.3).
    파괴 대상이었던 글자는 통째로 영역 안이므로 이 규칙으로 빠져나가지 못한다.
    """
    out: list[str] = []
    d = page.get_text("rawdict", clip=rect)
    for block in d.get("blocks", []):
        if block.get("type") != 0:   # 이미지 블록은 픽셀 검사가 맡는다
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                for ch in span.get("chars", []):
                    x0, y0, x1, y1 = ch["bbox"]
                    if rect.contains(fitz.Point((x0 + x1) / 2, (y0 + y1) / 2)):
                        out.append(ch["c"])
    return "".join(out).strip()


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
        doc = _scrub(doc)   # 문서가 바뀔 수 있다 — 아래는 새 문서를 쓴다

        # 3) 리댁션 — 페이지당 apply_redactions 는 한 번만 (§9)
        for page_no, rects in rect_map.items():
            _apply(doc[page_no], rects, fill)

        # 4) 남은 주석·링크 제거 + 메타데이터 제거
        _lib("주석·메타데이터 제거", _strip_extras, doc)
        removed = _lib("흔적 제거", _strip_traces, doc)  # scrub() 이 놓치는 것들

        # 5) 새 파일 저장 — 증분 저장하면 원본이 파일 안에 남는다
        _save(doc, dst_path, garbage=4, clean=True, deflate=True,
              incremental=False, encryption=fitz.PDF_ENCRYPT_NONE)
    finally:
        doc.close()

    # 여기서부터는 파일이 이미 디스크에 있다 — 실패해도 '저장 안 됨' 이라고 하면 안 된다
    try:
        return _verify(dst_path, rect_map, fill, removed)
    except Exception as e:
        raise RuntimeError(
            f"파괴한 파일은 저장됐지만 검증하지 못했습니다.\n\n{dst_path}\n\n"
            f"제대로 파괴됐는지 확인되지 않았습니다 — 파일을 직접 열어 확인하세요.\n"
            f"(원인: {e})") from e


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
            _apply(doc[page_no], rects, fill)
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
        unfilled: dict[int, list[str]] = {}
        page = out[0]
        for r in rect_map.get(0, []):
            ratio = _unfilled(page, r, fill)
            if ratio:
                unfilled.setdefault(0, []).append(ratio)
        return RedactionReport(ok=not unfilled, dst_path=dst_path,
                               pages_redacted=len(rect_map), leftover_pixels=unfilled)
    finally:
        out.close()


def _verify(dst_path: str, rect_map: dict[int, list[fitz.Rect]],
            fill: tuple = config.REDACT_FILL_COLOR,
            removed: dict[str, int] | None = None) -> RedactionReport:
    """저장본을 다시 열어 (a) 영역 텍스트 0건 (b) 영역이 fill 색 (c) 메타데이터 0 (§4.5)
    (d) 책갈피·PieceInfo 0건.

    (b) 가 없으면 스캔본은 사실상 무검증이다 — 글자층이 없으니 (a) 는 언제나 통과한다.
    """
    doc = fitz.open(dst_path)
    try:
        leftover: dict[int, list[str]] = {}
        unfilled: dict[int, list[str]] = {}
        for page_no, rects in rect_map.items():
            page = doc[page_no]
            for r in rects:
                txt = _leftover_text(page, r)
                if txt:
                    leftover.setdefault(page_no, []).append(txt)
                ratio = _unfilled(page, r, fill)
                if ratio:
                    unfilled.setdefault(page_no, []).append(ratio)
        meta_left = {k: v for k, v in (doc.metadata or {}).items()
                     if v and k not in ("format", "encryption")}
        xmp_left = False
        try:
            xmp = doc.get_xml_metadata()
            xmp_left = bool(xmp and xmp.strip())
        except Exception:
            pass
        traces_left = _leftover_traces(doc)
        ok = (not leftover and not unfilled and not meta_left and not xmp_left
              and not traces_left)
        return RedactionReport(ok=ok, dst_path=dst_path,
                               pages_redacted=len(rect_map),
                               leftover_text=leftover, leftover_pixels=unfilled,
                               metadata_left=meta_left, xmp_left=xmp_left,
                               traces_left=traces_left,
                               traces_removed=dict(removed or {}))
    finally:
        doc.close()
