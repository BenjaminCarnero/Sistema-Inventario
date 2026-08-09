import { useState, useEffect, useRef } from 'react';
import { Package, LayoutDashboard, Settings, LogOut, Plus, CloudDownload, ScanLine, Edit2, PieChart, Printer, Search, Users, X, CameraOff, Image as ImageIcon, Tag, AlertTriangle, FileSpreadsheet, TrendingUp } from 'lucide-react';
import Barcode from 'react-barcode';
import { Html5QrcodeScanner, Html5QrcodeSupportedFormats } from 'html5-qrcode';
import { motion, AnimatePresence } from 'framer-motion';
import { db } from './db';
import { useLiveQuery } from 'dexie-react-hooks';
import { api } from './api';
import { useUI } from './components/UIProvider';
import { Logo, LogoMark } from './components/Logo';
import { Skeleton, EmptyState } from './components/Skeleton';
import { TopProductosChart } from './components/TopProductosChart';
import { ProductImage } from './components/ProductImage';
import { ConfiguracionPanel } from './components/ConfiguracionPanel';
import { useConfig } from './components/ConfigProvider';
import { useCameraAvailability } from './useCamera';
import { sincronizarCatalogo, paraCatalogoLocal } from './catalogoLocal';

function getUserRole() {
  const token = localStorage.getItem('token');
  if (!token) return null;
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    return payload.rol;
  } catch (e) {
    return null;
  }
}

function getUsername() {
  const token = localStorage.getItem('token');
  if (!token) return null;
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    return payload.sub;
  } catch (e) {
    return null;
  }
}

function Admin() {
  const { showToast, confirm } = useUI();
  const { config, money } = useConfig();
  const userRole = getUserRole();
  const [activeTab, setActiveTab] = useState(userRole === 3 ? 'productos' : 'dashboard');
  const [loadingDashboard, setLoadingDashboard] = useState(true);
  const [loadingReportes, setLoadingReportes] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(!!localStorage.getItem('token'));
  
  // Login Form States
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  // New/Edit Product Form States
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [newProd, setNewProd] = useState({ codigo_barras: '', nombre: '', precio_venta: 0, costo: 0, stock_actual: 0, imagen_url: '' });
  const [showScanner, setShowScanner] = useState(false);
  const cameraStatus = useCameraAvailability();
  const scannerRef = useRef<Html5QrcodeScanner | null>(null);

  // Reportes States
  const [kpi, setKpi] = useState<any>(null);
  const [topProductos, setTopProductos] = useState<any[]>([]);
  const [historialCajas, setHistorialCajas] = useState<any[]>([]);
  const [selectedCaja, setSelectedCaja] = useState<any>(null);
  const [ventasCaja, setVentasCaja] = useState<any[]>([]);

  // User Creation States
  const [newUser, setNewUser] = useState({ nombre: '', pin_acceso: '', rol_id: 3 });
  const [usuarios, setUsuarios] = useState<any[]>([]);
  const [loadingUsuarios, setLoadingUsuarios] = useState(true);

  // Descuentos
  const [descuentos, setDescuentos] = useState<any[]>([]);
  const [loadingDescuentos, setLoadingDescuentos] = useState(true);
  const [editandoDescuento, setEditandoDescuento] = useState<number | null>(null);
  const NUEVO_DESCUENTO = { nombre: '', codigo_promocional: '', tipo: 'PORCENTAJE', valor: 0, producto_id: '', activo: true, fecha_inicio: '', fecha_fin: '' };
  const [nuevoDescuento, setNuevoDescuento] = useState<any>(NUEVO_DESCUENTO);

  // Alertas de stock
  // El umbral vive en la configuración del servidor para que sea el mismo
  // para todos los usuarios, no una preferencia por navegador.
  const umbralStock = config.umbral_stock_bajo || 5;
  const [stockBajo, setStockBajo] = useState<any[]>([]);
  const alertaStockMostrada = useRef(false);

  // Rentabilidad y exportación
  const [rentabilidad, setRentabilidad] = useState<any[]>([]);
  const hoyISO = new Date().toISOString().split('T')[0];
  const hace30 = new Date(Date.now() - 29 * 86400000).toISOString().split('T')[0];
  const [rangoDesde, setRangoDesde] = useState(hace30);
  const [rangoHasta, setRangoHasta] = useState(hoyISO);
  const [exportando, setExportando] = useState(false);

  // Orden del catálogo
  const [ordenProductos, setOrdenProductos] = useState<'nombre' | 'stock' | 'precio'>('nombre');

  // Sub-pestaña dentro de Configuración
  const [subTabConfig, setSubTabConfig] = useState<'sistema' | 'usuarios'>('sistema');

  const playBeep = () => {
    try {
      const AudioContext = window.AudioContext || (window as any).webkitAudioContext;
      const ctx = new AudioContext();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.type = "sine";
      osc.frequency.value = 800;
      gain.gain.setValueAtTime(0, ctx.currentTime);
      gain.gain.linearRampToValueAtTime(1, ctx.currentTime + 0.02);
      gain.gain.linearRampToValueAtTime(0, ctx.currentTime + 0.15);
      osc.start(ctx.currentTime);
      osc.stop(ctx.currentTime + 0.2);
    } catch (e) {
      console.warn("Audio not supported or blocked", e);
    }
  };

  useEffect(() => {
    // Sólo montamos el escáner si ya sabemos que hay cámara: así no se dispara
    // el diálogo de permisos en equipos sin webcam.
    if (!showScanner || cameraStatus !== 'available') return;

    const scanner = new Html5QrcodeScanner("admin-reader", {
      fps: 15,
      qrbox: {width: 250, height: 100},
      showTorchButtonIfSupported: true,
      formatsToSupport: [
        Html5QrcodeSupportedFormats.EAN_13,
        Html5QrcodeSupportedFormats.EAN_8,
        Html5QrcodeSupportedFormats.UPC_A,
        Html5QrcodeSupportedFormats.UPC_E,
        Html5QrcodeSupportedFormats.CODE_128,
        Html5QrcodeSupportedFormats.QR_CODE
      ]
    }, false);
    scannerRef.current = scanner;

    scanner.render(async (decodedText) => {
      playBeep();
      setShowScanner(false);

      // Autocompletar código
      setNewProd(prev => ({ ...prev, codigo_barras: decodedText }));

      // Autocompletar nombre e imagen con Open Food Facts
      try {
        const res = await fetch(`https://world.openfoodfacts.org/api/v0/product/${decodedText}.json`);
        const data = await res.json();
        if (data.status === 1 && data.product) {
          const nombre = data.product.product_name;
          const imagen = data.product.image_front_url || data.product.image_url;
          if (nombre || imagen) {
            setNewProd(prev => ({
              ...prev,
              ...(nombre ? { nombre } : {}),
              ...(imagen ? { imagen_url: imagen } : {})
            }));
            showToast('Datos del producto autocompletados', 'success');
          }
        }
      } catch (e) {
        console.error("Error fetching product data", e);
      }
    }, () => {});

    return () => {
      if (scannerRef.current) {
        scannerRef.current.clear().catch(e => console.warn(e));
        scannerRef.current = null;
      }
    };
  }, [showScanner, cameraStatus]);

  useEffect(() => {
    if (isAuthenticated) {
      if (activeTab === 'dashboard') {
        setLoadingDashboard(true);
        Promise.all([
          api.getKpi().then(setKpi),
          api.getTopProductos().then(setTopProductos),
          api.getRentabilidad().then(setRentabilidad),
        ])
          .catch(console.error)
          .finally(() => setLoadingDashboard(false));
      } else if (activeTab === 'reportes') {
        setLoadingReportes(true);
        api.getHistorialCajas().then(setHistorialCajas).catch(console.error).finally(() => setLoadingReportes(false));
      } else if (activeTab === 'descuentos') {
        cargarDescuentos();
      } else if (activeTab === 'configuracion' && getUserRole() === 1) {
        setLoadingUsuarios(true);
        api.getUsuarios().then(setUsuarios).catch(console.error).finally(() => setLoadingUsuarios(false));
      }
    }
  }, [isAuthenticated, activeTab]);

  // Alerta de stock bajo: se consulta al servidor al entrar y cada vez que
  // cambia el umbral. El aviso emergente aparece una sola vez por sesión.
  useEffect(() => {
    if (!isAuthenticated || userRole === 3) return;
    api.getStockBajo(umbralStock)
      .then(productos => {
        setStockBajo(productos);
        if (productos.length > 0 && !alertaStockMostrada.current) {
          alertaStockMostrada.current = true;
          showToast(
            `${productos.length} producto${productos.length > 1 ? 's' : ''} con stock bajo`,
            'error'
          );
        }
      })
      .catch(console.error);
  }, [isAuthenticated, umbralStock, userRole]);

  const cargarDescuentos = () => {
    setLoadingDescuentos(true);
    api.getDescuentos().then(setDescuentos).catch(console.error).finally(() => setLoadingDescuentos(false));
  };

  // IndexedDB data
  const localProductos = useLiveQuery(() => db.productos.toArray()) || [];

  // Filters state
  const [searchTerm, setSearchTerm] = useState('');
  const [lowStockFilter, setLowStockFilter] = useState(false);
  const [barcodeProduct, setBarcodeProduct] = useState<any>(null);

  const filteredProductos = localProductos
    .filter(p => {
      const termino = searchTerm.trim().toLowerCase();
      if (termino && !p.nombre.toLowerCase().includes(termino) && !p.codigo_barras.includes(termino)) return false;
      if (lowStockFilter && p.stock_actual >= umbralStock) return false;
      return true;
    })
    .sort((a, b) => {
      if (ordenProductos === 'stock') return a.stock_actual - b.stock_actual;
      if (ordenProductos === 'precio') return b.precio_venta - a.precio_venta;
      return a.nombre.localeCompare(b.nombre);
    });

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.login(username, password);
      setIsAuthenticated(true);
      const newRole = getUserRole();
      if (newRole === 3) setActiveTab('productos');
      else setActiveTab('dashboard');
      syncCatalog(); // Sincronizar al iniciar sesión
    } catch (err: any) {
      showToast("Error: " + err.message, 'error');
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    setIsAuthenticated(false);
  };

  const syncCatalog = async (avisar = false) => {
    try {
      const cantidad = await sincronizarCatalogo(await api.getProductos());
      if (avisar) showToast(`Catálogo sincronizado (${cantidad} productos)`, 'success');
    } catch (err: any) {
      console.error("Error al sincronizar: " + err.message);
      showToast("No se pudo sincronizar el catálogo: " + err.message, 'error');
    }
  };

  const handleGuardarDescuento = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const payload = {
        nombre: nuevoDescuento.nombre,
        codigo_promocional: nuevoDescuento.codigo_promocional?.trim() || null,
        tipo: nuevoDescuento.tipo,
        valor: Number(nuevoDescuento.valor),
        producto_id: nuevoDescuento.producto_id ? Number(nuevoDescuento.producto_id) : null,
        activo: nuevoDescuento.activo,
        fecha_inicio: nuevoDescuento.fecha_inicio ? `${nuevoDescuento.fecha_inicio}T00:00:00` : null,
        fecha_fin: nuevoDescuento.fecha_fin ? `${nuevoDescuento.fecha_fin}T23:59:59` : null,
      };

      if (editandoDescuento) {
        await api.updateDescuento(editandoDescuento, payload);
        showToast('Descuento actualizado', 'success');
      } else {
        await api.createDescuento(payload);
        showToast('Descuento creado', 'success');
      }

      setNuevoDescuento(NUEVO_DESCUENTO);
      setEditandoDescuento(null);
      cargarDescuentos();
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  const handleEditarDescuento = (d: any) => {
    setNuevoDescuento({
      nombre: d.nombre,
      codigo_promocional: d.codigo_promocional || '',
      tipo: d.tipo,
      valor: d.valor,
      producto_id: d.producto_id ?? '',
      activo: d.activo,
      fecha_inicio: d.fecha_inicio ? d.fecha_inicio.split('T')[0] : '',
      fecha_fin: d.fecha_fin ? d.fecha_fin.split('T')[0] : '',
    });
    setEditandoDescuento(d.id);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleEliminarDescuento = async (d: any) => {
    const ok = await confirm({
      title: 'Eliminar descuento',
      message: `¿Eliminar "${d.nombre}"? Si ya se usó en alguna venta, se desactivará en lugar de borrarse para no romper los reportes.`,
      confirmText: 'Eliminar',
      danger: true,
    });
    if (!ok) return;
    try {
      await api.deleteDescuento(d.id);
      showToast('Descuento eliminado', 'success');
      cargarDescuentos();
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  const handleExportarExcel = async () => {
    setExportando(true);
    try {
      const ventas = await api.getVentasPeriodo(rangoDesde, rangoHasta);
      if (ventas.length === 0) {
        showToast('No hay ventas en el período seleccionado', 'error');
        return;
      }
      const { exportarVentasExcel } = await import('./exportExcel');
      await exportarVentasExcel(ventas, rangoDesde, rangoHasta);
      showToast(`Excel generado con ${ventas.length} ventas`, 'success');
    } catch (err: any) {
      showToast('Error exportando: ' + err.message, 'error');
    } finally {
      setExportando(false);
    }
  };

  const exportToCSV = () => {
    let csv = "ID Turno,Cajero,Apertura,Cierre,Monto Inicial,Ventas Efectivo,Monto Declarado,Diferencia,Estado\n";
    historialCajas.forEach((c: any) => {
      csv += `${c.id},${c.cajero_nombre},${c.fecha_apertura},${c.fecha_cierre || ''},${c.monto_inicial},${c.total_ventas_turno || 0},${c.monto_final_declarado || 0},${c.diferencia_calculada || 0},${c.fecha_cierre ? 'Cerrada' : 'Abierta'}\n`;
    });
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `reporte_cajas_${new Date().toISOString().split('T')[0]}.csv`;
    link.click();
  };

  const verVentasCaja = async (caja: any) => {
    try {
      const ventas = await api.getVentasCaja(caja.id);
      setSelectedCaja(caja);
      setVentasCaja(ventas);
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  const handleSaveProduct = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      // Enviamos null en vez de string vacío para que la imagen quede sin definir
      const payload = { ...newProd, imagen_url: newProd.imagen_url?.trim() || null };

      let guardado;
      if (editingId) {
        guardado = await api.updateProducto(editingId, payload);
      } else {
        guardado = await api.createProducto(payload);
      }

      // Actualizar IndexedDB para que el POS local lo vea (sin el costo)
      await db.productos.put(paraCatalogoLocal(guardado));

      setShowAddForm(false);
      setEditingId(null);
      setNewProd({ codigo_barras: '', nombre: '', precio_venta: 0, costo: 0, stock_actual: 0, imagen_url: '' });
      showToast(editingId ? 'Producto actualizado correctamente' : 'Producto creado correctamente', 'success');
    } catch (err: any) {
      showToast("Error al guardar el producto: " + err.message, 'error');
    }
  };

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.registerUser(newUser.nombre, newUser.pin_acceso, newUser.rol_id);
      showToast("Usuario creado exitosamente", 'success');
      setNewUser({ nombre: '', pin_acceso: '', rol_id: 3 });
      api.getUsuarios().then(setUsuarios).catch(console.error);
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  const handleDeleteUser = async (u: any) => {
    const ok = await confirm({
      title: 'Eliminar usuario',
      message: `¿Estás seguro de que deseas eliminar a ${u.nombre}? Sus ventas pasadas se conservarán en los reportes.`,
      confirmText: 'Eliminar',
      danger: true,
    });
    if (!ok) return;
    try {
      await api.deleteUsuario(u.id);
      api.getUsuarios().then(setUsuarios).catch(console.error);
      showToast(`Usuario ${u.nombre} eliminado`, 'success');
    } catch (err: any) {
      showToast("Error eliminando usuario: " + err.message, 'error');
    }
  };

  const handleToggleRolUser = async (u: any) => {
    const newRol = u.rol_id === 1 ? 2 : (u.rol_id === 2 ? 3 : 1);
    try {
      await api.updateUsuario(u.id, { nombre: u.nombre, rol_id: newRol, estado: u.estado });
      api.getUsuarios().then(setUsuarios).catch(console.error);
    } catch (err: any) {
      showToast("Error actualizando rol: " + err.message, 'error');
    }
  };

  const startEdit = async (p: any) => {
    // El catálogo local ya no guarda el costo (es información del negocio y no
    // debe quedar en el equipo del cajero), así que para editar se pide el
    // producto completo al servidor.
    let completo = p;
    try {
      const delServidor = await api.getProductos();
      completo = delServidor.find((x: any) => x.id === p.id) || p;
    } catch {
      showToast('No se pudo traer el costo del servidor: revisá ese campo antes de guardar', 'error');
    }

    setNewProd({
      codigo_barras: completo.codigo_barras,
      nombre: completo.nombre,
      precio_venta: completo.precio_venta,
      costo: completo.costo ?? 0,
      stock_actual: completo.stock_actual,
      imagen_url: completo.imagen_url || ''
    });
    setEditingId(p.id);
    setShowAddForm(true);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-neutral-bg1 flex items-center justify-center text-text-primary p-4">
        <div className="glass-card p-8 w-full max-w-md">
          <div className="flex justify-center mb-6">
            <Logo size={52} subtitle="Backoffice" />
          </div>
          <form onSubmit={handleLogin} className="flex flex-col gap-4">
            <input 
              className="glass-input p-3 rounded-lg" type="text" placeholder="Usuario" 
              value={username} onChange={e => setUsername(e.target.value)} required 
            />
            <input 
              className="glass-input p-3 rounded-lg" type="password" placeholder="PIN de Acceso" 
              value={password} onChange={e => setPassword(e.target.value)} required 
            />
            <button type="submit" className="bg-brand hover:bg-brand-hover text-white py-3 rounded-lg font-bold transition-colors">
              Ingresar al Panel
            </button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-neutral-bg1 flex flex-col md:flex-row text-text-primary pb-20 md:pb-0">
      {/* Sidebar Desktop */}
      <aside className="hidden md:flex w-64 glass border-r border-border-subtle p-6 flex-col gap-6">
        <Logo size={36} subtitle="Backoffice" />
        {/* Sidebar Nav */}
        <nav className="flex-1 flex flex-col gap-1 mt-8">
          {userRole !== 3 && (
            <button
              onClick={() => setActiveTab('dashboard')}
              className={`flex items-center gap-3 px-4 py-3 rounded-xl font-medium transition-colors border-l-2 ${activeTab === 'dashboard' ? 'bg-brand/15 text-brand-light border-l-brand' : 'hover:bg-white/5 text-text-secondary border-l-transparent'}`}
            >
              <LayoutDashboard size={20} /> Resumen
            </button>
          )}
          <button
            onClick={() => setActiveTab('productos')}
            className={`flex items-center justify-between gap-3 px-4 py-3 rounded-xl font-medium transition-colors border-l-2 ${activeTab === 'productos' ? 'bg-brand/15 text-brand-light border-l-brand' : 'hover:bg-white/5 text-text-secondary border-l-transparent'}`}
          >
            <span className="flex items-center gap-3"><Package size={20} /> Catálogo</span>
            {stockBajo.length > 0 && (
              <span className="bg-status-error text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full min-w-[18px] text-center">
                {stockBajo.length}
              </span>
            )}
          </button>
          {userRole !== 3 && (
            <button
              onClick={() => setActiveTab('descuentos')}
              className={`flex items-center gap-3 px-4 py-3 rounded-xl font-medium transition-colors border-l-2 ${activeTab === 'descuentos' ? 'bg-brand/15 text-brand-light border-l-brand' : 'hover:bg-white/5 text-text-secondary border-l-transparent'}`}
            >
              <Tag size={20} /> Descuentos
            </button>
          )}
          {userRole !== 3 && (
            <button
              onClick={() => setActiveTab('reportes')}
              className={`flex items-center gap-3 px-4 py-3 rounded-xl font-medium transition-colors border-l-2 ${activeTab === 'reportes' ? 'bg-brand/15 text-brand-light border-l-brand' : 'hover:bg-white/5 text-text-secondary border-l-transparent'}`}
            >
              <PieChart size={20} /> Reportes y Cajas
            </button>
          )}
          {userRole === 1 && (
            <button
              onClick={() => setActiveTab('configuracion')}
              className={`flex items-center gap-3 px-4 py-3 rounded-xl font-medium transition-colors border-l-2 ${activeTab === 'configuracion' ? 'bg-brand/15 text-brand-light border-l-brand' : 'hover:bg-white/5 text-text-secondary border-l-transparent'}`}
            >
              <Settings size={20} /> Configuración
            </button>
          )}
        </nav>

        <div className="flex items-center gap-3 px-2 py-3 border-t border-border-subtle">
          <div className="w-9 h-9 rounded-full bg-gradient-to-br from-brand to-accent flex items-center justify-center font-bold text-white shrink-0">
            {getUsername()?.[0]?.toUpperCase() || '?'}
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold truncate">{getUsername() || 'Usuario'}</p>
            <p className="text-xs text-text-muted">{userRole === 1 ? 'Administrador' : (userRole === 2 ? 'Encargado' : 'Cajero')}</p>
          </div>
          <button onClick={handleLogout} title="Salir" className="p-2 rounded-lg hover:bg-white/5 text-status-error transition-colors shrink-0">
            <LogOut size={18} />
          </button>
        </div>
      </aside>

      {/* Mobile Bottom Navigation */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 glass border-t border-white/10 flex justify-around items-center p-3 z-50">
        {userRole !== 3 && (
          <button onClick={() => setActiveTab('dashboard')} className={`p-2 rounded-lg flex flex-col items-center gap-1 ${activeTab === 'dashboard' ? 'text-brand-light' : 'text-text-secondary'}`}>
            <LayoutDashboard size={24} />
            <span className="text-[10px]">Inicio</span>
          </button>
        )}
        <button onClick={() => setActiveTab('productos')} className={`relative p-2 rounded-lg flex flex-col items-center gap-1 ${activeTab === 'productos' ? 'text-brand-light' : 'text-text-secondary'}`}>
          <Package size={24} />
          {stockBajo.length > 0 && (
            <span className="absolute top-0 right-0 bg-status-error text-white text-[9px] font-bold px-1 rounded-full min-w-[15px] text-center">
              {stockBajo.length}
            </span>
          )}
          <span className="text-[10px]">Catálogo</span>
        </button>
        {userRole !== 3 && (
          <button onClick={() => setActiveTab('descuentos')} className={`p-2 rounded-lg flex flex-col items-center gap-1 ${activeTab === 'descuentos' ? 'text-brand-light' : 'text-text-secondary'}`}>
            <Tag size={24} />
            <span className="text-[10px]">Descuentos</span>
          </button>
        )}
        {userRole !== 3 && (
          <button onClick={() => setActiveTab('reportes')} className={`p-2 rounded-lg flex flex-col items-center gap-1 ${activeTab === 'reportes' ? 'text-brand-light' : 'text-text-secondary'}`}>
            <PieChart size={24} />
            <span className="text-[10px]">Reportes</span>
          </button>
        )}
        {userRole === 1 && (
          <button onClick={() => setActiveTab('configuracion')} className={`p-2 rounded-lg flex flex-col items-center gap-1 ${activeTab === 'configuracion' ? 'text-brand-light' : 'text-text-secondary'}`}>
            <Settings size={24} />
            <span className="text-[10px]">Ajustes</span>
          </button>
        )}
        <button onClick={handleLogout} className="p-2 rounded-lg flex flex-col items-center gap-1 text-status-error">
          <LogOut size={24} />
          <span className="text-[10px]">Salir</span>
        </button>
      </nav>

      {/* Main Content */}
      <main className="flex-1 p-4 md:p-8 overflow-y-auto">
        <div className="md:hidden flex items-center gap-2 mb-6">
          <LogoMark size={28} />
          <span className="font-bold text-brand-light tracking-tight truncate">{config.negocio_nombre} · Backoffice</span>
        </div>
        <header className="flex flex-col md:flex-row justify-between items-start md:items-center mb-8 gap-4">
          <h2 className="text-3xl font-bold">
            {activeTab === 'dashboard' && 'Resumen General (En Vivo)'}
            {activeTab === 'productos' && 'Gestión de Catálogo (Real)'}
            {activeTab === 'descuentos' && 'Descuentos y Promociones'}
            {activeTab === 'reportes' && 'Auditoría y Reportes de Caja'}
            {activeTab === 'configuracion' && 'Configuración del Sistema'}
          </h2>
          <div className="flex items-center gap-4">
            <button onClick={() => syncCatalog(true)} className="flex items-center gap-2 text-sm px-3 py-2 bg-neutral-bg3 hover:bg-neutral-bg4 rounded-lg text-text-secondary transition-colors">
              <CloudDownload size={16} /> Sincronizar DB Local
            </button>
            <span className="text-sm px-3 py-1 glass rounded-full text-brand-light border-brand/30">
              Nivel: {userRole === 1 ? 'Admin' : (userRole === 2 ? 'Encargado' : 'Cajero')}
            </span>
          </div>
        </header>

        {activeTab === 'dashboard' && (
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
            {loadingDashboard ? (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
                <Skeleton className="h-28" />
                <Skeleton className="h-28" />
                <Skeleton className="h-28" />
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
                <div className="glass-card p-6 border-l-4 border-l-status-success">
                  <h3 className="text-text-secondary text-sm font-medium mb-2">Recaudación Hoy (Real)</h3>
                  <p className="text-3xl font-bold text-brand-light">{money(kpi?.ventas_hoy_local || 0)}</p>
                  <p className="text-xs text-text-muted mt-2">{kpi?.cantidad_ventas_hoy || 0} tickets emitidos</p>
                </div>
                <div className="glass-card p-6 border-l-4 border-l-status-info">
                  <h3 className="text-text-secondary text-sm font-medium mb-2">Método Preferido Hoy</h3>
                  <p className="text-3xl font-bold text-text-primary">{kpi?.metodo_pago_preferido || 'N/A'}</p>
                </div>
                <div className="glass-card p-6">
                  <h3 className="text-text-secondary text-sm font-medium mb-2">Ingresos del Día</h3>
                  <p className="text-3xl font-bold text-status-success">{money(kpi?.ventas_hoy_local || 0)}</p>
                  <p className="text-xs text-text-muted mt-2">{kpi?.cantidad_ventas_hoy || 0} ventas registradas hoy</p>
                </div>
              </div>
            )}

            <div className="glass-card p-6 mb-8">
              <h3 className="text-xl font-semibold mb-6">Recaudación por Producto (Top 5)</h3>
              {loadingDashboard ? (
                <Skeleton className="h-64" />
              ) : topProductos.length > 0 ? (
                <TopProductosChart data={topProductos} />
              ) : (
                <EmptyState icon={PieChart} title="Sin datos de ventas todavía" description="El gráfico aparecerá aquí en cuanto se registren ventas." />
              )}
            </div>

            <div className="glass-card p-6">
              <h3 className="text-xl font-semibold mb-6">Productos Más Vendidos (Top 5)</h3>
              {loadingDashboard ? (
                <Skeleton className="h-40" />
              ) : topProductos.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-left">
                    <thead>
                      <tr className="border-b border-white/10 text-text-secondary">
                        <th className="pb-3 font-medium">Producto</th>
                        <th className="pb-3 font-medium text-right">Cantidad</th>
                        <th className="pb-3 font-medium text-right">Recaudado</th>
                      </tr>
                    </thead>
                    <tbody>
                      {topProductos.map(tp => (
                        <tr key={tp.id} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                          <td className="py-4 font-medium">{tp.nombre}</td>
                          <td className="py-4 text-right text-brand-light font-bold">{tp.cantidad_vendida}</td>
                          <td className="py-4 text-right">{money(tp.total_recaudado)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-text-muted">Aún no hay suficientes ventas registradas para el ranking.</p>
              )}
            </div>

            {/* Rentabilidad por producto */}
            <div className="glass-card p-6 mt-8">
              <h3 className="text-xl font-semibold mb-2 flex items-center gap-2">
                <TrendingUp size={20} className="text-status-success" /> Rentabilidad por Producto
              </h3>
              <p className="text-sm text-text-muted mb-6">Ganancia = recaudado − costo de las unidades vendidas.</p>
              {loadingDashboard ? (
                <Skeleton className="h-40" />
              ) : rentabilidad.length === 0 ? (
                <EmptyState icon={TrendingUp} title="Sin datos de rentabilidad" description="Se calcula a partir del costo cargado en cada producto y las ventas registradas." />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr className="border-b border-white/10 text-text-secondary">
                        <th className="pb-3 font-medium">Producto</th>
                        <th className="pb-3 font-medium text-right">Vendidos</th>
                        <th className="pb-3 font-medium text-right">Recaudado</th>
                        <th className="pb-3 font-medium text-right">Costo</th>
                        <th className="pb-3 font-medium text-right">Ganancia</th>
                        <th className="pb-3 font-medium text-right">Margen</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rentabilidad.map(r => (
                        <tr key={r.id} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                          <td className="py-3 font-medium">{r.nombre}</td>
                          <td className="py-3 text-right">{r.cantidad_vendida}</td>
                          <td className="py-3 text-right">{money(r.total_recaudado)}</td>
                          <td className="py-3 text-right text-text-muted">{money(r.costo_total)}</td>
                          <td className={`py-3 text-right font-bold ${r.ganancia >= 0 ? 'text-status-success' : 'text-status-error'}`}>{money(r.ganancia)}</td>
                          <td className="py-3 text-right">
                            <span className={`px-2 py-1 rounded-full text-xs font-bold ${
                              r.margen_pct >= 30 ? 'bg-status-success/20 text-status-success'
                              : r.margen_pct >= 0 ? 'bg-status-warning/20 text-status-warning'
                              : 'bg-status-error/20 text-status-error'
                            }`}>
                              {r.margen_pct.toFixed(1)}%
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </motion.div>
        )}

        {activeTab === 'reportes' && (
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
            {/* Exportación por período */}
            <div className="glass-card p-6 mb-8">
              <h3 className="text-xl font-semibold mb-2 flex items-center gap-2">
                <FileSpreadsheet size={20} className="text-status-success" /> Exportar ventas a Excel
              </h3>
              <p className="text-sm text-text-muted mb-5">
                Genera un archivo .xlsx con dos hojas: un resumen por venta y el detalle por producto.
              </p>
              <div className="flex flex-col md:flex-row md:items-end gap-4">
                <div className="flex-1">
                  <label className="block text-xs text-text-secondary mb-1 uppercase tracking-wide">Desde</label>
                  <input
                    type="date"
                    max={rangoHasta}
                    className="glass-input w-full p-3 rounded-lg"
                    value={rangoDesde}
                    onChange={e => setRangoDesde(e.target.value)}
                  />
                </div>
                <div className="flex-1">
                  <label className="block text-xs text-text-secondary mb-1 uppercase tracking-wide">Hasta</label>
                  <input
                    type="date"
                    min={rangoDesde}
                    className="glass-input w-full p-3 rounded-lg"
                    value={rangoHasta}
                    onChange={e => setRangoHasta(e.target.value)}
                  />
                </div>
                <button
                  onClick={handleExportarExcel}
                  disabled={exportando || !rangoDesde || !rangoHasta}
                  className="bg-status-success hover:bg-green-600 disabled:bg-neutral-bg4 disabled:text-text-muted text-white font-bold px-6 py-3 rounded-xl transition-colors flex items-center justify-center gap-2 shrink-0"
                >
                  <FileSpreadsheet size={18} />
                  {exportando ? 'Generando…' : 'Descargar Excel'}
                </button>
              </div>
            </div>

            <div className="glass-card p-6">
              <div className="flex justify-between items-center mb-6 gap-3 flex-wrap">
                <h3 className="text-xl font-semibold">Historial de Turnos y Arqueos de Caja</h3>
                <div className="flex gap-2">
                  <button onClick={exportToCSV} className="bg-white/10 hover:bg-white/20 px-3 py-1.5 rounded text-sm transition-colors flex items-center gap-2">
                    <CloudDownload size={16} /> CSV
                  </button>
                  <button onClick={() => window.print()} className="bg-brand/20 hover:bg-brand/40 text-brand-light px-3 py-1.5 rounded text-sm transition-colors flex items-center gap-2">
                    <Printer size={16} /> Imprimir
                  </button>
                </div>
              </div>
              {loadingReportes ? (
                <div className="space-y-2">
                  <Skeleton className="h-10" />
                  <Skeleton className="h-10" />
                  <Skeleton className="h-10" />
                </div>
              ) : historialCajas.length === 0 ? (
                <EmptyState icon={PieChart} title="No hay registros de caja todavía" description="Los turnos abiertos y cerrados por los cajeros aparecerán aquí." />
              ) : (
                <>
                  {/* Vista tabla (desktop) */}
                  <div className="hidden md:block overflow-x-auto">
                    <table className="w-full text-left">
                      <thead>
                        <tr className="border-b border-white/10 text-text-secondary text-sm">
                          <th className="pb-3 font-medium">Cajero</th>
                          <th className="pb-3 font-medium">Apertura</th>
                          <th className="pb-3 font-medium">Cierre</th>
                          <th className="pb-3 font-medium text-right">Inicial</th>
                          <th className="pb-3 font-medium text-right">Ventas</th>
                          <th className="pb-3 font-medium text-right">Declarado</th>
                          <th className="pb-3 font-medium text-right">Diferencia</th>
                          <th className="pb-3 font-medium text-center">Estado</th>
                        </tr>
                      </thead>
                      <tbody>
                        {historialCajas.map(c => (
                          <tr key={c.id} className="border-b border-white/5 hover:bg-white/5 transition-colors text-sm">
                            <td className="py-3 font-medium">
                              <button onClick={() => verVentasCaja(c)} className="text-brand-light hover:underline flex items-center gap-1">
                                {c.cajero_nombre}
                              </button>
                            </td>
                            <td className="py-3 text-xs">{new Date(c.fecha_apertura).toLocaleString()}</td>
                            <td className="py-3 text-xs">{c.fecha_cierre ? new Date(c.fecha_cierre).toLocaleString() : '-'}</td>
                            <td className="py-3 text-right">{money(c.monto_inicial)}</td>
                            <td className="py-3 text-right text-brand-light font-bold">{money(c.total_ventas_turno || 0)}</td>
                            <td className="py-3 text-right">{c.monto_final_declarado !== null ? money(c.monto_final_declarado) : "-"}</td>
                            <td className={`py-3 text-right font-bold ${c.diferencia_calculada !== null ? (c.diferencia_calculada < 0 ? 'text-status-error' : c.diferencia_calculada > 0 ? 'text-status-warning' : 'text-status-success') : ''}`}>
                              {c.diferencia_calculada !== null ? money(c.diferencia_calculada) : "-"}
                            </td>
                            <td className="py-3 text-center">
                              {c.fecha_cierre ? (
                                <span className="bg-neutral-bg3 text-text-secondary px-2 py-1 rounded-full text-xs">Cerrada</span>
                              ) : (
                                <span className="bg-status-success/20 text-status-success px-2 py-1 rounded-full text-xs font-bold animate-pulse">Abierta</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {/* Vista tarjetas (móvil) */}
                  <div className="md:hidden space-y-3">
                    {historialCajas.map(c => (
                      <button key={c.id} onClick={() => verVentasCaja(c)} className="w-full text-left glass rounded-xl p-4">
                        <div className="flex justify-between items-start mb-2">
                          <span className="font-semibold text-brand-light">{c.cajero_nombre}</span>
                          {c.fecha_cierre ? (
                            <span className="bg-neutral-bg3 text-text-secondary px-2 py-1 rounded-full text-xs">Cerrada</span>
                          ) : (
                            <span className="bg-status-success/20 text-status-success px-2 py-1 rounded-full text-xs font-bold animate-pulse">Abierta</span>
                          )}
                        </div>
                        <p className="text-xs text-text-muted mb-3">{new Date(c.fecha_apertura).toLocaleString()}</p>
                        <div className="flex justify-between text-sm">
                          <span className="text-text-secondary">Ventas del turno</span>
                          <span className="font-bold text-brand-light">{money(c.total_ventas_turno || 0)}</span>
                        </div>
                        {c.diferencia_calculada !== null && (
                          <div className="flex justify-between text-sm mt-1">
                            <span className="text-text-secondary">Diferencia</span>
                            <span className={`font-bold ${c.diferencia_calculada < 0 ? 'text-status-error' : c.diferencia_calculada > 0 ? 'text-status-warning' : 'text-status-success'}`}>
                              {money(c.diferencia_calculada)}
                            </span>
                          </div>
                        )}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>

            {/* Modal de Ventas */}
            <AnimatePresence>
              {selectedCaja && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
                  <motion.div 
                    initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.95 }}
                    className="glass-card p-6 max-w-3xl w-full max-h-[80vh] overflow-y-auto"
                  >
                    <div className="flex justify-between items-center mb-6">
                      <h3 className="text-xl font-bold">Detalle de Ventas - {selectedCaja.cajero_nombre}</h3>
                      <button onClick={() => setSelectedCaja(null)} className="text-text-secondary hover:text-white transition-colors p-1 hover:bg-white/10 rounded-lg">
                        <X size={20} />
                      </button>
                    </div>
                    
                    {ventasCaja.length === 0 ? (
                      <p className="text-text-muted text-center py-8">No hubo ventas registradas en este turno.</p>
                    ) : (
                      <div className="space-y-4">
                        {ventasCaja.map((v) => (
                          <div key={v.id} className="bg-white/5 p-4 rounded-lg border border-white/10">
                            <div className="flex justify-between items-center border-b border-white/10 pb-2 mb-2">
                              <span className="font-semibold text-brand-light">Venta #{v.id}</span>
                              <span className="text-xs text-text-muted">{new Date(v.fecha_hora).toLocaleTimeString()}</span>
                            </div>
                            <ul className="text-sm space-y-1.5 mb-2">
                              {v.detalles.map((d: any) => (
                                <li key={d.id} className="flex justify-between gap-3 text-text-secondary">
                                  <span className="min-w-0 truncate">
                                    <span className="text-brand-light font-bold">{d.cantidad}x</span> {d.producto_nombre}
                                    <span className="text-text-muted text-xs ml-1">
                                      ({money(d.precio_unitario)} c/u)
                                    </span>
                                  </span>
                                  <span className="shrink-0 font-medium">{money(d.subtotal)}</span>
                                </li>
                              ))}
                            </ul>
                            <div className="flex flex-col gap-1 pt-2 border-t border-white/5">
                              {v.descuento_nombre && (
                                <div className="flex justify-between text-xs text-status-warning mb-1">
                                  <span>Descuento aplicado</span>
                                  <span className="font-semibold">{v.descuento_nombre}</span>
                                </div>
                              )}
                              <div className="flex justify-between items-center text-sm font-bold">
                                <span className="text-text-primary uppercase text-xs">{v.metodo_pago}</span>
                                <span className="text-status-success">{money(v.total)}</span>
                              </div>
                              {v.metodo_pago === 'EFECTIVO' && v.monto_recibido != null && (
                                <div className="flex justify-between text-xs text-text-secondary mt-1">
                                  <span>Recibido: {money(v.monto_recibido)}</span>
                                  <span>Vuelto: {money(v.vuelto ?? 0)}</span>
                                </div>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </motion.div>
                </div>
              )}
            </AnimatePresence>
          </motion.div>
        )}

        {activeTab === 'productos' && (
          <motion.div
            initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}
          >
            {/* Alerta de disponibilidad */}
            {userRole !== 3 && stockBajo.length > 0 && (
              <div className="glass-card p-5 mb-6 border-l-4 border-l-status-error">
                <div className="flex items-start gap-3">
                  <AlertTriangle size={22} className="text-status-error shrink-0 mt-0.5" />
                  <div className="flex-1 min-w-0">
                    <h3 className="font-bold text-status-error">
                      {stockBajo.length} producto{stockBajo.length > 1 ? 's' : ''} por reponer
                    </h3>
                    <p className="text-sm text-text-secondary mt-0.5 mb-3">
                      Con stock menor a {umbralStock} unidades.
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {stockBajo.slice(0, 8).map((p: any) => (
                        <span key={p.id} className="bg-status-error/15 text-status-error px-2.5 py-1 rounded-lg text-xs font-medium">
                          {p.nombre} · {p.stock_actual}
                        </span>
                      ))}
                      {stockBajo.length > 8 && (
                        <span className="text-text-muted text-xs px-2 py-1">y {stockBajo.length - 8} más…</span>
                      )}
                    </div>
                  </div>
                  <button
                    onClick={() => { setLowStockFilter(true); setOrdenProductos('stock'); }}
                    className="text-xs font-semibold bg-status-error/20 text-status-error hover:bg-status-error/30 px-3 py-2 rounded-lg transition-colors shrink-0"
                  >
                    Ver sólo estos
                  </button>
                </div>
              </div>
            )}

            <div className="glass-card p-6">
            <div className="flex justify-between items-center mb-6">
              <h3 className="text-xl font-semibold">Inventario de la Base de Datos</h3>
              <button onClick={() => {
                setShowAddForm(!showAddForm);
                if (showAddForm) setEditingId(null);
              }} className="bg-brand hover:bg-brand-hover text-white px-4 py-2 rounded-lg transition-colors flex items-center gap-2">
                <Plus size={18} /> {showAddForm ? 'Cancelar' : 'Nuevo Producto'}
              </button>
            </div>

            <AnimatePresence>
            {showAddForm && (
              <motion.form 
                initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
                onSubmit={handleSaveProduct} 
                className="mb-8 p-4 bg-white/5 rounded-lg border border-white/10 grid grid-cols-1 md:grid-cols-5 gap-4 items-end overflow-hidden"
              >
                <div className="md:col-span-5 mb-2">
                  {cameraStatus === 'available' ? (
                    <button type="button" onClick={() => setShowScanner(!showScanner)} className="text-sm flex items-center gap-2 bg-brand/20 text-brand-light px-4 py-2 rounded-lg hover:bg-brand/30 transition-colors">
                      <ScanLine size={16} /> {showScanner ? 'Cerrar Escáner' : 'Autocompletar con Escáner'}
                    </button>
                  ) : cameraStatus === 'unavailable' ? (
                    <p className="text-xs text-text-muted flex items-center gap-2">
                      <CameraOff size={14} /> Sin cámara en este equipo — cargá el código a mano.
                    </p>
                  ) : null}
                </div>
                {showScanner && cameraStatus === 'available' && (
                  <div className="md:col-span-5 mb-4">
                    <div id="admin-reader" className="w-full max-w-sm mx-auto bg-white text-black overflow-hidden rounded-md"></div>
                  </div>
                )}
                <div>
                  <label className="block text-xs text-text-secondary mb-1">Código de Barras</label>
                  <input required className="glass-input w-full p-2 rounded-md" value={newProd.codigo_barras} onChange={e => setNewProd({...newProd, codigo_barras: e.target.value})} />
                </div>
                <div>
                  <label className="block text-xs text-text-secondary mb-1">Nombre</label>
                  <input required className="glass-input w-full p-2 rounded-md" value={newProd.nombre} onChange={e => setNewProd({...newProd, nombre: e.target.value})} />
                </div>
                <div>
                  <label className="block text-xs text-text-secondary mb-1">Costo ($)</label>
                  <input required type="number" className="glass-input w-full p-2 rounded-md" value={newProd.costo} onChange={e => setNewProd({...newProd, costo: Number(e.target.value)})} />
                </div>
                <div>
                  <label className="block text-xs text-text-secondary mb-1">Precio de Venta ($)</label>
                  <input required type="number" className="glass-input w-full p-2 rounded-md" value={newProd.precio_venta} onChange={e => setNewProd({...newProd, precio_venta: Number(e.target.value)})} />
                </div>
                <div>
                  <label className="block text-xs text-text-secondary mb-1">Stock Inicial</label>
                  <input required type="number" className="glass-input w-full p-2 rounded-md" value={newProd.stock_actual} onChange={e => setNewProd({...newProd, stock_actual: Number(e.target.value)})} />
                </div>

                <div className="md:col-span-4">
                  <label className="block text-xs text-text-secondary mb-1">Imagen del producto (URL)</label>
                  <input
                    type="url"
                    placeholder="https://… (opcional)"
                    className="glass-input w-full p-2 rounded-md"
                    value={newProd.imagen_url}
                    onChange={e => setNewProd({...newProd, imagen_url: e.target.value})}
                  />
                </div>
                <div>
                  <label className="block text-xs text-text-secondary mb-1">Vista previa</label>
                  <div className="h-[42px] w-full rounded-md bg-white/5 border border-white/10 flex items-center justify-center overflow-hidden">
                    {newProd.imagen_url ? (
                      <img
                        src={newProd.imagen_url}
                        alt="Vista previa"
                        className="h-full w-full object-contain"
                        onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }}
                        onLoad={e => { (e.currentTarget as HTMLImageElement).style.display = 'block'; }}
                      />
                    ) : (
                      <ImageIcon size={16} className="text-text-muted" />
                    )}
                  </div>
                </div>

                <div className="md:col-span-5 flex justify-end">
                  <button type="submit" className="bg-status-success text-white px-6 py-2 rounded-lg font-semibold hover:bg-green-600 transition-colors">
                    {editingId ? 'Guardar Cambios' : 'Guardar Producto Real'}
                  </button>
                </div>
              </motion.form>
            )}
            </AnimatePresence>
            <div className="flex flex-col md:flex-row gap-3 mb-4">
              <div className="relative flex-1">
                <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
                <input
                  type="text"
                  placeholder="Buscar por nombre o código de barras…"
                  className="glass-input w-full p-2 pl-9 rounded-md"
                  value={searchTerm}
                  onChange={e => setSearchTerm(e.target.value)}
                />
              </div>

              <select
                value={ordenProductos}
                onChange={e => setOrdenProductos(e.target.value as any)}
                className="glass-input p-2 rounded-md text-sm"
                title="Ordenar"
              >
                <option value="nombre">Ordenar: A-Z</option>
                <option value="stock">Ordenar: menor stock</option>
                <option value="precio">Ordenar: mayor precio</option>
              </select>

              <label
                className="flex items-center gap-2 text-sm bg-white/5 p-2 rounded-md cursor-pointer whitespace-nowrap"
                title={userRole === 1 ? 'El umbral se cambia en Configuración › Punto de venta' : undefined}
              >
                <input type="checkbox" checked={lowStockFilter} onChange={e => setLowStockFilter(e.target.checked)} />
                Sólo bajo stock (&lt; {umbralStock})
              </label>
            </div>

            {filteredProductos.length > 0 && (
              <p className="text-xs text-text-muted mb-3">
                Mostrando {filteredProductos.length} de {localProductos.length} productos
              </p>
            )}

            {filteredProductos.length === 0 ? (
              <EmptyState icon={Package} title="No se encontraron productos" description={searchTerm || lowStockFilter ? 'Ajusta la búsqueda o los filtros aplicados.' : 'Agrega tu primer producto con el botón "Nuevo Producto".'} />
            ) : (
              <>
                {/* Vista tabla (desktop) */}
                <div className="hidden md:block overflow-x-auto">
                  <table className="w-full text-left">
                    <thead>
                      <tr className="border-b border-border-subtle text-text-secondary text-sm">
                        <th className="pb-3 font-medium w-14"></th>
                        <th className="pb-3 font-medium">Código</th>
                        <th className="pb-3 font-medium">Producto</th>
                        <th className="pb-3 font-medium">Precio</th>
                        <th className="pb-3 font-medium">Stock</th>
                        <th className="pb-3 font-medium text-right">Acciones</th>
                      </tr>
                    </thead>
                    <tbody className="text-sm">
                      {filteredProductos.map(p => (
                        <tr key={p.id} className="border-b border-border-subtle/50 hover:bg-white/[0.02] transition-colors">
                          <td className="py-3">
                            <ProductImage src={p.imagen_url} alt={p.nombre} className="w-10 h-10 rounded-lg" iconSize={16} />
                          </td>
                          <td className="py-4 text-text-muted">{p.codigo_barras}</td>
                          <td className="py-4 font-medium">{p.nombre}</td>
                          <td className="py-4">{money(p.precio_venta)}</td>
                          <td className="py-4">
                            <span className={`px-2 py-1 rounded-full text-xs ${p.stock_actual < umbralStock ? 'bg-status-error/20 text-status-error' : 'bg-status-success/20 text-status-success'}`}>
                              {p.stock_actual} und.
                            </span>
                          </td>
                          <td className="py-4 text-right">
                            <button onClick={() => setBarcodeProduct(p)} className="text-text-secondary hover:text-brand-light transition-colors p-2 bg-white/5 hover:bg-white/10 rounded-md mr-2" title="Imprimir Etiqueta">
                              <Printer size={16} />
                            </button>
                            <button onClick={() => startEdit(p)} className="text-brand-light hover:text-brand transition-colors p-2 bg-white/5 hover:bg-white/10 rounded-md">
                              <Edit2 size={16} />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Vista tarjetas (móvil) */}
                <div className="md:hidden space-y-3">
                  {filteredProductos.map(p => (
                    <div key={p.id} className="glass rounded-xl p-4">
                      <div className="flex justify-between items-start gap-3 mb-2">
                        <ProductImage src={p.imagen_url} alt={p.nombre} className="w-12 h-12 rounded-lg shrink-0" iconSize={18} />
                        <div className="min-w-0 flex-1">
                          <p className="font-semibold truncate">{p.nombre}</p>
                          <p className="text-xs text-text-muted font-mono">{p.codigo_barras}</p>
                        </div>
                        <span className={`shrink-0 px-2 py-1 rounded-full text-xs ${p.stock_actual < umbralStock ? 'bg-status-error/20 text-status-error' : 'bg-status-success/20 text-status-success'}`}>
                          {p.stock_actual} und.
                        </span>
                      </div>
                      <div className="flex justify-between items-center mt-3">
                        <span className="text-accent font-bold text-lg">{money(p.precio_venta)}</span>
                        <div className="flex gap-2">
                          <button onClick={() => setBarcodeProduct(p)} className="text-text-secondary hover:text-brand-light transition-colors p-2 bg-white/5 hover:bg-white/10 rounded-md" title="Imprimir Etiqueta">
                            <Printer size={16} />
                          </button>
                          <button onClick={() => startEdit(p)} className="text-brand-light hover:text-brand transition-colors p-2 bg-white/5 hover:bg-white/10 rounded-md">
                            <Edit2 size={16} />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
            </div>
          </motion.div>
        )}

        {activeTab === 'descuentos' && (
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
            <div className="glass-card p-6 max-w-3xl">
              <h3 className="text-xl font-semibold mb-2 border-b border-white/10 pb-4">
                {editandoDescuento ? 'Editar descuento' : 'Nuevo descuento'}
              </h3>
              <p className="text-sm text-text-muted mb-6">
                Los descuentos vigentes aparecen automáticamente en el POS para que el cajero los aplique al cobrar.
              </p>

              <form onSubmit={handleGuardarDescuento} className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm text-text-secondary mb-1">Nombre</label>
                    <input
                      type="text" required
                      className="glass-input w-full p-3 rounded-lg"
                      placeholder="Ej. Jubilados"
                      value={nuevoDescuento.nombre}
                      onChange={e => setNuevoDescuento({...nuevoDescuento, nombre: e.target.value})}
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-text-secondary mb-1">Código promocional (opcional)</label>
                    <input
                      type="text"
                      className="glass-input w-full p-3 rounded-lg font-mono uppercase"
                      placeholder="JUBILADOS15"
                      value={nuevoDescuento.codigo_promocional}
                      onChange={e => setNuevoDescuento({...nuevoDescuento, codigo_promocional: e.target.value.toUpperCase()})}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div>
                    <label className="block text-sm text-text-secondary mb-1">Tipo</label>
                    <select
                      className="glass-input w-full p-3 rounded-lg"
                      value={nuevoDescuento.tipo}
                      onChange={e => setNuevoDescuento({...nuevoDescuento, tipo: e.target.value})}
                    >
                      <option value="PORCENTAJE">Porcentaje (%)</option>
                      <option value="MONTO">Monto fijo ($)</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm text-text-secondary mb-1">
                      Valor {nuevoDescuento.tipo === 'PORCENTAJE' ? '(%)' : '($)'}
                    </label>
                    <input
                      type="number" required min="0.01" step="0.01"
                      max={nuevoDescuento.tipo === 'PORCENTAJE' ? 100 : undefined}
                      className="glass-input w-full p-3 rounded-lg"
                      value={nuevoDescuento.valor}
                      onChange={e => setNuevoDescuento({...nuevoDescuento, valor: e.target.value})}
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-text-secondary mb-1">Aplica a</label>
                    <select
                      className="glass-input w-full p-3 rounded-lg"
                      value={nuevoDescuento.producto_id}
                      onChange={e => setNuevoDescuento({...nuevoDescuento, producto_id: e.target.value})}
                    >
                      <option value="">Toda la venta</option>
                      {localProductos.map(p => (
                        <option key={p.id} value={p.id}>{p.nombre}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm text-text-secondary mb-1">Vigente desde (opcional)</label>
                    <input
                      type="date"
                      className="glass-input w-full p-3 rounded-lg"
                      value={nuevoDescuento.fecha_inicio}
                      onChange={e => setNuevoDescuento({...nuevoDescuento, fecha_inicio: e.target.value})}
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-text-secondary mb-1">Vigente hasta (opcional)</label>
                    <input
                      type="date"
                      className="glass-input w-full p-3 rounded-lg"
                      value={nuevoDescuento.fecha_fin}
                      onChange={e => setNuevoDescuento({...nuevoDescuento, fecha_fin: e.target.value})}
                    />
                  </div>
                </div>

                <label className="flex items-center gap-2 text-sm cursor-pointer">
                  <input
                    type="checkbox"
                    checked={nuevoDescuento.activo}
                    onChange={e => setNuevoDescuento({...nuevoDescuento, activo: e.target.checked})}
                  />
                  Activo (disponible en el POS)
                </label>

                <div className="pt-2 flex gap-3">
                  <button type="submit" className="btn-primary px-6 py-3">
                    {editandoDescuento ? 'Guardar cambios' : 'Crear descuento'}
                  </button>
                  {editandoDescuento && (
                    <button
                      type="button"
                      onClick={() => { setEditandoDescuento(null); setNuevoDescuento(NUEVO_DESCUENTO); }}
                      className="px-6 py-3 rounded-xl bg-neutral-bg3 hover:bg-neutral-bg4 text-text-secondary font-bold transition-colors"
                    >
                      Cancelar
                    </button>
                  )}
                </div>
              </form>
            </div>

            <div className="glass-card p-6 mt-8 max-w-4xl">
              <h3 className="text-xl font-semibold mb-6 border-b border-white/10 pb-4">Descuentos cargados</h3>
              {loadingDescuentos ? (
                <div className="space-y-2"><Skeleton className="h-12" /><Skeleton className="h-12" /></div>
              ) : descuentos.length === 0 ? (
                <EmptyState icon={Tag} title="Todavía no hay descuentos" description="Creá el primero con el formulario de arriba." />
              ) : (
                <div className="space-y-3">
                  {descuentos.map(d => (
                    <div key={d.id} className="glass rounded-xl p-4 flex flex-col sm:flex-row sm:items-center gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-semibold">{d.nombre}</span>
                          <span className="bg-brand/20 text-brand-light px-2 py-0.5 rounded text-xs font-bold">
                            {d.tipo === 'PORCENTAJE' ? `${d.valor}%` : `$${d.valor}`}
                          </span>
                          {d.activo ? (
                            <span className="bg-status-success/20 text-status-success px-2 py-0.5 rounded-full text-xs font-bold">Activo</span>
                          ) : (
                            <span className="bg-neutral-bg3 text-text-muted px-2 py-0.5 rounded-full text-xs">Inactivo</span>
                          )}
                        </div>
                        <p className="text-xs text-text-muted mt-1">
                          {d.codigo_promocional && <span className="font-mono mr-2">{d.codigo_promocional}</span>}
                          {d.producto_id
                            ? `Sólo: ${localProductos.find(p => p.id === d.producto_id)?.nombre || `producto #${d.producto_id}`}`
                            : 'Toda la venta'}
                          {(d.fecha_inicio || d.fecha_fin) && (
                            <> · {d.fecha_inicio ? new Date(d.fecha_inicio).toLocaleDateString() : '…'} a {d.fecha_fin ? new Date(d.fecha_fin).toLocaleDateString() : '…'}</>
                          )}
                        </p>
                      </div>
                      <div className="flex gap-2 shrink-0">
                        <button onClick={() => handleEditarDescuento(d)} className="text-brand-light hover:text-brand p-2 bg-white/5 hover:bg-white/10 rounded-md transition-colors" title="Editar">
                          <Edit2 size={16} />
                        </button>
                        <button onClick={() => handleEliminarDescuento(d)} className="text-status-error hover:text-red-400 p-2 bg-white/5 hover:bg-white/10 rounded-md transition-colors" title="Eliminar">
                          <X size={16} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        )}

        {activeTab === 'configuracion' && (
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
            {/* Sub-pestañas: parámetros del sistema vs. usuarios */}
            <div className="flex gap-2 mb-6 border-b border-white/10">
              {([
                { id: 'sistema', label: 'Parámetros del sistema' },
                { id: 'usuarios', label: 'Usuarios' },
              ] as const).map(t => (
                <button
                  key={t.id}
                  onClick={() => setSubTabConfig(t.id)}
                  className={`px-4 py-3 font-semibold text-sm border-b-2 -mb-px transition-colors ${
                    subTabConfig === t.id
                      ? 'border-brand text-brand-light'
                      : 'border-transparent text-text-secondary hover:text-white'
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {subTabConfig === 'sistema' && <ConfiguracionPanel />}

            {subTabConfig === 'usuarios' && (
            <>
            <div className="glass-card p-6 max-w-2xl">
              <h3 className="text-xl font-semibold mb-2 border-b border-white/10 pb-4">Gestión de Usuarios</h3>
              <p className="text-sm text-text-muted mb-6">Crea cuentas para los empleados. Usa contraseñas numéricas para que sea rápido ingresar desde el móvil (Cajeros).</p>
              
              <form onSubmit={handleCreateUser} className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm text-text-secondary mb-1">Nombre de Usuario</label>
                    <input 
                      type="text" required
                      className="glass-input w-full p-3 rounded-lg" 
                      placeholder="Ej. Juan Perez"
                      value={newUser.nombre} 
                      onChange={e => setNewUser({...newUser, nombre: e.target.value})} 
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-text-secondary mb-1">PIN de Acceso</label>
                    <input 
                      type="password" required
                      className="glass-input w-full p-3 rounded-lg" 
                      placeholder="Ej. 1234"
                      value={newUser.pin_acceso} 
                      onChange={e => setNewUser({...newUser, pin_acceso: e.target.value})} 
                    />
                  </div>
                </div>
                
                <div>
                  <label className="block text-sm text-text-secondary mb-1">Nivel de Acceso (Rol)</label>
                  <select 
                    className="glass-input w-full p-3 rounded-lg"
                    value={newUser.rol_id}
                    onChange={e => setNewUser({...newUser, rol_id: Number(e.target.value)})}
                  >
                    <option value={1}>1 - Administrador (Acceso Total)</option>
                    <option value={2}>2 - Encargado (Productos y Cajas)</option>
                    <option value={3}>3 - Cajero (Solo POS Remoto)</option>
                  </select>
                </div>
                
                <div className="pt-4">
                  <button type="submit" className="bg-brand hover:bg-brand-hover text-white px-6 py-3 rounded-lg font-bold transition-colors w-full md:w-auto">
                    Crear Usuario
                  </button>
                </div>
              </form>
            </div>

            <div className="glass-card p-6 mt-8 max-w-4xl">
              <h3 className="text-xl font-semibold mb-6 border-b border-white/10 pb-4">Lista de Usuarios</h3>
              {loadingUsuarios ? (
                <div className="space-y-2">
                  <Skeleton className="h-10" />
                  <Skeleton className="h-10" />
                </div>
              ) : usuarios.filter(u => u.estado).length === 0 ? (
                <EmptyState icon={Users} title="Aún no hay usuarios" description="Crea el primer empleado con el formulario de arriba." />
              ) : (
                <>
                  {/* Vista tabla (desktop) */}
                  <div className="hidden md:block overflow-x-auto">
                    <table className="w-full text-left">
                      <thead>
                        <tr className="border-b border-white/10 text-text-secondary text-sm">
                          <th className="pb-3 font-medium">Nombre</th>
                          <th className="pb-3 font-medium">Nivel</th>
                          <th className="pb-3 font-medium text-center">Estado</th>
                          <th className="pb-3 font-medium text-right">Acciones</th>
                        </tr>
                      </thead>
                      <tbody>
                        {usuarios.filter(u => u.estado).map(u => (
                          <tr key={u.id} className="border-b border-white/5 hover:bg-white/5 transition-colors text-sm">
                            <td className="py-3 font-medium">{u.nombre}</td>
                            <td className="py-3">
                              <span className="bg-white/10 px-2 py-1 rounded text-xs">
                                {u.rol_id === 1 ? 'Administrador' : (u.rol_id === 2 ? 'Encargado' : 'Cajero')}
                              </span>
                            </td>
                            <td className="py-3 text-center">
                              <span className="text-status-success text-xs font-bold bg-status-success/20 px-2 py-1 rounded-full">Activo</span>
                            </td>
                            <td className="py-3 text-right">
                              {u.nombre !== getUsername() && (
                                <>
                                  <button onClick={() => handleToggleRolUser(u)} className="text-brand-light hover:underline text-xs mr-4">
                                    Cambiar Rol
                                  </button>
                                  <button onClick={() => handleDeleteUser(u)} className="text-status-error hover:underline text-xs">
                                    Eliminar
                                  </button>
                                </>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {/* Vista tarjetas (móvil) */}
                  <div className="md:hidden space-y-3">
                    {usuarios.filter(u => u.estado).map(u => (
                      <div key={u.id} className="glass rounded-xl p-4">
                        <div className="flex justify-between items-center mb-2">
                          <span className="font-semibold">{u.nombre}</span>
                          <span className="text-status-success text-xs font-bold bg-status-success/20 px-2 py-1 rounded-full">Activo</span>
                        </div>
                        <span className="bg-white/10 px-2 py-1 rounded text-xs">
                          {u.rol_id === 1 ? 'Administrador' : (u.rol_id === 2 ? 'Encargado' : 'Cajero')}
                        </span>
                        {u.nombre !== getUsername() && (
                          <div className="flex gap-4 mt-3 pt-3 border-t border-white/5">
                            <button onClick={() => handleToggleRolUser(u)} className="text-brand-light hover:underline text-xs">
                              Cambiar Rol
                            </button>
                            <button onClick={() => handleDeleteUser(u)} className="text-status-error hover:underline text-xs">
                              Eliminar
                            </button>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
            </>
            )}
          </motion.div>
        )}
      </main>

      {/* Barcode Modal */}
      {barcodeProduct && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
          <motion.div 
            initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
            className="glass-card p-6 max-w-sm w-full text-center print-area"
          >
            <div className="flex justify-between items-center mb-4 no-print">
              <h3 className="text-lg font-bold text-white">Etiqueta: {barcodeProduct.nombre}</h3>
              <button onClick={() => setBarcodeProduct(null)} className="text-text-secondary hover:text-white p-1 hover:bg-white/10 rounded-lg"><X size={18} /></button>
            </div>
            
            <div className="bg-white p-4 rounded-lg flex flex-col items-center justify-center mb-4 text-black">
              <span className="font-bold text-lg mb-2">{barcodeProduct.nombre}</span>
              <Barcode value={barcodeProduct.codigo_barras} width={2} height={60} displayValue={true} />
              <span className="text-2xl font-bold mt-2">${barcodeProduct.precio_venta}</span>
            </div>
            
            <div className="mt-6 no-print">
              <button onClick={() => window.print()} className="w-full bg-brand hover:bg-brand-hover text-white py-3 rounded-lg font-bold flex justify-center items-center gap-2 transition-colors">
                <Printer size={20} /> Imprimir Etiqueta
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </div>
  );
}

export default Admin;
