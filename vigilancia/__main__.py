"""Interfaz de línea de órdenes del módulo de vigilancia.

    python -m vigilancia calendarios                 descarga y cachea los calendarios
    python -m vigilancia descarte 2026-11-20 [21:27] revisa una fecha y muestra el resultado
    python -m vigilancia feed                        revisa todo data/recientes.json sin escribirlo
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone

from . import descarte
from .config import CFG


def _imprimir(x):
    print(json.dumps(x, ensure_ascii=False, indent=2))


def _calendarios(dia=None):
    cal = descarte.calendarios(dia)
    lan, met = cal["lanzamientos"], cal["meteoros"]
    print(f"Lanzamientos: {len(lan.get('lanzamientos', []))} ({lan.get('origen')})"
          f" · obtenido {lan.get('obtenido')}")
    print(f"Lluvias:      {len(met.get('lluvias', []))} ({met.get('origen')})"
          f" · {met.get('url')}")
    for n in cal["notas"]:
        print("  nota:", n)
    return cal


def main(argv: list[str]) -> int:
    orden = argv[1] if len(argv) > 1 else "calendarios"

    if orden == "calendarios":
        _calendarios()
        return 0

    if orden == "descarte":
        if len(argv) < 3:
            print("falta la fecha: python -m vigilancia descarte 2026-11-20 [21:27]", file=sys.stderr)
            return 2
        f = argv[2]
        hora = argv[3] if len(argv) > 3 else None
        cal = _calendarios(date.fromisoformat(f))
        print()
        _imprimir(descarte.revisar(cal, f, hora))
        return 0

    if orden == "feed":
        p = CFG.cache.parent / "recientes.json"
        if not p.exists():
            print(f"no existe {p}", file=sys.stderr)
            return 2
        feed = json.loads(p.read_text(encoding="utf-8"))
        cal = _calendarios()
        print()
        con, sin = 0, 0
        for it in feed.get("items", []):
            r = descarte.revisar(cal, it.get("fechaEvento", ""), None,
                                 it.get("lat"), it.get("lon"), it.get("rareza"))
            if r["descarteRevisado"]:
                con += 1
                if r["descarte"]:
                    print(f"· {it['id']}  ({it.get('fechaEvento')})")
                    for c in r["descarte"]:
                        print(f"    [{c['tipo']}] {c['detalle'][:120]}…")
            else:
                sin += 1
        print(f"\n{con} casos con fecha revisados, {sin} sin fecha de evento.")
        return 0

    print(f"orden desconocida: {orden}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
