"""Capa interpretativa: un LLM local (Ollama) redacta lo que la capa analítica calculó.

Principios:
1. El modelo NO analiza datos crudos. Recibe un JSON compacto con resultados
   ya calculados y solo los explica.
2. Toda cifra que escriba se verifica contra ese JSON. Las que no aparecen
   se informan como "no verificadas" en la salida, a la vista del lector.
3. Si Ollama no responde, una plantilla determinística redacta el resumen.
   El visor nunca queda vacío y la salida dice qué motor se usó.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from .config import CFG

log = logging.getLogger(__name__)

SISTEMA = """Eres analista de datos de NEREO, un visor de reportes de avistamientos aéreos y marítimos no identificados.
Recibes resultados estadísticos ya calculados, en JSON. Tu trabajo es explicarlos en español claro para un público general y para el equipo editorial.

Reglas:
- Usa SOLO cifras que aparezcan en el JSON. No calcules cifras nuevas ni redondees de forma distinta.
- Habla de "reportes", nunca de "ovnis confirmados". Un reporte es un testimonio, no un hecho verificado.
- Cuando un patrón tenga una explicación convencional en los datos (fechas festivas, lanzamientos, meteoros), dila primero.
- No especules sobre origen extraterrestre, tecnología secreta ni conspiraciones.
- La concentración en Estados Unidos refleja dónde se reporta a NUFORC, no dónde ocurren más fenómenos.
- Las recomendaciones deben ser las que trae el JSON en "recomendaciones", en el mismo orden, explicadas y convertidas en pasos concretos.
- Responde exclusivamente con el JSON del esquema pedido."""

ESQUEMA = {
    "type": "object",
    "properties": {
        "titular": {"type": "string"},
        "resumen": {"type": "string"},
        "hallazgos": {"type": "array", "items": {"type": "object", "properties": {
            "titulo": {"type": "string"}, "explicacion": {"type": "string"}}, "required": ["titulo", "explicacion"]}},
        "recomendaciones": {"type": "array", "items": {"type": "object", "properties": {
            "accion": {"type": "string"}, "por_que": {"type": "string"}, "como": {"type": "string"}},
            "required": ["accion", "por_que", "como"]}},
        "nombres_temas": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "integer"}, "nombre": {"type": "string"}}, "required": ["id", "nombre"]}},
    },
    "required": ["titular", "resumen", "hallazgos", "recomendaciones", "nombres_temas"],
}


# ─────────────────────────────────────────────────────────────── entrada
def preparar_entrada(r: dict) -> dict:
    """Reduce los resultados a lo que el modelo necesita (≈ 3–4k tokens)."""
    hot, olas, anom, est, pron, tem = (r["hotspots"], r["oleadas"], r["anomalias"], r["estacionalidad"],
                                       r["pronostico"], r["temas"])
    corto = lambda h, ks: {k: h[k] for k in ks if k in h and h[k] is not None}
    por_id = {h["id"]: h for h in hot["por_volumen"]}
    intensos = [por_id[i] for i in hot["por_intensidad"] if i in por_id]   # orden por intensidad
    return {
        "archivo": r["meta"],
        "hotspots": {
            "total": hot["total_clusteres"], "cobertura_pct": hot["cobertura_pct"],
            "tendencia_global_5a_pct": hot["tendencia_global_pct"],
            "mayor_volumen": [corto(h, ["lugar", "n", "por_100k", "tendencia_rel_pct", "maritimo_pct", "explicable_pct"])
                              for h in hot["por_volumen"][:6]],
            "mayor_intensidad_por_100k_habitantes": [corto(h, ["lugar", "n", "por_100k"]) for h in intensos[:5]],
        },
        "oleadas": {
            "total": olas["total"], "en_fechas_festivas": olas["en_fechas_festivas"],
            "principales_no_festivas": [corto(o, ["lugar", "n", "localidades", "inicio", "dias", "explicable_pct"])
                                        for o in olas["sin_fecha_festiva"][:5]],
        },
        "anomalias": {
            "celdas_mes_evaluadas": anom["evaluadas"], "anomalas": anom["anomalas"],
            "principales": [corto(a, ["lugar", "mes", "n", "esperado", "veces", "explicable_pct"]) for a in anom["top"][:5]],
        },
        "estacionalidad": {
            "hora_pico": est["hora_pico"], "dia_pico": est["dia_pico"], "mes_pico": est["mes_pico"],
            "dias_mas_cargados": est["dias_mas_cargados"][:3],
        },
        "serie": {"anio_pico": pron["anio_pico"], "reportes_anio_pico": pron["anio_pico_n"],
                  "corte_archivo": pron["corte_archivo"], "metodo": pron["metodo"],
                  "contraste": {k: pron["contraste"][k] for k in ("periodo", "reportes", "esperado", "error_pct")}},
        "temas": ([{"id": t["id"], "n": t["n"], "palabras": t["palabras"][:6], "agua_pct": t["agua_pct"]}
                   for t in tem.get("temas", [])[:10]] if tem.get("disponible") else []),
        "recomendaciones": [{"accion": x["accion"], "prioridad": x["prioridad"], "datos": x["datos"]}
                            for x in r["recomendaciones"]],
    }


# ─────────────────────────────────────────────────────────────── verificación
_NUM = re.compile(r"(?<![\w-])(\d{1,3}(?:\.\d{3})+|\d+(?:[.,]\d+)?)(?![\w])")


def _numeros(obj) -> set[float]:
    out: set[float] = set()
    if isinstance(obj, dict):
        for v in obj.values():
            out |= _numeros(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out |= _numeros(v)
    elif isinstance(obj, bool):
        pass
    elif isinstance(obj, (int, float)):
        out.add(float(obj))
    elif isinstance(obj, str):
        for m in _NUM.findall(obj):
            out |= _interpretar(m)
    return out


def _interpretar(t: str) -> set[float]:
    """Lectura en español: '1.721' son miles, '73,8' y '73.8' son decimales."""
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", t):
        return {float(t.replace(".", ""))}
    try:
        return {float(t.replace(",", "."))}
    except ValueError:
        return set()


CONSTANTES = {100.0, 1000.0, 100000.0}      # bases de porcentajes y tasas, no son datos


def verificar(salida: dict, entrada: dict) -> dict:
    base = _numeros(entrada) | CONSTANTES
    texto = json.dumps({k: salida[k] for k in ("titular", "resumen", "hallazgos", "recomendaciones") if k in salida},
                       ensure_ascii=False)
    vistos, malos = 0, []
    for m in _NUM.findall(texto):
        cands = _interpretar(m)
        if any(c <= 12 and c == int(c) for c in cands):       # ordinales y cantidades pequeñas
            continue
        vistos += 1
        ok = any(abs(c - b) <= max(0.05, 0.005 * abs(b)) for c in cands for b in base) or \
            any(1900 <= c <= 2035 for c in cands)
        if not ok:
            malos.append(m)
    return {"cifras": vistos, "verificadas": vistos - len(malos), "no_verificadas": sorted(set(malos))}


# ─────────────────────────────────────────────────────────────── motores
def _ollama(entrada: dict) -> dict:
    import requests
    cuerpo = {
        "model": CFG.ollama_modelo,
        "messages": [
            {"role": "system", "content": SISTEMA},
            {"role": "user", "content": "Resultados de esta semana:\n" + json.dumps(entrada, ensure_ascii=False)},
        ],
        "format": ESQUEMA,
        "stream": False,
        "options": {"temperature": 0.2, "num_ctx": 8192, "seed": CFG.semilla},
    }
    r = requests.post(f"{CFG.ollama_url}/api/chat", json=cuerpo, timeout=CFG.ollama_timeout)
    r.raise_for_status()
    return json.loads(r.json()["message"]["content"])


def _miles(n) -> str:
    return f"{int(round(n)):,}".replace(",", ".")


def _dec(x) -> str:
    return str(x).replace(".", ",")


def _plantilla(e: dict) -> dict:
    h, o, a, s, c = e["hotspots"], e["oleadas"], e["anomalias"], e["estacionalidad"], e["serie"]
    top, inten = h["mayor_volumen"][0], (h["mayor_intensidad_por_100k_habitantes"] or [{}])[0]
    hallazgos = [
        {"titulo": "Dónde se reporta más",
         "explicacion": f"El foco de mayor volumen es {top['lugar']}, con {_miles(top['n'])} reportes. "
                        + (f"Ajustado por población, el foco más intenso es {inten['lugar']}, con {_dec(inten['por_100k'])} "
                           f"reportes por cada 100.000 habitantes." if inten else "")},
        {"titulo": "Cuándo se reporta",
         "explicacion": f"La hora pico es las {s['hora_pico']}:00, el día pico es el {s['dia_pico']} y el mes pico es {s['mes_pico']}. "
                        f"El día más cargado del calendario es el {s['dias_mas_cargados'][0]['etiqueta']}, con "
                        f"{_dec(s['dias_mas_cargados'][0]['veces_promedio'])} veces un día promedio."},
        {"titulo": "Oleadas",
         "explicacion": f"Se detectaron {o['total']} concentraciones breves en espacio y tiempo; {o['en_fechas_festivas']} caen en fechas festivas."},
    ]
    if a["principales"]:
        x = a["principales"][0]
        hallazgos.append({"titulo": "Anomalía principal",
                          "explicacion": f"{x['lugar']} en {x['mes']}: {x['n']} reportes frente a {_dec(x['esperado'])} esperados ({_dec(x['veces'])} veces)."})
    ct = c["contraste"]
    hallazgos.append({"titulo": "Pronóstico frente a la realidad",
                      "explicacion": f"Para {ct['periodo']} el modelo esperaba {_miles(ct['esperado'])} reportes y la cifra publicada fue "
                                     f"{_miles(ct['reportes'])} (error de {_dec(ct['error_pct'])} %)."})
    return {
        "titular": f"{top['lugar']} concentra el mayor volumen; {s['mes_pico']} y las {s['hora_pico']}:00 son el pico",
        "resumen": " ".join(x["explicacion"] for x in hallazgos[:2]),
        "hallazgos": hallazgos,
        "recomendaciones": [{"accion": r["accion"], "por_que": f"Prioridad {r['prioridad']}.", "como": "Ver el detalle en el panel."}
                            for r in e["recomendaciones"]],
        "nombres_temas": [],
    }


def redactar(resultados: dict) -> dict:
    entrada = preparar_entrada(resultados)
    motor, modelo, error = "ollama", CFG.ollama_modelo, None
    try:
        salida = _ollama(entrada)
    except Exception as e:
        log.warning("Ollama no disponible (%s): se usa la plantilla determinística", e)
        salida, motor, modelo, error = _plantilla(entrada), "plantilla", None, str(e)[:200]
    ver = verificar(salida, entrada)
    return {
        "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "motor": motor, "modelo": modelo, "error_motor": error,
        **salida,
        "verificacion": ver,
        "advertencia": ("Texto redactado automáticamente por un modelo de lenguaje local a partir de las estadísticas. "
                        "Las cifras se verifican contra los datos; las no verificadas se listan aparte."),
        "entrada": entrada,
    }
