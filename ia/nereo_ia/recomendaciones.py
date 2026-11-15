"""Recomendaciones accionables calculadas, no imaginadas.

El LLM las redacta, pero cada una nace aquí de una regla verificable sobre
los resultados analíticos. Así ninguna recomendación depende de lo que el
modelo de lenguaje "crea".
"""
from __future__ import annotations

import numpy as np

from .hotspots import _dist_km


def calcular(hot: dict, olas: dict, anom: dict, est: dict, pron: dict, camaras: list, zonas: list) -> list[dict]:
    recs: list[dict] = []
    top = hot["por_volumen"]

    # 1 · hotspots intensos sin zona de vigilancia
    por_id = {h["id"]: h for h in hot["por_volumen"]}
    intensos = [por_id[i] for i in hot["por_intensidad"] if i in por_id]   # orden por intensidad
    sin_zona = [h for h in intensos
                if not any(_dist_km(h["lat"], h["lon"], z["lat"], z["lon"]) <= z["km"] for z in zonas)]
    if sin_zona:
        recs.append({
            "tipo": "zona", "prioridad": "alta",
            "accion": "Crear zonas de vigilancia en los focos de mayor intensidad relativa",
            "datos": [{"lugar": h["lugar"], "por_100k": h["por_100k"], "n": h["n"], "lat": h["lat"], "lon": h["lon"],
                       "radio_km": h["radio_km"]} for h in sin_zona[:5]],
        })

    # 2 · cobertura de cámaras de cielo
    if camaras:
        lejos = []
        for h in top[:20]:
            d = min(float(_dist_km(h["lat"], h["lon"], c["lat"], c["lon"])) for c in camaras)
            if d > 300:
                lejos.append({"lugar": h["lugar"], "n": h["n"], "camara_mas_cercana_km": round(d)})
        if lejos:
            recs.append({"tipo": "camaras", "prioridad": "media",
                         "accion": "Sumar cámaras de cielo completo cerca de hotspots sin cobertura (más de 300 km)",
                         "datos": lejos[:6]})

    # 3 · ventana horaria de vigilancia
    horas = sorted(est["hora"], key=lambda x: -x["indice"])[:4]
    recs.append({"tipo": "horario", "prioridad": "media",
                 "accion": "Concentrar la revisión del feed en la franja de mayor actividad",
                 "datos": {"horas_pico": [h["k"] for h in horas], "indices": [h["indice"] for h in horas],
                           "mes_pico": est["mes_pico"], "dia_pico": est["dia_pico"]}})

    # 4 · filtro de fechas festivas
    festivos = [d for d in est["dias_mas_cargados"] if d["dia"] in ("07-04", "07-05", "12-31", "01-01")]
    if festivos:
        recs.append({"tipo": "filtro", "prioridad": "alta",
                     "accion": "Marcar por defecto como 'probable fuego artificial o farolillo' los reportes de fechas festivas",
                     "datos": {"dias": festivos, "oleadas_festivas": olas["en_fechas_festivas"]}})

    # 5 · revisar anomalías sin explicación
    sin_exp = [a for a in anom["top"] if a["explicable_pct"] < 20][:5]
    if sin_exp:
        recs.append({"tipo": "revision", "prioridad": "alta",
                     "accion": "Revisar a mano las concentraciones anómalas que no tienen explicación convencional",
                     "datos": [{"lugar": a["lugar"], "mes": a["mes"], "n": a["n"], "veces": a["veces"]} for a in sin_exp]})

    # 6 · calibración del pronóstico
    c = pron.get("contraste") or {}
    if c.get("error_pct") is not None and abs(c["error_pct"]) > 25:
        recs.append({"tipo": "datos", "prioridad": "media",
                     "accion": "Actualizar el archivo con reportes posteriores a 2023: el pronóstico se desvía de la cifra publicada",
                     "datos": {"periodo": c["periodo"], "real": c["reportes"], "esperado": c["esperado"], "error_pct": c["error_pct"]}})
    return recs
