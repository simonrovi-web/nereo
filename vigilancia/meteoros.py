"""Lluvias de meteoros · panorama semanal de la American Meteor Society.

La AMS publica cada semana un «Meteor Activity Outlook» con la tabla de lluvias
activas, sus fechas de actividad, su máximo y sus tasas. Es la misma página que
se consultaba a mano para el campo `descarte`, así que aquí se lee y se parsea.

Principios:
1. No se embarca ninguna tabla de lluvias escrita de memoria. Lo que se publique
   sale de la página que se descargó, y cada coincidencia cita su URL.
2. El parseo es tolerante: si la tabla cambia de forma y no se reconoce, se
   devuelve vacío con una nota, nunca una suposición.
3. Lo descargado se cachea en data/descarte/meteoros.json para sobrevivir a una
   caída de la AMS.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timezone
from html.parser import HTMLParser

from .config import CFG

log = logging.getLogger(__name__)

ARCHIVO = "meteoros.json"

MESES = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june",
     "july", "august", "september", "october", "november", "december"], 1)}

MESES_ES = {1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
            7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"}

# .../2026/11/meteor-activity-outlook-for-november-14-20-2026/
_SLUG_MES_PRIMERO = re.compile(
    r"meteor-activity-outlook-for-([a-z]+)-(\d{1,2})-(\d{1,2})-(\d{4})", re.I)
# .../meteor-activity-outlook-for-15-21-november-2025/
_SLUG_DIA_PRIMERO = re.compile(
    r"meteor-activity-outlook-for-(\d{1,2})-(\d{1,2})-([a-z]+)-(\d{4})", re.I)

_ENLACE = re.compile(r'href="(https?://(?:www\.)?amsmeteors\.org/\d{4}/\d{2}/[^"]*'
                     r'meteor-activity-outlook[^"]*)"', re.I)


# ─────────────────────────────────────────────────────── periodo de una URL
def periodo_de_url(url: str) -> tuple[date, date] | None:
    """Fechas que cubre un panorama semanal, deducidas de su URL. None si no encaja."""
    m = _SLUG_MES_PRIMERO.search(url)
    if m:
        mes_txt, d1, d2, anio = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))
    else:
        m = _SLUG_DIA_PRIMERO.search(url)
        if not m:
            return None
        d1, d2, mes_txt, anio = int(m.group(1)), int(m.group(2)), m.group(3), int(m.group(4))
    mes = MESES.get(mes_txt.lower())
    if not mes:
        return None
    try:
        ini = date(anio, mes, d1)
        # una semana puede cruzar de mes: 28 nov – 4 dic sale como 28-4
        fin = date(anio, mes, d2) if d2 >= d1 else (
            date(anio + 1, 1, d2) if mes == 12 else date(anio, mes + 1, d2))
    except ValueError:
        return None
    return ini, fin


def elegir_panorama(urls: list[str], dia: date) -> str | None:
    """De una lista de panoramas, el que cubre `dia`; si ninguno, el más cercano anterior."""
    candidatos = []
    for u in urls:
        p = periodo_de_url(u)
        if p:
            candidatos.append((p, u))
    for (ini, fin), u in candidatos:
        if ini <= dia <= fin:
            return u
    previos = [((ini, fin), u) for (ini, fin), u in candidatos if fin < dia]
    if previos:
        return max(previos, key=lambda x: x[0][1])[1]
    return None


# ─────────────────────────────────────────────────────────── parseo de tabla
class _Tablas(HTMLParser):
    """Extrae todas las tablas de un HTML como listas de filas de texto."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tablas: list[list[list[str]]] = []
        self._tabla = None
        self._fila = None
        self._celda = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._tabla = []
        elif tag == "tr" and self._tabla is not None:
            self._fila = []
        elif tag in ("td", "th") and self._fila is not None:
            self._celda = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._celda is not None:
            self._fila.append(re.sub(r"\s+", " ", "".join(self._celda)).strip())
            self._celda = None
        elif tag == "tr" and self._fila is not None:
            if any(self._fila):
                self._tabla.append(self._fila)
            self._fila = None
        elif tag == "table" and self._tabla is not None:
            self.tablas.append(self._tabla)
            self._tabla = None

    def handle_data(self, data):
        if self._celda is not None:
            self._celda.append(data)


def parsear_lluvias(html: str) -> list[dict]:
    """Lluvias listadas en un panorama de la AMS.

    Busca la tabla cuya cabecera mencione la lluvia y su máximo, y devuelve
    [{nombre, codigo, maximo, actividad, velocidad, clase}]. Si no reconoce
    ninguna tabla, devuelve [] — nunca adivina.
    """
    p = _Tablas()
    p.feed(html)
    for tabla in p.tablas:
        if len(tabla) < 2:
            continue
        cab = [c.lower() for c in tabla[0]]
        if not any("shower" in c for c in cab):
            continue
        idx = {}
        for i, c in enumerate(cab):
            if "shower" in c and "nombre" not in idx:
                idx["nombre"] = i
            elif "code" in c:
                idx["codigo"] = i
            elif "activity" in c or "period" in c:
                idx["actividad"] = i
            elif "max" in c or "peak" in c:
                idx["maximo"] = i
            elif "velocity" in c or "km" in c:
                idx["velocidad"] = i
            elif "class" in c:
                idx["clase"] = i
        if "nombre" not in idx:
            continue
        filas = []
        for f in tabla[1:]:
            if len(f) <= idx["nombre"] or not f[idx["nombre"]]:
                continue
            filas.append({k: (f[i] if i < len(f) else "") for k, i in idx.items()})
        if filas:
            return filas
    return []


# ─────────────────────────────────────────────────────────── coincidencias
def coincidencias(lluvias: list[dict], url: str, dia: date) -> list[dict]:
    """Una sola entrada de descarte que resume las lluvias activas esa semana.

    Función pura. Se emite una entrada agregada y no una por lluvia, porque lo
    que importa para el descarte es si había actividad meteórica, no el catálogo.
    """
    if not lluvias:
        return []
    partes = []
    for l in lluvias:
        t = l.get("nombre", "").strip()
        if not t:
            continue
        extra = []
        if l.get("actividad"):
            extra.append(f"activa {l['actividad']}")
        if l.get("maximo"):
            extra.append(f"máximo {l['maximo']}")
        if l.get("velocidad"):
            extra.append(f"{l['velocidad']} km/s")
        partes.append(f"{t} ({', '.join(extra)})" if extra else t)
    if not partes:
        return []
    return [{
        "tipo": "meteoros",
        "detalle": f"Según el panorama de actividad de la American Meteor Society que cubre el "
                   f"{dia.day} de {MESES_ES[dia.month]} de {dia.year}, estaban activas: "
                   + "; ".join(partes)
                   + ". La coincidencia de calendario es real; que explique el caso depende de si "
                     "el objeto se comportó como un meteoro.",
        "fuente": url,
    }]


# ─────────────────────────────────────────────────────────── red y caché
def _ruta():
    return CFG.cache / ARCHIVO


def leer_cache() -> dict:
    p = _ruta()
    if not p.exists():
        return {"obtenido": None, "url": None, "lluvias": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        log.warning("caché de meteoros ilegible: %s", e)
        return {"obtenido": None, "url": None, "lluvias": []}


def _guardar(datos: dict) -> None:
    p = _ruta()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _urls_desde_wp(s, cab) -> list[str]:
    """Panoramas vía la API REST de WordPress del sitio de la AMS.

    Es mucho más robusto que raspar el índice: devuelve JSON con el enlace de
    cada entrada y no depende de cómo esté maquetada la portada.
    """
    r = s.get(CFG.ams_wp, timeout=CFG.ams_timeout, headers=cab,
              params={"search": "meteor activity outlook", "per_page": 20,
                      "orderby": "date", "order": "desc", "_fields": "link"})
    r.raise_for_status()
    datos = r.json()
    if not isinstance(datos, list):
        raise RuntimeError("la API de WordPress no devolvió una lista")
    return [d["link"] for d in datos if isinstance(d, dict) and isinstance(d.get("link"), str)]


def _urls_desde_indice(s, cab) -> list[str]:
    """Respaldo: los enlaces de panorama que aparezcan en el índice de artículos."""
    r = s.get(CFG.ams_indice, timeout=CFG.ams_timeout, headers=cab)
    r.raise_for_status()
    return list(dict.fromkeys(_ENLACE.findall(r.text)))


def obtener(dia: date, sesion=None) -> dict:
    """Busca el panorama de la AMS que cubre `dia`, lo parsea y lo cachea.

    Devuelve {"lluvias": [...], "url": str|None, "obtenido": iso,
              "origen": "api"|"cache", "via": str|None, "nota": str|None}.
    No lanza por red: degrada a la caché del repositorio.
    """
    import requests

    s = sesion or requests
    cab = {"User-Agent": CFG.agente}
    intentos, urls, via = [], [], None
    for nombre, fn in (("wp-json", _urls_desde_wp), ("índice", _urls_desde_indice)):
        try:
            encontradas = fn(s, cab)
        except Exception as e:
            intentos.append(f"{nombre}: {e}")
            continue
        if encontradas:
            urls, via = encontradas, nombre
            break
        intentos.append(f"{nombre}: 0 enlaces de panorama")

    try:
        if not urls:
            raise RuntimeError("no se obtuvo ningún panorama (" + "; ".join(intentos) + ")")
        elegida = elegir_panorama(urls, dia)
        if not elegida:
            raise RuntimeError(f"ninguno de los {len(urls)} panoramas de {via} cubre la fecha; "
                               f"el primero es {urls[0]}")
        a = s.get(elegida, timeout=CFG.ams_timeout, headers=cab)
        a.raise_for_status()
        lluvias = parsear_lluvias(a.text)
        if not lluvias:
            raise RuntimeError(f"no se reconoció la tabla de lluvias en {elegida}")
    except Exception as e:
        cache = leer_cache()
        nota = f"No se pudo leer el panorama de la AMS ({e}); se usa la caché del repositorio."
        log.warning(nota)
        cache.update({"origen": "cache", "via": via, "nota": nota})
        return cache

    datos = {
        "obtenido": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "url": elegida,
        "via": via,
        "lluvias": lluvias,
    }
    _guardar(datos)
    return {**datos, "origen": "api", "nota": None}
