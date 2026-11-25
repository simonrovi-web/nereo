# NEREO · vigilancia

Ingesta y descarte automáticos del feed de casos recientes. El objetivo es que
el feed siga llenándose sin depender de una sesión de Claude.

Estado: **pieza 1 de 5** construida.

| # | Pieza | Estado |
|---|---|---|
| 1 | Descarte determinista contra calendarios reales | hecho |
| 2 | Ingesta por feeds (AMS, IMO, NUFORC, NOAA, GEIPAN, verificadores, Google News RSS) | pendiente |
| 3 | Criba y redacción con un modelo abierto | pendiente |
| 4 | Detección de oleadas sobre el feed vivo | pendiente |
| 5 | Poda y commit | pendiente |

## Qué hace el descarte

Cruza la fecha de un caso con dos calendarios y anota **solo coincidencias que
existen**, cada una con la URL que la respalda:

- **Lanzamientos orbitales** · [Launch Library 2](https://ll.thespacedevs.com/2.3.0/launches/)
  de The Space Devs. Ventana de ±1 día para un lanzamiento cualquiera y de hasta
  72 h para Starlink, porque el tren de satélites se ve las noches siguientes.
- **Lluvias de meteoros** · el panorama semanal de la
  [American Meteor Society](https://www.amsmeteors.org/articles/), que es la
  misma página que se consultaba a mano. Los panoramas se descubren por el
  archivo mensual del sitio (`/AAAA/MM/`); si eso falla se construye la URL de
  la semana —van de sábado a viernes— y **se comprueba pidiéndola**, y como
  último recurso se raspa el índice de artículos. La API REST de WordPress se
  probó y no existe en ese sitio: devuelve 404.

Devuelve el campo `descarte` en el formato que ya usa el feed, más
`descarteRevisado`, que solo es `true` si el caso tenía fecha de evento y algún
calendario respondió.

## Decisiones que conviene conocer

- **Una sola petición a Launch Library por ejecución.** El nivel gratuito son 15
  por hora y por IP, y la IP del runner de GitHub Actions se comparte con otros
  usuarios. Por eso se pide la última página de lanzamientos pasados y se filtra
  en local, en vez de usar filtros de fecha de la API.
- **No se embarca ninguna tabla de lluvias escrita de memoria.** Lo que se
  publica sale de la página descargada. Si la tabla cambia de forma y no se
  reconoce, el módulo devuelve vacío con una nota, nunca una suposición.
- **Todo lo descargado se cachea** en `data/descarte/`. Si una fuente cae o
  agota la cuota, se usa la caché y se dice que es caché.
- **Sin fecha de evento no hay descarte.** Se devuelve lista vacía y
  `descarteRevisado: false`, que es lo que la regla pide.
- **Pertinencia antes que exhaustividad.** Una coincidencia que no puede
  explicar el caso es ruido, no rigor. Por eso:
  - a una entrada con `rareza` de mar, montaje o natural no se le aplica
    descarte por calendario — un cohete no explica un varamiento de cachalotes,
    un video hecho con IA ni un halo solar;
  - un lanzamiento solo se adjunta si pudo verse desde donde se reportó el caso.
    El techo son 2.500 km, deliberadamente generoso: sirve para descartar lo
    imposible, no para afirmar que algo sí se vio, y la distancia real va escrita
    en el detalle. Starlink queda fuera de ese filtro, porque un tren se ve a
    miles de kilómetros del sitio de lanzamiento.
  - Sobre el feed actual esto baja las coincidencias de 57 a 42 y deja limpios
    ocho casos que recibían cohetes sin sentido.

## Uso

```bash
pip install -r vigilancia/requirements.txt
python -m vigilancia calendarios              # descarga y cachea los calendarios
python -m vigilancia descarte 2026-11-20      # revisa una fecha (hora opcional: 21:27)
python -m vigilancia feed                     # revisa todo data/recientes.json sin escribirlo
python -m pytest -q vigilancia/tests          # 51 pruebas, todas sin red
```

El workflow `vigilancia-descarte.yml` corre lo mismo a diario y refresca la
caché. Por ahora **solo informa**: no escribe en `data/recientes.json`, para
poder comparar su criterio con el del descarte hecho a mano antes de confiarle
el feed.
