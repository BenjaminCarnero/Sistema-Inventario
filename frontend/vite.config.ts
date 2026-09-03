import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

/**
 * Certificado propio para entrar por HTTPS desde el celular.
 *
 * Sin HTTPS el navegador no presta la cámara y el escáner queda inutilizable
 * justo en el dispositivo donde más sirve. Se genera con
 * `bash scripts/generar-certificado.sh` y no se sube al repositorio.
 *
 * Va detrás de `npm run dev:celular` y no del `npm run dev` de siempre: al
 * estar firmado por uno mismo, el navegador muestra una advertencia que en el
 * trabajo diario molesta y no aporta nada. Si falta el certificado, se avisa y
 * se sigue por HTTP en lugar de no arrancar.
 */
function certificadoLocal() {
  if (process.env.APPLIFY_HTTPS !== '1') return undefined

  const carpeta = fileURLToPath(new URL('./certs/', import.meta.url))
  const clave = `${carpeta}dev.key`
  const certificado = `${carpeta}dev.crt`

  if (!existsSync(clave) || !existsSync(certificado)) {
    console.warn(
      '\n  No hay certificado en frontend/certs/. Generalo con:\n' +
      '      bash scripts/generar-certificado.sh\n' +
      '  Por ahora se arranca por HTTP, sin cámara fuera de esta computadora.\n'
    )
    return undefined
  }
  return { key: readFileSync(clave), cert: readFileSync(certificado) }
}

export default defineConfig({
  server: {
    https: certificadoLocal(),
    // Escucha en toda la red local para poder entrar desde el celular o la
    // tablet. El backend sigue atado a 127.0.0.1: el navegador le pega a la
    // API con rutas relativas y Vite hace de intermediario, así que alcanza
    // con exponer este único puerto.
    host: true,
    // Vite rechaza las peticiones cuyo `Host` no reconoce, como defensa contra
    // el DNS rebinding. Sin esto, entrar por el nombre de Tailscale da un
    // "Blocked request" en vez de la app. Se permite el dominio de Tailscale en
    // general y no el de una máquina concreta: alcanza para que funcione y no
    // deja el nombre del tailnet escrito en un repositorio público.
    allowedHosts: ['.ts.net'],
    proxy: {
      '/auth': 'http://127.0.0.1:8001',
      '/productos': 'http://127.0.0.1:8001',
      '/ventas': 'http://127.0.0.1:8001',
      '/cajas': 'http://127.0.0.1:8001',
      '/reportes': 'http://127.0.0.1:8001',
      '/descuentos': 'http://127.0.0.1:8001',
      '/pagos': 'http://127.0.0.1:8001',
      '/configuracion': 'http://127.0.0.1:8001',
      '/categorias': 'http://127.0.0.1:8001',
      '/stock': 'http://127.0.0.1:8001',
      '/devoluciones': 'http://127.0.0.1:8001',
      '/proveedores': 'http://127.0.0.1:8001',
      '/pedidos': 'http://127.0.0.1:8001',
      // Estos dos faltaban: los routers existían en el backend desde hacía
      // rato, así que la primera pantalla que los usara habría fallado en
      // desarrollo con un error confuso —el servidor de Vite contestando el
      // index en vez de la API— y andado bien en producción.
      '/auditoria': 'http://127.0.0.1:8001',
      '/respaldos': 'http://127.0.0.1:8001',
      '/actualizaciones': 'http://127.0.0.1:8001',
      // Se descubrió faltante probando la impresión térmica de punta a punta
      // en el navegador: sin esto, "Imprimir" fallaba con un error de red
      // silencioso y caía al window.print() de siempre, que además puede
      // quedarse esperando un diálogo nativo que un navegador headless nunca
      // resuelve. Exactamente el mismo bug que ya se había dado con
      // /auditoria y /respaldos — este router es nuevo y quedó afuera igual.
      '/impresion': 'http://127.0.0.1:8001',
      '/logs': 'http://127.0.0.1:8001',
      // Lo usa el POS para saber si el servidor responde de verdad
      '/health': 'http://127.0.0.1:8001',
    }
  },
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg', 'apple-touch-icon.png', 'mask-icon.svg'],
      manifest: {
        name: 'APPLIFY POS',
        short_name: 'Applify',
        description: 'Punto de Venta Offline-First',
        theme_color: '#8251EE',
        background_color: '#0F0F13',
        display: 'standalone',
        icons: [
          {
            src: 'pwa-192x192.png',
            sizes: '192x192',
            type: 'image/png',
            purpose: 'any'
          },
          {
            src: 'pwa-512x512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'any'
          },
          {
            src: 'pwa-512x512-maskable.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable'
          }
        ]
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg}'],
        runtimeCaching: [
          {
            urlPattern: /^https:\/\/api\.applify\.local\/.*$/i,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-cache',
              expiration: {
                maxEntries: 100,
                maxAgeSeconds: 60 * 60 * 24 * 7 // 7 days
              },
              networkTimeoutSeconds: 5
            }
          }
        ]
      }
    })
  ]
})
