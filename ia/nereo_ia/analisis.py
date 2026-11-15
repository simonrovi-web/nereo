"""Orquestación de la capa analítica y escritura de data/ia/*.json."""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

from . import anomalias, datos, fuentes, hotspots, recomendaciones, series, textos
from .config import CFG

log = logging.getLogger(__name__)


def _paso(nombre, fn, *a):
    t = time.time()
    r = fn(*a)
    log.info("✓ %s (%.1f s)", nombre, time.time() - t)
    return r


def analizar(con_texto: bool = True) -> dict:
    df, meta = datos.cargar()
    pob = fuentes.poblacion_por_lugar()
    r = {"meta": {**meta, "normalizado_por_poblacion": bool(pob)}}
    r["hotspots"] = _paso("hotspots (DBSCAN)", hotspots.hotspots, df, pob)
    r["oleadas"] = _paso("oleadas (HDBSCAN espacio-temporal)", hotspots.oleadas, df)
    r["hexagonos"] = _paso("densidad H3", hotspots.hexagonos, df)
    r["anomalias"] = _paso("anomalías celda-mes (Isolation Forest)", anomalias.celdas_mes, df)
    r["anomalias_reportes"] = _paso("anomalías por reporte (Isolation Forest)", anomalias.reportes, df)
    r["estacionalidad"] = _paso("estacionalidad", series.estacionalidad, df)
    r["pronostico"] = _paso("pronóstico", series.pronostico, df)
    r["temas"] = _paso("temas de texto", textos.temas) if con_texto else {"disponible": False, "motivo": "desactivado"}
    camaras = (datos.cargar_json("cams.json") or {}).get("sitios", [])
    zonas = (datos.cargar_json("recientes.json") or {}).get("zonas", [])
    r["recomendaciones"] = recomendaciones.calcular(r["hotspots"], r["oleadas"], r["anomalias"],
                                                    r["estacionalidad"], r["pronostico"], camaras, zonas)
    guardar(r)
    return r


def guardar(r: dict) -> None:
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    datos.guardar("hotspots.json", {"generado": ahora, **r["hotspots"], "oleadas": r["oleadas"]})
    datos.guardar("hexagonos.json", {"generado": ahora, **r["hexagonos"]})
    datos.guardar("anomalias.json", {"generado": ahora, "celdas_mes": r["anomalias"], "reportes": r["anomalias_reportes"]})
    datos.guardar("temporal.json", {"generado": ahora, "estacionalidad": r["estacionalidad"], **r["pronostico"]})
    datos.guardar("temas.json", {"generado": ahora, **r["temas"]})
    datos.guardar("recomendaciones.json", {"generado": ahora, "items": r["recomendaciones"]})
    datos.guardar("meta.json", {"generado": ahora, "archivo": r["meta"], "version": "1.0",
                                "parametros": {k: v for k, v in CFG.__dict__.items() if isinstance(v, (int, float, str))}})


def cargar_resultados() -> dict:
    """Relee data/ia/*.json para redactar sin repetir el análisis."""
    leer = lambda n: json.loads((CFG.salida / n).read_text(encoding="utf-8"))
    hot, tmp, an = leer("hotspots.json"), leer("temporal.json"), leer("anomalias.json")
    est = tmp.pop("estacionalidad")
    return {"meta": leer("meta.json")["archivo"], "hotspots": hot, "oleadas": hot["oleadas"],
            "anomalias": an["celdas_mes"], "estacionalidad": est, "pronostico": tmp,
            "temas": leer("temas.json"), "recomendaciones": leer("recomendaciones.json")["items"]}
