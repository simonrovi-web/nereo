#!/usr/bin/env python3
"""Telar · investigación de un nombre con un modelo de pesos abiertos.

Diseño ANTIALUCINACIÓN, que es lo único que hace utilizable un modelo
pequeño en una herramienta periodística: el modelo nunca responde de
memoria y nunca elige una URL.

  1. Se busca el nombre en SearXNG (metabuscador de código abierto que el
     flujo levanta en su propia máquina) y, de apoyo, en la API de
     Wikipedia, que es abierta y no pide clave.
  2. Se descarga cada página candidata y se extrae su texto.
  3. Se le pasa al modelo UNA página por vez, y se le pide que extraiga
     afirmaciones SOLO de ese texto. No se le pregunta de dónde salen:
     la URL la estampa este programa, porque sabe qué página le dio.
     Así el modelo no puede inventar una fuente ni aunque quiera.
  4. Todo vínculo que no pase la validación estructural se descarta antes
     de escribir. Menos vínculos, pero ninguno sin respaldo.

El resultado se funde con telar/data/registro.json, que es el archivo que
lee el visor estático.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import requests
import trafilatura

# ─────────────────────────── parámetros ───────────────────────────

RAIZ = Path(__file__).resolve().parents[1]
REGISTRO = RAIZ / "data" / "registro.json"

SEARXNG = os.environ.get("TELAR_SEARXNG", "http://127.0.0.1:8080")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_KEY = os.environ.get("GROQ_API_KEY", "").strip()
MODELO = os.environ.get("TELAR_MODELO", "openai/gpt-oss-120b")

# El plan gratuito de Groq es estrecho en tokens por minuto, así que se
# recorta cada página y se espera entre llamadas en vez de chocar con el 429.
MAX_CARACTERES_PAGINA = int(os.environ.get("TELAR_MAX_CHARS", "7000"))
MAX_PAGINAS = int(os.environ.get("TELAR_MAX_PAGINAS", "12"))
ESPERA_ENTRE_LLAMADAS = float(os.environ.get("TELAR_ESPERA", "21"))
TIEMPO_LIMITE_HTTP = 25

TIPOS = {"cargo", "empresa", "dinero", "afiliacion", "personal"}
PROCEDENCIAS = {"registro", "judicial", "declaracion", "prensa"}
TIPOS_ORG = {
    "empresa", "fundacion", "partido", "medio", "gremio",
    "organizacion religiosa", "club", "universidad", "organismo publico", "otra",
}

UA = "TelarBot/1.0 (+https://github.com/simonrovi-web/nereo)"


def ahora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slug(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:60]


def log(*a):
    print(*a, flush=True)


# ─────────────────────────── búsqueda ───────────────────────────

def buscar_searxng(consulta: str, n: int = 8) -> list[dict]:
    """Consulta la instancia de SearXNG que el flujo levantó al lado."""
    try:
        r = requests.get(
            f"{SEARXNG}/search",
            params={"q": consulta, "format": "json", "language": "es"},
            headers={"User-Agent": UA},
            timeout=TIEMPO_LIMITE_HTTP,
        )
        r.raise_for_status()
        datos = r.json()
    except Exception as e:  # el buscador es un apoyo, no una dependencia dura
        log(f"  · SearXNG falló para «{consulta}»: {e}")
        return []
    salida = []
    for it in (datos.get("results") or [])[: n * 2]:
        url = (it.get("url") or "").strip()
        if url.startswith("http"):
            salida.append({"url": url, "titulo": (it.get("title") or "").strip()})
    return salida[:n]


def buscar_wikipedia(nombre: str) -> list[dict]:
    """Respaldo abierto y sin clave: la API de Wikipedia en español."""
    try:
        r = requests.get(
            "https://es.wikipedia.org/w/api.php",
            params={
                "action": "query", "list": "search", "srsearch": nombre,
                "srlimit": 3, "format": "json",
            },
            headers={"User-Agent": UA},
            timeout=TIEMPO_LIMITE_HTTP,
        )
        r.raise_for_status()
        hits = r.json().get("query", {}).get("search", [])
    except Exception as e:
        log(f"  · Wikipedia falló: {e}")
        return []
    salida = []
    for h in hits:
        titulo = h.get("title", "")
        salida.append({
            "url": "https://es.wikipedia.org/wiki/" + titulo.replace(" ", "_"),
            "titulo": titulo + " · Wikipedia",
        })
    return salida


def candidatos(nombre: str, pais: str, rol: str, nota: str) -> list[dict]:
    consultas = [
        f"{nombre} {pais}".strip(),
        f"{nombre} {rol}".strip() if rol else f"{nombre} biografía",
        f"{nombre} directorio sociedad empresa",
        f"{nombre} aportes campaña declaración de intereses",
    ]
    if nota:
        consultas.append(f"{nombre} {nota}"[:180])

    vistos, salida = set(), []
    for c in consultas:
        for it in buscar_searxng(c):
            if it["url"] not in vistos:
                vistos.add(it["url"])
                salida.append(it)
    for it in buscar_wikipedia(nombre):
        if it["url"] not in vistos:
            vistos.add(it["url"])
            salida.append(it)

    # Una sola página por dominio: evita que un medio cope la ficha entera.
    # Las Wikipedias cuentan como un solo dominio: es y gl y en son la misma
    # fuente traducida, y colarlas tres veces finge una corroboración que no hay.
    por_dominio, final = {}, []
    for it in salida:
        try:
            d = re.sub(r"^www\.", "", it["url"].split("/")[2].lower())
        except Exception:
            continue
        if d.endswith("wikipedia.org"):
            d = "wikipedia.org"
        if por_dominio.get(d):
            continue
        por_dominio[d] = 1
        it["dominio"] = d
        final.append(it)
    return final[:MAX_PAGINAS]


def descargar(url: str) -> str | None:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=TIEMPO_LIMITE_HTTP)
        if r.status_code != 200 or len(r.content) > 5_000_000:
            return None
        texto = trafilatura.extract(r.text, include_comments=False, favor_precision=True)
        if not texto or len(texto) < 400:
            return None
        return texto[:MAX_CARACTERES_PAGINA]
    except Exception:
        return None


# ─────────────────────────── modelo abierto ───────────────────────────

INSTRUCCIONES = """Eres un extractor de datos para un registro periodístico de influencia de figuras públicas.

Te doy el TEXTO de UNA sola página web y el nombre de una persona. Tu única tarea es extraer, de ESE TEXTO Y DE NINGUNA OTRA PARTE, afirmaciones verificables sobre esa persona.

REGLAS ABSOLUTAS:
- No uses nada que sepas de antes. Si el texto no lo dice, no existe.
- No deduzcas ni completes. Si el texto no da el año, deja el campo vacío.
- Si el texto no habla de esa persona, devuelve listas vacías.
- No inventes URLs ni nombres de fuentes: no te corresponde, el sistema las pone.

Devuelve SOLO un objeto JSON con esta forma exacta:
{
  "es_figura_publica": true|false,
  "rol_publico": "cargo o papel público que el texto le atribuye, o null",
  "resumen": "2 frases, solo con lo que dice el texto, o null",
  "vinculos": [
    {
      "tipo": "cargo|empresa|dinero|afiliacion|personal",
      "contraparte": "nombre de la organización, tal como aparece en el texto",
      "etiqueta": "el cargo o papel concreto",
      "desde": "YYYY o vacío",
      "hasta": "YYYY o vacío",
      "registro": "registro|judicial|declaracion|prensa",
      "detalle": "una frase con lo que el texto afirma"
    }
  ]
}

Cómo elegir "tipo": cargo = puestos públicos o privados; empresa = propiedad, acciones, directorios; dinero = donaciones, lobby, contratos públicos; afiliacion = fundaciones, partidos, gremios, clubes, iglesias; personal = parentesco o sociedades conjuntas que el texto documente.

Cómo elegir "registro": registro = registros oficiales, memorias, reguladores; judicial = fallos o expedientes; declaracion = la propia persona u organización lo declara (su web, su biografía oficial); prensa = un medio lo informa."""


def preguntar(texto_pagina: str, titulo: str, nombre: str) -> dict | None:
    if not GROQ_KEY:
        log("  · Falta GROQ_API_KEY: no se puede extraer.")
        return None
    cuerpo = {
        "model": MODELO,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": INSTRUCCIONES},
            {"role": "user", "content":
                f"PERSONA: {nombre}\nTÍTULO DE LA PÁGINA: {titulo}\n\nTEXTO:\n{texto_pagina}"},
        ],
    }
    for intento in range(3):
        try:
            r = requests.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
                json=cuerpo, timeout=120,
            )
            if r.status_code == 429:
                espera = float(r.headers.get("retry-after", 30)) + 2
                log(f"  · límite alcanzado, esperando {espera:.0f}s")
                time.sleep(espera)
                continue
            r.raise_for_status()
            contenido = r.json()["choices"][0]["message"]["content"]
            return json.loads(contenido)
        except Exception as e:
            log(f"  · intento {intento + 1} falló: {e}")
            time.sleep(5)
    return None


# ─────────────────────────── validación ───────────────────────────

def procedencia(valor, url: str) -> str:
    """La procedencia la decide el DOMINIO, no el modelo.

    De dónde viene un dato es un hecho sobre la fuente, no una opinión
    sobre el contenido: el programa sabe qué servidor le entregó el texto,
    así que no hay por qué dejárselo adivinar a un modelo pequeño, que en
    la práctica contesta «prensa» para todo. Solo si el dominio no dice
    nada se usa lo que propuso el modelo.
    """
    host = ""
    try:
        host = re.sub(r"^www\.", "", url.split("/")[2].lower())
    except Exception:
        pass

    if host.endswith(".gob.cl") or host.endswith(".gov") or ".gov." in host:
        return "registro"
    if any(host.endswith(d) or host == d for d in (
            "bcn.cl", "cmfchile.cl", "servel.cl", "diariooficial.interior.gob.cl",
            "sii.cl", "mercadopublico.cl", "leychile.cl", "infoprobidad.cl")):
        return "registro"
    if "poderjudicial" in host or "pjud.cl" in host or host.endswith(".jus.cl"):
        return "judicial"

    # Llegados aquí el dominio no es ni oficial ni judicial, y eso lo sabe el
    # programa con certeza. «registro» y «judicial» son afirmaciones sobre la
    # naturaleza de la fuente, no sobre su contenido: se ganan estando en las
    # listas de arriba, y un modelo no puede ascender a un sitio cualquiera.
    # Lo único que se le acepta es «declaracion», que depende del texto.
    v = unicodedata.normalize("NFD", str(valor or "").lower())
    v = "".join(c for c in v if unicodedata.category(c) != "Mn").strip()
    return "declaracion" if v.startswith("declaracion") else "prensa"


def es_terciaria(url: str) -> bool:
    """Wikipedia y similares: útiles para orientarse, débiles como prueba."""
    return "wikipedia.org" in url or "wikidata.org" in url


def anio(valor) -> str:
    """Un año de cuatro cifras, o nada. Nunca una fecha a medio inventar."""
    m = re.search(r"\b(1[89]\d{2}|20\d{2})\b", str(valor or ""))
    return m.group(0) if m else ""


def validar_vinculos(bruto, url: str, titulo: str) -> list[dict]:
    """Deja pasar solo lo que tiene forma válida. La URL la pone el sistema."""
    salida = []
    # Tope por página: que una sola fuente no copie la ficha entera.
    for v in (bruto or [])[:8]:
        if not isinstance(v, dict):
            continue
        tipo = str(v.get("tipo") or "").strip().lower()
        contraparte = str(v.get("contraparte") or "").strip()
        detalle = str(v.get("detalle") or "").strip()
        if tipo not in TIPOS or len(contraparte) < 2 or len(detalle) < 10:
            continue
        etiqueta = str(v.get("etiqueta") or "")[:120]
        if es_terciaria(url):
            etiqueta = (etiqueta + " · fuente terciaria").strip(" ·")[:120]
        salida.append({
            "tipo": tipo,
            "contraparte_nombre": contraparte[:120],
            "etiqueta": etiqueta,
            "desde": anio(v.get("desde")),
            "hasta": anio(v.get("hasta")),
            "registro": procedencia(v.get("registro"), url),
            "detalle": detalle[:600],
            "fuentes": [[titulo[:140] or url, url]],
        })
    return salida


# ─────────────────────────── registro ───────────────────────────

def cargar_registro() -> dict:
    if REGISTRO.exists():
        try:
            d = json.loads(REGISTRO.read_text(encoding="utf-8"))
            d.setdefault("personas", {})
            d.setdefault("organizaciones", {})
            d.setdefault("vinculos", {})
            return d
        except Exception:
            pass
    return {"personas": {}, "organizaciones": {}, "vinculos": {}}


def main() -> int:
    nombre = os.environ.get("TELAR_NOMBRE", "").strip()
    pais = os.environ.get("TELAR_PAIS", "").strip()
    rol = os.environ.get("TELAR_ROL", "").strip()
    nota = os.environ.get("TELAR_NOTA", "").strip()
    if not nombre:
        log("Falta TELAR_NOMBRE.")
        return 2

    pid = slug(nombre)
    if not pid:
        log("El nombre no produce un identificador válido.")
        return 2

    log(f"Telar · investigando «{nombre}» con {MODELO}")
    paginas = candidatos(nombre, pais, rol, nota)
    log(f"  {len(paginas)} páginas candidatas")
    if not paginas:
        log("Sin resultados de búsqueda; no se abre ficha.")
        return 1

    confirmaciones, vinculos, resumenes, roles = 0, [], [], []
    for i, p in enumerate(paginas, 1):
        texto = descargar(p["url"])
        if not texto:
            log(f"  [{i}/{len(paginas)}] {p['dominio']}: sin texto utilizable")
            continue
        r = preguntar(texto, p["titulo"], nombre)
        if not r:
            continue
        if r.get("es_figura_publica") is True:
            confirmaciones += 1
            if r.get("rol_publico"):
                roles.append(str(r["rol_publico"])[:200])
            if r.get("resumen"):
                resumenes.append(str(r["resumen"])[:600])
        nuevos = validar_vinculos(r.get("vinculos"), p["url"], p["titulo"])
        vinculos += nuevos
        log(f"  [{i}/{len(paginas)}] {p['dominio']}: {len(nuevos)} vínculos")
        time.sleep(ESPERA_ENTRE_LLAMADAS)

    # Admisión: sin confirmación de rol público en al menos dos páginas, no hay ficha.
    if confirmaciones < 2 or not vinculos:
        log(f"No se abre ficha: {confirmaciones} confirmaciones de rol público, {len(vinculos)} vínculos.")
        print(f"::notice::Telar no abrió ficha para «{nombre}»: no se confirmó un rol público con fuentes suficientes.")
        return 1

    reg = cargar_registro()

    # Organizaciones, deducidas del nombre que da cada página.
    for v in vinculos:
        oid = slug(v["contraparte_nombre"])
        if not oid:
            continue
        v["_oid"] = oid
        if oid not in reg["organizaciones"]:
            reg["organizaciones"][oid] = {
                "nombre": v["contraparte_nombre"], "tipo": "otra",
                "pais": pais, "ciudad": "", "lat": None, "lon": None,
                "resumen": "", "creado": ahora(), "por": "flujo",
            }

    previa = reg["personas"].get(pid, {})
    reg["personas"][pid] = {
        "nombre": previa.get("nombre") or nombre,
        "rolPublico": previa.get("rolPublico") or (roles[0] if roles else rol) or "Figura pública",
        "pais": previa.get("pais") or pais,
        "ciudad": previa.get("ciudad", ""),
        "lat": previa.get("lat"), "lon": previa.get("lon"),
        "alias": previa.get("alias", []),
        "resumen": previa.get("resumen") or (" ".join(resumenes[:2])[:900]),
        "estado": "en curso",
        "creado": previa.get("creado") or ahora(),
        "actualizado": ahora(),
        "por": "flujo",
    }

    escritos = 0
    for v in vinculos:
        if not v.get("_oid"):
            continue
        vid = slug(f"{pid}-{v['_oid']}-{v['tipo']}-{v['desde']}")[:60]
        if vid in reg["vinculos"]:
            vid = slug(f"{vid}-{abs(hash(v['detalle'])) % 9973}")[:60]
        reg["vinculos"][vid] = {
            "personaId": pid, "contraparte": "org:" + v["_oid"], "tipo": v["tipo"],
            "etiqueta": v["etiqueta"], "desde": v["desde"], "hasta": v["hasta"],
            "monto": "", "moneda": "", "registro": v["registro"],
            "detalle": v["detalle"], "fuentes": v["fuentes"],
            "creado": ahora(), "por": "flujo",
        }
        escritos += 1

    reg["generado"] = ahora()
    reg["nota"] = ("Registro de Telar. Fichas extraídas de páginas realmente descargadas; "
                   "cada vínculo lleva la URL de la página de la que salió.")
    REGISTRO.parent.mkdir(parents=True, exist_ok=True)
    REGISTRO.write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8")

    log(f"Ficha escrita: {escritos} vínculos, {len(reg['organizaciones'])} organizaciones en el registro.")
    print(f"::notice::Telar abrió la ficha de «{nombre}» con {escritos} vínculos.")
    resumen = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumen:
        with open(resumen, "a", encoding="utf-8") as f:
            f.write(f"### Telar · {nombre}\n\n"
                    f"Modelo: **{MODELO}** · páginas leídas: {len(paginas)} · "
                    f"vínculos escritos: **{escritos}** · confirmaciones de rol público: {confirmaciones}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
