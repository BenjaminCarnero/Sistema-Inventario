/**
 * Saneo de los campos de dinero del POS.
 *
 * Un `<input type="number">` acepta cualquier cosa: notación científica,
 * cientos de dígitos, decimales infinitos y valores negativos. En una caja eso
 * termina en importes imposibles y vueltos absurdos, así que se filtra lo que
 * el cajero puede escribir en lugar de corregirlo después.
 */

export interface ResultadoMonto {
  /** Texto que debe quedar en el campo. */
  texto: string;
  /** Valor numérico correspondiente (0 si está vacío). */
  valor: number;
  /** Motivo por el que se rechazó lo tecleado, si corresponde. */
  rechazo?: string;
}

/**
 * Filtra lo tecleado en un campo de dinero.
 *
 * Si la nueva entrada no es válida, devuelve el texto anterior sin cambios:
 * en la práctica la tecla "no entra", que es menos confuso que ver el número
 * corregido solo.
 */
export function sanitizarMonto(entrada: string, anterior: string, tope: number): ResultadoMonto {
  const texto = entrada.trim();

  // Campo vacío es válido: significa "todavía no escribió nada"
  if (texto === '') return { texto: '', valor: 0 };

  // Sólo dígitos con hasta dos decimales. Bloquea el signo menos, la "e" de la
  // notación científica y los separadores de miles.
  if (!/^\d*(?:[.,]\d{0,2})?$/.test(texto)) {
    return { texto: anterior, valor: Number(anterior.replace(',', '.')) || 0, rechazo: 'formato' };
  }

  const valor = Number(texto.replace(',', '.'));
  if (!Number.isFinite(valor)) {
    return { texto: anterior, valor: Number(anterior.replace(',', '.')) || 0, rechazo: 'formato' };
  }

  if (valor > tope) {
    return {
      texto: anterior,
      valor: Number(anterior.replace(',', '.')) || 0,
      rechazo: 'tope',
    };
  }

  return { texto, valor };
}

/** Formatea el tope para mostrarlo en los mensajes. */
export function formatearTope(tope: number, simbolo: string) {
  return `${simbolo}${tope.toLocaleString('es-AR')}`;
}
