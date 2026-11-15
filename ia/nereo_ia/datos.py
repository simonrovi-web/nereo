"""Carga del archivo de avistamientos de NEREO.

El visor guarda los 114.034 reportes en data/points.json como columnas
binarias codificadas en base64. Este módulo las decodifica a un DataFrame
con nombres explícitos, sin depender del pipeline que las generó.
"""
from __future__ import annotations

import base64
import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from .config import CFG

# columna → (tipo numpy, factor de escala)
_COLUMNAS = {
    "lat": (np.int32, 1e-4), "lon": (np.int32, 1e-4),
    "year": (np.uint16, 1), "month": (np.uint8, 1), "day": (np.uint8, 1), "hour": (np.uint8, 1),
    "shape": (np.uint8, 1), "mar": (np.uint8, 1), "flags": (np.uint8, 1), "ev": (np.uint8, 1),
    "exp": (np.uint8, 1), "sol": (np.uint8, 1), "dur": (np.uint16, 1), "dcoast": (np.uint16, 1),
    "place": (np.uint16, 1),
}

CATEGORIAS_MAR = ["aéreo", "costero", "desde embarcación", "sobre el agua", "entró al agua", "emergió del agua"]


def _dec(b64: str, tipo) -> np.ndarray:
    return np.frombuffer(base64.b64decode(b64), dtype=tipo)


@lru_cache(maxsize=2)
def cargar(ruta: Path | None = None) -> tuple[pd.DataFrame, dict]:
    """Devuelve (df, meta). meta trae las listas de formas y lugares."""
    ruta = ruta or (CFG.datos / "points.json")
    raw = json.loads(Path(ruta).read_text(encoding="utf-8"))
    cols = {}
    for c, (t, f) in _COLUMNAS.items():
        v = _dec(raw[c], t)
        cols[c] = v * f if f != 1 else v.astype(np.int64)
    df = pd.DataFrame(cols)
    if len(df) != raw["n"]:
        raise ValueError(f"points.json inconsistente: {len(df)} filas, se esperaban {raw['n']}")

    df["forma"] = np.array(raw["shapes"])[df["shape"].to_numpy()]
    df["lugar"] = np.array(raw["places"], dtype=object)[df["place"].to_numpy()]
    # duración real en segundos (se guardó como log1p * 1000)
    df["dur_s"] = np.expm1(df["dur"] / 1000.0).round()
    df["hora_valida"] = df["hour"] <= 23
    dia = df["day"].clip(lower=1)
    hora = df["hour"].where(df["hora_valida"], 12)
    df["fecha"] = pd.to_datetime(dict(year=df["year"], month=df["month"].clip(1, 12), day=dia, hour=hora),
                                 errors="coerce")
    df = df.dropna(subset=["fecha"]).reset_index(drop=True)
    df["maritimo"] = df["mar"] > 0
    df["explicable"] = df["exp"] > 0
    df["nocturno"] = df["hora_valida"] & ((df["hour"] >= 20) | (df["hour"] < 5))

    meta = {"n": int(len(df)), "formas": raw["shapes"], "desde": int(df["year"].min()),
            "hasta": str(df["fecha"].max().date())}
    return df, meta


def cargar_json(nombre: str, defecto=None):
    """Lee un JSON de data/ (cams.json, recientes.json…) si existe."""
    p = CFG.datos / nombre
    if not p.exists():
        return defecto
    return json.loads(p.read_text(encoding="utf-8"))


def guardar(nombre: str, obj) -> Path:
    CFG.salida.mkdir(parents=True, exist_ok=True)
    p = CFG.salida / nombre
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=_json_default), encoding="utf-8")
    return p


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else round(float(o), 4)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp,)):
        return o.isoformat()
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))
