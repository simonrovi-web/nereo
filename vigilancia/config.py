"""Parámetros del módulo de vigilancia de NEREO.

Todo valor ajustable vive aquí. Se puede sobreescribir con variables de
entorno con el prefijo NEREO_ (por ejemplo NEREO_LL2_BASE=...).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]          # raíz del repositorio


def _env(nombre: str, defecto):
    v = os.environ.get("NEREO_" + nombre)
    if v is None:
        return defecto
    return type(defecto)(v) if not isinstance(defecto, bool) else v.lower() in ("1", "true", "si", "sí")


@dataclass(frozen=True)
class Config:
    # caché en disco de lo que se consulta fuera (se versiona en el repo)
    cache: Path = RAIZ / "data" / "descarte"

    # Launch Library 2 · 15 peticiones por hora y por IP sin autenticar, y la IP
    # del runner se comparte con otros usuarios de GitHub Actions. Por eso se
    # hace UNA sola petición por ejecución y se filtra en local.
    ll2_base: str = _env("LL2_BASE", "https://ll.thespacedevs.com/2.3.0")
    ll2_limite: int = _env("LL2_LIMITE", 100)        # máximo que acepta la API
    ll2_timeout: int = _env("LL2_TIMEOUT", 40)

    # American Meteor Society · panorama semanal de actividad
    ams_wp: str = _env("AMS_WP", "https://www.amsmeteors.org/wp-json/wp/v2/posts")
    ams_indice: str = _env("AMS_INDICE", "https://www.amsmeteors.org/articles/")
    ams_timeout: int = _env("AMS_TIMEOUT", 40)

    # ventanas de coincidencia
    dias_lanzamiento: float = _env("DIAS_LANZAMIENTO", 1.0)   # ±1 día para un lanzamiento cualquiera
    horas_starlink: float = _env("HORAS_STARLINK", 72.0)      # los trenes se ven los días siguientes

    # Hasta dónde puede verse el ascenso de un cohete. Es un techo deliberadamente
    # generoso, no una cifra de manual: sirve para descartar lo imposible (un
    # Long March desde Jiuquan no explica una luz en Brasil), no para afirmar que
    # algo sí se vio. Cuando hay coordenadas, la distancia real se escribe en el
    # detalle para que el lector juzgue. No se aplica a Starlink: un tren de
    # satélites se ve a miles de kilómetros del sitio de lanzamiento.
    visibilidad_km: float = _env("VISIBILIDAD_KM", 2500.0)

    # Categorías de rareza a las que el descarte por calendario no aplica: un
    # cohete no explica un varamiento de cachalotes ni un video hecho con IA.
    rarezas_sin_descarte: tuple = ("mar", "montaje", "natural")

    agente: str = _env("AGENTE", "NEREO-vigilancia/1.0 (+https://github.com/simonrovi-web/nereo)")


CFG = Config()
