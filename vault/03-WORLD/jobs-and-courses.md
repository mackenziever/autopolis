---
tags: [civitas, world, economy]
---

# Jobs and courses (riferimento condiviso)

Usato da Alveare retrieval e prompt agenti.

- **intern** richiede `basic_literacy`, wage basso, slot illimitati.
- **layout_designer** ← `layout`; **motion_designer** ← `motion`; **ux_designer** ← `interaction`;
  **webgl_developer** ← `webgl` (il più avanzato/raro — coerente con Awwwards, dove 3D/WebGL
  distingue i siti "Site of the Day").
- Assunzione automatica post-esame se idonei; oppure scelta LLM `career_choice` se ruolo in choices.
- Studio: tick in aula incrementa `study_progress[course]`; focus=study raddoppia progresso.
