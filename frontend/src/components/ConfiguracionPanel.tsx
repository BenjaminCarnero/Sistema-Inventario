import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Store, Percent, Coins, ShoppingBag, Receipt, RotateCcw, Save, AlertTriangle, Palette, Upload, Image as ImageIcon } from 'lucide-react';
import { api } from '../api';
import { useUI } from './UIProvider';
import { useConfig } from './ConfigProvider';
import { Skeleton } from './Skeleton';

interface Parametro {
  clave: string;
  valor: any;
  tipo: string;
  categoria: string;
  descripcion?: string;
}

const ICONOS: Record<string, typeof Store> = {
  marca: Palette,
  negocio: Store,
  impuestos: Percent,
  moneda: Coins,
  pos: ShoppingBag,
  ticket: Receipt,
};

const TITULOS: Record<string, string> = {
  marca: 'Marca y apariencia',
  negocio: 'Datos del negocio',
  impuestos: 'Impuestos',
  moneda: 'Moneda',
  pos: 'Punto de venta',
  ticket: 'Ticket',
};

const ETIQUETAS: Record<string, string> = {
  marca_logo_url: 'Logo',
  marca_color_primario: 'Color principal',
  marca_color_acento: 'Color de acento',
  negocio_nombre: 'Nombre del negocio',
  negocio_cuit: 'CUIT / Tax ID',
  negocio_direccion: 'Dirección',
  negocio_telefono: 'Teléfono',
  iva_porcentaje: 'Alícuota (%)',
  iva_incluido_en_precio: 'Los precios ya incluyen el impuesto',
  mostrar_iva_en_ticket: 'Desglosar el impuesto en el ticket',
  iva_nombre: 'Nombre del impuesto',
  moneda_simbolo: 'Símbolo',
  moneda_codigo: 'Código ISO',
  umbral_stock_bajo: 'Umbral de stock bajo',
  permitir_stock_negativo: 'Permitir vender sin stock',
  metodos_pago_habilitados: 'Métodos de pago habilitados',
  ticket_mensaje_pie: 'Mensaje del pie',
  ticket_mostrar_logo: 'Mostrar nombre del negocio destacado',
};

const METODOS_DISPONIBLES = ['EFECTIVO', 'TARJETA', 'TRANSFERENCIA', 'MERCADOPAGO'];

export function ConfiguracionPanel() {
  const { showToast, confirm } = useUI();
  const { recargar } = useConfig();
  const [parametros, setParametros] = useState<Parametro[]>([]);
  const [valores, setValores] = useState<Record<string, any>>({});
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Sin esto, soportar por teléfono a un comercio es adivinar qué versión
  // tiene instalada. Se lee de /health y no de un archivo del frontend:
  // así siempre muestra la versión del backend que realmente está corriendo,
  // que es la que importa cuando algo no anda.
  const [version, setVersion] = useState<string | null>(null);

  useEffect(() => {
    fetch('/health').then(r => r.json()).then(d => setVersion(d.version)).catch(() => {});
  }, []);

  const cargar = () => {
    setCargando(true);
    setError(null);
    api.getConfiguracion()
      .then((ps: Parametro[]) => {
        setParametros(ps);
        setValores(Object.fromEntries(ps.map(p => [p.clave, p.valor])));
      })
      .catch(err => setError(err.message))
      .finally(() => setCargando(false));
  };

  useEffect(cargar, []);

  const cambiado = parametros.some(p => JSON.stringify(p.valor) !== JSON.stringify(valores[p.clave]));

  const guardar = async () => {
    setGuardando(true);
    try {
      const cambios = Object.fromEntries(
        parametros
          .filter(p => JSON.stringify(p.valor) !== JSON.stringify(valores[p.clave]))
          .map(p => [p.clave, valores[p.clave]])
      );
      const actualizados = await api.updateConfiguracion(cambios);
      setParametros(actualizados);
      setValores(Object.fromEntries(actualizados.map((p: Parametro) => [p.clave, p.valor])));
      await recargar();
      showToast('Configuración guardada', 'success');
    } catch (err: any) {
      showToast(err.message, 'error');
    } finally {
      setGuardando(false);
    }
  };

  /**
   * Convierte el archivo elegido en un data URI reducido a 256px.
   * Así el logo viaja embebido en la configuración sin necesitar un servicio
   * de archivos, y se mantiene chico (unos pocos KB en lugar de cientos).
   */
  const onSubirLogo = (e: React.ChangeEvent<HTMLInputElement>) => {
    const archivo = e.target.files?.[0];
    if (!archivo) return;
    e.target.value = ''; // permite volver a elegir el mismo archivo

    if (!archivo.type.startsWith('image/')) {
      showToast('El archivo tiene que ser una imagen', 'error');
      return;
    }

    const lector = new FileReader();
    lector.onload = () => {
      const img = new Image();
      img.onload = () => {
        const MAX = 256;
        const escala = Math.min(1, MAX / Math.max(img.width, img.height));
        const canvas = document.createElement('canvas');
        canvas.width = Math.round(img.width * escala);
        canvas.height = Math.round(img.height * escala);
        const ctx = canvas.getContext('2d');
        if (!ctx) {
          showToast('No se pudo procesar la imagen', 'error');
          return;
        }
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        // PNG para conservar transparencia (logos suelen tener fondo transparente)
        setValores(v => ({ ...v, marca_logo_url: canvas.toDataURL('image/png') }));
        showToast('Logo cargado. Acordate de guardar los cambios.', 'success');
      };
      img.onerror = () => showToast('No se pudo leer la imagen', 'error');
      img.src = lector.result as string;
    };
    lector.onerror = () => showToast('No se pudo leer el archivo', 'error');
    lector.readAsDataURL(archivo);
  };

  const restaurar = async () => {
    const ok = await confirm({
      title: 'Restaurar valores de fábrica',
      message: 'Se van a descartar todas tus personalizaciones y volver a los valores por defecto (IVA 21%, pesos argentinos). ¿Continuar?',
      confirmText: 'Restaurar',
      danger: true,
    });
    if (!ok) return;
    try {
      const ps = await api.restaurarConfiguracion();
      setParametros(ps);
      setValores(Object.fromEntries(ps.map((p: Parametro) => [p.clave, p.valor])));
      await recargar();
      showToast('Configuración restaurada a los valores de fábrica', 'success');
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  if (cargando) {
    return (
      <div className="space-y-6 max-w-3xl">
        <Skeleton className="h-48" />
        <Skeleton className="h-48" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="glass-card p-8 max-w-2xl border-l-4 border-l-status-error">
        <div className="flex items-start gap-3 mb-4">
          <AlertTriangle size={24} className="text-status-error shrink-0 mt-0.5" />
          <div>
            <h3 className="font-bold text-status-error text-lg">No se pudo cargar la configuración</h3>
            <p className="text-text-secondary text-sm mt-1">{error}</p>
          </div>
        </div>
        <div className="bg-white/5 rounded-xl p-4 text-sm text-text-secondary mb-4">
          <p className="font-semibold mb-2">Si acabás de actualizar el proyecto, reiniciá los dos servidores:</p>
          <ol className="list-decimal list-inside space-y-1 text-text-muted">
            <li>El backend de Python (para que cargue las rutas nuevas)</li>
            <li>El <code className="text-brand-light">npm run dev</code> del frontend (para que tome el proxy nuevo)</li>
          </ol>
        </div>
        <button onClick={cargar} className="btn-primary px-5 py-2 flex items-center gap-2 text-sm">
          <RotateCcw size={15} /> Reintentar
        </button>
      </div>
    );
  }

  const categorias = [...new Set(parametros.map(p => p.categoria))];

  const renderCampo = (p: Parametro) => {
    const valor = valores[p.clave];
    const etiqueta = ETIQUETAS[p.clave] || p.clave;

    if (p.tipo === 'boolean') {
      return (
        <label key={p.clave} className="flex items-start gap-3 p-3 rounded-xl hover:bg-white/5 cursor-pointer transition-colors">
          <input
            type="checkbox"
            className="mt-1 shrink-0"
            checked={!!valor}
            onChange={e => setValores({ ...valores, [p.clave]: e.target.checked })}
          />
          <span className="min-w-0">
            <span className="block font-medium text-sm">{etiqueta}</span>
            {p.descripcion && <span className="block text-xs text-text-muted mt-0.5">{p.descripcion}</span>}
          </span>
        </label>
      );
    }

    if (p.clave === 'marca_color_primario' || p.clave === 'marca_color_acento') {
      return (
        <div key={p.clave} className="p-3">
          <label className="block font-medium text-sm mb-1">{etiqueta}</label>
          {p.descripcion && <p className="text-xs text-text-muted mb-2">{p.descripcion}</p>}
          <div className="flex items-center gap-3">
            <input
              type="color"
              value={/^#[0-9a-fA-F]{6}$/.test(valor) ? valor : '#000000'}
              onChange={e => setValores({ ...valores, [p.clave]: e.target.value.toUpperCase() })}
              className="w-12 h-11 rounded-lg bg-transparent border border-white/15 cursor-pointer p-1"
            />
            <input
              type="text"
              className="glass-input flex-1 p-3 rounded-lg font-mono uppercase"
              value={valor ?? ''}
              placeholder="#8251EE"
              onChange={e => setValores({ ...valores, [p.clave]: e.target.value })}
            />
          </div>
        </div>
      );
    }

    if (p.clave === 'marca_logo_url') {
      return (
        <div key={p.clave} className="p-3">
          <label className="block font-medium text-sm mb-1">{etiqueta}</label>
          {p.descripcion && <p className="text-xs text-text-muted mb-2">{p.descripcion}</p>}
          <div className="flex items-start gap-3">
            <div className="w-16 h-16 rounded-xl bg-white/5 border border-white/15 flex items-center justify-center overflow-hidden shrink-0">
              {valor ? (
                <img src={valor} alt="Logo" className="w-full h-full object-contain" />
              ) : (
                <ImageIcon size={20} className="text-text-muted" />
              )}
            </div>
            <div className="flex-1 min-w-0 space-y-2">
              <input
                type="text"
                className="glass-input w-full p-3 rounded-lg text-sm"
                placeholder="https://… o subí un archivo"
                value={valor?.startsWith('data:') ? '(imagen cargada desde tu equipo)' : (valor ?? '')}
                readOnly={valor?.startsWith('data:')}
                onChange={e => setValores({ ...valores, [p.clave]: e.target.value })}
              />
              <div className="flex gap-2">
                <label className="text-xs font-semibold px-3 py-2 rounded-lg bg-brand/20 text-brand-light hover:bg-brand/30 transition-colors cursor-pointer flex items-center gap-2">
                  <Upload size={14} /> Subir imagen
                  <input type="file" accept="image/*" className="hidden" onChange={onSubirLogo} />
                </label>
                {valor && (
                  <button
                    type="button"
                    onClick={() => setValores({ ...valores, [p.clave]: '' })}
                    className="text-xs font-semibold px-3 py-2 rounded-lg bg-white/5 text-text-secondary hover:bg-white/10 transition-colors"
                  >
                    Quitar
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      );
    }

    if (p.clave === 'metodos_pago_habilitados') {
      const seleccionados: string[] = Array.isArray(valor) ? valor : [];
      return (
        <div key={p.clave} className="p-3">
          <span className="block font-medium text-sm mb-1">{etiqueta}</span>
          {p.descripcion && <span className="block text-xs text-text-muted mb-3">{p.descripcion}</span>}
          <div className="flex flex-wrap gap-2">
            {METODOS_DISPONIBLES.map(m => {
              const activo = seleccionados.includes(m);
              return (
                <button
                  key={m}
                  type="button"
                  onClick={() => {
                    const nuevos = activo ? seleccionados.filter(x => x !== m) : [...seleccionados, m];
                    setValores({ ...valores, [p.clave]: nuevos });
                  }}
                  className={`px-3 py-2 rounded-lg text-sm font-semibold transition-colors ${
                    activo
                      ? 'bg-brand/20 text-brand-light border border-brand/40'
                      : 'bg-white/5 text-text-muted border border-white/10 hover:bg-white/10'
                  }`}
                >
                  {m}
                </button>
              );
            })}
          </div>
          {seleccionados.length === 0 && (
            <p className="text-xs text-status-error mt-2">Tiene que quedar al menos uno habilitado.</p>
          )}
        </div>
      );
    }

    return (
      <div key={p.clave} className="p-3">
        <label className="block font-medium text-sm mb-1">{etiqueta}</label>
        {p.descripcion && <p className="text-xs text-text-muted mb-2">{p.descripcion}</p>}
        <input
          type={p.tipo === 'number' ? 'number' : 'text'}
          step={p.clave === 'iva_porcentaje' ? '0.01' : undefined}
          min={p.tipo === 'number' ? 0 : undefined}
          max={p.clave === 'iva_porcentaje' ? 100 : undefined}
          className="glass-input w-full p-3 rounded-lg"
          value={valor ?? ''}
          // La rueda del mouse sobre un campo numérico enfocado le cambia el
          // valor sin que se note. En parámetros como la alícuota de IVA eso es
          // peligroso, así que se desenfoca en lugar de modificar.
          onWheel={e => e.currentTarget.blur()}
          onKeyDown={e => {
            if (p.tipo === 'number' && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
              e.preventDefault();
            }
          }}
          onChange={e =>
            setValores({
              ...valores,
              [p.clave]: p.tipo === 'number' ? Number(e.target.value) : e.target.value,
            })
          }
        />
      </div>
    );
  };

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }} className="max-w-3xl">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
        <p className="text-sm text-text-muted">
          Estos parámetros se aplican al POS de todos los cajeros apenas los guardás.
        </p>
        <div className="flex gap-2">
          <button
            onClick={restaurar}
            className="flex items-center gap-2 text-sm px-3 py-2 bg-neutral-bg3 hover:bg-neutral-bg4 rounded-lg text-text-secondary transition-colors"
          >
            <RotateCcw size={15} /> Restaurar
          </button>
          <button
            onClick={guardar}
            disabled={!cambiado || guardando}
            className="btn-primary px-5 py-2 flex items-center gap-2 text-sm"
          >
            <Save size={15} /> {guardando ? 'Guardando…' : 'Guardar cambios'}
          </button>
        </div>
      </div>

      <div className="space-y-6">
        {categorias.map(cat => {
          const Icono = ICONOS[cat] || Store;
          return (
            <div key={cat} className="glass-card p-6">
              <h3 className="text-lg font-semibold mb-4 pb-3 border-b border-white/10 flex items-center gap-2">
                <Icono size={18} className="text-brand-light" /> {TITULOS[cat] || cat}
              </h3>
              <div className="divide-y divide-white/5">
                {parametros.filter(p => p.categoria === cat).map(renderCampo)}
              </div>

              {cat === 'impuestos' && (
                <div className="mt-4 p-4 rounded-xl bg-brand/10 border border-brand/20 text-sm">
                  <p className="text-text-secondary">
                    {valores.iva_incluido_en_precio ? (
                      <>
                        Un producto de <strong>{valores.moneda_simbolo}100</strong> se cobra{' '}
                        <strong>{valores.moneda_simbolo}100</strong>, de los cuales{' '}
                        <strong>
                          {valores.moneda_simbolo}
                          {(100 - 100 / (1 + (Number(valores.iva_porcentaje) || 0) / 100)).toFixed(2)}
                        </strong>{' '}
                        son {valores.iva_nombre}. Es el modo habitual en Argentina.
                      </>
                    ) : (
                      <>
                        Un producto de <strong>{valores.moneda_simbolo}100</strong> se cobra{' '}
                        <strong>
                          {valores.moneda_simbolo}
                          {(100 * (1 + (Number(valores.iva_porcentaje) || 0) / 100)).toFixed(2)}
                        </strong>
                        , sumando {valores.iva_nombre} al cobrar.
                      </>
                    )}
                  </p>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {version && (
        <p className="text-xs text-text-muted mt-6 text-center">
          Sistema de Inventario y POS · versión {version}
        </p>
      )}
    </motion.div>
  );
}
