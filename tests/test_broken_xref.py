"""xref 표에 구멍이 뚫린 PDF 도 파괴된다.

trailer /Size 는 크게 적어놓고 xref 구획에서는 일부 번호를 빼먹은 PDF 가 실제로
돌아다닌다 (WPS Office 로 만든 42쪽 매뉴얼에서 확인 — 604 중 62개 번호가 표에 없다).
보기·인쇄에는 지장이 없어 사용자에게는 멀쩡한 문서인데, PyMuPDF 의 scrub() 이
xref 를 1번부터 끝까지 훑으며 모든 번호를 읽으려다 죽는다.
"""
import fitz
import pytest

from app.core import redactor

SECRET = "secret"


def _gap_pdf(path) -> str:
    """6·7번이 어느 xref 구획에도 없는 1쪽짜리 PDF. 8번은 구멍 뒤에 둔다 —
    그래야 xref 길이가 9 로 잡혀 6·7 이 '있다고 하는데 없는' 번호가 된다."""
    stream = b"BT /F1 12 Tf 20 100 Td (%s) Tj ET\n" % SECRET.encode()
    objs = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>"),
        4: b"<< /Length %d >>\nstream\n%sendstream" % (len(stream), stream),
        5: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        8: b"<< /Type /Metadata /Note (unused) >>",
    }
    body = b"%PDF-1.7\n"
    off = {}
    for num in sorted(objs):
        off[num] = len(body)
        body += b"%d 0 obj\n" % num + objs[num] + b"\nendobj\n"

    xstart = len(body)
    xref = b"xref\n0 6\n0000000000 65535 f \n"
    for num in (1, 2, 3, 4, 5):
        xref += b"%010d 00000 n \n" % off[num]
    xref += b"8 1\n%010d 00000 n \n" % off[8]        # 6·7 을 건너뛴다
    body += xref + b"trailer\n<< /Size 9 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % xstart

    p = str(path / "gap.pdf")
    with open(p, "wb") as f:
        f.write(body)
    return p


def test_gap_pdf_really_has_the_defect(tmp_path):
    """재현 자체가 유효한지 — 여기가 깨지면 아래 테스트는 아무것도 지키지 않는다."""
    src = _gap_pdf(tmp_path)
    doc = fitz.open(src)
    try:
        assert doc.page_count == 1
        assert SECRET in doc[0].get_text()      # 사용자에겐 멀쩡한 문서다
        missing = []
        for x in range(1, doc.xref_length()):
            try:
                doc.xref_object(x, compressed=True)
            except Exception:
                missing.append(x)
        assert missing == [6, 7], f"의도한 구멍이 안 뚫렸다: {missing}"
    finally:
        doc.close()


def test_redact_survives_xref_gap(tmp_path):
    src = _gap_pdf(tmp_path)
    dst = str(tmp_path / "out.pdf")
    rep = redactor.redact(src, {0: [fitz.Rect(0, 80, 200, 120)]}, dst)
    assert rep.ok, rep.summary()

    out = fitz.open(dst)
    try:
        assert SECRET not in out[0].get_text(), "글자가 남았다"
        for x in range(1, out.xref_length()):
            out.xref_object(x, compressed=True)   # 결과물에는 구멍이 없어야 한다
    finally:
        out.close()


def test_library_failure_names_the_step(tmp_path, monkeypatch):
    """고칠 수 없는 라이브러리 오류는 단계 이름과 원문을 함께 올린다."""
    src = _gap_pdf(tmp_path)

    def boom(*a, **k):
        raise RuntimeError("code=7: cannot find object in xref (6 0 R)")

    monkeypatch.setattr(fitz.Document, "scrub", boom)
    monkeypatch.setattr(fitz.Document, "tobytes", boom)
    with pytest.raises(RuntimeError) as ei:
        redactor.redact(src, {0: [fitz.Rect(0, 80, 200, 120)]},
                        str(tmp_path / "out.pdf"))
    msg = str(ei.value)
    assert "문서 정리" in msg, msg          # 어느 단계인지
    assert "저장하지 않았습니다" in msg, msg  # 파일이 남았는지
    assert "code=7" in msg, msg            # 원문은 문의용으로 남긴다
    assert ei.value.__cause__ is not None   # UI 가 '자세히' 여부를 이걸로 가른다
