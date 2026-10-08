"""Run Kalima on the Kalam-20 benchmark: all twenty steps of dalil al-kalima and dalil al-imkan.

Usage:
  python scripts/run_kalam20.py --proposer claude-cli:sonnet --out runs/claude
  python scripts/run_kalam20.py --proposer hf:checkpoints/kalima-sft --out runs/sft
  python scripts/run_kalam20.py --proposer none --out runs/provers-only     # the provers alone
"""
import argparse, json, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "benchmarks" / "kalam20"))
import statements as K
from kalima.search.decompose import Search
from kalima.provers import leaf
from kalima.proposers.base import Proposer

UNFOLD = ("unfold MP001, MP002, MP003, MP007, MP008, MP009, MP010, MP011, MP012, OP001, OP006, SP001, OfItself, "
          "ThroughAnother, Necessary, Possible, InUniverse, DependsOn, Independent, NonExistencePossible, AggregateOfPossibles in *")


class NoModel(Proposer):
    name = "none"
    def propose(self, *a):
        return [], ""


def make_proposer(spec):
    if spec == "none":
        return NoModel()
    kind, arg = spec.split(":", 1)
    if kind == "claude-cli":
        from kalima.proposers.claude_cli import ClaudeCLI; return ClaudeCLI(arg)
    if kind == "hf":
        from kalima.proposers.hf import HFModel; return HFModel(arg)
    raise SystemExit(f"unknown proposer {spec}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--proposer", default="none"); ap.add_argument("--out", required=True)
    ap.add_argument("--steps", nargs="*"); ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--rounds", type=int, default=3)
    a = ap.parse_args()
    out = Path(a.out); (out / "logs").mkdir(parents=True, exist_ok=True); (out / "proofs").mkdir(exist_ok=True)
    proposer = make_proposer(a.proposer)

    def one(step):
        s = Search(K.PREAMBLE, "Thing", UNFOLD, proposer, section_end=K.SECTION_END, rounds=a.rounds,
                   log_path=out / "logs" / f"{step}.jsonl", name=step)
        t0 = time.time(); top = s.prove(K.STEPS[step])
        res = {"proved": top is not None, "model_calls": s.calls, "seconds": round(time.time() - t0, 1)}
        if top:
            f = out / "proofs" / f"{step}.v"; f.write_text(s.final_file(top))
            ok, o = leaf.compile_(f.read_text(), 900)
            res.update(final_compiles=ok, assumptions=o.split("Axioms:")[-1].split() if "Axioms:" in o else [])
        s.record(kind="result", **res); print(step, json.dumps(res), flush=True)
        return step, res

    with ThreadPoolExecutor(a.workers) as ex:
        summary = dict(ex.map(one, a.steps or list(K.STEPS)))
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    print("PROVED", sum(r["proved"] and r.get("final_compiles", False) for r in summary.values()), "of", len(summary))


if __name__ == "__main__":
    main()
