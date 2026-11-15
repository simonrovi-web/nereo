"""Servicio HTTP opcional para uso local (FastAPI).

En producción NEREO corre el análisis en GitHub Actions y publica JSON
estático. Este servicio sirve para explorar y re-ejecutar en un equipo propio:

    uvicorn nereo_ia.api:app --reload --port 8800
"""
from __future__ import annotations

import json
import threading

from fastapi import BackgroundTasks, FastAPI, HTTPException

from . import analisis, datos, llm
from .config import CFG

app = FastAPI(title="NEREO · Inteligencia", version="1.0")
_lock = threading.Lock()
ARCHIVOS = {"resumen", "hotspots", "hexagonos", "anomalias", "temporal", "temas", "recomendaciones", "meta"}


@app.get("/salud")
def salud():
    import requests
    try:
        ok = requests.get(f"{CFG.ollama_url}/api/tags", timeout=3).ok
    except Exception:
        ok = False
    return {"ok": True, "ollama": ok, "modelo": CFG.ollama_modelo, "salida": str(CFG.salida)}


@app.get("/resultados/{nombre}")
def resultado(nombre: str):
    if nombre not in ARCHIVOS:
        raise HTTPException(404, "resultado desconocido")
    p = CFG.salida / f"{nombre}.json"
    if not p.exists():
        raise HTTPException(404, "aún no generado: ejecuta POST /analizar")
    return json.loads(p.read_text(encoding="utf-8"))


def _correr(redactar: bool):
    with _lock:
        r = analisis.analizar()
        if redactar:
            datos.guardar("resumen.json", llm.redactar(r))


@app.post("/analizar")
def analizar(bg: BackgroundTasks, redactar: bool = True):
    if _lock.locked():
        raise HTTPException(409, "ya hay un análisis en curso")
    bg.add_task(_correr, redactar)
    return {"estado": "en curso"}


@app.post("/redactar")
def redactar():
    return llm.redactar(analisis.cargar_resultados())
