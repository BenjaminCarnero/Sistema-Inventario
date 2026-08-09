
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import Admin from './Admin.tsx'
import { UIProvider } from './components/UIProvider.tsx'
import { ConfigProvider } from './components/ConfigProvider.tsx'

function Navigation() {
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

createRoot(document.getElementById('root')!).render(
  <BrowserRouter>
    <UIProvider>
      <ConfigProvider>
        <Navigation />
        <Routes>
          <Route path="/" element={<App />} />
          <Route path="/admin" element={<Admin />} />
        </Routes>
      </ConfigProvider>
    </UIProvider>
  </BrowserRouter>
)
