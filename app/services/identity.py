"""Identity verification gate.

BACKENDS
  demo          DEMO ADAPTER. The outcome is chosen by an explicit 'scenario' parameter. It performs NO biometric
                analysis and every result is labelled is_real_biometric=False with a warning.
  opencv_basic  Real face DETECTION (OpenCV Haar cascade) + a WEAK similarity score (grid LBP-histogram
                intersection between the reference photo and the live frame). It is far less accurate than
                modern face-embedding models; not biometric grade. Upgrade path: swap in InsightFace / DeepFace
                behind the same FaceBackend interface.

GATE RULE (deterministic): passed = face_detected AND single_face AND match_confidence >= threshold.
Anything else - including backend errors, missing reference photo, unreadable image - is a FAIL
(inconclusive=True when we could not decide) and is routed to the human review queue.
Only scores/metadata are logged; live frames are never stored."""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.schemas import IdentityResult

log = logging.getLogger(__name__)
DEMO_WARNING = "DEMO ADAPTER - outcome selected by scenario; this is NOT biometric verification."
BASIC_WARNING = "Basic OpenCV heuristic (Haar + LBP histogram) - not biometric grade; human review recommended."
SCENARIOS = ["match", "no_face", "multiple_faces", "different_person", "swap_mid_session"]


class IdentityBackendError(Exception):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def evaluate(r: IdentityResult) -> IdentityResult:
    """Apply the hard gate rule to a raw backend result."""
    r.single_face = r.face_count == 1
    r.face_detected = r.face_count >= 1
    r.passed = bool(r.face_detected and r.single_face and r.match_confidence >= r.threshold and not r.inconclusive)
    if not r.reason:
        if r.passed:
            r.reason = "face detected, single face, confidence above threshold"
        elif not r.face_detected:
            r.reason = "no face detected"
        elif not r.single_face:
            r.reason = f"{r.face_count} faces detected (exactly one required)"
        else:
            r.reason = f"match confidence {r.match_confidence:.2f} below threshold {r.threshold:.2f}"
    return r


class DemoBackend:
    name = "demo_adapter"

    def verify(self, reference: Optional[bytes], live: Optional[bytes], scenario: str, check_type: str, threshold: float):
        scenario = scenario or "match"
        table = {"match": (1, 0.93), "no_face": (0, 0.0), "multiple_faces": (2, 0.88),
                 "different_person": (1, 0.21), "swap_mid_session": (1, 0.18)}
        if scenario not in table:
            raise IdentityBackendError(f"unknown demo scenario {scenario!r}")
        n, conf = table[scenario]
        return IdentityResult(timestamp=_now(), check_type=check_type, backend=self.name, is_real_biometric=False,
                              face_count=n, match_confidence=conf, threshold=threshold, warning=DEMO_WARNING)


class OpenCVBasicBackend:
    name = "opencv_basic"

    def __init__(self):
        import cv2
        self.cv2 = cv2
        self.cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_alt2.xml")
        if self.cascade.empty():
            raise IdentityBackendError("could not load Haar cascade")

    def _faces(self, data: bytes):
        import numpy as np
        img = self.cv2.imdecode(np.frombuffer(data, np.uint8), self.cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise IdentityBackendError("unreadable image")
        faces = self.cascade.detectMultiScale(img, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
        return img, list(faces)

    def _descriptor(self, img, box):
        import numpy as np
        x, y, w, h = box
        face = self.cv2.resize(img[y:y + h, x:x + w], (96, 96))
        face = self.cv2.equalizeHist(face)
        c = face[1:-1, 1:-1].astype(np.int16)
        code = np.zeros_like(c, dtype=np.uint8)
        for bit, (dy, dx) in enumerate([(-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1)]):
            nb = face[1 + dy:95 + dy, 1 + dx:95 + dx].astype(np.int16)
            code |= ((nb >= c).astype(np.uint8) << bit)
        cells = []
        for gy in range(4):
            for gx in range(4):
                blk = code[gy * 23:(gy + 1) * 23 + 1, gx * 23:(gx + 1) * 23 + 1]
                hist = np.bincount(blk.ravel() >> 2, minlength=64).astype(float)  # 64-bin coarse LBP
                cells.append(hist / max(hist.sum(), 1))
        return np.array(cells)

    def verify(self, reference, live, scenario, check_type, threshold):
        if not live:
            raise IdentityBackendError("no live frame supplied")
        if not reference:
            raise IdentityBackendError("no reference photo available for this candidate")
        _, ref_faces = self._faces(reference)
        if len(ref_faces) != 1:
            raise IdentityBackendError(f"reference photo must contain exactly one face (found {len(ref_faces)})")
        live_img, live_faces = self._faces(live)
        ref_img, _ = self._faces(reference)
        conf = 0.0
        if len(live_faces) >= 1:
            biggest = max(live_faces, key=lambda b: b[2] * b[3])
            a, b = self._descriptor(ref_img, ref_faces[0]), self._descriptor(live_img, biggest)
            import numpy as np
            conf = float(np.minimum(a, b).sum(axis=1).mean())   # histogram intersection, 0..1
        return IdentityResult(timestamp=_now(), check_type=check_type, backend=self.name, is_real_biometric=False,
                              face_count=len(live_faces), match_confidence=round(conf, 3), threshold=threshold,
                              warning=BASIC_WARNING)


def get_backend(settings):
    if settings.identity_backend == "opencv_basic":
        return OpenCVBasicBackend()
    return DemoBackend()


def verify_identity(settings, reference_path: Optional[str], live_bytes: Optional[bytes], scenario: Optional[str] = None,
                    check_type: str = "pre_interview", backend=None) -> IdentityResult:
    """Run one identity check. NEVER raises: failures become inconclusive FAIL results (safe default)."""
    thr = settings.identity_match_threshold
    try:
        backend = backend or get_backend(settings)
        ref = Path(reference_path).read_bytes() if reference_path and Path(reference_path).exists() else None
        res = backend.verify(ref, live_bytes, scenario, check_type, thr)
        return evaluate(res)
    except Exception as e:
        log.warning("identity check inconclusive: %s", e)
        r = IdentityResult(timestamp=_now(), check_type=check_type, backend=getattr(backend, "name", settings.identity_backend),
                           threshold=thr, inconclusive=True, reason=f"inconclusive: {e}",
                           warning="Check could not be completed; routed to human review.")
        return evaluate(r)


def append_identity_log(settings, application_id: int, result: IdentityResult) -> Path:
    """identity_log_<id>.json - JSON list; one entry per check with timestamp + confidence."""
    p = settings.subdir("identity_logs") / f"identity_log_{application_id}.json"
    entries = json.loads(p.read_text()) if p.exists() else []
    entries.append(result.model_dump(mode="json"))
    p.write_text(json.dumps(entries, indent=2))
    return p


def read_identity_log(settings, application_id: int) -> list:
    p = settings.subdir("identity_logs") / f"identity_log_{application_id}.json"
    return json.loads(p.read_text()) if p.exists() else []


def delete_photo(path: Optional[str]) -> bool:
    """Data minimisation: remove the reference photo once it is no longer needed."""
    if path and Path(path).exists():
        Path(path).unlink()
        return True
    return False
