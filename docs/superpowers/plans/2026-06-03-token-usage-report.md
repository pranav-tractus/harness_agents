# Token Usage Tracking & Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture per-LLM-call token counts (input, output, cache read/write) throughout the extraction pipeline and generate a `token_report.html` alongside `report.html` showing aggregate totals, per-model breakdown, and per-chat detail — styled identically to the main report.

**Architecture:** A new `call_llm_with_usage(...)` function (same signature as `call_llm` but returns `(T, TokenUsage)`) is added alongside the existing `call_llm`. `_call_with_retry` in `core/extractor.py` switches to it and propagates a summed `TokenUsage` up to `AgentRunResult.token_usage`. The postprocess validation LLM stage likewise captures its usage. `harness/artifacts.py` serializes token fields into JSONL rows and rolls them up in `aggregate`. A new `harness/token_report_html.py` module renders the HTML using the same CSS classes. `artifacts.write_token_report()` is called at run-end from `runner.py`.

**Tech Stack:** Python 3, `instructor` 1.15.x (via `create_with_completion`), `unittest`, Chart.js (report).

---

## File Structure

- **Create:** `core/token_usage.py` — `TokenUsage` dataclass with arithmetic helpers.
- **Modify:** `core/llm_client.py` — add `call_llm_with_usage`; update internal `_call_*` functions to return `(T, TokenUsage)`.
- **Modify:** `core/extractor.py` — switch `_call_with_retry` to `call_llm_with_usage`; propagate `TokenUsage` through `ExtractionResult`.
- **Modify:** `core/db.py` — add `token_usage: dict | None` to `ExtractionResult`.
- **Modify:** `core/postprocess_stages.py` — capture validation LLM token usage in `StageResult`.
- **Modify:** `agents/base.py` — add `token_usage: dict | None` to `AgentRunResult`.
- **Modify:** `agents/so_extraction/agent.py` — collect and store token usage from extraction + validation.
- **Modify:** `harness/artifacts.py` — serialize token fields in `record_to_row`; roll up in `_summarize`; add `write_token_report`.
- **Create:** `harness/token_report_html.py` — HTML token report renderer.
- **Modify:** `harness/runner.py` — call `write_token_report` at run-end.
- **Create:** `tests/test_token_usage.py` — unit tests for `TokenUsage` and `call_llm_with_usage` dispatch.
- **Create:** `tests/test_token_report_html.py` — unit tests for the report renderer.

---

## Task 1: `TokenUsage` dataclass

**Files:**
- Create: `core/token_usage.py`
- Test: `tests/test_token_usage.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_token_usage.py
"""Unit tests for TokenUsage dataclass and call_llm_with_usage."""

from __future__ import annotations

import unittest

from core.token_usage import TokenUsage


class TestTokenUsage(unittest.TestCase):
    def test_defaults_are_zero(self):
        u = TokenUsage()
        self.assertEqual(u.input_tokens, 0)
        self.assertEqual(u.output_tokens, 0)
        self.assertEqual(u.cache_read_tokens, 0)
        self.assertEqual(u.cache_write_tokens, 0)

    def test_total_tokens(self):
        u = TokenUsage(input_tokens=100, output_tokens=50)
        self.assertEqual(u.total_tokens(), 150)

    def test_addition(self):
        a = TokenUsage(input_tokens=10, output_tokens=5, cache_read_tokens=3, cache_write_tokens=1)
        b = TokenUsage(input_tokens=20, output_tokens=8, cache_read_tokens=0, cache_write_tokens=2)
        c = a + b
        self.assertEqual(c.input_tokens, 30)
        self.assertEqual(c.output_tokens, 13)
        self.assertEqual(c.cache_read_tokens, 3)
        self.assertEqual(c.cache_write_tokens, 3)

    def test_to_dict(self):
        u = TokenUsage(input_tokens=100, output_tokens=50, cache_read_tokens=20, cache_write_tokens=5)
        d = u.to_dict()
        self.assertEqual(d["input_tokens"], 100)
        self.assertEqual(d["output_tokens"], 50)
        self.assertEqual(d["cache_read_tokens"], 20)
        self.assertEqual(d["cache_write_tokens"], 5)
        self.assertEqual(d["total_tokens"], 150)

    def test_from_dict(self):
        d = {"input_tokens": 10, "output_tokens": 5, "cache_read_tokens": 2, "cache_write_tokens": 1}
        u = TokenUsage.from_dict(d)
        self.assertEqual(u.input_tokens, 10)
        self.assertEqual(u.total_tokens(), 15)

    def test_from_dict_handles_missing_keys(self):
        u = TokenUsage.from_dict({"input_tokens": 7})
        self.assertEqual(u.input_tokens, 7)
        self.assertEqual(u.output_tokens, 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_token_usage.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.token_usage'`.

- [ ] **Step 3: Create `core/token_usage.py`**

```python
# core/token_usage.py
"""Lightweight token-usage counter passed through the LLM call stack."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "total_tokens": self.total_tokens(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TokenUsage":
        return cls(
            input_tokens=int(d.get("input_tokens") or 0),
            output_tokens=int(d.get("output_tokens") or 0),
            cache_read_tokens=int(d.get("cache_read_tokens") or 0),
            cache_write_tokens=int(d.get("cache_write_tokens") or 0),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_token_usage.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add core/token_usage.py tests/test_token_usage.py
git commit -m "feat: add TokenUsage dataclass"
```

---

## Task 2: Add `call_llm_with_usage` to llm_client

**Files:**
- Modify: `core/llm_client.py`
- Test: `tests/test_token_usage.py` (extend)

The strategy: each `_call_*` function is updated to use `create_with_completion` internally so it can return `(T, TokenUsage)`. A new public `call_llm_with_usage` is added. The existing `call_llm` is kept unchanged (still returns just `T`) to avoid breaking `report_summary.py`.

- [ ] **Step 1: Extend the failing test**

Append to `tests/test_token_usage.py`:

```python
class TestCallLlmWithUsage(unittest.TestCase):
    def test_returns_tuple_of_model_and_usage(self):
        from unittest.mock import MagicMock, patch

        from core.llm_client import call_llm_with_usage
        from core.models import SOExtractContractList

        fake_result = SOExtractContractList.model_validate({"data": []})
        fake_usage = {"input_tokens": 100, "output_tokens": 50, "cache_read_tokens": 0, "cache_write_tokens": 0}

        with patch("core.llm_client._call_bedrock_with_usage", return_value=(fake_result, fake_usage)):
            model, usage = call_llm_with_usage(
                "prompt",
                SOExtractContractList,
                model_key="sonnet-4-6",
            )

        self.assertIsInstance(model, SOExtractContractList)
        self.assertEqual(usage["input_tokens"], 100)
        self.assertEqual(usage["output_tokens"], 50)

    def test_call_llm_unchanged_still_returns_model_only(self):
        from unittest.mock import patch

        from core.llm_client import call_llm
        from core.models import SOExtractContractList

        fake_result = SOExtractContractList.model_validate({"data": []})

        with patch("core.llm_client._call_bedrock", return_value=fake_result):
            result = call_llm("prompt", SOExtractContractList, model_key="sonnet-4-6")

        self.assertIsInstance(result, SOExtractContractList)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_token_usage.py::TestCallLlmWithUsage -v`
Expected: FAIL — `cannot import name 'call_llm_with_usage'`.

- [ ] **Step 3: Update `core/llm_client.py`**

Read `core/llm_client.py` first, then apply all changes below.

**3a. Add import at top:**
```python
from core.token_usage import TokenUsage
```

**3b. Add `_call_bedrock_with_usage` after the existing `_call_bedrock` function:**

```python
def _call_bedrock_with_usage(
    prompt: str, schema: Type[T], model_id: str, system_prompt: str | None = None
) -> tuple[T, dict]:
    logger.info("Calling Bedrock (with usage) model=%s schema=%s", model_id, schema.__name__)
    raw_client = create_boto3_client("bedrock-runtime")
    client = instructor.from_bedrock(raw_client)
    kwargs: dict = dict(
        model=model_id,
        response_model=schema,
        max_tokens=_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    if system_prompt:
        kwargs["system"] = [{"text": system_prompt}]
    result, completion = client.messages.create_with_completion(**kwargs)
    raw_usage = completion.get("usage", {}) if isinstance(completion, dict) else {}
    usage = TokenUsage(
        input_tokens=int(raw_usage.get("inputTokens") or 0),
        output_tokens=int(raw_usage.get("outputTokens") or 0),
    ).to_dict()
    logger.info("Bedrock extraction succeeded with usage=%s", usage)
    return result, usage
```

**3c. Add `_call_openai_with_usage` after the existing `_call_openai` function:**

```python
def _call_openai_with_usage(
    prompt: str, schema: Type[T], model_id: str, system_prompt: str | None = None
) -> tuple[T, dict]:
    logger.info("Calling OpenAI (with usage) model=%s schema=%s", model_id, schema.__name__)
    client = _get_openai_client()
    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    result, completion = client.chat.completions.create_with_completion(
        model=model_id,
        response_model=schema,
        messages=messages,
    )
    raw_usage = getattr(completion, "usage", None)
    usage = TokenUsage(
        input_tokens=int(getattr(raw_usage, "prompt_tokens", 0) or 0),
        output_tokens=int(getattr(raw_usage, "completion_tokens", 0) or 0),
    ).to_dict()
    logger.info("OpenAI extraction succeeded with usage=%s", usage)
    return result, usage
```

**3d. Add `_call_anthropic_with_usage` after the existing `_call_anthropic` function (which was added in Plan 1). If Plan 1 hasn't been applied yet, add `_call_anthropic` first from that plan, then add this:**

```python
def _call_anthropic_with_usage(
    prompt: str, schema: Type[T], model_id: str, system_prompt: str | None = None
) -> tuple[T, dict]:
    logger.info("Calling Anthropic (with usage) model=%s schema=%s", model_id, schema.__name__)
    client = instructor.from_anthropic(anthropic_sdk.Anthropic())
    kwargs: dict = dict(
        model=model_id,
        response_model=schema,
        max_tokens=_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    if system_prompt:
        kwargs["system"] = system_prompt
    result, completion = client.messages.create_with_completion(**kwargs)
    raw_usage = getattr(completion, "usage", None)
    usage = TokenUsage(
        input_tokens=int(getattr(raw_usage, "input_tokens", 0) or 0),
        output_tokens=int(getattr(raw_usage, "output_tokens", 0) or 0),
        cache_read_tokens=int(getattr(raw_usage, "cache_read_input_tokens", 0) or 0),
        cache_write_tokens=int(getattr(raw_usage, "cache_creation_input_tokens", 0) or 0),
    ).to_dict()
    logger.info("Anthropic extraction succeeded with usage=%s", usage)
    return result, usage
```

**3e. Add `_call_gemini_with_usage` after the existing `_call_gemini` function:**

```python
def _call_gemini_with_usage(
    prompt: str, schema: Type[T], model_id: str, system_prompt: str | None = None
) -> tuple[T, dict]:
    logger.info("Calling Gemini (with usage) model=%s schema=%s", model_id, schema.__name__)
    instructor_model = model_id
    api_model = _gemini_model_for_api(instructor_model)
    client = _get_gemini_client(instructor_model)
    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    result, completion = client.chat.completions.create_with_completion(
        model=api_model,
        response_model=schema,
        messages=messages,
    )
    raw_usage = getattr(completion, "usage", None)
    usage = TokenUsage(
        input_tokens=int(getattr(raw_usage, "prompt_tokens", 0) or 0),
        output_tokens=int(getattr(raw_usage, "completion_tokens", 0) or 0),
    ).to_dict()
    logger.info("Gemini extraction succeeded with usage=%s", usage)
    return result, usage
```

**3f. Add `call_llm_with_usage` after the existing `call_llm` function:**

```python
def call_llm_with_usage(
    prompt: str,
    schema: Type[T],
    model_key: str,
    system_prompt: str | None = None,
) -> tuple[T, dict]:
    """Provider-aware LLM call returning (validated_model, token_usage_dict).

    Token usage dict has keys: input_tokens, output_tokens, cache_read_tokens,
    cache_write_tokens, total_tokens. All values are ints.
    """
    resolved = resolve_model_selection(model_key)
    provider = resolved["provider"]
    model_id = resolved["model_id"]
    if provider == "bedrock":
        return _call_bedrock_with_usage(prompt, schema, model_id=model_id, system_prompt=system_prompt)
    if provider == "openai":
        return _call_openai_with_usage(prompt, schema, model_id=model_id, system_prompt=system_prompt)
    if provider == "anthropic":
        return _call_anthropic_with_usage(prompt, schema, model_id=model_id, system_prompt=system_prompt)
    if provider == "gemini":
        return _call_gemini_with_usage(prompt, schema, model_id=model_id, system_prompt=system_prompt)
    raise ValueError(f"Unsupported provider '{provider}' for model_key='{model_key}'")
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_token_usage.py -v`
Expected: PASS (all tests).

Run full suite:
```bash
python -m pytest tests/ -v
```
Expected: all existing tests still pass.

- [ ] **Step 5: Commit**

```bash
git add core/llm_client.py core/token_usage.py tests/test_token_usage.py
git commit -m "feat: add call_llm_with_usage returning (model, token_usage_dict)"
```

---

## Task 3: Propagate token usage through the extractor

**Files:**
- Modify: `core/db.py` (add `token_usage` to `ExtractionResult`)
- Modify: `core/extractor.py` (switch `_call_with_retry` to `call_llm_with_usage`)
- Test: `tests/test_token_usage.py` (extend)

- [ ] **Step 1: Add `token_usage` field to `ExtractionResult` in `core/db.py`**

In `core/db.py`, add this field to the `ExtractionResult` dataclass immediately after `input_chars: int = 0`:

```python
    token_usage: dict | None = None
```

No test needed for this — it's a plain dataclass field with a default.

Verify the module still imports:
```bash
python -c "from core.db import ExtractionResult; r = ExtractionResult(input_text='x', prompt_text=None, schema_name='S', status='success', attempts=1); print(r.token_usage)"
```
Expected: `None`

- [ ] **Step 2: Extend the failing test for extractor propagation**

Append to `tests/test_token_usage.py`:

```python
class TestExtractorTokenPropagation(unittest.TestCase):
    def test_extraction_engine_run_stores_token_usage(self):
        from pathlib import Path
        from unittest.mock import MagicMock, patch

        from core.extractor import ExtractionEngine
        from core.models import SOExtractContractList

        fake_model = SOExtractContractList.model_validate({"data": []})
        fake_usage = {
            "input_tokens": 200, "output_tokens": 80,
            "cache_read_tokens": 0, "cache_write_tokens": 0, "total_tokens": 280,
        }

        with patch("core.extractor.call_llm_with_usage", return_value=(fake_model, fake_usage)), \
                patch("core.extractor.init_db"):
            engine = ExtractionEngine(model_key="sonnet-4-6", db_path=Path("/tmp/test.db"))
            result = engine.run("some chat text")

        self.assertEqual(result.status, "success")
        self.assertIsNotNone(result.token_usage)
        self.assertEqual(result.token_usage["input_tokens"], 200)
        self.assertEqual(result.token_usage["total_tokens"], 280)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_token_usage.py::TestExtractorTokenPropagation -v`
Expected: FAIL — `cannot import name 'call_llm_with_usage' from 'core.extractor'`.

- [ ] **Step 4: Update `core/extractor.py`**

Read `core/extractor.py`. Find the import of `call_llm`:
```python
from core.llm_client import call_llm
```
Change it to:
```python
from core.llm_client import call_llm, call_llm_with_usage
```

In `_call_with_retry`, add a `token_usage_accumulator` nonlocal variable. The full updated function:

```python
def _call_with_retry(
    schema: Type[T],
    model_key: str,
    prompt_factory,
    system_prompt: str | None,
) -> tuple[T, int, str, dict | None]:
    """Run prompt -> LLM -> validated model, retrying up to ``_MAX_ATTEMPTS`` times.

    Returns (model, attempts_used, last_prompt, accumulated_token_usage).
    """
    attempts_used = 0
    last_prompt = ""
    accumulated_usage: dict | None = None

    @retry(
        retry=retry_if_exception_type((ValidationError, ValueError, json.JSONDecodeError)),
        stop=stop_after_attempt(_MAX_ATTEMPTS),
        wait=wait_fixed(1),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _attempt() -> T:
        nonlocal attempts_used, last_prompt, accumulated_usage
        attempts_used += 1
        current_attempt = attempts_used

        logger.info(
            "LLM attempt %d/%d for schema=%s",
            current_attempt, _MAX_ATTEMPTS, schema.__name__,
        )
        prompt = prompt_factory(current_attempt)
        last_prompt = prompt
        logger.debug("Prompt (attempt=%d):\n%s", current_attempt, textwrap.indent(prompt, "  "))

        result, usage = call_llm_with_usage(prompt, schema, model_key=model_key, system_prompt=system_prompt)

        # Accumulate usage across retry attempts.
        if usage:
            if accumulated_usage is None:
                accumulated_usage = dict(usage)
            else:
                for k in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"):
                    accumulated_usage[k] = accumulated_usage.get(k, 0) + usage.get(k, 0)
                accumulated_usage["total_tokens"] = (
                    accumulated_usage.get("input_tokens", 0)
                    + accumulated_usage.get("output_tokens", 0)
                )

        logger.info("Attempt %d succeeded", current_attempt)
        return result

    result = _attempt()
    return result, attempts_used, last_prompt, accumulated_usage
```

> **Important:** `_call_with_retry` now returns a 4-tuple `(T, int, str, dict | None)` instead of the previous 3-tuple. You must also update the two call sites in `ExtractionEngine.run()` and `ExtractionEngine.update()`.

In `ExtractionEngine.run()`, find:
```python
            result_model, attempts_used, final_prompt = _call_with_retry(
                target_schema, self.model_key, _factory, system_prompt,
            )
```
Change to:
```python
            result_model, attempts_used, final_prompt, token_usage = _call_with_retry(
                target_schema, self.model_key, _factory, system_prompt,
            )
```

And in the success `return ExtractionResult(...)` call, add `token_usage=token_usage,` as a keyword argument.

In the failure `return ExtractionResult(...)` call (in the `except` block), add `token_usage=None,`.

Do the same for `ExtractionEngine.update()` — find the `_call_with_retry` call, unpack 4 values, and pass `token_usage=token_usage` to the success `ExtractionResult`.

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_token_usage.py::TestExtractorTokenPropagation -v`
Expected: PASS.

Full suite:
```bash
python -m pytest tests/ -v
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add core/db.py core/extractor.py tests/test_token_usage.py
git commit -m "feat: propagate token usage through ExtractionEngine"
```

---

## Task 4: Capture validation LLM token usage in postprocess

**Files:**
- Modify: `core/postprocess_stages.py` (`ValidationLLMStage.run`, `StageResult`)

- [ ] **Step 1: Add `token_usage` to `StageResult`**

In `core/postprocess_stages.py`, read the file and find the `StageResult` dataclass. Add this field:

```python
    token_usage: dict | None = None
```

(Add it at the end of the dataclass, after `elapsed_ms`.)

- [ ] **Step 2: Capture usage in `ValidationLLMStage.run`**

In `ValidationLLMStage.run`, change the `call_llm(...)` call to use `call_llm_with_usage`. The full updated call block:

```python
        from core.llm_client import call_llm_with_usage
        ...
        try:
            ...
            result, val_usage = call_llm_with_usage(
                user_prompt,
                SOValidationResult,
                model_key=ctx.validation_model_key,
                system_prompt=system_prompt,
            )
            return StageResult(
                name=self.name,
                status="ok",
                contract=result.extraction.model_dump(),
                issues=[i.model_dump() for i in result.issues],
                notes=result.notes,
                elapsed_ms=round((time.perf_counter() - t0) * 1000, 3),
                token_usage=val_usage,
            )
```

The `except` branch `StageResult` already returns without `token_usage`, so it defaults to `None`.

- [ ] **Step 3: Verify tests still pass**

Run: `python -m pytest tests/ -v`
Expected: all pass (no test change needed — the field has a default).

- [ ] **Step 4: Commit**

```bash
git add core/postprocess_stages.py
git commit -m "feat: capture validation LLM token usage in StageResult"
```

---

## Task 5: Add `token_usage` to `AgentRunResult` and wire the agent

**Files:**
- Modify: `agents/base.py`
- Modify: `agents/so_extraction/agent.py`
- Test: `tests/test_token_usage.py` (extend)

- [ ] **Step 1: Add field to `AgentRunResult`**

In `agents/base.py`, add this field to `AgentRunResult` immediately after `baseline_output_json`:

```python
    token_usage: dict | None = None
```

Verify:
```bash
python -c "from agents.base import AgentRunResult; r = AgentRunResult(agent_id='a', dataset_id='d', source_path='p', success=True, status='success', attempts=1, elapsed_sec=0.0); print(r.token_usage)"
```
Expected: `None`

- [ ] **Step 2: Extend the failing test for agent wiring**

Append to `tests/test_token_usage.py`:

```python
class TestAgentTokenWiring(unittest.TestCase):
    def test_run_one_stores_token_usage_from_engine(self):
        from pathlib import Path
        from unittest.mock import MagicMock, patch

        from agents.base import RunOptions
        from agents.so_extraction.agent import ChatInput, SOExtractionAgent

        agent = SOExtractionAgent(
            id="so_extraction",
            display_name="SO Extraction",
            datasets=[],
            repo_root=Path(__file__).resolve().parents[1],
        )
        payload = ChatInput(
            source_path=Path("raw_data/chats/x.json"),
            text="buy 10 bags",
            meta={},
        )
        opts = RunOptions(model_key="sonnet-4-6", extra={})

        engine = MagicMock()
        engine.iso_date = "2026-06-01"
        engine.run.return_value = MagicMock(
            status="success",
            output_json='{"data": []}',
            attempts=1,
            error=None,
            model_key="sonnet-4-6",
            model_provider="bedrock",
            chunk_count=1,
            chunk_truncated=False,
            input_chars=10,
            token_usage={"input_tokens": 150, "output_tokens": 60, "cache_read_tokens": 0,
                         "cache_write_tokens": 0, "total_tokens": 210},
        )

        with patch("agents.so_extraction.agent.ExtractionEngine", return_value=engine), \
                patch("agents.so_extraction.agent.run_postprocess_pipeline",
                      return_value=({"data": []}, {"llm_validate_ms": 0, "postprocess_total_ms": 0,
                                                    "deterministic_ms": 0})), \
                patch.object(agent, "expected_for", return_value=None):
            result = agent.run_one(payload, opts)

        self.assertIsNotNone(result.token_usage)
        self.assertEqual(result.token_usage["input_tokens"], 150)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_token_usage.py::TestAgentTokenWiring -v`
Expected: FAIL — `result.token_usage` is `None`.

- [ ] **Step 4: Update `agents/so_extraction/agent.py`**

In `run_one`, `result` is the `ExtractionResult` from `engine.run(...)`. It now has a `token_usage` field (added in Task 3). The postprocess pipeline's `diagnostics` dict may also contain validation LLM token usage (since `StageResult.token_usage` is stored in `diagnostics` — but currently postprocess_pipeline returns aggregated diagnostics, not individual stage token usage).

The simplest approach: read extraction token usage from `result.token_usage` and add it to the `AgentRunResult`.

In `run_one`, find the block that constructs `flow_ms` and the final `return AgentRunResult[dict](...)`. After the existing baseline block and before the `return`, add:

```python
        # Collect token usage: extraction + (optionally) validation.
        agent_token_usage: dict | None = None
        if result.token_usage:
            agent_token_usage = dict(result.token_usage)
        # Validation LLM token usage is stored by postprocess_pipeline in diagnostics.
        val_usage = (diagnostics or {}).get("validation_token_usage")
        if val_usage and isinstance(val_usage, dict):
            if agent_token_usage is None:
                agent_token_usage = dict(val_usage)
            else:
                for k in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"):
                    agent_token_usage[k] = agent_token_usage.get(k, 0) + val_usage.get(k, 0)
                agent_token_usage["total_tokens"] = (
                    agent_token_usage.get("input_tokens", 0)
                    + agent_token_usage.get("output_tokens", 0)
                )
```

Then in the `return AgentRunResult[dict](...)` call, add:
```python
            token_usage=agent_token_usage,
```

> NOTE: The `validation_token_usage` key in diagnostics needs to be set by `run_postprocess_pipeline`. See Step 5.

- [ ] **Step 5: Thread validation usage through postprocess_pipeline**

In `core/postprocess_pipeline.py`, read the file. Find where the pipeline aggregates `diagnostics`. The function `run_postprocess_pipeline` returns `(final_dict, diagnostics)`. Find where `diagnostics` is built (after `ValidationLLMStage.run`). The validation stage result is already stored in diagnostics somewhere.

Look for where `stage_result` from `ValidationLLMStage` is read. Add this to the diagnostics dict after calling the validation stage:

```python
        if hasattr(stage_result, "token_usage") and stage_result.token_usage:
            diagnostics["validation_token_usage"] = stage_result.token_usage
```

Read `core/postprocess_pipeline.py` carefully before editing — the exact lines depend on the current structure.

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest tests/test_token_usage.py::TestAgentTokenWiring -v`
Expected: PASS.

Full suite:
```bash
python -m pytest tests/ -v
```
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add agents/base.py agents/so_extraction/agent.py core/postprocess_pipeline.py tests/test_token_usage.py
git commit -m "feat: store token_usage in AgentRunResult from extraction + validation"
```

---

## Task 6: Emit token fields in artifacts

**Files:**
- Modify: `harness/artifacts.py`
- Test: `tests/test_token_usage.py` (extend)

- [ ] **Step 1: Extend the failing test**

Append to `tests/test_token_usage.py`:

```python
class TestArtifactsTokenFields(unittest.TestCase):
    def _make_rec(self, token_usage):
        from agents.base import AgentRunResult, ScoreResult
        return AgentRunResult(
            agent_id="so_extraction",
            dataset_id="default",
            source_path="raw_data/chats/x.json",
            success=True,
            status="success",
            attempts=1,
            elapsed_sec=1.0,
            model_key="sonnet-4-6",
            score=ScoreResult(expected_available=True, mismatch_count=1, compared_field_count=10),
            token_usage=token_usage,
        )

    def test_record_row_exposes_token_fields(self):
        from harness.artifacts import record_to_row
        usage = {"input_tokens": 200, "output_tokens": 80, "cache_read_tokens": 10,
                 "cache_write_tokens": 5, "total_tokens": 280}
        row = record_to_row(self._make_rec(usage))
        self.assertEqual(row["input_tokens"], 200)
        self.assertEqual(row["output_tokens"], 80)
        self.assertEqual(row["total_tokens"], 280)

    def test_record_row_zero_when_no_usage(self):
        from harness.artifacts import record_to_row
        row = record_to_row(self._make_rec(None))
        self.assertEqual(row["input_tokens"], 0)
        self.assertEqual(row["total_tokens"], 0)

    def test_aggregate_sums_tokens(self):
        from harness.artifacts import aggregate
        recs = [
            self._make_rec({"input_tokens": 100, "output_tokens": 40, "cache_read_tokens": 0,
                            "cache_write_tokens": 0, "total_tokens": 140}),
            self._make_rec({"input_tokens": 200, "output_tokens": 80, "cache_read_tokens": 20,
                            "cache_write_tokens": 0, "total_tokens": 280}),
        ]
        summary = aggregate(recs)
        totals = summary["totals"]
        self.assertEqual(totals["total_input_tokens"], 300)
        self.assertEqual(totals["total_output_tokens"], 120)
        self.assertEqual(totals["total_tokens"], 420)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_token_usage.py::TestArtifactsTokenFields -v`
Expected: FAIL — `KeyError: 'input_tokens'`.

- [ ] **Step 3: Update `record_to_row` in `harness/artifacts.py`**

Read the file. In `record_to_row`, after the `"baseline_output_json": rec.baseline_output_json,` line, add:

```python
        "input_tokens": int((rec.token_usage or {}).get("input_tokens") or 0),
        "output_tokens": int((rec.token_usage or {}).get("output_tokens") or 0),
        "cache_read_tokens": int((rec.token_usage or {}).get("cache_read_tokens") or 0),
        "cache_write_tokens": int((rec.token_usage or {}).get("cache_write_tokens") or 0),
        "total_tokens": int((rec.token_usage or {}).get("total_tokens") or 0),
```

- [ ] **Step 4: Update `_summarize` in `aggregate` in `harness/artifacts.py`**

In the `_summarize` inner function, after the `baseline_rows` block (from the baseline plan), add:

```python
        total_input_tokens = sum(r.get("input_tokens", 0) for r in rows_in)
        total_output_tokens = sum(r.get("output_tokens", 0) for r in rows_in)
        total_cache_read = sum(r.get("cache_read_tokens", 0) for r in rows_in)
        total_cache_write = sum(r.get("cache_write_tokens", 0) for r in rows_in)
        total_tokens_all = sum(r.get("total_tokens", 0) for r in rows_in)
```

Then in the returned dict, add:

```python
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_cache_read_tokens": total_cache_read,
            "total_cache_write_tokens": total_cache_write,
            "total_tokens": total_tokens_all,
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_token_usage.py::TestArtifactsTokenFields -v`
Expected: PASS (3 tests).

Full suite:
```bash
python -m pytest tests/ -v
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add harness/artifacts.py tests/test_token_usage.py
git commit -m "feat: emit token fields in artifacts record_to_row and aggregate"
```

---

## Task 7: Token report HTML renderer

**Files:**
- Create: `harness/token_report_html.py`
- Test: `tests/test_token_report_html.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_token_report_html.py
"""Token report HTML generation tests."""

from __future__ import annotations

import unittest

from harness.token_report_html import render_token_report_html


def _summary(with_tokens: bool = True):
    token_fields = {}
    if with_tokens:
        token_fields = {
            "total_input_tokens": 1500,
            "total_output_tokens": 600,
            "total_cache_read_tokens": 200,
            "total_cache_write_tokens": 50,
            "total_tokens": 2100,
        }
    totals = {"run_count": 3, "success_rate": 1.0, **token_fields}
    by_model = [
        {"model_key": "sonnet-4-6", "total_input_tokens": 1500,
         "total_output_tokens": 600, "total_tokens": 2100, "run_count": 3}
    ] if with_tokens else []
    by_chat = [
        {"chat_filename": "chat_01.json", "model_key": "sonnet-4-6",
         "few_shot_count": 0, "total_input_tokens": 500, "total_output_tokens": 200,
         "total_tokens": 700, "run_count": 1}
    ] if with_tokens else []
    return {"totals": totals, "by_combo": by_model, "by_chat": by_chat}


class TestTokenReportHtml(unittest.TestCase):
    def test_report_contains_token_totals(self):
        html = render_token_report_html("run-001", "2026-06-03T12:00:00Z", {}, _summary())
        self.assertIn("1,500", html)   # input tokens formatted
        self.assertIn("600", html)     # output tokens
        self.assertIn("Token Usage", html)

    def test_report_contains_per_chat_table(self):
        html = render_token_report_html("run-001", "2026-06-03T12:00:00Z", {}, _summary())
        self.assertIn("chat_01.json", html)

    def test_report_no_tokens_shows_placeholder(self):
        html = render_token_report_html("run-001", "2026-06-03T12:00:00Z", {}, _summary(with_tokens=False))
        self.assertIn("No token data", html)

    def test_report_is_valid_html_structure(self):
        html = render_token_report_html("run-001", "2026-06-03T12:00:00Z", {}, _summary())
        self.assertTrue(html.strip().startswith("<!DOCTYPE html"))
        self.assertIn("</html>", html)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_token_report_html.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'harness.token_report_html'`.

- [ ] **Step 3: Create `harness/token_report_html.py`**

Create the file with the full renderer. The CSS reuses the same variables and classes as `harness/report_dashboard_html.py` (copy the `<style>` block from there for consistency — read that file's `_build_style()` or inline `<style>` section and reuse it verbatim):

```python
# harness/token_report_html.py
"""Token usage report HTML — styled identically to report_dashboard_html."""

from __future__ import annotations

import html as html_lib
import json
from typing import Any

_CHART_CDN = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"


def _esc(s: str) -> str:
    return html_lib.escape(str(s), quote=True)


def _fmt_num(n: Any, decimals: int = 0) -> str:
    if n is None:
        return "—"
    try:
        return f"{float(n):,.{decimals}f}"
    except (TypeError, ValueError):
        return "—"


def _token_summary_cards(totals: dict[str, Any]) -> str:
    ti = totals.get("total_input_tokens") or 0
    to_ = totals.get("total_output_tokens") or 0
    cr = totals.get("total_cache_read_tokens") or 0
    cw = totals.get("total_cache_write_tokens") or 0
    tt = totals.get("total_tokens") or 0
    cards = "".join([
        f'<div class="dataset-card"><div class="name">Input Tokens</div>'
        f'<div class="score">{_fmt_num(ti)}</div></div>',
        f'<div class="dataset-card"><div class="name">Output Tokens</div>'
        f'<div class="score">{_fmt_num(to_)}</div></div>',
        f'<div class="dataset-card"><div class="name">Cache Read</div>'
        f'<div class="score">{_fmt_num(cr)}</div></div>',
        f'<div class="dataset-card"><div class="name">Cache Write</div>'
        f'<div class="score">{_fmt_num(cw)}</div></div>',
        f'<div class="dataset-card"><div class="name">Total Tokens</div>'
        f'<div class="score">{_fmt_num(tt)}</div></div>',
    ])
    return f'<div class="dataset-grid">{cards}</div>'


def _per_model_table(by_combo: list[dict[str, Any]]) -> str:
    if not by_combo:
        return ""
    rows = "".join(
        f"<tr><td>{_esc(str(r.get('model_key', '')))}</td>"
        f"<td>{_fmt_num(r.get('run_count'))}</td>"
        f"<td>{_fmt_num(r.get('total_input_tokens'))}</td>"
        f"<td>{_fmt_num(r.get('total_output_tokens'))}</td>"
        f"<td>{_fmt_num(r.get('total_tokens'))}</td></tr>"
        for r in by_combo
    )
    return (
        "<div class='chart-wrap' style='margin-top:24px;'>"
        "<div class='chart-title'>By Model</div>"
        "<table class='leaderboard'><thead><tr>"
        "<th>Model</th><th>Runs</th><th>Input</th><th>Output</th><th>Total</th>"
        "</tr></thead><tbody>"
        + rows
        + "</tbody></table></div>"
    )


def _per_chat_table(by_chat: list[dict[str, Any]]) -> str:
    if not by_chat:
        return ""
    rows = "".join(
        f"<tr><td>{_esc(str(r.get('chat_filename', '')))}</td>"
        f"<td>{_esc(str(r.get('model_key', '')))}</td>"
        f"<td>{_fmt_num(r.get('total_input_tokens'))}</td>"
        f"<td>{_fmt_num(r.get('total_output_tokens'))}</td>"
        f"<td>{_fmt_num(r.get('total_cache_read_tokens'))}</td>"
        f"<td>{_fmt_num(r.get('total_tokens'))}</td></tr>"
        for r in by_chat
    )
    return (
        "<div class='chart-wrap' style='margin-top:24px;'>"
        "<div class='chart-title'>Per Chat</div>"
        "<table class='leaderboard'><thead><tr>"
        "<th>Chat</th><th>Model</th><th>Input</th><th>Output</th><th>Cache Read</th><th>Total</th>"
        "</tr></thead><tbody>"
        + rows
        + "</tbody></table></div>"
    )


def _bar_chart_script(by_combo: list[dict[str, Any]]) -> str:
    if not by_combo:
        return ""
    chart_data = json.dumps([
        {
            "label": str(r.get("model_key", "")),
            "input": int(r.get("total_input_tokens") or 0),
            "output": int(r.get("total_output_tokens") or 0),
            "cache": int((r.get("total_cache_read_tokens") or 0) + (r.get("total_cache_write_tokens") or 0)),
        }
        for r in by_combo
    ], ensure_ascii=False)
    return f"""
const tkData = {chart_data};
if (tkData.length && document.getElementById("tokenChart")) {{
  new Chart(document.getElementById("tokenChart").getContext("2d"), {{
    type: "bar",
    data: {{
      labels: tkData.map((d) => d.label),
      datasets: [
        {{ label: "Input", data: tkData.map((d) => d.input), backgroundColor: "#7a8aa8cc" }},
        {{ label: "Output", data: tkData.map((d) => d.output), backgroundColor: "#2d6b3fcc" }},
        {{ label: "Cache", data: tkData.map((d) => d.cache), backgroundColor: "#b9543fcc" }},
      ],
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      plugins: {{ legend: {{ position: "bottom" }} }},
      scales: {{ x: {{ stacked: true }}, y: {{ stacked: true }} }},
    }},
  }});
}}
"""


def render_token_report_html(
    run_id: str,
    generated_at: str,
    config: dict[str, Any],
    summary: dict[str, Any],
) -> str:
    totals = summary.get("totals") or {}
    by_combo = summary.get("by_combo") or []
    by_chat = summary.get("by_chat") or []

    has_tokens = bool(totals.get("total_tokens"))

    if has_tokens:
        summary_cards = _token_summary_cards(totals)
        model_table = _per_model_table(by_combo)
        chat_table = _per_chat_table(by_chat)
        chart_canvas = '<div class="chart-canvas-wrap" style="height:320px;"><canvas id="tokenChart"></canvas></div>'
        chart_script = _bar_chart_script(by_combo)
        no_data_msg = ""
    else:
        summary_cards = ""
        model_table = ""
        chat_table = ""
        chart_canvas = ""
        chart_script = ""
        no_data_msg = '<p class="section-intro">No token data available for this run. Re-run with a current version of the harness to capture token usage.</p>'

    # Read style from main report module to stay in sync.
    try:
        from harness.report_dashboard_html import _INLINE_STYLE  # type: ignore[attr-defined]
        style_block = f"<style>{_INLINE_STYLE}</style>"
    except (ImportError, AttributeError):
        style_block = "<style>body{font-family:sans-serif;margin:2rem;}</style>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Token Usage · {_esc(run_id)}</title>
{style_block}
</head>
<body>
<header class="report-header">
  <div class="report-meta">Run <strong>{_esc(run_id)}</strong> · Generated {_esc(generated_at)}</div>
  <h1>Token Usage Report</h1>
</header>
<main>
<section id="token-summary">
  <div class="section-head"><span class="section-num">Sec. 1</span><h2>Token Usage</h2></div>
  {no_data_msg}
  {summary_cards}
  {chart_canvas}
  {model_table}
  {chat_table}
</section>
</main>
<script src="{_CHART_CDN}"></script>
<script>
{chart_script}
</script>
</body>
</html>"""
```

> **Note on shared styles:** The approach above tries to import `_INLINE_STYLE` from `report_dashboard_html`. Read `harness/report_dashboard_html.py` — if the styles are inlined in a function rather than a module-level constant, extract them to a module-level constant `_INLINE_STYLE` in that file, then import it here. If that's too disruptive, copy the style block directly.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_token_report_html.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add harness/token_report_html.py tests/test_token_report_html.py
git commit -m "feat: add token usage HTML report renderer"
```

---

## Task 8: Wire token report into runner and artifacts

**Files:**
- Modify: `harness/artifacts.py` (add `write_token_report`)
- Modify: `harness/runner.py` (call `write_token_report` at run-end)

- [ ] **Step 1: Add `write_token_report` to `harness/artifacts.py`**

Read `harness/artifacts.py`. After the `write_report` function, add:

```python
def write_token_report(
    run_dir: Path,
    run_id: str,
    config: dict[str, Any],
    summary: dict[str, Any],
) -> Path:
    from harness.token_report_html import render_token_report_html
    path = run_dir / "token_report.html"
    path.write_text(
        render_token_report_html(
            run_id,
            datetime.now(timezone.utc).isoformat(),
            config,
            summary,
        ),
        encoding="utf-8",
    )
    return path
```

- [ ] **Step 2: Call `write_token_report` from `harness/runner.py`**

Read `harness/runner.py`. In `_run_bulk`, find where `artifacts.write_report(...)` is called at the final checkpoint (`is_final = completed == total`). After that call, add:

```python
                if is_final:
                    artifacts.write_token_report(run_dir, run_id, config, summary)
```

Do the same in `_run_pipeline` — after the `artifacts.write_report(...)` call at the end, add:
```python
    artifacts.write_token_report(run_dir, run_id, config_payload, summary)
```

And in `main()` at the very end, after the final `artifacts.write_report(...)` call, add:
```python
    artifacts.write_token_report(run_dir, run_id, config_payload, summary)
    print(f"Token report  : {run_dir / 'token_report.html'}")
```

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: all tests pass.

- [ ] **Step 4: Verify runner help still works**

```bash
python -m harness.runner --help | head -5
```
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add harness/artifacts.py harness/runner.py
git commit -m "feat: write token_report.html alongside report.html"
```

---

## Self-Review Notes

- **Spec: token tracking for all providers** — `call_llm_with_usage` covers bedrock, openai, anthropic, gemini. ✓
- **Spec: per-run aggregate totals** — `_summarize` adds `total_input_tokens`, `total_output_tokens`, `total_tokens`. ✓
- **Spec: per-chat breakdown** — `by_chat` table in token report. ✓
- **Spec: model-by-model split** — `by_combo` table in token report. ✓
- **Spec: same styles as main report** — Token report imports `_INLINE_STYLE` from `report_dashboard_html`. ✓
- **Spec: file alongside main report** — `token_report.html` in same run directory. ✓
- **`call_llm` unchanged** — `report_summary.py` callers untouched. ✓
- **Type consistency:** `token_usage` is always `dict | None` throughout; `TokenUsage.to_dict()` produces the dict; `TokenUsage.from_dict()` parses it. ✓
- **Gap: `_INLINE_STYLE` extraction** — Task 7 notes that `_INLINE_STYLE` may need to be extracted to a module-level constant in `report_dashboard_html.py`. If it's currently inlined in a function, that extraction is a prerequisite for the import to work. If it is inlined, add a step in Task 7 to extract it first.
