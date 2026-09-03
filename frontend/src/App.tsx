import { useState, useEffect, useRef } from 'react';
import { Html5QrcodeScanner } from 'html5-qrcode';
import { ShoppingCart, ScanLine, WifiOff, Wifi, Printer, Banknote, CreditCard, Smartphone, Landmark, X, Camera, CameraOff, Package, Tag, Search, Plus, Minus, Trash2, Keyboard, CloudOff, AlertTriangle } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { QRCodeCanvas } from 'qrcode.react';
import { api } from './api';
import { db, type ProductoLocal, type VentaOffline } from './db';
import { clasificarFalloDeEnvio } from './sincronizacion';
import { useLiveQuery } from 'dexie-react-hooks';
import { useUI } from './components/UIProvider';
import { useConfig } from './components/ConfigProvider';
import { useCameraAvailability } from './useCamera';
import { useConexion } from './useConexion';
import { sanitizarMonto, formatearTope } from './montos';
import { sincronizarCatalogo } from './catalogoLocal';
import { CONFIG_ESCANER, mejorarImagen } from './escaner';
import { recordarCaja, cajaRecordada, cajaProvisoria, esProvisoria } from './cajaLocal';
import { recordarAcceso, validarOffline, hayCredencialesGuardadas } from './sesionLocal';
import { Logo, LogoMark } from './components/Logo';
import { ProductImage } from './components/ProductImage';
import { DiagnosticoRed } from './components/DiagnosticoRed';

/** Presentación de cada método de pago. La lista real sale de la configuración. */
const METODOS_PAGO: Record<string, { etiqueta: string; icono: typeof Banknote; color: string }> = {
  EFECTIVO: { etiqueta: 'Efectivo', icono: Banknote, color: 'text-status-success' },
  TARJETA: { etiqueta: 'Tarjeta', icono: CreditCard, color: 'text-accent' },
  MERCADOPAGO: { etiqueta: 'Mercado Pago QR', icono: Smartphone, color: 'text-[#009EE3]' },
  TRANSFERENCIA: { etiqueta: 'Transferencia', icono: Landmark, color: 'text-brand-light' },
};


function POS() {
  const { showToast } = useUI();
  const { config, money, desglosarIva, recargar: recargarConfig } = useConfig();
  const localProductos = useLiveQuery(() => db.productos.toArray()) || [];
  // Ventas cobradas que todavía no llegaron al servidor. Las rechazadas se
  // cuentan aparte: nunca se reintentan solas, así que sumarlas acá dejaba el
  // cierre de caja bloqueado para siempre esperando algo que no iba a pasar.
  const ventasPendientes = useLiveQuery(() => db.ventasOffline.filter(v => !v.rechazo).count()) ?? 0;
  const ventasRechazadas = useLiveQuery(() => db.ventasOffline.filter(v => !!v.rechazo).count()) ?? 0;
  const [cart, setCart] = useState<{producto: ProductoLocal, cantidad: number}[]>([]);
  // Contempla tanto la falta de red como el servidor caído
  const { offline: isOffline, servidorCaido } = useConexion();
  const [showReceipt, setShowReceipt] = useState(false);
  const cameraStatus = useCameraAvailability();
  const [scannerActivo, setScannerActivo] = useState(false);

  // Mercado Pago States
  const [showMpQR, setShowMpQR] = useState(false);
  const [mpQrUrl, setMpQrUrl] = useState('');
  const [mpPollingRef, setMpPollingRef] = useState<any>(null);
  const [lastSale, setLastSale] = useState<VentaOffline | null>(null);
  const [manualCode, setManualCode] = useState('');
  
  // Auth States
  const [isAuthenticated, setIsAuthenticated] = useState(!!localStorage.getItem('token'));
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  // Se entró validando contra el equipo porque no había servidor. Se puede
  // vender, pero no hay token: todo lo que necesite la API queda esperando a
  // que vuelva la conexión.
  const [sesionOffline, setSesionOffline] = useState(false);

  // null mientras no se sabe todavía: no hay que mostrar el login ni el
  // asistente hasta tener la respuesta, porque una base vacía que muestra el
  // login por un instante invita a probar usuarios que no existen.
  const [necesitaPrimerArranque, setNecesitaPrimerArranque] = useState<boolean | null>(null);
  const [nombreComercioInicial, setNombreComercioInicial] = useState('');
  const [pinConfirmado, setPinConfirmado] = useState('');
  const [enviandoPrimerArranque, setEnviandoPrimerArranque] = useState(false);
  const [mostrarDiagnostico, setMostrarDiagnostico] = useState(false);
  
  // Caja States
  const [caja, setCaja] = useState<any>(null);
  const [loadingCaja, setLoadingCaja] = useState(true);
  const [montoInicial, setMontoInicial] = useState('');
  const [showCloseCaja, setShowCloseCaja] = useState(false);
  const [montoFinal, setMontoFinal] = useState('');

  // Payment States
  const [showPaymentModal, setShowPaymentModal] = useState(false);
  const [clientPhone, setClientPhone] = useState('');
  const [selectedMethod, setSelectedMethod] = useState<string | null>(null);
  const [montoRecibido, setMontoRecibido] = useState<string>('');

  // Catálogo y descuentos
  const [busquedaCatalogo, setBusquedaCatalogo] = useState('');
  const [categoriaActiva, setCategoriaActiva] = useState<number | null>(null);
  // Sacar de la vista lo que no hay es una preferencia de cada mostrador, así
  // que se recuerda en el equipo. Apagada por defecto: esconder un producto
  // que físicamente está en la góndola es peor que verlo marcado.
  const [ocultarSinStock, setOcultarSinStock] = useState(
    () => localStorage.getItem('ocultar_sin_stock') === '1'
  );
  const [categorias, setCategorias] = useState<any[]>(() => {
    // Se arranca con lo último que se bajó: sin conexión el filtro igual anda
    try {
      return JSON.parse(localStorage.getItem('categorias_cache') || '[]');
    } catch {
      return [];
    }
  });
  const [descuentos, setDescuentos] = useState<any[]>([]);
  const [descuentoAplicado, setDescuentoAplicado] = useState<any>(null);

  // Operación por teclado
  const [lineaSeleccionada, setLineaSeleccionada] = useState(-1);
  const [metodoResaltado, setMetodoResaltado] = useState(0);
  const [mostrarAyuda, setMostrarAyuda] = useState(false);

  const lastScannedRef = useRef<{ code: string, time: number } | null>(null);
  const codigoInputRef = useRef<HTMLInputElement>(null);

  const sinStock = (p: ProductoLocal) => (p.stock_actual ?? 0) <= 0;

  const productosFiltrados = localProductos
    .filter(p => {
      if (categoriaActiva !== null && p.categoria_id !== categoriaActiva) return false;
      if (ocultarSinStock && sinStock(p)) return false;
      if (!busquedaCatalogo) return true;
      return p.nombre.toLowerCase().includes(busquedaCatalogo.toLowerCase())
        || p.codigo_barras.includes(busquedaCatalogo);
    })
    // Lo que no hay va al final: estorba, pero no se esconde. El lector de
    // códigos no pasa por acá, así que un producto agotado en el sistema pero
    // presente en la góndola se sigue pudiendo cobrar escaneándolo.
    .sort((a, b) => Number(sinStock(a)) - Number(sinStock(b)));

  // Sólo se ofrecen las categorías que tienen algo cargado: un filtro que
  // siempre da vacío es ruido en una pantalla de venta.
  const categoriasConProductos = categorias.filter(
    c => localProductos.some(p => p.categoria_id === c.id)
  );

  // Mercado Pago necesita hablar con el servidor para generar el QR y
  // confirmar el pago: sin conexión no se ofrece en lugar de fallar al tocarlo.
  const metodosHabilitados = (config.metodos_pago_habilitados?.length
    ? config.metodos_pago_habilitados
    : ['EFECTIVO']
  ).filter(m => !(isOffline && m === 'MERCADOPAGO'));

  const topeEfectivo = config.monto_maximo_efectivo || 1000000;

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

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const datos = await api.login(username, password);

      // Queda guardado en el equipo para poder entrar la próxima vez aunque no
      // haya servidor. Se renueva en cada acceso, así el hash sigue el PIN si
      // cambió y la credencial no se vence trabajando normalmente.
      try {
        const payload = JSON.parse(atob(datos.access_token.split('.')[1]));
        await recordarAcceso(username, password, payload.rol);
      } catch {
        /* sin acceso offline: no es motivo para no dejar entrar ahora */
      }

      setSesionOffline(false);
      setIsAuthenticated(true);
      recargarConfig();

      // Sincronizar catálogo para que la DB local no esté vacía
      try {
        await sincronizarCatalogo(await api.getCatalogo());
      } catch (syncErr: any) {
        console.warn("Error al sincronizar catálogo al inicio:", syncErr);
        showToast("No se pudo actualizar el catálogo. Se usará el guardado localmente.", 'error');
      }

    } catch (err: any) {
      // Sin servidor se valida contra el equipo. Es la única forma de que un
      // comercio que abre con el internet caído pueda vender: la cola de
      // ventas y el catálogo ya viven acá, lo único que faltaba era entrar.
      //
      // Sólo cuando el fallo es de red. Si el servidor contestó "PIN
      // incorrecto", el PIN es incorrecto y no hay nada que reintentar acá.
      if (err?.esFalloDeRed) {
        const resultado = await validarOffline(username, password);

        if (resultado.ok) {
          setSesionOffline(true);
          setIsAuthenticated(true);
          showToast('Entraste sin conexión: podés vender, y todo se sincroniza al volver la señal', 'success');
          return;
        }

        if (resultado.motivo === 'vencida') {
          showToast(
            'Hace demasiado que este equipo no se conecta. Hay que entrar una vez con señal.',
            'error',
          );
          return;
        }

        if (resultado.motivo === 'sin_credencial') {
          showToast(
            hayCredencialesGuardadas()
              ? 'Ese usuario nunca entró en este equipo. Sin conexión sólo pueden entrar los que ya lo usaron.'
              : 'No hay servidor y este equipo todavía no tiene ninguna sesión guardada.',
            'error',
          );
          return;
        }
      }

      showToast(err.message, 'error');
    }
  };

  useEffect(() => {
    // Sin esto, una base recién instalada muestra el login de siempre y el
    // dueño del comercio no tiene forma de crear el primer administrador sin
    // usar la consola.
    if (isAuthenticated) return;
    api.estadoInicial()
      .then(({ hay_usuarios }) => setNecesitaPrimerArranque(!hay_usuarios))
      // Sin servidor no se puede inicializar nada: se asume que ya hay
      // usuarios y se muestra el login de siempre, que a su vez ofrece el
      // acceso offline si corresponde.
      .catch(() => setNecesitaPrimerArranque(false));
  }, [isAuthenticated]);

  const handlePrimerArranque = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== pinConfirmado) {
      showToast('Los PIN no coinciden', 'error');
      return;
    }
    setEnviandoPrimerArranque(true);
    try {
      await api.register(username, password, 1);
      await api.login(username, password);

      const nombre = nombreComercioInicial.trim();
      if (nombre) {
        try {
          await api.updateConfiguracion({ negocio_nombre: nombre });
        } catch {
          // El administrador ya quedó creado y puede entrar: el nombre del
          // comercio se cambia después desde Configuración sin perder nada.
          showToast('El administrador se creó, pero el nombre del comercio no se pudo guardar. Cambialo desde Configuración.', 'error');
        }
      }

      setNecesitaPrimerArranque(false);
      setIsAuthenticated(true);
      recargarConfig();
      showToast('Sistema inicializado. Ya podés vender.', 'success');
    } catch (err: any) {
      showToast(err.message || 'No se pudo completar el primer arranque', 'error');
    } finally {
      setEnviandoPrimerArranque(false);
    }
  };

  useEffect(() => {
    // Estado de la caja. Si el servidor no responde se cae al turno que quedó
    // guardado en el equipo, así un corte de internet no frena la venta.
    if (isAuthenticated) {
      api.getCajaEstado()
        .then(res => {
          setCaja(res);
          recordarCaja(res);
        })
        .catch(() => {
          const guardada = cajaRecordada();
          if (guardada) {
            setCaja(guardada);
            showToast('Sin conexión: seguís con el turno abierto guardado en este equipo', 'info');
          } else {
            setCaja(null);
          }
        })
        .finally(() => setLoadingCaja(false));
      // Descuentos vigentes disponibles para aplicar en el cobro
      api.getDescuentos(true).then(setDescuentos).catch(() => setDescuentos([]));
      // Las categorías se guardan en el equipo: si después se corta internet,
      // los filtros del catálogo siguen funcionando.
      api.getCategorias()
        .then((cats: any[]) => {
          setCategorias(cats);
          localStorage.setItem('categorias_cache', JSON.stringify(cats));
        })
        .catch(() => {});
    } else {
      setLoadingCaja(false);
    }
  }, [isAuthenticated]);

  // El escáner sólo se monta cuando el cajero lo activa y hay una cámara
  // detectada. Así una PC de escritorio con lector USB nunca ve el diálogo
  // de permisos de cámara.
  useEffect(() => {
    if (!caja || loadingCaja || !scannerActivo || cameraStatus !== 'available') return;

    const scanner = new Html5QrcodeScanner("reader", CONFIG_ESCANER, false);
    const dejarDeEsperarLaCamara = mejorarImagen(scanner);

    scanner.render(async (decodedText) => {
      const now = Date.now();
      if (lastScannedRef.current) {
        // Ignorar si es el mismo código y han pasado menos de 2 segundos
        if (lastScannedRef.current.code === decodedText && now - lastScannedRef.current.time < 2000) {
          return;
        }
      }
      lastScannedRef.current = { code: decodedText, time: now };

      // Buscar producto en IndexedDB
      const producto = await db.productos.where('codigo_barras').equals(decodedText).first();
      if (producto) {
        addToCart(producto);
        playBeep();
        showToast(`¡${producto.nombre} añadido!`, 'success');
      } else {
        showToast("Producto no encontrado: " + decodedText, 'error');
      }
    }, () => {
      // Ignorar errores de lectura continuos
    });

    return () => {
      dejarDeEsperarLaCamara();
      scanner.clear().catch(error => console.error("Failed to clear html5QrcodeScanner. ", error));
    };
  }, [caja, loadingCaja, scannerActivo, cameraStatus]);

  const addToCart = (producto: ProductoLocal) => {
    setCart(prev => {
      const existing = prev.find(item => item.producto.id === producto.id);
      if (existing) {
        // Se selecciona la línea afectada para que el cajero vea qué cambió
        setLineaSeleccionada(prev.findIndex(i => i.producto.id === producto.id));
        return prev.map(item => item.producto.id === producto.id ? { ...item, cantidad: item.cantidad + 1 } : item);
      }
      setLineaSeleccionada(prev.length);
      return [...prev, { producto, cantidad: 1 }];
    });
  };

  /** Suma o resta unidades de una línea. Si llega a cero, la quita. */
  const cambiarCantidad = (indice: number, delta: number) => {
    setCart(prev => {
      const item = prev[indice];
      if (!item) return prev;
      const nueva = item.cantidad + delta;
      if (nueva <= 0) {
        setLineaSeleccionada(s => Math.min(s, prev.length - 2));
        return prev.filter((_, i) => i !== indice);
      }
      return prev.map((it, i) => i === indice ? { ...it, cantidad: nueva } : it);
    });
  };

  const quitarLinea = (indice: number) => {
    setCart(prev => {
      const item = prev[indice];
      if (item) showToast(`${item.producto.nombre} quitado`, 'info');
      setLineaSeleccionada(s => Math.min(s, prev.length - 2));
      return prev.filter((_, i) => i !== indice);
    });
  };

  /** Devuelve el foco al campo de código: es donde escribe el lector USB. */
  const enfocarCodigo = () => {
    // El timeout deja que React termine de renderizar antes de mover el foco
    setTimeout(() => codigoInputRef.current?.focus(), 0);
  };

  const buscarYAgregar = async (codigo: string) => {
    const limpio = codigo.trim();
    if (!limpio) return false;
    const producto = await db.productos.where('codigo_barras').equals(limpio).first();
    if (producto) {
      addToCart(producto);
      playBeep();
      showToast(`${producto.nombre} añadido`, 'success');
      return true;
    }
    showToast('Producto no encontrado: ' + limpio, 'error');
    return false;
  };

  const handleManualSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    // Enter con el campo vacío y con carrito cargado: pasa directo a cobrar
    if (!manualCode.trim()) {
      if (cart.length > 0) setShowPaymentModal(true);
      return;
    }
    const ok = await buscarYAgregar(manualCode);
    if (ok) setManualCode('');
    enfocarCodigo();
  };

  const subtotal = cart.reduce((acc, item) => acc + (item.producto.precio_venta * item.cantidad), 0);

  // El servidor recalcula el descuento al sincronizar; esto es sólo para
  // mostrarle el total correcto al cajero y poder cobrar estando offline.
  const calcularDescuento = () => {
    if (!descuentoAplicado) return 0;
    const base = descuentoAplicado.producto_id
      ? cart
          .filter(i => i.producto.id === descuentoAplicado.producto_id)
          .reduce((acc, i) => acc + i.producto.precio_venta * i.cantidad, 0)
      : subtotal;
    const rebaja = descuentoAplicado.tipo === 'PORCENTAJE'
      ? base * (descuentoAplicado.valor / 100)
      : Math.min(descuentoAplicado.valor, base);
    return Math.round(rebaja * 100) / 100;
  };

  const montoDescuento = calcularDescuento();
  const totalConDescuento = Math.max(0, Math.round((subtotal - montoDescuento) * 100) / 100);

  // El impuesto se calcula sobre el total ya descontado. Si está configurado
  // como "incluido en el precio" el total no cambia; si no, se le suma.
  const iva = desglosarIva(totalConDescuento);
  const total = iva.total;

  /**
   * Importes sugeridos para cobrar más rápido: el total exacto y los redondeos
   * "de billete" hacia arriba. Se descartan los que pasan el tope.
   */
  const sugerenciasEfectivo = (() => {
    if (total <= 0) return [];
    const candidatos = new Set<number>([Math.ceil(total)]);
    for (const paso of [100, 500, 1000, 2000, 5000, 10000, 20000]) {
      const redondeado = Math.ceil(total / paso) * paso;
      if (redondeado >= total) candidatos.add(redondeado);
    }
    return [...candidatos]
      .filter(m => m <= topeEfectivo)
      .sort((a, b) => a - b)
      .slice(0, 5);
  })();

  const processCheckout = async (
    metodo: string,
    recibido?: number,
    vuelto?: number,
    pagoReferencia?: string,
  ) => {
    if (cart.length === 0) return;

    const venta: VentaOffline = {
      fecha_hora_local: new Date().toISOString(),
      // Se genera acá y viaja al servidor: si la sincronización se reintenta,
      // el backend reconoce la venta y no la cobra dos veces.
      uuid_cliente: crypto.randomUUID(),
      metodo_pago: metodo,
      // Con QR viaja la referencia del cobro: el servidor la comprueba contra
      // Mercado Pago antes de dar la venta por registrada.
      pago_referencia: pagoReferencia,
      monto_recibido: recibido,
      vuelto: vuelto,
      descuento_id: descuentoAplicado?.id ?? null,
      descuento_nombre: descuentoAplicado?.nombre ?? null,
      subtotal_bruto: subtotal,
      iva_porcentaje: config.iva_porcentaje || null,
      iva_monto: iva.iva || null,
      iva_incluido: config.iva_incluido_en_precio,
      iva_nombre: config.iva_nombre,
      total: total,
      estado_sincronizacion: false,
      detalles: cart.map(item => ({
        producto_id: item.producto.id,
        producto_nombre: item.producto.nombre,
        cantidad: item.cantidad,
        precio_unitario: item.producto.precio_venta
      }))
    };

    // Guardar offline
    await db.ventasOffline.add(venta);
    
    // Descontar stock local para reflejarlo inmediatamente
    await db.transaction('rw', db.productos, async () => {
      for (const item of cart) {
        const prod = await db.productos.get(item.producto.id);
        if (prod) {
          await db.productos.update(prod.id, { stock_actual: prod.stock_actual - item.cantidad });
        }
      }
    });

    setLastSale(venta);
    setCart([]);
    setLineaSeleccionada(-1);
    setDescuentoAplicado(null);
    setShowPaymentModal(false);
    setShowReceipt(true);

    // Intentar sincronizar en segundo plano
    if (!isOffline) {
      setTimeout(syncVentas, 1000);
    }
  };

  const handleImprimir = async (venta: VentaOffline) => {
    // Sin impresora configurada, o venta que todavía no tiene id del
    // servidor (offline, sin sincronizar todavía): no hay contra qué
    // imprimir en la térmica, así que se sigue usando el diálogo del
    // navegador, que es lo único que puede andar sin conexión.
    if (!config.impresora_habilitada || !venta.id) {
      window.print();
      return;
    }
    try {
      await api.imprimirTicket(venta.id);
      showToast('Imprimiendo en la térmica...', 'success');
    } catch (err: any) {
      showToast(err.message || 'No se pudo imprimir en la térmica. Se abre el diálogo del navegador.', 'error');
      window.print();
    }
  };

  const cerrarRecibo = () => {
    setShowReceipt(false);
    setClientPhone('');
    enfocarCodigo();
  };

  const cerrarCobro = () => {
    setShowPaymentModal(false);
    setSelectedMethod(null);
    setMontoRecibido('');
    enfocarCodigo();
  };

  /**
   * Operación completa por teclado, pensada para que el cajero no toque el mouse:
   * el lector de barras escribe en el campo de código y Enter encadena todo el
   * flujo. Las flechas mueven por el carrito o por los métodos de pago según el
   * contexto activo.
   */
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const objetivo = e.target as HTMLElement | null;
      const enCampo = !!objetivo && (
        objetivo.tagName === 'INPUT' || objetivo.tagName === 'TEXTAREA' || objetivo.tagName === 'SELECT'
      );
      const enCampoCodigo = objetivo === codigoInputRef.current;

      // Ayuda: se abre y cierra desde cualquier lado
      if (e.key === 'F1' || (e.key === '?' && !enCampo)) {
        e.preventDefault();
        setMostrarAyuda(v => !v);
        return;
      }
      if (mostrarAyuda) {
        if (e.key === 'Escape' || e.key === 'Enter') {
          e.preventDefault();
          setMostrarAyuda(false);
          enfocarCodigo();
        }
        return;
      }

      // --- Ticket abierto: Enter arranca la venta siguiente ---
      if (showReceipt) {
        if (e.key === 'Enter' || e.key === 'Escape') {
          e.preventDefault();
          cerrarRecibo();
        }
        return;
      }

      // --- Modal de Mercado Pago ---
      if (showMpQR) {
        if (e.key === 'Escape') {
          e.preventDefault();
          cancelMercadoPago();
        }
        return;
      }

      // --- Modal de cobro ---
      if (showPaymentModal) {
        if (e.key === 'Escape') {
          e.preventDefault();
          if (selectedMethod) {
            setSelectedMethod(null);
            setMontoRecibido('');
          } else {
            cerrarCobro();
          }
          return;
        }
        // Con el método elegido, el campo de monto maneja su propio Enter
        if (selectedMethod) return;

        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
          e.preventDefault();
          setMetodoResaltado(i => {
            const n = metodosHabilitados.length;
            return (i + (e.key === 'ArrowDown' ? 1 : -1) + n) % n;
          });
          return;
        }
        if (e.key === 'Enter') {
          e.preventDefault();
          const metodo = metodosHabilitados[metodoResaltado];
          if (metodo === 'EFECTIVO') setSelectedMethod('EFECTIVO');
          else if (metodo === 'MERCADOPAGO') handleMercadoPago();
          else processCheckout(metodo);
        }
        return;
      }

      // --- Pantalla principal del POS ---
      if (!caja) return;

      if (e.key === 'Escape') {
        setLineaSeleccionada(-1);
        enfocarCodigo();
        return;
      }

      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        if (cart.length === 0) return;
        // En el campo de código las flechas navegan el carrito en vez de mover el cursor
        e.preventDefault();
        setLineaSeleccionada(i => {
          const paso = e.key === 'ArrowDown' ? 1 : -1;
          if (i < 0) return e.key === 'ArrowDown' ? 0 : cart.length - 1;
          return (i + paso + cart.length) % cart.length;
        });
        return;
      }

      if (lineaSeleccionada >= 0 && lineaSeleccionada < cart.length) {
        if (e.key === '+' || (e.key === 'ArrowRight' && enCampoCodigo && !manualCode)) {
          e.preventDefault();
          cambiarCantidad(lineaSeleccionada, 1);
          return;
        }
        if (e.key === '-' || (e.key === 'ArrowLeft' && enCampoCodigo && !manualCode)) {
          e.preventDefault();
          cambiarCantidad(lineaSeleccionada, -1);
          return;
        }
        if (e.key === 'Delete') {
          e.preventDefault();
          quitarLinea(lineaSeleccionada);
          return;
        }
      }

      // Cualquier tecla imprimible devuelve el foco al campo de código, así el
      // lector funciona aunque el cajero haya hecho clic en otro lado.
      if (!enCampo && e.key.length === 1 && !e.ctrlKey && !e.altKey && !e.metaKey) {
        enfocarCodigo();
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [
    cart, lineaSeleccionada, showPaymentModal, showReceipt, showMpQR,
    selectedMethod, metodoResaltado, metodosHabilitados, caja, manualCode, mostrarAyuda,
  ]);

  // Al quedar la pantalla libre de modales, el foco vuelve al campo de código
  useEffect(() => {
    if (caja && !showPaymentModal && !showReceipt && !showMpQR && !mostrarAyuda) {
      enfocarCodigo();
    }
  }, [caja, showPaymentModal, showReceipt, showMpQR, mostrarAyuda]);

  // Al abrir el cobro se arranca siempre desde el primer método
  useEffect(() => {
    if (showPaymentModal) setMetodoResaltado(0);
  }, [showPaymentModal]);

  const handleMercadoPago = async () => {
    if (cart.length === 0) return;
    try {
      const summaryTitle = cart.length === 1 ? cart[0].producto.nombre : `Compra de ${cart.length} artículos`;
      const result = await api.createMercadoPagoPreference(summaryTitle, 1, total);
      
      setMpQrUrl(result.init_point);
      setShowMpQR(true);
      setShowPaymentModal(false); // Hide the main payment modal
      
      // Start polling
      const totalEsperado = total;
      const interval = setInterval(async () => {
        try {
          const status = await api.checkMercadoPagoStatus(result.external_reference, totalEsperado);
          if (status.approved) {
            clearInterval(interval);
            setShowMpQR(false);
            // La referencia viaja con la venta: el servidor vuelve a confirmar
            // el cobro con ella antes de registrarla.
            processCheckout('MERCADOPAGO', undefined, undefined, result.external_reference);
            showToast('Pago acreditado por Mercado Pago', 'success');
          } else if (status.monto_insuficiente) {
            // Se pagó, pero por menos de lo que vale la compra: no se cierra
            // la venta sola, decide el cajero.
            clearInterval(interval);
            showToast(
              `El pago recibido (${money(status.pagado)}) es menor al total (${money(totalEsperado)})`,
              'error'
            );
          }
        } catch (e) {
          console.error("Polling error", e);
        }
      }, 3000);
      setMpPollingRef(interval);

    } catch (err: any) {
      showToast("Error iniciando Mercado Pago: " + err.message, 'error');
    }
  };

  const cancelMercadoPago = () => {
    if (mpPollingRef) clearInterval(mpPollingRef);
    setShowMpQR(false);
    setShowPaymentModal(true); // Go back to payment selection
  };

  const handleAbrirCaja = async (e: React.FormEvent) => {
    e.preventDefault();
    const monto = Number(montoInicial.replace(',', '.'));
    try {
      const nuevaCaja = await api.abrirCaja(monto);
      setCaja(nuevaCaja);
      recordarCaja(nuevaCaja);
    } catch (err: any) {
      // Sin servidor se abre un turno provisorio para no frenar la venta.
      // Queda marcado como pendiente y se registra al volver la conexión.
      const provisoria = cajaProvisoria(0, monto);
      setCaja(provisoria);
      recordarCaja(provisoria);
      showToast('Sin conexión: turno abierto en este equipo, se registrará al volver la red', 'info');
    }
  };

  const handleCerrarCaja = async (e: React.FormEvent) => {
    e.preventDefault();
    const monto = Number(montoFinal.replace(',', '.'));

    // Cerrar con ventas sin sincronizar dejaría el arqueo mal calculado
    if (ventasPendientes > 0) {
      showToast(
        `Quedan ${ventasPendientes} venta${ventasPendientes > 1 ? 's' : ''} sin sincronizar. Esperá a que vuelva la conexión antes de cerrar.`,
        'error'
      );
      return;
    }

    if (esProvisoria(caja)) {
      showToast('Este turno todavía no está registrado en el servidor. Esperá a que vuelva la conexión.', 'error');
      return;
    }

    try {
      const cerrada = await api.cerrarCaja(caja.id, monto);
      showToast(`Caja cerrada con éxito. Diferencia: ${money(cerrada.diferencia_calculada)}`, 'success');
      setCaja(null);
      recordarCaja(null);
      setShowCloseCaja(false);
    } catch (err: any) {
      showToast('No se pudo cerrar la caja: ' + err.message, 'error');
    }
  };

  const syncVentas = async () => {
    try {
      // Si el turno se abrió sin conexión, primero hay que registrarlo:
      // las ventas necesitan una caja real del servidor.
      if (esProvisoria(caja)) {
        try {
          const real = await api.getCajaEstado() || await api.abrirCaja(caja.monto_inicial);
          setCaja(real);
          recordarCaja(real);
          showToast('Turno registrado en el servidor', 'success');
        } catch {
          return; // sigue sin conexión: se reintenta más adelante
        }
      }

      // Las ya rechazadas se saltean: reintentarlas trabaría a las de atrás.
      const offlineVentas = (await db.ventasOffline.toArray()).filter(v => !v.rechazo);
      if (offlineVentas.length === 0) return;

      let sincronizadas = 0;
      let rechazadas = 0;

      for (const venta of offlineVentas) {
        try {
          await api.createVenta({
            uuid_cliente: venta.uuid_cliente,
            metodo_pago: venta.metodo_pago,
            pago_referencia: venta.pago_referencia,
            monto_recibido: venta.monto_recibido,
            vuelto: venta.vuelto,
            descuento_id: venta.descuento_id ?? null,
            estado_sincronizacion: true,
            // Cuándo se cobró de verdad. Sin esto la venta quedaba fechada
            // cuando se sincronizaba: un corte el viernes a la tarde movía
            // todas esas ventas al sábado y los dos arqueos daban mal.
            fecha_hora_local: venta.fecha_hora_local,
            // Lo que decía el ticket. El servidor recalcula el total con su
            // catálogo —así tiene que ser—, pero si el precio cambió mientras
            // el equipo estaba sin señal los dos números no coinciden, y esa
            // diferencia tiene que quedar registrada en algún lado.
            total_cobrado: venta.total,
            detalles: venta.detalles.map(d => ({
              producto_id: d.producto_id,
              cantidad: d.cantidad,
              precio_unitario: d.precio_unitario
            }))
          });
        } catch (err: any) {
          const destino = clasificarFalloDeEnvio(err?.status, venta.intentos ?? 0);

          if (destino === 'cortar') return;  // se reintenta todo más adelante

          if (destino === 'reintentar') {
            if (venta.id) {
              await db.ventasOffline.update(venta.id, { intentos: (venta.intentos ?? 0) + 1 });
            }
            continue;
          }

          if (destino === 'rechazada') {
            // La venta NO se borra: si hubo plata de por medio, el registro
            // tiene que quedar. Se marca para que no se reintente sola y para
            // que alguien la mire.
            if (venta.id) await db.ventasOffline.update(venta.id, { rechazo: err.message });
            rechazadas++;
            continue;
          }
          // 'registrada': el servidor ya la tiene, sigue al borrado de abajo
        }

        // Registrada en el servidor: se borra de la cola local
        if (venta.id) {
          await db.ventasOffline.delete(venta.id);
        }
        sincronizadas++;
      }

      if (sincronizadas > 0) {
        showToast("Ventas locales sincronizadas con el servidor", 'success');
      }
      if (rechazadas > 0) {
        showToast(
          `${rechazadas} venta(s) quedaron sin registrar: el servidor las rechazó. Revisalas con el encargado.`,
          'error'
        );
      }

    } catch (err) {
      console.error("Error sincronizando ventas:", err);
    }
  };

  useEffect(() => {
    // Con sesión offline no hay token, así que no se puede sincronizar todavía:
    // las ventas quedan en la cola —que es su lugar— hasta que alguien entre
    // con el servidor a mano. Se avisa, porque si no el cajero ve el contador
    // de pendientes subir con la señal ya de vuelta y no entiende por qué.
    if (!isOffline && sesionOffline) {
      showToast(
        'Volvió la conexión. Cerrá sesión y entrá de nuevo para que se sincronicen las ventas.',
        'success',
      );
      return;
    }
    if (!isOffline && isAuthenticated) {
      syncVentas();
    }
  }, [isOffline, isAuthenticated, sesionOffline]);

  if (!isAuthenticated) {
    // Todavía no se sabe si hay usuarios: evita mostrar el login (o el
    // asistente) un instante antes de tener la respuesta del servidor.
    if (necesitaPrimerArranque === null) {
      return <div className="min-h-screen flex items-center justify-center p-4" />;
    }

    if (necesitaPrimerArranque) {
      return (
        <div className="min-h-screen flex items-center justify-center p-4">
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="glass-card p-8 w-full max-w-md relative overflow-hidden">
            <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-brand to-accent"></div>
            <div className="flex justify-center mb-2">
              <Logo size={56} subtitle="Primer arranque" />
            </div>
            <p className="text-sm text-text-secondary text-center mb-6">
              Todavía no hay ningún usuario cargado. Creá la cuenta de administrador para empezar.
            </p>
            <form onSubmit={handlePrimerArranque} className="flex flex-col gap-5">
              <input
                className="glass-input p-4 rounded-xl" type="text" placeholder="Nombre del comercio (opcional)"
                value={nombreComercioInicial} onChange={e => setNombreComercioInicial(e.target.value)}
              />
              <input
                className="glass-input p-4 rounded-xl" type="text" placeholder="Usuario administrador"
                value={username} onChange={e => setUsername(e.target.value)} required
              />
              <input
                className="glass-input p-4 rounded-xl" type="password" placeholder="PIN de acceso"
                value={password} onChange={e => setPassword(e.target.value)} required
              />
              <input
                className="glass-input p-4 rounded-xl" type="password" placeholder="Repetí el PIN"
                value={pinConfirmado} onChange={e => setPinConfirmado(e.target.value)} required
              />
              <button type="submit" disabled={enviandoPrimerArranque} className="btn-primary py-4 mt-2 disabled:opacity-60">
                {enviandoPrimerArranque ? 'Creando...' : 'Crear administrador y entrar'}
              </button>
            </form>
          </motion.div>
        </div>
      );
    }

    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="glass-card p-8 w-full max-w-md relative overflow-hidden">
          <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-brand to-accent"></div>
          <div className="flex justify-center mb-6">
            <Logo size={56} subtitle="Acceso a Caja" />
          </div>
          <form onSubmit={handleLogin} className="flex flex-col gap-5">
            <input
              className="glass-input p-4 rounded-xl" type="text" placeholder="Usuario"
              value={username} onChange={e => setUsername(e.target.value)} required
            />
            <input
              className="glass-input p-4 rounded-xl" type="password" placeholder="PIN de Acceso"
              value={password} onChange={e => setPassword(e.target.value)} required
            />
            <button type="submit" className="btn-primary py-4 mt-2">
              Ingresar al POS
            </button>
          </form>
          <button
            onClick={() => setMostrarDiagnostico(true)}
            className="w-full text-center text-xs text-text-muted hover:text-text-secondary mt-4 underline"
          >
            ¿No podés entrar? Diagnóstico de conexión
          </button>
        </motion.div>
        {mostrarDiagnostico && <DiagnosticoRed onClose={() => setMostrarDiagnostico(false)} />}
      </div>
    );
  }

  return (
    <div className="min-h-screen text-text-primary p-4 md:p-8 relative selection:bg-brand selection:text-white">
      <header className="flex justify-between items-center mb-8">
        <div className="flex items-center gap-3 min-w-0">
          <Logo size={40} />
          {/* Se entró validando contra este equipo, sin servidor. Se puede
              vender, pero nada llega al servidor hasta volver a entrar. */}
          {sesionOffline && (
            <button
              onClick={() => { setSesionOffline(false); setIsAuthenticated(false); setPassword(''); }}
              title="Entraste sin conexión. Tocá para volver a entrar cuando haya señal y que se sincronicen las ventas."
              className="text-xs font-semibold px-2 py-1 rounded-full border whitespace-nowrap bg-status-warning/20 text-status-warning border-status-warning/30"
            >
              Sesión sin conexión
            </button>
          )}
          {caja && (
            <span className={`text-xs font-semibold px-2 py-1 rounded-full border whitespace-nowrap ${
              esProvisoria(caja)
                ? 'bg-status-warning/20 text-status-warning border-status-warning/30'
                : 'bg-status-success/20 text-status-success border-status-success/30'
            }`}>
              {esProvisoria(caja) ? 'Turno sin registrar' : 'Turno Abierto'}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {/* Ventas cobradas que esperan conexión para llegar al servidor */}
          {ventasPendientes > 0 && (
            <span
              className="flex items-center gap-1.5 text-xs font-semibold bg-status-warning/20 text-status-warning px-2.5 py-1.5 rounded-lg border border-status-warning/30"
              title="Están guardadas en este equipo y se envían solas al volver la conexión"
            >
              <CloudOff size={14} />
              {ventasPendientes} sin enviar
            </span>
          )}
          {/* Rechazadas por el servidor: no se reintentan solas y hay que mirarlas */}
          {ventasRechazadas > 0 && (
            <span
              className="flex items-center gap-1.5 text-xs font-semibold bg-status-error/20 text-status-error px-2.5 py-1.5 rounded-lg border border-status-error/30"
              title="El servidor las rechazó. No se van a enviar solas: mostráselas al encargado."
            >
              <AlertTriangle size={14} />
              {ventasRechazadas} rechazada{ventasRechazadas > 1 ? 's' : ''}
            </span>
          )}
          <div className="flex items-center gap-2">
            {isOffline ? <WifiOff className="text-status-error" /> : <Wifi className="text-status-success" />}
            <span className="text-sm text-text-secondary hidden md:inline">{isOffline ? 'Sin conexión' : 'En línea'}</span>
          </div>
          {lastSale && (
            <button
              onClick={() => handleImprimir(lastSale)}
              title="Reimprimir el ticket de la última venta"
              className="flex items-center gap-1.5 text-xs font-semibold bg-white/5 hover:bg-white/10 text-text-secondary px-2.5 py-1.5 rounded-lg border border-white/10 transition-colors"
            >
              <Printer size={14} /> <span className="hidden md:inline">Reimprimir última venta</span>
            </button>
          )}
          {caja && (
            <button onClick={() => setShowCloseCaja(true)} className="bg-status-error/20 text-status-error hover:bg-status-error/30 px-3 py-1 rounded-md text-sm font-semibold transition-colors">
              Cerrar Caja
            </button>
          )}
        </div>
      </header>

      {/* Aviso persistente: el cajero tiene que saber que sigue vendiendo bien */}
      {isOffline && caja && (
        <div className="mb-6 glass-card p-4 border-l-4 border-l-status-warning flex items-start gap-3">
          <CloudOff size={20} className="text-status-warning shrink-0 mt-0.5" />
          <div className="text-sm">
            <p className="font-bold text-status-warning">
              {servidorCaido ? 'El servidor no responde' : 'Estás trabajando sin conexión'}
            </p>
            <p className="text-text-secondary mt-0.5">
              Podés seguir vendiendo normalmente: las ventas se guardan en este equipo y se envían
              solas cuando vuelva la conexión. Mercado Pago no está disponible hasta entonces.
            </p>
          </div>
        </div>
      )}

      {/* BLOQUEO SI NO HAY CAJA */}
      {!caja && !loadingCaja && (
        <div className="absolute inset-0 z-40 bg-neutral-bg1 flex items-center justify-center p-4">
          <div className="glass-card p-8 w-full max-w-md text-center">
            <h2 className="text-2xl font-bold text-brand mb-2">Apertura de Caja</h2>
            <p className="text-text-secondary mb-6">Declara el efectivo inicial para comenzar tu turno y habilitar el escáner.</p>
            <form onSubmit={handleAbrirCaja} className="flex flex-col gap-4">
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-2 text-left">
                  Efectivo Físico Inicial ({config.moneda_simbolo})
                </label>
                <input
                  type="text"
                  inputMode="decimal"
                  autoComplete="off"
                  required
                  className="glass-input w-full p-4 rounded-xl text-2xl font-bold text-center text-accent tracking-wider"
                  value={montoInicial}
                  onChange={e => {
                    const r = sanitizarMonto(e.target.value, montoInicial, topeEfectivo);
                    setMontoInicial(r.texto);
                    if (r.rechazo === 'tope') {
                      showToast(`El máximo permitido es ${formatearTope(topeEfectivo, config.moneda_simbolo)}`, 'error');
                    }
                  }}
                  placeholder="0.00"
                />
                <p className="text-xs text-text-muted mt-2 text-left">
                  Máximo {formatearTope(topeEfectivo, config.moneda_simbolo)}
                </p>
              </div>
              <button type="submit" className="btn-primary py-4 mt-2">
                Abrir Caja y Comenzar
              </button>
            </form>
          </div>
        </div>
      )}

      {/* MODAL CIERRE CAJA */}
      <AnimatePresence>
      {showCloseCaja && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4">
          <motion.div initial={{ scale: 0.9 }} animate={{ scale: 1 }} exit={{ scale: 0.9 }} className="glass-card p-8 w-full max-w-md text-center">
            <h2 className="text-2xl font-bold text-status-error mb-2">Cierre de Caja</h2>
            <p className="text-text-secondary mb-6">Cuenta el dinero físico en tu caja registradora y decláralo abajo. El sistema calculará la diferencia.</p>
            <form onSubmit={handleCerrarCaja} className="flex flex-col gap-4">
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-2 text-left">
                  Efectivo Físico Final ({config.moneda_simbolo})
                </label>
                <input
                  type="text"
                  inputMode="decimal"
                  autoComplete="off"
                  required
                  className="glass-input border-status-error/50 focus:border-status-error w-full p-4 rounded-xl text-2xl font-bold text-center text-status-error tracking-wider shadow-[0_0_15px_rgba(239,68,68,0.2)] focus:shadow-[0_0_20px_rgba(239,68,68,0.4)]"
                  value={montoFinal}
                  onChange={e => {
                    const r = sanitizarMonto(e.target.value, montoFinal, topeEfectivo);
                    setMontoFinal(r.texto);
                    if (r.rechazo === 'tope') {
                      showToast(`El máximo permitido es ${formatearTope(topeEfectivo, config.moneda_simbolo)}`, 'error');
                    }
                  }}
                  placeholder="0.00"
                />
                <p className="text-xs text-text-muted mt-2 text-left">
                  Máximo {formatearTope(topeEfectivo, config.moneda_simbolo)}
                </p>
              </div>
              <div className="flex gap-3 mt-2">
                <button type="button" onClick={() => setShowCloseCaja(false)} className="flex-1 bg-neutral-bg3 hover:bg-neutral-bg4 text-text-secondary py-4 rounded-xl font-bold transition-colors">Cancelar</button>
                <button type="submit" className="flex-[2] bg-status-error hover:bg-red-500 text-white py-4 rounded-xl font-bold transition-all hover:shadow-[0_0_15px_rgba(239,68,68,0.5)]">
                  Cerrar Caja
                </button>
              </div>
            </form>
          </motion.div>
        </motion.div>
      )}
      </AnimatePresence>

      <main className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 flex flex-col gap-6">
          {/* Scanner Panel */}
          <section className="glass-card p-4">
          <div className="flex items-center justify-between mb-4 gap-3">
            <h2 className="text-lg font-semibold flex items-center gap-2"><ScanLine /> Escáner de Productos</h2>
            {cameraStatus === 'available' && (
              <button
                onClick={() => setScannerActivo(v => !v)}
                className={`text-sm font-semibold px-4 py-2 rounded-lg transition-colors flex items-center gap-2 ${
                  scannerActivo
                    ? 'bg-status-error/20 text-status-error hover:bg-status-error/30'
                    : 'bg-brand/20 text-brand-light hover:bg-brand/30'
                }`}
              >
                {scannerActivo ? <><CameraOff size={16} /> Apagar</> : <><Camera size={16} /> Activar cámara</>}
              </button>
            )}
          </div>

          {cameraStatus === 'checking' && (
            <div className="bg-white/5 p-4 rounded-xl text-center text-text-muted text-sm">
              Detectando cámara…
            </div>
          )}

          {cameraStatus === 'unavailable' && (
            <div className="bg-white/5 border border-white/10 p-4 rounded-xl flex items-center gap-3 text-sm">
              <CameraOff size={20} className="text-text-muted shrink-0" />
              <div>
                <p className="text-text-secondary font-medium">Este equipo no tiene cámara</p>
                <p className="text-text-muted text-xs mt-0.5">Usá un lector USB o el ingreso manual de abajo.</p>
              </div>
            </div>
          )}

          {cameraStatus === 'inseguro' && (
            <div className="bg-status-warning/10 border border-status-warning/30 p-4 rounded-xl flex items-center gap-3 text-sm">
              <CameraOff size={20} className="text-status-warning shrink-0" />
              <div>
                <p className="text-text-secondary font-medium">La cámara necesita una conexión segura</p>
                <p className="text-text-muted text-xs mt-0.5">
                  Entraste por <span className="font-mono">{window.location.hostname}</span> sin HTTPS y el
                  navegador no presta la cámara. Usá un lector USB o el ingreso manual de abajo.
                </p>
              </div>
            </div>
          )}

          {cameraStatus === 'available' && !scannerActivo && (
            <div className="bg-white/5 border border-white/10 p-6 rounded-xl text-center">
              <Camera size={28} className="mx-auto mb-3 text-text-muted" />
              <p className="text-text-secondary text-sm">Cámara disponible</p>
              <p className="text-text-muted text-xs mt-1">Tocá "Activar cámara" para escanear con la cámara.</p>
            </div>
          )}

          {cameraStatus === 'available' && scannerActivo && (
            <div id="reader" className="w-full bg-white text-black overflow-hidden rounded-md"></div>
          )}

          <div className="mt-4">
            <h3 className="text-sm text-text-secondary mb-2">
              {cameraStatus === 'available' ? 'Ingreso Manual (Respaldo)' : 'Ingreso de Código'}
            </h3>
            <form onSubmit={handleManualSubmit} className="flex gap-2">
              {/* type="text": con number el navegador recorta los ceros a la
                  izquierda de los códigos y las flechas cambian el valor. */}
              <input
                ref={codigoInputRef}
                type="text"
                inputMode="numeric"
                autoComplete="off"
                value={manualCode}
                onChange={e => setManualCode(e.target.value)}
                placeholder="Escaneá o escribí el código y presioná Enter"
                autoFocus
                className="glass-input flex-1 p-3 rounded-xl font-mono tracking-widest text-accent"
              />
              <button type="submit" className="btn-primary px-6 rounded-xl">
                {manualCode.trim() ? 'Añadir' : 'Cobrar'}
              </button>
            </form>
            <p className="text-xs text-text-muted mt-2">
              Enter agrega el producto · con el campo vacío, Enter va directo a cobrar ·{' '}
              <button type="button" onClick={() => setMostrarAyuda(true)} className="text-brand-light hover:underline font-semibold">
                ver atajos (F1)
              </button>
            </p>
          </div>
          </section>

          <section className="glass-card p-5 flex-1 relative overflow-hidden">
            <div className="absolute top-0 right-0 w-32 h-32 bg-brand/10 rounded-full blur-3xl -z-10 pointer-events-none"></div>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-5">
              <h2 className="text-xl font-bold flex items-center gap-2"><Package className="text-accent" /> Catálogo</h2>
              <div className="flex items-center gap-3">
                <label className="flex items-center gap-2 text-xs text-text-secondary cursor-pointer whitespace-nowrap select-none">
                  <input
                    type="checkbox"
                    checked={ocultarSinStock}
                    onChange={e => {
                      setOcultarSinStock(e.target.checked);
                      localStorage.setItem('ocultar_sin_stock', e.target.checked ? '1' : '0');
                    }}
                  />
                  Ocultar sin stock
                </label>
                <div className="relative sm:w-64">
                  <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
                  <input
                    type="text"
                    value={busquedaCatalogo}
                    onChange={e => setBusquedaCatalogo(e.target.value)}
                    placeholder="Buscar producto…"
                    className="glass-input w-full p-2 pl-9 rounded-xl text-sm"
                  />
                </div>
              </div>
            </div>
            {categoriasConProductos.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-4">
                <button
                  onClick={() => setCategoriaActiva(null)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                    categoriaActiva === null ? 'bg-brand text-white' : 'bg-white/5 text-text-secondary hover:bg-white/10'
                  }`}
                >
                  Todo
                </button>
                {categoriasConProductos.map(c => (
                  <button
                    key={c.id}
                    onClick={() => setCategoriaActiva(categoriaActiva === c.id ? null : c.id)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                      categoriaActiva === c.id ? 'bg-brand text-white' : 'bg-white/5 text-text-secondary hover:bg-white/10'
                    }`}
                  >
                    {c.nombre}
                  </button>
                ))}
              </div>
            )}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 overflow-y-auto max-h-[400px] pr-2 custom-scrollbar">
              {productosFiltrados.map(p => (
                <motion.div
                  whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }} key={p.id}
                  onClick={() => addToCart(p)}
                  className={`glass cursor-pointer rounded-xl p-3 flex flex-col justify-between transition-colors group relative ${
                    sinStock(p) ? 'opacity-45 hover:opacity-100 border-status-error/40' : 'hover:border-brand/50'
                  }`}
                >
                  {sinStock(p) && (
                    <span className="absolute top-2 right-2 bg-status-error text-white text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wide">
                      Sin stock
                    </span>
                  )}
                  <div>
                    <ProductImage src={p.imagen_url} alt={p.nombre} className="w-full h-20 rounded-lg mb-2" iconSize={24} />
                    <h3 className="font-semibold text-sm leading-tight mb-1 truncate text-white group-hover:text-brand-light transition-colors" title={p.nombre}>{p.nombre}</h3>
                    <p className="text-accent font-bold text-lg">{money(p.precio_venta)}</p>
                  </div>
                  <div className="mt-2 flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${p.stock_actual < 5 ? 'bg-status-error shadow-[0_0_8px_#EF4444]' : 'bg-status-success shadow-[0_0_8px_#10B981]'}`}></div>
                    <span className="text-xs text-text-secondary font-medium">
                      {sinStock(p) ? `El sistema dice ${p.stock_actual}` : `Stock: ${p.stock_actual}`}
                    </span>
                  </div>
                </motion.div>
              ))}
              {productosFiltrados.length === 0 && (
                <p className="text-text-muted col-span-full italic py-6 text-center">
                  {busquedaCatalogo
                    ? `Sin resultados para "${busquedaCatalogo}"`
                    : 'No hay productos en catálogo local.'}
                </p>
              )}
            </div>
          </section>
        </div>

        <section className="glass-card p-5 flex flex-col h-[600px] lg:h-auto relative">
          <div className="absolute bottom-0 left-0 w-full h-1/2 bg-gradient-to-t from-brand/5 to-transparent pointer-events-none rounded-b-2xl"></div>
          <div className="flex items-center justify-between mb-5">
            <h2 className="text-xl font-bold flex items-center gap-2"><ShoppingCart className="text-brand-light" /> Carrito Actual</h2>
            {cart.length > 0 && (
              <span className="text-xs text-text-muted bg-white/5 px-2 py-1 rounded-lg">
                ↑↓ elegir · +/− cantidad · Supr quitar
              </span>
            )}
          </div>

          <div className="flex-1 overflow-y-auto space-y-3 p-1 custom-scrollbar">
            <AnimatePresence>
            {cart.map((item, indice) => {
              const activa = indice === lineaSeleccionada;
              return (
              <motion.div
                layout
                initial={{ opacity: 0, x: -20, scale: 0.95 }}
                animate={{ opacity: 1, x: 0, scale: 1 }}
                exit={{ opacity: 0, scale: 0.9, x: 20 }}
                key={item.producto.id}
                onClick={() => setLineaSeleccionada(indice)}
                ref={el => { if (activa && el) el.scrollIntoView({ block: 'nearest' }); }}
                className={`flex justify-between items-center gap-3 p-4 rounded-xl cursor-pointer transition-colors ${
                  activa
                    ? 'bg-brand/20 border border-brand/60 shadow-glow'
                    : 'glass hover:bg-white/10'
                }`}
              >
                <div className="min-w-0 flex-1">
                  <p className="font-semibold text-white truncate">{item.producto.nombre}</p>
                  <p className="text-sm text-text-secondary font-medium">
                    {money(item.producto.precio_venta)} x <span className="text-brand-light font-bold">{item.cantidad}</span>
                  </p>
                </div>

                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={e => { e.stopPropagation(); cambiarCantidad(indice, -1); }}
                    className="w-7 h-7 rounded-lg bg-white/5 hover:bg-white/15 flex items-center justify-center text-text-secondary hover:text-white transition-colors"
                    title="Quitar una unidad (−)"
                  >
                    <Minus size={14} />
                  </button>
                  <button
                    onClick={e => { e.stopPropagation(); cambiarCantidad(indice, 1); }}
                    className="w-7 h-7 rounded-lg bg-white/5 hover:bg-white/15 flex items-center justify-center text-text-secondary hover:text-white transition-colors"
                    title="Agregar una unidad (+)"
                  >
                    <Plus size={14} />
                  </button>
                  <button
                    onClick={e => { e.stopPropagation(); quitarLinea(indice); }}
                    className="w-7 h-7 rounded-lg bg-white/5 hover:bg-status-error/20 flex items-center justify-center text-text-muted hover:text-status-error transition-colors ml-1"
                    title="Quitar del carrito (Supr)"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>

                <div className="font-bold text-accent text-lg shrink-0 w-24 text-right">
                  {money(item.producto.precio_venta * item.cantidad)}
                </div>
              </motion.div>
            );})}
            </AnimatePresence>
            {cart.length === 0 && (
              <div className="h-full flex flex-col items-center justify-center opacity-50">
                <ShoppingCart size={48} className="mb-4 text-text-muted" />
                <p className="text-text-muted font-medium text-lg">El carrito está vacío</p>
                <p className="text-text-muted text-sm mt-1">Escaneá un producto para empezar</p>
              </div>
            )}
          </div>

          <div className="mt-4 pt-5 border-t border-border-subtle relative z-10">
            {/* Selector de descuento: sólo si hay descuentos vigentes cargados */}
            {descuentos.length > 0 && cart.length > 0 && (
              <div className="mb-4">
                <label className="flex items-center gap-2 text-xs text-text-secondary uppercase tracking-wide mb-2">
                  <Tag size={14} /> Descuento
                </label>
                <select
                  value={descuentoAplicado?.id ?? ''}
                  onChange={e => {
                    const id = Number(e.target.value);
                    setDescuentoAplicado(id ? descuentos.find(d => d.id === id) ?? null : null);
                  }}
                  className="glass-input w-full p-3 rounded-xl text-sm"
                >
                  <option value="">Sin descuento</option>
                  {descuentos.map(d => (
                    <option key={d.id} value={d.id}>
                      {d.nombre} ({d.tipo === 'PORCENTAJE' ? `${d.valor}%` : money(d.valor)})
                    </option>
                  ))}
                </select>
              </div>
            )}

            {(montoDescuento > 0 || iva.iva > 0) && cart.length > 0 && (
              <div className="space-y-1 mb-3 text-sm">
                <div className="flex justify-between text-text-secondary">
                  <span>Subtotal</span>
                  <span>{money(subtotal)}</span>
                </div>
                {montoDescuento > 0 && (
                  <div className="flex justify-between text-status-warning font-semibold">
                    <span className="truncate mr-2">{descuentoAplicado?.nombre}</span>
                    <span className="shrink-0">−{money(montoDescuento)}</span>
                  </div>
                )}
                {iva.iva > 0 && (
                  <div className="flex justify-between text-text-secondary">
                    <span>
                      {config.iva_nombre} {config.iva_porcentaje}%
                      {config.iva_incluido_en_precio && <span className="text-text-muted text-xs ml-1">(incluido)</span>}
                    </span>
                    <span>{config.iva_incluido_en_precio ? '' : '+'}{money(iva.iva)}</span>
                  </div>
                )}
              </div>
            )}

            <div className="flex justify-between items-end mb-6">
              <span className="text-text-secondary font-medium uppercase tracking-wider text-sm">Total a Pagar</span>
              <span className="text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-brand-light to-accent drop-shadow-sm">{money(total)}</span>
            </div>
            <button
              onClick={() => setShowPaymentModal(true)}
              disabled={cart.length === 0}
              className="btn-primary py-4 text-xl w-full flex items-center justify-center gap-2"
            >
              Completar Venta <span className="text-2xl leading-none">→</span>
            </button>
          </div>
        </section>
      </main>

      {/* Modal Método de Pago */}
      <AnimatePresence>
      {showPaymentModal && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-50 bg-black/80 flex flex-col items-center justify-end md:justify-center p-4">
          <motion.div initial={{ y: 100 }} animate={{ y: 0 }} exit={{ y: 100 }} className="glass-card p-6 w-full max-w-md bg-neutral-bg1/90 rounded-t-2xl md:rounded-2xl pb-10 md:pb-6">
            <h2 className="text-xl font-bold mb-6 text-center">Seleccionar Método de Pago</h2>
            <div className="text-center mb-6">
              {montoDescuento > 0 && (
                <p className="text-sm text-text-muted line-through mb-1">{money(subtotal)}</p>
              )}
              <div className="text-3xl font-bold text-brand-light">{money(total)}</div>
              {montoDescuento > 0 && (
                <p className="text-xs text-status-warning font-semibold mt-1 flex items-center justify-center gap-1">
                  <Tag size={12} /> {descuentoAplicado?.nombre} · −{money(montoDescuento)}
                </p>
              )}
              {iva.iva > 0 && (
                <p className="text-xs text-text-muted mt-1">
                  {config.iva_incluido_en_precio ? 'Incluye' : 'Más'} {config.iva_nombre} {config.iva_porcentaje}%: {money(iva.iva)}
                </p>
              )}
            </div>
            
            {selectedMethod === 'EFECTIVO' ? (
              <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} className="flex flex-col gap-5">
                <div>
                  <label className="block text-sm font-medium text-text-secondary mb-2 uppercase tracking-wide">Monto Recibido ({config.moneda_simbolo})</label>
                  {/* type="text" con inputMode decimal: el teclado numérico sigue
                      apareciendo en móvil, pero el filtrado lo hacemos nosotros
                      porque type="number" deja pasar notación científica y signos. */}
                  <input
                    type="text"
                    inputMode="decimal"
                    autoComplete="off"
                    className="glass-input w-full p-5 rounded-xl text-3xl font-extrabold text-center text-accent tracking-widest"
                    value={montoRecibido}
                    onChange={e => {
                      const r = sanitizarMonto(e.target.value, montoRecibido, topeEfectivo);
                      setMontoRecibido(r.texto);
                      if (r.rechazo === 'tope') {
                        showToast(`El máximo permitido es ${formatearTope(topeEfectivo, config.moneda_simbolo)}`, 'error');
                      }
                    }}
                    onKeyDown={e => {
                      // Enter cobra si alcanza; si el campo está vacío se asume
                      // importe justo, que es el caso más común con tarjeta o QR.
                      if (e.key !== 'Enter') return;
                      e.preventDefault();
                      const recibido = montoRecibido === '' ? total : Number(montoRecibido.replace(',', '.'));
                      if (recibido < total) {
                        showToast('El monto recibido es menor al total', 'error');
                        return;
                      }
                      processCheckout('EFECTIVO', recibido, recibido - total);
                    }}
                    placeholder={`Enter = importe justo (${money(total)})`}
                    autoFocus
                  />
                  <div className="flex justify-between items-center gap-2 mt-2">
                    <p className="text-xs text-text-muted">Escribí lo recibido y Enter · Esc vuelve</p>
                    <p className="text-xs text-text-muted shrink-0">
                      Máx. {formatearTope(topeEfectivo, config.moneda_simbolo)}
                    </p>
                  </div>

                  {/* Atajos con los billetes más usados: evitan tipear de más */}
                  <div className="flex flex-wrap gap-2 mt-3">
                    {sugerenciasEfectivo.map(monto => (
                      <button
                        key={monto}
                        type="button"
                        onClick={() => setMontoRecibido(String(monto))}
                        className="px-3 py-2 rounded-lg bg-white/5 hover:bg-brand/20 border border-white/10 hover:border-brand/40 text-sm font-semibold transition-colors"
                      >
                        {money(monto)}
                      </button>
                    ))}
                  </div>
                </div>
                {montoRecibido !== '' && Number(montoRecibido.replace(',', '.')) >= total && (
                  <motion.div initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="bg-status-success/10 p-5 rounded-xl text-center border border-status-success/30 shadow-[0_0_20px_rgba(16,185,129,0.15)] relative overflow-hidden">
                    <div className="absolute top-0 left-0 w-full h-1 bg-status-success/50"></div>
                    <p className="text-sm text-status-success font-semibold uppercase tracking-wider mb-1">Cambio a entregar</p>
                    <p className="text-5xl font-black text-status-success drop-shadow-md">{money(Number(montoRecibido.replace(',', '.')) - total)}</p>
                  </motion.div>
                )}
                <div className="flex gap-3 mt-4">
                  <button onClick={() => {setSelectedMethod(null); setMontoRecibido('');}} className="flex-1 glass py-4 rounded-xl font-bold hover:bg-white/10 transition-colors">Atrás</button>
                  <button
                    onClick={() => {
                      const recibido = montoRecibido === '' ? total : Number(montoRecibido.replace(',', '.'));
                      processCheckout('EFECTIVO', recibido, recibido - total);
                    }}
                    disabled={montoRecibido !== '' && Number(montoRecibido.replace(',', '.')) < total}
                    className="flex-[2] btn-primary py-4 text-lg"
                  >
                    Confirmar Pago
                  </button>
                </div>
              </motion.div>
            ) : (
              <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} className="flex flex-col gap-3">
                {/* La lista sale de los métodos habilitados en Configuración y en
                    ese mismo orden se mueve la selección con las flechas. */}
                {metodosHabilitados.map((metodo, indice) => {
                  const meta = METODOS_PAGO[metodo];
                  if (!meta) return null;
                  const Icono = meta.icono;
                  const resaltado = indice === metodoResaltado;
                  return (
                    <button
                      key={metodo}
                      onMouseEnter={() => setMetodoResaltado(indice)}
                      onClick={() => {
                        if (metodo === 'EFECTIVO') setSelectedMethod('EFECTIVO');
                        else if (metodo === 'MERCADOPAGO') handleMercadoPago();
                        else processCheckout(metodo);
                      }}
                      className={`p-5 rounded-xl font-semibold text-lg transition-all text-left flex items-center gap-3 border ${
                        resaltado
                          ? 'bg-brand/20 border-brand shadow-glow'
                          : 'glass border-white/15 hover:bg-white/10'
                      }`}
                    >
                      <Icono size={24} className={meta.color} />
                      <span className="flex-1">{meta.etiqueta}</span>
                      {resaltado && (
                        <span className="text-xs font-bold text-brand-light bg-brand/20 px-2 py-1 rounded">Enter</span>
                      )}
                    </button>
                  );
                })}
                <button onClick={cerrarCobro} className="mt-4 text-text-muted p-2 hover:text-white font-medium uppercase tracking-wide text-sm transition-colors">
                  Cancelar venta (Esc)
                </button>
                <p className="text-center text-xs text-text-muted">↑↓ para elegir · Enter para confirmar</p>
              </motion.div>
            )}
          </motion.div>
        </motion.div>
      )}
      </AnimatePresence>

      {/* Ayuda de atajos de teclado */}
      <AnimatePresence>
      {mostrarAyuda && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          onClick={() => { setMostrarAyuda(false); enfocarCodigo(); }}
          className="fixed inset-0 z-[60] bg-black/80 backdrop-blur-sm flex items-center justify-center p-4"
        >
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.95, opacity: 0 }}
            onClick={e => e.stopPropagation()}
            className="glass-card p-6 w-full max-w-lg max-h-[85vh] overflow-y-auto custom-scrollbar"
          >
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-xl font-bold flex items-center gap-2">
                <Keyboard size={22} className="text-brand-light" /> Atajos de teclado
              </h2>
              <button onClick={() => { setMostrarAyuda(false); enfocarCodigo(); }} className="text-text-secondary hover:text-white p-1 hover:bg-white/10 rounded-lg transition-colors">
                <X size={18} />
              </button>
            </div>

            {[
              {
                titulo: 'Vender',
                atajos: [
                  ['Escanear o escribir código + Enter', 'Agrega el producto al carrito'],
                  ['Enter con el campo vacío', 'Abre el cobro'],
                  ['↑ ↓', 'Elegir una línea del carrito'],
                  ['+ / −', 'Sumar o restar unidades'],
                  ['Supr', 'Quitar la línea del carrito'],
                  ['Esc', 'Deseleccionar la línea'],
                ],
              },
              {
                titulo: 'Cobrar',
                atajos: [
                  ['↑ ↓', 'Elegir el método de pago'],
                  ['Enter', 'Confirmar el método'],
                  ['Enter en efectivo', 'Cobra e imprime; vacío = importe justo'],
                  ['Esc', 'Volver o cancelar la venta'],
                ],
              },
              {
                titulo: 'Después de cobrar',
                atajos: [
                  ['Enter', 'Cerrar el ticket y arrancar la venta siguiente'],
                ],
              },
            ].map(grupo => (
              <div key={grupo.titulo} className="mb-5 last:mb-0">
                <h3 className="text-sm font-bold text-brand-light uppercase tracking-wide mb-2">{grupo.titulo}</h3>
                <div className="space-y-1">
                  {grupo.atajos.map(([tecla, desc]) => (
                    <div key={tecla} className="flex items-start gap-3 py-2 border-b border-white/5 last:border-0">
                      <kbd className="shrink-0 bg-white/10 border border-white/20 rounded-md px-2 py-1 text-xs font-mono font-bold text-white min-w-[3rem] text-center">
                        {tecla}
                      </kbd>
                      <span className="text-sm text-text-secondary pt-1">{desc}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}

            <p className="text-xs text-text-muted mt-4 text-center">
              El foco vuelve solo al campo de código, así el lector siempre funciona.
            </p>
          </motion.div>
        </motion.div>
      )}
      </AnimatePresence>

      {/* Modal QR Mercado Pago */}
      <AnimatePresence>
      {showMpQR && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-50 bg-black/80 flex flex-col items-center justify-center p-4 backdrop-blur-sm">
          <motion.div initial={{ scale: 0.9 }} animate={{ scale: 1 }} exit={{ scale: 0.9 }} className="glass-card p-8 w-full max-w-sm text-center bg-white text-black rounded-2xl">
            <h2 className="text-2xl font-bold mb-2 text-[#009EE3]">Mercado Pago</h2>
            <p className="text-gray-600 mb-6 font-medium">Escanea para pagar {money(total)}</p>
            
            <div className="flex justify-center mb-6 bg-white p-2 rounded-xl shadow-sm border border-gray-100">
              {mpQrUrl ? (
                <QRCodeCanvas value={mpQrUrl} size={220} level={"H"} />
              ) : (
                <div className="w-[220px] h-[220px] flex items-center justify-center bg-gray-50 rounded-lg">
                  <span className="animate-pulse text-gray-400">Generando QR...</span>
                </div>
              )}
            </div>
            
            <p className="text-sm text-gray-500 mb-6 animate-pulse">Esperando el pago...</p>
            
            <button onClick={cancelMercadoPago} className="w-full bg-gray-100 hover:bg-gray-200 text-gray-700 font-bold py-3 rounded-xl transition-colors">
              Cancelar
            </button>
            
            {/* Fallback button in case polling fails or cashier needs to force it */}
            <button 
              onClick={() => {
                if (mpPollingRef) clearInterval(mpPollingRef);
                setShowMpQR(false);
                processCheckout('TRANSFERENCIA');
              }} 
              className="w-full mt-3 bg-transparent text-[#009EE3] text-sm py-2 hover:underline"
            >
              Forzar Acreditación Manual
            </button>
          </motion.div>
        </motion.div>
      )}
      </AnimatePresence>

      {/* Recibo / Factura Modal */}
      {showReceipt && lastSale && (
        <div className="fixed inset-0 z-50 bg-black/85 backdrop-blur-sm flex items-center justify-center p-4">
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 10 }} animate={{ opacity: 1, scale: 1, y: 0 }}
            className="max-w-[80mm] w-full rounded-2xl overflow-hidden shadow-2xl"
          >
            <div className="bg-gradient-to-r from-brand to-accent px-4 py-3 flex items-center justify-between print:hidden">
              <div className="flex items-center gap-2">
                <LogoMark size={22} />
                <span className="text-white font-bold text-sm">Venta completada</span>
              </div>
              <button onClick={cerrarRecibo} className="text-white/80 hover:text-white p-1 hover:bg-white/10 rounded-lg transition-colors">
                <X size={18} />
              </button>
            </div>
          <div id="printable-receipt" className="print-area w-full bg-white text-black p-4 text-xs font-mono">
            <div className="text-center mb-4">
              {config.ticket_mostrar_logo && (
                <h2 className="text-xl font-bold font-mono">{config.negocio_nombre}</h2>
              )}
              {config.negocio_direccion && <p className="text-[10px] font-mono">{config.negocio_direccion}</p>}
              {config.negocio_telefono && <p className="text-[10px] font-mono">Tel: {config.negocio_telefono}</p>}
              {config.negocio_cuit && <p className="text-[10px] font-mono">CUIT: {config.negocio_cuit}</p>}
              <p className="text-xs font-mono mt-1">Ticket de Venta</p>
              <p className="text-xs font-mono">{new Date(lastSale.fecha_hora_local).toLocaleString()}</p>
            </div>
            <div className="border-t border-b border-dashed border-gray-400 py-2 mb-4">
              {lastSale.detalles.map((item, i) => (
                <div key={i} className="mb-1.5">
                  <div className="flex justify-between text-sm font-mono">
                    <span className="truncate mr-2">{item.cantidad}x {item.producto_nombre || `Prod #${item.producto_id}`}</span>
                    <span className="shrink-0">{money(item.precio_unitario * item.cantidad)}</span>
                  </div>
                  <div className="text-[10px] font-mono text-gray-500">
                    {money(item.precio_unitario)} c/u
                  </div>
                </div>
              ))}
            </div>
            {lastSale.descuento_nombre && lastSale.subtotal_bruto != null && (
              <div className="text-sm font-mono mb-2">
                <div className="flex justify-between text-gray-600">
                  <span>Subtotal</span>
                  <span>{money(lastSale.subtotal_bruto)}</span>
                </div>
                <div className="flex justify-between text-gray-600">
                  <span className="truncate mr-2">{lastSale.descuento_nombre}</span>
                  <span className="shrink-0">-{money(lastSale.subtotal_bruto - lastSale.total + (lastSale.iva_incluido === false ? (lastSale.iva_monto || 0) : 0))}</span>
                </div>
              </div>
            )}
            {/* Desglose impositivo: obligatorio en muchos países */}
            {config.mostrar_iva_en_ticket && !!lastSale.iva_monto && (
              <div className="text-sm font-mono mb-2 text-gray-600">
                <div className="flex justify-between">
                  <span>Neto gravado</span>
                  <span>{money(lastSale.total - lastSale.iva_monto)}</span>
                </div>
                <div className="flex justify-between">
                  <span>{lastSale.iva_nombre || 'IVA'} {lastSale.iva_porcentaje}%</span>
                  <span>{money(lastSale.iva_monto)}</span>
                </div>
              </div>
            )}
            <div className="flex justify-between font-bold font-mono text-lg mb-2">
              <span>TOTAL</span>
              <span>{money(lastSale.total)}</span>
            </div>
            {lastSale.metodo_pago === 'EFECTIVO' && lastSale.monto_recibido && lastSale.vuelto !== undefined && (
              <div className="text-sm font-mono mb-4 border-t border-dashed border-gray-400 pt-2">
                <div className="flex justify-between text-gray-600">
                  <span>Recibido:</span>
                  <span>{money(lastSale.monto_recibido)}</span>
                </div>
                <div className="flex justify-between font-bold mt-1">
                  <span>VUELTO:</span>
                  <span>{money(lastSale.vuelto)}</span>
                </div>
              </div>
            )}
            {lastSale.metodo_pago !== 'EFECTIVO' && (
              <div className="text-sm font-mono mb-4 text-right text-gray-600">
                Abonado con {lastSale.metodo_pago}
              </div>
            )}
            <div className="text-center text-xs font-mono mt-4">
              <p>{config.ticket_mensaje_pie}</p>
            </div>
            
            <div className="mt-6 space-y-3 print:hidden">
              <div className="mb-4">
                <label className="block text-xs font-semibold text-gray-500 uppercase mb-1">Teléfono del cliente (WhatsApp)</label>
                <div className="flex gap-2">
                  <span className="bg-gray-100 p-2 rounded-md font-mono text-gray-600">+</span>
                  <input
                    type="tel"
                    inputMode="numeric"
                    maxLength={15}
                    value={clientPhone}
                    // Sólo dígitos: lo que se escribe acá termina dentro de una
                    // URL, así que no se dejan pasar caracteres que la alteren.
                    onChange={e => setClientPhone(e.target.value.replace(/\D/g, '').slice(0, 15))}
                    placeholder="Ej. 5491122334455"
                    className="flex-1 bg-gray-100 border-none rounded-md p-2 font-mono text-gray-800"
                  />
                </div>
              </div>

              <button
                onClick={() => {
                  const telefono = clientPhone.replace(/\D/g, '');
                  if (telefono.length < 8) {
                    showToast('El número parece incompleto', 'error');
                    return;
                  }
                  const text = encodeURIComponent(`*${config.negocio_nombre}*\nTicket de Venta\nTotal: ${money(lastSale.total)}\nMétodo: ${lastSale.metodo_pago}\n${config.ticket_mensaje_pie}`);
                  window.open(`https://wa.me/${telefono}?text=${text}`, '_blank', 'noopener,noreferrer');
                }}
                disabled={clientPhone.replace(/\D/g, '').length < 8}
                className="w-full bg-[#25D366] hover:bg-[#128C7E] disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-bold py-3 rounded-lg flex justify-center items-center gap-2"
              >
                Enviar Ticket por WhatsApp
              </button>
              
              <button onClick={() => handleImprimir(lastSale)} className="w-full bg-black text-white py-3 rounded-lg flex justify-center items-center gap-2 font-bold hover:bg-gray-800">
                <Printer size={20} /> Imprimir Recibo Fisico
              </button>
              <button onClick={cerrarRecibo} className="w-full bg-gray-200 text-black py-3 rounded-lg font-bold mt-2">
                Nueva Venta (Enter)
              </button>
            </div>
          </div>
          </motion.div>
        </div>
      )}
    </div>
  );
}

export default POS;
