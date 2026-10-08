"""Needs Rocq 9.2 with CoqHammer (see README). Skipped otherwise."""
import os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "benchmarks" / "kalam20"))
import pytest
from kalima.rocq.env import HAMMER_BIN
pytestmark = pytest.mark.skipif(not os.path.exists(os.path.join(HAMMER_BIN, "rocq")), reason="Rocq + CoqHammer not installed")


def test_provers_alone_prove_premise_2():
    import statements as K
    from kalima.provers import leaf
    sys.path.insert(0, str(ROOT / "scripts")); from run_kalam20 import UNFOLD
    head = leaf.header(K.PREAMBLE, "Thing")
    assert leaf.prove(head, [], K.STEPS["pr002_no_self_creation"], UNFOLD) is not None


def test_combining_from_correct_subgoals():
    """Claude's three subgoals for the conclusion without the 'if' (run 3): the provers must combine them."""
    import statements as K
    from kalima.provers import leaf
    sys.path.insert(0, str(ROOT / "scripts")); from run_kalam20 import UNFOLD
    head = leaf.header(K.PREAMBLE, "Thing")
    subs = ["MP008 -> forall x, Possible x -> ThroughAnother x",
            "MP008 -> OP001 -> forall x b, Gives b x -> Exists b /\\ Necessary b /\\ Independent b",
            "OP006 -> exists x, InUniverse x /\\ Possible x"]
    hyps = [(f"sub{i+1}", s) for i, s in enumerate(subs)]
    assert leaf.prove(head, [], K.STEPS["kalima_unconditional"], UNFOLD, hyps=hyps) is not None
