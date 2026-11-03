with open('frontend/iqui/helpers.py', 'r', encoding='utf-8') as f:
    h_txt = f.read()

old_curr_idx = '''    curr_idx = {
        "PARSED": 0, "SCORING_FAILED": 0, "SCORED": 0, "SHORTLISTED": 0,
        "SCHEDULED": 1,
        "HUMAN_REVIEW": 1,
        "REJECTED_AT_REVIEW": 1,
        "IDENTITY_PASSED": 2,
        "INTERVIEW_IN_PROGRESS": 2,
        "INTERVIEW_COMPLETE": 3,
        "ASSESSMENT_FAILED": 3,
        "ASSESSED": 5,
        "DECIDED": 6
    }.get(status, 1)'''

new_curr_idx = '''    curr_idx = {
        "PARSED": 0, "SCORING_FAILED": 0, "SCORED": 0, "SHORTLISTED": 0,
        "SCHEDULED": 0,
        "HUMAN_REVIEW": 1,
        "REJECTED_AT_REVIEW": 1,
        "IDENTITY_PASSED": 1,
        "INTERVIEW_IN_PROGRESS": 2,
        "INTERVIEW_COMPLETE": 3,
        "ASSESSMENT_FAILED": 3,
        "ASSESSED": 4,
        "DECIDED": 5
    }.get(status, 0)'''

assert old_curr_idx in h_txt, 'old_curr_idx not found in helpers.py'
h_txt = h_txt.replace(old_curr_idx, new_curr_idx)

with open('frontend/iqui/helpers.py', 'w', encoding='utf-8') as f:
    f.write(h_txt)
print('Updated frontend/iqui/helpers.py')
