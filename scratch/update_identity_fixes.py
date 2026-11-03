# 1. Update app/schemas.py
with open('app/schemas.py', 'r', encoding='utf-8') as f:
    s_txt = f.read()

old_id_result = '''class IdentityResult(BaseModel):
    timestamp: str
    check_type: str = "pre_interview"      # pre_interview | mid_session
    backend: str
    is_real_biometric: bool = False
    face_detected: bool = False
    face_count: int = 0
    single_face: bool = False
    match_confidence: float = 0.0
    threshold: float = 0.7
    passed: bool = False
    inconclusive: bool = False
    reason: str = ""
    warning: str = ""'''

new_id_result = '''class IdentityResult(BaseModel):
    timestamp: str
    check_type: str = "pre_interview"      # pre_interview | mid_session
    backend: str
    is_real_biometric: bool = False
    face_detected: bool = False
    face_count: int = 0
    single_face: bool = False
    match_confidence: float = 0.0
    threshold: float = 0.7
    passed: bool = False
    inconclusive: bool = False
    reason: str = ""
    warning: str = ""
    human_override: bool = False'''

assert old_id_result in s_txt, 'old_id_result not found in app/schemas.py'
s_txt = s_txt.replace(old_id_result, new_id_result)
with open('app/schemas.py', 'w', encoding='utf-8') as f:
    f.write(s_txt)
print('Updated app/schemas.py')

# 2. Update app/workflow/supervisor.py
with open('app/workflow/supervisor.py', 'r', encoding='utf-8') as f:
    sup_txt = f.read()

old_sup_pass = '''            self.db.add(IdentityCheckRow(application_id=a.id, check_type="human_review", backend="human_reviewer",
                                         passed=True, human_override=True, reason=f"manual pass: {notes}",
                                         confidence=0.0, threshold=self.s.identity_match_threshold))
            idsvc.append_identity_log(self.s, a.id, IdentityResult(
                timestamp=idsvc._now(), check_type="human_review", backend="human_reviewer", passed=True,
                reason=f"HUMAN OVERRIDE: {notes}", threshold=self.s.identity_match_threshold, face_count=1, face_detected=True, single_face=True))'''

new_sup_pass = '''            self.db.add(IdentityCheckRow(application_id=a.id, check_type="human_review", backend="human_reviewer",
                                         passed=True, human_override=True, reason=f"manual pass: {notes}",
                                         confidence=0.0, threshold=self.s.identity_match_threshold))
            idsvc.append_identity_log(self.s, a.id, IdentityResult(
                timestamp=idsvc._now(), check_type="human_review", backend="human_reviewer", passed=True,
                human_override=True, reason=f"HUMAN OVERRIDE: {notes}",
                threshold=self.s.identity_match_threshold, face_count=1, face_detected=True, single_face=True))'''

assert old_sup_pass in sup_txt, 'old_sup_pass not found in app/workflow/supervisor.py'
sup_txt = sup_txt.replace(old_sup_pass, new_sup_pass)
with open('app/workflow/supervisor.py', 'w', encoding='utf-8') as f:
    f.write(sup_txt)
print('Updated app/workflow/supervisor.py')

# 3. Update frontend/iqui/views/identity_review.py
with open('frontend/iqui/views/identity_review.py', 'r', encoding='utf-8') as f:
    id_txt = f.read()

old_table_loop = '''    rows = []
    for c in checks:
        is_pass = c.get("passed", False)
        is_inconcl = c.get("inconclusive", False)
        is_override = c.get("human_override", False)

        if is_override:
            res_b = C.badge("Manual Pass", "success") if is_pass else C.badge("Manual Decision", "neutral")
        elif is_pass:
            res_b = C.badge("Passed", "success")
        elif is_inconcl:
            res_b = C.badge("Inconclusive", "warning")
        else:
            res_b = C.badge("Failed", "error")

        rows.append({
            "t": H.fmt_dt(c.get("timestamp")),
            "type": (c.get("check_type") or "check").replace("_", " ").title(),
            "backend": c.get("backend", "-"),
            "faces": str(c.get("face_count", 0)),
            "conf": f"{c.get('confidence', 0.0):.2f} / {c.get('threshold', 0.0):.2f}" if not is_override else "-",
            "res": res_b,
            "why": c.get("reason", "-")
        })'''

new_table_loop = '''    rows = []
    for c in checks:
        is_pass = c.get("passed", False)
        is_inconcl = c.get("inconclusive", False)
        is_override = bool(
            c.get("human_override")
            or c.get("backend") == "human_reviewer"
            or c.get("check_type") == "human_review"
            or "OVERRIDE" in str(c.get("reason", "")).upper()
        )

        conf_num = c.get("confidence") if c.get("confidence") is not None else c.get("match_confidence", 0.0)

        if is_override:
            res_b = C.badge("Manual Pass", "success") if is_pass else C.badge("Manual Decision", "neutral")
            conf_display = "Manual Override (N/A)"
        elif is_pass:
            res_b = C.badge("Passed", "success")
            conf_display = f"{conf_num:.2f} / {c.get('threshold', 0.0):.2f}"
        elif is_inconcl:
            res_b = C.badge("Inconclusive", "warning")
            conf_display = f"{conf_num:.2f} / {c.get('threshold', 0.0):.2f}"
        else:
            res_b = C.badge("Failed", "error")
            conf_display = f"{conf_num:.2f} / {c.get('threshold', 0.0):.2f}"

        rows.append({
            "t": H.fmt_dt(c.get("timestamp")),
            "type": (c.get("check_type") or "check").replace("_", " ").title(),
            "backend": "Recruiter Override" if is_override else c.get("backend", "-"),
            "faces": str(c.get("face_count", 0)),
            "conf": conf_display,
            "res": res_b,
            "why": c.get("reason", "-")
        })'''

old_passed = '''            verified_time = H.fmt_dt(latest_check["timestamp"]) if latest_check else "-"
            conf_display = f"{latest_check.get('confidence', 0.0):.2f} (min: {latest_check.get('threshold', threshold):.2f})" if latest_check and not is_override else "Manual Pass"'''

new_passed = '''            verified_time = H.fmt_dt(latest_check["timestamp"]) if latest_check else "-"
            conf_num = latest_check.get("confidence") if latest_check and latest_check.get("confidence") is not None else (latest_check.get("match_confidence", 0.0) if latest_check else 0.0)
            conf_display = "Manual Override (N/A)" if is_override else f"{conf_num:.2f} (min: {latest_check.get('threshold', threshold):.2f})"'''

assert old_table_loop in id_txt, 'old_table_loop not found in identity_review.py'
assert old_passed in id_txt, 'old_passed not found in identity_review.py'

id_txt = id_txt.replace(old_table_loop, new_table_loop).replace(old_passed, new_passed)
with open('frontend/iqui/views/identity_review.py', 'w', encoding='utf-8') as f:
    f.write(id_txt)
print('Updated frontend/iqui/views/identity_review.py')
