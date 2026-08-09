import { useEffect, useState } from 'react';

/**
 * Estado real de conexión con el servidor.
 *
 * `navigator.onLine` sólo dice si la máquina tiene red, no si el backend
 * responde: con el wifi del local andando pero el servidor caído, el POS creía
 * estar en línea y seguía ofreciendo cobros que iban a fallar.
 *
 * Se combinan las dos señales: sin red se corta enseguida, y con red se
 * confirma consultando el endpoint de salud cada tanto.
 */
const INTERVALO_MS = 15_000;
const TIMEOUT_MS = 4_000;

export function useConexion() {
  const [sinRed, setSinRed] = useState(!navigator.onLine);
  const [servidorCaido, setServidorCaido] = useState(false);

  useEffect(() => {
    let cancelado = false;

    const consultar = async () => {
      if (!navigator.onLine) {
        if (!cancelado) setServidorCaido(false); // manda la señal de red
        return;
      }
      const abortar = new AbortController();
      const t = setTimeout(() => abortar.abort(), TIMEOUT_MS);
      try {
        const res = await fetch('/health', { signal: abortar.signal, cache: 'no-store' });
        if (!cancelado) setServidorCaido(!res.ok);
      } catch {
        if (!cancelado) setServidorCaido(true);
      } finally {
        clearTimeout(t);
      }
    };

    const alConectar = () => { setSinRed(false); consultar(); };
    const alDesconectar = () => setSinRed(true);

    window.addEventListener('online', alConectar);
    window.addEventListener('offline', alDesconectar);
    consultar();
    const timer = setInterval(consultar, INTERVALO_MS);

    return () => {
      cancelado = true;
      clearInterval(timer);
      window.removeEventListener('online', alConectar);
      window.removeEventListener('offline', alDesconectar);
    };
  }, []);

  return {
    /** No se puede llegar al servidor, sea por red o porque está caído. */
    offline: sinRed || servidorCaido,
    sinRed,
    servidorCaido,
  };
}
