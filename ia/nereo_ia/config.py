"""Parámetros del módulo de inteligencia de NEREO.

Todo valor ajustable vive aquí. Se puede sobreescribir con variables de
entorno con el prefijo NEREO_ (por ejemplo NEREO_OLLAMA_MODELO=qwen2.5:3b).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]          # raíz del repositorio


def _env(nombre: str, defecto):
    v = os.environ.get("NEREO_" + nombre)
    if v is None:
        return defecto
    return type(defecto)(v) if not isinstance(defecto, bool) else v.lower() in ("1", "true", "si", "sí")


@dataclass(frozen=True)
class Config:
    # rutas
    datos: Path = RAIZ / "data"
    salida: Path = RAIZ / "data" / "ia"
    fuentes: Path = RAIZ / "ia" / "fuentes"           # descargas no versionadas (relatos, población)

    # hotspots espaciales · DBSCAN ponderado sobre localidades únicas
    hot_eps_km: float = _env("HOT_EPS_KM", 12.0)
    hot_min_reportes: int = _env("HOT_MIN", 150)
    hot_top: int = _env("HOT_TOP", 40)

    # oleadas históricas · HDBSCAN espacio-temporal
    ola_km_por_dia: float = _env("OLA_KM_DIA", 25.0)  # cuántos km "vale" un día de separación
    ola_min_cluster: int = _env("OLA_MIN", 12)
    ola_desde: int = _env("OLA_DESDE", 1995)
    ola_top: int = _env("OLA_TOP", 30)

    # H3
    h3_res_mapa: int = _env("H3_MAPA", 4)             # ~1.770 km² por celda
    h3_res_anomalias: int = _env("H3_ANOM", 3)        # ~12.400 km² por celda
    h3_min_reportes: int = _env("H3_MIN", 12)

    # anomalías · Isolation Forest
    anom_contaminacion: float = _env("ANOM_CONT", 0.01)
    anom_top: int = _env("ANOM_TOP", 30)
    anom_desde: int = _env("ANOM_DESDE", 2000)

    # series temporales
    serie_desde: int = _env("SERIE_DESDE", 1998)
    pronostico_meses: int = _env("PRON_MESES", 30)

    # temas de texto
    texto_modelo: str = _env("TEXTO_MODELO", "sentence-transformers/all-MiniLM-L6-v2")
    texto_muestra: int = _env("TEXTO_MUESTRA", 25000)
    texto_temas: int = _env("TEXTO_TEMAS", 14)

    # capa interpretativa
    ollama_url: str = _env("OLLAMA_URL", "http://127.0.0.1:11434")
    ollama_modelo: str = _env("OLLAMA_MODELO", "gemma4:e4b")
    ollama_timeout: int = _env("OLLAMA_TIMEOUT", 900)

    semilla: int = 42
    extra: dict = field(default_factory=dict)


CFG = Config()
