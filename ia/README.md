# NEREO · Inteligencia

Módulo de análisis 100 % open source para el archivo de NEREO. Corre en GitHub Actions una vez por semana y publica sus resultados como JSON estático en `data/ia/`, que el visor lee en el panel **Inteligencia**. No hay servidor ni base de datos que mantener.

```
                 ┌─────────────────────── GitHub Actions (semanal) ───────────────────────┐
data/points.json │  CAPA ANALÍTICA                                  CAPA INTERPRETATIVA    │
114.034 reportes ─▶  DBSCAN ponderado ─────▶ hotspots.json          ┌──────────────────┐  │
                 │  HDBSCAN espacio-tiempo ─▶ (oleadas)         ┌──▶│ Ollama · qwen2.5 │  │
ia/fuentes/      │  H3 res 4 ─────────────▶ hexagonos.json      │   │ 3B en CPU        │  │
población,       │  Isolation Forest ─────▶ anomalias.json      │   └────────┬─────────┘  │
relatos ─────────▶  Prophet ──────────────▶ temporal.json        │            ▼            │
(uso interno)    │  sentence-transformers ▶ temas.json         ─┤   verificación de cifras│
                 │  reglas ───────────────▶ recomendaciones.json┘            ▼            │
                 │                                                     resumen.json       │
                 └───────────────────────────────────────┬────────────────────────────────┘
                                                         ▼  commit a main → GitHub Pages
                                                   panel «Inteligencia» del visor
```

## Qué hace cada técnica y por qué

| Pregunta | Técnica | Decisión de diseño |
|---|---|---|
| ¿Dónde se reporta más? | **DBSCAN** haversine con `sample_weight` | Los 114.034 reportes caen en ~28.000 coordenadas únicas, porque se geocodifican a su localidad. Agrupar localidades con su conteo como peso da el mismo resultado que agrupar reportes, unas 20 veces más rápido. |
| ¿Dónde se reporta más **de lo esperable**? | Normalización por población | El volumen bruto replica el mapa de población. Los reportes por cada 100.000 habitantes son los que distinguen un foco real. |
| ¿Hubo oleadas? | **HDBSCAN** sobre (x, y, z, t) | Coordenadas cartesianas en km sobre la esfera más el tiempo escalado: 25 km equivalen a un día. Se recorta cada clúster a sus miembros con probabilidad ≥ 0,4 y se separan las oleadas en fechas festivas. |
| ¿Cómo se ve la densidad en el mapa? | **H3** resolución 4 | Hexágonos de ~1.770 km² con su borde precalculado, listos para dibujar. |
| ¿Qué meses y regiones se salen de lo normal? | **Isolation Forest** por celda H3 de ~12.400 km² y mes | La base es la mediana de los 24 meses previos de la propia celda. Cada anomalía informa los rasgos que más se desvían, para que se pueda explicar. |
| ¿Qué reportes individuales son raros? | **Isolation Forest** por reporte | Filtrado a solidez ≥ 3 y sin explicación convencional: son los candidatos a revisión manual. |
| ¿Cuándo se reporta? ¿Qué viene? | Estacionalidad + **Prophet** | Prophet se ajusta sobre log(1 + y) para que el pronóstico no baje de cero. Como el archivo termina en 2023, el pronóstico se contrasta con una cifra publicada de 2025. |
| ¿De qué hablan los relatos? | **sentence-transformers** + KMeans + c-TF-IDF | Los relatos se usan solo dentro del pipeline. Se publican palabras clave y conteos, nunca texto. |
| ¿Qué hacer con todo esto? | Reglas + **LLM local** | Las recomendaciones se calculan con reglas verificables. El LLM solo las redacta, y cada cifra que escribe se verifica contra los datos. |

## Garantías de la capa interpretativa

1. El modelo **no ve datos crudos**: recibe un JSON compacto (~7.000 caracteres) con resultados ya calculados.
2. **Cada cifra del texto se verifica** contra ese JSON. Las que no aparecen se publican en `verificacion.no_verificadas` y el visor las muestra.
3. Si Ollama no responde, **una plantilla determinística** redacta el resumen y la salida dice `"motor": "plantilla"`.
4. El prompt prohíbe especular sobre origen extraterrestre y obliga a dar primero las explicaciones convencionales.

## Uso local

```bash
cd ia
pip install -r requirements.txt
pip install torch --index-url https://download.pytorch.org/whl/cpu   # opcional, para temas de texto
pip install -r requirements-texto.txt                                  # opcional
ollama pull qwen2.5:3b                                                 # opcional, para el resumen

python -m nereo_ia todo           # descarga fuentes, analiza y redacta
python -m nereo_ia analizar       # solo la capa analítica
python -m nereo_ia redactar       # solo el resumen, sobre resultados ya calculados
python -m pytest -q               # pruebas

uvicorn nereo_ia.api:app --port 8800   # servicio HTTP opcional
```

Los parámetros están en `nereo_ia/config.py` y se pueden cambiar con variables de entorno: `NEREO_HOT_EPS_KM=15`, `NEREO_OLLAMA_MODELO=llama3.2:3b`, etc.

## Estructura

```
ia/
├── nereo_ia/
│   ├── config.py            parámetros (sobrescribibles con NEREO_*)
│   ├── datos.py             decodifica data/points.json
│   ├── fuentes.py           población y relatos (descarga a ia/fuentes/, no versionado)
│   ├── hotspots.py          DBSCAN, HDBSCAN espacio-temporal, H3
│   ├── anomalias.py         Isolation Forest (celda-mes y reporte)
│   ├── series.py            estacionalidad, Prophet y contraste
│   ├── textos.py            sentence-transformers + KMeans + c-TF-IDF
│   ├── recomendaciones.py   reglas accionables
│   ├── llm.py               Ollama, verificación de cifras y plantilla
│   ├── analisis.py          orquestación y escritura de data/ia/
│   ├── api.py               FastAPI opcional
│   └── __main__.py          CLI
├── tests/
├── requirements.txt
└── requirements-texto.txt
```

## Límites

- El archivo está sesgado hacia Estados Unidos, que es donde se reporta a NUFORC. Los hotspots describen dónde se reporta, no dónde ocurren más fenómenos.
- El tramo posterior a 2018 está incompleto. El propio contraste del pronóstico lo muestra: el modelo esperaba 675 reportes para el primer semestre de 2025 y se publicaron 2.174.
- Se pronostican **reportes**, no fenómenos.
- qwen2.5:3b en CPU redacta bien, pero es un modelo pequeño. Por eso cada cifra se verifica y el texto se presenta como borrador automático.
