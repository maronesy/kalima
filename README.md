# Kalima

**A neural-symbolic prover that divides a goal into subgoals for automated provers — every step checked by Rocq.**

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-%E2%89%A53.10-blue)
![Status](https://img.shields.io/badge/status-early-orange)

Kalima follows the design of [HyperTree Proof Search](https://arxiv.org/abs/2205.11491): a
neural model *states subgoals*, and symbolic provers (Rocq's automation and CoqHammer with
Vampire and E) prove them. **The model never writes a proof step.** A goal counts as proved
only when Rocq compiles the assembled proof from scratch — with nothing assumed beyond the
declared starting points and the law of excluded middle.

Kalima is developed at the [al-Kalam Institute](https://alkalam.org) for **algorithmic
theology**: testing classical arguments of Islamic theology by machine. Its benchmark,
**Kalam-20**, is the twenty steps of two arguments for a first cause — *dalīl al-kalima* and
*dalīl al-imkān* ([`benchmarks/kalam20/`](benchmarks/kalam20/)). Results, proofs, and
interactive search replays are published at **[at.alkalam.org/kalima](https://at.alkalam.org/kalima)**.

---

## How it works

Kalima divides the labour strictly, so the machine proof never depends on the language model
being right — only on it being *useful*:

| Part | Role | Code |
|---|---|---|
| **Proposer** (neural) | States subgoals. Never writes proof steps. | [`kalima/proposers/`](kalima/proposers/) |
| **Provers** (symbolic) | Prove every goal, subgoal, and combination. | [`kalima/provers/leaf.py`](kalima/provers/leaf.py) |
| **Search** | Divides, recurses, retries with feedback, assembles the proof. | [`kalima/search/decompose.py`](kalima/search/decompose.py) |
| **Checker** | Rocq compiles the assembled proof from scratch. | [`kalima/provers/leaf.py`](kalima/provers/leaf.py) |

An AND-OR search over one goal:

```
 goal ──▶ provers try it? ──yes──▶ proved ✓
            │ no
            ▼
   proposer states ≤2 divisions, each 2–4 subgoals        [neural]
            │
   a division is accepted only if the provers
   derive the goal from its subgoals                      [symbolic]
            │
   each subgoal of an accepted division becomes
   a new goal ───────────────▶ (recurse, depth ≤ 4)
            │
   assemble the lemmas ──▶ Rocq compiles from scratch
            │
   Print Assumptions ⊆ { excluded middle }  ──▶  proved ✓
```

If every division fails, the proposer is asked again (up to three times) and shown the failed
divisions and *why* each failed. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the
full account and the fixed prover list.

## Status

**Early, and the results are real.** The search, the provers, and the benchmark all work.
Kalima has run in two versions, and a third is in training:

1. **Version 1 — our own model.** A small code model, **Qwen2.5-Coder-0.5B**, that we
   fine-tuned for the task (LoRA + expert iteration, on a laptop). It works — it even proved
   one step the symbolic tools alone could not — but overall it lands about at the level of
   the provers alone.
2. **Version 2 — Claude, as released.** **Claude Sonnet 5.5**, with no training of any kind,
   as the proposer. It needed no training and got the furthest: it proved **all 20** steps in
   a single run (and again in a second). Restricted to *only* stating subgoals, it proved 16
   of 20. It is the current default proposer.
3. **Next — a bigger model of our own.** We are training a **7–8B** prover model to do the
   proposing in-house and close the gap to Claude — see [`docs/TRAINING_PLAN.md`](docs/TRAINING_PLAN.md).

| Proposer | Kalam-20 (subgoals only) |
|---|---|
| None (provers alone) | 10 / 20 |
| **V1** — our Qwen2.5-Coder-0.5B fine-tune | ≈ 10 / 20 (about the level of the provers) |
| **V2** — Claude Sonnet 5.5, no training | 16, 19, 19, **20** / 20 across runs (also **20 / 20** when allowed to write proofs) |
| **V3** — our own 7–8B prover | in training |

Full results, the proofs, and interactive search replays: **[at.alkalam.org/kalima](https://at.alkalam.org/kalima)**.

## Install

Rocq 9.2 with CoqHammer 1.3.3 (via opam):

```bash
opam switch create hammer ocaml-base-compiler.5.2.1
opam install rocq-core.9.2.0 rocq-stdlib coq-hammer.1.3.3+9.2
```

Vampire and E must be on `PATH` for CoqHammer. Set `KALIMA_OPAMROOT` / `KALIMA_SWITCH` if your
opam root or switch differ. Then:

```bash
pip install -e .            # add [train] for training, [serve] for vLLM
```

## Run

```bash
python scripts/run_kalam20.py --proposer none                --out runs/provers-only
python scripts/run_kalam20.py --proposer hf:checkpoints/kalima-sft --out runs/sft
pytest tests
```

## Repository layout

```
benchmarks/kalam20/   the 20 benchmark statements (statements only; never training data)
kalima/provers/       the automated provers and the combining tactics
kalima/search/        the decomposition search (and the earlier tactic-level search)
kalima/proposers/     who states subgoals: a fine-tuned model (hf.py), Claude (claude_cli.py)
kalima/rocq/          the Rocq environment and checker
kalima/data/          generated training problems, and the hold-out guard
kalima/train/         SFT data from search logs, fine-tuning, the provers-as-judge reward
configs/              training configurations
scripts/              run the benchmark, verify proofs
docs/                 architecture, training plan, hold-out rule
tests/                prover and hold-out tests
```

## The two rules

- **Hold-out.** No Kalam-20 statement or proof is ever used for training — as data, prompt, or
  example. The training code refuses problems that match them
  ([`docs/HOLDOUT.md`](docs/HOLDOUT.md), [`kalima/data/holdout.py`](kalima/data/holdout.py)).
- **Nothing assumed silently.** Every proof is compiled from scratch; `Print Assumptions` must
  show nothing beyond the declared starting points and the law of excluded middle.

## Citation

```bibtex
@software{kalima,
  title  = {Kalima: a neural-symbolic prover for algorithmic theology},
  author = {{al-Kalam Institute}},
  year   = {2026},
  url    = {https://github.com/alkalaminstitute/kalima}
}
```

## License

Kalima is **free and open-source software**, released under the [Apache 2.0](LICENSE) license —
free to use, modify, and distribute, including commercially, with an explicit patent grant.
Model weights released by this project will state the license of the base model they derive from.
