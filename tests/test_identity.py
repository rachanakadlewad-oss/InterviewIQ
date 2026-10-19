import json

import pytest

from app.schemas import IdentityResult
from app.services import identity as idsvc


def raw(count, conf, thr=0.7, inconclusive=False):
    return IdentityResult(timestamp="t", backend="x", face_count=count, match_confidence=conf, threshold=thr,
                          inconclusive=inconclusive)


def test_gate_passes_only_with_single_face_and_confidence():
    assert idsvc.evaluate(raw(1, 0.9)).passed
    assert not idsvc.evaluate(raw(0, 0.9)).passed
    assert not idsvc.evaluate(raw(2, 0.99)).passed
    assert not idsvc.evaluate(raw(1, 0.69)).passed
    assert idsvc.evaluate(raw(1, 0.7)).passed                         # boundary: >= threshold


def test_inconclusive_never_passes():
    assert not idsvc.evaluate(raw(1, 0.99, inconclusive=True)).passed


def test_failure_reasons_are_specific():
    assert "no face" in idsvc.evaluate(raw(0, 0)).reason
    assert "2 faces" in idsvc.evaluate(raw(2, 0.9)).reason
    assert "below threshold" in idsvc.evaluate(raw(1, 0.1)).reason


def test_demo_scenarios(settings):
    out = {sc: idsvc.verify_identity(settings, None, b"", sc) for sc in idsvc.SCENARIOS}
    assert out["match"].passed
    for sc in ("no_face", "multiple_faces", "different_person", "swap_mid_session"):
        assert not out[sc].passed, sc
    assert all(r.is_real_biometric is False and "DEMO" in r.warning for r in out.values())


def test_unknown_scenario_is_inconclusive_fail_not_exception(settings):
    r = idsvc.verify_identity(settings, None, b"", "bogus")
    assert not r.passed and r.inconclusive


def test_backend_exception_is_safe_failure(settings):
    class Boom:
        name = "boom"
        def verify(self, *a, **k):
            raise RuntimeError("camera exploded")
    r = idsvc.verify_identity(settings, None, b"x", backend=Boom())
    assert not r.passed and r.inconclusive and "camera exploded" in r.reason


def test_opencv_backend_rejects_unreadable_and_missing_inputs(settings, tmp_path):
    settings.identity_backend = "opencv_basic"
    ref = tmp_path / "ref.img"
    ref.write_bytes(b"not an image")
    r = idsvc.verify_identity(settings, str(ref), b"not an image either")
    assert not r.passed and r.inconclusive
    r2 = idsvc.verify_identity(settings, None, b"x")                      # no reference photo
    assert not r2.passed and "reference" in r2.reason


def test_opencv_no_face_image_fails(settings, tmp_path):
    import cv2
    import numpy as np
    blank = np.full((300, 300, 3), 128, np.uint8)
    ok, buf = cv2.imencode(".png", blank)
    settings.identity_backend = "opencv_basic"
    ref = tmp_path / "ref.img"
    ref.write_bytes(buf.tobytes())
    r = idsvc.verify_identity(settings, str(ref), buf.tobytes())
    assert not r.passed                                   # reference has no face -> inconclusive fail


def test_identity_log_file_appends(settings):
    r = idsvc.verify_identity(settings, None, b"", "match")
    idsvc.append_identity_log(settings, 7, r)
    idsvc.append_identity_log(settings, 7, r)
    p = settings.subdir("identity_logs") / "identity_log_7.json"
    entries = json.loads(p.read_text())
    assert len(entries) == 2 and {"timestamp", "match_confidence", "passed"} <= set(entries[0])


def test_photo_deletion(tmp_path):
    p = tmp_path / "x.img"
    p.write_bytes(b"1")
    assert idsvc.delete_photo(str(p)) is True and not p.exists()
    assert idsvc.delete_photo(str(p)) is False and idsvc.delete_photo(None) is False
