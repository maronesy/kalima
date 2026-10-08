"""A proposer states subgoals for a goal. It never writes proof steps."""
import json, re

INSTRUCTIONS = (
    "Automated provers (first-order automation, CoqHammer, and induction on a clos_trans or clos_trans_1n "
    "hypothesis followed by automation) could not prove this goal. Decompose it into 2 to 4 simpler subgoals: "
    "closed Rocq propositions over the section's vocabulary, such that the goal follows easily from them and each "
    "is easier to prove than the goal. Do NOT write any tactics or proofs; the automated provers will derive the "
    "goal from the subgoals and prove each subgoal. Propose up to 2 alternative decompositions. "
    'Reply as JSON: {"decompositions": [{"subgoals": ["...", "..."]}]}')


def prompt(preamble, lemmas, goal, failed):
    avail = "\n".join(f"Lemma {n} : {s}." for n, s in lemmas) or "(none yet)"
    fb = ("Earlier decompositions of this goal failed:\n" + "\n".join(f"- subgoals {json.dumps(s)}: {why}" for s, why in failed)
          + "\nPropose different decompositions.\n\n") if failed else ""
    return (f"Rocq context (a Section; you cannot change it):\n{preamble}\n"
            f"Lemmas already proved in this section:\n{avail}\n\nGoal:\n{goal}\n\n{fb}{INSTRUCTIONS}")


def parse(text):
    """Extract the list of divisions (each a list of subgoal strings) from a model reply."""
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        return [[s for s in (d.get("subgoals") or []) if isinstance(s, str)] for d in json.loads(m.group(0)).get("decompositions", [])]
    except Exception:
        return []


class Proposer:
    name = "base"

    def propose(self, preamble, lemmas, goal, failed):
        """Returns (divisions, raw_text)."""
        raise NotImplementedError
