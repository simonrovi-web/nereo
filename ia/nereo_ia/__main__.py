"""CLI del módulo de inteligencia.

    python -m nereo_ia descargar     # fuentes externas opcionales (población, relatos)
    python -m nereo_ia analizar      # capa analítica → data/ia/*.json
    python -m nereo_ia redactar      # capa interpretativa (Ollama) → data/ia/resumen.json
    python -m nereo_ia todo          # las tres en orden
"""
from __future__ import annotations

import argparse
import logging
import sys

from . import analisis, datos, fuentes, llm


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="nereo_ia", description="Inteligencia de NEREO")
    p.add_argument("orden", choices=["descargar", "analizar", "redactar", "todo"])
    p.add_argument("--sin-texto", action="store_true", help="omitir los temas de texto")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(asctime)s %(message)s",
                        datefmt="%H:%M:%S")
    for ruido in ("cmdstanpy", "prophet", "urllib3", "sentence_transformers", "httpx"):
        logging.getLogger(ruido).setLevel(logging.WARNING)

    if a.orden in ("descargar", "todo"):
        fuentes.descargar()
    resultados = None
    if a.orden in ("analizar", "todo"):
        resultados = analisis.analizar(con_texto=not a.sin_texto)
    if a.orden in ("redactar", "todo"):
        resultados = resultados or analisis.cargar_resultados()
        out = llm.redactar(resultados)
        datos.guardar("resumen.json", out)
        v = out["verificacion"]
        logging.info("resumen: motor %s · cifras verificadas %d/%d", out["motor"], v["verificadas"], v["cifras"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
