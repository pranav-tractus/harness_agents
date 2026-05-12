# Agent Harness

The repo is organized around a small set of pluggable **agents**, each owning
its own dataset, few-shot pool, expected-results file, and scoring logic. A
single **runner** drives single-chat runs, bulk sweeps, and pipelines. A single
**dashboard** is the Streamlit UI for everything.

## Repo layout

```
agents/
├── base.py                         BaseAgent[I, O] + Pipeline
├── config.py                       configs/agents.json loader
├── so_extraction/                  Agent 1: chat -> SOExtractContractList
│   ├── agent.py
│   ├── expected_results.py
│   └── data_gen/                   synthetic + realistic chat generators
└── product_retrieval/              Agent 2 (scaffold): summary -> ranked spec docs
    ├── agent.py
    ├── expected_results.py
    └── README.md

core/                               LLM-agnostic primitives (models, prompts, db, ...)
harness/
├── runner.py                       unified single + bulk + pipeline runner
├── scoring.py                      json_diff + retrieval_metrics
├── artifacts.py                    one folder per run (run.jsonl, aggregate.json, report.html, config.json)
├── seed_expected.py                helper to draft new expected_results entries
└── auto_expected.py                automatic writer for expected_results.py (best-of-N + AST rewrite)

dashboard/app.py                    Streamlit (Single Run / Bulk / Results / Seed)

configs/agents.json                 declarative agent + dataset + pipeline config
raw_data/                           chat sources (per dataset)
results/<run_id>/                   one folder per harness run
```

## Configure agents

[configs/agents.json](../configs/agents.json) declares every agent, its
datasets (file globs), per-dataset DB paths and customer info, the few-shot
pool, and any chained pipelines. Schema highlights:

- `agents[].id` — unique agent id (`so_extraction`, `product_retrieval`, ...)
- `agents[].module` — `pkg.mod:ClassName` of the `BaseAgent` subclass
- `agents[].datasets[]` — `{id, chat_globs?, doc_globs?, db_path?, organization_info?, customer_info?}`
- `agents[].few_shot_globs` — glob patterns for the agent's allowed few-shot pool
- `agents[].consumes_output_of` — name of the upstream agent (for chained pipelines)
- `pipelines[]` — `{id, steps: [agent_id, ...]}`

## Run a single chat

```bash
python main.py --agent so_extraction \
  --chat raw_data/chats/single_product_single_shipment_simple.json \
  --few-shot raw_data/customers/acme_foods/chats/fs_acme_simple.json
```

Outputs go to `results/<run_id>/{run.jsonl,aggregate.json,report.html,config.json}`.

## Run a pipeline

```bash
python main.py --pipeline so_then_retrieval \
  --chat raw_data/chats/single_product_single_shipment_simple.json
```

The retrieval agent ships as a scaffold — plug your retrieval backend into
[agents/product_retrieval/agent.py](../agents/product_retrieval/agent.py) when
ready. The pipeline runs the extraction step regardless; the retrieval step
currently fails fast with `not_implemented` so the plumbing is testable.

## Bulk benchmark with few-shot sweep

```bash
python main.py --agent so_extraction --bulk \
  --datasets acme_foods nova_exports \
  --few-shot-sweep 0 1 3 5 10 \
  --few-shot-seed 42 \
  --models sonnet-4-6 gpt-5-mini gemini-2-5-pro \
  --runs-per-chat 2 --max-workers 8 \
  --skip-without-expected
```

All variants land in **one** results folder per invocation. Comparing variants
across multiple runs is done in the dashboard's Results Browser tab.

### Multiple models

Pass `--models m1 m2 m3` (or pick several in the dashboard's Models multiselect)
to test multiple models in the same run. Every `(source × model × few-shot
variant × run)` combination is submitted as a future on the same
`ThreadPoolExecutor`, so models run concurrently up to `--max-workers`.

### Few-shot sweep semantics

For each agent the few-shot **pool** is exactly the union of
`agents[].few_shot_globs` from `configs/agents.json` (for `so_extraction` this
is every chat JSON under `raw_data/`). When `--few-shot-sweep` is set the
runner:

1. Calls `agent.few_shot_pool()` to materialise the candidate paths.
2. Shuffles that pool **once** with `--few-shot-seed` (default `42`).
3. For each requested count `c`, takes the **prefix of length `c`** of the
   shuffled pool. This guarantees that the count=2 set is a subset of count=5,
   which is a subset of count=10 — so sweeps are interpretable.
4. By default, drops the source-under-test from its own variant to prevent
   leakage. Pass `--allow-self-fewshot` to disable that guard.

Each run persists the resolved few-shot files into `results/<run_id>/config.json`
under `few_shot_variants[].paths`, so any artifact can be replayed exactly.
The dashboard's Bulk Benchmark tab shows a live "Preview few-shot variants"
panel that renders the same plan before launch.

### Curating the few-shot pool

By default sweep variants are sampled from the agent's full
`few_shot_pool()`. To restrict sampling to a hand-picked subset for a run,
pass `--few-shot-pool <path> [<path> ...]`:

```bash
python main.py --agent so_extraction --bulk \
  --datasets acme_foods \
  --few-shot-sweep 0 2 5 \
  --few-shot-pool \
    raw_data/customers/acme_foods/chats/realistic_acme_foods_001.json \
    raw_data/customers/acme_foods/chats/realistic_acme_foods_002.json \
    raw_data/customers/acme_foods/chats/fs_acme_simple.json
```

Behaviour:

- Missing paths are warn-and-skipped (same convention as `--few-shot`).
- The curated pool composes with `--few-shot-sweep` (nested sampling still
  applies, just over this smaller pool) and with `--allow-self-fewshot`
  (source-under-test exclusion runs **after** pool curation).
- `--few-shot` (explicit single variant) still wins over `--few-shot-pool`;
  the curated pool only affects sweep variants.
- The resolved curated list lands in `results/<run_id>/config.json` under
  `few_shot_pool_override` for reproducibility.

The dashboard's Bulk Benchmark tab exposes the same control as a
**"Curate few-shot pool (optional)"** multiselect right next to the explicit
picker; the live "Preview few-shot variants" panel re-samples against the
curated pool so you see exactly what each `fs<count>` variant will use before
launching.

### Deterministic walk over hand-picked chats

When you want to know exactly which chats contribute to each variant — no
shuffling, no sampling — use `--few-shot-walk`. Pass an **ordered** list of
chats and the runner builds variants `fs0=[]`, `fs1=[A]`, `fs2=[A, B]`, …,
`fs<N>=[A, B, …, N]`:

```bash
python main.py --agent so_extraction --bulk \
  --datasets acme_foods \
  --few-shot-walk \
    raw_data/customers/acme_foods/chats/fs_acme_simple.json \
    raw_data/customers/acme_foods/chats/realistic_acme_foods_001.json \
    raw_data/customers/acme_foods/chats/realistic_acme_foods_002.json
```

The example above produces four variants per chat (`fs0..fs3`). Behaviour:

- Order is preserved exactly — pick the chats in the order you want them
  introduced, smallest variant first.
- Capped at 10 picks (so at most `fs0..fs10`).
- Duplicates and missing paths are silently dropped (with a warning for
  missing ones).
- Wins over `--few-shot-sweep` and `--few-shot-pool`. Still loses to
  `--few-shot` (single explicit variant).
- `--allow-self-fewshot` still applies, so a picked chat that happens to be
  the source-under-test is dropped from that source's run unless you opt in.
- The persisted plan in `results/<run_id>/config.json` reports
  `few_shot_mode: "walk"` plus the full `few_shot_variants[].paths` list.

The dashboard's Bulk Benchmark tab exposes this as a **"Walk over selected
chats (0..N, in order)"** multiselect; the live preview panel renders the
exact `fs0..fsN` plan before launch.

## Seed expected results

Each agent owns its own `expected_results.py`. Two helpers cover the two
typical workflows:

**Manual review (draft only, no writes)** — print paste-ready blocks + diffs:

```bash
python -m harness.seed_expected --agent so_extraction \
  --source raw_data/customers/acme_foods/chats/realistic_acme_foods_001.json \
  --runs 2
```

**Automatic apply (best-of-N + AST rewrite)** — write directly into
`agents/<agent>/expected_results.py`:

```bash
# Backfill every chat in a dataset that doesn't yet have an expected entry.
python -m harness.auto_expected --agent so_extraction \
  --dataset acme_foods --only-missing --runs 3 --backup

# Refresh one chat (replacing the existing entry, with a .py.bak backup).
python -m harness.auto_expected --agent so_extraction \
  --source raw_data/chats/single_product_single_shipment_simple.json \
  --overwrite-existing --backup

# Show what would change without writing anything.
python -m harness.auto_expected --agent so_extraction --all --dry-run

# Reuse outputs from a prior benchmark instead of re-running the LLM.
python -m harness.auto_expected --agent so_extraction \
  --from-jsonl results/<run_id>/run.jsonl --only-missing
```

The rewriter is AST-based, so it preserves the module docstring, helper
functions (e.g. `get_expected_for_chat`), and any custom comments outside the
`EXPECTED_BY_CHAT` assignment. The default policy is conservative: existing
entries are never overwritten unless you pass `--overwrite-existing`.

## Generate synthetic chats

```bash
python -m agents.so_extraction.data_gen.generate_customer_chats \
  --config configs/agents.json --count-per-customer 10

python -m agents.so_extraction.data_gen.generate_realistic_chats \
  --config configs/agents.json --count-per-customer 10 --seed 42
```

Files land under each customer dataset's `chats/` folder, with `realism_flags`
metadata for the dashboard's filtering tools.

## Dashboard

```bash
streamlit run dashboard/app.py
```

Tabs:

- **Single Run** — pick agent + chat + 0..10 few-shot files; runs the agent (or
  pipeline) and shows the structured output, mismatches against expected, and
  a Save-to-DB button.
- **Bulk Benchmark** — configure a sweep and shell out to `python -m harness.runner`.
- **Results Browser** — point at one or more `results/<run_id>/` folders and
  see leaderboards, per-chat breakdowns, and mismatch detail.
- **Seed Expected** — interactive UI on top of `harness.seed_expected`.

## Adding the next agent

1. Subclass `BaseAgent[I, O]` under `agents/<your_agent>/agent.py` and
   implement `load_input`, `run_one`, `expected_for`, `score`.
2. Add an `expected_results.py` alongside it.
3. Register the agent in [configs/agents.json](../configs/agents.json) with
   its datasets, few-shot pool, and (optionally) `consumes_output_of` plus a
   new `pipelines[]` entry.
4. Pick a scorer (`harness.scoring.json_diff`, `harness.scoring.retrieval_metrics`,
   or a new helper).
5. Run via `python main.py --agent <your_agent>` — the runner / dashboard /
   seed helper all pick it up for free.
