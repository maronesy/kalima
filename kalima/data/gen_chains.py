"""Generic chain problems that teach "strengthen, then induct".

The technique (a property that passes
along each link of a chain passes along the whole chain) may be taught on
generic problems in abstract symbols. Hold-out guards:
- abstract vocabulary only (T, E, F, P, Q, R, a, b, c); none of the causal
  vocabulary;
- no problem shaped like PR-003 (no "a chain cannot return to its start"
  conclusion, i.e. no `~ clos_trans E x x` goal) and no four-way
  exhaustiveness statement like PR-001.

Each template gives a statement and a canonical decomposition. The
decomposition is replayed in Rocq, and every goal it acts on becomes a
training pair (goal -> step); leaves must be closable by the automation
closers. Only problems whose whole replay succeeds are kept.

Usage: python gen_chains.py N out.jsonl
"""
import json, random, re, sys
from kalima.rocq.env import Coqtop, Goal
from kalima.search import tactic_search as htps

PRELUDE = """From Stdlib Require Import Classical Relations.
Section Chains.
Variable T : Type.
Variables E F : T -> T -> Prop.
Variables P Q R : T -> Prop.
Variables a b c : T."""
AMBIENT = {"T", "E", "F", "P", "Q", "R", "a", "b", "c"}
FORBID = re.compile(r"~\s*\(?\s*clos_trans T \w+ (\w+) \1\b|Gives|Through|Exists|Ess|Universe|DependsOn")


def ct(rel, x, y):
    return f"clos_trans T {rel} {x} {y}"


def templates(rng):
    E = rng.choice(["E", "F"])
    P, Q = rng.sample(["P", "Q", "R"], 2)
    x, y = rng.sample(["a", "b", "c"], 2)
    T = []
    # 1. invariant propagation along a chain (needs the starting hypothesis generalized before induction)
    T.append((f"(forall u v, {E} u v -> {P} u -> {P} v) -> {P} {x} -> {ct(E, x, y)} -> {P} {y}",
              ["intros Hstep Hx Hc", f"revert Hx", "induction Hc", "intros"], "invariant"))
    # 2. backward invariant
    T.append((f"(forall u v, {E} u v -> {P} v -> {P} u) -> {P} {y} -> {ct(E, x, y)} -> {P} {x}",
              ["intros Hstep Hy Hc", "revert Hy", "induction Hc", "intros"], "backward-invariant"))
    # 3. chains stay inside a transitive relation that contains the links (general lemma, both endpoints free)
    T.append((f"(forall u v, {E} u v -> {P} u -> {Q} v) -> (forall u, {Q} u -> {P} u) -> forall u v, {ct(E, 'u', 'v')} -> {P} u -> {Q} v",
              ["intros H1 H2 u v Hc", "induction Hc"], "two-property"))
    # 4. strengthen then specialise: prove the general chain lemma first, then use it at specific points
    T.append((f"(forall u v, {E} u v -> {P} u -> {P} v) -> {P} {x} -> {ct(E, x, y)} -> {ct(E, y, 'c')} -> {P} c",
              [f"intros Hstep Hx H1 H2",
               f"assert (G : forall u v, {ct(E, 'u', 'v')} -> {P} u -> {P} v)",
               "intros u v Hc", "induction Hc"], "assert-general"))
    # 5. a chain of E is a chain of F when every E-link is an F-link
    F = "F" if E == "E" else "E"
    T.append((f"(forall u v, {E} u v -> {F} u v) -> forall u v, {ct(E, 'u', 'v')} -> {ct(F, 'u', 'v')}",
              ["intros Hsub u v Hc", "induction Hc"], "monotone"))
    # 6. reversed chains under a symmetric relation
    T.append((f"(forall u v, {E} u v -> {E} v u) -> forall u v, {ct(E, 'u', 'v')} -> {ct(E, 'v', 'u')}",
              ["intros Hsym u v Hc", "induction Hc"], "symmetric"))
    # 7. a property no link can produce is never reached along a chain
    T.append((f"(forall u v, {E} u v -> ~ {P} v) -> forall u v, {ct(E, 'u', 'v')} -> ~ {P} v",
              ["intros H u v Hc", "induction Hc"], "never-reached"))
    # 8. existence of a first step: every chain begins with a link
    T.append((f"forall u v, {ct(E, 'u', 'v')} -> exists w, {E} u w",
              ["intros u v Hc", "induction Hc"], "first-link"))
    # --- round 6: relational invariants and first-link splitting (same technique, two-place relations)
    S = F   # a second relation used as the invariant
    # 9. a transitive relation containing every link contains every chain (general lemma, assert then induct)
    T.append((f"(forall u v, {E} u v -> {S} u v) -> (forall u v w, {S} u v -> {S} v w -> {S} u w) -> forall u v, {ct(E, 'u', 'v')} -> {S} u v",
              ["intros Hsub Htr u v Hc", "induction Hc"], "relational-invariant"))
    # 10. the same lemma used at a particular chain: assert it, then apply it
    T.append((f"(forall u v, {E} u v -> {S} u v) -> (forall u v w, {S} u v -> {S} v w -> {S} u w) -> {ct(E, x, y)} -> {S} {x} {y}",
              ["intros Hsub Htr Hc",
               f"assert (G : forall u v, {ct(E, 'u', 'v')} -> {S} u v)",
               "intros u v Hc'", "induction Hc'"], "relational-assert"))
    # 11. reversed relational invariant: links give S backwards, so chains do too
    T.append((f"(forall u v, {E} u v -> {S} v u) -> (forall u v w, {S} u v -> {S} v w -> {S} u w) -> forall u v, {ct(E, 'u', 'v')} -> {S} v u",
              ["intros Hsub Htr u v Hc", "induction Hc"], "reverse-relational-invariant"))
    # 12. combine: from a chain u..v and a relation incompatible with the first link, derive a contradiction with an asserted lemma
    T.append((f"(forall u v, {E} u v -> {S} v u) -> (forall u v w, {S} u v -> {S} v w -> {S} u w) -> (forall u v, {E} u v -> ~ {S} v u -> False) -> {ct(E, x, y)} -> {S} {y} {x}",
              ["intros Hsub Htr Hbad Hc",
               f"assert (G : forall u v, {ct(E, 'u', 'v')} -> {S} v u)",
               "intros u v Hc'", "induction Hc'"], "reverse-assert"))
    return T


CLOSERS = ["assumption", "tauto", "firstorder", "intros; firstorder", "intros; eauto", "eauto",
           "intros; apply G; assumption", "intros; eapply G; eauto", "intros; exists y; split; auto",
           "intros; destruct IHHc as [w [Hw Hr]]; exists x; split; auto", "intros; exists y; split; [assumption | left; reflexivity]",
           "intros; exists y; split; [assumption | right; assumption]",
           "intros; eauto using t_step, t_trans", "intros; econstructor; eauto",
           "intros; eapply t_trans; eauto", "intros; apply t_step; firstorder", "auto"]


def close(coq, g):
    for t in CLOSERS:
        st, res = coq.apply(g, t)
        if st == "ok" and not res:
            return t
    return None


def replay(coq, stmt, steps):
    """Apply each step to the first open goal; close all others with the closers.
    Returns the list of (goal, step) pairs, or None if anything fails."""
    pairs, open_goals = [], [Goal([], stmt)]
    for step in steps:
        if not open_goals:
            return None
        g = open_goals.pop(0)
        st, kids = coq.apply(g, step)
        if st != "ok":
            return None
        pairs.append((g.key, step))
        open_goals = kids + open_goals
    for g in open_goals:
        t = close(coq, g)
        if t is None:
            return None
    return pairs


def main(n, out):
    rng = random.Random(7)
    coq = Coqtop(PRELUDE, AMBIENT, tac_timeout=3)
    seen, kept, tried = set(), 0, 0
    kinds = {}
    with open(out, "w") as fo:
        while kept < n and tried < n * 20:
            tried += 1
            stmt, steps, kind = rng.choice(templates(rng))
            # random distractor hypotheses, so the model must pick the right ones
            extra = rng.sample([f"{rng.choice('PQR')} {rng.choice('abc')}",
                                f"forall u, {rng.choice('PQR')} u -> {rng.choice('PQR')} u",
                                f"{rng.choice('EF')} {rng.choice('abc')} {rng.choice('abc')}"], rng.choice([0, 1, 2]))
            if extra:
                stmt = " -> ".join(f"({h})" for h in extra) + " -> " + stmt
                steps = ["intros " + " ".join(f"D{i}" for i in range(len(extra)))] + steps
            if stmt in seen or FORBID.search(stmt):
                continue
            seen.add(stmt)
            pairs = replay(coq, stmt, steps)
            if not pairs:
                continue
            kept += 1; kinds[kind] = kinds.get(kind, 0) + 1
            for g, s in pairs:
                fo.write(json.dumps({"prompt": f"Goal:\n{g}\nTactic:", "completion": " " + s + ".",
                                     "project": "synth-chain-" + kind, "family": None}) + "\n")
    print("problems kept", kept, "of", tried, kinds)


if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2])
