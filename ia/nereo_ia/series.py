"""Estacionalidad y pronóstico.

· Estacionalidad descriptiva: hora del día, día de la semana y mes del año,
  expresadas como índice (100 = promedio), más el día del año más cargado.

· Pronóstico con Prophet sobre la serie mensual. Si Prophet no está
  instalado, se usa un respaldo estacional ingenuo y se dice en la salida.

· Contraste: el archivo termina en mayo de 2023. Para no presentar un
  pronóstico imposible de evaluar, se compara contra una cifra publicada de
  reportes reales a NUFORC posterior al corte del archivo.
"""
from __future__ import annotations

import logging
import warnings

import numpy as np
import pandas as pd

from .config import CFG

log = logging.getLogger(__name__)

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre"]

# Cifra pública posterior al corte del archivo (NewsNation, julio 2025, con datos de NUFORC).
CONTRASTE = {"periodo": "2025-01 a 2025-06", "desde": "2025-01", "hasta": "2025-06", "reportes": 2174,
             "fuente": "NewsNation, «Over 2K UFO sightings reported in first half of 2025», con datos de NUFORC",
             "url": "https://digital-release.newsnationnow.com/?p=3449587"}


def _indice(conteo: pd.Series, etiquetas: list[str]) -> list[dict]:
    media = conteo.mean()
    return [{"k": etiquetas[i], "n": int(v), "indice": round(100 * v / media, 1)} for i, v in enumerate(conteo)]


def estacionalidad(df: pd.DataFrame) -> dict:
    d = df[df["year"] >= CFG.serie_desde]
    horas = d.loc[d["hora_valida"], "hour"].value_counts().reindex(range(24), fill_value=0)
    dias = d["fecha"].dt.dayofweek.value_counts().reindex(range(7), fill_value=0)
    meses = d["month"].value_counts().reindex(range(1, 13), fill_value=0)
    dia_anio = d["fecha"].dt.strftime("%m-%d").value_counts()
    media_dia = len(d) / 365.25
    return {
        "desde": CFG.serie_desde,
        "hora": _indice(horas, [f"{h:02d}" for h in range(24)]),
        "dia_semana": _indice(dias, DIAS),
        "mes": _indice(meses, MESES),
        "dias_mas_cargados": [{"dia": k, "etiqueta": f"{int(k[3:])} de {MESES[int(k[:2]) - 1]}", "n": int(v),
                               "veces_promedio": round(v / media_dia, 1)}
                              for k, v in dia_anio.head(5).items()],
        "hora_pico": int(horas.idxmax()), "dia_pico": DIAS[int(dias.idxmax())], "mes_pico": MESES[int(meses.idxmax()) - 1],
    }


def pronostico(df: pd.DataFrame) -> dict:
    d = df[df["year"] >= CFG.serie_desde]
    serie = d.set_index("fecha").resample("MS").size()
    serie = serie.iloc[:-1]                         # el último mes del archivo está incompleto
    hist = pd.DataFrame({"ds": serie.index, "y": serie.values})
    h = CFG.pronostico_meses + int((pd.Timestamp("2025-06-01") - serie.index[-1]).days // 30)

    metodo, fut = None, None
    try:
        from prophet import Prophet
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
            # se modela log(1 + y): el pronóstico no puede ser negativo y la estacionalidad queda multiplicativa
            m = Prophet(yearly_seasonality=True, weekly_seasonality=False, daily_seasonality=False,
                        changepoint_prior_scale=0.05, changepoint_range=0.9, interval_width=0.8)
            m.fit(hist.assign(y=np.log1p(hist["y"])))
            f = m.predict(m.make_future_dataframe(periods=h, freq="MS"))
            for c in ("yhat", "yhat_lower", "yhat_upper"):
                f[c] = np.expm1(f[c]).clip(lower=0)
        fut = f[["ds", "yhat", "yhat_lower", "yhat_upper"]]
        metodo = "Prophet sobre log(1 + reportes mensuales) · estacionalidad anual · intervalo 80 %"
    except Exception as e:                            # prophet ausente o sin backend
        log.warning("Prophet no disponible (%s): respaldo estacional ingenuo", e)
        ultimos = hist.tail(36)
        perfil = ultimos.groupby(ultimos["ds"].dt.month)["y"].mean()
        fechas = pd.date_range(hist["ds"].iloc[-1] + pd.offsets.MonthBegin(), periods=h, freq="MS")
        yhat = np.array([perfil[m] for m in fechas.month])
        fut = pd.concat([hist.rename(columns={"y": "yhat"}).assign(yhat_lower=lambda x: x.yhat, yhat_upper=lambda x: x.yhat),
                         pd.DataFrame({"ds": fechas, "yhat": yhat, "yhat_lower": yhat * .7, "yhat_upper": yhat * 1.3})])
        metodo = "Respaldo estacional ingenuo (promedio por mes de los últimos 3 años) · Prophet no disponible"

    fut = fut.assign(ds=pd.to_datetime(fut["ds"]))
    corte = hist["ds"].iloc[-1]
    futuro = fut[fut["ds"] > corte]
    c = futuro[(futuro["ds"] >= CONTRASTE["desde"]) & (futuro["ds"] <= CONTRASTE["hasta"] + "-28")]
    esperado = float(c["yhat"].sum())
    contraste = dict(CONTRASTE, esperado=round(esperado), rango=[round(float(c["yhat_lower"].sum())), round(float(c["yhat_upper"].sum()))],
                     error_pct=round((CONTRASTE["reportes"] - esperado) / CONTRASTE["reportes"] * 100, 1) if esperado else None)

    anual = hist.groupby(hist["ds"].dt.year)["y"].sum()
    return {
        "metodo": metodo,
        "serie_desde": str(hist["ds"].iloc[0].date()), "corte_archivo": str(corte.date()),
        "historico": [[str(a.date())[:7], int(b)] for a, b in zip(hist["ds"], hist["y"])],
        "pronostico": [[str(r.ds.date())[:7], round(max(r.yhat, 0), 1), round(max(r.yhat_lower, 0), 1), round(max(r.yhat_upper, 0), 1)]
                       for r in futuro.itertuples()],
        "anual": [[int(a), int(b)] for a, b in anual.items()],
        "anio_pico": int(anual.idxmax()), "anio_pico_n": int(anual.max()),
        "contraste": contraste,
        "advertencia": ("Se pronostican reportes, no fenómenos. El volumen depende de la difusión de NUFORC, "
                        "de la cobertura mediática y de cambios en la forma de reportar."),
    }
