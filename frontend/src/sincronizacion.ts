/**
 * Decisiones sobre la cola de ventas offline.
 *
 * Vive aparte del componente porque es la lógica de la que depende que no se
 * pierda una venta cobrada, y así se puede probar sin montar el POS entero.
 */

/** Envíos fallidos que se toleran antes de dar una venta por perdida. */
export const MAX_REINTENTOS_COBRO = 5;

export type DestinoDeVenta = 'registrada' | 'rechazada' | 'reintentar' | 'cortar';

/**
 * Qué hacer con una venta que el servidor no aceptó.
 *
 * Tratar todo 4xx como definitivo pierde ventas reales: una sesión vencida
 * (401) o el freno al login (429) no dicen nada sobre la venta en sí, y un 409
 * significa lo contrario de un rechazo —el servidor ya la tiene—.
 *
 * - `registrada`: ya está en el servidor. Se borra de la cola local.
 * - `cortar`: el problema no es de esta venta y les va a pasar a las que
 *   siguen. Se abandona la vuelta y se reintenta todo más adelante.
 * - `reintentar`: puede que ande en el próximo intento. Se deja en la cola.
 * - `rechazada`: el servidor la va a rechazar siempre. Se marca para que
 *   alguien la mire y no se reintenta más.
 */
export function clasificarFalloDeEnvio(
  status: number | undefined,
  intentos: number,
): DestinoDeVenta {
  // El servidor ya la registró (choque de uuid o de referencia de cobro)
  if (status === 409) return 'registrada';

  // Sin código es un corte de red. 5xx es el servidor. 401/403 son de sesión y
  // 429 es del freno: ninguno tiene que ver con esta venta.
  if (!status || status >= 500 || status === 401 || status === 403 || status === 429) {
    return 'cortar';
  }

  // La búsqueda de pagos de Mercado Pago es consistente en diferido: un cobro
  // que existe puede tardar en aparecer, y el POS manda la venta apenas lo ve
  // acreditado. Darlo por perdido en el primer intento tira plata cobrada.
  if (status === 402) return intentos < MAX_REINTENTOS_COBRO ? 'reintentar' : 'rechazada';

  // 400, 404, 422: la venta está mal armada y va a estarlo siempre.
  return 'rechazada';
}
