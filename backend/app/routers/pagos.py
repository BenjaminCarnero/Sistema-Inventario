from fastapi import APIRouter, Depends, HTTPException, Query, status
from app import models, dependencies
from app.config import settings
import mercadopago
from mercadopago.config import RequestOptions
from pydantic import BaseModel, Field
import uuid

router = APIRouter(prefix="/pagos", tags=["pagos"])

# Tolerancia al comparar importes: Mercado Pago redondea a dos decimales.
TOLERANCIA_CENTAVOS = 0.01

# El SDK viene con 60 segundos de espera y 3 reintentos: hasta tres minutos
# colgado. `POST /ventas` consulta el cobro con la transacción de escritura
# abierta, así que ese tiempo es tiempo de base bloqueada para las demás cajas.
# Ocho segundos sin reintentos es de sobra para una consulta de estado.
ESPERA_CONSULTA = RequestOptions(connection_timeout=8.0, max_retries=0)


def get_sdk():
    """Instancia el SDK recién cuando se usa.

    Si el token no está configurado se devuelve un 503 claro, en vez de romper
    el arranque de toda la API por una integración opcional.
    """
    if not settings.MERCADOPAGO_ACCESS_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Mercado Pago no está configurado: falta MERCADOPAGO_ACCESS_TOKEN en el .env del backend",
        )
    return mercadopago.SDK(settings.MERCADOPAGO_ACCESS_TOKEN)


def total_aprobado(external_reference: str) -> float:
    """Suma de los pagos aprobados contra una referencia.

    Puede haber más de uno: el cliente que paga en dos partes, o el que
    reintenta después de un rechazo.
    """
    respuesta = get_sdk().payment().search(
        {"external_reference": external_reference},
        request_options=ESPERA_CONSULTA,
    )
    pagos = respuesta.get("response", {}).get("results", [])
    return sum(
        float(p.get("transaction_amount") or 0)
        for p in pagos
        if p.get("status") == "approved"
    )


def alcanza(pagado: float, esperado: float) -> bool:
    """¿Lo cobrado cubre lo que había que cobrar?"""
    return pagado + TOLERANCIA_CENTAVOS >= esperado


class PreferenceCreate(BaseModel):
    # Sin techos, un importe negativo o absurdo viaja tal cual a Mercado Pago
    title: str = Field(min_length=1, max_length=200)
    quantity: int = Field(gt=0, le=10_000)
    unit_price: float = Field(gt=0)


@router.post("/mercadopago/preference")
def create_preference(
    pref: PreferenceCreate,
    current_user: models.Usuario = Depends(dependencies.get_current_active_user),
):
    external_reference = str(uuid.uuid4())

    preference_data = {
        "items": [
            {
                "title": pref.title,
                "quantity": pref.quantity,
                "unit_price": pref.unit_price,
            }
        ],
        "external_reference": external_reference,
        # A dónde vuelve el comprador después de pagar. Clavado a localhost
        # dejaba al cliente en una página inexistente apenas se publicaba el POS.
        "back_urls": {
            "success": settings.FRONTEND_URL,
            "failure": settings.FRONTEND_URL,
            "pending": settings.FRONTEND_URL,
        },
        "auto_return": "approved",
    }

    preference_response = get_sdk().preference().create(preference_data)
    preference = preference_response["response"]

    return {
        "init_point": preference["init_point"],
        "external_reference": external_reference,
    }


@router.get("/mercadopago/status/{external_reference}")
def check_payment_status(
    external_reference: str,
    total_esperado: float = Query(..., gt=0, description="Total que debería haberse cobrado"),
    current_user: models.Usuario = Depends(dependencies.get_current_active_user),
):
    """Estado del cobro, para que el POS sepa cuándo mostrar el ticket.

    Ojo: esto es sólo un aviso para la pantalla del cajero. La venta no se da
    por cobrada con lo que devuelva acá, porque tanto la referencia como el
    total los elige quien llama. La confirmación que vale es la que hace
    `POST /ventas` contra el total que calcula el propio servidor.
    """
    pagado = total_aprobado(external_reference)
    if pagado <= 0:
        return {"approved": False, "pagado": 0.0}

    suficiente = alcanza(pagado, total_esperado)

    return {
        "approved": suficiente,
        "pagado": round(pagado, 2),
        "esperado": round(total_esperado, 2),
        # Acá ya se sabe que algo se pagó: si no alcanza, conviene avisarle al
        # cajero en lugar de dejar la pantalla girando
        "monto_insuficiente": not suficiente,
    }
