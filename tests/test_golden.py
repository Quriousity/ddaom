"""골든 회귀 테스트 (명세 §8 완료 기준 + §14).

의존성을 올리든 엔진을 갈든, 이 파일 통과 = 생존 판정.
실행: .venv/bin/python -m pytest tests/ -v
"""
import os

import fitz
import pytest

from app import config
from app.core import coords, extractor, redactor
from app.core.document import Document, NeedsPassword, BadPassword
from tools.make_samples import LINES, SECRET, OUT

SAMPLES = OUT


@pytest.fixture(scope="session", autouse=True)
def ensure_samples():
    if not os.path.exists(os.path.join(SAMPLES, "text.pdf")):
        from tools import make_samples
        make_samples.main()


@pytest.fixture(scope="session")
def text_doc():
    d = Document(os.path.join(SAMPLES, "text.pdf"))
    yield d
    d.close()


@pytest.fixture(scope="session")
def scan_doc():
    d = Document(os.path.join(SAMPLES, "scan.pdf"))
    yield d
    d.close()


# ---------- §8-1: 텍스트 PDF 는 OCR 없이 정확히 ----------

class TestTextLayer:
    def test_full_page_rect(self, text_doc):
        rect = text_doc.page_rect(0)
        text, source = extractor.extract_text(text_doc, 0, rect=rect)
        assert source == "text-layer"
        for line in LINES:
            assert line in text
        assert SECRET in text

    def test_partial_rect_only_one_line(self, text_doc):
        # "합계금액 1,234,567원" 줄만 (y=180 근처, fontsize 14)
        rect = fitz.Rect(60, 165, 400, 195)
        text, source = extractor.extract_text(text_doc, 0, rect=rect)
        assert source == "text-layer"
        assert "1,234,567" in text
        assert "김철수" not in text

    def test_polygon_selection(self, text_doc):
        # 위쪽 두 줄을 덮는 폴리곤
        poly = [(60, 80), (500, 80), (500, 155), (60, 155)]
        text, source = extractor.extract_text(text_doc, 0, polygon=poly)
        assert source == "text-layer"
        assert "김철수" in text
        assert "1,234,567" not in text

    def test_empty_region(self, text_doc):
        rect = fitz.Rect(400, 700, 550, 800)  # 빈 영역
        text, source = extractor.extract_text(text_doc, 0, rect=rect)
        assert text == "" or source == "ocr"  # 글자층 없음 -> OCR 폴백, 결과도 빈 것 허용


# ---------- §8-2: 스캔 PDF 는 OCR 로 한국어/영어/숫자 ----------

class TestOCRFallback:
    def test_scan_full_page(self, scan_doc):
        rect = scan_doc.page_rect(0)
        text, source = extractor.extract_text(scan_doc, 0, rect=rect)
        assert source == "ocr"
        assert "김철수" in text
        assert "123-45-67890" in text
        assert "1,234,567" in text.replace(" ", "")

    def test_scan_single_line_fast_path(self, scan_doc):
        # 스캔본에서 "합계금액 1,234,567원" 줄만: 150dpi 렌더 기준 y=368~410px
        # -> PDF pt: 페이지 595x842, 이미지 1240x1754 => scale 595/1240
        s = 595 / 1240
        rect = fitz.Rect(140 * s, 360 * s, 700 * s, 420 * s)
        text, source = extractor.extract_text(scan_doc, 0, rect=rect)
        assert source == "ocr"
        assert "1,234,567" in text.replace(" ", "")

    def test_scan_polygon(self, scan_doc):
        s = 595 / 1240
        poly = [(140 * s, 190 * s), (900 * s, 190 * s),
                (900 * s, 330 * s), (140 * s, 330 * s)]
        text, source = extractor.extract_text(scan_doc, 0, polygon=poly)
        assert source == "ocr"
        assert "김철수" in text


# ---------- §8-3: 줌 배율과 무관한 좌표 ----------

class TestCoords:
    def test_zoom_roundtrip(self):
        for zoom in (0.5, 1.0, 1.7, 3.2):
            r = coords.scene_to_pdf_rect(100 * zoom, 50 * zoom, 300 * zoom, 200 * zoom, zoom)
            assert abs(r.x0 - 100) < 1e-6 and abs(r.y1 - 200) < 1e-6

    def test_crop_roundtrip(self):
        clip = fitz.Rect(72, 100, 300, 200)
        poly_pt = [(80, 110), (250, 110), (250, 180), (80, 180)]
        px = coords.pdf_to_crop_polygon(poly_pt, clip, 300, pad_px=10)
        back = coords.crop_polygon_to_pdf(px, clip, 300, pad_px=10)
        for (ax, ay), (bx, by) in zip(poly_pt, back):
            assert abs(ax - bx) < 1e-6 and abs(ay - by) < 1e-6

    def test_point_in_polygon(self):
        sq = [(0, 0), (10, 0), (10, 10), (0, 10)]
        assert coords.point_in_polygon(5, 5, sq)
        assert not coords.point_in_polygon(15, 5, sq)

    def test_rotated_page_extraction(self):
        # 회전 페이지: page.rect 기준 좌표로 추출이 성립해야 한다 (§9 최다 버그)
        d = Document(os.path.join(SAMPLES, "rotated.pdf"))
        try:
            page = d.page(0)
            assert page.rotation == 90
            rect = page.rect  # 회전 반영된 표시 공간
            text, source = extractor.extract_text(d, 0, rect=rect)
            assert source == "text-layer"
            for line in LINES:
                assert line in text
            # 부분 선택: 단어 하나를 words 좌표로 집어 그 좌표로 다시 추출
            words = page.get_text("words")
            target = next(w for w in words if "김철수" in w[4])
            r = fitz.Rect(target[0] - 2, target[1] - 2, target[2] + 2, target[3] + 2)
            text2, _ = extractor.extract_text(d, 0, rect=r)
            assert "김철수" in text2
        finally:
            d.close()


# ---------- §8-4/5: 리댁션 + 메타데이터 ----------

class TestRedaction:
    def test_text_pdf_redaction(self, tmp_path):
        src = os.path.join(SAMPLES, "text.pdf")
        dst = str(tmp_path / "redacted_text.pdf")
        # SECRET 줄 좌표를 글자층에서 찾는다
        d = fitz.open(src)
        rects = [fitz.Rect(w[:4]) for w in d[0].get_text("words") if "900101" in w[4]]
        d.close()
        assert rects, "SECRET 단어를 찾지 못함"
        area = rects[0] + (-5, -5, 5, 5)

        report = redactor.redact(src, {0: [area]}, dst)
        assert report.ok, report.summary()

        # 재열람 검증: 가려진 문자열이 검색되지 않는다
        d2 = fitz.open(dst)
        assert "900101" not in d2[0].get_text()
        assert not d2.search_for("900101-1234567") if hasattr(d2, "search_for") else True
        # 나머지 내용은 살아있다
        assert "김철수" in d2[0].get_text()
        # 메타데이터 0
        meta = {k: v for k, v in d2.metadata.items()
                if v and k not in ("format", "encryption")}
        assert not meta, meta
        d2.close()

    def test_scan_pdf_image_redaction(self, tmp_path):
        """스캔본: 이미지 픽셀이 실제로 파괴됐는지 — OCR 로 재검증."""
        src = os.path.join(SAMPLES, "scan.pdf")
        dst = str(tmp_path / "redacted_scan.pdf")
        s = 595 / 1240
        secret_rect = fitz.Rect(140 * s, 1030 * s, 900 * s, 1100 * s)

        report = redactor.redact(src, {0: [secret_rect]}, dst)
        assert report.ok, report.summary()

        d2 = Document(dst)
        try:
            text, _ = extractor.extract_text(d2, 0, rect=d2.page_rect(0))
            assert "900101" not in text.replace(" ", "")
            assert "김철수" in text  # 다른 내용은 생존
        finally:
            d2.close()

    def test_polygon_redaction_bbox_approx(self, tmp_path):
        src = os.path.join(SAMPLES, "text.pdf")
        dst = str(tmp_path / "redacted_poly.pdf")
        d = fitz.open(src)
        w = next(w for w in d[0].get_text("words") if "900101" in w[4])
        d.close()
        poly = [(w[0] - 3, w[1] - 3), (w[2] + 3, w[1] - 3),
                (w[2] + 3, w[3] + 3), (w[0] - 3, w[3] + 3)]
        report = redactor.redact(src, {0: [poly]}, dst)
        assert report.ok, report.summary()

    def test_refuses_overwrite(self):
        src = os.path.join(SAMPLES, "text.pdf")
        with pytest.raises(ValueError):
            redactor.redact(src, {0: []}, src)


# ---------- 암호화 PDF ----------

class TestEncrypted:
    def test_needs_password(self):
        with pytest.raises(NeedsPassword):
            Document(os.path.join(SAMPLES, "encrypted.pdf"))

    def test_bad_password(self):
        with pytest.raises(BadPassword):
            Document(os.path.join(SAMPLES, "encrypted.pdf"), password="wrong")

    def test_good_password(self):
        d = Document(os.path.join(SAMPLES, "encrypted.pdf"), password="test123")
        try:
            text, _ = extractor.extract_text(d, 0, rect=d.page_rect(0))
            assert LINES[0] in text
        finally:
            d.close()


# ---------- 이미지 추출 (§4.4) ----------

class TestImageExtract:
    def test_rect_export_dpi(self, text_doc):
        rect = fitz.Rect(60, 80, 500, 300)
        img = extractor.extract_image(text_doc, 0, rect=rect, dpi=300)
        # 300dpi: pt * 300/72
        assert abs(img.width - (500 - 60) * 300 / 72) <= 2
        assert img.mode == "RGB"

    def test_polygon_masked_white(self, text_doc):
        poly = [(60, 80), (500, 80), (280, 300)]
        img = extractor.extract_image(text_doc, 0, polygon=poly, dpi=150)
        # 폴리곤 밖(우하단 모서리)은 흰색
        assert img.getpixel((img.width - 1, img.height - 1)) == (255, 255, 255)

    def test_polygon_transparent(self, text_doc):
        poly = [(60, 80), (500, 80), (280, 300)]
        img = extractor.extract_image(text_doc, 0, polygon=poly, dpi=150,
                                      transparent_outside=True)
        assert img.mode == "RGBA"
        assert img.getpixel((img.width - 1, img.height - 1))[3] == 0


# ---------- 후처리 ----------

class TestPostprocess:
    def test_hyphen_join(self):
        assert extractor.postprocess("compli-\nance") == "compliance"

    def test_korean_hyphen_kept(self):
        assert "110-234" in extractor.postprocess("계좌 110-234\n다음줄")

    def test_line_grouping_order(self):
        words = [(50, 10, 80, 20, "B"), (10, 10, 40, 20, "A"), (10, 40, 40, 50, "C")]
        assert extractor.group_words_into_lines(words) == "A B\nC"
