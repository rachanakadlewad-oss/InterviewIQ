import re

with open('interviewiq/app/llm/client.py', 'r', encoding='utf-8') as f:
    content = f.read()

target1 = """class LLMError(Exception):
    \"\"\"Transport / provider failure (timeout, HTTP error, empty response).\"\"\""""

repl1 = """class LLMError(Exception):
    \"\"\"Transport / provider failure (timeout, HTTP error, empty response).\"\"\"
    def __init__(self, message: str, status_code: int = 0, retry_after: float = 0.0):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after"""

target2 = """            if not r.ok:
                detail = r.text[:300]
                raise LLMError(f\"HTTP {r.status_code} ({r.reason}) calling {self.base_url}/chat/completions [model={self.model}]: {detail}\")"""

repl2 = """            if not r.ok:
                detail = r.text[:400]
                retry_after = 0.0
                if r.status_code == 429:
                    ra_hdr = r.headers.get("retry-after")
                    if ra_hdr:
                        try:
                            retry_after = float(ra_hdr)
                        except ValueError:
                            pass
                    if not retry_after:
                        m = re.search(r"try again in (\\d+\\.?\\d*)\\s*s", detail, re.IGNORECASE)
                        if m:
                            retry_after = float(m.group(1))
                raise LLMError(
                    f"HTTP {r.status_code} ({r.reason}) calling {self.base_url}/chat/completions [model={self.model}]: {detail}",
                    status_code=r.status_code,
                    retry_after=retry_after,
                )"""

assert target1 in content, "target1 not found"
assert target2 in content, "target2 not found"
new_content = content.replace(target1, repl1, 1).replace(target2, repl2, 1)
with open('interviewiq/app/llm/client.py', 'w', encoding='utf-8') as f:
    f.write(new_content)
print("Updated interviewiq/app/llm/client.py successfully")
