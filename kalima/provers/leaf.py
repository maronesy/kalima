"""The automated provers: everything that proves a goal or a subgoal in Kalima.

The neural model never writes a proof step. It only states subgoals (kalima/search/decompose.py);
every step of every proof is found by the fixed tactics below, the same list for every goal:
  1. Rocq's standard automation (firstorder, intuition, tauto), with and without unfolding
     definitions, and with a proof by contradiction;
  2. a generic induction on a transitive-closure hypothesis, followed by automation;
  3. generic combining tactics: forward chaining, one classical case split, and CoqHammer's
     reconstruction tactics (sauto, hauto) run without external provers;
  4. CoqHammer: the external provers Vampire and E, with the proof rebuilt as Rocq tactics.
Every check compiles a complete file with `rocq compile`; a check that runs past its time
limit is killed together with Rocq's worker processes.
"""
import os, re, signal, subprocess, tempfile
from pathlib import Path
from kalima.rocq.env import HAMMER_BIN, HAMMER_ENV

LTAC = r"""
Ltac isprop H := let t := type of H in let s := type of t in lazymatch s with Prop => idtac end.
(* forward chaining: apply hypotheses to the facts at hand, filling their quantified variables
   from one or two premises by unification; use facts before unpacking them; each step
   consumes a quantifier or a premise, so it terminates *)
Ltac fwd := repeat match goal with
  | H : ?A -> _, H' : ?A |- _ => isprop H; isprop H'; specialize (H H')
  | H : forall x : {D}, _, H' : _ |- _ => isprop H; isprop H'; specialize (H _ H')
  | H : forall x : {D}, _, H' : _, H'' : _ |- _ => isprop H; isprop H'; isprop H''; specialize (H _ H' H'')
  | H : forall x : {D}, forall y : {D}, _, H' : _, H'' : _ |- _ => isprop H; isprop H'; isprop H''; specialize (H _ _ H' H'')
  | H : forall x : {D}, forall y : {D}, _, H' : _ |- _ => isprop H; isprop H'; specialize (H _ _ H')
  | H : exists _, _ |- _ => destruct H
  | H : _ /\ _ |- _ => destruct H
  end.
(* one classical case split on a premise of a hypothesis, at an object in context *)
Ltac split1 := match goal with
  | H : forall x : {D}, @?P x -> _, a : {D} |- _ => isprop H; let Q := eval cbv beta in (P a) in destruct (classic Q)
  end.
Ltac close := first [ solve [ firstorder eauto ] | solve [ sauto ] | solve [ eauto 8 ] ].
"""
RECONSTRUCTION = re.compile(r"Replace the hammer tactic with:\s*(.+?)\s*$", re.M)


def header(preamble, domain, atp_limit=20):
    """The preamble with CoqHammer's tactics and the combining tactics loaded."""
    pre = preamble.replace("From Stdlib Require Import Classical Relations.",
                           "From Stdlib Require Import Classical Relations.\nFrom Hammer Require Import Hammer Tactics.")
    return pre + f"\nSet Hammer ATPLimit {atp_limit}.\nSet Hammer ReconstrLimit 10.\n" + LTAC.replace("{D}", domain)


def tactic_list(unfold):
    """The fixed leaf tactics. `unfold` is the unfold command for the vocabulary's definitions."""
    U = unfold
    return [
        "intros; firstorder.", f"{U}; intros; firstorder.", f"{U}; intros; intuition eauto.",
        f"{U}; intros; apply NNPP; intro; firstorder.",
        "intros; match goal with H : clos_trans _ _ _ _ |- _ => induction H end; firstorder eauto.",
        f"{U}; intros; match goal with H : clos_trans _ _ _ _ |- _ => induction H end; firstorder eauto.",
        "intros; match goal with H : clos_trans_1n _ _ _ _ |- _ => induction H end; firstorder eauto.",
        "intros; sauto.", f"{U}; intros; sauto.", "intros; hauto lq: on.",
        "intros; fwd; split1; fwd; close.", f"{U}; intros; apply NNPP; intro; fwd; close.",
    ]


def hammer_list(unfold):
    return ["intros; hammer.", f"{unfold}; intros; hammer.", f"{unfold}; intros; apply NNPP; intro; hammer."]


def compile_(src, timeout):
    """Compile a complete Rocq file. Returns (ok, output)."""
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "Check.v"; f.write_text(src)
        pr = subprocess.Popen([os.path.join(HAMMER_BIN, "rocq"), "compile", "-q", str(f)], stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, cwd=d, env=HAMMER_ENV, start_new_session=True)
        try:
            out, _ = pr.communicate(timeout=timeout)
            return pr.returncode == 0, out
        except subprocess.TimeoutExpired:
            try: os.killpg(pr.pid, signal.SIGKILL)
            except Exception: pass
            pr.communicate()
            return False, "TIMEOUT"


def lemma_src(head, lemmas, name, stmt, proof, hyps=(), section_end="End Kalam."):
    """A file with the proved lemmas, then `name : stmt`. Hypotheses become premises of the
    lemma (local, as in the assembled proof), introduced under their own names."""
    body = head + "".join(f"\nLemma {n} : {s}.\nProof.\n{p}\nQed.\n" for n, s, p in lemmas)
    if hyps:
        stmt = " -> ".join(f"({s})" for _, s in hyps) + f" -> ({stmt})"
        proof = "intros " + " ".join(h for h, _ in hyps) + ". " + proof
    return body + f"\nLemma {name} : {stmt}.\nProof.\n{proof}\nQed.\n\n{section_end}\n"


def prove(head, lemmas, stmt, unfold, hyps=(), section_end="End Kalam.", log=None):
    """Try the fixed provers on `stmt` (with `hyps` as premises). Returns (prover, tactic) or None."""
    for tac in tactic_list(unfold):
        ok, _ = compile_(lemma_src(head, lemmas, "kalima_try", stmt, tac, hyps, section_end), 60)
        if ok:
            return "automation", tac
    for tac in hammer_list(unfold):
        ok, out = compile_(lemma_src(head, lemmas, "kalima_try", stmt, tac, hyps, section_end), 150)
        m = RECONSTRUCTION.search(out) if ok else None
        if m:
            final = tac.replace("hammer.", m.group(1).strip().rstrip(".") + ".")
            if compile_(lemma_src(head, lemmas, "kalima_try", stmt, final, hyps, section_end), 150)[0]:
                return "CoqHammer", final
    return None
