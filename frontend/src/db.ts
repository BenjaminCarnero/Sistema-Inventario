import Dexie, { type Table } from 'dexie';

export interface ProductoLocal {
  id: number;
  codigo_barras: string;
  nombre: string;
  precio_venta: number;
  stock_actual: number;
  imagen_url?: string | null;
  categoria_id?: number | null;
  proveedor_id?: number | null;
  // El costo NO se guarda acá a propósito: el catálogo local queda en el
  // equipo del cajero y expondría el margen del negocio. Para vender alcanza
  // con el precio de venta.
}

export interface VentaOffline {
  id?: number;
  /** Identificador propio de esta venta: evita duplicarla al reintentar la sincronización. */
  uuid_cliente?: string;
  metodo_pago: string;
  /** Referencia del cobro por QR. El servidor la usa para confirmar el pago. */
  pago_referencia?: string;
  /**
   * Motivo por el que el servidor rechazó esta venta de forma definitiva (por
   * ejemplo, un cobro por QR que nunca se acreditó). Mientras esté cargado, la
   * venta se saltea al sincronizar: si se reintentara, trabaría para siempre a
   * las que vienen atrás en la cola.
   */
  rechazo?: string;
  /**
   * Envíos fallidos con motivo reintentable. La búsqueda de pagos de Mercado
   * Pago es consistente en diferido: un cobro que existe puede tardar en
   * aparecer, así que un "no está acreditado" no se toma como definitivo a la
   * primera. Pasado el tope, la venta se marca con `rechazo`.
   */
  intentos?: number;
  monto_recibido?: number;
  vuelto?: number;
  descuento_id?: number | null;
  descuento_nombre?: string | null;
  subtotal_bruto?: number;
  iva_porcentaje?: number | null;
  iva_monto?: number | null;
  iva_incluido?: boolean;
  iva_nombre?: string;
  total: number;
  detalles: {
    producto_id: number;
    producto_nombre?: string;
    cantidad: number;
    precio_unitario: number;
  }[];
  estado_sincronizacion: boolean;
  fecha_hora_local: string;
}

export class ApplifyDB extends Dexie {
  productos!: Table<ProductoLocal, number>;
  ventasOffline!: Table<VentaOffline, number>;

  constructor() {
    super('ApplifyDB');
    this.version(1).stores({
      productos: 'id, codigo_barras, nombre',
      ventasOffline: '++id, estado_sincronizacion'
    });
  }
}

export const db = new ApplifyDB();
