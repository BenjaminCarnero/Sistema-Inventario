import { Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import { UIProvider } from './components/UIProvider.tsx'
import { ConfigProvider } from './components/ConfigProvider.tsx'
import { Navegacion, CargandoAdmin } from './components/Navegacion.tsx'

/**
 * El backoffice se carga recién cuando se entra a /admin.
 *
 * Es la mitad del peso de la aplicación y el cajero no lo abre nunca: iba en
 * el mismo paquete que el POS, así que una tablet con datos móviles se
 * descargaba el panel entero —dashboard, reportes, gráficos, exportación a
 * Excel— antes de poder cobrar la primera venta.
 */
const Admin = lazy(() => import('./Admin.tsx'))

createRoot(document.getElementById('root')!).render(
  <BrowserRouter>
    <UIProvider>
      <ConfigProvider>
        <Navegacion />
        <Routes>
          <Route path="/" element={<App />} />
          <Route
            path="/admin"
            element={
              <Suspense fallback={<CargandoAdmin />}>
                <Admin />
              </Suspense>
            }
          />
        </Routes>
      </ConfigProvider>
    </UIProvider>
  </BrowserRouter>
)
