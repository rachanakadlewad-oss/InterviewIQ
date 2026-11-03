with open('interviewiq/app/agents/base.py', 'r', encoding='utf-8') as f:
    content = f.read()

target = """    error_note = ""
    last_err = "unknown"
    attempts = max_retries + 1
    for attempt in range(1, attempts + 1):
        try:
            raw = llm.complete(system + "\\n" + INJECTION_NOTE, base_user + error_note)
            out = out_model.model_validate(extract_json(raw))
            if semantic_check:
                semantic_check(out)
            log.info("%s: valid output on attempt %d", name, attempt)
            return AgentResult(out, "llm", attempt)
        except LLMError as e:           # service failure: back off, retry
            last_err = f"service error: {e}"
            log.warning("%s attempt %d service failure: %s", name, attempt, e)
            sleep_time = (backoff or 0.5) * attempt
            err_str = str(e)
            if "429" in err_str or "too many requests" in err_str.lower() or "rate" in err_str.lower():
                m = re.search(r"try again in (\\d+\\.?\\d*)\\s*s", err_str, re.IGNORECASE)
                if m:
                    sleep_time = float(m.group(1)) + 0.5
                else:
                    sleep_time = max(sleep_time, 4.0 * attempt)
            if sleep_time:
                time.sleep(sleep_time)
        except (ValidationError, ValueError) as e:   # invalid output: tell the model what was wrong
            last_err = f"invalid output: {e}"
            log.warning("%s attempt %d invalid: %s", name, attempt, e)
            error_note = f"\\n\\nYour previous reply was rejected: {str(e)[:600]}\\nFix it and reply with valid JSON only."
    raise AgentError(f"{name} failed after {attempts} attempts ({last_err})")"""

repl = """    error_note = ""
    last_err = "unknown"
    max_attempts = max(max_retries + 1, 4)
    attempt = 0
    while attempt < max_attempts:
        attempt += 1
        try:
            raw = llm.complete(system + "\\n" + INJECTION_NOTE, base_user + error_note)
            out = out_model.model_validate(extract_json(raw))
            if semantic_check:
                semantic_check(out)
            log.info("%s: valid output on attempt %d", name, attempt)
            return AgentResult(out, "llm", attempt)
        except LLMError as e:           # service failure: back off, retry
            last_err = f"service error: {e}"
            log.warning("%s attempt %d service failure: %s", name, attempt, e)
            sleep_time = (backoff or 0.5) * attempt
            status_code = getattr(e, "status_code", 0)
            retry_after = getattr(e, "retry_after", 0.0)
            err_str = str(e)
            is_rate_limit = (status_code == 429) or (retry_after > 0) or ("429" in err_str) or ("too many requests" in err_str.lower()) or ("rate" in err_str.lower())
            if is_rate_limit:
                if retry_after > 0:
                    sleep_time = retry_after + 0.5
                else:
                    m = re.search(r"try again in (\\d+\\.?\\d*)\\s*s", err_str, re.IGNORECASE)
                    if m:
                        sleep_time = float(m.group(1)) + 0.5
                    else:
                        sleep_time = max(sleep_time, 3.0 * attempt)
                log.warning("[RateLimit] %s: rate-limited by provider. Sleeping for %.2fs before attempt %d/%d...", name, sleep_time, attempt + 1, max_attempts)
            if sleep_time and attempt < max_attempts:
                time.sleep(sleep_time)
        except (ValidationError, ValueError) as e:   # invalid output: tell the model what was wrong
            last_err = f"invalid output: {e}"
            log.warning("%s attempt %d invalid: %s", name, attempt, e)
            error_note = f"\\n\\nYour previous reply was rejected: {str(e)[:600]}\\nFix it and reply with valid JSON only."
    raise AgentError(f"{name} failed after {max_attempts} attempts ({last_err})")"""

assert target in content, "target not found in base.py"
new_content = content.replace(target, repl, 1)
with open('interviewiq/app/agents/base.py', 'w', encoding='utf-8') as f:
    f.write(new_content)
print("Updated interviewiq/app/agents/base.py successfully")
