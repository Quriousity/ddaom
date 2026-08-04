"""이 문서로 무엇을 할 수 있는가 — 열 때 판정한다.

세 갈래다:
  ① 못 읽는다        → 열지 않는다
  ② 읽지만 못 지운다  → 열되, 복사·이미지 저장만
  ③ 다 된다          → 경고 없이 조용히 연다

저장 직전에야 파괴 불가를 알게 되면 이미 늦다 — 그때 사용자는 지울 것을 다 골라놓은
뒤다. 그래서 문 앞에서 묻는다. 여기서 통과해도 저장은 실패할 수 있고, 그때는
redactor._save 가 읽을 수 있는 오류로 받아준다 (두 겹).
"""
from __future__ import annotations

from dataclasses import dataclass

from . import redactor
from .document import Document


@dataclass
class Capability:
    can_read: bool
    can_destroy: bool
    read_error: str = ""      # 못 읽는 이유
    destroy_error: str = ""   # 읽을 수는 있으나 파괴 못 하는 이유

    @property
    def silent(self) -> bool:
        """경고 없이 열어도 되는가."""
        return self.can_read and self.can_destroy


def probe(doc: Document, default_dst: str) -> Capability:
    """default_dst = 파괴 결과가 저장될 기본 경로 (원본 옆). 이름 규칙은 UI 몫이다."""
    if doc.page_count < 1:
        return Capability(False, False, read_error="페이지가 없는 문서입니다.")
    try:
        # 열리기만 하고 못 그리는 파일이 있다 — 작게 한 장 실제로 그려본다
        doc.render_thumb_png(0, 24)
    except Exception as e:
        return Capability(False, False,
                          read_error=f"페이지를 그릴 수 없습니다 — 손상된 파일로 보입니다.\n\n({e})")

    # 파괴는 언제나 '원본 옆에 새 파일 쓰기'다. 쓸 수 없으면 파괴도 없다.
    blocker = redactor.save_blocker(default_dst)
    if blocker:
        return Capability(True, False, destroy_error=blocker)
    return Capability(True, True)
