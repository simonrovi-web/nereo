# Telar · Edición Abierta

Registro de influencia de **figuras públicas** que mapea, con la fuente de cada
afirmación, cinco dimensiones: cargos y trayectoria, empresas y propiedad,
dinero y política, afiliaciones declaradas y vínculos personales documentados.
Grafo de vínculos + mapamundi, con ventana temporal, análisis de caminos y
coincidencias, cronología, ontología a la vista y una sección de teorías en
circulación tratadas como objeto de estudio.

Esta es la **edición abierta y autoalojable**: corre entera en el navegador, sin
depender de ningún servicio de Claude. Es gratis, de código abierto y la puedes
publicar tú.

## Qué la hace distinta de la versión alojada

- **Sin backend.** Los datos viven en tu navegador (`localStorage`), sembrados
  desde `data/registro.json`. Puedes leer, crear y editar fichas, organizaciones,
  vínculos, teorías y notas; todo se guarda localmente en tu equipo.
- **IA de código abierto, local.** El botón «Investigar» usa **WebLLM**: un
  modelo de lenguaje abierto que corre en tu navegador (vía WebGPU), sin enviar
  nada a ningún servidor.

### Lo que la IA abierta hace — y lo que NO hace

Un modelo que corre en tu navegador **no navega la web ni abre registros
oficiales**. Por eso **no puede producir datos con fuente**. Si lo dejáramos
escribir fichas, Telar se llenaría de afirmaciones inventadas sobre personas
reales: exactamente lo que este registro existe para evitar.

Entonces la IA abierta **sólo genera PISTAS de investigación**, marcadas en
grande como **NO VERIFICADAS · SIN FUENTE**. Son preguntas e hipótesis para
guiarte, no hechos. Tú confirmas cada una con una fuente pública real (registro
de comercio, boletín oficial, fallo, declaración, prensa con atribución) y
recién entonces la registras a mano como vínculo, con su enlace. La regla de
Telar no cambia: **ningún dato sin fuente.**

## Cómo publicarla gratis

Es un sitio estático: cualquier host gratuito sirve.

**GitHub Pages**
1. Crea un repositorio y sube todos estos archivos (respeta la carpeta `data/`).
2. Settings → Pages → Branch: `main` / carpeta `/root` → Save.
3. Tu Telar queda en `https://<usuario>.github.io/<repo>/`.

**Netlify / Cloudflare Pages / Vercel**
- Arrastra la carpeta, o conéctala al repositorio. Sin pasos de build.

**En tu computador (para probar)**
```
cd telar-open
python3 -m http.server 8080
# abre http://localhost:8080
```
No abras `index.html` con doble clic (`file://`): el navegador bloquea la lectura
de `data/`. Sírvelo por HTTP.

## Instalable en el teléfono

Incluye manifiesto PWA e íconos. En el navegador del teléfono: **Compartir →
Agregar a inicio** (iPhone) o **menú → Instalar aplicación** (Android). Se abre
como app propia.

## Requisitos de la IA abierta

- Navegador con **WebGPU**: Chrome o Edge de escritorio recientes, o Chrome en
  Android nuevo. (Safari aún es parcial.)
- La **primera vez** descarga los pesos del modelo (cientos de MB) y los deja en
  caché. Sin WebGPU, el asistente te ofrece una plantilla de líneas de
  investigación para llenar a mano.
- El modelo por defecto es `Llama-3.2-1B-Instruct` (pequeño). Para cambiarlo,
  edita la constante `MODELO` en `telar-open.js`. La librería se carga desde
  `esm.run` (jsDelivr); si prefieres no depender de un CDN, puedes alojar WebLLM
  tú mismo.

## Datos

- **Partir de cero o editar:** todo cambio se guarda en `localStorage` de este
  navegador, en este equipo. No se comparte ni sube a ningún lado.
- **Exportar:** el botón «Exportar dosier» descarga un Markdown con la ficha (o
  todo el registro) y la fuente de cada línea.
- **Reiniciar a la instantánea original:** abre la consola y ejecuta
  `telarReset()`, o borra los datos del sitio en el navegador.
- `data/registro.json` es una instantánea del registro al momento de generar
  esta copia. Reemplázala por la tuya cuando quieras un punto de partida distinto.

## Archivos

```
index.html              La app
telar-open.js           Adaptador local (base de datos en el navegador) + IA abierta
data/registro.json      Instantánea del registro (editable)
data/world.json         Geometría del mapamundi
manifest.webmanifest    Manifiesto PWA
icon-*.png              Íconos de la app
LICENSE                 MIT
```

## Doctrina (no se rompe)

- Solo figuras públicas, con rastro en registros públicos.
- Ningún dato sin fuente. Lo que no la tiene se dibuja punteado y se marca.
- Relaciones, no etiquetas. Una afiliación es un vínculo fechado con una fuente.
- Lo declarado o registrado, no lo inferido.
- Las teorías en circulación van aparte, como objeto de estudio con fuente,
  nunca colgadas de la ficha de una persona.

## Licencia

MIT. Úsala, modifícala y redistribúyela libremente. Si prefieres obligar a que
las versiones derivadas sigan siendo abiertas, cambia la licencia a AGPL-3.0.
