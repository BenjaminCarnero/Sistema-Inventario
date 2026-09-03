import { useEffect, useState } from 'react';
import { X, Wifi, WifiOff, Loader2 } from 'lucide-react';

type Estado = 'probando' | 'ok' | 'error';

/**
 * Diagnóstico de conexión, para el celular o la tablet que "no anda" y nadie
 * sabe si es el wifi, el firewall de la PC servidor o el router que le dio
 * otra IP al reiniciar. Sin esto, cada caso termina en "probá de nuevo" por
 * WhatsApp hasta encontrar la causa a los ponchazos.
 *
 * Vive en la pantalla de login (con o sin sesión) porque es justo el momento
 * en que hace falta: si no se puede entrar, tampoco se puede llegar a esto
 * desde adentro del sistema.
 */
export function DiagnosticoRed({ onClose }: { onClose: () => void }) {
  const [estado, setEstado] = useState<Estado>('probando');
  const [demoraMs, setDemoraMs] = useState<number | null>(null);
  const [version, setVersion] = useState<string | null>(null);

  useEffect(() => {
    let cancelado = false;
    const inicio = performance.now();
    const abortar = new AbortController();
    const timeout = setTimeout(() => abortar.abort(), 5000);

    fetch('/health', { signal: abortar.signal, cache: 'no-store' })
      .then(async res => {
        if (cancelado) return;
        setDemoraMs(Math.round(performance.now() - inicio));
        if (!res.ok) { setEstado('error'); return; }
        const datos = await res.json().catch(() => null);
        setVersion(datos?.version ?? null);
        setEstado('ok');
      })
      .catch(() => {
        if (!cancelado) { setDemoraMs(Math.round(performance.now() - inicio)); setEstado('error'); }
      })
      .finally(() => clearTimeout(timeout));

    return () => { cancelado = true; clearTimeout(timeout); abortar.abort(); };
  }, []);

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-50">
      <div className="glass-card p-6 w-full max-w-md relative">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-text-secondary hover:text-white"
          aria-label="Cerrar"
        >
          <X size={20} />
        </button>

        <h2 className="text-lg font-semibold mb-4">Diagnóstico de conexión</h2>

        <div className="space-y-3 text-sm">
          <div>
            <p className="text-text-muted">Este equipo está hablando con</p>
            <p className="font-mono text-text-primary break-all">{window.location.origin}</p>
          </div>

          <div className="flex items-center gap-2 pt-1">
            {estado === 'probando' && <Loader2 size={18} className="animate-spin text-text-secondary" />}
            {estado === 'ok' && <Wifi size={18} className="text-status-success" />}
            {estado === 'error' && <WifiOff size={18} className="text-status-error" />}

            {estado === 'probando' && <span className="text-text-secondary">Probando...</span>}
            {estado === 'ok' && (
              <span className="text-status-success">
                Servidor alcanzado{demoraMs != null ? ` en ${demoraMs} ms` : ''}
                {version ? ` · versión ${version}` : ''}
              </span>
            )}
            {estado === 'error' && (
              <span className="text-status-error">
                No se pudo llegar al servidor{demoraMs != null ? ` (esperó ${demoraMs} ms)` : ''}
              </span>
            )}
          </div>
        </div>

        {estado === 'error' && (
          <div className="mt-5 p-4 rounded-xl bg-status-error/10 border border-status-error/20 text-sm text-text-secondary space-y-2">
            <p className="font-semibold text-status-error">Qué revisar:</p>
            <ul className="list-disc list-inside space-y-1">
              <li>¿La PC que hace de servidor está prendida y con el sistema corriendo?</li>
              <li>¿Este equipo está en el mismo wifi que la PC servidor?</li>
              <li>¿La dirección de arriba es la de siempre? Un router puede haberle dado
                otra IP a la PC servidor al reiniciar.</li>
              <li>¿El firewall de Windows de la PC servidor tiene el puerto abierto?</li>
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
