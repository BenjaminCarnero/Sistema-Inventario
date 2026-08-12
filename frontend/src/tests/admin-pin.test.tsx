/**
 * Cambio y reinicio de PIN desde el backoffice.
 *
 * Los endpoints existieron un rato sin nada que los llamara, así que la
 * funcionalidad era inalcanzable para un usuario real. Estos tests fijan que la
 * pantalla siga conectada a la API.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { UIProvider } from '../components/UIProvider';
import { ConfigProvider } from '../components/ConfigProvider';

const USUARIOS = [
  { id: 1, nombre: 'jefe', rol_id: 1, estado: true },
  { id: 2, nombre: 'ana', rol_id: 3, estado: true },
];

const cambiarMiPin = vi.fn(async () => {});
const reiniciarPinUsuario = vi.fn(async () => {});

/**
 * El panel pide muchas cosas al arrancar y ninguna hace falta acá. El Proxy
 * responde una lista vacía a cualquier método que no esté declarado, así el
 * test no se rompe cada vez que el panel suma una llamada.
 */
const api: Record<string, unknown> = {
  getUsuarios: vi.fn(async () => USUARIOS),
  cambiarMiPin,
  reiniciarPinUsuario,
  getConfiguracion: vi.fn(async () => []),
  getMarca: vi.fn(async () => ({})),
};
vi.mock('../api', () => ({
  api: new Proxy({}, {
    get: (_t, clave: string) => api[clave] ?? (async () => []),
  }),
}));

/** Token con el payload que lee `getUsername()`; la firma no se valida acá. */
function tokenDe(usuario: string, rol: number) {
  const payload = btoa(JSON.stringify({ sub: usuario, rol }));
  return `cabecera.${payload}.firma`;
}

async function montarPanelDeUsuarios(usuario: ReturnType<typeof userEvent.setup>) {
  const { default: Admin } = await import('../Admin');
  render(
    <UIProvider>
      <ConfigProvider>
        <Admin />
      </ConfigProvider>
    </UIProvider>,
  );
  // Hay dos barras de navegación, la de escritorio y la de móvil: alcanza con
  // la primera, las dos mueven el mismo estado.
  await usuario.click((await screen.findAllByText('Configuración'))[0]);
  await usuario.click((await screen.findAllByText('Usuarios'))[0]);
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('token', tokenDe('jefe', 1));
  cambiarMiPin.mockClear();
  reiniciarPinUsuario.mockClear();
});

afterEach(cleanup);

describe('Admin: PIN', () => {
  it('el usuario cambia su propio PIN dando el actual', async () => {
    const usuario = userEvent.setup();
    await montarPanelDeUsuarios(usuario);

    await usuario.type(screen.getByLabelText('PIN actual'), 'claveVieja1');
    await usuario.type(screen.getByLabelText('PIN nuevo'), 'claveNueva2');
    await usuario.click(screen.getByRole('button', { name: 'Cambiar mi PIN' }));

    await waitFor(() => {
      expect(cambiarMiPin).toHaveBeenCalledWith('claveVieja1', 'claveNueva2');
    });
  });

  it('el admin reinicia el PIN de otra cuenta', async () => {
    const usuario = userEvent.setup();
    await montarPanelDeUsuarios(usuario);

    // "Reiniciar PIN" aparece por cada usuario que no sea uno mismo
    const botones = await screen.findAllByText('Reiniciar PIN');
    await usuario.click(botones[0]);

    // El modal dice de quién es el PIN que se está por reiniciar
    expect(await screen.findByText(/Reiniciar PIN de ana/)).toBeInTheDocument();

    await usuario.type(screen.getByPlaceholderText('PIN nuevo'), '9999');
    await usuario.click(screen.getByRole('button', { name: 'Guardar PIN nuevo' }));

    await waitFor(() => {
      expect(reiniciarPinUsuario).toHaveBeenCalledWith(2, '9999');
    });
  });

  it('no se ofrece reiniciar el PIN de uno mismo: para eso está el formulario', async () => {
    const usuario = userEvent.setup();
    await montarPanelDeUsuarios(usuario);

    const botones = await screen.findAllByText('Reiniciar PIN');
    // Una por vista (tabla de escritorio y tarjetas de móvil), sólo para ana
    expect(botones).toHaveLength(2);

    await usuario.click(botones[0]);
    expect(await screen.findByText(/Reiniciar PIN de ana/)).toBeInTheDocument();
    expect(screen.queryByText(/Reiniciar PIN de jefe/)).not.toBeInTheDocument();
  });
});
