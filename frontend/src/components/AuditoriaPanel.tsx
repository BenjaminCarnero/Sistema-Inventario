import { useCallback, useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { ShieldCheck, Filter, RotateCcw } from 'lucide-react';
import { api } from '../api';
import { useUI } from './UIProvider';
import { Skeleton } from './Skeleton';

/**
 * Registro de quién cambió qué.
 *
 * El backend tenía este router completo —con filtros por entidad, usuario y
 * rango de fechas— desde hacía rato, y el frontend no lo llamaba nunca. Toda
 * la trazabilidad de cambios de precio existía y no había forma de mirarla,
 * que es lo mismo que no tenerla: el argumento contra el fraude interno es
 * poder abrir esta pantalla y ver quién bajó un precio el martes.
 */

interface Entrada {
  id: number;
  usuario_id: number | null;
  usuario_nombre: string | null;
  fecha_hora: string;
  entidad: string;
  entidad_id: number | null;
  entidad_nombre: string | null;
  accion: string;
  campo: string | null;
  valor_anterior: string | null;
  valor_nuevo: string | null;
}

const ENTIDADES = [
  { id: '', etiqueta: 'Todo' },
  { id: 'producto', etiqueta: 'Productos' },
  { id: 'descuento', etiqueta: 'Descuentos' },
  { id: 'configuracion', etiqueta: 'Configuración' },
  { id: 'usuario', etiqueta: 'Usuarios' },
  { id: 'devolucion', etiqueta: 'Devoluciones' },
  { id: 'venta', etiqueta: 'Ventas' },
];

const COLOR_ACCION: Record<string, string> = {
  CREAR: 'bg-status-success/20 text-status-success border-status-success/30',
  MODIFICAR: 'bg-status-warning/20 text-status-warning border-status-warning/30',
  ELIMINAR: 'bg-status-error/20 text-status-error border-status-error/30',
};

export function AuditoriaPanel() {
  const { showToast } = useUI();
  // `null` es "todavía no cargó". Un estado aparte para eso obligaba a
  // encenderlo dentro del efecto, que dispara un render en cascada.
  const [entradas, setEntradas] = useState<Entrada[] | null>(null);
  const [entidad, setEntidad] = useState('');
  const [desde, setDesde] = useState('');
  const [hasta, setHasta] = useState('');
  // Sube al cambiar un filtro y vuelve a pedir. Se usa también para el botón.
  const [vuelta, setVuelta] = useState(0);

  useEffect(() => {
    // Si los filtros cambian antes de que vuelva la respuesta anterior, la
    // vieja no tiene que pisar a la nueva.
    let vigente = true;

    api.getAuditoria({ entidad, desde, hasta, limite: 500 })
      .then((datos: Entrada[]) => { if (vigente) setEntradas(datos); })
      .catch((e: unknown) => {
        if (!vigente) return;
        setEntradas([]);
        showToast(e instanceof Error ? e.message : 'No se pudo leer la auditoría', 'error');
      });

    return () => { vigente = false; };
  }, [entidad, desde, hasta, vuelta, showToast]);

  const cargar = useCallback(() => setVuelta(v => v + 1), []);
  const limpiar = () => { setEntidad(''); setDesde(''); setHasta(''); };
  const cargando = entradas === null;

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
      <div className="glass-card p-6">
        <div className="flex items-start gap-3 border-b border-white/10 pb-4 mb-5">
          <ShieldCheck className="text-brand-light shrink-0 mt-1" size={22} />
          <div>
            <h3 className="text-xl font-semibold">Registro de cambios</h3>
            <p className="text-sm text-text-muted mt-1">
              Quién tocó un precio, un descuento, un permiso o la configuración, cuándo,
              y de qué valor a qué valor. Los movimientos de mercadería tienen su propia
              pantalla en Stock.
            </p>
          </div>
        </div>

        {/* Filtros */}
        <div className="flex flex-wrap items-end gap-3 mb-5">
          <div className="min-w-[160px]">
            <label className="block text-xs text-text-secondary mb-1">Qué se tocó</label>
            <select
              className="glass-input w-full p-2.5 rounded-lg text-sm"
              value={entidad}
              onChange={e => setEntidad(e.target.value)}
            >
              {ENTIDADES.map(e => <option key={e.id} value={e.id}>{e.etiqueta}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs text-text-secondary mb-1">Desde</label>
            <input
              type="date" className="glass-input p-2.5 rounded-lg text-sm"
              value={desde} onChange={e => setDesde(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs text-text-secondary mb-1">Hasta</label>
            <input
              type="date" className="glass-input p-2.5 rounded-lg text-sm"
              value={hasta} onChange={e => setHasta(e.target.value)}
            />
          </div>
          <button
            onClick={cargar}
            className="bg-brand/20 hover:bg-brand/40 text-brand-light px-4 py-2.5 rounded-lg text-sm font-semibold flex items-center gap-2 transition-colors"
          >
            <Filter size={15} /> Filtrar
          </button>
          <button
            onClick={limpiar}
            className="text-text-secondary hover:text-white px-3 py-2.5 rounded-lg text-sm flex items-center gap-2 transition-colors"
          >
            <RotateCcw size={15} /> Limpiar
          </button>
        </div>

        {cargando ? (
          <div className="space-y-2">
            {[...Array(6)].map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}
          </div>
        ) : entradas.length === 0 ? (
          <p className="text-text-muted text-sm py-10 text-center">
            No hay cambios registrados con esos filtros.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[820px]">
              <thead>
                <tr className="text-left text-text-secondary border-b border-white/10">
                  <th className="py-2 pr-4 font-medium">Cuándo</th>
                  <th className="py-2 pr-4 font-medium">Quién</th>
                  <th className="py-2 pr-4 font-medium">Qué</th>
                  <th className="py-2 pr-4 font-medium">Acción</th>
                  <th className="py-2 pr-4 font-medium">Campo</th>
                  <th className="py-2 pr-4 font-medium">Antes</th>
                  <th className="py-2 font-medium">Después</th>
                </tr>
              </thead>
              <tbody>
                {(entradas ?? []).map(e => (
                  <tr key={e.id} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                    <td className="py-2.5 pr-4 whitespace-nowrap text-text-secondary">
                      {new Date(e.fecha_hora).toLocaleString()}
                    </td>
                    <td className="py-2.5 pr-4 whitespace-nowrap">{e.usuario_nombre || 'Sistema'}</td>
                    <td className="py-2.5 pr-4">
                      <span className="text-text-secondary">{e.entidad}</span>
                      {e.entidad_nombre && <span className="ml-1.5">{e.entidad_nombre}</span>}
                    </td>
                    <td className="py-2.5 pr-4">
                      <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border whitespace-nowrap ${
                        COLOR_ACCION[e.accion] || 'bg-white/10 text-text-secondary border-white/20'
                      }`}>
                        {e.accion}
                      </span>
                    </td>
                    <td className="py-2.5 pr-4 text-text-secondary">{e.campo || '—'}</td>
                    <td className="py-2.5 pr-4 font-mono text-xs max-w-[180px] truncate" title={e.valor_anterior || ''}>
                      {e.valor_anterior ?? '—'}
                    </td>
                    <td className="py-2.5 font-mono text-xs max-w-[180px] truncate" title={e.valor_nuevo || ''}>
                      {e.valor_nuevo ?? '—'}
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
