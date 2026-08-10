/**
 * Exportación a Excel de las ventas de un período.
 *
 * La librería se carga con import dinámico para que no entre en el bundle
 * inicial: sólo se descarga cuando el admin realmente exporta.
 */

interface DetalleVenta {
  producto_id: number;
  producto_nombre: string;
  cantidad: number;
  precio_unitario: number;
  subtotal: number;
}

interface VentaReporte {
  id: number;
  fecha_hora: string;
  cajero_nombre?: string | null;
  metodo_pago: string;
  monto_recibido?: number | null;
  vuelto?: number | null;
  descuento_nombre?: string | null;
  total: number;
  detalles: DetalleVenta[];
}

const HEADER = { fontWeight: 'bold' as const, backgroundColor: '#8251EE', color: '#FFFFFF' };

function formatearFecha(iso: string) {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleString('es-AR');
}

export async function exportarVentasExcel(
  ventas: VentaReporte[],
  desde: string,
  hasta: string
) {
  const { default: writeXlsxFile } = await import('write-excel-file/browser');

  // Hoja 1: una fila por venta
  const hojaVentas = [
    [
      { value: 'Venta #', ...HEADER },
      { value: 'Fecha y hora', ...HEADER },
      { value: 'Cajero', ...HEADER },
      { value: 'Método de pago', ...HEADER },
      { value: 'Descuento', ...HEADER },
      { value: 'Recibido', ...HEADER },
      { value: 'Vuelto', ...HEADER },
      { value: 'Total', ...HEADER },
    ],
    ...ventas.map(v => [
      { type: Number, value: v.id },
      { type: String, value: formatearFecha(v.fecha_hora) },
      { type: String, value: v.cajero_nombre || '—' },
      { type: String, value: v.metodo_pago },
      { type: String, value: v.descuento_nombre || '—' },
      { type: Number, value: v.monto_recibido ?? null, format: '#,##0.00' },
      { type: Number, value: v.vuelto ?? null, format: '#,##0.00' },
      { type: Number, value: v.total, format: '#,##0.00' },
    ]),
  ];

  // Hoja 2: una fila por producto vendido, para tablas dinámicas
  const hojaDetalle = [
    [
      { value: 'Venta #', ...HEADER },
      { value: 'Fecha y hora', ...HEADER },
      { value: 'Cajero', ...HEADER },
      { value: 'Producto', ...HEADER },
      { value: 'Cantidad', ...HEADER },
      { value: 'Precio unitario', ...HEADER },
      { value: 'Subtotal', ...HEADER },
    ],
    ...ventas.flatMap(v =>
      v.detalles.map(d => [
        { type: Number, value: v.id },
        { type: String, value: formatearFecha(v.fecha_hora) },
        { type: String, value: v.cajero_nombre || '—' },
        { type: String, value: d.producto_nombre },
        { type: Number, value: d.cantidad },
        { type: Number, value: d.precio_unitario, format: '#,##0.00' },
        { type: Number, value: d.subtotal, format: '#,##0.00' },
      ])
    ),
  ];

  // En el navegador la librería devuelve { toBlob, toFile }; toFile dispara la descarga.
  await writeXlsxFile([
    {
      data: hojaVentas as any,
      sheet: 'Ventas',
      columns: [10, 22, 18, 18, 22, 14, 14, 14].map(width => ({ width })),
    },
    {
      data: hojaDetalle as any,
      sheet: 'Detalle por producto',
      columns: [10, 22, 18, 34, 12, 16, 14].map(width => ({ width })),
    },
  ]).toFile(`ventas_${desde}_a_${hasta}.xlsx`);
}

interface MovimientoStock {
  id: number;
  fecha_hora: string;
  producto_nombre: string;
  usuario_nombre: string;
  tipo_movimiento: string;
  cantidad: number;
  motivo?: string | null;
}

const ETIQUETA_TIPO: Record<string, string> = {
  INGRESO: 'Entrada',
  EGRESO: 'Salida',
  AJUSTE: 'Ajuste',
};

export async function exportarMovimientosExcel(
  movimientos: MovimientoStock[],
  desde: string,
  hasta: string
) {
  const { default: writeXlsxFile } = await import('write-excel-file/browser');

  const filas = [
    [
      { value: 'Fecha y hora', ...HEADER },
      { value: 'Producto', ...HEADER },
      { value: 'Tipo', ...HEADER },
      { value: 'Cantidad', ...HEADER },
      { value: 'Usuario', ...HEADER },
      { value: 'Motivo', ...HEADER },
    ],
    ...movimientos.map(m => [
      { type: String, value: formatearFecha(m.fecha_hora) },
      { type: String, value: m.producto_nombre },
      { type: String, value: ETIQUETA_TIPO[m.tipo_movimiento] || m.tipo_movimiento },
      // La salida va en negativo para que la columna se pueda sumar directo.
      // El ajuste queda en positivo: es la diferencia encontrada, y su
      // dirección está en el motivo.
      { type: Number, value: m.tipo_movimiento === 'EGRESO' ? -m.cantidad : m.cantidad },
      { type: String, value: m.usuario_nombre },
      { type: String, value: m.motivo || '—' },
    ]),
  ];

  await writeXlsxFile([
    {
      data: filas as any,
      sheet: 'Movimientos de stock',
      columns: [22, 34, 12, 12, 18, 46].map(width => ({ width })),
    },
  ]).toFile(`movimientos_stock_${desde}_a_${hasta}.xlsx`);
}
