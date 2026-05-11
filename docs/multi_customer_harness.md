# Multi-customer Harness

This repo now supports customer-scoped simulation runs with isolated SQLite DBs,
customer-specific few-shot datasets, and customer-aware benchmark visualization.

## 1) Configure customers

Use JSON config like `configs/customers.sample.json`:

- `customers[].id`: unique customer id
- `customers[].db_path`: SQLite file path for that customer
- `customers[].dataset_root`: root folder containing customer datasets
- `customers[].chat_globs`: chat file globs under `dataset_root`
- `customers[].few_shot.paths`: explicit few-shot files
- `customers[].synthetic_generation`: generation settings

## 2) Generate customer-specific chats

```bash
python tests/generate_customer_chats.py --harness-config configs/customers.sample.json
```

This creates files under each customer's `dataset_root/chats/` and includes
`customer_id`, `scenario_tags`, and `complexity_tier` metadata.

### 2b) Generate operationally-realistic chats

For tougher, more realistic test cases (long threads, noisy text, missing
prices, contradictory instructions, multi-language snippets):

```bash
python tests/generate_realistic_chats.py \
  --harness-config configs/customers.sample.json \
  --count-per-customer 10 \
  --seed 42
```

Each generated file carries a `realism_flags` list (e.g. `["noisy_text",
"contradictory"]`) at the top level. The dashboard reads this and exposes a
"Realism flags" filter plus a "Realism Flag Breakdown" section that surfaces
the hardest and easiest realism flavors for the current run set.

Subset by flavor (e.g. only contradictory + multilingual):

```bash
python tests/generate_realistic_chats.py \
  --harness-config configs/customers.sample.json \
  --flavors contradictory multilingual
```

## 3) Run benchmark across customers

```bash
python tests/benchmark_fewshot.py --harness-config configs/customers.sample.json --runs-per-chat 2
```

Optional subset:

```bash
python tests/benchmark_fewshot.py --harness-config configs/customers.sample.json --customers acme_foods
```

## 4) Visualize by customer and generation flow

```bash
streamlit run tests/fewshot_dashboard.py
```

Use customer filters and the `Generation Flow Timeline` table to inspect stage
timings (`chat_load_ms`, `fewshot_plan_ms`, `model_run_ms`, `total_case_ms`).

## 5) CLI and app customer scoping

- CLI:
  - `python main.py --harness-config configs/customers.sample.json --customer acme_foods --file ...`
- App:
  - In sidebar, provide `Harness config (JSON)` and choose a customer.
  - The selected customer scopes DB path used by extraction/update runs.
