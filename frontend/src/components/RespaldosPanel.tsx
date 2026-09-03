import { useCallback, useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { HardDriveDownload, Plus, Download, AlertTriangle } from 'lucide-react';
import { api } from '../api';
import { useUI } from './UIProvider';
import { Skeleton } from './Skeleton';

/**
 * Copias de seguridad de la base.
 *
 * El backend ya hacía una copia en cada cierre de caja y tenía los endpoints
 * para listarlas, crearlas y bajarlas. Lo que no existía era la pantalla, así
 * que el dueño del comercio no tenía forma de llevarse una copia ni de saber
 * si había alguna.
 *
 * Y ese es el riesgo más probable de todo el sistema: no un atacante, sino
 * perder el archivo de la base. Ahí se van el inventario, el historial de
 * ventas y los arqueos.
 */

interface Copia {
  nombre: string;
  bytes: number;
  fecha_hora: string;
}

interface EstadoExterno {
  configurado: boolean;
  alcanzable: boolean;
  ultimo: string | null;
  dias_desde_ultimo: number | null;
  en_alarma: boolean;
}

function enMegas(bytes: number) {
  return `${(bytes / 1_048_576).toFixed(1)} MB`;
}

export function RespaldosPanel() {
  const { showToast, confirm } = useUI();
  // `null` es "todavía no cargó": un estado aparte para eso habría que
  // encenderlo dentro del efecto, que dispara un render en cascada.
  const [copias, setCopias] = useState<Copia[] | null>(null);
  const [estadoExterno, setEstadoExterno] = useState<EstadoExterno | null>(null);
  const [creando, setCreando] = useState(false);
  const [bajando, setBajando] = useState<string | null>(null);
  const [vuelta, setVuelta] = useState(0);

  useEffect(() => {
    let vigente = true;

    api.getRespaldos()
      .then((datos: Copia[]) => { if (vigente) setCopias(datos); })
      .catch((e: unknown) => {
        if (!vigente) return;
        setCopias([]);
        showToast(e instanceof Error ? e.message : 'No se pudieron listar los respaldos', 'error');
      });

    // Si esto falla (por ejemplo, sin conexión) se queda en null y
    // simplemente no se muestra el aviso: no es motivo para romper el resto
    // de la pantalla ni para insistirle al usuario con un error de más.
    api.getEstadoRespaldoExterno()
      .then((datos: EstadoExterno) => { if (vigente) setEstadoExterno(datos); })
      .catch(() => {});

    return () => { vigente = false; };
  }, [vuelta, showToast]);

  const cargando = copias === null;
  const recargar = useCallback(() => setVuelta(v => v + 1), []);

  const crear = async () => {
    setCreando(true);
    try {
      await api.crearRespaldo();
      showToast('Copia creada', 'success');
      recargar();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : 'No se pudo crear la copia', 'error');
    } finally {
      setCreando(false);
    }
  };

  const descargar = async (copia: Copia) => {
    // Una copia tiene las ventas y los PIN hasheados de todos los usuarios: es
    // el archivo más sensible del sistema. Vale la pena que el clic sea a
    // conciencia y no de paso.
    const seguro = await confirm({
      title: 'Descargar una copia de la base',
      message:
        'El archivo tiene todas las ventas y los datos de acceso de los usuarios. ' +
        'Guardalo en un lugar seguro y no lo mandes por chat.',
      confirmText: 'Descargar',
    });
    if (!seguro) return;

    setBajando(copia.nombre);
    try {
      await api.descargarRespaldo(copia.nombre);
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : 'No se pudo descargar la copia', 'error');
    } finally {
      setBajando(null);
    }
  };

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
      <div className="glass-card p-6">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-white/10 pb-4 mb-5">
          <div className="flex items-start gap-3">
            <HardDriveDownload className="text-brand-light shrink-0 mt-1" size={22} />
            <div>
              <h3 className="text-xl font-semibold">Copias de seguridad</h3>
              <p className="text-sm text-text-muted mt-1">
                Se guarda una copia sola en cada cierre de caja. Acá podés crear una a mano
                y bajártela.
              </p>
            </div>
          </div>
          <button
            onClick={crear}
            disabled={creando}
            className="bg-brand hover:bg-brand-hover disabled:opacity-50 text-white px-4 py-2.5 rounded-lg text-sm font-semibold flex items-center gap-2 transition-colors"
          >
            <Plus size={16} /> {creando ? 'Creando…' : 'Crear copia ahora'}
          </button>
        </div>

        {estadoExterno?.en_alarma ? (
          <div className="flex gap-3 items-start bg-status-error/10 border border-status-error/30 rounded-lg p-4 mb-5">
            <AlertTriangle className="text-status-error shrink-0 mt-0.5" size={18} />
            <p className="text-sm text-text-secondary">
              {!estadoExterno.configurado ? (
                <>No hay ninguna copia fuera de este disco. Estas copias no sirven si el disco
                  se rompe o se pierde la computadora.</>
              ) : !estadoExterno.alcanzable ? (
                <>No se puede llegar a la carpeta de respaldo externo configurada — ¿el pendrive
                  está puesto? ¿la carpeta de OneDrive/Drive sigue existiendo en esta cuenta?</>
              ) : estadoExterno.dias_desde_ultimo == null ? (
                <>La carpeta de respaldo externo está configurada, pero todavía no hay ninguna
                  copia adentro.</>
              ) : (
                <>Hace <strong className="text-text-primary">{estadoExterno.dias_desde_ultimo}</strong> días
                  que no se hace una copia fuera de este disco.</>
              )}
              {' '}Configurá <span className="font-mono text-xs mx-1 text-text-primary">RESPALDO_EXTERNO</span>
              en el <span className="font-mono text-xs">.env</span> del backend para que se duplique sola.
            </p>
          </div>
        ) : (
          <div className="flex gap-3 items-start bg-status-warning/10 border border-status-warning/30 rounded-lg p-4 mb-5">
            <AlertTriangle className="text-status-warning shrink-0 mt-0.5" size={18} />
            <p className="text-sm text-text-secondary">
              {estadoExterno?.configurado && estadoExterno.dias_desde_ultimo != null && (
                <>Última copia fuera de este disco: hace {estadoExterno.dias_desde_ultimo < 1
                  ? 'menos de un día' : `${estadoExterno.dias_desde_ultimo} días`}. </>
              )}
              <strong className="text-text-primary">Probá restaurar una antes de necesitarla:</strong> un
              respaldo que nadie probó no es un respaldo.
            </p>
          </div>
        )}

        {cargando ? (
          <div className="space-y-2">
            {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}
          </div>
        ) : copias.length === 0 ? (
          <p className="text-text-muted text-sm py-10 text-center">
            Todavía no hay ninguna copia. Se crea una en cada cierre de caja.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[520px]">
              <thead>
                <tr className="text-left text-text-secondary border-b border-white/10">
                  <th className="py-2 pr-4 font-medium">Archivo</th>
                  <th className="py-2 pr-4 font-medium">Cuándo</th>
                  <th className="py-2 pr-4 font-medium">Tamaño</th>
                  <th className="py-2 font-medium"></th>
                </tr>
              </thead>
              <tbody>
                {(copias ?? []).map(c => (
                  <tr key={c.nombre} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                    <td className="py-2.5 pr-4 font-mono text-xs">{c.nombre}</td>
                    <td className="py-2.5 pr-4 whitespace-nowrap text-text-secondary">
                      {new Date(c.fecha_hora).toLocaleString()}
                    </td>
                    <td className="py-2.5 pr-4 whitespace-nowrap">{enMegas(c.bytes)}</td>
                    <td className="py-2.5 text-right">
                      <button
                        onClick={() => descargar(c)}
                        disabled={bajando === c.nombre}
                        className="bg-white/5 hover:bg-white/10 disabled:opacity-50 px-3 py-1.5 rounded text-xs font-semibold inline-flex items-center gap-1.5 transition-colors"
                      >
                        <Download size={13} />
                        {bajando === c.nombre ? 'Bajando…' : 'Descargar'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </motion.div>
  );
}
