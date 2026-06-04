# Model-Neutral Prompt Strategies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement three prompt strategies (XML-neutral, provider-profile, schema-driven) alongside the existing pipeline so all can be benchmarked against each other to find which makes extraction accuracy model-independent.

**Architecture:** A `PromptStrategy` enum routes `prompt_builder.py` to one of four template sets (CURRENT / XML_NEUTRAL / PROVIDER_PROFILE / SCHEMA_DRIVEN). The strategy flows from a new `--prompt-strategy` CLI flag → `RunOptions.extra` → `SOExtractionAgent` → `ExtractionEngine` → `prompt_builder`. Existing behaviour is preserved as the `CURRENT` default.

**Tech Stack:** Python 3.11+, Pydantic v2, Jinja2, instructor, pytest

---

## File Map

| Status | File | Purpose |
|--------|------|---------|
| **Create** | `core/prompt_strategy.py` | `PromptStrategy` enum + `provider_family()` helper |
| **Modify** | `core/models.py` | Enrich all `Field(description=...)` for schema-driven approach |
| **Create** | `templates/extraction_xml_neutral.j2` | Approach 1 & 2 (non-Anthropic): XML-tagged extraction prompt |
| **Create** | `templates/validation_system_xml_neutral.j2` | XML-tagged validation system prompt |
| **Create** | `templates/validation_user_xml_neutral.j2` | XML-tagged validation user prompt (no checklist markdown) |
| **Create** | `templates/extraction_schema_driven.j2` | Approach 3: minimal 3-sentence prompt, schema carries rules |
| **Modify** | `core/prompt_builder.py` | Add `strategy` + `model_key` params; route to correct template |
| **Modify** | `core/extractor.py` | Add `strategy` param to `ExtractionEngine.__init__` and `run()` |
| **Modify** | `agents/so_extraction/agent.py` | Read `prompt_strategy` from `options.extra`, pass to engine |
| **Modify** | `harness/runner.py` | Add `--prompt-strategy` CLI arg; inject into `_run_extra()` |
| **Create** | `tests/test_prompt_strategy.py` | Unit tests for strategy enum and template routing |

---

## Task 1: Create `PromptStrategy` enum

**Files:**
- Create: `core/prompt_strategy.py`
- Create: `tests/test_prompt_strategy.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_prompt_strategy.py
import pytest
from core.prompt_strategy import PromptStrategy, provider_family


def test_enum_values():
    assert PromptStrategy.CURRENT.value == "current"
    assert PromptStrategy.XML_NEUTRAL.value == "xml_neutral"
    assert PromptStrategy.PROVIDER_PROFILE.value == "provider_profile"
    assert PromptStrategy.SCHEMA_DRIVEN.value == "schema_driven"


def test_from_string_valid():
    assert PromptStrategy.from_str("xml_neutral") == PromptStrategy.XML_NEUTRAL
    assert PromptStrategy.from_str("CURRENT") == PromptStrategy.CURRENT
    assert PromptStrategy.from_str("schema_driven") == PromptStrategy.SCHEMA_DRIVEN


def test_from_string_invalid_returns_current():
    assert PromptStrategy.from_str("unknown") == PromptStrategy.CURRENT
    assert PromptStrategy.from_str("") == PromptStrategy.CURRENT
    assert PromptStrategy.from_str(None) == PromptStrategy.CURRENT


def test_provider_family_anthropic():
    assert provider_family("sonnet-4-6") == "anthropic"
    assert provider_family("opus-4-6") == "anthropic"
    assert provider_family("anthropic:opus-4-7") == "anthropic"


def test_provider_family_openai():
    assert provider_family("openai:5.4") == "openai"
    assert provider_family("openai:5.2") == "openai"


def test_provider_family_gemini():
    assert provider_family("gemini:gemini-2.5-pro") == "gemini"


def test_provider_family_unknown():
    assert provider_family("") == "anthropic"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /Users/tripathipranav/conductor/workspaces/harness_agents/stuttgart
python -m pytest tests/test_prompt_strategy.py -v
```

Expected: `ModuleNotFoundError: No module named 'core.prompt_strategy'`

- [ ] **Step 3: Create `core/prompt_strategy.py`**

```python
"""Prompt strategy selection for model-neutral extraction."""

from __future__ import annotations

from enum import Enum

from core.utils import resolve_model_selection


class PromptStrategy(Enum):
    CURRENT = "current"
    XML_NEUTRAL = "xml_neutral"
    PROVIDER_PROFILE = "provider_profile"
    SCHEMA_DRIVEN = "schema_driven"

    @classmethod
    def from_str(cls, value: str | None) -> "PromptStrategy":
        if not value:
            return cls.CURRENT
        try:
            return cls(value.lower())
        except ValueError:
            return cls.CURRENT


def provider_family(model_key: str) -> str:
    """Return provider family string for a model key: 'anthropic', 'openai', 'gemini', 'bedrock'."""
    if not model_key:
        return "anthropic"
    try:
        resolved = resolve_model_selection(model_key)
        return resolved.get("provider", "anthropic")
    except (ValueError, KeyError):
        return "anthropic"
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python -m pytest tests/test_prompt_strategy.py -v
```

Expected: All 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add core/prompt_strategy.py tests/test_prompt_strategy.py
git commit -m "feat: add PromptStrategy enum and provider_family helper"
```

---

## Task 2: Enrich Pydantic field descriptions (schema-driven foundation)

**Files:**
- Modify: `core/models.py`

The current descriptions are vague and contain model-specific hints ("from counter party info"). We replace them with precise, model-neutral descriptions that work as schema-level instructions for any LLM.

- [ ] **Step 1: Write a test that verifies key field descriptions exist**

Add to `tests/test_prompt_strategy.py`:

```python
from core.models import LLMExtractContractProductItem, SalesOrderExtractContractKeyDetails


def test_item_field_descriptions_are_precise():
    schema = LLMExtractContractProductItem.model_json_schema()
    props = schema.get("properties", {})
    # Confirm agreement-only rule is encoded for unit_price
    assert "agreed" in props["unit_price"]["description"].lower() or \
           "final" in props["unit_price"]["description"].lower()
    # Confirm verbatim rule is encoded for packing
    assert "verbatim" in props["packing"]["description"].lower() or \
           "exact" in props["packing"]["description"].lower()


def test_contract_field_descriptions_encode_rules():
    schema = SalesOrderExtractContractKeyDetails.model_json_schema()
    props = schema.get("properties", {})
    # payment_date must mention not copying shipping/document notes
    assert "payment" in props["payment_date"]["description"].lower()
    assert "null" in props["vendor_name"]["description"].lower() or \
           "empty" in props["vendor_name"]["description"].lower()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_prompt_strategy.py::test_item_field_descriptions_are_precise tests/test_prompt_strategy.py::test_contract_field_descriptions_encode_rules -v
```

Expected: FAIL — current descriptions don't meet these criteria.

- [ ] **Step 3: Update `core/models.py` with enriched field descriptions**

Replace the entire file content:

```python
from typing import List, Optional
from pydantic import BaseModel, Field
from pydantic.type_adapter import TypeAdapter


class LLMExtractContractProductItem(BaseModel):
    sr_no: int = Field(
        description="Serial number for this line item (1, 2, 3, …)."
    )
    description: str = Field(
        description=(
            "Product name exactly as agreed in the chat. Copy verbatim — "
            "exact casing, spacing, and punctuation. Empty string if not stated."
        )
    )
    quantity: Optional[float] = Field(
        description=(
            "Agreed numeric quantity as a float. null if not stated or not "
            "yet mutually agreed by both parties."
        )
    )
    quantity_unit: str = Field(
        description=(
            "Unit for quantity exactly as written in the chat (e.g. MT, KG, lb, "
            "bags, cartons, reams). Preserve capitalisation. Empty string if not stated."
        )
    )
    unit_price: Optional[float] = Field(
        description=(
            "Final agreed unit price as a float. Use only the mutually accepted "
            "price — not initial quotes or unaccepted counter-offers. null if not stated."
        )
    )
    pricing_unit: str = Field(
        description=(
            "Pricing basis exactly as written in the chat (e.g. USD/MT, SGD/MT, "
            "USD/KG, INR/MT). Preserve capitalisation. Empty string if not stated."
        )
    )
    ship_term: str = Field(
        description=(
            "Incoterm only: one of EXW, FOB, CIF, DDP. Copy the exact term from "
            "the chat. Empty string if not stated."
        )
    )
    delivery_terms: str = Field(
        description=(
            "Full per-product delivery terms including incoterm and location, verbatim "
            "from chat (e.g. 'CIF Busan', 'FOB Shanghai'). Empty string if not stated."
        )
    )
    shipment_date: str = Field(
        description=(
            "Per-product shipment date in ISO 8601 format (YYYY-MM-DD). For partial "
            "months use last day (e.g. 'November 2026' → '2026-11-30'). "
            "Empty string if not stated."
        )
    )
    shipping_address: str = Field(
        description=(
            "Per-product ship-to destination or address, verbatim from the chat. "
            "Empty string if not stated."
        )
    )
    packing: str = Field(
        description=(
            "Physical packaging description verbatim from the chat (e.g. '25kg bags', "
            "'50lb sacks'). This is NOT a logistics phrase. Empty string if not stated."
        )
    )
    loading: str = Field(
        description=(
            "Loading specification verbatim from the chat (e.g. '23MT/40\\u2019FCL', "
            "'12MT/20\\u2019FCL'). Empty string if not stated."
        )
    )
    total: Optional[float] = Field(
        description=(
            "quantity × unit_price. Only set when both values are present and share "
            "the same unit basis. null if either is missing or units differ."
        )
    )


class SalesOrderExtractContractKeyDetails(BaseModel):
    items: List[LLMExtractContractProductItem] = Field(
        description="Ordered list of agreed line items."
    )
    do_date: str = Field(
        description=(
            "Delivery or shipment date in ISO 8601 (YYYY-MM-DD). Empty string if not stated."
        ),
        default="",
    )
    po_date: str = Field(
        description=(
            "Sales order date in ISO 8601 (YYYY-MM-DD). Empty string if not stated."
        ),
        default="",
    )
    po_ref_no: str = Field(
        description=(
            "Purchase order reference number from the chat. Empty string if not stated."
        ),
        default="",
    )
    vendor_name: str = Field(
        description=(
            "Seller/vendor name. Use the vendor reference block if provided; "
            "chat wording wins if it names a different party. Empty string if not available."
        )
    )
    payment_date: str = Field(
        description=(
            "Payment terms: either a calendar date (YYYY-MM-DD) or an explicit "
            "phrase from the chat such as 'Net 30 from delivery', '100% Advance', "
            "'70% CAD'. Do NOT copy shipping instructions or document-handling notes "
            "(e.g. 'Against scan copies of documents') into this field. Empty string if unclear."
        )
    )
    delivery_terms: str = Field(
        description=(
            "Block-level delivery terms from the chat, verbatim. Empty string if not stated."
        )
    )
    billing_address: str = Field(
        description=(
            "Buyer billing address. May be filled from the counterparty reference block "
            "when not contradicted by the chat. Empty string if not available."
        )
    )
    shipping_method: str = Field(
        description=(
            "Shipping method exactly as stated in the chat (e.g. 'by sea', 'by air'). "
            "Empty string if not stated."
        )
    )
    shipping_address: str = Field(
        description=(
            "Block-level ship-to address. May be filled from the counterparty reference block "
            "when no item-level shipping_address is set and the chat does not contradict. "
            "Empty string if not available."
        )
    )


class SalesOrderUpdateContractKeyDetails(BaseModel):
    items: List[LLMExtractContractProductItem] = Field(
        description="Ordered list of agreed line items."
    )
    do_date: str = Field(
        description="Delivery or shipment date in ISO 8601 (YYYY-MM-DD). Empty string if not stated.",
        default="",
    )
    po_date: str = Field(
        description="Sales order date in ISO 8601 (YYYY-MM-DD). Empty string if not stated.",
        default="",
    )
    po_ref_no: str = Field(
        description="Purchase order reference number. Empty string if not stated.",
        default="",
    )
    vendor_name: str = Field(
        description=(
            "Seller/vendor name from the chat or prior summary. Empty string if not stated."
        )
    )
    payment_date: str = Field(
        description=(
            "Payment terms: calendar date or explicit phrase (e.g. 'Net 30 from delivery'). "
            "Never copy shipping/document notes. Empty string if unclear."
        )
    )
    delivery_terms: str = Field(
        description="Block-level delivery terms verbatim from chat. Empty string if not stated."
    )
    billing_address: str = Field(
        description="Buyer billing address from chat or counterparty reference. Empty string if not available."
    )
    shipping_method: str = Field(
        description="Shipping method from chat (e.g. 'by sea'). Empty string if not stated."
    )
    shipping_address: str = Field(
        description="Ship-to address from chat or counterparty reference. Empty string if not available."
    )


class SOExtractContractList(BaseModel):
    data: List[SalesOrderExtractContractKeyDetails] = Field(
        description="List of contracts, one entry per distinct purchase order."
    )


class SOUpdateContractList(BaseModel):
    data: List[SalesOrderUpdateContractKeyDetails] = Field(
        description="List of contracts, one entry per distinct purchase order."
    )


def dict_to_items_type(items: List[dict]):
    ExtractedListAdapter = TypeAdapter(List[LLMExtractContractProductItem])
    return ExtractedListAdapter.validate_python(items)


def dict_to_llm_details(details: dict):
    ExtractedListAdapter = TypeAdapter(SalesOrderExtractContractKeyDetails)
    return ExtractedListAdapter.validate_python(details)
```

- [ ] **Step 4: Run the tests**

```bash
python -m pytest tests/test_prompt_strategy.py -v
python -m pytest tests/ -v --tb=short -q
```

Expected: All tests pass. The existing test suite should not break since the schema structure (field names, types) is unchanged.

- [ ] **Step 5: Commit**

```bash
git add core/models.py tests/test_prompt_strategy.py
git commit -m "feat: enrich Pydantic field descriptions for schema-driven extraction"
```

---

## Task 3: Create XML-neutral extraction template

**Files:**
- Create: `templates/extraction_xml_neutral.j2`

This template encodes the same rules as the current `extraction.j2` but uses XML tags that all frontier models parse reliably.

- [ ] **Step 1: Create `templates/extraction_xml_neutral.j2`**

```jinja2
<extraction_task>
<rules>
<rule id="source_of_truth">The chat transcript is the only source of truth. Extract only terms both parties have explicitly agreed to.</rule>
<rule id="empty_valid">If a field is not stated in the chat, return null or empty string per the schema. Never guess. A partial but accurate extraction is strictly preferred over a complete but invented one.</rule>
<rule id="agreements_only">Only extract mutually accepted values. Proposals, counter-offers, and unanswered messages are not agreements. Confirmation signals: "confirmed", "ok", "agreed", "deal", "let's go", or explicit acceptance of a counter-offer.</rule>
<rule id="sequence">Messages are prefixed [seq=N] where seq=0 is oldest. When a value is revised by a later message both sides accept, the later value wins. An unaccepted counter-offer is not extractable.</rule>
<rule id="dates">Today is {{ iso_date }}. Normalize all dates to ISO 8601 (YYYY-MM-DD). Partial months (e.g. "November 2026") use the last day of the month (2026-11-30). If a date cannot be resolved to a concrete day, leave the field empty.</rule>
<rule id="verbatim">Copy these fields verbatim — exact spacing, casing, punctuation, word order — do not paraphrase: packing, loading, shipping_method, delivery_terms, billing_address, shipping_address, description, vendor_name, ship_term.</rule>
<rule id="units">Preserve units and currencies exactly as stated. No conversion (MT to KG, USD to INR, etc.). If the chat says "USD 3.5 per KG", write unit_price=3.5 and pricing_unit="USD/KG".</rule>
<rule id="payment_date">payment_date must be a calendar date or an explicit payment-term phrase from the chat (e.g. "Net 30 from delivery", "100% Advance"). Never copy shipping or document-handling instructions into this field. If unclear, leave empty.</rule>
<rule id="packing_loading_defaults">Apply ONLY when the field is missing from the chat: "Fat Powder" product → loading "23MT/40'FCL"; "Feeds" product → loading "12MT/20'FCL". packing is physical packaging only (e.g. "25kg bags") — never a logistics phrase.</rule>
<rule id="no_inference">Do not deduce values from common knowledge, industry norms, or arithmetic. If the chat does not state it, leave the field empty.</rule>
</rules>

{% if organization_info or customer_info %}
<reference_context note="Use only to interpret abbreviations or party names. Do not copy values into output fields unless the chat explicitly confirms them.">
{% if organization_info %}
<vendor>{{ organization_info | jsonpretty }}</vendor>
{% endif %}
{% if customer_info %}
<counterparty>{{ customer_info | jsonpretty }}</counterparty>
{% endif %}
</reference_context>
{% endif %}

{% if few_shot_examples %}
<examples note="Use only to learn the output structure. Do not copy values, prices, names, or dates from examples into this extraction.">
{% for ex in few_shot_examples %}
<example id="{{ loop.index }}">
<input>{{ ex.input_text }}</input>
<output>{{ ex.output_json }}</output>
</example>
{% endfor %}
</examples>
{% endif %}

<schema>
{{ schema_json }}
</schema>

<chat_transcript>
{{ input_text }}
</chat_transcript>

</extraction_task>

Extract the structured sales order from the chat_transcript above. Return only valid JSON that strictly conforms to the schema. No text, explanation, or markdown before or after the JSON.
{% if attempt is defined and attempt > 1 %}

Note (retry {{ attempt }}): A previous attempt failed schema validation. Ensure every required field is present — set it to null or empty string if not found. Double-check all value types match the schema.
{% endif %}
```

- [ ] **Step 2: Verify the template renders without error using a quick smoke test**

```python
# Run from repo root in a Python REPL or quick script
import sys; sys.path.insert(0, ".")
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader("templates"), trim_blocks=True, lstrip_blocks=True)
import json
env.filters["jsonpretty"] = lambda v, indent=2: json.dumps(v, indent=indent)
tpl = env.get_template("extraction_xml_neutral.j2")
out = tpl.render(
    input_text="Test chat",
    schema_json='{"type": "object"}',
    few_shot_examples=[],
    attempt=1,
    iso_date="2026-06-03",
    organization_info=None,
    customer_info=None,
)
assert "<extraction_task>" in out
assert "<rules>" in out
assert "Test chat" in out
print("OK — template renders correctly")
```

```bash
python -c "
import sys; sys.path.insert(0, '.')
from jinja2 import Environment, FileSystemLoader
import json
env = Environment(loader=FileSystemLoader('templates'), trim_blocks=True, lstrip_blocks=True)
env.filters['jsonpretty'] = lambda v, indent=2: json.dumps(v, indent=indent)
tpl = env.get_template('extraction_xml_neutral.j2')
out = tpl.render(input_text='Test chat', schema_json='{\"type\": \"object\"}', few_shot_examples=[], attempt=1, iso_date='2026-06-03', organization_info=None, customer_info=None)
assert '<extraction_task>' in out
assert 'Test chat' in out
print('OK')
"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add templates/extraction_xml_neutral.j2
git commit -m "feat: add XML-neutral extraction template"
```

---

## Task 4: Create XML-neutral validation templates

**Files:**
- Create: `templates/validation_system_xml_neutral.j2`
- Create: `templates/validation_user_xml_neutral.j2`

The current validation templates use markdown checklists (optimised for Claude). These XML variants are structured for all providers.

- [ ] **Step 1: Create `templates/validation_system_xml_neutral.j2`**

```jinja2
You are a sales-order extraction validator. Your task is to audit and correct a structured JSON extraction. The chat transcript is the source of truth for every field.

<rules>
<rule id="no_invention">Do not add values not present in the chat. If a field is empty or null, only populate it from (a) an explicit statement in the chat, or (b) the vendor/counterparty reference blocks for the specific fields listed in rule 6. Leave all other empty fields empty.</rule>
<rule id="dont_fix_correct">Before changing any non-empty field, verify the chat contradicts it. If the chat supports the current value, leave it unchanged and do not log an issue.</rule>
<rule id="dates_frozen">Do not change po_date, do_date, or items[].shipment_date. Copy them exactly from the provided extraction JSON.</rule>
<rule id="unit_scale">Only adjust unit_price or pricing_unit when the chat itself explicitly states a different basis (e.g. chat says "USD 3.5 per KG" but extraction shows USD/MT). Arithmetic mismatch alone is not sufficient — you must cite the chat.</rule>
<rule id="verbatim">Do not reformat string fields. Copy packing, loading, shipping_method, billing_address, shipping_address, delivery_terms, description, vendor_name, ship_term verbatim from the extraction JSON unless the chat literally contradicts the value.</rule>
<rule id="reference_fields">You MAY fill these empty fields from reference data: vendor_name (from vendor block), billing_address and block-level shipping_address (from counterparty block), ONLY when empty in the extraction and the chat does not state a different value. Chat always wins over reference data.</rule>
<rule id="payment_date">payment_date must be a date or an explicit payment-term phrase from the chat (e.g. "Net 30 from delivery"). Never copy boilerplate like "Against scan copies of documents". If unsure, leave empty.</rule>
<rule id="log_changes">Every change you make must have a corresponding entry in the issues array with a chat quote in the suggestion field. If you make no changes, return the extraction unchanged with an empty issues list.</rule>
</rules>

{% if organization_info %}
<vendor_reference>
{{ organization_info | jsonpretty }}
</vendor_reference>
{% endif %}

{% if customer_info %}
<counterparty_reference>
{{ customer_info | jsonpretty }}
</counterparty_reference>
{% endif %}
```

- [ ] **Step 2: Create `templates/validation_user_xml_neutral.j2`**

```jinja2
<chat_transcript>
{{ source_text }}
</chat_transcript>

<extraction_to_validate>
{{ extraction_json | jsonpretty }}
</extraction_to_validate>

Audit the extraction against the chat transcript using the rules in your system prompt.

For each non-empty field: does the chat contradict it? If not, leave it unchanged.
For each empty field: does the chat explicitly state a value? If not, leave it empty. Exception: vendor_name, billing_address, and block-level shipping_address may be filled from reference blocks per rule 6.
Do not change po_date, do_date, or items[].shipment_date.
Every change must be logged in the issues array with a chat quote as evidence.

Return the corrected contract in the extraction field (SOExtractContractList shape with top-level data array), plus issues and optional notes. If nothing needed changing, return the input extraction unchanged and issues as an empty list.
```

- [ ] **Step 3: Smoke test both templates**

```bash
python -c "
import sys; sys.path.insert(0, '.')
from jinja2 import Environment, FileSystemLoader
import json
env = Environment(loader=FileSystemLoader('templates'), trim_blocks=True, lstrip_blocks=True)
env.filters['jsonpretty'] = lambda v, indent=2: json.dumps(v, indent=indent)

sys_tpl = env.get_template('validation_system_xml_neutral.j2')
sys_out = sys_tpl.render(organization_info={'name': 'Test Co'}, customer_info=None)
assert '<rules>' in sys_out
assert 'Test Co' in sys_out

usr_tpl = env.get_template('validation_user_xml_neutral.j2')
usr_out = usr_tpl.render(source_text='Chat here', extraction_json={'data': []})
assert '<chat_transcript>' in usr_out
assert 'Chat here' in usr_out

print('OK')
"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add templates/validation_system_xml_neutral.j2 templates/validation_user_xml_neutral.j2
git commit -m "feat: add XML-neutral validation templates"
```

---

## Task 5: Create schema-driven extraction template

**Files:**
- Create: `templates/extraction_schema_driven.j2`

Approach 3: the schema's enriched `Field(description=...)` carries most rules. The prompt is intentionally minimal — 3 key principles + the schema + the chat.

- [ ] **Step 1: Create `templates/extraction_schema_driven.j2`**

```jinja2
Extract a sales order from the chat transcript below.

Three rules:
1. Extract only terms both parties explicitly agreed to. Proposals and unanswered offers are not agreements.
2. If a field is not clearly stated in the chat, return null or empty string — never guess.
3. Preserve units, currencies, and string fields exactly as written in the chat — no conversion, no reformatting.

{% if organization_info or customer_info %}
<reference_context note="Use only to identify parties or fill vendor_name, billing_address, shipping_address when not stated in the chat.">
{% if organization_info %}
<vendor>{{ organization_info | jsonpretty }}</vendor>
{% endif %}
{% if customer_info %}
<counterparty>{{ customer_info | jsonpretty }}</counterparty>
{% endif %}
</reference_context>
{% endif %}

<schema>
{{ schema_json }}
</schema>

<chat>
{{ input_text }}
</chat>

Return only valid JSON matching the schema. No text before or after the JSON.
{% if attempt is defined and attempt > 1 %}

Retry {{ attempt }}: previous attempt failed schema validation. Ensure every required field is present (null or "" if not found). Check all types match the schema.
{% endif %}
```

- [ ] **Step 2: Smoke test**

```bash
python -c "
import sys; sys.path.insert(0, '.')
from jinja2 import Environment, FileSystemLoader
import json
env = Environment(loader=FileSystemLoader('templates'), trim_blocks=True, lstrip_blocks=True)
env.filters['jsonpretty'] = lambda v, indent=2: json.dumps(v, indent=indent)
tpl = env.get_template('extraction_schema_driven.j2')
out = tpl.render(input_text='Test chat', schema_json='{\"type\": \"object\"}', attempt=1, iso_date='2026-06-03', organization_info=None, customer_info=None)
assert 'Three rules' in out
assert 'Test chat' in out
print('OK')
"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add templates/extraction_schema_driven.j2
git commit -m "feat: add schema-driven (minimal) extraction template"
```

---

## Task 6: Update `prompt_builder.py` to route by strategy

**Files:**
- Modify: `core/prompt_builder.py`

Add `strategy` and `model_key` parameters to all three build functions. Route to the correct template. Default is `PromptStrategy.CURRENT` for backward compatibility.

- [ ] **Step 1: Write a failing test for strategy routing**

Add to `tests/test_prompt_strategy.py`:

```python
from core.prompt_builder import build_prompt, build_validation_system_prompt, build_validation_user_prompt
from core.prompt_strategy import PromptStrategy


def test_build_prompt_current_strategy_contains_extraction_rules():
    prompt = build_prompt(
        "Test chat",
        attempt=1,
        iso_date="2026-06-03",
        strategy=PromptStrategy.CURRENT,
    )
    assert "Extraction rules" in prompt or "extraction rules" in prompt.lower()


def test_build_prompt_xml_neutral_uses_xml_tags():
    prompt = build_prompt(
        "Test chat",
        attempt=1,
        iso_date="2026-06-03",
        strategy=PromptStrategy.XML_NEUTRAL,
    )
    assert "<extraction_task>" in prompt
    assert "<rules>" in prompt


def test_build_prompt_schema_driven_is_short():
    prompt = build_prompt(
        "Test chat",
        attempt=1,
        iso_date="2026-06-03",
        strategy=PromptStrategy.SCHEMA_DRIVEN,
    )
    assert "Three rules" in prompt
    assert len(prompt) < 3000  # schema-driven should be concise


def test_build_prompt_provider_profile_anthropic_uses_current():
    prompt = build_prompt(
        "Test chat",
        attempt=1,
        iso_date="2026-06-03",
        strategy=PromptStrategy.PROVIDER_PROFILE,
        model_key="sonnet-4-6",
    )
    assert "Extraction rules" in prompt or "extraction rules" in prompt.lower()


def test_build_prompt_provider_profile_openai_uses_xml():
    prompt = build_prompt(
        "Test chat",
        attempt=1,
        iso_date="2026-06-03",
        strategy=PromptStrategy.PROVIDER_PROFILE,
        model_key="openai:5.4",
    )
    assert "<extraction_task>" in prompt


def test_build_validation_system_xml_neutral():
    prompt = build_validation_system_prompt(strategy=PromptStrategy.XML_NEUTRAL)
    assert "<rules>" in prompt


def test_build_validation_system_current():
    prompt = build_validation_system_prompt(strategy=PromptStrategy.CURRENT)
    assert "<rules>" not in prompt or "Hard rules" in prompt


def test_build_validation_user_xml_neutral():
    prompt = build_validation_user_prompt(
        source_text="Chat here",
        extraction_json={"data": []},
        strategy=PromptStrategy.XML_NEUTRAL,
    )
    assert "<chat_transcript>" in prompt


def test_build_validation_user_current():
    prompt = build_validation_user_prompt(
        source_text="Chat here",
        extraction_json={"data": []},
        strategy=PromptStrategy.CURRENT,
    )
    assert "## Chat transcript" in prompt
```

- [ ] **Step 2: Run to confirm failures**

```bash
python -m pytest tests/test_prompt_strategy.py -k "build_prompt or build_validation" -v
```

Expected: `TypeError` — `build_prompt` does not accept `strategy` kwarg yet.

- [ ] **Step 3: Update `core/prompt_builder.py`**

Replace the entire file:

```python
import json
import logging
from pathlib import Path
from typing import Type

from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from pydantic import BaseModel

from core.db import DB_PATH, get_recent_success_examples, get_recent_update_examples
from core.models import SOExtractContractList, SOUpdateContractList
from core.prompt_strategy import PromptStrategy, provider_family
from core.utils import customer_info as utils_customer_info, team_info as utils_team_info

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
_env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), trim_blocks=True, lstrip_blocks=True)
_env.filters["jsonpretty"] = lambda value, indent=2: json.dumps(value, indent=indent, ensure_ascii=False)


INITIAL_SCHEMA: Type[BaseModel] = SOExtractContractList
UPDATE_SCHEMA: Type[BaseModel] = SOUpdateContractList

UPDATE_FEW_SHOT_DB_LIMIT = 5
UPDATE_FEW_SHOT_MAX_TOTAL = 18

INITIAL_FEW_SHOT_DB_LIMIT_DEFAULT = 5
INITIAL_FEW_SHOT_MAX_TOTAL = 18


def _extraction_template_name(strategy: PromptStrategy, model_key: str) -> str:
    """Return the Jinja2 template filename for the given strategy and model."""
    if strategy == PromptStrategy.XML_NEUTRAL:
        return "extraction_xml_neutral.j2"
    if strategy == PromptStrategy.SCHEMA_DRIVEN:
        return "extraction_schema_driven.j2"
    if strategy == PromptStrategy.PROVIDER_PROFILE:
        family = provider_family(model_key)
        if family in ("anthropic", "bedrock"):
            return "extraction.j2"
        return "extraction_xml_neutral.j2"
    return "extraction.j2"  # CURRENT


def _validation_system_template_name(strategy: PromptStrategy, model_key: str) -> str:
    if strategy == PromptStrategy.CURRENT:
        return "validation_system.j2"
    if strategy == PromptStrategy.PROVIDER_PROFILE:
        family = provider_family(model_key)
        if family in ("anthropic", "bedrock"):
            return "validation_system.j2"
        return "validation_system_xml_neutral.j2"
    return "validation_system_xml_neutral.j2"


def _validation_user_template_name(strategy: PromptStrategy, model_key: str) -> str:
    if strategy == PromptStrategy.CURRENT:
        return "validation_user.j2"
    if strategy == PromptStrategy.PROVIDER_PROFILE:
        family = provider_family(model_key)
        if family in ("anthropic", "bedrock"):
            return "validation_user.j2"
        return "validation_user_xml_neutral.j2"
    return "validation_user_xml_neutral.j2"


def build_system_prompt(
    organization_info: dict | None = None,
    customer_info: dict | None = None,
) -> str:
    """Render the system prompt with optional vendor/counterparty reference context."""
    try:
        template = _env.get_template("system_prompt.j2")
    except TemplateNotFound:
        raise FileNotFoundError(f"system_prompt.j2 not found in {_TEMPLATES_DIR}")

    prompt = template.render(
        organization_info=organization_info if organization_info is not None else utils_team_info,
        customer_info=customer_info if customer_info is not None else utils_customer_info,
    )
    logger.debug("Built system prompt (chars=%d)", len(prompt))
    return prompt


def build_prompt(
    input_text: str,
    attempt: int = 1,
    *,
    iso_date: str,
    organization_info: dict | None = None,
    customer_info: dict | None = None,
    extra_few_shot_examples: list[dict] | None = None,
    db_few_shot_limit: int = INITIAL_FEW_SHOT_DB_LIMIT_DEFAULT,
    db_path: Path = DB_PATH,
    strategy: PromptStrategy = PromptStrategy.CURRENT,
    model_key: str = "",
) -> str:
    """Build a Jinja2-rendered initial extraction prompt.

    The schema is locked to ``SOExtractContractList`` for the initial extraction flow.
    ``strategy`` selects the template variant; defaults to CURRENT for backward compat.
    """
    target_schema = INITIAL_SCHEMA
    template_name = _extraction_template_name(strategy, model_key)
    try:
        template = _env.get_template(template_name)
    except TemplateNotFound:
        raise FileNotFoundError(f"{template_name} not found in {_TEMPLATES_DIR}")

    schema_json = json.dumps(target_schema.model_json_schema(), indent=2)
    extra = list(extra_few_shot_examples or [])
    db_examples = (
        get_recent_success_examples(
            limit=db_few_shot_limit,
            schema_name=target_schema.__name__,
            db_path=db_path,
        )
        if db_few_shot_limit > 0
        else []
    )
    merged = extra + db_examples
    if len(merged) > INITIAL_FEW_SHOT_MAX_TOTAL:
        keep_extra = min(len(extra), INITIAL_FEW_SHOT_MAX_TOTAL)
        trimmed_extra = extra[:keep_extra]
        room = INITIAL_FEW_SHOT_MAX_TOTAL - len(trimmed_extra)
        merged = trimmed_extra + db_examples[: max(0, room)]

    prompt = template.render(
        input_text=input_text.strip(),
        schema_json=schema_json,
        few_shot_examples=merged,
        attempt=attempt,
        iso_date=iso_date,
        organization_info=organization_info,
        customer_info=customer_info,
    )

    logger.debug(
        "Built initial extraction prompt (attempt=%d, schema=%s, strategy=%s, chars=%d)",
        attempt, target_schema.__name__, strategy.value, len(prompt),
    )
    return prompt


def build_update_prompt(
    previous_summary: dict,
    update_instruction: str,
    original_input_text: str | None = None,
    attempt: int = 1,
    *,
    iso_date: str,
    organization_info: dict | None = None,
    customer_info: dict | None = None,
    synthetic_few_shot_examples: list[dict] | None = None,
    db_path: Path = DB_PATH,
) -> str:
    """Build the human-in-the-loop update prompt (always uses CURRENT template)."""
    target_schema = UPDATE_SCHEMA
    try:
        template = _env.get_template("update.j2")
    except TemplateNotFound:
        raise FileNotFoundError(f"update.j2 not found in {_TEMPLATES_DIR}")

    schema_json = json.dumps(target_schema.model_json_schema(), indent=2)
    previous_summary_json = json.dumps(previous_summary, indent=2, ensure_ascii=False)
    db_examples = get_recent_update_examples(limit=UPDATE_FEW_SHOT_DB_LIMIT, db_path=db_path)
    synth = list(synthetic_few_shot_examples or [])
    few_shot_examples = synth + db_examples
    if len(few_shot_examples) > UPDATE_FEW_SHOT_MAX_TOTAL:
        few_shot_examples = few_shot_examples[:UPDATE_FEW_SHOT_MAX_TOTAL]

    prompt = template.render(
        previous_summary_json=previous_summary_json,
        update_instruction=update_instruction.strip(),
        original_input_text=(original_input_text or "").strip() or None,
        schema_json=schema_json,
        few_shot_examples=few_shot_examples,
        attempt=attempt,
        iso_date=iso_date,
        organization_info=organization_info,
        customer_info=customer_info,
    )
    logger.debug(
        "Built update prompt (attempt=%d, schema=%s, chars=%d)",
        attempt, target_schema.__name__, len(prompt),
    )
    return prompt


def build_validation_system_prompt(
    organization_info: dict | None = None,
    customer_info: dict | None = None,
    strategy: PromptStrategy = PromptStrategy.CURRENT,
    model_key: str = "",
) -> str:
    """System prompt for the validation / post-processing LLM layer."""
    template_name = _validation_system_template_name(strategy, model_key)
    try:
        template = _env.get_template(template_name)
    except TemplateNotFound:
        raise FileNotFoundError(f"{template_name} not found in {_TEMPLATES_DIR}")
    return template.render(
        organization_info=organization_info if organization_info is not None else utils_team_info,
        customer_info=customer_info if customer_info is not None else utils_customer_info,
    )


def build_validation_user_prompt(
    source_text: str,
    extraction_json: dict,
    strategy: PromptStrategy = PromptStrategy.CURRENT,
    model_key: str = "",
) -> str:
    """User prompt for validation LLM: chat + current extraction JSON."""
    template_name = _validation_user_template_name(strategy, model_key)
    try:
        template = _env.get_template(template_name)
    except TemplateNotFound:
        raise FileNotFoundError(f"{template_name} not found in {_TEMPLATES_DIR}")
    return template.render(
        source_text=source_text.strip(),
        extraction_json=extraction_json,
    )
```

- [ ] **Step 4: Run the routing tests**

```bash
python -m pytest tests/test_prompt_strategy.py -v
```

Expected: All tests pass.

- [ ] **Step 5: Run the full test suite to check for regressions**

```bash
python -m pytest tests/ -v --tb=short -q
```

Expected: All existing tests still pass (the added `strategy` and `model_key` params have defaults).

- [ ] **Step 6: Commit**

```bash
git add core/prompt_builder.py tests/test_prompt_strategy.py
git commit -m "feat: route prompt_builder to correct template by strategy"
```

---

## Task 7: Thread strategy through `ExtractionEngine`

**Files:**
- Modify: `core/extractor.py`

The engine needs to accept a `strategy` and pass it to `build_prompt` and `build_validation_*`.

- [ ] **Step 1: Write a failing test**

Add to `tests/test_prompt_strategy.py`:

```python
from core.extractor import ExtractionEngine
from core.prompt_strategy import PromptStrategy


def test_extraction_engine_accepts_strategy():
    engine = ExtractionEngine(strategy=PromptStrategy.XML_NEUTRAL)
    assert engine.strategy == PromptStrategy.XML_NEUTRAL


def test_extraction_engine_default_strategy_is_current():
    engine = ExtractionEngine()
    assert engine.strategy == PromptStrategy.CURRENT
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_prompt_strategy.py::test_extraction_engine_accepts_strategy tests/test_prompt_strategy.py::test_extraction_engine_default_strategy_is_current -v
```

Expected: `TypeError` — `ExtractionEngine.__init__` does not accept `strategy`.

- [ ] **Step 3: Update `core/extractor.py`**

In `ExtractionEngine.__init__`, add `strategy: PromptStrategy = PromptStrategy.CURRENT` and store it. In the `run()` method, pass `strategy=self.strategy` and `model_key=self.model_key` to `build_prompt`. In the `ValidationLLMStage` call inside the postprocess pipeline, pass strategy via `StageContext`. 

Because the strategy needs to reach the validation stage, also update `StageContext` in `core/postprocess_stages.py` to carry it, and update `ValidationLLMStage.run()` to pass it to the validation prompt builders.

**`core/extractor.py` changes** — add import and update `__init__` and `_factory` closure in `run()`:

```python
# Add to imports at top of core/extractor.py:
from core.prompt_strategy import PromptStrategy

# In ExtractionEngine.__init__ signature, add:
#   strategy: PromptStrategy = PromptStrategy.CURRENT,
# And store:
#   self.strategy = strategy

# In ExtractionEngine.run(), update _factory:
#   def _factory(attempt: int) -> str:
#       return build_prompt(
#           text_to_extract,
#           attempt=attempt,
#           iso_date=self.iso_date,
#           organization_info=self.organization_info,
#           customer_info=self.customer_info,
#           extra_few_shot_examples=extra_few_shot_examples,
#           db_few_shot_limit=db_few_shot_limit,
#           db_path=self.db_path,
#           strategy=self.strategy,
#           model_key=self.model_key,
#       )
```

Apply the full patch to `core/extractor.py`:

```python
"""Extraction Engine — orchestrates the full pipeline:

    normalize -> build_prompt -> call_llm (instructor) -> return result

Schemas are locked:
- initial extraction always uses ``SOExtractContractList``
- summary updates always use ``SOUpdateContractList``

The engine does not write to the database. Persistence is the caller's
responsibility (typically the Streamlit UI's "Save" button via
:func:`core.db.save_summary`).

Retry logic (Tenacity) wraps the LLM call so transient validation or parsing
failures automatically re-run with a progressively clarified prompt.
"""

import json
import logging
import textwrap
from datetime import date
from pathlib import Path
from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError
from tenacity import (
    RetryError,
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

from core.chat_loader import load_synthetic_update_few_shot_examples
from core.db import DB_PATH, ExtractionResult, init_db
from core.llm_client import call_llm, call_llm_with_usage
from core.models import SOExtractContractList, SOUpdateContractList
from core.prompt_builder import (
    INITIAL_FEW_SHOT_DB_LIMIT_DEFAULT,
    build_prompt,
    build_system_prompt,
    build_update_prompt,
)
from core.prompt_strategy import PromptStrategy
from core.utils import DEFAULT_MODEL_KEY, resolve_model_selection

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_MAX_ATTEMPTS = 3
_CHUNK_THRESHOLD = 4_000


def _normalize(text: str) -> str:
    lines = text.splitlines()
    cleaned: list[str] = []
    blank_run = 0
    for line in lines:
        stripped = line.strip()
        if stripped == "":
            blank_run += 1
            if blank_run <= 1:
                cleaned.append("")
        else:
            blank_run = 0
            cleaned.append(stripped)
    return "\n".join(cleaned).strip()


def _chunk_text(text: str, max_chars: int = _CHUNK_THRESHOLD) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        if current_len + len(para) > max_chars and current:
            chunks.append("\n\n".join(current))
            current = []
            current_len = 0
        current.append(para)
        current_len += len(para)

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def _call_with_retry(
    schema: Type[T],
    model_key: str,
    prompt_factory,
    system_prompt: str | None,
) -> tuple[T, int, str, dict | None]:
    """Run prompt -> LLM -> validated model, retrying up to ``_MAX_ATTEMPTS`` times."""
    from core.token_usage import TokenUsage
    attempts_used = 0
    last_prompt = ""
    accumulated_usage: TokenUsage | None = None

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
        if usage:
            usage_obj = TokenUsage.from_dict(usage)
            accumulated_usage = usage_obj if accumulated_usage is None else accumulated_usage + usage_obj

        logger.info("Attempt %d succeeded", current_attempt)
        return result

    result = _attempt()
    return result, attempts_used, last_prompt, accumulated_usage.to_dict() if accumulated_usage else None


class ExtractionEngine:
    """Orchestrates the locked initial-extraction and summary-update flows.

    Schema selection is fixed:
    - :meth:`run` -> ``SOExtractContractList``
    - :meth:`update` -> ``SOUpdateContractList``
    """

    INITIAL_SCHEMA: Type[BaseModel] = SOExtractContractList
    UPDATE_SCHEMA: Type[BaseModel] = SOUpdateContractList

    def __init__(
        self,
        model_key: str = DEFAULT_MODEL_KEY,
        organization_info: dict | None = None,
        customer_info: dict | None = None,
        iso_date: str | None = None,
        db_path: Path = DB_PATH,
        strategy: PromptStrategy = PromptStrategy.CURRENT,
    ) -> None:
        self.model_key = model_key
        resolved = resolve_model_selection(model_key)
        self.model_provider = resolved["provider"]
        self.organization_info = organization_info
        self.customer_info = customer_info
        self.iso_date = iso_date if iso_date is not None else date.today().isoformat()
        self.db_path = Path(db_path).expanduser().resolve()
        self.strategy = strategy
        init_db(self.db_path)

    def run(
        self,
        input_text: str,
        schema: Type[BaseModel] | None = None,
        *,
        extra_few_shot_examples: list[dict] | None = None,
        db_few_shot_limit: int = INITIAL_FEW_SHOT_DB_LIMIT_DEFAULT,
    ) -> ExtractionResult:
        """Run the initial extraction pipeline and return the (un-persisted) result."""
        target_schema = self.INITIAL_SCHEMA
        normalized = _normalize(input_text)
        chunks = _chunk_text(normalized)
        chunk_count = len(chunks)
        chunk_truncated = chunk_count > 1

        if chunk_truncated:
            logger.warning(
                "Input split into %d chunks (total chars=%d); only chunk[0] (%d chars) is sent to the LLM",
                chunk_count, len(normalized), len(chunks[0]),
            )

        text_to_extract = chunks[0] if chunks else normalized

        system_prompt = build_system_prompt(
            organization_info=self.organization_info,
            customer_info=self.customer_info,
        )

        logger.info(
            "Starting initial extraction: schema=%s chars=%d strategy=%s",
            target_schema.__name__, len(text_to_extract), self.strategy.value,
        )

        def _factory(attempt: int) -> str:
            return build_prompt(
                text_to_extract,
                attempt=attempt,
                iso_date=self.iso_date,
                organization_info=self.organization_info,
                customer_info=self.customer_info,
                extra_few_shot_examples=extra_few_shot_examples,
                db_few_shot_limit=db_few_shot_limit,
                db_path=self.db_path,
                strategy=self.strategy,
                model_key=self.model_key,
            )

        try:
            result_model, attempts_used, final_prompt, token_usage = _call_with_retry(
                target_schema, self.model_key, _factory, system_prompt,
            )
            output_json = result_model.model_dump_json(indent=2)
            logger.info("Initial extraction succeeded after %d attempt(s)", attempts_used)
            return ExtractionResult(
                input_text=input_text,
                prompt_text=final_prompt,
                schema_name=target_schema.__name__,
                output_json=output_json,
                status="success",
                error=None,
                attempts=attempts_used,
                model_key=self.model_key,
                model_provider=self.model_provider,
                chunk_count=chunk_count,
                chunk_truncated=chunk_truncated,
                input_chars=len(normalized),
                token_usage=token_usage,
            )

        except (ValidationError, ValueError, json.JSONDecodeError, RetryError, Exception) as exc:
            error_msg = str(exc)
            logger.error("Initial extraction failed after %d attempt(s): %s", _MAX_ATTEMPTS, error_msg)
            return ExtractionResult(
                input_text=input_text,
                prompt_text=None,
                schema_name=target_schema.__name__,
                output_json=None,
                status="failed",
                error=error_msg,
                attempts=_MAX_ATTEMPTS,
                model_key=self.model_key,
                model_provider=self.model_provider,
                chunk_count=chunk_count,
                chunk_truncated=chunk_truncated,
                input_chars=len(normalized),
                token_usage=None,
            )

    def update(
        self,
        previous_summary: dict,
        update_instruction: str,
        original_input_text: str | None = None,
        *,
        include_synthetic_update_few_shot: bool = False,
        synthetic_update_few_shot_paths: list[Path] | None = None,
    ) -> ExtractionResult:
        """Apply a human update instruction to an existing summary."""
        target_schema = self.UPDATE_SCHEMA

        system_prompt = build_system_prompt(
            organization_info=self.organization_info,
            customer_info=self.customer_info,
        )

        normalized_chat = _normalize(original_input_text) if original_input_text else None

        logger.info(
            "Starting summary update: schema=%s previous_keys=%d instruction_chars=%d synthetic_few_shot=%s",
            target_schema.__name__,
            len(previous_summary or {}),
            len(update_instruction or ""),
            include_synthetic_update_few_shot,
        )

        synthetic_examples = (
            load_synthetic_update_few_shot_examples(paths=synthetic_update_few_shot_paths)
            if include_synthetic_update_few_shot
            else None
        )

        def _factory(attempt: int) -> str:
            return build_update_prompt(
                previous_summary=previous_summary,
                update_instruction=update_instruction,
                original_input_text=normalized_chat,
                attempt=attempt,
                iso_date=self.iso_date,
                organization_info=self.organization_info,
                customer_info=self.customer_info,
                synthetic_few_shot_examples=synthetic_examples,
                db_path=self.db_path,
            )

        try:
            result_model, attempts_used, final_prompt, token_usage = _call_with_retry(
                target_schema, self.model_key, _factory, system_prompt,
            )
            output_json = result_model.model_dump_json(indent=2)
            logger.info("Summary update succeeded after %d attempt(s)", attempts_used)
            return ExtractionResult(
                input_text=original_input_text or "",
                prompt_text=final_prompt,
                schema_name=target_schema.__name__,
                output_json=output_json,
                status="success",
                error=None,
                attempts=attempts_used,
                model_key=self.model_key,
                model_provider=self.model_provider,
                token_usage=token_usage,
            )

        except (ValidationError, ValueError, json.JSONDecodeError, RetryError, Exception) as exc:
            error_msg = str(exc)
            logger.error("Summary update failed after %d attempt(s): %s", _MAX_ATTEMPTS, error_msg)
            return ExtractionResult(
                input_text=original_input_text or "",
                prompt_text=None,
                schema_name=target_schema.__name__,
                output_json=None,
                status="failed",
                error=error_msg,
                attempts=_MAX_ATTEMPTS,
                model_key=self.model_key,
                model_provider=self.model_provider,
                token_usage=None,
            )
```

- [ ] **Step 4: Update `StageContext` and `ValidationLLMStage` to pass strategy**

In `core/postprocess_stages.py`, add `prompt_strategy` field to `StageContext` and thread it into `ValidationLLMStage.run()`:

```python
# In StageContext dataclass, add:
#   prompt_strategy: PromptStrategy = field(default=PromptStrategy.CURRENT)

# In ValidationLLMStage.run(), update the calls to:
#   system_prompt = build_validation_system_prompt(
#       organization_info=ctx.organization_info,
#       customer_info=ctx.customer_info,
#       strategy=ctx.prompt_strategy,
#       model_key=ctx.validation_model_key or "",
#   )
#   user_prompt = build_validation_user_prompt(
#       source_text=ctx.source_text,
#       extraction_json=contract,
#       strategy=ctx.prompt_strategy,
#       model_key=ctx.validation_model_key or "",
#   )
```

Apply the full change to `core/postprocess_stages.py` — only show the changed sections:

At top, add import:
```python
from core.prompt_strategy import PromptStrategy
```

In `StageContext` dataclass, add field after `customer_info`:
```python
prompt_strategy: PromptStrategy = field(default_factory=lambda: PromptStrategy.CURRENT)
```

In `ValidationLLMStage.run()`, replace the two prompt builder calls:
```python
system_prompt = build_validation_system_prompt(
    organization_info=ctx.organization_info,
    customer_info=ctx.customer_info,
    strategy=ctx.prompt_strategy,
    model_key=ctx.validation_model_key or "",
)
user_prompt = build_validation_user_prompt(
    source_text=ctx.source_text,
    extraction_json=contract,
    strategy=ctx.prompt_strategy,
    model_key=ctx.validation_model_key or "",
)
```

In `core/postprocess_pipeline.py`, update `StageContext` construction to pass `prompt_strategy`:
```python
ctx = StageContext(
    source_text=source_text,
    reference_iso_date=reference_iso_date,
    raw_contract=copy.deepcopy(raw_contract),
    extraction_model_key=extraction_model_key,
    validation_model_key=validation_model_key,
    organization_info=organization_info,
    customer_info=customer_info,
    prompt_strategy=prompt_strategy,  # NEW
)
```

And update `run_postprocess_pipeline` signature to accept `prompt_strategy`:
```python
def run_postprocess_pipeline(
    raw_contract: dict[str, Any],
    *,
    source_text: str,
    reference_iso_date: str,
    extraction_model_key: str,
    validation_model_key: str | None = None,
    enable_deterministic: bool = True,
    enable_validation_llm: bool = True,
    organization_info: dict | None = None,
    customer_info: dict | None = None,
    stages: list[PostprocessStage] | None = None,
    prompt_strategy: "PromptStrategy | None" = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
```

And resolve the strategy in the function body:
```python
from core.prompt_strategy import PromptStrategy as _PS
_strategy = prompt_strategy if prompt_strategy is not None else _PS.CURRENT
```

- [ ] **Step 5: Run the tests**

```bash
python -m pytest tests/test_prompt_strategy.py -v
python -m pytest tests/ -v --tb=short -q
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add core/extractor.py core/postprocess_stages.py core/postprocess_pipeline.py tests/test_prompt_strategy.py
git commit -m "feat: thread PromptStrategy through ExtractionEngine and postprocess pipeline"
```

---

## Task 8: Pass strategy from agent → runner

**Files:**
- Modify: `agents/so_extraction/agent.py`
- Modify: `harness/runner.py`

- [ ] **Step 1: Update `agents/so_extraction/agent.py`**

In `run_one()`, read `prompt_strategy` from `options.extra` and pass it to `ExtractionEngine` and `run_postprocess_pipeline`:

```python
# At top of agent.py, add import:
from core.prompt_strategy import PromptStrategy

# In run_one(), after building engine_kwargs, add:
strategy_str = options.extra.get("prompt_strategy", "current")
strategy = PromptStrategy.from_str(strategy_str)
engine_kwargs["strategy"] = strategy

# In the run_postprocess_pipeline call, add:
# prompt_strategy=strategy,
```

Full updated `run_one` relevant section (replace from `engine_kwargs` construction to `run_postprocess_pipeline` call):

```python
        from core.prompt_strategy import PromptStrategy
        strategy_str = options.extra.get("prompt_strategy", "current")
        strategy = PromptStrategy.from_str(strategy_str)

        t0 = time.perf_counter()
        engine_kwargs: dict[str, Any] = {
            "model_key": options.model_key,
            "strategy": strategy,
        }
        if db_path is not None:
            engine_kwargs["db_path"] = Path(db_path)
        if organization_info:
            engine_kwargs["organization_info"] = organization_info
        if customer_info:
            engine_kwargs["customer_info"] = customer_info
        engine = ExtractionEngine(**engine_kwargs)
```

And in the `run_postprocess_pipeline` call, add `prompt_strategy=strategy`:

```python
            final_dict, diagnostics = run_postprocess_pipeline(
                raw_dict,
                source_text=input_payload.text,
                reference_iso_date=engine.iso_date,
                extraction_model_key=options.model_key,
                validation_model_key=validation_model_key,
                enable_deterministic=pp_opts["enable_deterministic"],
                enable_validation_llm=pp_opts["enable_validation_llm"],
                organization_info=organization_info,
                customer_info=customer_info,
                prompt_strategy=strategy,
            )
```

- [ ] **Step 2: Update `harness/runner.py`**

Add `--prompt-strategy` CLI argument and include it in `_run_extra()`:

In `_parse_args()`, after the `--report-story-model` argument, add:

```python
    p.add_argument(
        "--prompt-strategy",
        type=str,
        default="current",
        choices=["current", "xml_neutral", "provider_profile", "schema_driven"],
        help="Prompt template strategy: current (default), xml_neutral, provider_profile, schema_driven.",
    )
```

In `_run_extra()`, add `prompt_strategy` to the returned dict:

```python
def _run_extra(args: argparse.Namespace, extraction_model_key: str) -> dict[str, Any]:
    validation_key = (args.validation_model or "").strip() or extraction_model_key
    return {
        "db_few_shot_limit": args.db_few_shot_limit,
        "validation_model_key": validation_key,
        "enable_validation_llm": True,
        "enable_deterministic_postprocess": True,
        "run_baseline": bool(getattr(args, "with_baseline", False)),
        "prompt_strategy": getattr(args, "prompt_strategy", "current"),
    }
```

- [ ] **Step 3: Verify help text**

```bash
python harness/runner.py --help | grep prompt-strategy
```

Expected: `--prompt-strategy {current,xml_neutral,provider_profile,schema_driven}`

- [ ] **Step 4: Run the full test suite**

```bash
python -m pytest tests/ -v --tb=short -q
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add agents/so_extraction/agent.py harness/runner.py
git commit -m "feat: add --prompt-strategy CLI flag and pass strategy end-to-end"
```

---

## Task 9: Smoke-test each strategy with a real chat

**Files:**
- No new files — this is a manual verification step

- [ ] **Step 1: Find a sample chat to test with**

```bash
ls raw_data/chats/*.json | head -3
```

Note one path, e.g. `raw_data/chats/sample_chat.json`.

- [ ] **Step 2: Run each strategy against the sample chat with sonnet-4-6**

```bash
# CURRENT (baseline check — must work)
python harness/runner.py --agent so_extraction \
  --chat raw_data/chats/$(ls raw_data/chats/*.json | head -1 | xargs basename) \
  --models sonnet-4-6 \
  --prompt-strategy current \
  --with-baseline \
  --no-report-llm

# XML_NEUTRAL
python harness/runner.py --agent so_extraction \
  --chat raw_data/chats/$(ls raw_data/chats/*.json | head -1 | xargs basename) \
  --models sonnet-4-6 \
  --prompt-strategy xml_neutral \
  --no-report-llm

# PROVIDER_PROFILE
python harness/runner.py --agent so_extraction \
  --chat raw_data/chats/$(ls raw_data/chats/*.json | head -1 | xargs basename) \
  --models sonnet-4-6 \
  --prompt-strategy provider_profile \
  --no-report-llm

# SCHEMA_DRIVEN
python harness/runner.py --agent so_extraction \
  --chat raw_data/chats/$(ls raw_data/chats/*.json | head -1 | xargs basename) \
  --models sonnet-4-6 \
  --prompt-strategy schema_driven \
  --no-report-llm
```

Expected: All four runs complete successfully with `status: success`. No crashes.

- [ ] **Step 3: Commit**

```bash
git commit --allow-empty -m "chore: smoke-tested all four prompt strategies successfully"
```

---

## Task 10: Run full multi-model benchmark across all strategies

**Files:**
- No code changes — run the harness for the experiment

This produces one results folder per strategy. Compare the reports to determine which strategy achieves the most consistent accuracy across models.

- [ ] **Step 1: Run CURRENT strategy (control group)**

```bash
python harness/runner.py --bulk \
  --agent so_extraction \
  --models sonnet-4-6 opus-4-6 openai:5.4 openai:5.2 gemini:gemini-2.5-pro \
  --prompt-strategy current \
  --with-baseline \
  --runs-per-chat 1 \
  --no-report-llm
```

Note the `results/<run_id>/` folder produced.

- [ ] **Step 2: Run XML_NEUTRAL strategy**

```bash
python harness/runner.py --bulk \
  --agent so_extraction \
  --models sonnet-4-6 opus-4-6 openai:5.4 openai:5.2 gemini:gemini-2.5-pro \
  --prompt-strategy xml_neutral \
  --with-baseline \
  --runs-per-chat 1 \
  --no-report-llm
```

- [ ] **Step 3: Run PROVIDER_PROFILE strategy**

```bash
python harness/runner.py --bulk \
  --agent so_extraction \
  --models sonnet-4-6 opus-4-6 openai:5.4 openai:5.2 gemini:gemini-2.5-pro \
  --prompt-strategy provider_profile \
  --with-baseline \
  --runs-per-chat 1 \
  --no-report-llm
```

- [ ] **Step 4: Run SCHEMA_DRIVEN strategy**

```bash
python harness/runner.py --bulk \
  --agent so_extraction \
  --models sonnet-4-6 opus-4-6 openai:5.4 openai:5.2 gemini:gemini-2.5-pro \
  --prompt-strategy schema_driven \
  --with-baseline \
  --runs-per-chat 1 \
  --no-report-llm
```

- [ ] **Step 5: Compare results**

Open all four `results/<run_id>/report.html` files. The winning strategy is the one where:
1. The gap between the highest and lowest model accuracy (raw_pct) is smallest.
2. No individual model regresses below its CURRENT raw_pct score.

---

## Self-Review

**Spec coverage check:**
- ✅ `PromptStrategy` enum with all four values → Task 1
- ✅ Enriched field descriptions for schema-driven → Task 2
- ✅ XML-neutral extraction template (Approach 1 + Approach 2 non-Anthropic) → Task 3
- ✅ XML-neutral validation templates → Task 4
- ✅ Schema-driven extraction template (Approach 3) → Task 5
- ✅ `prompt_builder` routing by strategy → Task 6
- ✅ Strategy threaded through `ExtractionEngine` → Task 7
- ✅ Strategy threaded through postprocess pipeline (validation uses strategy) → Task 7
- ✅ `--prompt-strategy` CLI flag → Task 8
- ✅ Agent reads strategy from `options.extra` → Task 8
- ✅ End-to-end smoke test per strategy → Task 9
- ✅ Full benchmark across all models and all strategies → Task 10

**Placeholder scan:** No TBDs, no "implement later", all code blocks contain actual runnable code.

**Type consistency check:**
- `PromptStrategy.from_str()` used in Tasks 1, 6, 7, 8 — consistent
- `provider_family()` used in Tasks 1, 6 — consistent
- `build_prompt(..., strategy=PromptStrategy, model_key=str)` — consistent across Tasks 6, 7
- `build_validation_system_prompt(..., strategy=, model_key=)` — consistent Tasks 6, 7
- `run_postprocess_pipeline(..., prompt_strategy=)` — consistent Tasks 7, 8
- `StageContext.prompt_strategy` — set in pipeline, read in ValidationLLMStage — consistent
