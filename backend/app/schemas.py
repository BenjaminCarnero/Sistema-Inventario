from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import datetime


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None
    rol: Optional[int] = None


class UsuarioBase(BaseModel):
    nombre: str
    rol_id: int
    estado: bool = True


class UsuarioCreate(UsuarioBase):
    pin_acceso: str


class Usuario(UsuarioBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class CategoriaBase(BaseModel):
    nombre: str


class CategoriaCreate(CategoriaBase):
    pass


class Categoria(CategoriaBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class ProveedorBase(BaseModel):
    nombre: str
    telefono: Optional[str] = Field(default=None, max_length=30)
    email: Optional[str] = Field(default=None, max_length=150)
    cuit: Optional[str] = Field(default=None, max_length=20)
    notas: Optional[str] = Field(default=None, max_length=500)
    activo: bool = True


class ProveedorCreate(ProveedorBase):
    pass


class Proveedor(ProveedorBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class ProductoBase(BaseModel):
    codigo_barras: str
    nombre: str
    precio_venta: float
    costo: float
    categoria_id: Optional[int] = None
    imagen_url: Optional[str] = None
    proveedor_id: Optional[int] = None
    cantidad_pedido_habitual: Optional[int] = Field(default=None, ge=0, le=1_000_000)


class ProductoCreate(ProductoBase):
    stock_actual: int = 0


class ProductoUpdate(BaseModel):
    codigo_barras: Optional[str] = None
    nombre: Optional[str] = None
    precio_venta: Optional[float] = None
    costo: Optional[float] = None
    stock_actual: Optional[int] = None
    categoria_id: Optional[int] = None
    imagen_url: Optional[str] = None
    proveedor_id: Optional[int] = None
    cantidad_pedido_habitual: Optional[int] = Field(default=None, ge=0, le=1_000_000)


class Producto(ProductoBase):
    id: int
    stock_actual: int
    # El costo es el margen del negocio. Viaja vacío para el cajero, que no
    # tiene por qué conocerlo: el catálogo del POS ya lo descartaba al
    # guardarlo en el equipo, pero la API lo entregaba igual.
    costo: Optional[float] = None
    model_config = ConfigDict(from_attributes=True)


class DetalleVentaBase(BaseModel):
    producto_id: int
    cantidad: int
    precio_unitario: float


class DetalleVentaCreate(DetalleVentaBase):
    # Las restricciones van sólo en el alta: al leer ventas históricas no se
    # deben rechazar filas que se hayan guardado antes de estas validaciones.
    cantidad: int = Field(gt=0, le=10_000)
    # Informativo: el servidor cobra siempre con el precio del catálogo.
    precio_unitario: float = Field(ge=0)


class DetalleVenta(DetalleVentaBase):
    id: int
    venta_id: int
    subtotal: float
    model_config = ConfigDict(from_attributes=True)


class DescuentoBase(BaseModel):
    nombre: str
    codigo_promocional: Optional[str] = None
    tipo: str  # PORCENTAJE o MONTO
    valor: float
    producto_id: Optional[int] = None
    activo: bool = True
    fecha_inicio: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None


class DescuentoCreate(DescuentoBase):
    pass


class DescuentoUpdate(BaseModel):
    nombre: Optional[str] = None
    codigo_promocional: Optional[str] = None
    tipo: Optional[str] = None
    valor: Optional[float] = None
    producto_id: Optional[int] = None
    activo: Optional[bool] = None
    fecha_inicio: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None


class Descuento(DescuentoBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class VentaBase(BaseModel):
    metodo_pago: str
    monto_recibido: Optional[float] = None
    vuelto: Optional[float] = None
    descuento_id: Optional[int] = None
    iva_porcentaje: Optional[float] = None
    iva_monto: Optional[float] = None
    uuid_cliente: Optional[str] = Field(default=None, max_length=64)
    estado: str = "COMPLETADA"
    estado_sincronizacion: bool = True


class VentaCreate(VentaBase):
    detalles: List[DetalleVentaCreate]


class Venta(VentaBase):
    id: int
    usuario_id: int
    fecha_hora: datetime
    total: float
    detalles: List[DetalleVenta]
    model_config = ConfigDict(from_attributes=True)


class DetalleDevolucionCreate(BaseModel):
    producto_id: int
    cantidad: int = Field(gt=0, le=10_000)


class DevolucionCreate(BaseModel):
    """Devolución de una venta.

    Con `detalles` vacío se devuelve todo lo que quede pendiente, que es el
    caso de una anulación.
    """
    motivo: Optional[str] = Field(default=None, max_length=255)
    metodo_devolucion: str = "EFECTIVO"
    detalles: List[DetalleDevolucionCreate] = []


class DetalleDevolucion(BaseModel):
    id: int
    producto_id: int
    cantidad: int
    precio_unitario: float
    subtotal: float
    producto_nombre: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class Devolucion(BaseModel):
    id: int
    venta_id: int
    usuario_id: int
    fecha_hora: datetime
    motivo: Optional[str] = None
    total_devuelto: float
    es_anulacion: bool
    metodo_devolucion: str
    detalles: List[DetalleDevolucion]
    usuario_nombre: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class ProductoDevolvible(BaseModel):
    """Cuánto queda por devolver de cada producto de una venta."""
    producto_id: int
    producto_nombre: str
    precio_unitario: float
    cantidad_vendida: int
    cantidad_devuelta: int
    cantidad_disponible: int


class MovimientoStockCreate(BaseModel):
    producto_id: int
    # Positiva para INGRESO; para AJUSTE es el stock que contaste, y contar
    # cero es un resultado válido (se agotó y el sistema no se enteró).
    cantidad: int = Field(ge=0, le=1_000_000)
    tipo_movimiento: str  # INGRESO o AJUSTE
    motivo: Optional[str] = Field(default=None, max_length=255)


class MovimientoStockOut(BaseModel):
    id: int
    producto_id: int
    usuario_id: int
    tipo_movimiento: str
    cantidad: int
    fecha_hora: datetime
    motivo: Optional[str] = None
    producto_nombre: Optional[str] = None
    usuario_nombre: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class CajaTurnoCreate(BaseModel):
    monto_inicial: float


class CajaTurnoClose(BaseModel):
    monto_final_declarado: float


class CajaTurno(BaseModel):
    id: int
    usuario_id: int
    fecha_apertura: datetime
    monto_inicial: float
    fecha_cierre: Optional[datetime] = None
    monto_final_declarado: Optional[float] = None
    diferencia_calculada: Optional[float] = None
    model_config = ConfigDict(from_attributes=True)


class KpiResponse(BaseModel):
    ventas_hoy_local: float
    cantidad_ventas_hoy: int
    metodo_pago_preferido: str


class TopProducto(BaseModel):
    id: int
    nombre: str
    cantidad_vendida: int
    total_recaudado: float


class CajaReporte(CajaTurno):
    cajero_nombre: str
    total_ventas_turno: float


class DetalleVentaReporte(DetalleVenta):
    producto_nombre: str


class VentaReporte(Venta):
    detalles: List[DetalleVentaReporte]
    cajero_nombre: Optional[str] = None
    descuento_nombre: Optional[str] = None
    # Cuánto de esta venta se devolvió, para poder mostrar el neto
    total_devuelto: float = 0.0


class ProductoStockBajo(BaseModel):
    id: int
    nombre: str
    codigo_barras: str
    stock_actual: int
    umbral: int


class RentabilidadProducto(BaseModel):
    id: int
    nombre: str
    cantidad_vendida: int
    total_recaudado: float
    costo_total: float
    ganancia: float
    margen_pct: float


# ---- Reposición: sugerencia y pedidos a proveedores -------------------------

class ItemAReponer(BaseModel):
    """Un producto que hay que reponer, con la cantidad ya propuesta."""
    producto_id: int
    producto_nombre: str
    codigo_barras: str
    stock_actual: int
    # Lo que el dueño configuró como "de esto siempre pido tanto". Si no hay
    # nada cargado, la pantalla deja el campo en blanco: mejor vacío que un
    # número inventado.
    cantidad_sugerida: Optional[int] = None
    # Unidades de este producto que ya están en camino en otro pedido, para
    # no pedir dos veces lo mismo
    ya_pedido: int = 0


class GrupoAReponer(BaseModel):
    """Los faltantes de un mismo proveedor. El pedido se arma por proveedor."""
    proveedor_id: Optional[int] = None
    proveedor_nombre: Optional[str] = None
    proveedor_telefono: Optional[str] = None
    items: List[ItemAReponer]


class DetallePedidoCreate(BaseModel):
    producto_id: int
    cantidad: int = Field(gt=0, le=1_000_000)


class PedidoCreate(BaseModel):
    proveedor_id: int
    notas: Optional[str] = Field(default=None, max_length=500)
    detalles: List[DetallePedidoCreate]


class DetallePedidoRecibir(BaseModel):
    producto_id: int
    # Lo que realmente llegó: el proveedor manda lo que tiene
    cantidad_recibida: int = Field(ge=0, le=1_000_000)


class PedidoRecibir(BaseModel):
    detalles: List[DetallePedidoRecibir] = []


class DetallePedido(BaseModel):
    id: int
    producto_id: int
    producto_nombre: Optional[str] = None
    cantidad: int
    cantidad_recibida: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)


class Pedido(BaseModel):
    id: int
    proveedor_id: int
    proveedor_nombre: Optional[str] = None
    proveedor_telefono: Optional[str] = None
    usuario_id: int
    usuario_nombre: Optional[str] = None
    fecha_hora: datetime
    estado: str
    fecha_recepcion: Optional[datetime] = None
    notas: Optional[str] = None
    detalles: List[DetallePedido]
    model_config = ConfigDict(from_attributes=True)


# ---- Auditoría y respaldos -------------------------------------------------

class EntradaAuditoria(BaseModel):
    id: int
    usuario_id: Optional[int] = None
    usuario_nombre: Optional[str] = None
    fecha_hora: datetime
    entidad: str
    entidad_id: Optional[int] = None
    entidad_nombre: Optional[str] = None
    accion: str
    campo: Optional[str] = None
    valor_anterior: Optional[str] = None
    valor_nuevo: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class Respaldo(BaseModel):
    nombre: str
    bytes: int
    fecha_hora: datetime
