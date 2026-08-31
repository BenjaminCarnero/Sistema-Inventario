from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime, timezone
import enum

from app.database import Base


def ahora_utc():
    """Fecha actual en UTC, sin tzinfo.

    Se genera en Python y no con CURRENT_TIMESTAMP porque SQLite lo guarda sin
    microsegundos, mientras que SQLAlchemy compara contra valores que sí los
    tienen: dos eventos del mismo segundo quedaban fuera de rango y el arqueo
    de caja no contaba esas ventas.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class RolEnum(int, enum.Enum):
    ADMIN = 1
    ENCARGADO = 2
    CAJERO = 3


class MetodoPagoEnum(str, enum.Enum):
    EFECTIVO = "EFECTIVO"
    TARJETA = "TARJETA"
    TRANSFERENCIA = "TRANSFERENCIA"


class TipoMovimientoEnum(str, enum.Enum):
    INGRESO = "INGRESO"
    EGRESO = "EGRESO"
    AJUSTE = "AJUSTE"


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    # UNIQUE de verdad y no sólo validado en código: el token identificaba al
    # usuario por su nombre, así que renombrar a un cajero y crear después otro
    # usuario con el nombre viejo convertía la sesión abierta del cajero en la
    # del usuario nuevo. Ahora el token lleva el id, pero el nombre igual tiene
    # que ser único: es con lo que se inicia sesión.
    nombre = Column(String(100), unique=True, index=True, nullable=False)
    pin_acceso = Column(String(255), nullable=False)  # Hash bcrypt
    rol_id = Column(Integer, default=RolEnum.CAJERO.value)
    estado = Column(Boolean, default=True)
    # Se incrementa cada vez que cambia el PIN. El token lleva el valor que
    # tenía al emitirse, así cambiar o reiniciar un PIN corta las sesiones
    # abiertas al instante. Antes no: quien había visto un PIN por encima del
    # hombro seguía adentro hasta doce horas después de que se lo cambiaran.
    credenciales_version = Column(Integer, nullable=False, default=1, server_default="1")

    ventas = relationship("Venta", back_populates="cajero")
    movimientos = relationship("MovimientoStock", back_populates="encargado")
    cajas = relationship("CajaTurno", back_populates="usuario")


class Categoria(Base):
    __tablename__ = "categorias"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), unique=True, index=True, nullable=False)

    productos = relationship("Producto", back_populates="categoria")


class Proveedor(Base):
    """A quién se le compra la mercadería.

    Un producto tiene un solo proveedor: para un comercio chico alcanza, y
    evita una pantalla de relaciones que nadie mantiene al día.
    """
    __tablename__ = "proveedores"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(150), unique=True, index=True, nullable=False)
    # El teléfono se usa para abrir WhatsApp con el pedido ya escrito
    telefono = Column(String(30), nullable=True)
    email = Column(String(150), nullable=True)
    cuit = Column(String(20), nullable=True)
    # "Entrega los martes", "pedido mínimo $50.000"…
    notas = Column(String(500), nullable=True)
    activo = Column(Boolean, default=True)

    productos = relationship("Producto", back_populates="proveedor")
    pedidos = relationship("Pedido", back_populates="proveedor")


class Producto(Base):
    __tablename__ = "productos"

    id = Column(Integer, primary_key=True, index=True)
    codigo_barras = Column(String(50), unique=True, index=True, nullable=False)
    nombre = Column(String(150), nullable=False)
    precio_venta = Column(Float, nullable=False)
    costo = Column(Float, nullable=False)
    stock_actual = Column(Integer, default=0)
    categoria_id = Column(Integer, ForeignKey("categorias.id"), nullable=True)
    imagen_url = Column(String(500), nullable=True)
    proveedor_id = Column(Integer, ForeignKey("proveedores.id"), nullable=True)
    # "De esto siempre pido dos cajones". Viene precargado al armar el pedido.
    # Es más confiable que calcularlo con las ventas cuando todavía hay poco
    # historial, y el dueño ya sabe el número de memoria.
    cantidad_pedido_habitual = Column(Integer, nullable=True)
    # Baja lógica, igual que la de usuarios. Un producto no se borra: sus
    # ventas pasadas lo siguen refiriendo. Antes no había ninguna forma de
    # sacarlo de circulación, así que el catálogo del POS sólo podía crecer y
    # lo discontinuado seguía apareciendo para siempre.
    activo = Column(Boolean, nullable=False, default=True, server_default="1")

    categoria = relationship("Categoria", back_populates="productos")
    proveedor = relationship("Proveedor", back_populates="productos")
    detalles_venta = relationship("DetalleVenta", back_populates="producto")
    movimientos = relationship("MovimientoStock", back_populates="producto")


class Venta(Base):
    __tablename__ = "ventas"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), index=True, nullable=False)
    # Indexada: el arqueo, los reportes y el panel filtran por rango de fechas
    # en cada consulta. Sin el índice, cada una recorría la tabla entera.
    fecha_hora = Column(DateTime(timezone=True), default=ahora_utc, index=True)
    total = Column(Float, nullable=False)
    # Lo que decía el ticket que se le dio al cliente. En una venta offline el
    # POS calcula el total con el catálogo y el IVA que tiene guardados, y al
    # sincronizar el servidor lo recalcula con los suyos: si el precio o la
    # alícuota cambiaron mientras el equipo estaba sin señal, los dos números
    # no coinciden. Guardarlo es lo que permite darse cuenta; antes la
    # diferencia existía igual y no quedaba registrada en ningún lado.
    total_cobrado = Column(Float, nullable=True)
    metodo_pago = Column(String(50), default=MetodoPagoEnum.EFECTIVO.value)
    monto_recibido = Column(Float, nullable=True)
    vuelto = Column(Float, nullable=True)
    descuento_id = Column(Integer, ForeignKey("descuentos.id"), nullable=True)
    # Guardamos la tasa y el monto de IVA vigentes al momento de la venta:
    # si mañana cambia la alícuota, los tickets viejos siguen siendo correctos.
    iva_porcentaje = Column(Float, nullable=True)
    iva_monto = Column(Float, nullable=True)
    # Identificador que genera el POS al cobrar. Permite reintentar la
    # sincronización sin registrar la venta dos veces.
    uuid_cliente = Column(String(64), unique=True, index=True, nullable=True)
    # Referencia del cobro por QR (el external_reference de Mercado Pago).
    # Es lo que permite conciliar después contra el resumen de la pasarela, y
    # es única: un mismo pago no puede respaldar dos ventas.
    pago_referencia = Column(String(64), unique=True, index=True, nullable=True)
    # COMPLETADA, ANULADA o CON_DEVOLUCION. La venta nunca se borra: anularla
    # deja el registro y suma una devolución que la referencia.
    estado = Column(String(20), default="COMPLETADA", nullable=False)
    estado_sincronizacion = Column(Boolean, default=True)

    cajero = relationship("Usuario", back_populates="ventas")
    # Sin cascada de borrado a propósito. Una venta no se borra nunca: anularla
    # deja el registro y suma una devolución que lo referencia. Con
    # `delete-orphan` puesto, el día que alguien agregara un `DELETE /ventas`
    # se llevaría en silencio los detalles y las devoluciones, y el historial
    # contable quedaría con un agujero imposible de reconstruir. Así, ese
    # borrado falla contra la clave foránea, que es lo que corresponde.
    detalles = relationship("DetalleVenta", back_populates="venta")
    devoluciones = relationship("Devolucion", back_populates="venta")


class DetalleVenta(Base):
    __tablename__ = "detalle_ventas"

    id = Column(Integer, primary_key=True, index=True)
    # Indexadas: el ticket, los reportes y el cálculo de lo devolvible se
    # buscan siempre por una de estas dos columnas.
    venta_id = Column(Integer, ForeignKey("ventas.id"), index=True, nullable=False)
    producto_id = Column(Integer, ForeignKey("productos.id"), index=True, nullable=False)
    cantidad = Column(Integer, nullable=False)
    precio_unitario = Column(Float, nullable=False)
    subtotal = Column(Float, nullable=False)

    venta = relationship("Venta", back_populates="detalles")
    producto = relationship("Producto", back_populates="detalles_venta")


class EstadoVentaEnum(str, enum.Enum):
    COMPLETADA = "COMPLETADA"
    ANULADA = "ANULADA"      # se dio de baja la venta entera
    CON_DEVOLUCION = "CON_DEVOLUCION"  # se devolvió una parte


class Devolucion(Base):
    """Devolución total o parcial de una venta.

    No se borra ni se modifica la venta original: la devolución queda como un
    registro aparte que la referencia. Así el historial es auditable y los
    reportes pueden mostrar tanto lo vendido como lo neto.
    """
    __tablename__ = "devoluciones"

    id = Column(Integer, primary_key=True, index=True)
    venta_id = Column(Integer, ForeignKey("ventas.id"), nullable=False, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    fecha_hora = Column(DateTime(timezone=True), default=ahora_utc)
    motivo = Column(String(255), nullable=True)
    total_devuelto = Column(Float, nullable=False)
    # Una anulación es una devolución de todo lo vendido. Se distingue para
    # poder mostrarla distinto y para los reportes.
    es_anulacion = Column(Boolean, default=False)
    # Cómo se le devolvió la plata al cliente: importa para el arqueo de caja
    metodo_devolucion = Column(String(50), default=MetodoPagoEnum.EFECTIVO.value)
    # De qué cajón salió la plata. Sin esto, el arqueo restaba toda devolución
    # hecha dentro de la ventana del turno, así que con dos cajas abiertas la
    # misma devolución le daba faltante a las dos.
    caja_turno_id = Column(Integer, ForeignKey("cajas_turnos.id"), nullable=True, index=True)

    venta = relationship("Venta", back_populates="devoluciones")
    detalles = relationship("DetalleDevolucion", back_populates="devolucion", cascade="all, delete-orphan")


class DetalleDevolucion(Base):
    __tablename__ = "detalle_devoluciones"

    id = Column(Integer, primary_key=True, index=True)
    devolucion_id = Column(Integer, ForeignKey("devoluciones.id"), nullable=False)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False)
    cantidad = Column(Integer, nullable=False)
    precio_unitario = Column(Float, nullable=False)
    subtotal = Column(Float, nullable=False)

    devolucion = relationship("Devolucion", back_populates="detalles")
    producto = relationship("Producto")


class EstadoPedidoEnum(str, enum.Enum):
    PENDIENTE = "PENDIENTE"   # se mandó al proveedor, todavía no llegó
    RECIBIDO = "RECIBIDO"     # llegó y se cargó al stock
    CANCELADO = "CANCELADO"   # no va a llegar


class Pedido(Base):
    """Pedido de reposición a un proveedor.

    Existe sobre todo para responder dos preguntas del día a día: qué está en
    camino (para no pedir dos veces lo mismo) y qué llegó. Al recibirlo carga
    todo el stock de una, en vez de producto por producto.
    """
    __tablename__ = "pedidos"

    id = Column(Integer, primary_key=True, index=True)
    proveedor_id = Column(Integer, ForeignKey("proveedores.id"), nullable=False, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    fecha_hora = Column(DateTime(timezone=True), default=ahora_utc)
    estado = Column(String(20), default=EstadoPedidoEnum.PENDIENTE.value, nullable=False, index=True)
    fecha_recepcion = Column(DateTime(timezone=True), nullable=True)
    notas = Column(String(500), nullable=True)

    proveedor = relationship("Proveedor", back_populates="pedidos")
    detalles = relationship("DetallePedido", back_populates="pedido", cascade="all, delete-orphan")


class DetallePedido(Base):
    __tablename__ = "detalle_pedidos"

    id = Column(Integer, primary_key=True, index=True)
    pedido_id = Column(Integer, ForeignKey("pedidos.id"), nullable=False)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False, index=True)
    cantidad = Column(Integer, nullable=False)
    # Lo que realmente llegó. Puede diferir de lo pedido: el proveedor manda
    # lo que tiene. Queda en NULL mientras el pedido está pendiente.
    cantidad_recibida = Column(Integer, nullable=True)

    pedido = relationship("Pedido", back_populates="detalles")
    producto = relationship("Producto")


class MovimientoStock(Base):
    __tablename__ = "movimientos_stock"

    id = Column(Integer, primary_key=True, index=True)
    # El historial de stock se consulta siempre filtrando por producto, por
    # rango de fechas, o por los dos. Sin índices recorría la tabla entera, que
    # es la que más rápido crece de todo el sistema: una fila por línea vendida.
    producto_id = Column(Integer, ForeignKey("productos.id"), index=True, nullable=False)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    tipo_movimiento = Column(String(50), nullable=False)
    cantidad = Column(Integer, nullable=False)
    fecha_hora = Column(DateTime(timezone=True), default=ahora_utc, index=True)
    motivo = Column(String(255), nullable=True)

    producto = relationship("Producto", back_populates="movimientos")
    encargado = relationship("Usuario", back_populates="movimientos")


class CajaTurno(Base):
    __tablename__ = "cajas_turnos"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    fecha_apertura = Column(DateTime(timezone=True), default=ahora_utc)
    monto_inicial = Column(Float, nullable=False)
    fecha_cierre = Column(DateTime(timezone=True), nullable=True)
    monto_final_declarado = Column(Float, nullable=True)
    diferencia_calculada = Column(Float, nullable=True)

    usuario = relationship("Usuario", back_populates="cajas")


class Auditoria(Base):
    """Quién cambió qué, cuándo, y de qué valor a qué valor.

    El stock ya tenía su historial, pero los pesos no: cambiar un precio, un
    descuento o el IVA no dejaba rastro. Eso permite bajar un precio, vender y
    volver a subirlo sin que nadie se entere, que es el fraude interno clásico.
    """
    __tablename__ = "auditoria"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    fecha_hora = Column(DateTime(timezone=True), default=ahora_utc, index=True)
    # Qué se tocó: "producto", "descuento", "configuracion", "usuario"…
    entidad = Column(String(40), nullable=False, index=True)
    entidad_id = Column(Integer, nullable=True)
    # Cómo quedó identificado en la pantalla, para no depender de que el
    # registro siga existiendo cuando se lea la auditoría
    entidad_nombre = Column(String(150), nullable=True)
    accion = Column(String(20), nullable=False)  # CREAR, MODIFICAR, ELIMINAR
    campo = Column(String(60), nullable=True)
    # Texto y no un tipo específico: acá conviven precios, banderas y textos
    valor_anterior = Column(Text, nullable=True)
    valor_nuevo = Column(Text, nullable=True)

    usuario = relationship("Usuario")


class IntentoLogin(Base):
    """Intentos fallidos de acceso.

    Antes vivían en un diccionario en memoria: reiniciar el servidor borraba el
    contador, y en desarrollo el servidor se reinicia solo al tocar un archivo.
    Guardados acá, el freno sobrevive al reinicio.
    """
    __tablename__ = "intentos_login"

    id = Column(Integer, primary_key=True, index=True)
    usuario = Column(String(100), nullable=False, index=True)
    fecha_hora = Column(DateTime(timezone=True), default=ahora_utc, index=True)


class Configuracion(Base):
    """Configuración del sistema como clave-valor tipado.

    Se usa una tabla genérica en lugar de columnas fijas para poder agregar
    parámetros nuevos sin migrar la base cada vez. `tipo` indica cómo castear
    el valor, que siempre se guarda como texto.
    """
    __tablename__ = "configuracion"

    clave = Column(String(60), primary_key=True, index=True)
    # Text y no String(n): el logo puede venir como data URI embebido, que es
    # mucho más largo que cualquier otro parámetro.
    valor = Column(Text, nullable=False)
    tipo = Column(String(20), nullable=False, default="string")  # string | number | boolean | json
    categoria = Column(String(40), nullable=False, default="general")
    descripcion = Column(String(255), nullable=True)


class Descuento(Base):
    __tablename__ = "descuentos"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    codigo_promocional = Column(String(50), nullable=True)  # Ej: JUBILADOS15
    tipo = Column(String(20), nullable=False)  # PORCENTAJE o MONTO
    valor = Column(Float, nullable=False)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=True)  # NULL = global
    activo = Column(Boolean, default=True)
    fecha_inicio = Column(DateTime, nullable=True)
    fecha_fin = Column(DateTime, nullable=True)
