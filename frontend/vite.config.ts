import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  server: {
    // Escucha en toda la red local para poder entrar desde el celular o la
    // tablet. El backend sigue atado a 127.0.0.1: el navegador le pega a la
    // API con rutas relativas y Vite hace de intermediario, así que alcanza
    // con exponer este único puerto.
    host: true,
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
