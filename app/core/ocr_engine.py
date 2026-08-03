"""OCR 백엔드 추상화 (명세 §4.6).

계약: run() 은 텍스트·폴리곤(crop 픽셀)·점수를 함께 반환한다.
텍스트만 반환하면 라인 그룹핑(§4.2)이 불가능하다.
구현체는 RapidOCR 하나 — 래퍼가 죽어도 이 파일만 갈아끼우면 된다 (§14).
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from .. import config


@dataclass
class OCRLine:
    polygon: list[tuple[float, float]]  # 4점, crop 이미지 픽셀 좌표 (§4.1-4)
    text: str
    score: float


class OCREngine(Protocol):
    def preload(self) -> None: ...

    def run(self, img: np.ndarray, single_line: bool = False) -> list[OCRLine]: ...


class RapidOCREngine:
    """rapidocr-onnxruntime + 번들 PP-OCRv5 한국어 모델.

    엔진 인스턴스는 프로세스 수명 동안 상주 (§4.6 콜드스타트 제거).
    """

    def __init__(self):
        self._ocr = None
        self._lock = threading.Lock()

    def preload(self) -> None:
        with self._lock:
            if self._ocr is None:
                from rapidocr_onnxruntime import RapidOCR

                # 세 경로 모두 명시 — 생략 시 일부 버전이 런타임 다운로드를 시도한다 (§2.1)
                self._ocr = RapidOCR(
                    det_model_path=config.OCR_DET_MODEL,
                    rec_model_path=config.OCR_REC_MODEL,
                    rec_keys_path=config.OCR_REC_KEYS,
                    intra_op_num_threads=config.OCR_THREADS,
                )

    @property
    def ready(self) -> bool:
        return self._ocr is not None

    def run(self, img: np.ndarray, single_line: bool = False) -> list[OCRLine]:
        self.preload()
        h, w = img.shape[:2]
        if single_line:
            # det 생략 — 사용자가 이미 영역을 지정했다 (§4.2.2)
            result, _ = self._ocr(img, use_det=False, use_cls=False)
            lines = []
            for item in result or []:
                text, score = item[0], float(item[1])
                if text:
                    # 폴리곤 = 이미지 전체 (라인 그룹핑은 항등 연산이 된다)
                    lines.append(OCRLine(
                        polygon=[(0.0, 0.0), (float(w), 0.0), (float(w), float(h)), (0.0, float(h))],
                        text=text, score=score))
            return lines

        result, _ = self._ocr(img)
        lines = []
        for box, text, score in result or []:
            if text:
                lines.append(OCRLine(
                    polygon=[(float(x), float(y)) for x, y in box],
                    text=text, score=float(score)))
        return lines


_default_engine: RapidOCREngine | None = None
_default_lock = threading.Lock()


def default_engine() -> RapidOCREngine:
    global _default_engine
    with _default_lock:
        if _default_engine is None:
            _default_engine = RapidOCREngine()
        return _default_engine
