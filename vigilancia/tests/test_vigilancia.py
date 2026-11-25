"""Pruebas del módulo de vigilancia.  Ejecutar desde vigilancia/:  python -m pytest -q

Todo corre sin red: las funciones de parseo y de coincidencia son puras y los
clientes HTTP se prueban con una sesión falsa.
"""
from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from vigilancia import descarte, lanzamientos, meteoros


# ───────────────────────────────────────────────────────── lanzamientos
CRUDO = {
    "id": "abc", "name": "Falcon 9 | Starlink Group 15-21", "net": "2026-11-20T04:08:00Z",
    "url": "https://ll.thespacedevs.com/2.3.0/launches/abc/",
    "launch_service_provider": {"name": "SpaceX"},
    "rocket": {"configuration": {"full_name": "Falcon 9 Block 5"}},
    "pad": {"location": {"name": "Vandenberg SFB"}, "country": {"alpha_3_code": "USA"}},
}


def test_normalizar_extrae_lo_necesario_y_detecta_starlink():
    n = lanzamientos.normalizar(CRUDO)
    assert n["nombre"] == "Falcon 9 | Starlink Group 15-21"
    assert n["cohete"] == "Falcon 9 Block 5"
    assert n["sitio"] == "Vandenberg SFB"
    assert n["pais"] == "USA"
    assert n["starlink"] is True


def test_normalizar_descarta_lo_que_no_tiene_fecha():
    assert lanzamientos.normalizar({"name": "Sin fecha"}) is None


def test_normalizar_tolera_estructuras_incompletas():
    n = lanzamientos.normalizar({"name": "X", "net": "2026-11-20T00:00:00Z", "pad": None})
    assert n["sitio"] == "" and n["cohete"] == "" and n["starlink"] is False


def test_starlink_coincide_hasta_72_horas_despues():
    l = [lanzamientos.normalizar(CRUDO)]
    dentro = datetime(2026, 11, 22, 4, 0, tzinfo=timezone.utc)      # ~48 h después
    fuera = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)      # ~104 h después
    assert [c["tipo"] for c in lanzamientos.coincidencias(l, dentro)] == ["starlink"]
    assert lanzamientos.coincidencias(l, fuera) == []


def test_starlink_no_coincide_antes_del_lanzamiento():
    """Un tren no se ve antes de despegar: la ventana no puede ser simétrica."""
    l = [lanzamientos.normalizar(CRUDO)]
    antes = datetime(2026, 11, 19, 4, 0, tzinfo=timezone.utc)
    assert lanzamientos.coincidencias(l, antes) == []


def test_lanzamiento_no_starlink_usa_ventana_de_un_dia():
    crudo = dict(CRUDO, name="Long March 8A | SatNet LEO Group 30")
    l = [lanzamientos.normalizar(crudo)]
    assert [c["tipo"] for c in lanzamientos.coincidencias(
        l, datetime(2026, 11, 20, 20, 0, tzinfo=timezone.utc))] == ["lanzamiento"]
    assert lanzamientos.coincidencias(l, datetime(2026, 11, 23, 4, 0, tzinfo=timezone.utc)) == []


def test_cada_coincidencia_lleva_fuente_y_tipo_valido():
    l = [lanzamientos.normalizar(CRUDO)]
    for c in lanzamientos.coincidencias(l, datetime(2026, 11, 21, 4, 0, tzinfo=timezone.utc)):
        assert c["fuente"].startswith("http")
        assert c["tipo"] in descarte.TIPOS
        assert c["detalle"]


def test_obtener_degrada_a_cache_sin_lanzar(monkeypatch, tmp_path):
    class SesionRota:
        def get(self, *a, **k):
            raise OSError("sin red")

    monkeypatch.setattr(lanzamientos, "CFG", replace(lanzamientos.CFG, cache=tmp_path))
    r = lanzamientos.obtener(sesion=SesionRota())
    assert r["origen"] == "cache" and r["lanzamientos"] == [] and r["nota"]


# ───────────────────────────────────────────────────────────── meteoros
def test_periodo_de_url_en_los_dos_formatos():
    assert meteoros.periodo_de_url(
        "https://www.amsmeteors.org/2026/11/meteor-activity-outlook-for-november-14-20-2026/"
    ) == (date(2026, 11, 14), date(2026, 11, 20))
    assert meteoros.periodo_de_url(
        "https://amsmeteors.org/2025/11/meteor-activity-outlook-for-15-21-november-2025/"
    ) == (date(2025, 11, 15), date(2025, 11, 21))


def test_periodo_de_url_cruza_de_mes():
    assert meteoros.periodo_de_url(
        "https://www.amsmeteors.org/2026/11/meteor-activity-outlook-for-november-28-4-2026/"
    ) == (date(2026, 11, 28), date(2026, 12, 4))


def test_periodo_de_url_rechaza_lo_que_no_es_panorama():
    assert meteoros.periodo_de_url("https://www.amsmeteors.org/2026/11/otra-nota/") is None


def test_elegir_panorama_prefiere_el_que_cubre_el_dia():
    urls = [
        "https://www.amsmeteors.org/2026/11/meteor-activity-outlook-for-november-14-20-2026/",
        "https://www.amsmeteors.org/2026/11/meteor-activity-outlook-for-november-21-27-2026/",
    ]
    assert "21-27" in meteoros.elegir_panorama(urls, date(2026, 11, 24))


def test_elegir_panorama_cae_al_anterior_mas_cercano():
    urls = [
        "https://www.amsmeteors.org/2026/11/meteor-activity-outlook-for-november-7-13-2026/",
        "https://www.amsmeteors.org/2026/11/meteor-activity-outlook-for-november-14-20-2026/",
    ]
    assert "14-20" in meteoros.elegir_panorama(urls, date(2026, 11, 24))


HTML = """
<html><body>
<table><tr><th>Otra cosa</th></tr><tr><td>ruido</td></tr></table>
<table>
  <tr><th>Shower</th><th>Code</th><th>Activity Period</th><th>Max Date</th>
      <th>Velocity (km/sec)</th><th>Class</th></tr>
  <tr><td>Leonids</td><td>LEO</td><td>Oct 27 - Dec 7</td><td>Nov 18</td><td>70</td><td>I</td></tr>
  <tr><td>alpha Monocerotids</td><td>AMO</td><td>Nov 13 - Nov 27</td><td>Nov 22</td>
      <td>65</td><td>III</td></tr>
</table>
</body></html>
"""


def test_parsear_lluvias_encuentra_la_tabla_correcta():
    f = meteoros.parsear_lluvias(HTML)
    assert [x["nombre"] for x in f] == ["Leonids", "alpha Monocerotids"]
    assert f[0]["maximo"] == "Nov 18" and f[0]["codigo"] == "LEO"
    assert f[1]["actividad"] == "Nov 13 - Nov 27"


def test_parsear_lluvias_devuelve_vacio_si_no_reconoce_la_tabla():
    assert meteoros.parsear_lluvias("<table><tr><th>Precio</th></tr></table>") == []
    assert meteoros.parsear_lluvias("<p>sin tablas</p>") == []


def test_coincidencia_de_meteoros_cita_la_url_y_nombra_las_lluvias():
    f = meteoros.parsear_lluvias(HTML)
    url = "https://www.amsmeteors.org/2026/11/meteor-activity-outlook-for-november-21-27-2026/"
    c = meteoros.coincidencias(f, url, date(2026, 11, 24))
    assert len(c) == 1 and c[0]["tipo"] == "meteoros" and c[0]["fuente"] == url
    assert "Leonids" in c[0]["detalle"] and "24 de noviembre" in c[0]["detalle"]


def test_sin_lluvias_no_hay_coincidencia():
    assert meteoros.coincidencias([], "https://x", date(2026, 11, 24)) == []


# ───────────────────────────────────────────────────────────── descarte
def _cal():
    return {
        "dia": "2026-11-24",
        "lanzamientos": {"lanzamientos": [lanzamientos.normalizar(CRUDO)]},
        "meteoros": {"lluvias": meteoros.parsear_lluvias(HTML),
                     "url": "https://www.amsmeteors.org/2026/11/"
                            "meteor-activity-outlook-for-november-21-27-2026/"},
        "notas": [],
    }


def test_revisar_sin_fecha_no_marca_revisado():
    r = descarte.revisar(_cal(), "")
    assert r["descarte"] == [] and r["descarteRevisado"] is False and r["notas"]


@pytest.mark.parametrize("mala", [None, "no declarado", "2026-13-45"])
def test_revisar_tolera_fechas_invalidas(mala):
    r = descarte.revisar(_cal(), mala)
    assert r["descarteRevisado"] is False


def test_revisar_devuelve_las_dos_categorias():
    r = descarte.revisar(_cal(), "2026-11-22")
    tipos = {c["tipo"] for c in r["descarte"]}
    assert tipos == {"starlink", "meteoros"} and r["descarteRevisado"] is True


def test_revisar_sin_datos_de_calendario_no_marca_revisado():
    vacio = {"dia": "2026-11-24", "lanzamientos": {"lanzamientos": []},
             "meteoros": {"lluvias": [], "url": None}, "notas": []}
    r = descarte.revisar(vacio, "2026-11-22")
    assert r["descarte"] == [] and r["descarteRevisado"] is False


def test_revisar_usa_la_hora_cuando_se_da():
    """A las 02:00 del 23 el tren sigue dentro de las 72 h; a las 23:00 ya no."""
    assert any(c["tipo"] == "starlink" for c in descarte.revisar(_cal(), "2026-11-23", "02:00")["descarte"])
    assert not any(c["tipo"] == "starlink" for c in descarte.revisar(_cal(), "2026-11-23", "23:00")["descarte"])


# ─────────────────────────────────────────────── pertinencia: distancia
VANDENBERG = dict(CRUDO, name="Falcon 9 | NROL-136",
                  pad={"location": {"name": "Vandenberg SFB"}, "latitude": "34.632",
                       "longitude": "-120.611", "country": {"alpha_3_code": "USA"}})
JIUQUAN = dict(CRUDO, name="Long March 2D | Shijian 24",
               pad={"location": {"name": "Jiuquan"}, "latitude": 40.958,
                    "longitude": 100.291, "country": {"alpha_3_code": "CHN"}})

CUANDO = datetime(2026, 11, 20, 4, 0, tzinfo=timezone.utc)


def test_normalizar_extrae_las_coordenadas_del_pad():
    n = lanzamientos.normalizar(VANDENBERG)
    assert round(n["lat"], 3) == 34.632 and round(n["lon"], 3) == -120.611


def test_distancia_km_conocida():
    """Vandenberg a Jiuquan, por el arco mayor del globo: unos 10.600 km."""
    d = lanzamientos.distancia_km(34.632, -120.611, 40.958, 100.291)
    assert 10400 < d < 10800


def test_distancia_km_sin_coordenada_es_none():
    assert lanzamientos.distancia_km(None, -120.6, 40.9, 100.2) is None


def test_lanzamiento_lejano_se_descarta():
    """Un Long March desde Jiuquan no explica nada visto en Nueva Zelanda."""
    l = [lanzamientos.normalizar(JIUQUAN)]
    assert lanzamientos.coincidencias(l, CUANDO, -34.75, 172.85) == []


def test_lanzamiento_cercano_se_conserva_y_dice_la_distancia():
    l = [lanzamientos.normalizar(VANDENBERG)]
    c = lanzamientos.coincidencias(l, CUANDO, 32.83, -117.27)      # San Diego
    assert len(c) == 1 and c[0]["tipo"] == "lanzamiento"
    assert "km del avistamiento" in c[0]["detalle"]


def test_sin_coordenadas_se_conserva_pero_se_advierte():
    l = [lanzamientos.normalizar(JIUQUAN)]
    c = lanzamientos.coincidencias(l, CUANDO)
    assert len(c) == 1 and "No se pudo comprobar si era visible" in c[0]["detalle"]


def test_starlink_no_se_filtra_por_distancia():
    """Un tren se ve a miles de km del pad, así que la lejanía no lo descarta."""
    l = [lanzamientos.normalizar(dict(CRUDO, pad=VANDENBERG["pad"]))]
    c = lanzamientos.coincidencias(l, datetime(2026, 11, 22, 4, 0, tzinfo=timezone.utc),
                                   -34.75, 172.85)
    assert len(c) == 1 and c[0]["tipo"] == "starlink"
    assert "la lejanía no lo descarta" in c[0]["detalle"]


# ─────────────────────────────────────────────── pertinencia: rareza
@pytest.mark.parametrize("rareza", ["mar", "montaje", "natural"])
def test_rareza_sin_descarte_no_recibe_coincidencias(rareza):
    """Un cohete no explica cachalotes varados, un video con IA ni un halo solar."""
    r = descarte.revisar(_cal(), "2026-11-22", rareza=rareza)
    assert r["descarte"] == [] and r["descarteRevisado"] is False
    assert any("no aplica" in n for n in r["notas"])


@pytest.mark.parametrize("rareza", ["cielo", None])
def test_rareza_cielo_y_avistamiento_clasico_si_se_cruzan(rareza):
    r = descarte.revisar(_cal(), "2026-11-22", rareza=rareza)
    assert r["descarte"] and r["descarteRevisado"] is True


# ─────────────────────────────────────────────── descubrimiento del panorama
def test_meteoros_cae_al_indice_si_falla_wp(monkeypatch, tmp_path):
    panorama = "https://www.amsmeteors.org/2026/11/meteor-activity-outlook-for-november-21-27-2026/"

    class Sesion:
        def get(self, url, **k):
            class R:
                status_code = 200
                def raise_for_status(self): pass
            r = R()
            if "wp-json" in url:
                raise OSError("wp-json caído")
            if "articles" in url:
                r.text = f'<a href="{panorama}">x</a>'
            else:
                r.text = HTML
            return r

    monkeypatch.setattr(meteoros, "CFG", replace(meteoros.CFG, cache=tmp_path))
    r = meteoros.obtener(date(2026, 11, 24), sesion=Sesion())
    assert r["origen"] == "api" and r["via"] == "índice" and len(r["lluvias"]) == 2


def test_meteoros_informa_por_que_falla(monkeypatch, tmp_path):
    class Sesion:
        def get(self, *a, **k):
            raise OSError("sin red")

    monkeypatch.setattr(meteoros, "CFG", replace(meteoros.CFG, cache=tmp_path))
    r = meteoros.obtener(date(2026, 11, 24), sesion=Sesion())
    assert r["origen"] == "cache" and "wp-json" in r["nota"] and "índice" in r["nota"]
