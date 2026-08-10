import { db, type ProductoLocal } from './db';

/**
 * Deja el catálogo local en el equipo con sólo lo necesario para vender.
 *
 * El backend devuelve también el `costo` de cada producto. Ese dato es el
 * margen del negocio y no tiene por qué quedar guardado en la tablet o la PC
 * del cajero, así que se descarta antes de escribir en IndexedDB.
 */
export function paraCatalogoLocal(producto: any): ProductoLocal {
  return {
    id: producto.id,
    codigo_barras: producto.codigo_barras,
    nombre: producto.nombre,
    precio_venta: producto.precio_venta,
    stock_actual: producto.stock_actual,
    imagen_url: producto.imagen_url ?? null,
    categoria_id: producto.categoria_id ?? null,
    proveedor_id: producto.proveedor_id ?? null,
  };
}

/** Reemplaza el catálogo local por el del servidor. Devuelve cuántos quedaron. */
export async function sincronizarCatalogo(productosDelServidor: any[]) {
  const limpios = productosDelServidor.map(paraCatalogoLocal);
  await db.transaction('rw', db.productos, async () => {
    await db.productos.clear();
    await db.productos.bulkAdd(limpios);
  });
  return limpios.length;
}
