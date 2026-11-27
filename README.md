# NEREO

**Registro de fenómenos anómalos aéreos y submarinos.** Un visor OSINT a pantalla completa para explorar avistamientos de objetos no identificados en el cielo y en el mar, con contexto suficiente para descartar antes de afirmar.

🔭 **Visor en vivo:** https://simonrovi-web.github.io/nereo/

---

## Qué muestra

- **114.034 reportes geolocalizados, de 1906 a 2023**, del National UFO Reporting Center (NUFORC), en un mapa Mercator propio dibujado en canvas.
- **Interfaz mar–aire.** Cada reporte se clasifica según su relación con el agua por dos vías independientes: geométrica (distancia a la costa y coordenada sobre mar o lago) y textual (relato que describe al objeto entrando o saliendo del agua, sobre ella o visto desde una embarcación). 20.837 reportes tienen componente marítima; 62 describen un objeto sumergiéndose o emergiendo.
- **Expedientes oficiales.** Once casos con material liberado o reconocido por organismos del Estado, entre ellos FLIR1, GIMBAL, GOFAST, USS Omaha, Aguadilla, Monte Etna, la Armada de Chile (2014), Campeche (2004), la Noche Oficial de los OVNIs en Brasil (1986) y el caso Bariloche (1995). Los casos disputados se presentan con ambas versiones.
- **Explicaciones convencionales.** Marca los reportes que coinciden con lluvias de meteoros, fechas de fuegos artificiales y lanzamientos orbitales, y permite ocultarlos para quedarse con el residuo.
- **Índice de solidez (0–5)** por reporte, según la información que aporta: registro visual declarado, radar, varios testigos y duración.
- **Contexto marítimo.** Batimetría, rutas navieras principales y zonas de entrenamiento naval.
- **Últimos videos.** Feed de registros recientes: material oficial, prensa y redes, cada uno con fuente y estado de verificación.
- **Cámaras de cielo completo** de observatorios y redes de bólidos, con seis sitios en Chile.
- Línea de tiempo con reproducción por oleadas, mapa de calor, cuadrícula de densidad, terminador día/noche en vivo, filtros por forma, hora, duración y distancia a la costa, y buscador de localidades.

## Lo que hay que tener presente

- La coordenada de cada reporte es la de la **localidad desde donde se informó**, no la del objeto.
- El archivo está fuertemente **sesgado hacia Estados Unidos**.
- Son **testimonios sin verificar**. NEREO cartografía reportes, no fenómenos confirmados.
- Una coincidencia con una explicación convencional **señala una causa posible, no la demuestra**. Los lanzamientos cubren hasta 2018.
- El índice de solidez mide **cuánta información trae el reporte**, no si el fenómeno es real.
- NEREO **no descarga ni rehospeda videos de terceros**: enlaza siempre al original.
- Las zonas de entrenamiento naval están dibujadas de forma aproximada.

## Uso local

Es un sitio estático, sin dependencias ni compilación:

```bash
python3 -m http.server 8000
# abrir http://localhost:8000
```

## Estructura

```
index.html          interfaz
css/app.css         sistema visual
js/app.js           mapa, capas, paneles y lógica
data/points.bin.gz  reportes en columnas binarias (gzip)
data/points-meta.json índice de columnas, lugares y formas
data/stats.json     estadísticas agregadas
data/world.json     costas, lagos y fronteras
data/mar.json       batimetría, rutas navieras, zonas navales y puertos espaciales
data/videos.json    expedientes oficiales
data/cams.json      cámaras de cielo completo
data/recientes.json instantánea del feed de últimos videos
pipeline/           scripts que generan los archivos de data/
```

El archivo de reportes no incluye el texto de los relatos: solo metadatos y etiquetas derivadas. Los relatos completos quedan en el archivo original de NUFORC.

## Fuentes

- **NUFORC** — National UFO Reporting Center, https://nuforc.org
- **Tramo histórico (hasta 2014):** proyecto abierto [planetsig/ufo-reports](https://github.com/planetsig/ufo-reports).
- **Extensión 2014–2023:** extracción publicada por [TidyTuesday](https://github.com/rfordatascience/tidytuesday) a partir del trabajo de Timothy Renner.
- **Lanzamientos orbitales:** conjunto de TidyTuesday (2019) basado en el registro de lanzamientos de Jonathan McDowell.
- **Cartografía y batimetría:** [Natural Earth](https://www.naturalearthdata.com), dominio público.
- **Rutas navieras:** [newzealandpaul/Shipping-Lanes](https://github.com/newzealandpaul/Shipping-Lanes).
- Expedientes oficiales y feed: cada ficha enlaza a sus fuentes.

---

Un proyecto de **NOVA AUDIOVISUAL**.
