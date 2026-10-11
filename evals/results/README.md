# Saved experiments

The live provider for these runs is OpenAI. A scripted demo screenshot is UI evidence, not model evaluation evidence.

| Directory | Purpose | Use in the architecture decision |
|---|---|---|
| `openai-repeats-20261011/` | Same 18 cases, three trials per architecture on the current source, paired order with seed 42 | **Main evidence for the ship decision**; see its case analysis |
| `openai-comparison-20261008/` | Same 18 cases, one trial per architecture, on the earlier source | First experiment; consistent with the replication, shown in the app's benchmark view |
| `openai-precision-live-20261008/` | Four trials after the money-precision fix, covering SYN-12 and SYN-13 on both architectures | Targeted verification only; excluded from main comparison metrics |
| `pilot-openai-live-20261008/` | One simple case through each architecture, confirming live tool calls and structured outputs | Integration check only; excluded from the main metrics |

The live pilot used an earlier source fingerprint; the main experiment records its own source and settings.

Each directory contains `manifest.json`, a readable `summary.md`, machine-readable `summary.json`, per-run `runs.csv`, full `decisions.jsonl`, and an append-only trial checkpoint. The response IDs in the traces establish which OpenAI responses contributed to each result; credentials and encrypted reasoning are excluded.

The experiment's `git_dirty` field may be true because result files and documentation are created during the run. For model-behaviour reproducibility, compare `source_sha256` in the manifest and summary: it covers the agent code, tools, policy/data, labelled cases, evaluation runner and dependency lockfile. UI screenshots and documentation are outside that fingerprint.
