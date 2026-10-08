"""Kalima's decomposition search: the model states subgoals; the automated provers prove everything.

For a goal:
  1. the automated provers try it (kalima/provers/leaf.py);
  2. if they fail, the proposer states up to 2 alternative divisions into 2-4 subgoals.
     It writes no proof steps;
  3. a division is accepted only if the provers derive the goal from its subgoals; each
     subgoal is then proved the same way, recursively (AND); alternatives are tried in turn (OR);
  4. if every division fails, the proposer is asked again (up to `rounds` times), shown the
     failed divisions and why each failed.
The finished proof is assembled into one file and compiled from scratch.
"""
import json, re, time
from kalima.provers import leaf

FORBID = re.compile(r"\b(Admitted|admit|Axiom|Parameter|Hypothesis|Variable|Section|End|Proof|Qed)\b")


class Search:
    def __init__(self, preamble, domain, unfold, proposer, section_end="End Kalam.", max_depth=4, max_calls=30,
                 rounds=3, log_path=None, name="goal"):
        self.preamble, self.unfold, self.proposer = preamble, unfold, proposer
        self.head = leaf.header(preamble, domain)
        self.section_end, self.max_depth, self.max_calls, self.rounds = section_end, max_depth, max_calls, rounds
        self.lemmas, self.calls, self.counter, self.name = [], 0, 0, name
        self.log = open(log_path, "w") if log_path else None

    def record(self, **kw):
        if self.log:
            kw["time"] = time.strftime("%Y-%m-%dT%H:%M:%S"); self.log.write(json.dumps(kw) + "\n"); self.log.flush()

    def fresh(self):
        self.counter += 1
        return f"{self.name}_L{self.counter}"

    def well_formed(self, subs):
        src = self.head + "".join(f"Definition chk{i} : Prop := {s}.\n" for i, s in enumerate(subs)) + self.section_end + "\n"
        return leaf.compile_(src, 60)

    def prove(self, stmt, depth=0, path=()):
        known = next((n for n, s, _ in self.lemmas if " ".join(s.split()) == " ".join(stmt.split())), None)
        if known:
            return known
        r = leaf.prove(self.head, self.lemmas, stmt, self.unfold, section_end=self.section_end)
        if r:
            self.record(kind="leaf", stage="leaf", path=list(path), stmt=stmt, prover=r[0], proof=r[1])
            name = self.fresh(); self.lemmas.append((name, stmt, r[1])); return name
        self.record(kind="leaf_failed", stage="leaf", path=list(path), stmt=stmt)
        if depth >= self.max_depth:
            return None
        failed = []
        for _ in range(self.rounds):
            if self.calls >= self.max_calls:
                break
            self.calls += 1
            t0 = time.time()
            divisions, raw = self.proposer.propose(self.preamble, [(n, s) for n, s, _ in self.lemmas], stmt, failed)
            self.record(kind="model_call", n=self.calls, proposer=self.proposer.name, seconds=round(time.time() - t0, 1),
                        goal=stmt, failed=failed, response=raw)
            if not divisions:
                break
            for subs in divisions[:2]:
                subs = [s.strip().rstrip(".") for s in subs if isinstance(s, str)][:4]
                if not subs or any(FORBID.search(s) for s in subs):
                    self.record(kind="rejected", reason="bad format", subgoals=subs); failed.append((subs, "bad format")); continue
                ok, out = self.well_formed(subs)
                if not ok:
                    self.record(kind="rejected", reason="subgoal does not typecheck", subgoals=subs, rocq=out[-400:])
                    failed.append((subs, "a subgoal is not a well-formed Rocq proposition")); continue
                hyps = [(f"sub{i+1}", s) for i, s in enumerate(subs)]
                comb = leaf.prove(self.head, self.lemmas, stmt, self.unfold, hyps=hyps, section_end=self.section_end)
                if not comb:
                    self.record(kind="leaf_failed", stage="combine", path=list(path), stmt=stmt, subgoals=subs)
                    failed.append((subs, "the automated provers could not derive the goal from these subgoals")); continue
                self.record(kind="leaf", stage="combine", path=list(path), stmt=stmt, subgoals=subs, prover=comb[0], proof=comb[1])
                names = []
                for i, (_, s) in enumerate(hyps):
                    n = self.prove(s, depth + 1, tuple(path) + (i + 1,))
                    if n is None:
                        failed.append((subs, f"subgoal {i+1} could not be proved")); break
                    names.append(n)
                if len(names) != len(hyps):
                    continue
                proof = "".join(f"pose proof {n} as sub{i+1}. " for i, n in enumerate(names)) + comb[1]
                name = self.fresh()
                ok, _ = leaf.compile_(leaf.lemma_src(self.head, self.lemmas, name, stmt, proof, section_end=self.section_end), 150)
                self.record(kind="assembled", path=list(path), stmt=stmt, subgoals=subs, proof=proof, ok=ok)
                if ok:
                    self.lemmas.append((name, stmt, proof)); return name
        return None

    def final_file(self, top):
        body = self.head
        for n, s, p in self.lemmas:
            body += f"\nLemma {n} : {s}.\nProof.\n{p}\nQed.\n"
            if n == top:
                break
        return body + f"\n{self.section_end}\n\nPrint Assumptions {top}.\n"
