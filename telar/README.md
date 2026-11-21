# Telar

Registro de influencia de figuras públicas. Mapea, con la fuente de cada
afirmación, cinco dimensiones: cargos y trayectoria, empresas y propiedad,
dinero y política, afiliaciones declaradas y vínculos personales
documentados.

Hermano de [NEREO](../), con el que comparte el sistema visual y el
mapamundi (`data/world.json`).

## Qué es

Una estación de análisis de vínculos para trabajo periodístico. Tres vistas
enlazadas sobre los mismos objetos:

- **Grafo** de relaciones, con simulación de fuerzas, foco por vecindad y
  camino más corto entre dos entidades.
- **Mapamundi** equirectangular, con vuelo de cámara a la ubicación de cada
  entidad y los vínculos trazados como arcos.
- **Ventana temporal** con histograma y reproducción, que filtra por año de
  inicio y término de cada vínculo.

## Ontología

El modelo está declarado y es navegable dentro de la propia herramienta
(panel ONTOLOGÍA). Sigue la forma del modelo de Palantir: tipos de objeto con
propiedades, tipos de vínculo declarados entre dos tipos de objeto, y tipos de
acción como único camino por el que se escribe.

**Tipos de objeto**

| Tipo | Forma | Origen |
|---|---|---|
| Persona | círculo | colección `personas` |
| Organización | rombo | colección `organizaciones` |
| Documento | cuadrado | derivado de `vinculos.fuentes` |

El documento como objeto permite la pregunta inversa: qué parte del registro
descansa sobre una sola fuente.

**Tipos de vínculo**: `cargo`, `empresa`, `dinero`, `afiliacion`, `personal`.
Todos van de una persona a una contraparte, llevan procedencia
(`registro` · `judicial` · `declarado` · `prensa`) y exigen al menos un
enlace.

## Reglas de admisión

Estas reglas no son una advertencia legal: son el criterio de entrada de cada
dato, y lo que separa un mapa de influencia de un expediente.

1. **Solo figuras públicas.** Rol público y rastro en registros públicos. Un
   particular sin rol público no tiene ficha.
2. **Ningún dato sin fuente.** Los vínculos sin enlace se dibujan punteados,
   se marcan en rojo y se cuentan en la cabecera.
3. **Relaciones, no etiquetas.** Una afiliación se guarda como vínculo fechado
   con una organización, nunca como categoría pegada a la persona.
4. **Lo declarado, no lo inferido.** Nada de deducciones ni creencias
   atribuidas.
5. **Vínculos personales con prueba.** «Se le ve con» no es una fuente.
6. **Procedencia visible.** Cada fila declara de dónde sale.

## Cómo corre

La herramienta vive como artefacto de Claude, donde el registro es una base
compartida con control de acceso y escritura desde la propia interfaz.

Servida como sitio estático (por ejemplo aquí, en GitHub Pages), arranca en
**modo lectura** y busca una instantánea del registro en
`data/registro.json`:

```json
{
  "personas":       { "<slug>": { "nombre": "…", "rolPublico": "…", … } },
  "organizaciones": { "<slug>": { "nombre": "…", "tipo": "…", … } },
  "vinculos":       { "<id>":   { "personaId": "…", "contraparte": "org:…", … } }
}
```

Sin ese archivo la página carga vacía y lo dice. **Este repositorio no
incluye el registro**: publicar una base de datos sobre personas con nombre y
apellido es una decisión distinta de publicar la herramienta, y se toma
aparte.

## El motor libre: GitHub Actions + modelo de pesos abiertos

Además del artefacto, Telar corre con una cadena enteramente gratuita y de
código abierto, que es la que hace funcionar al sitio estático:

1. Desde el visor, escribir un nombre y elegir **ENCARGAR** abre un issue con
   el formulario `Telar: <nombre>`. No hace falta ninguna clave en el
   navegador.
2. El flujo `.github/workflows/telar.yml` lo recoge, levanta **SearXNG**
   (metabuscador de código abierto) en la propia máquina del runner, descarga
   las páginas candidatas y extrae su texto.
3. `telar/pipeline/investigar.py` le pasa **una página por vez** a un modelo de
   pesos abiertos (`openai/gpt-oss-120b` por omisión, servido por Groq) y le
   pide extraer afirmaciones **solo de ese texto**.
4. Escribe `data/registro.json` y comenta el issue.

**Por qué el modelo no puede inventar fuentes.** Nunca se le pregunta de dónde
sale un dato: el programa procesa una página a la vez y estampa él mismo la URL
de la página que le dio el texto. Un vínculo cuyo tipo, contraparte o
procedencia no pase la validación se descarta antes de escribir. El resultado
tiene menos vínculos que con un modelo grande, y ninguno sin respaldo.

Qué hace falta para encenderlo:

- El secreto `GROQ_API_KEY` en el repositorio (cuenta gratuita). La variable
  `TELAR_MODELO` permite cambiar a `openai/gpt-oss-20b` o `qwen/qwen3.8-27b`.
- Los minutos de Actions son gratuitos en repositorios públicos.

El flujo solo atiende issues abiertos por el dueño o colaboradores del
repositorio: el repositorio es público y, sin ese filtro, cualquiera podría
encargar la ficha de una persona y publicarla aquí.

## Archivos

- `index.html` — la aplicación completa, sin dependencias externas.
- `data/world.json` — contornos de costa, fronteras y lagos, compartido con NEREO.
- `pipeline/investigar.py` — la investigación con el modelo abierto.
- `../.github/workflows/telar.yml` — el flujo que la ejecuta.
