---
name: exam-feedback
description: Trasforma esito esame in lesson collettiva per Alveare e vault learnings.
tags: [civitas, skill, exam, feedback]
---

# Skill: Exam Feedback

## Quando
Dopo `evaluate_exam` (pass o fail).

## Procedura (deterministica + publish)
1. Se **pass** → lesson: skill sbloccata, corso, tip per altri.
2. Se **fail** → lesson: score, gap preparazione, consiglio studio.
3. Tag Alveare: `exam`, `self_improve`, `skill_unlock` se pass.

## Hard-case mining (ispirazione Lightly/VISSL)
Esami falliti e collisioni ripetute = casi difficili → priorità in retrieval reflection del giorno dopo.
