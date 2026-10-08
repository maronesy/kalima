"""Kalam-20: the twenty steps of dalil al-kalima (7) and dalil al-imkan (13) as Rocq statements.

STATEMENTS ONLY. This is the held-out test set: no proof of any of these statements may be
used as training data, as a prompt, or as an example (see docs/HOLDOUT.md). The training
code refuses problems that match them (kalima/data/holdout.py).

Proofs written by hand are published at https://at.alkalam.org/static/research/
(dalil-al-kalima/ and dalil-al-imkan/); they are not part of this repository's training data.
"""

PREAMBLE = r"""From Stdlib Require Import Classical Relations.

Section Kalam.
(* Vocabulary.  Nothing is assumed about any of these. *)
Variable Thing : Type.
Variable Gives : Thing -> Thing -> Prop.     (* Gives y x : y gives existence to x *)
Variable Through : Thing -> Thing -> Prop.   (* Through x y : x has its existence through y *)
Variable Exists : Thing -> Prop.             (* x exists *)
Variable Ess : Thing -> Prop.                (* x's existence is from its own nature *)
Variable PartOf : Thing -> Thing -> Prop.    (* p is a part of u *)
Variable Universe : Thing.                   (* the universe *)

(* Definitions. *)
Definition DependsOn (x y : Thing) : Prop := Gives y x.            (* x depends on y *)
Definition ThroughAnother (x : Thing) : Prop := exists y, Gives y x.
Definition OfItself (x : Thing) : Prop := Exists x /\ ~ ThroughAnother x.
Definition Necessary (x : Thing) : Prop := Exists x /\ Ess x.
Definition Possible (x : Thing) : Prop := Exists x /\ ~ Ess x.
Definition InUniverse (x : Thing) : Prop := x = Universe \/ PartOf x Universe.

(* Approved postulates, written as definitions: a theorem uses one only when
   its statement lists it as a condition. *)
Definition MP001 : Prop := forall x y, Gives y x -> ~ Through y x.   (* a giver does not have its existence through what it gives existence to *)
Definition MP002 : Prop := forall x y, Gives y x -> Through x y.     (* the receiver has its existence through the giver *)
Definition MP003 : Prop := forall x y z, Through x y -> Through y z -> Through x z.  (* existence-through is inherited *)
Definition MP008 : Prop := forall x, Exists x -> ~ ThroughAnother x -> Ess x.       (* existence comes from one's nature or from a giver *)
Definition OP001 : Prop := forall x y, Gives y x -> OfItself y.      (* only what exists of itself gives existence *)
Definition OP006 : Prop := exists x, InUniverse x /\ Possible x.     (* the universe is not wholly necessary *)
Definition SP001 : Prop := exists x, Exists x.                       (* something exists *)

(* Added for the full test: aggregates, possible worlds, and their postulates. *)
Variable MemberOf : Thing -> Thing -> Prop.  (* p is a member of the aggregate a *)
Variable World : Type.
Variable ExistsIn : World -> Thing -> Prop.  (* x exists in world w *)
Definition Independent (x : Thing) : Prop := forall y, ~ DependsOn x y.
Definition NonExistencePossible (x : Thing) : Prop := exists w, ~ ExistsIn w x.
Definition AggregateOfPossibles (A : Thing) : Prop :=
  (forall p, p <> A -> (MemberOf p A <-> Possible p)) /\ ~ MemberOf A A.
Definition MP007 : Prop := forall x, Ess x -> forall w, ExistsIn w x.        (* existence from one's nature cannot fail *)
Definition MP009 : Prop := (exists p, Possible p) -> exists A, AggregateOfPossibles A /\ Exists A.  (* the aggregate of possibles exists *)
Definition MP010 : Prop := forall A, (exists p, MemberOf p A) ->
  (forall p, MemberOf p A -> ~ Ess p) -> ~ Ess A.                            (* possibles do not add up to a necessary *)
Definition MP011 : Prop := forall c A p, Gives c A -> MemberOf p A -> clos_trans Thing Gives c p.  (* giving to a whole gives to its members *)
Definition MP012 : Prop := forall y x, Gives y x -> Exists y.               (* a giver exists *)
"""
SECTION_END = "End Kalam."

# step id -> (argument, step, statement)
STEPS = {
    'pr002_no_self_creation': 'MP001 -> MP002 -> forall x, ~ Gives x x',
    'pr004_no_two_step_giving': 'OP001 -> forall x y z, Gives y x -> ~ Gives z y',
    'pr003_no_circle': 'MP001 -> MP002 -> MP003 -> forall x, ~ clos_trans Thing DependsOn x x',
    'step3_possible_needs_cause': 'MP008 -> forall x, Possible x -> ThroughAnother x',
    'pr011_something_caused': 'MP008 -> OP006 -> exists x, InUniverse x /\\ Possible x /\\ ThroughAnother x',
    'kalima_first_cause': 'OP001 -> ThroughAnother Universe -> exists b, Gives b Universe /\\ OfItself b /\\ (forall y, ~ Gives y b)',
    'imkan_b_necessary_exists': 'MP008 -> OP001 -> SP001 -> exists n, Necessary n',
    'pr001_relational_exhaustive': 'forall x, (exists y, (x = y \\/ clos_trans Thing DependsOn x y) /\\ DependsOn y y) \\/ (exists y, (x = y \\/ clos_trans Thing DependsOn x y) /\\ clos_trans Thing DependsOn y y /\\ ~ DependsOn y y) \\/ (exists S : Thing -> Prop, S x /\\ forall a, S a -> exists b, S b /\\ DependsOn a b) \\/ ((forall y, ~ DependsOn x y) \\/ exists y, clos_trans Thing DependsOn x y /\\ forall z, ~ DependsOn y z)',
    'kalima_unconditional': 'MP001 -> MP002 -> MP003 -> OP001 -> MP008 -> OP006 -> exists x b, InUniverse x /\\ Gives b x /\\ Exists b /\\ Necessary b /\\ Independent b',
    'imkan_s1_division': 'forall x, Exists x -> (Necessary x \\/ Possible x) /\\ ~ (Necessary x /\\ Possible x)',
    'imkan_s2_necessary_cannot_fail': 'MP007 -> forall x, Necessary x -> ~ NonExistencePossible x',
    'imkan_s4_no_self_causation': 'MP001 -> MP002 -> forall A, ~ Gives A A',
    'imkan_s5_none_outside': 'forall A, AggregateOfPossibles A -> forall p, p <> A -> Possible p -> MemberOf p A',
    'imkan_s6_aggregate_possible_caused': 'MP008 -> MP010 -> forall A, AggregateOfPossibles A -> Exists A -> (exists p, p <> A /\\ Possible p) -> Possible A /\\ ThroughAnother A',
    'imkan_s7_cause_not_member': 'MP001 -> MP002 -> MP003 -> MP011 -> forall c A, Gives c A -> ~ MemberOf c A',
    'imkan_s8_no_internal_cause': 'MP001 -> MP002 -> MP003 -> MP010 -> MP011 -> forall A, AggregateOfPossibles A -> (forall x, ~ Gives x x) /\\ ~ Gives A A /\\ (forall c, MemberOf c A -> ~ Gives c A) /\\ (forall B, B <> A -> Exists B -> (exists p, MemberOf p B) -> (forall p, MemberOf p B -> MemberOf p A) -> ~ Gives B A)',
    'imkan_s9_cause_outside': 'MP001 -> MP002 -> MP003 -> MP011 -> forall A c, AggregateOfPossibles A -> Gives c A -> ~ MemberOf c A /\\ c <> A /\\ ~ Possible c',
    'imkan_s10_cause_necessary': 'MP001 -> MP002 -> MP003 -> MP011 -> MP012 -> forall A c, AggregateOfPossibles A -> Gives c A -> Necessary c',
    'imkan_s11_necessary_cause': 'MP001 -> MP002 -> MP003 -> MP008 -> MP010 -> MP011 -> MP012 -> forall A, AggregateOfPossibles A -> Exists A -> (exists p, p <> A /\\ Possible p) -> exists c, Gives c A /\\ Necessary c /\\ ~ MemberOf c A /\\ c <> A',
    'imkan_s12_necessary_exists': 'MP001 -> MP002 -> MP003 -> MP008 -> MP009 -> MP010 -> MP011 -> MP012 -> SP001 -> exists n, Necessary n',
}
assert len(STEPS) == 20
