/**
 * El flujo por teclado del POS.
 *
 * "Opera sin mouse" es lo primero que promete el README: el lector de barras
 * escribe en el campo de código y con Enter se encadena toda la venta. Es el
 * camino que hace el cajero cientos de veces por turno y el que más ramas
 * tiene, así que es el que conviene tener cubierto.
 *
 * Las comprobaciones van sobre los totales y no sobre el nombre del producto:
 * el nombre aparece a la vez en el catálogo, en el carrito y en el aviso, y lo
 * que decide cuánto paga el cliente es el total.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { db } from '../db';
import { UIProvider } from '../components/UIProvider';
import { ConfigProvider } from '../components/ConfigProvider';

// La cámara no existe en jsdom y el escáner monta un <video> real
vi.mock('../useCamera', () => ({ useCameraAvailability: () => 'unavailable' }));
vi.mock('html5-qrcode', () => ({
  Html5QrcodeScanner: class {
    render() {}
    clear() { return Promise.resolve(); }
    getState() { return 0; }
  },
  Html5QrcodeScannerState: { SCANNING: 2 },
  Html5QrcodeSupportedFormats: {
    EAN_13: 0, EAN_8: 1, UPC_A: 2, UPC_E: 3, CODE_128: 4, QR_CODE: 5,
  },
}));

const CAJA_ABIERTA = { id: 1, monto_inicial: 1000 };

const api = {
  getCajaEstado: vi.fn(async () => CAJA_ABIERTA),
  getProductos: vi.fn(async () => []),
  getDescuentos: vi.fn(async () => []),
  getCategorias: vi.fn(async () => []),
  getConfiguracion: vi.fn(async () => []),
  getMarca: vi.fn(async () => ({})),
  createVenta: vi.fn(async () => ({ id: 1 })),
  abrirCaja: vi.fn(async () => CAJA_ABIERTA),
  cerrarCaja: vi.fn(async () => ({})),
};
vi.mock('../api', () => ({ api: new Proxy({}, { get: (_t, k) => (api as never)[k] }) }));

/** Producto de $1000, el único del catálogo local. */
const PRODUCTO = {
  id: 7,
  codigo_barras: '7790000000001',
  nombre: 'Yerba Playadito',
  precio_venta: 1000,
  stock_actual: 50,
};

async function montarPOS() {
  const { default: POS } = await import('../App');
  return render(
    <UIProvider>
      <ConfigProvider>
        <POS />
      </ConfigProvider>
    </UIProvider>,
  );
}

/** Simula el lector USB: escribe el código de corrido y cierra con Enter. */
async function pasarPorElLector(usuario: ReturnType<typeof userEvent.setup>, codigo: string) {
  const campo = await screen.findByPlaceholderText(/código/i);
  await usuario.click(campo);
  await usuario.keyboard(`${codigo}{Enter}`);
}

/** Carrito vacío: el total se muestra igual, en cero. */
const CARRITO_VACIO = '$0.00';

/**
 * Total a cobrar según la pantalla.
 *
 * No sirve buscar el importe suelto: el catálogo muestra el precio del
 * producto igual, así que `$1000.00` aparece en pantalla aunque no se haya
 * cargado nada al carrito.
 */
function totalACobrar(): string | null {
  const etiqueta = screen.queryByText('Total a Pagar');
  if (!etiqueta?.parentElement) return null;
  return etiqueta.parentElement.textContent!.replace('Total a Pagar', '').trim();
}

beforeEach(async () => {
  localStorage.clear();
  localStorage.setItem('token', 'token-de-prueba');
  await db.productos.clear();
  await db.ventasOffline.clear();
  await db.productos.put(PRODUCTO as never);
});

afterEach(cleanup);

describe('POS: la venta se encadena con Enter', () => {
  it('el lector carga el producto y el total lo refleja', async () => {
    const usuario = userEvent.setup();
    await montarPOS();
    expect(totalACobrar()).toBe(CARRITO_VACIO);  // el carrito arranca vacío

    await pasarPorElLector(usuario, PRODUCTO.codigo_barras);

    await waitFor(() => expect(totalACobrar()).toBe('$1000.00'));
  });

  it('leer dos veces el mismo código suma cantidad', async () => {
    const usuario = userEvent.setup();
    await montarPOS();

    await pasarPorElLector(usuario, PRODUCTO.codigo_barras);
    await waitFor(() => expect(totalACobrar()).toBe('$1000.00'));
    await pasarPorElLector(usuario, PRODUCTO.codigo_barras);

    await waitFor(() => expect(totalACobrar()).toBe('$2000.00'));
  });

  it('un código que no existe avisa y no toca el carrito', async () => {
    const usuario = userEvent.setup();
    await montarPOS();

    await pasarPorElLector(usuario, '0000000000000');

    expect(await screen.findByText(/no encontrado/i)).toBeInTheDocument();
    expect(totalACobrar()).toBe(CARRITO_VACIO);
  });

  it('la venta cobrada queda guardada en el equipo aunque no haya servidor', async () => {
    // Es la promesa central del producto: se sigue vendiendo sin red
    const usuario = userEvent.setup();
    await montarPOS();

    await pasarPorElLector(usuario, PRODUCTO.codigo_barras);
    await waitFor(() => expect(totalACobrar()).toBe('$1000.00'));

    // Campo vacío + Enter abre el cobro; abajo se elige el método y se confirma
    await usuario.keyboard('{Enter}');
    await screen.findByText('Tarjeta');  // el modal de cobro ya está abierto
    await usuario.keyboard('{ArrowDown}');  // de EFECTIVO a TARJETA
    await usuario.keyboard('{Enter}');

    await waitFor(async () => {
      expect(await db.ventasOffline.count()).toBe(1);
    });
    const [guardada] = await db.ventasOffline.toArray();
    expect(guardada.total).toBe(1000);
    expect(guardada.metodo_pago).toBe('TARJETA');
    // Sin sincronizar todavía: el servidor no contestó
    expect(guardada.estado_sincronizacion).toBe(false);
  });

  it('el carrito descuenta el stock local para que la próxima lectura lo vea', async () => {
    const usuario = userEvent.setup();
    await montarPOS();

    await pasarPorElLector(usuario, PRODUCTO.codigo_barras);
    await waitFor(() => expect(totalACobrar()).toBe('$1000.00'));
    await usuario.keyboard('{Enter}');
    await usuario.keyboard('{ArrowDown}');
    await usuario.keyboard('{Enter}');

    await waitFor(async () => {
      const local = await db.productos.get(PRODUCTO.id);
      expect(local?.stock_actual).toBe(49);
    });
  });
});
