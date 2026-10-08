"""Claude as the proposer, through isolated, stateless Claude Code calls: no tools, no files,
no project memory, each from an empty folder. Used as a baseline; see docs/TRAINING_PLAN.md
on why its outputs are not used as training data."""
import json, subprocess, tempfile
from kalima.proposers.base import Proposer, prompt, parse

SYSTEM = ("You are an expert in the Rocq Prover (version 9, formerly Coq). You decompose goals into simpler "
          "subgoals for automated provers. You never write tactics. You reply with JSON only, no prose, no markdown fences.")


class ClaudeCLI(Proposer):
    def __init__(self, model="sonnet"):
        self.model, self.name = model, f"claude-cli:{model}"

    def propose(self, preamble, lemmas, goal, failed):
        with tempfile.TemporaryDirectory() as d:
            try:
                r = subprocess.run(["claude", "-p", "--model", self.model, "--tools", "", "--strict-mcp-config",
                                    "--setting-sources", "", "--no-session-persistence", "--system-prompt", SYSTEM,
                                    "--output-format", "json", prompt(preamble, lemmas, goal, failed)],
                                   cwd=d, capture_output=True, text=True, timeout=300)
                text = json.loads(r.stdout).get("result", "")
            except Exception as e:
                text = f"(call failed: {e})"
        return parse(text), text
