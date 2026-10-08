# Architecture

Kalima follows the design of HyperTree Proof Search (Lample et al., 2022): a goal is divided
into subgoals, and it is proved when every subgoal of one of its divisions is proved (an
AND-OR search). Kalima divides the labour strictly:

| Part | Role | Code |
|---|---|---|
| Proposer (neural) | States subgoals. Never writes proof steps. | `kalima/proposers/` |
| Provers (symbolic) | Prove every goal, every subgoal, and every combination. | `kalima/provers/leaf.py` |
| Search | Divides, recurses, retries with feedback, assembles the proof. | `kalima/search/decompose.py` |
| Checker | Rocq compiles the assembled proof from scratch. | `kalima/provers/leaf.py` |

## One goal, step by step

1. The provers try the goal. If they prove it, done.
2. Otherwise the proposer states up to two divisions, each of two to four subgoals.
3. A division is accepted only if the provers derive the goal from its subgoals.
4. Each subgoal of an accepted division is a new goal (back to 1), to depth 4.
5. If every division fails, the proposer is asked again, up to three times, and shown the
   failed divisions and why each failed.
6. The proof is assembled from the lemmas and compiled by Rocq from scratch; `Print
   Assumptions` must show nothing beyond excluded middle.

## The provers

The same fixed list for every goal (`tactic_list` in `leaf.py`): Rocq's automation, with and
without unfolding and by contradiction; induction on a transitive-closure hypothesis; the
combining tactics `fwd`, `split1`, `close`; CoqHammer's reconstruction tactics; and CoqHammer
with Vampire and E. A check that exceeds its time limit is killed with its worker processes.

## Also included

`kalima/search/tactic_search.py`: the earlier tactic-level search, in which a small model
proposed Rocq tactics directly. Kept for comparison.
