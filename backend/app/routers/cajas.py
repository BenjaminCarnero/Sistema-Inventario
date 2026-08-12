import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, or_
from app import models, schemas, database, dependencies, respaldos
from app.routers.configuracion import obtener_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cajas", tags=["cajas"])


def _validar_monto(db: Session, monto: float, etiqueta: str):
    """Rechaza importes negativos o por encima del tope configurado."""
    if monto < 0:
        raise HTTPException(status_code=400, detail=f"{etiqueta} no puede ser negativo")
    tope = float(obtener_config(db).get("monto_maximo_efectivo") or 1_000_000)
    if monto > tope:
        raise HTTPException(
            status_code=400,
            detail=f"{etiqueta} supera el tope configurado ({tope:,.0f})"
        )


@router.get("/estado", response_model=schemas.CajaTurno)
def get_estado_caja(
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(dependencies.get_current_active_user),
):
    """Devuelve la caja abierta actual del usuario, o 404 si está cerrada."""
    caja = db.query(models.CajaTurno).filter(
        models.CajaTurno.usuario_id == current_user.id,
        models.CajaTurno.fecha_cierre == None  # noqa: E711
    ).first()

    if not caja:
        raise HTTPException(status_code=404, detail="No hay caja abierta")
    return caja


@router.post("/abrir", response_model=schemas.CajaTurno, status_code=status.HTTP_201_CREATED)
def abrir_caja(
    caja_in: schemas.CajaTurnoCreate,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(dependencies.get_current_active_user),
):
    """Abre un nuevo turno de caja para el usuario."""
    caja_abierta = db.query(models.CajaTurno).filter(
        models.CajaTurno.usuario_id == current_user.id,
        models.CajaTurno.fecha_cierre == None  # noqa: E711
    ).first()

    if caja_abierta:
        raise HTTPException(status_code=400, detail="El usuario ya tiene una caja abierta")

    _validar_monto(db, caja_in.monto_inicial, "El efectivo inicial")

    nueva_caja = models.CajaTurno(
        usuario_id=current_user.id,
        monto_inicial=caja_in.monto_inicial,
    )
    db.add(nueva_caja)
    db.commit()
    db.refresh(nueva_caja)
    return nueva_caja


@router.put("/{caja_id}/cerrar", response_model=schemas.CajaTurno)
def cerrar_caja(
    caja_id: int,
    caja_close: schemas.CajaTurnoClose,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(dependencies.get_current_active_user),
):
    """Cierra la caja, calculando la diferencia con el total vendido en efectivo."""
    caja = db.query(models.CajaTurno).filter(
        models.CajaTurno.id == caja_id,
        models.CajaTurno.usuario_id == current_user.id,
        models.CajaTurno.fecha_cierre == None  # noqa: E711
    ).first()

    if not caja:
        raise HTTPException(status_code=404, detail="Caja no encontrada o ya cerrada")

    _validar_monto(db, caja_close.monto_final_declarado, "El efectivo declarado")

    # Total de ventas EN EFECTIVO durante este turno
    ventas_efectivo = db.query(func.sum(models.Venta.total)).filter(
        models.Venta.usuario_id == current_user.id,
        models.Venta.fecha_hora >= caja.fecha_apertura,
        models.Venta.metodo_pago == models.MetodoPagoEnum.EFECTIVO.value
    ).scalar() or 0.0

    # Lo devuelto en efectivo salió del cajón: sin restarlo, el arqueo daría
    # faltante todos los días en que se hizo una devolución.
    #
    # Cada devolución guarda de qué turno salió la plata. Antes esto se
    # resolvía por ventana de tiempo, y con dos cajas abiertas a la vez la
    # misma devolución les daba faltante a las dos.
    #
    # Las que quedaron sin turno —las anteriores a este cambio, y las hechas
    # con varias cajas abiertas por alguien que no tenía la suya— se siguen
    # contando por ventana de tiempo, que es el comportamiento de siempre.
    devoluciones_efectivo = db.query(func.sum(models.Devolucion.total_devuelto)).filter(
        models.Devolucion.metodo_devolucion == models.MetodoPagoEnum.EFECTIVO.value,
        or_(
            models.Devolucion.caja_turno_id == caja.id,
            and_(
                models.Devolucion.caja_turno_id.is_(None),
                models.Devolucion.fecha_hora >= caja.fecha_apertura,
            ),
        ),
    ).scalar() or 0.0

    # Diferencia = Declarado - (Inicial + Ventas en efectivo - Devoluciones en efectivo)
    monto_esperado = caja.monto_inicial + ventas_efectivo - devoluciones_efectivo
    diferencia = caja_close.monto_final_declarado - monto_esperado

    caja.fecha_cierre = func.now()
    caja.monto_final_declarado = caja_close.monto_final_declarado
    caja.diferencia_calculada = diferencia

    db.commit()
    db.refresh(caja)

    # El cierre de caja es el punto natural para respaldar: pasa una vez por
    # turno y marca el final de una jornada de datos. Si la copia falla, el
    # cierre igual quedó hecho: perder el respaldo no puede trabar el negocio.
    try:
        respaldos.crear("cierre_caja")
    except Exception:
        # Al log y no a la consola: este aviso es justamente el que hay que
        # poder leer después, cuando alguien pregunte por qué no hay respaldos.
        logger.exception("No se pudo respaldar la base al cerrar caja")

    return caja
