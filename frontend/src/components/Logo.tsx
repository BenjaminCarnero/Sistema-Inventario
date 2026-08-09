import { useState } from 'react';
import { useConfig } from './ConfigProvider';

interface LogoProps {
  size?: number;
  className?: string;
}

/** Ícono por defecto: etiqueta de precio con código de barras. */
function IconoPorDefecto({ size, className }: LogoProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" className={className}>
      <defs>
        <linearGradient id="logo-g" x1="4" y1="4" x2="60" y2="60" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="rgb(var(--color-brand))" />
          <stop offset="1" stopColor="rgb(var(--color-accent))" />
        </linearGradient>
      </defs>
      <rect width="64" height="64" rx="15" fill="url(#logo-g)" />
      <g transform="rotate(-8 32 32)">
        <rect x="15" y="20" width="34" height="24" rx="5" fill="#fff" />
        <circle cx="22" cy="27" r="2.6" fill="url(#logo-g)" />
        <rect x="27.5" y="24" width="3" height="16" rx="1" fill="#18181C" />
        <rect x="33.5" y="24" width="5" height="16" rx="1" fill="#18181C" />
        <rect x="41" y="24" width="3" height="16" rx="1" fill="#18181C" />
      </g>
    </svg>
  );
}

/**
 * Marca del comercio. Usa el logo cargado en Configuración; si no hay ninguno
 * (o la imagen no carga) cae al ícono por defecto, que sigue los colores
 * de marca configurados.
 */
export function LogoMark({ size = 40, className = '' }: LogoProps) {
  const { config } = useConfig();
  const [fallo, setFallo] = useState(false);
  const url = config.marca_logo_url?.trim();

  if (url && !fallo) {
    return (
      <img
        src={url}
        alt={config.negocio_nombre}
        width={size}
        height={size}
        onError={() => setFallo(true)}
        className={`rounded-xl object-contain ${className}`}
        style={{ width: size, height: size }}
      />
    );
  }

  return <IconoPorDefecto size={size} className={className} />;
}

export function Logo({ size = 40, className = '', subtitle }: LogoProps & { subtitle?: string }) {
  const { config } = useConfig();

  return (
    <div className={`flex items-center gap-3 ${className}`}>
      <LogoMark size={size} className="shrink-0 drop-shadow-[0_0_12px_rgb(var(--color-brand)/0.45)]" />
      <div className="leading-tight min-w-0">
        <h1 className="text-2xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-brand to-accent tracking-tight truncate">
          {config.negocio_nombre}
        </h1>
        {subtitle && <p className="text-xs text-text-muted font-medium tracking-wide">{subtitle}</p>}
      </div>
    </div>
  );
}
