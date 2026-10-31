import os
import tempfile
import unittest
from datetime import date

import analizar

CSV_PEQUENO = """time,latitude,longitude,depth,mag,magType,place,id,type
2026-10-30T10:00:00.000Z,0,0,10,3.0,ml,"Lugar A",a1,earthquake
2026-10-30T12:00:00.000Z,0,0,10,5.5,ml,"Lugar B",a2,earthquake
2026-10-29T08:30:00.000Z,0,0,10,2.6,ml,"Lugar C",a3,earthquake
2026-10-29T09:00:00.000Z,0,0,10,4.9,ml,"Cantera",a4,quarry blast
"""


def cargar(texto):
    with tempfile.TemporaryDirectory() as d:
        ruta = os.path.join(d, "x.csv")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(texto)
        return analizar.leer_csv(ruta)


class PruebasAnalizar(unittest.TestCase):
    def test_calculo_conocido(self):
        columnas, filas = cargar(CSV_PEQUENO)
        eventos = analizar.procesar(filas)  # excluye "quarry blast"
        ind = analizar.calcular_indicadores(eventos)
        self.assertEqual(ind["cantidad"], 3)
        self.assertEqual(ind["mag_max"], 5.5)
        self.assertEqual(ind["mas_reciente"].hour, 12)
        conteo = dict(analizar.conteo_por_fecha(eventos))
        self.assertEqual(conteo[date(2026, 10, 30)], 2)
        self.assertEqual(conteo[date(2026, 10, 29)], 1)

    def test_rechaza_magnitud_invalida(self):
        texto = CSV_PEQUENO.replace("5.5", "abc")
        _, filas = cargar(texto)
        with self.assertRaises(analizar.ErrorDatos):
            analizar.procesar(filas)

    def test_rechaza_magnitud_vacia_sin_convertir_a_cero(self):
        texto = CSV_PEQUENO.replace(",5.5,", ",,")
        _, filas = cargar(texto)
        with self.assertRaises(analizar.ErrorDatos):
            analizar.procesar(filas)

    def test_detecta_columna_ausente(self):
        columnas, _ = cargar(CSV_PEQUENO.replace("place", "lugar"))
        with self.assertRaises(analizar.ErrorDatos) as ctx:
            analizar.validar_columnas(columnas)
        self.assertIn("place", str(ctx.exception))

    def test_rechaza_fecha_invalida(self):
        texto = CSV_PEQUENO.replace("2026-10-30T12:00:00.000Z", "no-es-fecha")
        _, filas = cargar(texto)
        with self.assertRaises(analizar.ErrorDatos):
            analizar.procesar(filas)

    def test_genera_informe(self):
        with tempfile.TemporaryDirectory() as d:
            csv_ruta = os.path.join(d, "datos.csv")
            meta = os.path.join(d, "descarga.txt")
            salida = os.path.join(d, "public", "index.html")
            with open(csv_ruta, "w", encoding="utf-8") as f:
                f.write(CSV_PEQUENO)
            with open(meta, "w", encoding="utf-8") as f:
                f.write("2026-10-31 15:00:00 UTC")
            analizar.main(csv_ruta, meta, salida)
            with open(salida, encoding="utf-8") as f:
                contenido = f.read()
        self.assertIn("2026-10-31 15:00:00 UTC", contenido)
        self.assertIn("Lugar B", contenido)
        self.assertIn("5.5", contenido)
        self.assertIn("<svg", contenido)
        self.assertNotIn("Cantera", contenido)


if __name__ == "__main__":
    unittest.main()
