"""Rocq interface for the HTPS search: a persistent coqtop process.

A goal is a pair (hyps, concl).  To apply a tactic to a goal, the goal is
restated as a standalone statement `forall (h : T) ..., concl`, re-introduced
with the same hypothesis names, and the tactic is run under a timeout.  The
resulting goals become independent child goals (tactics that leave
existential variables shared between goals are rejected).  The symbolic side
decides: the final proof is assembled in place and compiled by coqc
(see verify()).
"""
import os, re, subprocess, tempfile

# The Rocq 9.2 + CoqHammer environment (separate opam root; the system Rocq 9.3 is untouched).
# Rocq 9.2 with CoqHammer (opam switch). Override with KALIMA_OPAMROOT / KALIMA_SWITCH.
OPAMROOT = os.path.expanduser(os.environ.get("KALIMA_OPAMROOT", "~/.opam-hammer"))
HAMMER_BIN = os.path.join(OPAMROOT, os.environ.get("KALIMA_SWITCH", "hammer"), "bin")
HAMMER_ENV = dict(os.environ, OPAMROOT=OPAMROOT, PATH=HAMMER_BIN + ":" + os.environ.get("PATH", ""))
HAMMER_IMPORT = "From Hammer Require Import Hammer Tactics.\nSet Hammer ATPLimit 6.\nSet Hammer ReconstrLimit 6."
REPLACE_RE = re.compile(r'Replace the hammer tactic with:\s*([^<\n]+)')


def with_hammer(prelude):
    """Insert the CoqHammer import right after the first Require line of a prelude."""
    lines = prelude.split('\n')
    return '\n'.join(lines[:1] + HAMMER_IMPORT.split('\n') + lines[1:])
import pexpect

PROMPT = re.compile(r"<prompt>.*?</prompt>", re.S)
FORBIDDEN = re.compile(
    r"\b(admit|Admitted|give_up|shelve|Abort|Qed|Defined|Save|Undo|Restart|Back|BackTo|Reset|Axiom|Axioms|"
    r"Parameter|Parameters|Hypothesis|Hypotheses|Variable|Variables|Conjecture|Require|Import|Export|Section|End|"
    r"Proof|Show|Timeout|Fail|Set|Unset|Load|Declare|Drop|Quit|Module|Definition|Lemma|Theorem|Goal|Opaque|Transparent|"
    r"Ltac|Tactic|Notation|Print|Check|Eval|Compute|Search|Locate|Time|Redirect)\b")


class Goal:
    __slots__ = ("hyps", "concl", "key")

    def __init__(self, hyps, concl):
        self.hyps = tuple(hyps)          # (name, type, body-or-None)
        self.concl = concl
        self.key = self.pretty()

    def pretty(self):
        """Printed exactly in the CoqGym style the policy was trained on."""
        lines = []
        for n, t, b in self.hyps:
            lines.append(f"{n} := {b} : {t}" if b is not None else f"{n} : {t}")
        return "\n".join(lines + ["=" * 28, self.concl])

    def statement(self):
        s = self.concl
        for n, t, b in reversed(self.hyps):
            s = f"let {n} : {t} := {b} in {s}" if b is not None else f"forall {n} : {t}, {s}"
        return s


def _clean(t):
    return re.sub(r"Type@\{[^}]*\}", "Type", t).strip()


def parse_goal_block(text, ambient):
    """Parse one goal display (hyps, ====, concl)."""
    text = re.split(r"\n\s*goal \d+ \(ID \d+\) is:", "\n" + text)
    text = text[1] if len(text) > 1 and "=" * 28 not in text[0] else text[0]
    if "=" * 28 not in text:
        return None
    top, concl = text.split("=" * 28, 1)
    hyps = []
    for line in top.splitlines():
        line = line.strip()
        if not line or " : " not in line and " := " not in line:
            continue
        if re.match(r"^\d+ goals?|^goal \d+", line):
            continue
        m = re.match(r"^([\w',\s]+?) := (.*) : (.*)$", line)
        if m and "," not in m.group(1):
            names, body, typ = [m.group(1).strip()], m.group(2), m.group(3)
        else:
            m = re.match(r"^([\w',\s]+?) : (.*)$", line)
            if not m:
                return None
            names, body, typ = [x.strip() for x in m.group(1).split(",")], None, m.group(2)
        for n in names:
            if n in ambient:
                continue
            hyps.append((n, _clean(typ), _clean(body) if body else None))
    concl = " ".join(concl.split())
    return Goal(hyps, _clean(concl))


class Coqtop:
    def __init__(self, prelude, ambient=(), tac_timeout=2, hammer=False):
        self.prelude, self.ambient, self.tac_timeout = prelude, set(ambient), tac_timeout
        self.hammer = hammer          # run in the Rocq 9.2 + CoqHammer environment
        self.last_replacement = None  # tactic CoqHammer suggests in place of `hammer`
        if hammer:
            self.prelude = with_hammer(prelude)
        self.p = None
        self.start()

    def start(self):
        if self.p is not None:
            try: self.p.terminate(force=True)
            except Exception: pass
        if self.hammer:
            self.p = pexpect.spawn(os.path.join(HAMMER_BIN, "rocq"), ["repl", "-q", "-emacs"], encoding="utf-8",
                                   timeout=60, env=dict(HAMMER_ENV, TERM="dumb"))
        else:
            self.p = pexpect.spawn("coqtop", ["-q", "-emacs"], encoding="utf-8", timeout=30,
                                   env=dict(os.environ, TERM="dumb"))
        self.p.delaybeforesend = None
        self.p.setwinsize(1000, 10000)
        self._read()
        for cmd in ["Set Printing All.", "Set Printing Width 100000.", "Unset Printing Records."]:
            self.cmd(cmd)
        for sent in split_sentences(self.prelude):
            out = self.cmd(sent)
            if "Error" in out:
                raise RuntimeError(f"prelude failed at {sent!r}: {out}")

    def _read(self, timeout=30):
        self.p.expect(PROMPT, timeout=timeout)
        return self.p.before

    def cmd(self, s, timeout=30):
        self.p.sendline(s.replace("\n", " "))
        out = self._read(timeout)
        # coqtop echoes nothing in -emacs mode, output is between prompts
        return out

    def state_no(self):
        return None

    def apply(self, goal, tac, timeout=None):
        """Apply tactic to goal.  Returns ("ok", [child goals]) or ("error", message)."""
        tac = tac.strip()
        if tac.endswith("."):
            tac = tac[:-1].strip()
        if not tac or FORBIDDEN.search(tac) or re.search(r"\.\s|\.$|[{}]|^[-+*]", tac) or len(tac) > 300:
            return "error", "rejected tactic text"
        try:
            out = self.cmd(f"Goal {goal.statement()}.") + self.cmd("Proof.")
            if "Error" in out:
                self.cmd("Abort All.")
                return "error", "goal restatement failed: " + out.strip()[-300:]
            names = [n for n, _, _ in goal.hyps]
            if names:
                out = self.cmd("intros " + " ".join(names) + ".")
                if "Error" in out:
                    self.cmd("Abort All.")
                    return "error", "intro failed: " + out.strip()[-300:]
            t = timeout or self.tac_timeout
            self.last_replacement = None
            out = self.cmd(f"Timeout {t} ({tac}).", timeout=t + 30)
            m = REPLACE_RE.search(out)
            if m:
                self.last_replacement = m.group(1).strip().rstrip('.')
            if "Error" in out or "Timeout" in out and "timed out" in out:
                self.cmd("Abort All.")
                return "error", out.strip()[-300:]
            show = self.cmd("Show.")
            if "No more goals" in show:
                self.cmd("Abort All.")
                return "ok", []
            m = re.search(r"(\d+) goals?", show)
            n = int(m.group(1)) if m else 1
            blocks = [show]
            for i in range(2, n + 1):
                blocks.append(self.cmd(f"Show {i}."))
            self.cmd("Abort All.")
            if n > 8:
                return "error", "too many goals"
            children = []
            for b in blocks:
                if re.search(r"\?[A-Za-z_]", b) or "shelved" in b.lower():
                    return "error", "existential variables shared between goals"
                g = parse_goal_block(b, self.ambient)
                if g is None:
                    return "error", "could not parse goal"
                children.append(g)
            return "ok", children
        except (pexpect.TIMEOUT, pexpect.EOF) as e:
            self.start()
            return "error", "coqtop timeout/crash"


def split_sentences(src):
    """Split a vernacular file into sentences (good enough for our preludes: no
    periods inside strings; comments removed)."""
    src = re.sub(r"\(\*.*?\*\)", " ", src, flags=re.S)
    parts = re.split(r"\.(?=\s|$)", src)
    return [p.strip() + "." for p in parts if p.strip()]


def assemble(tree, key):
    """tree: goal key -> (tactic, [child keys]).  Returns a tactic script."""
    tac, kids = tree[key]
    tac = tac.strip().rstrip(".")
    s = f"({tac})."
    for k in kids:
        s += " { " + assemble(tree, k) + " }"
    return s


def verify(prelude, name, stmt, script, section_end="", assumptions_ok=("classic",), hammer=False):
    """Compile the assembled proof with coqc.  Returns (ok, output)."""
    src = f"{prelude}\n\nTheorem {name} : {stmt}.\nProof.\n{script}\nQed.\n{section_end}\nPrint Assumptions {name}.\n"
    if re.search(r"\b(Admitted|admit|give_up)\b", script):
        return False, "forbidden", src
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "Check.v")
        open(f, "w").write(src)
        if hammer:
            r = subprocess.run([os.path.join(HAMMER_BIN, "rocq"), "compile", "-q", f], capture_output=True, text=True,
                               timeout=300, cwd=d, env=HAMMER_ENV)
        else:
            r = subprocess.run(["coqc", "-q", f], capture_output=True, text=True, timeout=120, cwd=d)
    out = r.stdout + r.stderr
    ok = r.returncode == 0
    if ok:
        tail = out.split("Axioms:", 1)
        if len(tail) == 2:
            axioms = re.findall(r"^(\S+) :", tail[1], re.M)
            bad = [a for a in axioms if a.split(".")[-1] not in assumptions_ok]
            if bad:
                ok = False
                out += f"\nUNEXPECTED AXIOMS: {bad}"
    return ok, out, src
