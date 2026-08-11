import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { api } from '../api';

export interface Config {
  marca_logo_url: string;
  marca_color_primario: string;
  marca_color_acento: string;
  negocio_nombre: string;
  negocio_cuit: string;
  negocio_direccion: string;
  negocio_telefono: string;
  iva_porcentaje: number;
  iva_incluido_en_precio: boolean;
  mostrar_iva_en_ticket: boolean;
  iva_nombre: string;
  moneda_simbolo: string;
  moneda_codigo: string;
  umbral_stock_bajo: number;
  permitir_stock_negativo: boolean;
  monto_maximo_efectivo: number;
  metodos_pago_habilitados: string[];
  ticket_mensaje_pie: string;
  ticket_mostrar_logo: boolean;
  pedido_saludo: string;
  pedido_despedida: string;
}

/**
 * Mismos valores que `configuracion_defaults.py` en el backend. Se usan
 * mientras la configuración carga y como respaldo si el POS está offline.
 */
export const CONFIG_DEFAULT: Config = {
  marca_logo_url: '',
  marca_color_primario: '#8251EE',
  marca_color_acento: '#00F2FE',
  negocio_nombre: 'APPLIFY POS',
  negocio_cuit: '',
  negocio_direccion: '',
  negocio_telefono: '',
  iva_porcentaje: 21,
  iva_incluido_en_precio: true,
  mostrar_iva_en_ticket: true,
  iva_nombre: 'IVA',
  moneda_simbolo: '$',
  moneda_codigo: 'ARS',
  umbral_stock_bajo: 5,
  permitir_stock_negativo: true,
  monto_maximo_efectivo: 1000000,
  metodos_pago_habilitados: ['EFECTIVO', 'TARJETA', 'TRANSFERENCIA', 'MERCADOPAGO'],
  ticket_mensaje_pie: '¡Gracias por su compra!',
  ticket_mostrar_logo: true,
  pedido_saludo: 'Hola, te hago un pedido:',
  pedido_despedida: '¡Gracias!',
};

const CACHE_KEY = 'applify_config';

interface ConfigContextValue {
  config: Config;
  cargando: boolean;
  recargar: () => Promise<void>;
  /** Formatea un importe con el símbolo de moneda configurado. */
  money: (valor: number) => string;
  /** Descompone un total en neto e impuesto según el modo configurado. */
  desglosarIva: (total: number) => { neto: number; iva: number; total: number };
}

const ConfigContext = createContext<ConfigContextValue | null>(null);

export function useConfig() {
  const ctx = useContext(ConfigContext);
  if (!ctx) throw new Error('useConfig debe usarse dentro de ConfigProvider');
  return ctx;
}

/** "#8251EE" → [130, 81, 238]. Acepta también el formato corto "#abc". */
function hexARgb(hex: string): [number, number, number] | null {
  const limpio = (hex || '').trim().replace('#', '');
  const completo = limpio.length === 3 ? limpio.split('').map(c => c + c).join('') : limpio;
  if (!/^[0-9a-fA-F]{6}$/.test(completo)) return null;
  return [
    parseInt(completo.slice(0, 2), 16),
    parseInt(completo.slice(2, 4), 16),
    parseInt(completo.slice(4, 6), 16),
  ];
}

/** Aclara u oscurece un color mezclándolo con blanco (factor > 0) o negro. */
function ajustar([r, g, b]: [number, number, number], factor: number): string {
  const mezcla = (c: number) =>
    Math.round(factor >= 0 ? c + (255 - c) * factor : c * (1 + factor));
  return `${mezcla(r)} ${mezcla(g)} ${mezcla(b)}`;
}

/**
 * Escribe los colores de marca como variables CSS. Tailwind los consume con
 * rgb(var(--color-brand) / <alpha>), así que un cambio acá repinta toda la app
 * sin recompilar ni recargar.
 */
function aplicarTema(config: Config) {
  const raiz = document.documentElement;
  const brand = hexARgb(config.marca_color_primario);
  const accent = hexARgb(config.marca_color_acento);

  if (brand) {
    raiz.style.setProperty('--color-brand', brand.join(' '));
    raiz.style.setProperty('--color-brand-hover', ajustar(brand, 0.15));
    raiz.style.setProperty('--color-brand-light', ajustar(brand, 0.45));
  }
  if (accent) {
    raiz.style.setProperty('--color-accent', accent.join(' '));
    raiz.style.setProperty('--color-accent-hover', ajustar(accent, -0.15));
  }

  // El color de la barra del navegador en móvil acompaña a la marca
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta && brand) meta.setAttribute('content', config.marca_color_primario);
}

function leerCache(): Config {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (raw) return { ...CONFIG_DEFAULT, ...JSON.parse(raw) };
  } catch {
    /* cache corrupta: seguimos con los defaults */
  }
  return CONFIG_DEFAULT;
}

export function ConfigProvider({ children }: { children: ReactNode }) {
  // Arrancamos con la última configuración conocida para que el POS pueda
  // cobrar con el IVA correcto incluso sin conexión.
  const [config, setConfig] = useState<Config>(leerCache);
  const [cargando, setCargando] = useState(true);

  const recargar = useCallback(async () => {
    try {
      const parametros = await api.getConfiguracion();
      const plano = Object.fromEntries(parametros.map((p: any) => [p.clave, p.valor]));
      const merged = { ...CONFIG_DEFAULT, ...plano } as Config;
      setConfig(merged);
      localStorage.setItem(CACHE_KEY, JSON.stringify(merged));
    } catch {
      // Sin token o sin red: se mantiene el cache/defaults.
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    if (localStorage.getItem('token')) {
      recargar();
      return;
    }
    // Sin sesión se pide sólo la marca, que no es secreta: sin esto, un
    // dispositivo que nunca entró muestra el nombre y los colores por
    // defecto justo en la primera pantalla que se ve.
    api.getMarca()
      .then((marca: Partial<Config>) => setConfig(previa => ({ ...previa, ...marca })))
      .catch(() => { /* sin red: quedan el cache o los defaults */ })
      .finally(() => setCargando(false));
  }, [recargar]);

  // Marca: colores y título se aplican apenas cambia la configuración, tanto al
  // arrancar desde el cache como al guardar cambios en el panel de admin.
  useEffect(() => {
    aplicarTema(config);
    if (config.negocio_nombre) document.title = config.negocio_nombre;
  }, [config]);

  const money = useCallback(
    (valor: number) => `${config.moneda_simbolo}${(valor ?? 0).toFixed(2)}`,
    [config.moneda_simbolo]
  );

  const desglosarIva = useCallback(
    (total: number) => {
      const pct = config.iva_porcentaje || 0;
      if (pct <= 0) return { neto: total, iva: 0, total };

      if (config.iva_incluido_en_precio) {
        const neto = total / (1 + pct / 100);
        return {
          neto: Math.round(neto * 100) / 100,
          iva: Math.round((total - neto) * 100) / 100,
          total,
        };
      }
      const iva = Math.round(total * (pct / 100) * 100) / 100;
      return { neto: total, iva, total: Math.round((total + iva) * 100) / 100 };
    },
    [config.iva_porcentaje, config.iva_incluido_en_precio]
  );

  return (
    <ConfigContext.Provider value={{ config, cargando, recargar, money, desglosarIva }}>
      {children}
    </ConfigContext.Provider>
  );
}
