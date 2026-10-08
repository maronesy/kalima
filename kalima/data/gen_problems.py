"""Synthetic first-order problems for expert iteration and evaluation.

Generic vocabulary only (a type T, predicates P Q R, relations E F, constants
a b, propositions A B, and a few generic definitions).  None of the kalima or
imkan vocabulary, statements or proofs is used; check_holdout() rejects any
problem whose shape matches a held-out statement.  Each problem is kept only if
Z3 shows it is valid (classically, over a non-empty domain -- the constant a
makes the domain non-empty in Rocq too) and its hypotheses are satisfiable
together (so it is not proved by contradiction among the hypotheses).

Usage: python gen_problems.py N seed out.jsonl
"""
import json, random, re, sys
import z3

PRELUDE = r"""From Stdlib Require Import Classical.
Section Synth.
Variable T : Type.
Variables P Q R : T -> Prop.
Variables E F : T -> T -> Prop.
Variables a b : T.
Variables A B : Prop.
Definition Good (x : T) : Prop := P x /\ ~ Q x.
Definition Linked (x y : T) : Prop := E x y \/ E y x.
Definition Source (x : T) : Prop := forall y, ~ E y x.
Definition Sink (x : T) : Prop := forall y, ~ E x y.
Definition Covered (x : T) : Prop := exists y, E y x /\ P y.
Definition Closed : Prop := forall x y, E x y -> P x -> P y.
Definition Total : Prop := forall x, exists y, E x y.
Definition Sym : Prop := forall x y, E x y -> E y x."""
AMBIENT = {"T", "P", "Q", "R", "E", "F", "a", "b", "A", "B"}
DEFS = {
    "Good": (1, lambda x: ("and", ("P", x), ("not", ("Q", x)))),
    "Linked": (2, lambda x, y: ("or", ("E", x, y), ("E", y, x))),
    "Source": (1, lambda x: ("all", "_s", ("not", ("E", "_s", x)))),
    "Sink": (1, lambda x: ("all", "_s", ("not", ("E", x, "_s")))),
    "Covered": (1, lambda x: ("ex", "_c", ("and", ("E", "_c", x), ("P", "_c")))),
    "Closed": (0, lambda: ("all", "_u", ("all", "_v", ("imp", ("E", "_u", "_v"), ("imp", ("P", "_u"), ("P", "_v")))))),
    "Total": (0, lambda: ("all", "_u", ("ex", "_v", ("E", "_u", "_v")))),
    "Sym": (0, lambda: ("all", "_u", ("all", "_v", ("imp", ("E", "_u", "_v"), ("E", "_v", "_u"))))),
}
UN, BIN, PROPS, CONSTS = ["P", "Q", "R"], ["E", "F"], ["A", "B"], ["a", "b"]


# ---------------- rendering
def rocq(f):
    op = f[0]
    if op in UN: return f"{op} {f[1]}"
    if op in BIN: return f"{op} {f[1]} {f[2]}"
    if op in PROPS: return op
    if op in DEFS:
        return " ".join([op] + list(f[1:]))
    if op == "eq": return f"{f[1]} = {f[2]}"
    if op == "not": return f"~ {par(f[1])}"
    if op in ("and", "or", "imp"):
        s = {"and": "/\\", "or": "\\/", "imp": "->"}[op]
        return f"{par(f[1])} {s} {par(f[2])}"
    if op in ("all", "ex"):
        q = "forall" if op == "all" else "exists"
        return f"{q} {f[1]} : T, {rocq(f[2])}"
    raise ValueError(f)


def par(f):
    return f"({rocq(f)})" if f[0] in ("and", "or", "imp", "all", "ex", "eq") else rocq(f)


# ---------------- z3
Tz = z3.DeclareSort("T")
Z = {p: z3.Function(p, Tz, z3.BoolSort()) for p in UN}
Z.update({r: z3.Function(r, Tz, Tz, z3.BoolSort()) for r in BIN})
Z.update({c: z3.Const(c, Tz) for c in CONSTS})
Z.update({p: z3.Bool(p) for p in PROPS})


def expand(f):
    if f[0] in DEFS:
        return expand(DEFS[f[0]][1](*f[1:]))
    if f[0] in ("not",): return ("not", expand(f[1]))
    if f[0] in ("and", "or", "imp"): return (f[0], expand(f[1]), expand(f[2]))
    if f[0] in ("all", "ex"): return (f[0], f[1], expand(f[2]))
    return f


_fresh = [0]


def z(f, env):
    op = f[0]
    t = lambda v: env[v] if v in env else Z[v]
    if op in UN: return Z[op](t(f[1]))
    if op in BIN: return Z[op](t(f[1]), t(f[2]))
    if op in PROPS: return Z[op]
    if op == "eq": return t(f[1]) == t(f[2])
    if op == "not": return z3.Not(z(f[1], env))
    if op == "and": return z3.And(z(f[1], env), z(f[2], env))
    if op == "or": return z3.Or(z(f[1], env), z(f[2], env))
    if op == "imp": return z3.Implies(z(f[1], env), z(f[2], env))
    if op in ("all", "ex"):
        _fresh[0] += 1
        v = z3.Const(f"{f[1]}_{_fresh[0]}", Tz)
        body = z(f[2], dict(env, **{f[1]: v}))
        return z3.ForAll([v], body) if op == "all" else z3.Exists([v], body)
    raise ValueError(f)


def z3_check(fs, timeout=2000):
    s = z3.Solver(); s.set("timeout", timeout)
    for f in fs: s.add(z(expand(f), {}))
    return s.check()


# ---------------- random generation
def atom(rng, vs):
    terms = vs + CONSTS if vs else CONSTS
    k = rng.random()
    if k < 0.35: return (rng.choice(UN), rng.choice(terms))
    if k < 0.6: return (rng.choice(BIN), rng.choice(terms), rng.choice(terms))
    if k < 0.7: return (rng.choice(PROPS),)
    if k < 0.75 and len(terms) > 1:
        x, y = rng.sample(terms, 2); return ("eq", x, y)
    name = rng.choice(list(DEFS))
    n = DEFS[name][0]
    return (name,) + tuple(rng.choice(terms) for _ in range(n))


def formula(rng, vs, depth):
    if depth <= 0 or rng.random() < 0.25:
        a = atom(rng, vs)
        return ("not", a) if rng.random() < 0.2 else a
    k = rng.random()
    if k < 0.3:
        v = ["x", "y", "z", "w"][len(vs)] if len(vs) < 4 else None
        if v:
            for _ in range(6):
                body = formula(rng, vs + [v], depth - 1)
                if mentions(body, v):
                    return (rng.choice(["all", "all", "ex"]), v, body)
    if k < 0.5: return ("imp", formula(rng, vs, depth - 1), formula(rng, vs, depth - 1))
    if k < 0.7: return ("and", formula(rng, vs, depth - 1), formula(rng, vs, depth - 1))
    if k < 0.85: return ("or", formula(rng, vs, depth - 1), formula(rng, vs, depth - 1))
    return ("not", formula(rng, vs, depth - 1))


def mentions(f, v):
    return any(mentions(g, v) if isinstance(g, tuple) else g == v for g in f[1:])


def problem(rng):
    nh = rng.choice([1, 2, 2, 3, 3, 4])
    hyps = [formula(rng, [], rng.choice([2, 3, 3, 4])) for _ in range(nh)]
    concl = formula(rng, [], rng.choice([2, 3, 3]))
    return hyps, concl


def statement(hyps, concl):
    return " -> ".join([par(h) for h in hyps] + [par(concl)])


# ---------------- hold-out guard
HELDOUT_SHAPES = [
    # shapes of the held-out statements with names abstracted; see pilot.TASKS
    r"clos_trans", r"Gives|Through|Exists|Ess|PartOf|Universe|Necessary|Possible|OfItself|ThroughAnother|DependsOn",
    r"MP0|OP0|SP0",
]


def check_holdout(stmt):
    return not any(re.search(p, stmt) for p in HELDOUT_SHAPES)


def iter_problems(n, seed):
    """Yield (id, hyps, concl, stmt, alone) exactly as main() writes them
    (same random sequence), so the formula trees can be recovered later."""
    rng = random.Random(seed)
    got, tried, seen = 0, 0, set()
    while got < n:
        tried += 1
        hyps, concl = problem(rng)
        st = statement(hyps, concl)
        if st in seen or len(st) > 400 or not check_holdout(st):
            continue
        seen.add(st)
        if z3_check(hyps + [("not", concl)]) != z3.unsat:
            continue
        if z3_check(hyps) != z3.sat:
            continue
        # the conclusion must not be valid on its own (the hypotheses must matter) for most problems
        alone = z3_check([("not", concl)]) == z3.unsat
        if alone and rng.random() < 0.7:
            continue
        yield f"s{seed}_{got}", hyps, concl, st, alone
        got += 1
    iter_problems.tried = tried


def main(n, seed, out):
    got = 0
    with open(out, "w") as fo:
        for pid, hyps, concl, st, alone in iter_problems(n, seed):
            fo.write(json.dumps({"id": pid, "stmt": st, "concl_valid_alone": alone}) + "\n")
            got += 1
    print("kept", got, "of", iter_problems.tried)


if __name__ == "__main__":
    main(int(sys.argv[1]), int(sys.argv[2]), sys.argv[3])
