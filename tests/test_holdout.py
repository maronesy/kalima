import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from kalima.data.holdout import check_example, HoldoutViolation, STATEMENTS
from kalima.data.gen_problems import PRELUDE


def test_abstract_prelude_passes():
    check_example(PRELUDE)


@pytest.mark.parametrize("stmt", STATEMENTS)
def test_every_benchmark_statement_is_refused(stmt):
    with pytest.raises(HoldoutViolation):
        check_example("Goal:\n" + stmt)
