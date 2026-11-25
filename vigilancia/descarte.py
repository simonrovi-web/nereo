"""Descarte automático: cruza un caso con calendarios reales.

Sustituye el paso que hasta ahora se hacía a mano abriendo RocketLaunch y el
calendario de la AMS. La regla no cambia: solo se anota una coincidencia que
exista de verdad, con la URL que la respalda, y nunca se presenta una
coincidencia como explicación.

Uso:
    from vigilancia import descarte
    cal = descarte.calendarios(date(2026, 11, 20))     # una vez por ejecución
    r = descarte.revisar(cal, "2026-11-20")            # por cada caso
    r["descarte"], r["descarteRevisado"]
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from . import lanzamientos as _lanz
from . import meteoros as _met

log = logging.getLogger(__name__)

TIPOS = {"lanzamiento", "starlink", "meteoros", "bolido", "globo", "dron", "fuegos", "avion", "otro"}


def _dia(f) -> date | None:
    """Acepta date, datetime o 'YYYY-MM-DD'. None si no hay fecha utilizable."""
    if isinstance(f, datetime):
        return f.date()
    if isinstance(f, date):
        return f
    if isinstance(f, str) and f.strip():
        try:
            return date.fromisoformat(f.strip()[:10])
        except ValueError:
            return None
    return None


def calendarios(dia: date | None = None, sesion=None) -> dict:
    """Descarga una sola vez los calendarios que después se consultan por caso.

    Hace como mucho tres peticiones HTTP en total, no por caso.
    """
    dia = dia or datetime.now(timezone.utc).date()
    lanz = _lanz.obtener(sesion=sesion)
    met = _met.obtener(dia, sesion=sesion)
    return {
        "dia": dia.isoformat(),
        "lanzamientos": lanz,
        "meteoros": met,
        "notas": [n for n in (lanz.get("nota"), met.get("nota")) if n],
    }


def revisar(cal: dict, fecha_evento, hora_utc: str | None = None) -> dict:
    """Coincidencias reales para un caso, en el formato del campo `descarte`.

    Devuelve {"descarte": [{tipo, detalle, fuente}, ...], "descarteRevisado": bool,
              "notas": [...]}.

    `descarteRevisado` es True solo si había fecha de evento y al menos un
    calendario respondió con datos. Sin fecha no se puede cruzar nada: se
    devuelve lista vacía y False, que es exactamente lo que la regla pide.
    """
    notas = list(cal.get("notas", []))
    d = _dia(fecha_evento)
    if d is None:
        return {"descarte": [], "descarteRevisado": False,
                "notas": notas + ["El caso no declara fecha de evento, así que no se pudo cruzar "
                                  "con calendarios de lanzamientos ni de lluvias de meteoros."]}

    # hora conocida → se usa; si no, mediodía UTC, que acota el error a ±12 h
    momento = datetime(d.year, d.month, d.day, 12, 0, tzinfo=timezone.utc)
    if hora_utc:
        try:
            hh, mm = (hora_utc.strip()[:5].split(":") + ["0"])[:2]
            momento = momento.replace(hour=int(hh), minute=int(mm))
        except (ValueError, IndexError):
            notas.append(f"Hora no interpretable ({hora_utc}); se asumió mediodía UTC.")

    fuera = []
    lista_lanz = cal.get("lanzamientos", {}).get("lanzamientos", [])
    lluvias = cal.get("meteoros", {}).get("lluvias", [])
    url_met = cal.get("meteoros", {}).get("url")

    hubo_datos = bool(lista_lanz) or bool(lluvias)
    if lista_lanz:
        fuera += _lanz.coincidencias(lista_lanz, momento)
    if lluvias and url_met:
        fuera += _met.coincidencias(lluvias, url_met, d)

    for c in fuera:
        if c["tipo"] not in TIPOS:                     # red de seguridad del esquema
            c["tipo"] = "otro"

    if not hubo_datos:
        notas.append("Ningún calendario devolvió datos en esta ejecución; el descarte no se "
                     "considera revisado.")

    return {"descarte": fuera, "descarteRevisado": hubo_datos, "notas": notas}
