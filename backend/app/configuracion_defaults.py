"""Parámetros configurables del sistema y sus valores por defecto.

Cada entrada define el tipo para castear el valor (que en la base se guarda
siempre como texto), la categoría con la que se agrupa en el panel de admin y
una descripción que se muestra como ayuda.

Los valores por defecto asumen Argentina (IVA 21% ya incluido en el precio de
góndola, pesos argentinos), pero todos se pueden cambiar desde el panel para
operar en otro país.
"""

DEFAULTS = {
    # ---- Marca (white-label) ----
    "marca_logo_url": {
        "valor": "", "tipo": "string", "categoria": "marca",
        "descripcion": "URL del logo del comercio. Si se deja vacío se usa el ícono por defecto. Ideal: PNG o SVG cuadrado.",
    },
    "marca_color_primario": {
        "valor": "#8251EE", "tipo": "string", "categoria": "marca",
        "descripcion": "Color principal de botones, títulos y acentos (hexadecimal)",
    },
    "marca_color_acento": {
        "valor": "#00F2FE", "tipo": "string", "categoria": "marca",
        "descripcion": "Color secundario usado en degradados e importes (hexadecimal)",
    },

    # ---- Datos del negocio (salen impresos en el ticket) ----
    "negocio_nombre": {
        "valor": "APPLIFY POS", "tipo": "string", "categoria": "negocio",
        "descripcion": "Nombre que aparece en el ticket y en el encabezado",
    },
    "negocio_cuit": {
        "valor": "", "tipo": "string", "categoria": "negocio",
        "descripcion": "CUIT / RUT / Tax ID del comercio",
    },
    "negocio_direccion": {
        "valor": "", "tipo": "string", "categoria": "negocio",
        "descripcion": "Dirección impresa en el ticket",
    },
    "negocio_telefono": {
        "valor": "", "tipo": "string", "categoria": "negocio",
        "descripcion": "Teléfono de contacto impreso en el ticket",
    },

    # ---- Impuestos ----
    "iva_porcentaje": {
        "valor": "21", "tipo": "number", "categoria": "impuestos",
        "descripcion": "Alícuota de IVA en porcentaje (Argentina: 21)",
    },
    "iva_incluido_en_precio": {
        "valor": "true", "tipo": "boolean", "categoria": "impuestos",
        "descripcion": "Si está activo, el precio de cada producto ya incluye IVA y en el ticket se desglosa. Si se desactiva, el IVA se suma al total al cobrar.",
    },
    "mostrar_iva_en_ticket": {
        "valor": "true", "tipo": "boolean", "categoria": "impuestos",
        "descripcion": "Mostrar el desglose de neto e IVA en el ticket",
    },
    "iva_nombre": {
        "valor": "IVA", "tipo": "string", "categoria": "impuestos",
        "descripcion": "Cómo se llama el impuesto en tu país (IVA, VAT, Sales Tax…)",
    },

    # ---- Moneda ----
    "moneda_simbolo": {
        "valor": "$", "tipo": "string", "categoria": "moneda",
        "descripcion": "Símbolo que precede a los importes",
    },
    "moneda_codigo": {
        "valor": "ARS", "tipo": "string", "categoria": "moneda",
        "descripcion": "Código ISO de la moneda (ARS, USD, EUR…)",
    },

    # ---- Punto de venta ----
    "umbral_stock_bajo": {
        "valor": "5", "tipo": "number", "categoria": "pos",
        "descripcion": "Stock por debajo del cual se avisa que hay que reponer",
    },
    "permitir_stock_negativo": {
        "valor": "true", "tipo": "boolean", "categoria": "pos",
        "descripcion": "Permitir vender aunque el stock quede en negativo (el producto físico ya salió del local)",
    },
    "monto_maximo_efectivo": {
        "valor": "1000000", "tipo": "number", "categoria": "pos",
        "descripcion": "Tope de lo que se puede cargar en los campos de efectivo (recibido, apertura y cierre de caja). Evita importes absurdos por una tecla de más.",
    },
    "metodos_pago_habilitados": {
        "valor": '["EFECTIVO", "TARJETA", "TRANSFERENCIA", "MERCADOPAGO"]',
        "tipo": "json", "categoria": "pos",
        "descripcion": "Métodos de pago que ve el cajero al cobrar",
    },

    # ---- Ticket ----
    "ticket_mensaje_pie": {
        "valor": "¡Gracias por su compra!", "tipo": "string", "categoria": "ticket",
        "descripcion": "Mensaje final del ticket",
    },
    "ticket_mostrar_logo": {
        "valor": "true", "tipo": "boolean", "categoria": "ticket",
        "descripcion": "Mostrar el nombre del negocio destacado arriba del ticket",
    },

    # ---- Impresora térmica ----
    "impresora_habilitada": {
        "valor": "false", "tipo": "boolean", "categoria": "impresora",
        "descripcion": "Imprimir en una térmica ESC/POS en vez de usar el diálogo de impresión del navegador",
    },
    "impresora_ip": {
        "valor": "", "tipo": "string", "categoria": "impresora",
        "descripcion": "IP de la impresora en la red del local (la mayoría de las térmicas con Ethernet o WiFi usan el puerto 9100)",
    },
    "impresora_puerto": {
        "valor": "9100", "tipo": "number", "categoria": "impresora",
        "descripcion": "Puerto de impresión por red. 9100 (raw/JetDirect) es el que trae la gran mayoría de las térmicas",
    },
    "impresora_ancho_caracteres": {
        "valor": "42", "tipo": "number", "categoria": "impresora",
        "descripcion": "Caracteres por línea: 32 para papel de 58mm, 42 o 48 para 80mm (según el modelo)",
    },
    "impresora_abrir_cajon": {
        "valor": "false", "tipo": "boolean", "categoria": "impresora",
        "descripcion": "Abrir el cajón de dinero al imprimir el ticket (necesita el cajón conectado a la impresora)",
    },

    # ---- Reposición ----
    "pedido_saludo": {
        "valor": "Hola, te hago un pedido:", "tipo": "string", "categoria": "reposicion",
        "descripcion": "Con qué empieza el mensaje que se le manda al proveedor. Adelante va el nombre del negocio.",
    },
    "devolucion_tope_encargado": {
        "valor": "0", "tipo": "number", "categoria": "reposicion",
        "descripcion": "Monto máximo que un encargado puede devolver de una vez sin un administrador. En cero no hay tope. Devolver es sacar plata de la caja.",
    },
    "pedido_despedida": {
        "valor": "¡Gracias!", "tipo": "string", "categoria": "reposicion",
        "descripcion": "Con qué termina el mensaje al proveedor",
    },
}

CATEGORIAS = {
    "marca": "Marca y apariencia",
    "negocio": "Datos del negocio",
    "impuestos": "Impuestos",
    "moneda": "Moneda",
    "pos": "Punto de venta",
    "ticket": "Ticket",
    "impresora": "Impresora térmica",
    "reposicion": "Pedidos a proveedores",
}


def castear(valor: str, tipo: str):
    """Convierte el valor de texto guardado en la base al tipo real."""
    import json

    if tipo == "number":
        try:
            numero = float(valor)
            return int(numero) if numero.is_integer() else numero
        except (TypeError, ValueError):
            return 0
    if tipo == "boolean":
        return str(valor).strip().lower() in ("true", "1", "si", "sí", "yes")
    if tipo == "json":
        try:
            return json.loads(valor)
        except (TypeError, ValueError):
            return None
    return valor


def serializar(valor, tipo: str) -> str:
    """Convierte un valor recibido de la API al texto que se guarda."""
    import json

    if tipo == "json":
        return json.dumps(valor, ensure_ascii=False)
    if tipo == "boolean":
        return "true" if valor in (True, "true", "True", 1, "1") else "false"
    return str(valor)
