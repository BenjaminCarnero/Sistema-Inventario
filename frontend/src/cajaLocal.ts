/**
 * Memoria local del turno de caja.
 *
 * Sin esto, un corte de internet dejaba el POS inutilizable: `getCajaEstado()`
 * fallaba, el POS asumía que no había turno abierto y tapaba la pantalla con
 * "Apertura de Caja" aunque el cajero tuviera el turno abierto en el servidor.
 *
 * La caja abierta se guarda en el equipo y se usa como respaldo mientras no
 * haya conexión. Es información de trabajo, no una credencial: el servidor
 * sigue siendo el que manda cuando vuelve la red.
 */

const CLAVE = 'applify_caja_abierta';

export interface CajaLocal {
  id: number;
  usuario_id: number;
  fecha_apertura: string;
  monto_inicial: number;
  /** true si se abrió sin conexión y todavía no se registró en el servidor. */
  pendiente_de_sincronizar?: boolean;
}

export function recordarCaja(caja: CajaLocal | null) {
  try {
    if (caja) localStorage.setItem(CLAVE, JSON.stringify(caja));
    else localStorage.removeItem(CLAVE);
  } catch {
    /* almacenamiento lleno o bloqueado: se sigue trabajando en memoria */
  }
}

export function cajaRecordada(): CajaLocal | null {
  try {
    const bruto = localStorage.getItem(CLAVE);
    return bruto ? (JSON.parse(bruto) as CajaLocal) : null;
  } catch {
    return null;
  }
}

/** Turno provisorio para poder vender ya, hasta que el servidor lo registre. */
export function cajaProvisoria(usuarioId: number, montoInicial: number): CajaLocal {
  return {
    // Negativo para que no se confunda con un id real del servidor
    id: -Date.now(),
    usuario_id: usuarioId,
    fecha_apertura: new Date().toISOString(),
    monto_inicial: montoInicial,
    pendiente_de_sincronizar: true,
  };
}

export function esProvisoria(caja: { id: number } | null | undefined) {
  return !!caja && caja.id < 0;
}
