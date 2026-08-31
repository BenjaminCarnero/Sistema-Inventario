"""Registro de cambios sensibles.

El stock ya tenía su historial de movimientos, pero los pesos no: cambiar un
precio, un descuento o la alícuota del impuesto no dejaba rastro. Eso permite
bajar un precio, vender y volver a subirlo sin que nadie se entere.

Se registran los campos que mueven plata o permisos, no todos. Un registro que
guarda cada cambio de imagen o de nombre se vuelve ilegible, y una auditoría
que nadie lee no sirve.
"""
from typing import Any, Optional

from sqlalchemy.orm import Session

from app import models

# Qué campos se vigilan de cada entidad. Lo que no está acá no se registra.
CAMPOS_VIGILADOS = {
    # `activo` es la baja y el alta de un producto: saca o devuelve mercadería
    # al catálogo del POS, así que es un cambio que hay que poder rastrear.
    "producto": ("precio_venta", "costo", "activo"),
    "descuento": ("nombre", "tipo", "valor", "activo", "codigo_promocional",
                  "producto_id", "fecha_inicio", "fecha_fin"),
    "usuario": ("rol_id", "estado", "pin_acceso"),
}


def _texto(valor: Any) -> Optional[str]:
    """Deja el valor listo para guardar y para leer de un vistazo."""
    if valor is None:
        return None
    if isinstance(valor, bool):
        return "sí" if valor else "no"
    # El PIN nunca se guarda, ni siquiera hasheado: alcanza con saber que cambió
    return str(valor)


def registrar(
    db: Session,
    usuario: Optional[models.Usuario],
    entidad: str,
    accion: str,
    entidad_id: Optional[int] = None,
    entidad_nombre: Optional[str] = None,
    campo: Optional[str] = None,
    valor_anterior: Any = None,
    valor_nuevo: Any = None,
) -> None:
    """Agrega una entrada. No hace commit: viaja con la transacción que la generó."""
    db.add(models.Auditoria(
        usuario_id=usuario.id if usuario else None,
        entidad=entidad,
        entidad_id=entidad_id,
        entidad_nombre=entidad_nombre,
        accion=accion,
        campo=campo,
        valor_anterior=_texto(valor_anterior),
        valor_nuevo=_texto(valor_nuevo),
    ))


def registrar_cambios(
    db: Session,
    usuario: Optional[models.Usuario],
    entidad: str,
    objeto: Any,
    datos_nuevos: dict,
    entidad_nombre: Optional[str] = None,
) -> None:
    """Compara y registra sólo los campos vigilados que realmente cambiaron.

    Guardar un cambio donde el valor quedó igual ensucia el registro y hace que
    después nadie lo mire.
    """
    vigilados = CAMPOS_VIGILADOS.get(entidad, ())

    for campo, valor_nuevo in datos_nuevos.items():
        if campo not in vigilados:
            continue

        valor_anterior = getattr(objeto, campo, None)
        if valor_anterior == valor_nuevo:
            continue

        # El PIN se registra como un hecho, sin los valores
        if campo == "pin_acceso":
            registrar(db, usuario, entidad, "MODIFICAR",
                      entidad_id=getattr(objeto, "id", None),
                      entidad_nombre=entidad_nombre,
                      campo="pin_acceso",
                      valor_anterior="(oculto)", valor_nuevo="(cambiado)")
            continue

        registrar(db, usuario, entidad, "MODIFICAR",
                  entidad_id=getattr(objeto, "id", None),
                  entidad_nombre=entidad_nombre,
                  campo=campo,
                  valor_anterior=valor_anterior, valor_nuevo=valor_nuevo)
