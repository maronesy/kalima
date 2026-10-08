"""Build supervised training data for the subgoal model from search logs.

An example is (prompt, completion): the prompt the proposer saw, and a division of the goal
that the automated provers ACCEPTED and then proved completely (an `assembled` record with
ok=true). Divisions that failed are kept separately as negatives for preference/RL training.
Every example passes the hold-out guard. Only logs of training problems (abstract symbols)
are accepted; logs of the Kalam-20 benchmark are refused.

Usage: python -m kalima.train.build_sft_data out.jsonl logs/*.jsonl
"""
import json, sys
from kalima.data.holdout import check_example
from kalima.proposers.base import prompt


def examples(log_path, preamble):
    recs = [json.loads(l) for l in open(log_path)]
    ok_divisions = {(r["stmt"], tuple(r["subgoals"])) for r in recs if r["kind"] == "assembled" and r.get("ok")}
    lemmas = []
    for r in recs:
        if r["kind"] == "model_call":
            for stmt, subs in list(ok_divisions):
                if stmt == r["goal"]:
                    p = prompt(preamble, lemmas, r["goal"], r.get("failed") or [])
                    c = json.dumps({"decompositions": [{"subgoals": list(subs)}]})
                    yield {"prompt": check_example(p), "completion": check_example(c)}
        if r["kind"] in ("leaf", "assembled") and r.get("stage", "assembled") in ("leaf", "assembled") and r.get("ok", True):
            lemmas.append((f"L{len(lemmas) + 1}", r["stmt"]))


if __name__ == "__main__":
    out, logs = sys.argv[1], sys.argv[2:]
    from kalima.data.gen_problems import PRELUDE
    n = 0
    with open(out, "w") as fo:
        for lp in logs:
            for ex in examples(lp, PRELUDE):
                fo.write(json.dumps(ex) + "\n"); n += 1
    print(n, "examples")
