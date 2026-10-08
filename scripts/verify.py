"""Independent check of a Kalam-20 run.

For every step: the proof file recompiles from scratch, its final lemma is exactly the
benchmark statement, nothing is assumed beyond excluded middle, and no Admitted/Axiom/
Hypothesis appears. Optionally, no prompt in the logs contains a line of a reference proof.
Usage: python scripts/verify.py RUN_DIR [--reference-proofs DIR_WITH_V_FILES]
"""
import argparse, glob, json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "benchmarks" / "kalam20"))
import statements as K
from kalima.provers import leaf


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("run"); ap.add_argument("--reference-proofs")
    a = ap.parse_args(); run = Path(a.run)
    problems, proved = [], 0
    for step, stmt in K.STEPS.items():
        f = run / "proofs" / f"{step}.v"
        if not f.exists():
            print(f"{step:40s} no proof"); continue
        src = f.read_text()
        body = src[src.index(K.PREAMBLE[-60:]) + 60:] if K.PREAMBLE[-60:] in src else src
        if re.search(r"\b(Admitted|admit|Axiom|Parameter|Hypothesis|Conjecture|give_up)\b", body):
            problems.append((step, "forbidden command"))
        top = re.search(r"Print Assumptions (\w+)\.", src).group(1)
        m = re.search(rf"Lemma {top} : (.*?)\.\nProof\.", src, re.S)
        if not m or " ".join(m.group(1).split()) != " ".join(stmt.split()):
            problems.append((step, "final lemma is not the benchmark statement"))
        ok, out = leaf.compile_(src, 900)
        axioms = re.findall(r"^(\S+) :", out.split("Axioms:")[-1], re.M) if "Axioms:" in out else []
        if not ok or not set(axioms) <= {"classic"}:
            problems.append((step, "does not compile, or assumes more than excluded middle"))
        else:
            proved += 1
        print(f"{step:40s} compiles={ok} assumptions={axioms or 'none'}")
    if a.reference_proofs:
        ref = set()
        for f in glob.glob(f"{a.reference_proofs}/**/*.v", recursive=True):
            for blk in re.findall(r"Proof\.(.*?)(?:Qed|Defined)\.", open(f).read(), re.S):
                ref |= {l.strip() for l in blk.split("\n") if len(l.strip()) > 25}
        leaks = sum(1 for f in glob.glob(str(run / "logs" / "*.jsonl")) for l in open(f)
                    if json.loads(l).get("kind") == "model_call" for line in ref if line in l)
        print(f"reference proof lines: {len(ref)}; found in prompts or replies: {leaks}")
    print(f"VERIFIED {proved} of {len(K.STEPS)}; problems: {problems}")


if __name__ == "__main__":
    main()
