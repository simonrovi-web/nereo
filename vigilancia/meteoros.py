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


def semana_de(dia: date) -> tuple[date, date]:
    """Sábado anterior o igual a `dia`, y el viernes siguiente.

    Los panoramas de la AMS cubren de sábado a viernes: «november-14-20-2026»
    y «15-21-november-2025» lo son. date.weekday() da 5 para el sábado.
    """
    from datetime import timedelta
    ini = dia - timedelta(days=(dia.weekday() - 5) % 7)
    return ini, ini + timedelta(days=6)


def url_probable(dia: date) -> str:
    """URL que debería tener el panorama de la semana de `dia`.

    Se construye, pero no se da por buena: quien la use tiene que pedirla y
    comprobar que responde y que su tabla se parsea.
    """
    ini, fin = semana_de(dia)
    mes = [m for m, i in MESES.items() if i == ini.month][0]
    return (f"https://www.amsmeteors.org/{ini.year}/{ini.month:02d}/"
            f"meteor-activity-outlook-for-{mes}-{ini.day}-{fin.day}-{ini.year}/")


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
    """Las lluvias activas la semana del caso, si el panorama la cubre.

    Un panorama de la AMS vale para su semana y solo para ella. Se descarga uno
    por ejecución —el de hoy—, así que a un caso de otra semana NO se le puede
    atribuir: devolver algo sería afirmar que una fuente dice lo que no dice.
    En ese caso se devuelve lista vacía y el llamador lo anota.

    Se emite una entrada agregada y no una por lluvia, porque para el descarte
    importa si había actividad meteórica, no el catálogo. Función pura.
    """
    if not lluvias or not url:
        return []
    periodo = periodo_de_url(url)
    if periodo is None or not (periodo[0] <= dia <= periodo[1]):
        return []
    ini, fin = periodo

    partes = []
    for l in lluvias:
        t = (l.get("nombre") or "").strip()
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

    rango = (f"del {ini.day} al {fin.day} de {MESES_ES[fin.month]} de {fin.year}"
             if ini.month == fin.month else
             f"del {ini.day} de {MESES_ES[ini.month]} al {fin.day} de {MESES_ES[fin.month]} de {fin.year}")
    return [{
        "tipo": "meteoros",
        "detalle": f"El panorama de actividad de la American Meteor Society para la semana "
                   f"{rango} lista como activas: " + "; ".join(partes)
                   + ". La coincidencia de calendario es real; que explique el caso depende de "
                     "si el objeto se comportó como un meteoro.",
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


def _urls_desde_archivo(s, cab, dia: date) -> list[str]:
    """Panoramas desde el archivo mensual de la AMS: /AAAA/MM/.

    Es la vía más fiable que hemos encontrado: una página de archivo de
    WordPress con los enlaces en el HTML, sin JavaScript de por medio. Se mira
    el mes del día buscado y también el anterior, porque la semana que cubre un
    día de principios de mes se publicó el mes pasado.
    """
    vistos = []
    meses = {(dia.year, dia.month)}
    previo = date(dia.year - 1, 12, 1) if dia.month == 1 else date(dia.year, dia.month - 1, 1)
    meses.add((previo.year, previo.month))
    for anio, mes in sorted(meses, reverse=True):
        r = s.get(f"https://www.amsmeteors.org/{anio}/{mes:02d}/",
                  timeout=CFG.ams_timeout, headers=cab)
        if r.status_code != 200:
            continue
        vistos += _ENLACE.findall(r.text)
    return list(dict.fromkeys(vistos))


def _urls_construidas(s, cab, dia: date) -> list[str]:
    """La URL que le tocaría a esa semana, comprobada pidiéndola.

    No se devuelve una URL inventada: solo se devuelve si el servidor la sirve.
    """
    u = url_probable(dia)
    r = s.get(u, timeout=CFG.ams_timeout, headers=cab)
    return [u] if r.status_code == 200 else []


def _urls_desde_indice(s, cab, dia: date) -> list[str]:
    """Último recurso: los enlaces que aparezcan en el índice de artículos."""
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
    for nombre, fn in (("archivo mensual", _urls_desde_archivo),
                       ("url construida", _urls_construidas),
                       ("índice", _urls_desde_indice)):
        try:
            encontradas = fn(s, cab, dia)
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
