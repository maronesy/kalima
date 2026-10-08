"""HTPS-style proof search: an AND-OR graph of goals, a tactic policy that
proposes the next step for a goal (each step splits the goal into subgoals),
and Rocq checking every step.

  goal  --tactic-->  [subgoal 1, subgoal 2, ...]      (AND: all must be proved)
  goal has several candidate tactics                   (OR: one suffices)

Leaves are expanded best-first by the policy's score along the path.  A goal is
proved when some tactic leaves no goals, or all of its subgoals are proved.
The final proof is assembled into one script and compiled by coqc; only then
does it count (rocq_env.verify: no admit, Print Assumptions shows at most
excluded middle).

Proposers:
  model:<path>  the trained (or untrained base) policy, beam search
  hybrid:<path> model proposals plus the fixed list
  fixed         symbolic-only baseline: a fixed hand-written tactic list
                (intros/split/destruct/apply/exists/... over the goal's names)
Both get the same automation "closers" at every goal.
"""
import heapq, json, math, queue, re, threading, time
from pathlib import Path
from kalima.rocq.env import Coqtop, Goal, assemble, verify

HERE = Path(__file__).resolve().parent

CLOSERS = ["assumption", "tauto", "firstorder", "congruence"]


def defs_in(text, defs):
    return [d for d in defs if re.search(rf"\b{d}\b", text)]


HAMMER_LEAF_TIMEOUT = 15


def closers_for(goal, defs, hammer=False):
    out = list(CLOSERS)
    ds = defs_in(goal.key, defs)
    if ds:
        out.append(f"unfold {', '.join(ds)} in *; firstorder")
    if hammer:   # one CoqHammer attempt per goal: it is the expensive leaf prover
        out.append(f"unfold {', '.join(ds)} in *; hammer" if ds else "hammer")
    return out


# ---------------------------------------------------------------- proposers
class FixedProposer:
    """Symbolic baseline: a fixed tactic list instantiated with the goal's names."""
    name = "fixed"

    def __init__(self, defs, consts, preds=None, max_splits=8):
        self.defs, self.consts = defs, consts
        self.preds = preds or {}          # predicate name -> arity, over the domain type(s) in consts
        self.max_splits = max_splits

    def case_splits(self, goal):
        """Classical case splits `destruct (classic (p a))` for predicates that
        occur in the goal, applied to the domain elements in scope."""
        text = goal.key
        elems = [n for n, t, _ in goal.hyps if t in self.consts]
        for ty, cs in self.consts.items():
            elems += cs
        elems = list(dict.fromkeys(elems))
        out = []
        for p, ar in sorted(self.preds.items(), key=lambda x: x[1]):
            if not re.search(rf"\b{p}\b", text):
                continue
            if ar == 0:
                out.append(p)
            elif ar == 1:
                out += [f"{p} {e}" for e in elems]
            elif ar == 2:
                out += [f"{p} {e} {f}" for e in elems for f in elems]
        used = {n for n, _, _ in goal.hyps}
        h = next(f"Hc{i}" if i else "Hc" for i in range(100) if (f"Hc{i}" if i else "Hc") not in used)
        return [f"destruct (classic ({a})) as [{h}|{h}]" for a in out[:self.max_splits]]

    def propose(self, goal, k):
        tacs = ["intros", "split", "left", "right", "exfalso", "constructor", "apply NNPP; intro"]
        ds = defs_in(goal.key, self.defs)
        if ds:
            tacs.append(f"unfold {', '.join(ds)} in *")
        types = {}
        for n, t, _ in goal.hyps:
            types[n] = t
            head = t.split()[0] if t else ""
            if head in ("and", "or", "ex", "@ex", "iff") or head.startswith("@ex"):
                tacs.append(f"destruct {n}")
            if t.startswith("forall") or t.startswith("not") or "->" in t:
                tacs.append(f"apply {n}")
        if goal.concl.startswith("@ex"):
            m = re.match(r"@ex (\S+)", goal.concl)
            ty = m.group(1) if m else None
            cands = [n for n, t in types.items() if t == ty] + list(self.consts.get(ty, []))
            tacs += [f"exists {c}" for c in dict.fromkeys(cands)]
        tacs += self.case_splits(goal)
        tacs = list(dict.fromkeys(tacs))
        return [(t, -1.0) for t in tacs]


class ModelProposer:
    """The neural policy.  Requests from all search threads are batched."""

    def __init__(self, path, beams=8, max_new=48, sample=0, temperature=0.8):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.torch = torch
        self.name = f"model:{path}"
        self.tok = AutoTokenizer.from_pretrained(path)
        self.tok.padding_side = "left"
        self.model = AutoModelForCausalLM.from_pretrained(path, dtype=torch.bfloat16).to("mps").eval()
        self.beams, self.max_new = beams, max_new
        self.sample, self.temperature = sample, temperature   # sample>0: draw that many candidates by sampling instead of beam search
        self.q = queue.Queue()
        self.calls = 0
        self.yes_no = None
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            reqs = [self.q.get()]
            time.sleep(0.02)
            while len(reqs) < 6:
                try: reqs.append(self.q.get_nowait())
                except queue.Empty: break
            for kind in ("gen", "value"):
                batch = [r for r in reqs if r[0] == kind]
                if not batch: continue
                try:
                    outs = (self._generate if kind == "gen" else self._value)([r[1] for r in batch])
                except Exception as e:  # never kill the server thread
                    outs = [[] if kind == "gen" else [0.5] * len(r[1]) for r in batch]
                    print(kind, "error", e, flush=True)
                for (_, _, box), o in zip(batch, outs):
                    box.put(o)

    def _value(self, groups):
        """Critic: P(" yes") vs P(" no") after "Provable:" for each goal; one
        forward pass for all goals of all requests."""
        torch = self.torch
        flat = [g for grp in groups for g in grp]
        if not flat:
            return [[] for _ in groups]
        if self.yes_no is None:
            self.yes_no = (self.tok(" yes", add_special_tokens=False)["input_ids"][0],
                           self.tok(" no", add_special_tokens=False)["input_ids"][0])
        prompts = [f"Goal:\n{g}\nProvable:" for g in flat]
        vals = []
        for i in range(0, len(prompts), 16):
            enc = self.tok(prompts[i:i + 16], return_tensors="pt", padding=True, truncation=True, max_length=900).to("mps")
            with torch.no_grad():
                h = self.model.model(**enc).last_hidden_state[:, -1]
                logits = self.model.lm_head(h).float()[:, list(self.yes_no)]
                vals += torch.softmax(logits, -1)[:, 0].cpu().tolist()
        out, k = [], 0
        for grp in groups:
            out.append(vals[k:k + len(grp)]); k += len(grp)
        return out

    def value(self, goals):
        box = queue.Queue()
        self.q.put(("value", [g.pretty() for g in goals], box))
        return box.get()

    def _generate(self, prompts):
        torch = self.torch
        enc = self.tok(prompts, return_tensors="pt", padding=True, truncation=True, max_length=900).to("mps")
        n = self.sample or self.beams
        with torch.no_grad():
            if self.sample:
                g = self.model.generate(**enc, do_sample=True, temperature=self.temperature, top_p=0.95,
                                        num_return_sequences=n, max_new_tokens=self.max_new,
                                        output_scores=True, return_dict_in_generate=True,
                                        pad_token_id=self.tok.eos_token_id, eos_token_id=self.tok.eos_token_id)
                # log-probability of each sampled sequence (sum over its generated tokens)
                ts = self.model.compute_transition_scores(g.sequences, g.scores, normalize_logits=True)
                L0 = enc["input_ids"].shape[1]
                gen = g.sequences[:, L0:]
                mask = gen != self.tok.eos_token_id
                first_eos = (~mask).float().cumsum(1) <= 1     # keep tokens up to and including the first EOS
                seq_scores = (ts.float().nan_to_num(neginf=0.0) * first_eos[:, :ts.shape[1]]).sum(1)
                g.sequences_scores = seq_scores
            else:
                g = self.model.generate(**enc, num_beams=self.beams, num_return_sequences=self.beams,
                                        max_new_tokens=self.max_new, do_sample=False, early_stopping=True,
                                        output_scores=True, return_dict_in_generate=True, length_penalty=0.0,
                                        pad_token_id=self.tok.eos_token_id, eos_token_id=self.tok.eos_token_id)
        L = enc["input_ids"].shape[1]
        seqs = g.sequences[:, L:]
        scores = g.sequences_scores.float().cpu().tolist()
        res = []
        for i in range(len(prompts)):
            best = {}
            for j in range(n):
                idx = i * n + j
                t = self.tok.decode(seqs[idx], skip_special_tokens=True).strip()
                t = t.split("\n")[0].strip()
                if t and (t not in best or scores[idx] > best[t]):
                    best[t] = scores[idx]          # sampling repeats candidates: keep each once
            res.append(sorted(best.items(), key=lambda x: -x[1]))
        self.calls += len(prompts)
        return res

    def propose(self, goal, k):
        box = queue.Queue()
        self.q.put(("gen", f"Goal:\n{goal.pretty()}\nTactic:", box))
        return box.get()[:k]


class HybridProposer:
    """Model proposals first (scored by the model), then the symbolic list
    (each at a fixed score FIXED_SCORE), deduplicated."""
    FIXED_SCORE = -2.0

    def __init__(self, model, fixed):
        self.model, self.fixed = model, fixed
        self.name = "hybrid:" + model.name.split(":", 1)[1]
        self.value = model.value

    def propose(self, goal, k):
        out, seen = [], set()
        for t, s in self.model.propose(goal, k) + [(t, self.FIXED_SCORE) for t, _ in self.fixed.propose(goal, k)]:
            n = " ".join(t.split()).rstrip(".")
            if n not in seen:
                seen.add(n); out.append((t, s))
        return out


# ---------------------------------------------------------------- search
class Node:
    __slots__ = ("goal", "score", "depth", "edges", "expanded", "proved", "failed", "proof_edge")

    def __init__(self, goal, score, depth):
        self.goal, self.score, self.depth = goal, score, depth
        self.edges, self.expanded, self.proved, self.failed, self.proof_edge = [], False, False, False, None


DECOMP = re.compile(r"^\s*(intros?|split|left|right|exists|eexists|destruct|case|induction|elim|revert|generalize|"
                    r"assert|cut|enough|pose proof|apply|unfold|exfalso|specialize|inversion)\b")


def is_decomposition(t):
    """Steps that restructure the goal or introduce subgoals, as opposed to closing it by automation."""
    return bool(DECOMP.match(t)) and not re.search(r"\b(firstorder|tauto|auto|eauto|intuition|congruence|sauto|hammer)\b", t)


STEP_PENALTY = 1.0   # per-step cost added to the policy's log-probability: favours short proofs
                     # and stops confident but useless chains (e.g. exists x; exists x; ...)


CRITIC_WEIGHT = 1.0  # priority = log v(goal) * CRITIC_WEIGHT + 0.5 * path score, when a critic is used


def search(coq, root_goal, proposer, defs, k=8, max_expansions=48, max_seconds=120, max_depth=14, log=None,
           critic=False, max_asserts=None, hammer=False, decompose_only=False, assert_splits=False,
           eager_leaves=False):
    t0 = time.time()
    nodes = {root_goal.key: Node(root_goal, 0.0, 0)}
    root = nodes[root_goal.key]
    frontier = [(0.0, 0, root_goal.key)]
    counter = 1
    expansions = 0
    tactic_calls = 0

    def update():
        changed = True
        while changed:
            changed = False
            for n in nodes.values():
                if not n.proved:
                    for e in n.edges:
                        if all(nodes[c].proved for c in e[1]):
                            n.proved, n.proof_edge, changed = True, e, True
                            break
                if n.expanded and not n.failed and not n.proved:
                    if all(any(nodes[c].failed for c in e[1]) for e in n.edges):
                        n.failed, changed = True, True

    def relevant():
        seen, stack = set(), [root.goal.key]
        while stack:
            key = stack.pop()
            if key in seen: continue
            seen.add(key)
            n = nodes[key]
            if n.proved or n.failed: continue
            for e in n.edges:
                if not any(nodes[c].failed for c in e[1]):
                    stack.extend(e[1])
        return seen

    while frontier and expansions < max_expansions and time.time() - t0 < max_seconds and not root.proved:
        rel = relevant()
        # pop best relevant leaf
        picked = None
        while frontier:
            negs, _, key = heapq.heappop(frontier)
            n = nodes[key]
            if not n.expanded and key in rel and not n.proved:
                picked = n; break
        if picked is None:
            break
        n = picked
        n.expanded = True
        expansions += 1
        cands = [(t, 0.0) for t in closers_for(n.goal, defs, hammer)]
        proposed = proposer.propose(n.goal, k)
        if decompose_only:   # the model decomposes; proving the leaves is the provers' job
            proposed = [(t, sc) for t, sc in proposed if is_decomposition(t)]
        if assert_splits:    # a proposed statement can also be used as a case split: phi or not phi
            extra = []
            for t, sc in proposed:
                m = re.match(r"^\s*assert\s*\((?:\s*\w+\s*:)?\s*(.+)\)\s*\.?\s*$", t)
                if m and "classic" not in t:
                    extra.append((f"destruct (classic ({m.group(1).strip()})) as [Hs|Hs]", sc))
            proposed = proposed + extra
        # try the most promising first, so a success stops the loop early
        proposed.sort(key=lambda x: -x[1])
        if max_asserts is not None:   # keep only the best few intermediate-lemma proposals
            na, kept = 0, []
            for t, sc in proposed:
                if t.strip().startswith(("assert", "cut", "enough")):
                    na += 1
                    if na > max_asserts: continue
                kept.append((t, sc))
            proposed = kept
        cands += proposed
        seen_t = set()
        pending = []          # new subgoals awaiting one batched critic call
        for tac, lp in cands:
            if time.time() - t0 > max_seconds:
                break
            tn = " ".join(tac.split()).rstrip(".")
            if tn in seen_t: continue
            seen_t.add(tn)
            is_ham = hammer and tn.endswith("hammer")
            status, res = coq.apply(n.goal, tn, timeout=HAMMER_LEAF_TIMEOUT if is_ham else None)
            if is_ham:
                if status == "ok" and coq.last_replacement:
                    tn = tn[: -len("hammer")] + coq.last_replacement   # plain tactic: no ATP call when re-checked
                else:
                    status = "error"
            tactic_calls += 1
            if log is not None:
                log.append({"goal": n.goal.key, "tactic": tn, "score": lp, "status": status,
                            "children": [g.key for g in res] if status == "ok" else str(res)[:200]})
            if status != "ok":
                continue
            kids = []
            new_kids = []
            bad = False
            for g in res:
                if g.key == n.goal.key:
                    bad = True; break   # no progress
                kids.append(g.key)
                if g.key not in nodes:
                    sc = n.score + lp - STEP_PENALTY
                    nodes[g.key] = Node(g, sc, n.depth + 1)
                    if n.depth + 1 <= max_depth:
                        if critic:
                            new_kids.append(g.key)      # pushed after scoring, below
                        else:
                            heapq.heappush(frontier, (-sc, counter, g.key)); counter += 1
                    else:
                        nodes[g.key].expanded = True   # too deep: dead leaf
            if bad: continue
            n.edges.append((tn, kids))
            if eager_leaves and lp != 0.0:
                # A decomposition step just created these subgoals: hand them to the leaf provers at once.
                # Cheap closers on every new subgoal first; CoqHammer (expensive) only when exactly one
                # subgoal is still open, i.e. when it can complete the decomposition.
                def try_close(nd, tactics):
                    nonlocal tactic_calls
                    for ct in tactics:
                        if time.time() - t0 > max_seconds:
                            return False
                        is_h = hammer and ct.endswith("hammer")
                        st2, res2 = coq.apply(nd.goal, ct, timeout=HAMMER_LEAF_TIMEOUT if is_h else None)
                        tactic_calls += 1
                        if st2 == "ok" and not res2:
                            if is_h:
                                if not coq.last_replacement:
                                    continue
                                ct = ct[: -len("hammer")] + coq.last_replacement
                            nd.expanded = True
                            nd.edges.append((ct, []))
                            if log is not None:
                                log.append({"goal": nd.goal.key, "tactic": ct, "score": 0.0, "status": "ok",
                                            "children": [], "eager": True})
                            return True
                    return False
                fresh = [nodes[c] for c in kids if not nodes[c].expanded and not nodes[c].proved]
                still_open = [nd for nd in fresh if not try_close(nd, closers_for(nd.goal, defs, False))]
                if hammer and len(still_open) == 1:
                    nd = still_open[0]
                    ds = defs_in(nd.goal.key, defs)
                    try_close(nd, [f"unfold {', '.join(ds)} in *; hammer" if ds else "hammer"])
                update()
            pending += new_kids
            if not kids:
                break     # closed this goal outright; no need to try more tactics
        if critic and pending:
            pending = list(dict.fromkeys(pending))
            vs = proposer.value([nodes[c].goal for c in pending])
            for c, v in zip(pending, vs):
                pr = CRITIC_WEIGHT * math.log(max(v, 1e-6)) + 0.5 * nodes[c].score
                heapq.heappush(frontier, (-pr, counter, c)); counter += 1
        update()

    result = {"proved": root.proved, "expansions": expansions, "tactic_calls": tactic_calls,
              "seconds": round(time.time() - t0, 1), "nodes": len(nodes)}
    if root.proved:
        tree = {}
        def collect(key):
            if key in tree: return
            e = nodes[key].proof_edge
            tree[key] = e
            for c in e[1]: collect(c)
        collect(root.goal.key)
        result["script"] = assemble(tree, root.goal.key)
        result["tree"] = tree
    # every proved subgoal, even if the root was not proved: training signal
    result["proved_steps"] = [(key, nd.proof_edge[0]) for key, nd in nodes.items() if nd.proved]
    return result
