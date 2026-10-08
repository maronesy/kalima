# Kalima

**A neural-symbolic prover that divides goals into subgoals for automated provers, with every
step checked by Rocq.**

Kalima follows the design of HyperTree Proof Search: a neural model states subgoals, and
symbolic provers (Rocq's automation and CoqHammer with Vampire and E) prove them. The model
never writes a proof step. A goal counts as proved only when Rocq compiles the assembled
proof from scratch, with nothing assumed beyond the declared starting points and the law of
excluded middle.

Kalima is developed at the [al-Kalam Institute](https://alkalam.org) for algorithmic
theology: testing classical arguments of Islamic theology by machine. Its benchmark,
**Kalam-20**, is the twenty steps of two arguments for a first cause, *dalīl al-kalima* and
*dalīl al-imkān* (`benchmarks/kalam20/`). Results, proofs and interactive search replays:
<https://at.alkalam.org/static/research/neural-symbolic-prover/index.html>.

## Status

Early. The search, the provers and the benchmark work. The project's own subgoal model (a
7–8B prover, fine-tuned) is not trained yet: see [`docs/TRAINING_PLAN.md`](docs/TRAINING_PLAN.md).

| Proposer | Kalam-20, model states subgoals only |
|---|---|
| None (provers alone) | 10 of 20 |
| Claude Sonnet 5.5, no further training | 16, 19, 19, **20** of 20 in four runs (the last with the final provers) |
| Kalima's own model | not trained yet |

## Layout

```
benchmarks/kalam20/   the 20 benchmark statements (statements only; never training data)
kalima/provers/       the automated provers and the combining tactics
kalima/search/        the decomposition search (and the earlier tactic-level search)
kalima/proposers/     who states subgoals: a fine-tuned model (hf.py), Claude (claude_cli.py)
kalima/data/          generated training problems, and the hold-out guard
kalima/train/         training data from search logs, fine-tuning, the provers-as-judge reward
configs/              training configurations
scripts/              run the benchmark, verify proofs
docs/                 architecture, training plan, hold-out rule
```

## Install

Rocq 9.2 with CoqHammer 1.3.3 (opam):

```
opam switch create hammer ocaml-base-compiler.5.2.1
opam install rocq-core.9.2.0 rocq-stdlib coq-hammer.1.3.3+9.2
```

Vampire and E must be on `PATH` for CoqHammer. Set `KALIMA_OPAMROOT` / `KALIMA_SWITCH` if your
opam root or switch differ. Then `pip install -e .` (add `[train]` for training, `[serve]` for vLLM).

## Run

```
python scripts/run_kalam20.py --proposer none --out runs/provers-only
python scripts/run_kalam20.py --proposer hf:checkpoints/kalima-sft --out runs/sft
pytest tests
```

## Rules

- **Hold-out:** no Kalam-20 statement or proof is ever used for training ([`docs/HOLDOUT.md`](docs/HOLDOUT.md)).
- **Nothing assumed silently:** every proof is compiled from scratch; only excluded middle is allowed beyond the declared starting points.

## Licence

Apache 2.0. Model weights released by this project will state the licence of the base model they derive from.
