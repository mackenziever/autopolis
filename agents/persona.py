"""Generatore deterministico di 50 personalita' distinte."""
from __future__ import annotations
import random
from agents.models import Persona
from config import COURSES

FIRST = ["Ada","Bruno","Cleo","Diego","Elena","Farah","Gio","Hana","Ivan","Jade",
         "Kai","Lina","Milo","Nora","Omar","Pia","Quinn","Ravi","Sara","Theo"]
LAST = ["Rossi","Bianchi","Conti","Romano","Greco","Costa","Fontana","Moretti","Galli","Ricci"]
# Ogni archetipo ha un motivo personale per studiare design (il "soul" — il
# perche', non solo il cosa): tutti condividono l'ambizione della citta',
# raggiungere lo standard Awwwards Site of the Day, ma ci arrivano in modo
# diverso secondo il proprio carattere.
ARCHETYPES = [
    ("metodica", "costruisce design system solidi: ogni componente misurato, documentato, riusabile"),
    ("socievole", "raccoglie feedback dagli altri cittadini prima di ogni rilascio, mai da sola"),
    ("curiosa", "prova ogni settimana una tecnica nuova di motion, shader o layout"),
    ("prudente", "rifinisce dettagli e performance finche' non e' perfetto, mai in fretta"),
    ("ambiziosa", "sogna il proprio nome su un Site of the Day, non si accontenta del \"buono\""),
]

def generate_persona(number: int, seed: int) -> Persona:
    r = random.Random(seed * 100_003 + number)
    # BUGFIX: (number // len(FIRST)) raggruppava il cognome a blocchi di 20
    # agenti identici (0-19 tutti "Rossi", 20-39 tutti "Bianchi", ...).
    # Modulo diretto e indipendente su number -> cognome varia per agente.
    name = f"{FIRST[number % len(FIRST)]} {LAST[number % len(LAST)]}"
    archetype, detail = ARCHETYPES[number % len(ARCHETYPES)]
    course = sorted(COURSES)[number % len(COURSES)]
    diligence, sociability, curiosity, risk = [round(0.2 + r.random()*0.75, 3) for _ in range(4)]
    bio = (
        f"Persona {archetype}: {detail}. Studia {course} per raggiungere lo "
        "standard Awwwards Site of the Day — questo e' lo scopo che la muove."
    )
    return Persona(name, r.randint(20, 58), diligence, sociability, curiosity, risk, course, bio)
