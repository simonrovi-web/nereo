"""Lanzamientos orbitales · cliente de Launch Library 2 (The Space Devs).

Principios:
1. UNA sola petición por ejecución. El nivel gratuito permite 15 por hora y por
   IP, y la IP del runner de GitHub Actions se comparte con otros usuarios, así
   que gastar más es pedir un 429 ajeno.
2. No se usan filtros de fecha de la API, cuyos nombres no están documentados en
   las páginas públicas. Se pide la última página de lanzamientos pasados
   ordenada por fecha y se filtra en local. Es una llamada y no depende de
   detalles del esquema.
3. Lo que se descarga se guarda en data/descarte/lanzamientos.json. Si la API
   falla o responde 429, se usa la caché y se dice que es caché.
4. Nunca se inventa una coincidencia: si no hay datos, no hay coincidencias y el
   llamador marcará descarteRevisado en false.
"""
from __future__ import annotations

import json
import logging
import math
import re
from datetime import datetime, timedelta, timezone

from .config import CFG

log = logging.getLogger(__name__)

ARCHIVO = "lanzamientos.json"

# El nombre de la misión es lo único que distingue de forma fiable una
# constelación: la API no expone un campo de constelación.
_STARLINK = re.compile(r"\bstarlink\b", re.I)


# ─────────────────────────────────────────────────────────── normalización
def _texto(d, *camino, defecto=""):
    """Baja por un camino de claves tolerando ausencias y valores nulos."""
    for k in camino:
        if not isinstance(d, dict):
            return defecto
        d = d.get(k)
    return d if isinstance(d, str) and d else defecto


def _coord(d, *camino):
    """Número desde un camino de claves; LL2 devuelve lat/lon como texto o número."""
    for k in camino:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    try:
        v = float(d)
    except (TypeError, ValueError):
        return None
    return v if -90.1 <= v <= 90.1 or abs(v) <= 180.1 else None


def distancia_km(lat1, lon1, lat2, lon2) -> float | None:
    """Distancia sobre el globo, en kilómetros. None si falta alguna coordenada."""
    if None in (lat1, lon1, lat2, lon2):
        return None
    r = 6371.0
    f1, f2 = math.radians(lat1), math.radians(lat2)
    df, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(df / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def normalizar(crudo: dict) -> dict | None:
    """Reduce un lanzamiento de LL2 a los campos que usa el descarte.

    Devuelve None si falta la fecha, que es el único campo imprescindible.
    """
    net = crudo.get("net") or crudo.get("window_start")
    if not isinstance(net, str) or not net:
        return None
    nombre = _texto(crudo, "name") or _texto(crudo, "mission", "name")
    return {
        "id": _texto(crudo, "id"),
        "nombre": nombre,
        "net": net,
        "proveedor": _texto(crudo, "launch_service_provider", "name"),
        "cohete": _texto(crudo, "rocket", "configuration", "full_name")
                  or _texto(crudo, "rocket", "configuration", "name"),
        "sitio": _texto(crudo, "pad", "location", "name") or _texto(crudo, "pad", "name"),
        "pais": _texto(crudo, "pad", "country", "alpha_3_code") or _texto(crudo, "pad", "country_code"),
        "url": _texto(crudo, "url"),
        "lat": _coord(crudo, "pad", "latitude"),
        "lon": _coord(crudo, "pad", "longitude"),
        "starlink": bool(_STARLINK.search(nombre)),
    }


def _fecha(iso: str) -> datetime | None:
    """ISO 8601 de LL2 (siempre UTC) a datetime con zona. None si no se puede."""
    if not isinstance(iso, str):
        return None
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


# ─────────────────────────────────────────────────────────── coincidencias
def coincidencias(lanzamientos: list[dict], cuando: datetime,
                  lat: float | None = None, lon: float | None = None) -> list[dict]:
    """Lanzamientos que podrían explicar algo visto en `cuando` desde (lat, lon).

    Dos ventanas distintas, por razones físicas distintas:
    - cualquier lanzamiento, ±1 día: el ascenso y la pluma se ven esa noche, y
      solo desde relativamente cerca, así que además se filtra por distancia;
    - Starlink, hasta 72 h antes y sin filtro de distancia: el tren de satélites
      da la vuelta al mundo y se ve lejísimos del sitio de lanzamiento.

    Si falta la coordenada del caso o la del pad, no se filtra por distancia y se
    dice en el detalle que no se pudo comprobar. Función pura: no toca la red.
    """
    if cuando.tzinfo is None:
        cuando = cuando.replace(tzinfo=timezone.utc)
    general = timedelta(days=CFG.dias_lanzamiento)
    tren = timedelta(hours=CFG.horas_starlink)
    out = []
    for l in lanzamientos:
        t = _fecha(l.get("net", ""))
        if t is None:
            continue
        delta = cuando - t
        fuente = l.get("url") or CFG.ll2_base + "/launches/"
        desde = f" desde {l['sitio']}" if l.get("sitio") else ""

        if l.get("starlink") and timedelta(0) <= delta <= tren:
            horas = round(delta.total_seconds() / 3600)
            out.append({
                "tipo": "starlink",
                "detalle": f"{l['nombre']} despegó {horas} h antes del avistamiento{desde}. "
                           "Los trenes de satélites se ven como una fila de puntos durante las "
                           "noches siguientes al lanzamiento, y a gran distancia del sitio de "
                           "despegue, así que la lejanía no lo descarta.",
                "fuente": fuente,
            })
            continue

        if abs(delta) > general:
            continue

        km = distancia_km(lat, lon, l.get("lat"), l.get("lon"))
        if km is not None and km > CFG.visibilidad_km:
            continue                                   # imposible de ver desde ahí
        if km is None:
            nota_dist = (" No se pudo comprobar si era visible desde el lugar del avistamiento, "
                         "porque falta la coordenada del caso o la del sitio de lanzamiento.")
        else:
            nota_dist = f" El sitio de lanzamiento está a unos {round(km):,} km del avistamiento.".replace(",", ".")

        cuando_txt = ("el mismo día" if abs(delta) < timedelta(hours=12)
                      else "el día anterior" if delta > timedelta(0) else "el día siguiente")
        out.append({
            "tipo": "lanzamiento",
            "detalle": f"{l['nombre']}"
                       + (f" ({l['cohete']})" if l.get("cohete") else "")
                       + f" despegó {cuando_txt}{desde}, el {t.strftime('%d-%m-%Y a las %H:%M UTC')}."
                       + nota_dist
                       + " Ninguna fuente lo vincula con el avistamiento.",
            "fuente": fuente,
        })
    return out


# ─────────────────────────────────────────────────────────── red y caché
def _ruta():
    return CFG.cache / ARCHIVO


def leer_cache() -> dict:
    p = _ruta()
    if not p.exists():
        return {"obtenido": None, "lanzamientos": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        log.warning("caché de lanzamientos ilegible: %s", e)
        return {"obtenido": None, "lanzamientos": []}


def _guardar(datos: dict) -> None:
    p = _ruta()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def obtener(sesion=None) -> dict:
    """Descarga la última página de lanzamientos pasados y la cachea.

    Devuelve {"lanzamientos": [...], "obtenido": iso, "origen": "api"|"cache",
              "nota": str|None}. Nunca lanza por un fallo de red: degrada a caché.
    """
    import requests

    s = sesion or requests
    # sin mode=list: ese modo no devuelve el pad, y sin las coordenadas del sitio
    # de lanzamiento no se puede juzgar si algo pudo verse desde donde se reportó.
    url = (f"{CFG.ll2_base}/launches/previous/"
           f"?ordering=-net&limit={CFG.ll2_limite}&include_suborbital=false")
    try:
        r = s.get(url, timeout=CFG.ll2_timeout, headers={"User-Agent": CFG.agente})
        if r.status_code == 429:
            raise RuntimeError("429 · cuota horaria de Launch Library agotada para esta IP")
        r.raise_for_status()
        crudos = r.json().get("results", [])
    except Exception as e:                                   # red, cuota, JSON inválido
        cache = leer_cache()
        nota = f"Launch Library no respondió ({e}); se usa la caché del repositorio."
        log.warning(nota)
        cache.update({"origen": "cache", "nota": nota})
        return cache

    lanzamientos = [n for n in (normalizar(c) for c in crudos) if n]
    datos = {
        "obtenido": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fuente": url,
        "lanzamientos": lanzamientos,
    }
    _guardar(datos)
    return {**datos, "origen": "api", "nota": None}
