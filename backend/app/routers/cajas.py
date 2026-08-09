from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from app import models, schemas, database, dependencies
from app.routers.configuracion import obtener_config

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

    # Diferencia = (Monto Declarado) - (Monto Inicial + Ventas Efectivo)
    monto_esperado = caja.monto_inicial + ventas_efectivo
    diferencia = caja_close.monto_final_declarado - monto_esperado

    caja.fecha_cierre = func.now()
    caja.monto_final_declarado = caja_close.monto_final_declarado
    caja.diferencia_calculada = diferencia

    db.commit()
    db.refresh(caja)
    return caja
