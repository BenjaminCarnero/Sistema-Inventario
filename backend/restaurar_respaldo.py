"""Restaura una copia de seguridad sobre la base en uso.

Un respaldo que nadie probó restaurar no es un respaldo: es una carpeta que
ocupa lugar y da tranquilidad falsa. Esto es el otro lado de `respaldos.py`.

    python restaurar_respaldo.py                    # lista lo que hay
    python restaurar_respaldo.py applify_2026....db # restaura esa copia

Antes de tocar nada verifica que la copia se pueda abrir y que tenga las tablas
esperadas, y guarda la base actual al lado con el sufijo `.reemplazada`. Si la
copia estuviera dañada, el comando se planta sin haber tocado la base buena.

IMPORTANTE: el backend tiene que estar detenido. Con WAL activo hay archivos
`-wal` y `-shm` al lado de la base; si se reemplaza el archivo mientras alguien
escribe, queda un revoltijo.
"""
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from app import respaldos
from app.config import settings

# Tablas sin las cuales esto no es una base de este sistema
TABLAS_ESPERADAS = {"usuarios", "productos", "ventas", "detalle_ventas"}


def _ruta_de_la_base() -> Path:
    prefijo = "sqlite:///"
    if not settings.DATABASE_URL.startswith(prefijo):
        print(
            "La base no es SQLite. Con SQL Server u otro motor, la restauración "
            "la hace el propio motor.",
            file=sys.stderr,
        )
        sys.exit(1)
    return Path(settings.DATABASE_URL[len(prefijo):])


def _verificar(copia: Path) -> None:
    """Se planta si la copia no sirve, antes de tocar la base buena.

    `sqlite3.connect` no falla al abrir un archivo que no es una base: el error
    aparece recién en la primera consulta. Por eso todo va dentro del try, y no
    sólo la conexión.
    """
    conexion = None
    try:
        conexion = sqlite3.connect(f"file:{copia}?mode=ro", uri=True)

        estado = conexion.execute("PRAGMA integrity_check").fetchone()[0]
        if estado != "ok":
            print(f"La copia está dañada: {estado}", file=sys.stderr)
            sys.exit(1)

        tablas = {f[0] for f in conexion.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        faltantes = TABLAS_ESPERADAS - tablas
        if faltantes:
            print(
                f"La copia no parece de este sistema: le faltan {', '.join(sorted(faltantes))}",
                file=sys.stderr,
            )
            sys.exit(1)

        ventas = conexion.execute("SELECT count(*) FROM ventas").fetchone()[0]
        usuarios = conexion.execute("SELECT count(*) FROM usuarios").fetchone()[0]
        print(f"La copia se abre bien: {ventas} ventas y {usuarios} usuarios.")
    except sqlite3.Error as error:
        print(f"No se puede leer la copia: {error}", file=sys.stderr)
        sys.exit(1)
    finally:
        if conexion is not None:
            conexion.close()


def listar() -> None:
    copias = respaldos.listar()
    if not copias:
        print(f"No hay copias en {respaldos.CARPETA}.")
        return

    print(f"Copias disponibles en {respaldos.CARPETA}:\n")
    for copia in copias:
        cuando = copia["fecha_hora"].strftime("%d/%m/%Y %H:%M")
        print(f"  {copia['nombre']}   {cuando}   {copia['bytes'] / 1024:.0f} KB")
    print("\nPara restaurar:  python restaurar_respaldo.py <nombre>")


def restaurar(nombre: str) -> None:
    copia = respaldos.ruta_de(nombre)
    if copia is None:
        print(f"No existe la copia '{nombre}'. Ejecutá el comando sin argumentos para ver la lista.",
              file=sys.stderr)
        sys.exit(1)

    base = _ruta_de_la_base()
    print(f"Copia:  {copia}")
    print(f"Base:   {base}\n")

    _verificar(copia)

    if base.exists():
        actual = sqlite3.connect(f"file:{base}?mode=ro", uri=True)
        try:
            ventas = actual.execute("SELECT count(*) FROM ventas").fetchone()[0]
            print(f"La base actual tiene {ventas} ventas y se va a reemplazar.")
        except sqlite3.Error:
            print("La base actual no se puede leer (por eso estarás restaurando).")
        finally:
            actual.close()

    print("\nEsto reemplaza la base en uso. El backend tiene que estar detenido.")
    if input("Escribí 'restaurar' para confirmar: ").strip().lower() != "restaurar":
        print("Cancelado. No se tocó nada.")
        return

    # La base actual se guarda antes de pisarla: si la copia resulta ser más
    # vieja de lo que se creía, todavía hay marcha atrás.
    if base.exists():
        marca = datetime.now().strftime("%Y%m%d_%H%M%S")
        reemplazada = base.with_name(f"{base.name}.reemplazada_{marca}")
        shutil.copy2(base, reemplazada)
        print(f"\nLa base anterior quedó en: {reemplazada}")

    # Los archivos de WAL pertenecen a la base vieja: dejarlos corrompe la nueva
    for sufijo in ("-wal", "-shm"):
        acompanante = base.with_name(base.name + sufijo)
        if acompanante.exists():
            acompanante.unlink()

    shutil.copy2(copia, base)
    print(f"Restaurado. Ya podés arrancar el backend de nuevo.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        listar()
    else:
        restaurar(sys.argv[1])
