from fastapi import APIRouter, Depends, HTTPException, Query, status
from app import models, dependencies
from app.config import settings
import mercadopago
from pydantic import BaseModel
import uuid

router = APIRouter(prefix="/pagos", tags=["pagos"])


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


class PreferenceCreate(BaseModel):
    title: str
    quantity: int
    unit_price: float


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
        "back_urls": {
            "success": "http://localhost:5173",
            "failure": "http://localhost:5173",
            "pending": "http://localhost:5173",
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
    """Confirma un pago sólo si además coincide el importe.

    Con mirar únicamente `status == approved` alcanzaba con generar una
    preferencia de $1 para dar por pagado un carrito de $50.000: hay que
    comparar contra lo que realmente se cobró.
    """
    payment_response = get_sdk().payment().search({"external_reference": external_reference})
    payments = payment_response.get("response", {}).get("results", [])

    aprobados = [p for p in payments if p.get("status") == "approved"]
    if not aprobados:
        return {"approved": False, "pagado": 0.0}

    # Puede haber más de un pago aprobado contra la misma referencia
    pagado = sum(float(p.get("transaction_amount") or 0) for p in aprobados)

    # Tolerancia de un centavo por el redondeo de Mercado Pago
    suficiente = pagado + 0.01 >= total_esperado

    return {
        "approved": suficiente,
        "pagado": round(pagado, 2),
        "esperado": round(total_esperado, 2),
        # Permite avisar al cajero en lugar de dar la venta por cerrada
        "monto_insuficiente": bool(aprobados) and not suficiente,
    }
