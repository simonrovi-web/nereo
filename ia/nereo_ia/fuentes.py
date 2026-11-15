"""Fuentes externas opcionales: población por localidad y relatos de texto.

Se descargan a ia/fuentes/ (fuera del control de versiones). Si no están
disponibles, el análisis sigue sin normalizar por población y sin temas de
texto. Los relatos NUNCA se publican: solo se usan para derivar temas.
"""
from __future__ import annotations

import html
import logging

import pandas as pd

from .config import CFG

log = logging.getLogger(__name__)

URLS = {
    "lugares.csv": "https://raw.githubusercontent.com/rfordatascience/tidytuesday/master/data/2023/2023-06-20/places.csv",
    "relatos_2023.csv": "https://raw.githubusercontent.com/rfordatascience/tidytuesday/master/data/2023/2023-06-20/ufo_sightings.csv",
    "relatos_hist.csv": "https://raw.githubusercontent.com/planetsig/ufo-reports/master/csv-data/ufo-scrubbed-geocoded-time-standardized.csv",
}


def descargar(forzar: bool = False) -> dict[str, bool]:
    """Descarga las fuentes. Devuelve {archivo: disponible}."""
    import requests
    CFG.fuentes.mkdir(parents=True, exist_ok=True)
    estado = {}
    for nombre, url in URLS.items():
        destino = CFG.fuentes / nombre
        if destino.exists() and not forzar:
            estado[nombre] = True
            continue
        try:
            r = requests.get(url, timeout=180)
            r.raise_for_status()
            destino.write_bytes(r.content)
            estado[nombre] = True
            log.info("descargado %s (%d KB)", nombre, len(r.content) // 1024)
        except Exception as e:                                   # red caída, URL movida…
            log.warning("no se pudo descargar %s: %s", nombre, e)
            estado[nombre] = False
    return estado


def poblacion_por_lugar() -> dict[str, int]:
    """'Ciudad, ESTADO' → población, con las mismas reglas de nombre que points.json."""
    p = CFG.fuentes / "lugares.csv"
    if not p.exists():
        return {}
    d = pd.read_csv(p, keep_default_na=False, low_memory=False)
    d["population"] = pd.to_numeric(d["population"], errors="coerce")
    d = d[d["population"] > 0]
    out: dict[str, int] = {}
    for city, st, cc, pob in zip(d["city"], d["state"], d["country_code"], d["population"]):
        cola = (st if st and st != "NA" else cc).upper()
        for nombre in {f"{city}, {cola}", f"{str(city).title()}, {cola}"}:
            out[nombre] = max(out.get(nombre, 0), int(pob))
    return out


def relatos(muestra: int | None = None, semilla: int = 42) -> pd.DataFrame:
    """Devuelve columnas [texto, anio, forma]. Uso interno exclusivo."""
    partes = []
    h = CFG.fuentes / "relatos_hist.csv"
    if h.exists():
        a = pd.read_csv(h, header=None, low_memory=False, usecols=[0, 4, 7], names=["dt", "forma", "texto"])
        a["anio"] = pd.to_datetime(a["dt"], format="%m/%d/%Y %H:%M", errors="coerce").dt.year
        a["texto"] = a["texto"].map(lambda s: html.unescape(html.unescape(s)).replace("&#44", ",") if isinstance(s, str) else "")
        partes.append(a[["texto", "anio", "forma"]])
    n = CFG.fuentes / "relatos_2023.csv"
    if n.exists():
        b = pd.read_csv(n, low_memory=False, keep_default_na=False, usecols=["reported_date_time", "shape", "summary"])
        b["anio"] = pd.to_datetime(b["reported_date_time"], errors="coerce", utc=True).dt.year
        b = b.rename(columns={"summary": "texto", "shape": "forma"})
        b = b[b["anio"] > 2014]
        partes.append(b[["texto", "anio", "forma"]])
    if not partes:
        return pd.DataFrame(columns=["texto", "anio", "forma"])
    df = pd.concat(partes, ignore_index=True)
    df["texto"] = df["texto"].astype(str).str.strip()
    df = df[df["texto"].str.len() >= 25].drop_duplicates("texto")
    df["forma"] = df["forma"].astype(str).str.lower().replace({"na": "unknown", "nan": "unknown"})
    if muestra and len(df) > muestra:
        df = df.sample(muestra, random_state=semilla)
    return df.reset_index(drop=True)
