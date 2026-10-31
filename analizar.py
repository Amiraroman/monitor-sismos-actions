"""Valida datos.csv y genera public/index.html con el informe de sismos."""
import csv
import html
import os
import sys
from datetime import datetime, timedelta, timezone

ESTUDIANTE = "AMIRA ROMAN"
TITULO = "Monitor automático de sismos recientes"
FUENTE_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_week.csv"
DOC_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/csv.php"
COLUMNAS_OBLIGATORIAS = ["time", "mag", "place", "id", "type"]


class ErrorDatos(Exception):
    """Dato indispensable ausente o inválido."""


# ---------------------------------------------------------------- datos

def leer_csv(ruta):
    with open(ruta, newline="", encoding="utf-8") as f:
        lector = csv.DictReader(f)
        columnas = lector.fieldnames or []
        filas = list(lector)
    return columnas, filas


def validar_columnas(columnas):
    faltan = [c for c in COLUMNAS_OBLIGATORIAS if c not in columnas]
    if faltan:
        raise ErrorDatos("Faltan columnas obligatorias: " + ", ".join(faltan))


def parsear_fecha(texto, fila_num=None):
    try:
        fecha = datetime.fromisoformat(texto.strip().replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        raise ErrorDatos(f"Fecha inválida en la fila {fila_num}: {texto!r}")
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    return fecha.astimezone(timezone.utc)


def parsear_magnitud(texto, fila_num=None):
    try:
        valor = float((texto or "").strip())
    except ValueError:
        raise ErrorDatos(f"Magnitud inválida en la fila {fila_num}: {texto!r}")
    if valor != valor or valor in (float("inf"), float("-inf")):
        raise ErrorDatos(f"Magnitud no finita en la fila {fila_num}: {texto!r}")
    return valor


def procesar(filas):
    """Devuelve eventos (solo type = earthquake) validados, del más reciente al más antiguo."""
    eventos = []
    for numero, fila in enumerate(filas, start=2):  # fila 1 = encabezado
        if (fila.get("type") or "").strip() != "earthquake":
            continue
        eventos.append({
            "id": fila["id"],
            "fecha": parsear_fecha(fila["time"], numero),
            "mag": parsear_magnitud(fila["mag"], numero),
            "lugar": (fila.get("place") or "").strip(),
        })
    if not eventos:
        raise ErrorDatos("No hay registros con type = earthquake.")
    eventos.sort(key=lambda e: e["fecha"], reverse=True)
    return eventos


def calcular_indicadores(eventos):
    mayor = max(eventos, key=lambda e: e["mag"])
    return {
        "cantidad": len(eventos),
        "mag_max": mayor["mag"],
        "lugar_max": mayor["lugar"],
        "mas_reciente": eventos[0]["fecha"],
        "inicio": min(e["fecha"] for e in eventos),
        "fin": max(e["fecha"] for e in eventos),
    }


def conteo_por_fecha(eventos):
    """Cantidad de sismos por día UTC (días sin sismos aparecen con 0)."""
    conteo = {}
    for e in eventos:
        dia = e["fecha"].date()
        conteo[dia] = conteo.get(dia, 0) + 1
    primero, ultimo = min(conteo), max(conteo)
    resultado, dia = [], primero
    while dia <= ultimo:
        resultado.append((dia, conteo.get(dia, 0)))
        dia += timedelta(days=1)
    return resultado


# ------------------------------------------------------------- gráficos

def traza_svg(eventos, ind):
    """Sismograma: cada sismo es un pico; la altura indica la magnitud (eje X = tiempo UTC)."""
    ancho, alto, medio, amp_max = 960, 210, 92, 78
    t0 = ind["inicio"].timestamp()
    span = max(ind["fin"].timestamp() - t0, 1)

    def pos_x(ts):
        return 8 + (ts - t0) / span * (ancho - 16)

    def amplitud(mag):
        escala = (ind["mag_max"] - 2.0) or 1.0
        return 6 + max(mag - 2.0, 0.0) / escala * (amp_max - 6)

    cronologicos = sorted(eventos, key=lambda e: e["fecha"])
    trazo = [f"M0,{medio}"]
    for e in cronologicos:
        x, a = pos_x(e["fecha"].timestamp()), amplitud(e["mag"])
        trazo.append(f"L{x - 1:.1f},{medio} L{x:.1f},{medio - a:.1f} "
                     f"L{x + 1:.1f},{medio + a * 0.7:.1f} L{x + 2:.1f},{medio}")
    trazo.append(f"L{ancho},{medio}")

    partes = [f'<svg viewBox="0 0 {ancho} {alto}" role="img" aria-label="Sismograma de los '
              f'{ind["cantidad"]} sismos del periodo. Cada pico es un sismo y su altura indica la magnitud.">']
    partes.append(f'<line class="base" x1="0" y1="{medio}" x2="{ancho}" y2="{medio}"/>')

    # marcas de medianoche UTC
    dia = ind["inicio"].date() + timedelta(days=1)
    while True:
        medianoche = datetime(dia.year, dia.month, dia.day, tzinfo=timezone.utc)
        if medianoche > ind["fin"]:
            break
        x = pos_x(medianoche.timestamp())
        partes.append(f'<line class="marca" x1="{x:.1f}" y1="14" x2="{x:.1f}" y2="{alto - 28}"/>')
        partes.append(f'<text x="{x + 5:.1f}" y="{alto - 10}">{dia.strftime("%d/%m")}</text>')
        dia += timedelta(days=1)

    partes.append(f'<path class="traza" pathLength="1" d="{" ".join(trazo)}"/>')

    # sismo de mayor magnitud
    mayor = next(e for e in cronologicos if e["mag"] == ind["mag_max"])
    x, y = pos_x(mayor["fecha"].timestamp()), medio - amplitud(mayor["mag"])
    lado = "end" if x > ancho * 0.8 else "start"
    dx = -9 if lado == "end" else 9
    partes.append(f'<circle class="mayor" cx="{x:.1f}" cy="{y:.1f}" r="4.5"/>')
    partes.append(f'<text class="etiqueta" text-anchor="{lado}" x="{x + dx:.1f}" y="{max(y + 4, 16):.1f}">'
                  f'magnitud {mayor["mag"]:.1f}</text>')
    partes.append("</svg>")
    return "".join(partes)


def grafico_svg(serie):
    ancho, alto = 720, 300
    mi, md, ms, mb = 44, 10, 24, 40
    maximo = max(n for _, n in serie) or 1
    area_h = alto - ms - mb
    paso = (ancho - mi - md) / len(serie)
    barra = min(paso * 0.62, 56)
    partes = [f'<svg viewBox="0 0 {ancho} {alto}" role="img" aria-label="Cantidad de sismos por fecha (UTC)">']
    for t in sorted({round(maximo * k / 4) for k in range(5)}):
        y = alto - mb - area_h * t / maximo
        partes.append(f'<line class="rejilla" x1="{mi}" y1="{y:.1f}" x2="{ancho - md}" y2="{y:.1f}"/>')
        partes.append(f'<text text-anchor="end" x="{mi - 8}" y="{y + 4:.1f}">{t}</text>')
    for i, (dia, n) in enumerate(serie):
        x = mi + i * paso + (paso - barra) / 2
        h = area_h * n / maximo
        y = alto - mb - h
        nombre = "sismo" if n == 1 else "sismos"
        partes.append(f'<rect class="barra" x="{x:.1f}" y="{y:.1f}" width="{barra:.1f}" height="{h:.1f}" rx="3">'
                      f'<title>{dia.strftime("%d/%m")}: {n} {nombre}</title></rect>')
        partes.append(f'<text class="valor" text-anchor="middle" x="{x + barra / 2:.1f}" y="{y - 6:.1f}">{n}</text>')
        partes.append(f'<text text-anchor="middle" x="{x + barra / 2:.1f}" y="{alto - mb + 18}">'
                      f'{dia.strftime("%d/%m")}</text>')
    partes.append("</svg>")
    return "".join(partes)


# ----------------------------------------------------------------- HTML

def fmt(fecha):
    return fecha.strftime("%Y-%m-%d %H:%M:%S UTC")


CSS = """
:root{
  --papel:#eef2ef; --tinta:#10253f; --suave:#586879; --linea:#cbd6d0;
  --traza:#d6452a; --verde:#1f7a7a;
  --titulos:"Bricolage Grotesque","Segoe UI",system-ui,sans-serif;
  --texto:"IBM Plex Sans","Segoe UI",system-ui,sans-serif;
}
*{box-sizing:border-box}
html{background:var(--papel)}
body{
  margin:0; color:var(--tinta); font:400 1rem/1.55 var(--texto);
  background-image:
    linear-gradient(rgba(16,37,63,.045) 1px,transparent 1px),
    linear-gradient(90deg,rgba(16,37,63,.045) 1px,transparent 1px);
  background-size:24px 24px;
}
main{max-width:1000px; margin:0 auto; padding:3rem 1.25rem 2rem}
a{color:var(--tinta); text-decoration-color:var(--traza); text-underline-offset:3px; text-decoration-thickness:2px}
a:hover{color:var(--traza)}
a:focus-visible{outline:3px solid var(--traza); outline-offset:3px; border-radius:2px}

h1{
  font:700 clamp(2.1rem,6vw,3.9rem)/1.02 var(--titulos);
  letter-spacing:-.025em; margin:0 0 1rem; max-width:14ch;
}
h2{font:600 1.35rem/1.2 var(--titulos); letter-spacing:-.01em; margin:0 0 .9rem}
.lead{max-width:62ch; margin:0 0 1.5rem; font-size:1.075rem}

.ficha{display:flex; flex-wrap:wrap; gap:.75rem 2.5rem; margin:0 0 2.25rem}
.ficha div{min-width:0}
.ficha dt{font-size:.85rem; color:var(--suave)}
.ficha dd{margin:0; font-weight:600; font-variant-numeric:tabular-nums}

.lienzo{overflow-x:auto}
.lienzo svg{display:block; width:100%; min-width:640px; height:auto}
svg text{fill:var(--suave); font:400 12px var(--texto)}
svg .base,svg .marca,svg .rejilla{stroke:var(--linea); stroke-width:1}
svg .marca{stroke-dasharray:3 4}
svg .traza{fill:none; stroke:var(--traza); stroke-width:1.3; stroke-linejoin:round; stroke-linecap:round;
  stroke-dasharray:1; stroke-dashoffset:0}
svg .mayor{fill:var(--papel); stroke:var(--traza); stroke-width:2.5}
svg text.etiqueta{fill:var(--tinta); font-weight:600}
svg .barra{fill:var(--tinta)}
svg .barra:hover{fill:var(--traza)}
svg text.valor{fill:var(--tinta); font-weight:600; font-variant-numeric:tabular-nums}
@media (prefers-reduced-motion:no-preference){
  svg .traza{animation:dibujar 2.6s cubic-bezier(.3,.6,.3,1) both}
  @keyframes dibujar{from{stroke-dashoffset:1}}
}
figcaption{font-size:.9rem; color:var(--suave); margin-top:.5rem}
figure{margin:0}

.cifras{display:grid; grid-template-columns:repeat(3,1fr); margin:2.5rem 0 3rem; border-block:2px solid var(--tinta)}
.cifras div{padding:1.1rem 1.25rem 1.2rem 0}
.cifras div+div{padding-left:1.5rem; border-left:1px solid var(--linea)}
.cifras strong{display:block; font:700 clamp(2.2rem,5vw,3.4rem)/1 var(--titulos); letter-spacing:-.03em;
  font-variant-numeric:tabular-nums}
.cifras .fecha{font-size:clamp(1.15rem,2.6vw,1.5rem); line-height:1.25; letter-spacing:-.01em}
.cifras span{display:block; margin-top:.4rem; color:var(--suave); font-size:.92rem}

section{margin-bottom:3rem}
.tabla{overflow-x:auto}
table{border-collapse:collapse; width:100%; min-width:560px}
th{font-weight:600; font-size:.88rem; color:var(--suave); text-align:left; padding:.5rem .75rem .5rem 0;
  border-bottom:2px solid var(--tinta)}
td{padding:.65rem .75rem .65rem 0; border-bottom:1px solid var(--linea); vertical-align:middle}
td.hora{white-space:nowrap; font-variant-numeric:tabular-nums}
th.num,td.mag{width:9.5rem}
.mag{display:flex; align-items:center; gap:.65rem; font-weight:600; font-variant-numeric:tabular-nums}
.mag i{display:block; height:8px; border-radius:4px; background:var(--verde); flex:none}
.mag.fuerte i{background:var(--traza)}

footer{border-top:1px solid var(--linea); padding-top:1.25rem; color:var(--suave); font-size:.92rem;
  display:flex; flex-wrap:wrap; gap:.4rem 2rem}
.vh{position:absolute; left:-9999px}

@media (max-width:640px){
  main{padding-top:2rem}
  .cifras{grid-template-columns:1fr}
  .cifras div,.cifras div+div{padding:1rem 0; border-left:0}
  .cifras div+div{border-top:1px solid var(--linea)}
}
"""


def generar_html(eventos, descarga_utc, repo_url, estudiante=ESTUDIANTE):
    ind = calcular_indicadores(eventos)
    serie = conteo_por_fecha(eventos)
    filas = []
    for e in eventos[:10]:
        ancho_barra = max(4, min(100, e["mag"] / ind["mag_max"] * 100)) * 0.6
        clase = "mag fuerte" if e["mag"] >= 5 else "mag"
        filas.append(
            f'<tr><td class="hora">{fmt(e["fecha"])}</td><td>{html.escape(e["lugar"])}</td>'
            f'<td><div class="{clase}"><i style="width:{ancho_barra:.0f}px"></i>{e["mag"]:.1f}</div></td></tr>'
        )
    filas = "".join(filas)
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(TITULO)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,700&family=IBM+Plex+Sans:wght@400;600&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<main>
<header>
<h1>{html.escape(TITULO)}</h1>
<p class="lead">Sismos de magnitud 2,5 o superior registrados en los últimos siete días.
Los datos vienen del <a href="{FUENTE_URL}">CSV del Servicio Geológico de Estados Unidos (USGS)</a>
y se actualizan solos con GitHub Actions. <a href="{DOC_URL}">Ver descripción de las columnas</a>.</p>
<dl class="ficha">
<div><dt>Estudiante</dt><dd>{html.escape(estudiante)}</dd></div>
<div><dt>Descarga de datos</dt><dd>{html.escape(descarga_utc)}</dd></div>
<div><dt>Periodo de los datos</dt><dd>{fmt(ind['inicio'])} a {fmt(ind['fin'])}</dd></div>
</dl>
</header>

<figure>
<div class="lienzo">{traza_svg(eventos, ind)}</div>
<figcaption>Cada pico es un sismo y su altura indica la magnitud. El eje horizontal es el tiempo en UTC.</figcaption>
</figure>

<div class="cifras">
<div><strong>{ind['cantidad']}</strong><span>sismos registrados</span></div>
<div><strong>{ind['mag_max']:.1f}</strong><span>magnitud máxima: {html.escape(ind['lugar_max'])}</span></div>
<div><strong class="fecha">{fmt(ind['mas_reciente'])}</strong><span>evento más reciente</span></div>
</div>

<section>
<h2>Los diez sismos más recientes</h2>
<div class="tabla">
<table>
<caption class="vh">Diez sismos más recientes con fecha, ubicación y magnitud</caption>
<thead><tr><th>Fecha (UTC)</th><th>Ubicación</th><th class="num">Magnitud</th></tr></thead>
<tbody>{filas}</tbody>
</table>
</div>
</section>

<section>
<h2>Sismos por fecha</h2>
<figure>
<div class="lienzo">{grafico_svg(serie)}</div>
<figcaption>Días en UTC (día/mes). El primer y el último día pueden estar incompletos.</figcaption>
</figure>
</section>

<footer>
<a href="{repo_url}">Repositorio en GitHub</a>
<a href="{repo_url}/actions">Ejecuciones en Actions</a>
</footer>
</main>
</body>
</html>
"""


def main(ruta_csv="datos.csv", ruta_meta="descarga.txt", salida="public/index.html"):
    columnas, filas = leer_csv(ruta_csv)
    validar_columnas(columnas)
    eventos = procesar(filas)
    with open(ruta_meta, encoding="utf-8") as f:
        descarga = f.read().strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "TU_USUARIO/monitor-sismos-actions")
    repo_url = f"https://github.com/{repo}"
    os.makedirs(os.path.dirname(salida), exist_ok=True)
    with open(salida, "w", encoding="utf-8") as f:
        f.write(generar_html(eventos, descarga, repo_url))
    print(f"Informe generado: {salida} ({len(eventos)} sismos)")


if __name__ == "__main__":
    try:
        main()
    except (ErrorDatos, FileNotFoundError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)