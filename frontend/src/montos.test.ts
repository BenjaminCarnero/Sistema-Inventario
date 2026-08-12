import { describe, it, expect } from 'vitest';
import { sanitizarMonto } from './montos';

const TOPE = 1_000_000;

/**
 * Lo que se teclea acá termina en el vuelto que se le da a un cliente, así que
 * lo que importa es que nunca deje pasar un número imposible.
 */
describe('sanitizarMonto', () => {
  it('acepta un importe normal', () => {
    expect(sanitizarMonto('1500', '', TOPE)).toEqual({ texto: '1500', valor: 1500 });
  });

  it('acepta coma o punto como decimal', () => {
    expect(sanitizarMonto('1500,50', '', TOPE).valor).toBe(1500.5);
    expect(sanitizarMonto('1500.50', '', TOPE).valor).toBe(1500.5);
  });

  it('el campo vacío es válido: todavía no escribió nada', () => {
    expect(sanitizarMonto('', '999', TOPE)).toEqual({ texto: '', valor: 0 });
  });

  it('no deja pasar negativos', () => {
    const r = sanitizarMonto('-500', '100', TOPE);
    expect(r.texto).toBe('100');
    expect(r.rechazo).toBe('formato');
  });

  it('no deja pasar notación científica', () => {
    // `<input type="number">` la acepta y da importes absurdos
    expect(sanitizarMonto('1e10', '100', TOPE).rechazo).toBe('formato');
  });

  it('no deja pasar más de dos decimales', () => {
    expect(sanitizarMonto('10,999', '10', TOPE).rechazo).toBe('formato');
  });

  it('no deja pasar letras ni separadores de miles', () => {
    expect(sanitizarMonto('abc', '10', TOPE).rechazo).toBe('formato');
    expect(sanitizarMonto('1.000.000', '10', TOPE).rechazo).toBe('formato');
  });

  it('frena en el tope configurado', () => {
    const r = sanitizarMonto('2000000', '100', TOPE);
    expect(r.texto).toBe('100');
    expect(r.rechazo).toBe('tope');
  });

  it('al rechazar deja el texto anterior tal cual', () => {
    // La tecla "no entra": es menos confuso que ver el número corregido solo
    const r = sanitizarMonto('50x', '1500,25', TOPE);
    expect(r.texto).toBe('1500,25');
    expect(r.valor).toBe(1500.25);
  });

  it('deja escribir el decimal a medio tipear', () => {
    // Al teclear "10," todavía no hay decimales, y no puede rebotar
    expect(sanitizarMonto('10,', '10', TOPE).rechazo).toBeUndefined();
  });
});
