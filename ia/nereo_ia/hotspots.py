"""Hotspots espaciales, oleadas espacio-temporales y densidad H3.

Tres técnicas, cada una para una pregunta distinta:

1. DBSCAN ponderado (dónde se reporta más).
   El archivo tiene ~114.000 reportes pero solo ~27.000 coordenadas únicas,
   porque cada reporte se geocodifica a su localidad. Agrupar las localidades
   con su conteo como `sample_weight` da el mismo resultado que agrupar los
   reportes uno a uno, con un costo ~20 veces menor.

2. Intensidad relativa (dónde se reporta más de lo esperable).
   El volumen bruto replica el mapa de población. Cuando hay población por
   localidad, cada hotspot informa reportes por 100.000 habitantes, que es la
   métrica que de verdad distingue un foco de una ciudad grande.

3. HDBSCAN espacio-temporal (oleadas históricas).
   Cada reporte se proyecta a coordenadas cartesianas en km sobre la esfera y
   se le agrega el tiempo escalado (km por día). Los clústeres densos en esa
   métrica son concentraciones en un lugar Y en un momento: oleadas.
"""
from __future__ import annotations

import logging
import re
from collections import Counter

import h3
import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN, HDBSCAN

from .config import CFG

log = logging.getLogger(__name__)
R_TIERRA = 6371.0088


def _cartesiano_km(lat, lon) -> np.ndarray:
    la, lo = np.radians(lat), np.radians(lon)
    return np.column_stack([R_TIERRA * np.cos(la) * np.cos(lo),
                            R_TIERRA * np.cos(la) * np.sin(lo),
                            R_TIERRA * np.sin(la)])


def _dist_km(lat1, lon1, lat2, lon2):
    la1, lo1, la2, lo2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
    return 2 * R_TIERRA * np.arcsin(np.sqrt(a))


def limpio(lugar: str) -> str:
    """Quita comentarios del informante: 'Spokane (30 mi SW), WA' → 'Spokane, WA'."""
    s = re.sub(r"\s*\([^)]*\)?", "", str(lugar)).strip()
    return re.sub(r"\s+,", ",", s)


def _resumen_grupo(g: pd.DataFrame) -> dict:
    formas = Counter(g["forma"]).most_common(3)
    horas = g.loc[g["hora_valida"], "hour"]
    return {
        "maritimo_pct": round(100 * g["maritimo"].mean(), 1),
        "explicable_pct": round(100 * g["explicable"].mean(), 1),
        "solidez_media": round(g["sol"].mean(), 2),
        "nocturno_pct": round(100 * g["nocturno"].mean(), 1),
        "formas": [[f, int(n)] for f, n in formas],
        "hora_pico": int(horas.mode().iloc[0]) if len(horas) else None,
    }


# ─────────────────────────────────────────────────────────────── 1 y 2
def hotspots(df: pd.DataFrame, poblacion: dict[str, int] | None = None) -> dict:
    loc = (df.groupby(["lat", "lon"], as_index=False)
             .agg(n=("lat", "size"), lugar=("lugar", "first")))
    X = np.radians(loc[["lat", "lon"]].to_numpy())
    modelo = DBSCAN(eps=CFG.hot_eps_km / R_TIERRA, min_samples=CFG.hot_min_reportes,
                    metric="haversine", algorithm="ball_tree")
    loc["cluster"] = modelo.fit_predict(X, sample_weight=loc["n"].to_numpy())
    log.info("DBSCAN: %d localidades, %d clústeres", len(loc), loc["cluster"].max() + 1)

    clave = df["lat"].astype(str) + "|" + df["lon"].astype(str)
    mapa = dict(zip(loc["lat"].astype(str) + "|" + loc["lon"].astype(str), loc["cluster"]))
    df = df.assign(cluster=clave.map(mapa).fillna(-1).astype(int))

    salida = []
    anio_ref = df["year"].max()
    g_rec = (df["year"] > anio_ref - 5).sum()
    g_prev = ((df["year"] > anio_ref - 10) & (df["year"] <= anio_ref - 5)).sum()
    ratio_global = g_rec / g_prev if g_prev else 1.0
    for cid, g in df[df["cluster"] >= 0].groupby("cluster"):
        locs = loc[loc["cluster"] == cid]
        w = locs["n"].to_numpy()
        lat_c, lon_c = np.average(locs["lat"], weights=w), np.average(locs["lon"], weights=w)
        radio = float(np.percentile(_dist_km(lat_c, lon_c, locs["lat"], locs["lon"]), 90))
        reciente = (g["year"] > anio_ref - 5).sum()
        previo = ((g["year"] > anio_ref - 10) & (g["year"] <= anio_ref - 5)).sum()
        item = {
            "id": int(cid),
            "lat": round(lat_c, 4), "lon": round(lon_c, 4), "radio_km": round(max(radio, 5.0), 1),
            "n": int(len(g)), "localidades": int(len(locs)),
            "lugar": limpio(locs.sort_values("n", ascending=False)["lugar"].iloc[0]),
            "desde": int(g["year"].min()), "hasta": int(g["year"].max()),
            # cambio de los últimos 5 años frente a los 5 anteriores, descontada la tendencia global
            "tendencia_rel_pct": round(((reciente / previo) / ratio_global - 1) * 100, 1) if previo >= 20 else None,
            **_resumen_grupo(g),
        }
        if poblacion:
            pob = sum(poblacion.get(l, 0) for l in locs["lugar"])
            if pob >= 20000:
                item["poblacion"] = int(pob)
                item["por_100k"] = round(len(g) / pob * 1e5, 1)
        salida.append(item)

    salida.sort(key=lambda h: -h["n"])
    for i, h in enumerate(salida, 1):
        h["rango"] = i
    intensos = sorted([h for h in salida if "por_100k" in h and h["n"] >= 2 * CFG.hot_min_reportes],
                      key=lambda h: -h["por_100k"])
    return {
        "metodo": f"DBSCAN haversine ponderado · eps {CFG.hot_eps_km} km · mínimo {CFG.hot_min_reportes} reportes",
        "total_clusteres": len(salida),
        "reportes_en_clusteres": int(sum(h["n"] for h in salida)),
        "cobertura_pct": round(100 * sum(h["n"] for h in salida) / len(df), 1),
        "por_volumen": salida[: CFG.hot_top],
        "por_intensidad": [h["id"] for h in intensos[:15]],
        "normalizado_por_poblacion": bool(poblacion),
        "tendencia_global_pct": round((ratio_global - 1) * 100, 1),
    }


# ─────────────────────────────────────────────────────────────── 3
def oleadas(df: pd.DataFrame) -> dict:
    d = df[(df["year"] >= CFG.ola_desde)].reset_index(drop=True)
    t_dias = (d["fecha"] - d["fecha"].min()).dt.total_seconds().to_numpy() / 86400.0
    X = np.column_stack([_cartesiano_km(d["lat"], d["lon"]), t_dias * CFG.ola_km_por_dia])
    modelo = HDBSCAN(min_cluster_size=CFG.ola_min_cluster, min_samples=CFG.ola_min_cluster,
                     algorithm="kd_tree", copy=True)
    etiquetas = modelo.fit_predict(X)
    # núcleo de cada oleada: se descartan los miembros con baja probabilidad de pertenencia,
    # que HDBSCAN agrega en los bordes y estiran la duración y el radio artificialmente
    etiquetas = np.where(modelo.probabilities_ >= 0.4, etiquetas, -1)
    d["ola"] = etiquetas
    log.info("HDBSCAN espacio-temporal: %d candidatos", etiquetas.max() + 1)

    olas = []
    for cid, g in d[d["ola"] >= 0].groupby("ola"):
        dias = (g["fecha"].max() - g["fecha"].min()).total_seconds() / 86400
        if dias > 21 or g["lugar"].nunique() < 3:          # oleada = corta y en varias localidades
            continue
        lat_c, lon_c = g["lat"].mean(), g["lon"].mean()
        md = g["fecha"].dt.strftime("%m-%d")
        olas.append({
            "id": int(cid), "n": int(len(g)), "localidades": int(g["lugar"].nunique()),
            "lat": round(lat_c, 3), "lon": round(lon_c, 3),
            "radio_km": round(float(np.percentile(_dist_km(lat_c, lon_c, g["lat"], g["lon"]), 90)), 1),
            "inicio": str(g["fecha"].min().date()), "fin": str(g["fecha"].max().date()),
            "dias": round(dias, 1),
            "lugar": limpio(g["lugar"].value_counts().index[0]),
            "fecha_festiva": bool(md.isin(["07-04", "07-05", "12-31", "01-01"]).mean() > 0.5),
            **_resumen_grupo(g),
        })
    olas.sort(key=lambda o: -o["n"])
    festivas = sum(o["fecha_festiva"] for o in olas)
    return {
        "metodo": (f"HDBSCAN sobre (x, y, z, t) · {CFG.ola_km_por_dia} km equivalen a un día · "
                   f"mínimo {CFG.ola_min_cluster} reportes · duración máxima 21 días · desde {CFG.ola_desde}"),
        "total": len(olas),
        "en_fechas_festivas": int(festivas),
        "sin_fecha_festiva": [o for o in olas if not o["fecha_festiva"]][: CFG.ola_top],
        "festivas_top": [o for o in olas if o["fecha_festiva"]][:5],
    }


# ─────────────────────────────────────────────────────────────── H3
def hexagonos(df: pd.DataFrame) -> dict:
    res = CFG.h3_res_mapa
    celdas = [h3.latlng_to_cell(a, b, res) for a, b in zip(df["lat"], df["lon"])]
    d = df.assign(h3=celdas)
    g = d.groupby("h3").agg(n=("h3", "size"), mar=("maritimo", "mean"), exp=("explicable", "mean"),
                            sol=("sol", "mean"), recientes=("year", lambda y: int((y >= y.max() - 4).sum())))
    g = g[g["n"] >= CFG.h3_min_reportes].sort_values("n", ascending=False)
    celdas_out = []
    for cel, r in g.iterrows():
        borde = [[round(lo, 3), round(la, 3)] for la, lo in h3.cell_to_boundary(cel)]
        celdas_out.append({"h": cel, "n": int(r["n"]), "mar": round(float(r["mar"]), 3),
                           "exp": round(float(r["exp"]), 3), "sol": round(float(r["sol"]), 2), "b": borde})
    return {"resolucion": res, "area_km2_aprox": round(h3.average_hexagon_area(res, unit="km^2")),
            "min_reportes": CFG.h3_min_reportes, "total": len(celdas_out), "celdas": celdas_out}
