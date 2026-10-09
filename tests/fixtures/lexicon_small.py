"""A tiny synthetic lexicon with the traps of docs/09 section 9 (no real people)."""

from services.ips.normalize import norm


def _m(value: str, dept: str) -> dict:
    return {"value": value, "norm": norm(value), "department": dept}


def _p(code: str, name: str, muni: str, dept: str) -> dict:
    return {"code": code, "name": name, "norm": norm(name), "municipality": muni, "department": dept}


LEXICON = {
    "built_at": "2026-10-09T15:00:00Z",
    "dataset_id": "s2ru-bqt6",
    "source_cutoff": "Fecha corte REPS: Nov  5 2022  1:37PM",
    "departments": [
        {"value": v, "norm": norm(v), "providers": n}
        for v, n in [("Antioquia", 837), ("Bogotá D.C", 1270), ("Cali", 300), ("Valle del cauca", 400),
                     ("Tolima", 150), ("Boyacá", 120), ("Santander", 597), ("Santa Marta", 90), ("Quindío", 80)]
    ],
    "municipalities": [
        _m("MEDELLÍN", "Antioquia"), _m("BELLO", "Antioquia"), _m("BOGOTÁ", "Bogotá D.C"), _m("CALI", "Cali"),
        _m("PALMIRA", "Valle del cauca"), _m("MELGAR", "Tolima"), _m("ARMENIA", "Antioquia"),
        _m("ARMENIA", "Quindío"), _m("LA VICTORIA", "Boyacá"), _m("LA VICTORIA", "Valle del cauca"),
    ],
    "providers": [
        _p("508804909", "EMPRESA SOCIAL DEL ESTADO BELLO SALUD", "BELLO", "Antioquia"),
        _p("111", "E.S.E. HOSPITAL SAN JOSÉ", "MELGAR", "Tolima"),
        _p("222", "HOSPITAL SAN JOSE DE BOYACA", "LA VICTORIA", "Boyacá"),
        _p("333", "CLINICA LAS AMERICAS", "MEDELLÍN", "Antioquia"),
    ],
    "capacity": [
        {"group": "CAMAS", "type": "Adultos"}, {"group": "CAMAS", "type": "Pediátrica"},
        {"group": "AMBULANCIAS", "type": "Básica"}, {"group": "SALAS", "type": "Quirófano"},
        {"group": "CONSULTORIOS", "type": "Urgencias"}, {"group": "CONSULTORIOS", "type": "Consulta Externa"},
    ],
}
