# Anthropic Direct API Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an `anthropic:<key>` model key prefix so any Anthropic model can be called directly via the Anthropic API (using `ANTHROPIC_API_KEY` from env) as an alternative to Bedrock.

**Architecture:** Mirrors the existing `openai:<key>` and `gemini:<key>` patterns exactly. A new `ANTHROPIC_DIRECT_MODELS` dict maps short keys to Anthropic-native model IDs; `build_model_catalog` registers them under the `"anthropic"` provider; `call_llm` dispatches to a new `_call_anthropic()` function via `instructor.from_anthropic()`. The Bedrock path is completely unchanged.

**Tech Stack:** Python 3, `anthropic` SDK, `instructor` 1.15.x, `unittest`.

---

## File Structure

- **Modify:** `core/utils.py` — add `ANTHROPIC_DIRECT_MODELS` dict and `ANTHROPIC_API_KEY` constant; update `build_model_catalog` and `resolve_model_selection`.
- **Modify:** `core/llm_client.py` — add `_call_anthropic()` function; add `"anthropic"` dispatch in `call_llm`.
- **Create:** `tests/test_anthropic_provider.py` — unit tests for the new provider.

---

## Task 1: Register Anthropic direct models in the catalog

**Files:**
- Modify: `core/utils.py`
- Test: `tests/test_anthropic_provider.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_anthropic_provider.py
"""Tests for Anthropic direct API model catalog entries."""

from __future__ import annotations

import unittest

from core.utils import MODEL_CATALOG, resolve_model_selection


class TestAnthropicDirectCatalog(unittest.TestCase):
    def test_anthropic_keys_present_in_catalog(self):
        for key in ("anthropic:sonnet-4-6", "anthropic:opus-4-8"):
            self.assertIn(key, MODEL_CATALOG, f"{key} not in MODEL_CATALOG")

    def test_anthropic_provider_field(self):
        entry = MODEL_CATALOG["anthropic:sonnet-4-6"]
        self.assertEqual(entry["provider"], "anthropic")
        self.assertEqual(entry["model_id"], "claude-sonnet-4-6")

    def test_resolve_model_selection_anthropic(self):
        resolved = resolve_model_selection("anthropic:opus-4-8")
        self.assertEqual(resolved["provider"], "anthropic")
        self.assertEqual(resolved["model_id"], "claude-opus-4-8")
        self.assertEqual(resolved["model_key"], "anthropic:opus-4-8")

    def test_bedrock_key_still_resolves_to_bedrock(self):
        resolved = resolve_model_selection("sonnet-4-6")
        self.assertEqual(resolved["provider"], "bedrock")

    def test_unknown_anthropic_key_raises(self):
        with self.assertRaises(ValueError):
            resolve_model_selection("anthropic:nonexistent-model")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_anthropic_provider.py -v`
Expected: FAIL — `anthropic:sonnet-4-6` not in MODEL_CATALOG.

- [ ] **Step 3: Add `ANTHROPIC_DIRECT_MODELS` and update `core/utils.py`**

In `core/utils.py`, after the existing `OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")` line, add:

```python
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

ANTHROPIC_DIRECT_MODELS = {
    "sonnet-4-5": "claude-sonnet-4-5-20250929",
    "sonnet-4-6": "claude-sonnet-4-6",
    "opus-4-5": "claude-opus-4-5-20251101",
    "opus-4-6": "claude-opus-4-6",
    "opus-4-7": "claude-opus-4-7",
    "opus-4-8": "claude-opus-4-8",
}
```

In `build_model_catalog`, after the existing Gemini loop, add:

```python
    for key, model_id in ANTHROPIC_DIRECT_MODELS.items():
        full_key = f"anthropic:{key}"
        catalog[full_key] = {
            "provider": "anthropic",
            "model_id": model_id,
            "display_name": f"Anthropic · {key}",
        }
```

In `resolve_model_selection`, after the `if key.startswith("gemini:"):` block (before the final `raise ValueError`), add:

```python
    if key.startswith("anthropic:"):
        short = key.split(":", 1)[1]
        if short in ANTHROPIC_DIRECT_MODELS:
            return {
                "provider": "anthropic",
                "model_id": ANTHROPIC_DIRECT_MODELS[short],
                "display_name": f"Anthropic · {short}",
                "model_key": key,
            }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_anthropic_provider.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add core/utils.py tests/test_anthropic_provider.py
git commit -m "feat: register Anthropic direct API models in catalog"
```

---

## Task 2: Add Anthropic direct API caller to llm_client

**Files:**
- Modify: `core/llm_client.py`
- Test: `tests/test_anthropic_provider.py` (extend)

- [ ] **Step 1: Extend the failing test**

Append to `tests/test_anthropic_provider.py`, inside `TestAnthropicDirectCatalog`:

```python
class TestAnthropicDirectCaller(unittest.TestCase):
    def test_call_llm_dispatches_to_anthropic_provider(self):
        from unittest.mock import MagicMock, patch

        from core.llm_client import call_llm
        from core.models import SOExtractContractList

        fake_result = SOExtractContractList.model_validate({"data": []})

        with patch("core.llm_client._call_anthropic", return_value=fake_result) as mocked:
            result = call_llm(
                "test prompt",
                SOExtractContractList,
                model_key="anthropic:sonnet-4-6",
                system_prompt="sys",
            )

        mocked.assert_called_once()
        call_args = mocked.call_args
        self.assertEqual(call_args.kwargs.get("system_prompt") or call_args.args[3], "sys")
        self.assertEqual(result, fake_result)

    def test_call_anthropic_passes_no_system_when_none(self):
        from unittest.mock import MagicMock, patch

        import instructor

        from core.llm_client import _call_anthropic
        from core.models import SOExtractContractList

        fake_client = MagicMock()
        fake_client.messages.create.return_value = SOExtractContractList.model_validate({"data": []})

        with patch("core.llm_client.instructor") as mock_instructor, \
                patch("core.llm_client.anthropic_sdk") as mock_sdk:
            mock_instructor.from_anthropic.return_value = fake_client
            result = _call_anthropic(
                "hello",
                SOExtractContractList,
                model_id="claude-sonnet-4-6",
                system_prompt=None,
            )

        call_kwargs = fake_client.messages.create.call_args.kwargs
        self.assertNotIn("system", call_kwargs)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_anthropic_provider.py::TestAnthropicDirectCaller -v`
Expected: FAIL — `cannot import name '_call_anthropic'`.

- [ ] **Step 3: Add `_call_anthropic` and update `call_llm` in `core/llm_client.py`**

At the top of `core/llm_client.py`, add this import after the existing imports:

```python
import anthropic as anthropic_sdk
```

Add this function after the existing `_call_gemini` function:

```python
def _call_anthropic(prompt: str, schema: Type[T], model_id: str, system_prompt: str | None = None) -> T:
    logger.info("Calling Anthropic model=%s schema=%s", model_id, schema.__name__)
    client = instructor.from_anthropic(anthropic_sdk.Anthropic())
    kwargs: dict = dict(
        model=model_id,
        response_model=schema,
        max_tokens=_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    if system_prompt:
        kwargs["system"] = system_prompt
    result: T = client.messages.create(**kwargs)
    logger.info("Anthropic extraction succeeded, type=%s", type(result).__name__)
    return result
```

In `call_llm`, add the Anthropic dispatch after the Gemini block (before the final `raise ValueError`):

```python
    if provider == "anthropic":
        return _call_anthropic(prompt, schema, model_id=model_id, system_prompt=system_prompt)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_anthropic_provider.py -v`
Expected: PASS (all tests).

Also run the full suite to check for regressions:
```bash
python -m pytest tests/ -v
```
Expected: all existing tests still pass.

- [ ] **Step 5: Commit**

```bash
git add core/llm_client.py tests/test_anthropic_provider.py
git commit -m "feat: add Anthropic direct API caller to llm_client"
```

---

## Task 3: Verify end-to-end wiring and requirements.txt

**Files:**
- Possibly modify: `requirements.txt`
- Test: manual smoke test of catalog resolution

- [ ] **Step 1: Check `anthropic` is in requirements.txt**

Run:
```bash
grep anthropic requirements.txt
```

If it is NOT present, add it:
```bash
echo "anthropic>=0.40.0" >> requirements.txt
```

- [ ] **Step 2: Smoke-test catalog resolution**

Run:
```bash
python -c "
from core.utils import MODEL_CATALOG, resolve_model_selection
print('anthropic models:', [k for k in MODEL_CATALOG if k.startswith('anthropic:')])
r = resolve_model_selection('anthropic:opus-4-8')
print('resolved:', r)
r2 = resolve_model_selection('sonnet-4-6')
print('bedrock still works:', r2['provider'])
"
```

Expected output:
```
anthropic models: ['anthropic:sonnet-4-5', 'anthropic:sonnet-4-6', 'anthropic:opus-4-5', 'anthropic:opus-4-6', 'anthropic:opus-4-7', 'anthropic:opus-4-8']
resolved: {'provider': 'anthropic', 'model_id': 'claude-opus-4-8', 'display_name': 'Anthropic · opus-4-8', 'model_key': 'anthropic:opus-4-8'}
bedrock still works: bedrock
```

- [ ] **Step 3: Verify `--models` flag accepts the new keys**

Run:
```bash
python -m harness.runner --help | grep -A2 "models"
python -c "from harness.runner import _models; from types import SimpleNamespace; print(_models(SimpleNamespace(models=['anthropic:sonnet-4-6'])))"
```

Expected: `['anthropic:sonnet-4-6']` (no error).

- [ ] **Step 4: Commit requirements if changed**

```bash
git add requirements.txt
git commit -m "chore: ensure anthropic SDK is in requirements"
```

(Skip this commit if `anthropic` was already present.)

---

## Self-Review Notes

- **Spec: `anthropic:<key>` prefix** — Task 1 registers all 6 Anthropic models under `anthropic:` prefix. ✓
- **Spec: reads `ANTHROPIC_API_KEY` from env** — `anthropic_sdk.Anthropic()` automatically reads `ANTHROPIC_API_KEY` from env (same as OpenAI client reads `OPENAI_API_KEY`). ✓
- **Spec: Bedrock path unchanged** — Bedrock keys like `sonnet-4-6` still resolve to `provider=bedrock`. ✓
- **Spec: same models usable on both** — `sonnet-4-6` → Bedrock; `anthropic:sonnet-4-6` → Anthropic API. ✓
- **No placeholder scan issues found.** ✓
- **Type consistency:** `provider="anthropic"` used in both `build_model_catalog` and `_call_anthropic` dispatch. ✓
