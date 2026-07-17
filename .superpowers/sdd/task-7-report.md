# Task 7 Report: Wire context assembly into `command_service`

## Status

Completed and committed as `215ce5a feat(api): ground sales-order summaries in assembled graph context`.

## Implementation

- Added injectable `context_fn=None` to `command_service.dispatch`; its default is
  `summary_context_service.assemble`.
- Threaded `context_fn` into `_create` and `_edit`.
- Both paths now assemble graph context using the customer ID and forward
  `product_block`, `profile_block`, and `history_block` to the summary generator
  or reviser.
- Removed the obsolete Mongo-backed `_product_catalog()` helper.
- Made command-service tests hermetic through `_ctx` injection and added dedicated
  create/edit forwarding assertions.
- Stubbed `summary_context_service.assemble` in the endpoint `client` fixture so
  command endpoint tests do not access the filesystem-backed assembler.

## TDD evidence

### RED

Command:

```bash
PYTHONPATH=. pytest tests/api/test_command_service.py tests/api/test_api_endpoints.py -v
```

Result: expected failure. All six command-service tests failed with
`TypeError: dispatch() got an unexpected keyword argument 'context_fn'`; the
endpoint tests errored because `command_service.summary_context_service` was not
yet imported.

### GREEN

Command:

```bash
PYTHONPATH=. pytest tests/api/test_command_service.py tests/api/test_api_endpoints.py -v
```

Result: `22 passed, 1 warning in 1.18s`.

## Full API suite

Command:

```bash
PYTHONPATH=. pytest tests/api -v
```

Result: `45 passed, 1 warning in 3.48s`. The warning is the pre-existing
Starlette `python_multipart` pending-deprecation warning.

## Files changed

- `apps/api/services/command_service.py`
- `tests/api/test_command_service.py`
- `tests/api/test_api_endpoints.py`

## Self-review

- Verified `context_fn` has the required default and is injected into both
  create and edit flows.
- Verified graph completion still precedes context assembly and generation.
- Verified all three context blocks are forwarded under the required positional
  and keyword arguments.
- Verified pending-summary guards remain before context assembly.
- Verified `_product_catalog()` has been removed.

## Concerns

None. The repository has unrelated pre-existing modified and untracked files;
the commit contains only the three Task 7 files.

## Final-review fixes

### What changed

- Product create, update, and delete now log and swallow graph-sync failures
  after their MongoDB writes, preserving the existing CRUD responses.
- Added endpoint-resilience coverage for failed create and delete graph syncs.
- Added `ORDER BY s.key`, `ORDER BY a.name`, and `ORDER BY a.key` to make
  catalog and profile graph text deterministic.

### RED/GREEN evidence

RED command:

```bash
PYTHONPATH=. pytest tests/api/test_api_endpoints.py -k 'succeeds_when_graph_sync_fails' -v
```

Result: expected failure — `2 failed, 16 deselected, 1 warning in 1.55s`;
the unguarded `resync_product` and `remove_product` calls raised
`RuntimeError: graph unavailable`.

GREEN is included in the covering run below; both new endpoint-resilience tests
passed.

### Covering tests

Command:

```bash
PYTHONPATH=. pytest tests/api/test_api_endpoints.py tests/api/test_product_graph_service.py tests/api/test_profile_graph_service.py -v
```

Output: `27 passed, 1 warning in 3.56s`.

### Full API suite

Command:

```bash
PYTHONPATH=. pytest tests/api -q
```

Output: `47 passed, 1 warning in 3.27s`. The warning is the existing Starlette
`python_multipart` pending-deprecation warning.

### Concerns

None.
