"""Detección de anomalías con Isolation Forest.

Dos escalas:

· Celda-mes: cada combinación (celda H3 de ~12.000 km², mes) se describe por
  su volumen, su desvío frente a la historia de la propia celda y la mezcla
  de rasgos de sus reportes. Una celda-mes anómala es un mes en que esa región
  reportó mucho más, o algo muy distinto, de lo habitual.

· Reporte individual: reportes cuya combinación de rasgos es rara en todo el
  archivo (por ejemplo, larga duración + radar + sobre el agua). Son los
  candidatos a revisar a mano.

En ambos casos se informan los rasgos que más se apartan de lo normal, para
que el resultado sea explicable y no una caja negra.
"""
from __future__ import annotations

import logging

import h3
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from .config import CFG
from .hotspots import limpio

log = logging.getLogger(__name__)

NOMBRES = {
    "log_n": "volumen de reportes", "exceso": "exceso sobre su historia", "mar": "proporción marítima",
    "sol": "solidez media", "exp": "proporción explicable", "noct": "proporción nocturna",
    "luz": "proporción de luces simples", "dur": "duración", "radar": "mención de radar",
    "video": "registro visual declarado", "multi": "varios testigos", "costa": "cercanía a la costa",
    "agua": "relación con el agua", "hora": "hora inusual",
}


def _factores(z: np.ndarray, cols: list[str], k: int = 3) -> list[list]:
    orden = np.argsort(-np.abs(z))[:k]
    return [[NOMBRES.get(cols[i], cols[i]), round(float(z[i]), 2)] for i in orden if abs(z[i]) >= 1.0]


def celdas_mes(df: pd.DataFrame) -> dict:
    d = df[df["year"] >= CFG.anom_desde].copy()
    d["h3"] = [h3.latlng_to_cell(a, b, CFG.h3_res_anomalias) for a, b in zip(d["lat"], d["lon"])]
    d["mes"] = d["fecha"].dt.to_period("M")
    d["luz"] = d["forma"].isin(["light", "fireball", "orb", "flash", "star"])
    g = d.groupby(["h3", "mes"]).agg(
        n=("h3", "size"), mar=("maritimo", "mean"), sol=("sol", "mean"), exp=("explicable", "mean"),
        noct=("nocturno", "mean"), luz=("luz", "mean"),
        lugar=("lugar", lambda s: s.value_counts().index[0])).reset_index()

    # historia de cada celda: mediana móvil de 24 meses previos (sin incluir el mes)
    g = g.sort_values(["h3", "mes"])
    g["base"] = (g.groupby("h3")["n"].transform(lambda s: s.shift(1).rolling(24, min_periods=6).median()))
    g = g.dropna(subset=["base"])
    g = g[g["n"] >= 5].copy()
    g["log_n"] = np.log1p(g["n"])
    g["exceso"] = np.log1p(g["n"]) - np.log1p(g["base"])

    cols = ["log_n", "exceso", "mar", "sol", "exp", "noct", "luz"]
    esc = StandardScaler().fit(g[cols])
    Z = esc.transform(g[cols])
    bosque = IsolationForest(n_estimators=300, contamination=CFG.anom_contaminacion, random_state=CFG.semilla)
    g["anomala"] = bosque.fit_predict(Z) == -1
    g["puntaje"] = -bosque.score_samples(Z)

    # nos interesan las anomalías por exceso (más reportes de lo esperable), no por escasez
    top = g[g["anomala"] & (g["exceso"] > 0)].sort_values("puntaje", ascending=False).head(CFG.anom_top)
    salida = []
    for (_, r), z in zip(top.iterrows(), esc.transform(top[cols])):
        la, lo = h3.cell_to_latlng(r["h3"])
        salida.append({
            "h3": r["h3"], "lat": round(la, 3), "lon": round(lo, 3), "mes": str(r["mes"]),
            "n": int(r["n"]), "esperado": round(float(r["base"]), 1),
            "veces": round(float(r["n"] / max(r["base"], 0.5)), 1),
            "lugar": limpio(r["lugar"]), "puntaje": round(float(r["puntaje"]), 3),
            "explicable_pct": round(100 * float(r["exp"]), 1),
            "maritimo_pct": round(100 * float(r["mar"]), 1),
            "factores": _factores(z, cols),
        })
    log.info("Isolation Forest celda-mes: %d evaluadas, %d anómalas", len(g), int(g["anomala"].sum()))
    return {
        "metodo": (f"Isolation Forest · celdas H3 res {CFG.h3_res_anomalias} por mes desde {CFG.anom_desde} · "
                   f"contaminación {CFG.anom_contaminacion} · base: mediana de los 24 meses previos"),
        "evaluadas": int(len(g)), "anomalas": int(g["anomala"].sum()), "top": salida,
    }


def reportes(df: pd.DataFrame) -> dict:
    d = df.copy()
    feats = pd.DataFrame({
        "dur": np.log1p(d["dur_s"].clip(0, 86400)),
        "radar": (d["ev"] & 4 > 0).astype(float), "video": (d["ev"] & 3 > 0).astype(float),
        "multi": (d["ev"] & 8 > 0).astype(float), "agua": (d["mar"] >= 2).astype(float),
        "costa": -np.log1p(d["dcoast"].clip(0, 2000)),
        "hora": np.where(d["hora_valida"], np.abs(((d["hour"] + 2) % 24) - 12) / 12.0, 0.5),
        "exp": d["explicable"].astype(float),
    })
    cols = list(feats.columns)
    esc = StandardScaler().fit(feats)
    Z = esc.transform(feats)
    bosque = IsolationForest(n_estimators=300, contamination=0.002, random_state=CFG.semilla)
    etiqueta = bosque.fit_predict(Z)
    puntaje = -bosque.score_samples(Z)
    # anomalías "interesantes": más información de lo normal y sin explicación convencional
    interes = (etiqueta == -1) & (d["sol"] >= 3) & (~d["explicable"])
    idx = np.argsort(-np.where(interes, puntaje, -1))[:CFG.anom_top]
    salida = []
    for i in idx:
        if not interes[i]:
            break
        r = d.iloc[i]
        salida.append({
            "lugar": limpio(r["lugar"]), "fecha": str(r["fecha"].date()), "lat": round(float(r["lat"]), 3),
            "lon": round(float(r["lon"]), 3), "forma": r["forma"], "solidez": int(r["sol"]),
            "duracion_s": int(r["dur_s"]), "categoria_mar": int(r["mar"]),
            "puntaje": round(float(puntaje[i]), 3), "factores": _factores(Z[i], cols),
        })
    return {"metodo": "Isolation Forest sobre rasgos del reporte · contaminación 0,002 · filtrado a solidez ≥ 3 y sin explicación",
            "anomalos": int((etiqueta == -1).sum()), "top": salida}
