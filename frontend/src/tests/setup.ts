import '@testing-library/jest-dom/vitest';
import { configure } from '@testing-library/react';
// Dexie necesita un IndexedDB; jsdom no lo trae.
import 'fake-indexeddb/auto';

/**
 * Más aire para los `waitFor`.
 *
 * Con el segundo que trae por defecto, dos tests del panel de PIN fallaban al
 * azar cuando la máquina estaba cargada —montar el Admin entero con framer-motion
 * y esperar a que resuelvan varias promesas no siempre entra en un segundo— y
 * pasaban al correrlos solos. Un CI que falla al azar deja de mirarse a la
 * tercera vez, que es peor que no tenerlo.
 *
 * No tapa nada: lo que está roto sigue fallando, sólo que ahora falla siempre.
 */
configure({ asyncUtilTimeout: 5000 });

/**
 * Almacenamiento en memoria.
 *
 * Node 22+ define su propio `localStorage` global, que queda sin definir si no
 * se arranca con `--localstorage-file`, y pisa al de jsdom. Como el POS guarda
 * ahí el token de sesión, sin esto no se puede montar nada.
 */
class AlmacenamientoEnMemoria implements Storage {
  #datos = new Map<string, string>();

  get length() { return this.#datos.size; }
  key(indice: number) { return [...this.#datos.keys()][indice] ?? null; }
  getItem(clave: string) { return this.#datos.get(clave) ?? null; }
  setItem(clave: string, valor: string) { this.#datos.set(clave, String(valor)); }
  removeItem(clave: string) { this.#datos.delete(clave); }
  clear() { this.#datos.clear(); }
}

for (const nombre of ['localStorage', 'sessionStorage'] as const) {
  if (!globalThis[nombre]) {
    Object.defineProperty(globalThis, nombre, {
      value: new AlmacenamientoEnMemoria(),
      configurable: true,
    });
  }
}

// jsdom no implementa el scroll. El POS lo usa para seguir la línea activa
// del carrito cuando se mueve con las flechas.
Element.prototype.scrollIntoView = () => {};

// El POS recarga la página al recibir un 401; en los tests eso mata la corrida.
Object.defineProperty(window, 'location', {
  value: { ...window.location, reload: () => {} },
  writable: true,
});
