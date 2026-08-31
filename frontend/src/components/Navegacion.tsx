import { Link, useLocation } from 'react-router-dom'

/**
 * Cambio entre el POS y el backoffice.
 *
 * Vive acá y no en `main.tsx` porque ese archivo es el punto de entrada: los
 * componentes definidos ahí no se pueden recargar en caliente mientras se
 * trabaja, así que cada retoque a estos botones obligaba a recargar la página
 * entera y perder el estado del carrito.
 */
export function Navegacion() {
  const { pathname } = useLocation();
  const linkClass = (active: boolean) =>
    `text-xs font-semibold px-3 py-1.5 rounded-full transition-colors ${
      active ? 'bg-brand text-white shadow-glow' : 'bg-neutral-bg3/80 hover:bg-neutral-bg4 text-text-secondary'
    }`;
  return (
    <div className="fixed top-3 right-3 p-1 z-50 flex gap-2 glass rounded-full">
      <Link to="/" className={linkClass(pathname === '/')}>POS</Link>
      <Link to="/admin" className={linkClass(pathname.startsWith('/admin'))}>Admin</Link>
    </div>
  )
}

/** Mientras baja el backoffice. Sin conexión no llega nunca: por eso lo dice. */
export function CargandoAdmin() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-3 text-text-secondary">
      <div className="w-8 h-8 border-2 border-brand border-t-transparent rounded-full animate-spin" />
      <p className="text-sm">Cargando el panel…</p>
      <p className="text-xs text-text-muted">Si no hay conexión, esta parte necesita señal.</p>
    </div>
  )
}
