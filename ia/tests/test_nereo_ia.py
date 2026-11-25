"""Pruebas del módulo de inteligencia.  Ejecutar desde ia/:  python -m pytest -q"""
import numpy as np
import pandas as pd
import pytest

from nereo_ia import hotspots, llm
from nereo_ia.config import CFG


def _df_sintetico(semilla=0):
    """Un foco denso en Valparaíso, ruido disperso en Chile y una oleada de 3 días en Concepción."""
    rng = np.random.default_rng(semilla)
    filas = []
    for _ in range(400):
        filas.append((-33.05 + rng.normal(0, .02), -71.62 + rng.normal(0, .02), "2020-03-01", "Valparaíso, VS"))
    for _ in range(200):
        filas.append((rng.uniform(-45, -20), rng.uniform(-73, -69), f"20{rng.integers(10, 22)}-0{rng.integers(1, 9)}-15", "Ruido, CL"))
    for i in range(40):
        filas.append((-36.82 + rng.normal(0, .05), -73.05 + rng.normal(0, .05), f"2019-07-0{1 + i % 3}", f"Concepción {i % 6}, BI"))
    df = pd.DataFrame(filas, columns=["lat", "lon", "f", "lugar"])
    df["fecha"] = pd.to_datetime(df["f"]) + pd.to_timedelta(rng.integers(0, 24, len(df)), unit="h")
    df["year"] = df["fecha"].dt.year
    df["hour"] = df["fecha"].dt.hour
    df["hora_valida"] = True
    df["nocturno"] = (df["hour"] >= 20) | (df["hour"] < 5)
    df["forma"] = "light"
    df["maritimo"] = False
    df["explicable"] = False
    df["sol"] = 2
    return df.round({"lat": 3, "lon": 3})


def test_hotspot_detecta_foco_denso(monkeypatch):
    monkeypatch.setattr(CFG.__class__, "hot_min_reportes", 50, raising=False)
    object.__setattr__(CFG, "hot_min_reportes", 50)
    r = hotspots.hotspots(_df_sintetico())
    assert r["total_clusteres"] >= 1
    assert r["por_volumen"][0]["lugar"].startswith("Valparaíso")


def test_oleada_espacio_temporal():
    object.__setattr__(CFG, "ola_min_cluster", 8)
    object.__setattr__(CFG, "ola_desde", 2000)
    r = hotspots.oleadas(_df_sintetico())
    assert any(o["lugar"].startswith("Concepción") and o["dias"] <= 3 for o in r["sin_fecha_festiva"])


@pytest.mark.parametrize("texto,esperado", [("1.721", {1721.0}), ("73,8", {73.8}), ("6.1", {6.1})])
def test_lectura_de_numeros(texto, esperado):
    assert llm._interpretar(texto) == esperado


def test_verificacion_detecta_cifra_inventada():
    entrada = {"a": 1721, "b": 73.8}
    salida = {"titular": "x", "resumen": "Hubo 1.721 reportes, 73,8 por 100.000 y 9.999 inventados.",
              "hallazgos": [], "recomendaciones": []}
    v = llm.verificar(salida, entrada)
    assert v["no_verificadas"] == ["9.999"]
    assert v["verificadas"] == 3


def test_limpieza_de_lugares():
    assert hotspots.limpio("Spokane (About 30 Miles Sw Of,I-90), WA") == "Spokane, WA"


def test_verificar_admite_el_dia_de_una_fecha_iso():
    """«2023-05-18» reescrito como «18 de mayo de 2023» no es una cifra inventada."""
    entrada = {"archivo": {"hasta": "2023-05-18"}, "anomalias": {"mes": "2015-11"}}
    salida = {"titular": "t", "resumen": "Datos hasta el 18 de mayo de 2023.",
              "hallazgos": [], "recomendaciones": []}
    v = llm.verificar(salida, entrada)
    assert v["no_verificadas"] == []


def test_verificar_sigue_marcando_una_cifra_inventada():
    entrada = {"archivo": {"hasta": "2023-05-18"}}
    salida = {"titular": "t", "resumen": "Se registraron 7431 reportes.",
              "hallazgos": [], "recomendaciones": []}
    v = llm.verificar(salida, entrada)
    assert v["no_verificadas"] == ["7431"]
