"""Descarga el CSV de sismos recientes del USGS y lo guarda como datos.csv.

Se ejecuta en cada corrida (local o en GitHub Actions). Si algo falla,
termina con código distinto de cero para que el workflow se detenga.
"""
import sys
import urllib.request
from datetime import datetime, timezone

URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_week.csv"
ARCHIVO_DATOS = "datos.csv"
ARCHIVO_META = "descarga.txt"


def descargar(url=URL, destino=ARCHIVO_DATOS, meta=ARCHIVO_META):
    peticion = urllib.request.Request(url, headers={"User-Agent": "monitor-sismos-actions"})
    try:
        with urllib.request.urlopen(peticion, timeout=60) as respuesta:
            if respuesta.status != 200:
                raise RuntimeError(f"El USGS respondió con estado HTTP {respuesta.status}")
            contenido = respuesta.read()
    except Exception as error:
        raise RuntimeError(f"No se pudo descargar {url}: {error}") from error

    if not contenido.strip() or b"time" not in contenido.split(b"\n", 1)[0]:
        raise RuntimeError("La descarga está vacía o no parece un CSV del USGS.")

    with open(destino, "wb") as f:
        f.write(contenido)

    # Hora real de la descarga, en UTC
    momento = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    with open(meta, "w", encoding="utf-8") as f:
        f.write(momento)
    return momento


if __name__ == "__main__":
    try:
        hora = descargar()
    except RuntimeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
    print(f"Descarga correcta: {ARCHIVO_DATOS} ({hora})")
