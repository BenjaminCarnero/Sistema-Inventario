import Dexie, { type Table } from 'dexie';

export interface ProductoLocal {
  id: number;
  codigo_barras: string;
  nombre: string;
  precio_venta: number;
  stock_actual: number;
  imagen_url?: string | null;
  // El costo NO se guarda acá a propósito: el catálogo local queda en el
  // equipo del cajero y expondría el margen del negocio. Para vender alcanza
  // con el precio de venta.
}

export interface VentaOffline {
  id?: number;
  /** Identificador propio de esta venta: evita duplicarla al reintentar la sincronización. */
  uuid_cliente?: string;
  metodo_pago: string;
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
