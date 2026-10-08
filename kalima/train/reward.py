"""The reward for reinforcement learning (stage 3 of docs/TRAINING_PLAN.md): the provers judge.

A completion (a JSON list of divisions) for a goal earns:
  1.0  if, for some division, the provers derive the goal from the subgoals AND prove every subgoal;
  0.5  if the provers derive the goal from the subgoals, and some but not all subgoals are proved;
  0.2  if the provers derive the goal from the subgoals, but prove none;
  0.0  if no division is well formed and sufficient.
Subgoals the provers cannot prove are not penalised further: a later round may divide them.
"""
from kalima.provers import leaf
from kalima.proposers.base import parse


def score(completion, goal, head, unfold, section_end, lemmas=()):
    best = 0.0
    for subs in parse(completion)[:2]:
        subs = [s.strip().rstrip(".") for s in subs][:4]
        if not subs:
            continue
        hyps = [(f"sub{i+1}", s) for i, s in enumerate(subs)]
        if not leaf.prove(head, list(lemmas), goal, unfold, hyps=hyps, section_end=section_end):
            continue
        proved = sum(1 for s in subs if leaf.prove(head, list(lemmas), s, unfold, section_end=section_end))
        r = 1.0 if proved == len(subs) else (0.5 if proved else 0.2)
        best = max(best, r)
        if best == 1.0:
            break
    return best
