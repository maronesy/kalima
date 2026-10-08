# Training plan: the Kalima subgoal model

## Goal

A model that, given a goal it cannot prove, states subgoals that the automated provers
(Rocq's automation, CoqHammer, the combining tactics in `kalima/provers/leaf.py`) can prove,
and from which they can derive the goal. The model never writes proof steps.

**Success measure:** Kalam-20 (`benchmarks/kalam20/`), all twenty steps of *dalīl al-kalima*
and *dalīl al-imkān*, proved in a single run with the model as the only proposer. The
benchmark is never used for training (see `HOLDOUT.md`).

**Reference points** (October 2026, same search and provers):

| Proposer | Kalam-20, subgoals only |
|---|---|
| None (provers alone) | 10 of 20 |
| Claude Sonnet 5.5, no further training (runs 3–6) | 16, 19, 19, 20 of 20 (run 6: the provers of this repository) |
| Qwen2.5-Coder-0.5B, our fine-tune (tactic search, not subgoals only) | 10 of 20 |

## Base model

A 7–8B prover already trained on formal proofs:

- `Goedel-LM/Goedel-Prover-V2-8B` (default in `configs/sft.yaml`), or
- `deepseek-ai/DeepSeek-Prover-V2-7B`.

Both were trained on Lean 4, not Rocq; stage 0 measures how much carries over.
**Check each model's licence before publishing weights derived from it.**

## Hardware

One 80 GB GPU (H100 or A100) for stages 1–3, with LoRA. The Rocq checks run on CPU, in
parallel; 32 cores keep up with one GPU.

## Stage 0: baseline (1 day)

Run the base model, untrained, as the proposer on Kalam-20 and on 200 generated problems.
This sets the floor and checks that the prompt format works.

## Stage 1: supervised fine-tuning on accepted divisions (≈1 week)

**Data.** Only divisions that the provers accepted and then proved completely
(`kalima/train/build_sft_data.py`), on **generated problems in abstract symbols**:

- the first-order problems of `kalima/data/gen_problems.py`, validated by Z3;
- the chain problems of `kalima/data/gen_chains.py` (strengthen, then induct);
- new families still to be written: aggregates and membership, case splits, existential
  witnesses, and problems that need a predicate as a witness (the shape of premise 1).

**Where the divisions come from.** The search itself produces them. The proposer for data
generation must be one whose licence allows training on its outputs: the base model with
sampling, then each new checkpoint (stage 2). **Claude's outputs are not used as training
data**, because Anthropic's terms restrict using them to train other models; Claude remains a
reference point only.

**Target:** 20–50k accepted divisions. Loss on the completion only; LoRA r=64; 2 epochs.

## Stage 2: expert iteration (≈2 weeks)

Repeat: run the current checkpoint as the proposer on fresh generated problems; keep the
divisions the provers accepted and proved; retrain. Problems are drawn harder each round
(deeper divisions needed). Stop when the share of problems proved stops rising.

## Stage 3: reinforcement learning with the provers as judge (≈2 weeks)

GRPO (`configs/rl.yaml`): sample 8 completions per goal; the reward is computed by the
provers (`kalima/train/reward.py`): 1.0 if they derive the goal from the subgoals and prove
every subgoal, 0.5 if they derive it and prove some, 0.2 if they derive it but prove none,
0 otherwise. This rewards exactly what the design needs: subgoals that are both sufficient
and provable.

## Evaluation

After every stage: Kalam-20 in a single run (count, model calls, time), plus a held-out
set of generated problems. Every proof is recompiled from scratch, must prove exactly the
stated step, and may assume nothing beyond excluded middle (`scripts/verify.py`). Results,
logs and proofs are published with each checkpoint.

## Known gap from the Claude runs

Every failure we analysed was in the **combining** step: the subgoals were right, but the
provers could not derive the goal from them. The combining tactics in `leaf.py` (forward
chaining that fills a hypothesis's variables from one or two premises, one classical case
split, CoqHammer's reconstruction tactics) closed those cases. Stronger combining is the
cheapest way to raise every proposer's score, and is worth improving alongside the model.
