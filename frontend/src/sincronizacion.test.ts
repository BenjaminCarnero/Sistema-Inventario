import { describe, it, expect } from 'vitest';
import { clasificarFalloDeEnvio, MAX_REINTENTOS_COBRO } from './sincronizacion';

/**
 * De esto depende que no se pierda una venta ya cobrada. La versión anterior
 * metía todo 4xx en la misma bolsa y perdía ventas reales.
 */
describe('clasificarFalloDeEnvio', () => {
  it('un 409 significa que el servidor ya la tiene, no que la rechazó', () => {
    expect(clasificarFalloDeEnvio(409, 0)).toBe('registrada');
  });

  it('una sesión vencida no dice nada sobre la venta', () => {
    // El caso que perdía ventas: token vencido a mitad de turno con la cola llena
    expect(clasificarFalloDeEnvio(401, 0)).toBe('cortar');
    expect(clasificarFalloDeEnvio(403, 0)).toBe('cortar');
  });

  it('el freno al login tampoco', () => {
    expect(clasificarFalloDeEnvio(429, 0)).toBe('cortar');
  });

  it('un corte de red o un servidor caído se reintentan enteros', () => {
    expect(clasificarFalloDeEnvio(undefined, 0)).toBe('cortar');
    expect(clasificarFalloDeEnvio(500, 0)).toBe('cortar');
    expect(clasificarFalloDeEnvio(503, 0)).toBe('cortar');
  });

  it('un cobro que todavía no aparece se reintenta un rato', () => {
    // Mercado Pago indexa los pagos en diferido: puede tardar en verse
    expect(clasificarFalloDeEnvio(402, 0)).toBe('reintentar');
    expect(clasificarFalloDeEnvio(402, MAX_REINTENTOS_COBRO - 1)).toBe('reintentar');
  });

  it('pero no para siempre', () => {
    expect(clasificarFalloDeEnvio(402, MAX_REINTENTOS_COBRO)).toBe('rechazada');
    expect(clasificarFalloDeEnvio(402, MAX_REINTENTOS_COBRO + 10)).toBe('rechazada');
  });

  it('una venta mal armada no mejora reintentándola', () => {
    expect(clasificarFalloDeEnvio(400, 0)).toBe('rechazada');
    expect(clasificarFalloDeEnvio(404, 0)).toBe('rechazada');
    expect(clasificarFalloDeEnvio(422, 0)).toBe('rechazada');
  });

  it('nunca devuelve rechazada por algo que no sea culpa de la venta', () => {
    for (const status of [401, 403, 429, 500, 502, 503, undefined]) {
      expect(clasificarFalloDeEnvio(status, 99)).not.toBe('rechazada');
    }
  });
});
