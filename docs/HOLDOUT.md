# The hold-out rule

Kalam-20 (`benchmarks/kalam20/statements.py`) is the test. Its statements, and every proof
of them (ours, published at at.alkalam.org, or any model's), are **never** used as training
data, as prompts, or as examples.

What a model is given at test time: the vocabulary, the declared starting points (postulates,
written as definitions), any lemmas it has itself proved for the current step, and the
statement to prove. Nothing else.

How this is enforced:

- `kalima/data/holdout.py` refuses any training example containing a Kalam-20 statement or
  the benchmark's vocabulary. Every builder of training data calls it, and
  `tests/test_holdout.py` checks it against all twenty statements.
- Training problems are generated in abstract symbols (`P`, `Q`, `E`, `F`, `a`, `b`), never in
  the vocabulary of the two arguments.
- Benchmark run logs are written under `runs/`, which training scripts do not read.
- Prompts can be checked against the published proofs (`scripts/verify.py`).

One limit cannot be enforced by code: a pretrained model may have seen the published proofs
during its developer's training. Report the base model's training cutoff with every result.
