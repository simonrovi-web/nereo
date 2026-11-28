"""Empaquetado de los reportes para el visor.

Escribe dos archivos en data/:
  points-meta.json  n, años, formas, lugares y la tabla de columnas
                    [nombre, tipo, desplazamiento en bytes]
  points.bin.gz     las columnas binarias una tras otra (little-endian),
                    cada una alineada a 4 bytes, comprimidas con gzip

GitHub Pages comprime los .json pero no los binarios, por eso el binario va en
gzip y el navegador lo abre con DecompressionStream. El gzip se escribe con
mtime=0 para que dos ejecuciones con los mismos datos den los mismos bytes y no
ensucien el historial.

Uso directo (convierte un points.json antiguo en base64):
    python pipeline/empaquetar.py data/points.json data
"""
from __future__ import annotations

import base64
import gzip
import json
import os
import sys

import numpy as np

# orden fijo: primero los de 4 bytes, luego 2 y 1, así todo queda alineado
COLUMNAS = [
    ("lat", "i32"), ("lon", "i32"),
    ("year", "u16"), ("dur", "u16"), ("dcoast", "u16"), ("place", "u16"),
    ("month", "u8"), ("day", "u8"), ("hour", "u8"), ("shape", "u8"), ("mar", "u8"),
    ("flags", "u8"), ("ev", "u8"), ("exp", "u8"), ("sol", "u8"),
]
DTYPE = {"i32": "<i4", "u16": "<u2", "u8": "u1"}


def escribir(cols: dict, n: int, shapes: list, places: list, y0: int, y1: int, out: str) -> None:
    """cols: nombre → array numpy con n elementos."""
    partes, tabla, off = [], [], 0
    for k, t in COLUMNAS:
        a = np.ascontiguousarray(cols[k], dtype=DTYPE[t])
        if len(a) != n:
            raise ValueError(f"columna {k}: {len(a)} elementos, se esperaban {n}")
        b = a.tobytes()
        tabla.append([k, t, off])
        relleno = (-len(b)) % 4
        partes.append(b + b"\0" * relleno)
        off += len(b) + relleno
    os.makedirs(out, exist_ok=True)
    meta = {"n": n, "y0": y0, "y1": y1, "shapes": shapes, "places": places, "cols": tabla}
    with open(os.path.join(out, "points-meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, separators=(",", ":"), ensure_ascii=False)
    with open(os.path.join(out, "points.bin.gz"), "wb") as f:
        f.write(gzip.compress(b"".join(partes), compresslevel=9, mtime=0))
    print("points.bin.gz:", os.path.getsize(os.path.join(out, "points.bin.gz")) // 1024, "KB |",
          "points-meta.json:", os.path.getsize(os.path.join(out, "points-meta.json")) // 1024, "KB")


def desde_json(ruta: str, out: str) -> None:
    raw = json.load(open(ruta, encoding="utf-8"))
    cols = {k: np.frombuffer(base64.b64decode(raw[k]), dtype=DTYPE[t]) for k, t in COLUMNAS}
    escribir(cols, raw["n"], raw["shapes"], raw["places"], raw["y0"], raw["y1"], out)


if __name__ == "__main__":
    desde_json(sys.argv[1] if len(sys.argv) > 1 else "data/points.json",
               sys.argv[2] if len(sys.argv) > 2 else "data")
