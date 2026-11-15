"""Temas de texto con sentence-transformers (uso interno de los relatos).

Los relatos se convierten en vectores semánticos, se agrupan con KMeans y
cada grupo se describe con sus palabras más distintivas (c-TF-IDF). Solo se
publican esas palabras y estadísticas agregadas: ningún relato sale del
pipeline.

Si sentence-transformers no está disponible, se usa un respaldo TF-IDF +
SVD, que también es 100 % local, y la salida lo indica.
"""
from __future__ import annotations

import logging
from collections import Counter

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import normalize

from .config import CFG
from . import fuentes

log = logging.getLogger(__name__)

RUIDO = {"nuforc", "note", "pd", "witness", "provides", "information", "anonymous", "elects", "remain",
         "saw", "seen", "looked", "like", "just", "did", "went", "got", "time", "sky", "object", "objects",
         "light", "lights", "ufo", "report", "reported", "approximately", "est", "nbsp", "minutes", "seconds"}


def _embeddings(textos: list[str]) -> tuple[np.ndarray, str]:
    try:
        from sentence_transformers import SentenceTransformer
        m = SentenceTransformer(CFG.texto_modelo, device="cpu")
        X = m.encode(textos, batch_size=128, show_progress_bar=False, normalize_embeddings=True)
        return np.asarray(X), f"sentence-transformers · {CFG.texto_modelo}"
    except Exception as e:
        log.warning("sentence-transformers no disponible (%s): respaldo TF-IDF + SVD", e)
        tf = TfidfVectorizer(max_features=30000, stop_words="english", min_df=3, sublinear_tf=True)
        A = tf.fit_transform(textos)
        X = TruncatedSVD(n_components=128, random_state=CFG.semilla).fit_transform(A)
        return normalize(X), "respaldo TF-IDF + SVD (128 dimensiones) · sentence-transformers no disponible"


def _palabras_distintivas(textos: pd.Series, etiquetas: np.ndarray, k: int) -> dict[int, list[str]]:
    docs = [" ".join(textos[etiquetas == c]) for c in range(k)]
    cv = CountVectorizer(stop_words="english", min_df=2, max_features=40000, token_pattern=r"(?u)\b[a-zA-Z]{3,}\b")
    M = cv.fit_transform(docs).astype(float)
    # c-TF-IDF de BERTopic: idf = log(1 + A / f_t), con A = palabras promedio por tema
    tf = normalize(M, norm="l1")
    A = M.sum() / k
    f_t = np.asarray(M.sum(axis=0)).ravel()
    idf = np.log(1 + A / np.maximum(f_t, 1))
    ctfidf = tf.multiply(idf).tocsr()
    vocab = np.array(cv.get_feature_names_out())
    out = {}
    for c in range(k):
        fila = ctfidf.getrow(c).toarray().ravel()
        orden = [vocab[i] for i in np.argsort(-fila) if vocab[i] not in RUIDO]
        out[c] = orden[:8]
    return out


def temas() -> dict:
    df = fuentes.relatos(muestra=CFG.texto_muestra, semilla=CFG.semilla)
    if df.empty:
        return {"disponible": False, "motivo": "No hay relatos descargados en ia/fuentes/."}
    X, motor = _embeddings(df["texto"].tolist())
    k = CFG.texto_temas
    km = KMeans(n_clusters=k, n_init=10, random_state=CFG.semilla)
    etiquetas = km.fit_predict(X)
    palabras = _palabras_distintivas(df["texto"], etiquetas, k)
    agua = df["texto"].str.contains(r"\b(?:ocean|sea|water|lake|beach|boat|ship|shore|coast)\b", case=False, regex=True)
    salida = []
    for c in range(k):
        m = etiquetas == c
        sub = df[m]
        salida.append({
            "id": int(c), "n": int(m.sum()), "pct": round(100 * m.mean(), 1),
            "palabras": palabras[c],
            "formas": [[f, int(n)] for f, n in Counter(sub["forma"]).most_common(3)],
            "anio_mediano": int(sub["anio"].median()) if sub["anio"].notna().any() else None,
            "agua_pct": round(100 * float(agua[m].mean()), 1),
        })
    salida.sort(key=lambda t: -t["n"])
    return {"disponible": True, "motor": motor, "muestra": int(len(df)), "k": k,
            "nota": "Temas derivados de los relatos de NUFORC. Se publican solo palabras clave y conteos, nunca el texto.",
            "temas": salida}
