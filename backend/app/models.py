from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.database import Base


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
    nombre = Column(String(100), nullable=False)
    pin_acceso = Column(String(255), nullable=False)  # Hash bcrypt
    rol_id = Column(Integer, default=RolEnum.CAJERO.value)
    estado = Column(Boolean, default=True)

    ventas = relationship("Venta", back_populates="cajero")
    movimientos = relationship("MovimientoStock", back_populates="encargado")
    cajas = relationship("CajaTurno", back_populates="usuario")


class Categoria(Base):
    __tablename__ = "categorias"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), unique=True, index=True, nullable=False)

    productos = relationship("Producto", back_populates="categoria")


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

    categoria = relationship("Categoria", back_populates="productos")
    detalles_venta = relationship("DetalleVenta", back_populates="producto")
    movimientos = relationship("MovimientoStock", back_populates="producto")


class Venta(Base):
    __tablename__ = "ventas"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    fecha_hora = Column(DateTime(timezone=True), server_default=func.now())
    total = Column(Float, nullable=False)
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
    estado_sincronizacion = Column(Boolean, default=True)

    cajero = relationship("Usuario", back_populates="ventas")
    detalles = relationship("DetalleVenta", back_populates="venta", cascade="all, delete-orphan")


class DetalleVenta(Base):
    __tablename__ = "detalle_ventas"

    id = Column(Integer, primary_key=True, index=True)
    venta_id = Column(Integer, ForeignKey("ventas.id"), nullable=False)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False)
    cantidad = Column(Integer, nullable=False)
    precio_unitario = Column(Float, nullable=False)
    subtotal = Column(Float, nullable=False)

    venta = relationship("Venta", back_populates="detalles")
    producto = relationship("Producto", back_populates="detalles_venta")


class MovimientoStock(Base):
    __tablename__ = "movimientos_stock"

    id = Column(Integer, primary_key=True, index=True)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    tipo_movimiento = Column(String(50), nullable=False)
    cantidad = Column(Integer, nullable=False)
    fecha_hora = Column(DateTime(timezone=True), server_default=func.now())
    motivo = Column(String(255), nullable=True)

    producto = relationship("Producto", back_populates="movimientos")
    encargado = relationship("Usuario", back_populates="movimientos")


class CajaTurno(Base):
    __tablename__ = "cajas_turnos"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    fecha_apertura = Column(DateTime(timezone=True), server_default=func.now())
    monto_inicial = Column(Float, nullable=False)
    fecha_cierre = Column(DateTime(timezone=True), nullable=True)
    monto_final_declarado = Column(Float, nullable=True)
    diferencia_calculada = Column(Float, nullable=True)

    usuario = relationship("Usuario", back_populates="cajas")


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
