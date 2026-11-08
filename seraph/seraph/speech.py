"""Every sentence Seraph says, as templates. Radio French: short, « <dest> de Seraph : … ». No model writes French."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
NUMS = ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix", "onze", "douze"]
LANG_FR = {"en": "anglais", "es": "espagnol", "ar": "arabe", "other": "langue étrangère"}
ORD = {0: "RDC", 1: "1er"}


def n_fr(n: int, fem: bool = False) -> str:
    if n == 1 and fem:
        return "une"
    return NUMS[n] if 0 <= n < len(NUMS) else str(n)


def cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def level_fr(level: Optional[int]) -> str:
    if level is None:
        return "étage inconnu"
    return ORD.get(level, f"{level}e")


def hhmm(iso: str) -> str:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return dt.astimezone(PARIS).strftime("%H:%M")


def dest_fr(speaker: str) -> str:
    s = (speaker or "").strip()
    return s if s else "COS"


def addressed(dest: str, text: str) -> str:
    return f"{dest} de Seraph : {text}"


def room_fr(room: Optional[str]) -> str:
    if not room:
        return ""
    if room == "corridor":
        return "circulation"
    return f"salle {room}"


# ───────── Calls, in the caller's language ─────────
REROUTE = {
    "fr": "Les pompiers vous demandent de vous arrêter et de prendre l'escalier {to}. N'utilisez pas l'escalier {frm}, il y a de la fumée.",
    "en": "The firefighters ask you to stop and use stairway {to}{to_side}. Do not use the {frm_side_en} stairs, there is smoke.",
    "es": "Los bomberos le piden que se detenga y use la escalera {to}. No use la escalera {frm}, hay humo.",
}
STANDING = {
    "fr": "Restez dans la pièce, porte fermée, calfeutrez le bas de la porte. Les pompiers sont informés de votre position. Restez en ligne.",
    "en": "Stay in the room with the door closed, block the gap under the door. The firefighters know where you are. Stay on the line.",
    "es": "Quédese en la habitación con la puerta cerrada, tape la parte de abajo de la puerta. Los bomberos saben dónde está. No cuelgue.",
}
HOLD = {
    "fr": "Restez en ligne, je transmets aux pompiers.",
    "en": "Stay on the line, I am passing this to the firefighters.",
    "es": "Quédese en línea, estoy transmitiendo su situación a los bomberos.",
}
STAIR_SIDE_EN = {"A": " on the north side", "B": " on the south side"}
STAIR_SIDE_WORD_EN = {"A": "north", "B": "south"}


def reroute_text(lang: str, to: str, frm: str) -> str:
    t = REROUTE.get(lang) or REROUTE["fr"]
    return t.format(to=to, frm=frm, to_side=STAIR_SIDE_EN.get(to, ""), frm_side_en=STAIR_SIDE_WORD_EN.get(frm, frm))


def standing_text(lang: str) -> str:
    return STANDING.get(lang) or STANDING["fr"]


# Infinitive (as said on the radio) → imperative for the read-back and the call. Only what radio orders use.
IMPERATIVE = {
    "rester": "restez", "prendre": "prenez", "descendre": "descendez", "monter": "montez", "sortir": "sortez",
    "attendre": "attendez", "fermer": "fermez", "ouvrir": "ouvrez", "aller": "allez", "partir": "partez",
    "evacuer": "évacuez", "évacuer": "évacuez", "utiliser": "utilisez", "rejoindre": "rejoignez", "faire": "faites",
    "mettre": "mettez", "venir": "venez", "garder": "gardez", "calfeutrer": "calfeutrez", "bouger": "bougez",
    "quitter": "quittez", "remonter": "remontez", "redescendre": "redescendez", "rentrer": "rentrez",
}


def imperative(order_raw: str) -> str:
    """« de rester sur place » → « Restez sur place. » ; « de ne pas utiliser l'ascenseur » → « N'utilisez pas l'ascenseur. »"""
    words = order_raw.strip().rstrip(".!?").split()
    if not words:
        return ""
    if words[0] in ("de", "d", "d'"):
        words = words[1:]
    neg = None
    if len(words) >= 3 and words[0] == "ne" and words[1] in ("pas", "plus"):
        neg = words[1]
        words = words[2:]
    v = words[0]
    imp = IMPERATIVE.get(v) or (v[:-2] + "ez" if v.endswith("er") else v)
    rest = " ".join(words[1:])
    if neg:
        lead = ("n'" if imp[:1] in "aeiouéè" else "ne ") + imp + f" {neg}"
        s = f"{lead} {rest}".strip()
    else:
        s = f"{imp} {rest}".strip()
    return cap(s) + "."


# Orders the COS gives most, already translated (anything else goes out in French with translate=true).
ORDERS = {
    "Restez sur place.": {"en": "Stay where you are.", "es": "Quédese donde está."},
    "Restez dans la pièce.": {"en": "Stay in the room.", "es": "Quédese en la habitación."},
    "Restez dans la pièce, porte fermée.": {"en": "Stay in the room with the door closed.", "es": "Quédese en la habitación con la puerta cerrada."},
    "Ne bougez pas.": {"en": "Do not move.", "es": "No se mueva."},
    "N'utilisez pas l'ascenseur.": {"en": "Do not use the elevator.", "es": "No use el ascensor."},
    "Prenez l'escalier A.": {"en": "Use stairway A.", "es": "Use la escalera A."},
    "Prenez l'escalier B.": {"en": "Use stairway B.", "es": "Use la escalera B."},
    "Descendez par l'escalier A.": {"en": "Go down by stairway A.", "es": "Baje por la escalera A."},
    "Descendez par l'escalier B.": {"en": "Go down by stairway B.", "es": "Baje por la escalera B."},
    "Sortez du bâtiment.": {"en": "Leave the building.", "es": "Salga del edificio."},
    "Attendez les pompiers.": {"en": "Wait for the firefighters.", "es": "Espere a los bomberos."},
    "Fermez la porte.": {"en": "Close the door.", "es": "Cierre la puerta."},
    "Allez à la fenêtre.": {"en": "Go to the window.", "es": "Vaya a la ventana."},
    "Signalez-vous à la fenêtre.": {"en": "Show yourself at the window.", "es": "Hágase ver en la ventana."},
}


def translate_order(order_fr: str, lang: str) -> Optional[str]:
    if lang == "fr":
        return order_fr
    return ORDERS.get(order_fr, {}).get(lang)
