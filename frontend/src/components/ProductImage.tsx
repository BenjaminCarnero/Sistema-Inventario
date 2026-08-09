import { useState } from 'react';
import { Package } from 'lucide-react';

interface ProductImageProps {
  src?: string | null;
  alt: string;
  className?: string;
  iconSize?: number;
}

/**
 * Miniatura del producto con fallback. Si no hay URL, o la imagen no carga
 * (link roto, sin internet), cae al ícono en vez de mostrar el ícono de
 * imagen rota del navegador.
 */
export function ProductImage({ src, alt, className = '', iconSize = 20 }: ProductImageProps) {
  const [fallo, setFallo] = useState(false);

  if (!src || fallo) {
    return (
      <div className={`flex items-center justify-center bg-white/5 ${className}`}>
        <Package size={iconSize} className="text-text-muted" />
      </div>
    );
  }

  return (
    <img
      src={src}
      alt={alt}
      loading="lazy"
      onError={() => setFallo(true)}
      className={`object-cover bg-white/5 ${className}`}
    />
  );
}
