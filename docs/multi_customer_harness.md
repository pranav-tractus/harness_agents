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
└── seed_expected.py                helper to draft new expected_results entries

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
  --models sonnet-4-6 \
  --runs-per-chat 2 --max-workers 8 \
  --skip-without-expected
```

All variants land in **one** results folder per invocation. Comparing variants
across multiple runs is done in the dashboard's Results Browser tab.

## Seed expected results

`raw_data/expected_results.py` (and each agent's `expected_results.py`) stay
manually curated. Use the helper to draft entries:

```bash
python -m harness.seed_expected --agent so_extraction \
  --source raw_data/customers/acme_foods/chats/realistic_acme_foods_001.json \
  --runs 2
```

The helper prints a Python literal ready to paste into `EXPECTED_BY_CHAT` and a
field-by-field diff against any existing entry. Nothing is auto-written.

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
