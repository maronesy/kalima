"""Hold-out guard: nothing from the Kalam-20 benchmark may enter training data.

Every training example passes through `check_example`, which refuses an example whose text
contains any benchmark statement, or the benchmark's vocabulary (the names of its postulates
and predicates). Training problems are written in abstract symbols instead (kalima/data/)."""
import re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "benchmarks" / "kalam20"))
import statements as K

def _norm(s):
    return " ".join(s.split())

STATEMENTS = [_norm(s) for s in K.STEPS.values()]
VOCAB = re.compile(r"\b(Gives|Through|Ess|PartOf|Universe|MemberOf|ExistsIn|DependsOn|ThroughAnother|OfItself|"
                   r"Necessary|Possible|InUniverse|AggregateOfPossibles|MP0\d\d|OP0\d\d|SP0\d\d)\b")


class HoldoutViolation(ValueError):
    pass


def check_example(text):
    t = _norm(text)
    for s in STATEMENTS:
        if s in t:
            raise HoldoutViolation("a Kalam-20 statement appears in a training example")
    m = VOCAB.search(t)
    if m:
        raise HoldoutViolation(f"Kalam-20 vocabulary ({m.group(0)}) appears in a training example")
    return text
