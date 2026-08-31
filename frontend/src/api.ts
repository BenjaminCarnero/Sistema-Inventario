const API_URL = '';

/**
 * Texto legible a partir del `detail` de FastAPI.
 *
 * En los errores de validación `detail` no es un texto sino una lista de
 * objetos, y concatenarla a secas deja un "[object Object]" — que es
 * justamente lo que después se guarda como motivo del rechazo para que lo
 * lea el encargado.
 */
function detalleLegible(detail: unknown, porDefecto = 'Error sincronizando venta'): string {
  if (typeof detail === 'string' && detail) return detail;
  if (Array.isArray(detail)) {
    const mensajes = detail
      .map(d => (typeof d?.msg === 'string' ? d.msg : null))
      .filter(Boolean);
    if (mensajes.length) return mensajes.join('; ');
  }
  return porDefecto;
}

export const api = {
  async register(nombre: string, pin_acceso: string, rol_id: number = 1) {
    const res = await fetch(`${API_URL}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nombre, pin_acceso, rol_id, estado: true })
    });
    if (!res.ok) throw new Error('Error al registrar');
    return res.json();
  },

  async login(username: string, password: string) {
    const formData = new URLSearchParams();
    formData.append('username', username);
    formData.append('password', password);

    let res: Response;
    try {
      res = await fetch(`${API_URL}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: formData
      });
    } catch {
      // No se llegó al servidor. Distinguirlo importa dos veces: el cajero veía
      // "Credenciales incorrectas" cuando el problema era el wifi —y se ponía a
      // probar PIN— y además es lo que habilita el acceso sin conexión, que no
      // se puede ofrecer cuando el servidor sí contestó que el PIN está mal.
      throw Object.assign(new Error('No se pudo llegar al servidor'), { esFalloDeRed: true });
    }

    if (res.status >= 500) {
      throw Object.assign(new Error('El servidor no está respondiendo bien'), { esFalloDeRed: true });
    }

    if (res.status === 429) {
      const cuerpo = await res.json().catch(() => null);
      throw new Error(cuerpo?.detail || 'Demasiados intentos. Esperá un momento.');
    }

    if (!res.ok) {
      const cuerpo = await res.json().catch(() => null);
      throw new Error(cuerpo?.detail || 'Usuario o PIN incorrectos');
    }

    const data = await res.json();
    localStorage.setItem('token', data.access_token);
    return data;
  },

  async registerUser(nombre: string, pin_acceso: string, rol_id: number) {
    const res = await fetch(`${API_URL}/auth/register`, {
      method: 'POST',
      headers: this.headers,
      body: JSON.stringify({ nombre, pin_acceso, rol_id, estado: true })
    });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw new Error('Error al crear usuario. Verifica que no exista.');
    return res.json();
  },

  async getUsuarios() {
    const res = await fetch(`${API_URL}/auth/users`, { headers: this.headers });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw new Error('Error obteniendo usuarios');
    return res.json();
  },

  async updateUsuario(id: number, data: any) {
    const res = await fetch(`${API_URL}/auth/users/${id}`, {
      method: 'PUT',
      headers: this.headers,
      body: JSON.stringify(data)
    });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw new Error('Error actualizando usuario');
    return res.json();
  },

  /** Cambio del PIN propio. Hace falta el actual: un equipo dejado abierto no
   *  alcanza para quedarse con la cuenta. */
  async cambiarMiPin(pin_actual: string, pin_nuevo: string) {
    const res = await fetch(`${API_URL}/auth/me/pin`, {
      method: 'PUT',
      headers: this.headers,
      body: JSON.stringify({ pin_actual, pin_nuevo })
    });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) {
      const cuerpo = await res.json().catch(() => null);
      throw new Error(detalleLegible(cuerpo?.detail, 'No se pudo cambiar el PIN'));
    }
  },

  /** Reinicio del PIN de otra cuenta, para el que se lo olvidó. Sólo admin. */
  async reiniciarPinUsuario(id: number, pin_nuevo: string) {
    const res = await fetch(`${API_URL}/auth/users/${id}/pin`, {
      method: 'PUT',
      headers: this.headers,
      body: JSON.stringify({ pin_nuevo })
    });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) {
      const cuerpo = await res.json().catch(() => null);
      throw new Error(detalleLegible(cuerpo?.detail, 'No se pudo reiniciar el PIN'));
    }
  },

  async deleteUsuario(id: number) {
    const res = await fetch(`${API_URL}/auth/users/${id}`, {
      method: 'DELETE',
      headers: this.headers
    });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw new Error('Error eliminando usuario');
    return;
  },

  async createMercadoPagoPreference(title: string, quantity: number, unit_price: number) {
    const res = await fetch(`${API_URL}/pagos/mercadopago/preference`, {
      method: 'POST',
      headers: this.headers,
      body: JSON.stringify({ title, quantity, unit_price })
    });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw new Error('Error creando preferencia MP');
    return res.json();
  },

  async checkMercadoPagoStatus(external_reference: string, totalEsperado: number) {
    // El total viaja para que el servidor compare cuánto se pagó realmente:
    // sin eso, una preferencia de $1 daría por cobrado un carrito entero.
    const res = await fetch(
      `${API_URL}/pagos/mercadopago/status/${encodeURIComponent(external_reference)}?total_esperado=${totalEsperado}`,
      { headers: this.headers }
    );
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw new Error('Error consultando estado MP');
    return res.json();
  },

  get headers() {
    const token = localStorage.getItem('token');
    return {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {})
    };
  },

  /**
   * Parsea la respuesta verificando que realmente sea JSON.
   *
   * Si falta la ruta en el proxy de vite.config.ts, Vite responde el index.html
   * con status 200 y `res.json()` explota con un error de sintaxis críptico.
   * Lo mismo si el backend está apagado o quedó corriendo una versión vieja sin
   * el router. Detectarlo acá permite dar un mensaje que dice qué hacer.
   */
  async parseJson(res: Response, contexto: string) {
    const tipo = res.headers.get('content-type') || '';
    if (!tipo.includes('application/json')) {
      throw new Error(
        `${contexto}: el servidor no devolvió JSON. Revisá que el backend esté corriendo en el puerto 8001 y reiniciá "npm run dev".`
      );
    }
    return res.json();
  },

  // --- Auditoría -----------------------------------------------------------
  // El backend tenía este router completo desde hacía rato y el frontend no lo
  // llamaba nunca: toda la trazabilidad de cambios de precio, de descuentos y
  // de permisos existía y no había forma de mirarla.

  async getAuditoria(filtros: {
    entidad?: string; usuario_id?: number; desde?: string; hasta?: string; limite?: number;
  } = {}) {
    const parametros = new URLSearchParams();
    for (const [clave, valor] of Object.entries(filtros)) {
      if (valor !== undefined && valor !== '' && valor !== null) parametros.set(clave, String(valor));
    }
    const res = await fetch(`${API_URL}/auditoria/?${parametros}`, { headers: this.headers });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw await this.errorDe(res, 'No se pudo leer el registro de auditoría');
    return this.parseJson(res, 'Auditoría');
  },

  // --- Respaldos -----------------------------------------------------------

  async getRespaldos() {
    const res = await fetch(`${API_URL}/respaldos/`, { headers: this.headers });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw await this.errorDe(res, 'No se pudieron listar los respaldos');
    return this.parseJson(res, 'Respaldos');
  },

  async crearRespaldo() {
    const res = await fetch(`${API_URL}/respaldos/`, { method: 'POST', headers: this.headers });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw await this.errorDe(res, 'No se pudo crear el respaldo');
    return this.parseJson(res, 'Respaldos');
  },

  /**
   * Baja una copia al equipo.
   *
   * Va por `fetch` y no por un enlace directo porque la descarga necesita la
   * cabecera de autorización: el endpoint es sólo para administradores, y un
   * `<a href>` no manda el token.
   */
  async descargarRespaldo(nombre: string) {
    const res = await fetch(`${API_URL}/respaldos/${encodeURIComponent(nombre)}`, {
      headers: this.headers,
    });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw await this.errorDe(res, 'No se pudo descargar el respaldo');

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const enlace = document.createElement('a');
    enlace.href = url;
    enlace.download = nombre;
    document.body.appendChild(enlace);
    enlace.click();
    enlace.remove();
    URL.revokeObjectURL(url);
  },

  // --- Productos: baja lógica ----------------------------------------------

  async darDeBajaProducto(id: number) {
    const res = await fetch(`${API_URL}/productos/${id}`, {
      method: 'DELETE', headers: this.headers,
    });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw await this.errorDe(res, 'No se pudo dar de baja el producto');
  },

  /** Extrae el detalle de error de FastAPI, con un texto de respaldo. */
  async errorDe(res: Response, respaldo: string) {
    const tipo = res.headers.get('content-type') || '';
    if (res.status === 404) {
      return new Error(`${respaldo}: el backend no conoce esta ruta (404). Reiniciá el servidor de Python para que cargue los routers nuevos.`);
    }
    if (!tipo.includes('application/json')) {
      return new Error(`${respaldo}: el servidor no devolvió JSON. ¿Está corriendo el backend en el puerto 8001?`);
    }
    const cuerpo = await res.json().catch(() => ({}));
    return new Error(cuerpo.detail || respaldo);
  },

  async getProductos() {
    const res = await fetch(`${API_URL}/productos/`, { headers: this.headers });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw new Error('Error obteniendo productos');
    return res.json();
  },

  /**
   * Catálogo completo para el POS.
   *
   * Va por su propio endpoint y no por `getProductos`, que devuelve una página
   * de 100: el POS reemplaza su catálogo local con lo que reciba, así que con
   * una página incompleta los productos que faltaban dejaban de poder venderse
   * y el lector sólo decía "producto no encontrado".
   */
  async getCatalogo() {
    const res = await fetch(`${API_URL}/productos/catalogo`, { headers: this.headers });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw new Error('Error obteniendo el catálogo');
    return res.json();
  },

  async createProducto(producto: {codigo_barras: string, nombre: string, precio_venta: number, costo: number, stock_actual: number, imagen_url?: string | null, categoria_id?: number | null, proveedor_id?: number | null, cantidad_pedido_habitual?: number | null}) {
    const res = await fetch(`${API_URL}/productos/`, {
      method: 'POST',
      headers: this.headers,
      body: JSON.stringify(producto)
    });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw new Error('Error creando producto');
    return res.json();
  },

  async updateProducto(id: number, producto: {codigo_barras?: string, nombre?: string, precio_venta?: number, costo?: number, stock_actual?: number, imagen_url?: string | null, categoria_id?: number | null, proveedor_id?: number | null, cantidad_pedido_habitual?: number | null}) {
    const res = await fetch(`${API_URL}/productos/${id}`, {
      method: 'PUT',
      headers: this.headers,
      body: JSON.stringify(producto)
    });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw new Error('Error actualizando producto');
    return res.json();
  },

  async getCajaEstado() {
    const res = await fetch(`${API_URL}/cajas/estado`, { headers: this.headers });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (res.status === 404) return null; // No open register
    if (!res.ok) throw new Error('Error verificando estado de caja');
    return res.json();
  },

  async abrirCaja(monto_inicial: number) {
    const res = await fetch(`${API_URL}/cajas/abrir`, {
      method: 'POST',
      headers: this.headers,
      body: JSON.stringify({ monto_inicial })
    });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw new Error('Error abriendo caja');
    return res.json();
  },

  async cerrarCaja(id: number, monto_final_declarado: number) {
    const res = await fetch(`${API_URL}/cajas/${id}/cerrar`, {
      method: 'PUT',
      headers: this.headers,
      body: JSON.stringify({ monto_final_declarado })
    });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw new Error('Error cerrando caja');
    return res.json();
  },

  async createVenta(venta: any) {
    const res = await fetch(`${API_URL}/ventas/`, {
      method: 'POST',
      headers: this.headers,
      body: JSON.stringify(venta)
    });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) {
      // El código importa al sincronizar: un 4xx es definitivo (el servidor
      // rechazó la venta y la va a rechazar siempre) y un 5xx o un corte de red
      // es transitorio. Sin distinguirlos, una venta rechazada se reintenta
      // eternamente y traba la cola.
      const cuerpo = await res.json().catch(() => null);
      const error = new Error(detalleLegible(cuerpo?.detail)) as Error & { status?: number };
      error.status = res.status;
      throw error;
    }
    return res.json();
  },

  async getKpi() {
    const res = await fetch(`${API_URL}/reportes/kpi`, { headers: this.headers });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw new Error('Error obteniendo KPI');
    return res.json();
  },

  async getTopProductos() {
    const res = await fetch(`${API_URL}/reportes/top_productos`, { headers: this.headers });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw new Error('Error obteniendo top productos');
    return res.json();
  },

  async getHistorialCajas() {
    const res = await fetch(`${API_URL}/reportes/cajas`, { headers: this.headers });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw new Error('Error obteniendo historial de cajas');
    return res.json();
  },

  async getVentasCaja(caja_id: number) {
    const res = await fetch(`${API_URL}/reportes/cajas/${caja_id}/ventas`, { headers: this.headers });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw new Error('Error obteniendo ventas de la caja');
    return res.json();
  },

  async getStockBajo(umbral: number = 5) {
    const res = await fetch(`${API_URL}/reportes/stock_bajo?umbral=${umbral}`, { headers: this.headers });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw new Error('Error obteniendo stock bajo');
    return res.json();
  },

  async getVentasPeriodo(desde: string, hasta: string) {
    const res = await fetch(`${API_URL}/reportes/ventas_periodo?desde=${desde}&hasta=${hasta}`, { headers: this.headers });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw new Error('Error obteniendo ventas del período');
    return res.json();
  },

  async getRentabilidad() {
    const res = await fetch(`${API_URL}/reportes/rentabilidad`, { headers: this.headers });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw new Error('Error obteniendo rentabilidad');
    return res.json();
  },

  async getVentasPorDia(dias: number = 14) {
    const res = await fetch(`${API_URL}/reportes/ventas_por_dia?dias=${dias}`, { headers: this.headers });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw new Error('Error obteniendo ventas por día');
    return res.json();
  },

  async getDescuentos(soloVigentes: boolean = false) {
    const res = await fetch(`${API_URL}/descuentos/?solo_vigentes=${soloVigentes}`, { headers: this.headers });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw await this.errorDe(res, 'Error obteniendo descuentos');
    return this.parseJson(res, 'Error obteniendo descuentos');
  },

  async createDescuento(descuento: any) {
    const res = await fetch(`${API_URL}/descuentos/`, {
      method: 'POST',
      headers: this.headers,
      body: JSON.stringify(descuento)
    });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Error creando descuento');
    return res.json();
  },

  async updateDescuento(id: number, descuento: any) {
    const res = await fetch(`${API_URL}/descuentos/${id}`, {
      method: 'PUT',
      headers: this.headers,
      body: JSON.stringify(descuento)
    });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Error actualizando descuento');
    return res.json();
  },

  /** Marca del comercio, sin necesidad de estar logueado. */
  async getMarca() {
    const res = await fetch(`${API_URL}/configuracion/marca`);
    if (!res.ok) throw await this.errorDe(res, 'Error obteniendo la marca');
    return this.parseJson(res, 'Error obteniendo la marca');
  },

  async getConfiguracion() {
    const res = await fetch(`${API_URL}/configuracion/`, { headers: this.headers });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw await this.errorDe(res, 'Error obteniendo configuración');
    return this.parseJson(res, 'Error obteniendo configuración');
  },

  async updateConfiguracion(valores: Record<string, any>) {
    const res = await fetch(`${API_URL}/configuracion/`, {
      method: 'PUT',
      headers: this.headers,
      body: JSON.stringify({ valores })
    });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw await this.errorDe(res, 'Error guardando configuración');
    return this.parseJson(res, 'Error guardando configuración');
  },

  async restaurarConfiguracion() {
    const res = await fetch(`${API_URL}/configuracion/restaurar`, {
      method: 'POST',
      headers: this.headers
    });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw await this.errorDe(res, 'Error restaurando configuración');
    return this.parseJson(res, 'Error restaurando configuración');
  },

  // --- Devoluciones y anulaciones -------------------------------------------

  /** Qué queda por devolver de una venta, ya descontado lo devuelto antes. */
  async getDevolvible(ventaId: number) {
    const res = await fetch(`${API_URL}/devoluciones/venta/${ventaId}/disponible`, { headers: this.headers });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw await this.errorDe(res, 'Error obteniendo los productos devolvibles');
    return this.parseJson(res, 'Error obteniendo los productos devolvibles');
  },

  async getDevoluciones(ventaId: number) {
    const res = await fetch(`${API_URL}/devoluciones/venta/${ventaId}`, { headers: this.headers });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw await this.errorDe(res, 'Error obteniendo las devoluciones');
    return this.parseJson(res, 'Error obteniendo las devoluciones');
  },

  /** Sin `detalles` se anula la venta entera. */
  async crearDevolucion(ventaId: number, datos: {
    motivo?: string,
    metodo_devolucion?: string,
    detalles?: { producto_id: number, cantidad: number }[],
  }) {
    const res = await fetch(`${API_URL}/devoluciones/venta/${ventaId}`, {
      method: 'POST',
      headers: this.headers,
      body: JSON.stringify({ metodo_devolucion: 'EFECTIVO', detalles: [], ...datos })
    });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw await this.errorDe(res, 'Error registrando la devolución');
    return this.parseJson(res, 'Error registrando la devolución');
  },

  // --- Movimientos de stock -------------------------------------------------

  /** INGRESO suma al stock; AJUSTE lo fija en la cantidad contada. */
  async registrarMovimientoStock(datos: {
    producto_id: number,
    cantidad: number,
    tipo_movimiento: 'INGRESO' | 'AJUSTE',
    motivo?: string,
  }) {
    const res = await fetch(`${API_URL}/stock/movimientos`, {
      method: 'POST',
      headers: this.headers,
      body: JSON.stringify(datos)
    });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw await this.errorDe(res, 'Error registrando el movimiento');
    return this.parseJson(res, 'Error registrando el movimiento');
  },

  async getMovimientosStock(
    productoId?: number,
    limite: number = 100,
    filtros: { tipo?: string, desde?: string, hasta?: string } = {}
  ) {
    const params = new URLSearchParams({ limite: String(limite) });
    if (productoId) params.set('producto_id', String(productoId));
    if (filtros.tipo) params.set('tipo', filtros.tipo);
    if (filtros.desde) params.set('desde', filtros.desde);
    if (filtros.hasta) params.set('hasta', filtros.hasta);

    const res = await fetch(`${API_URL}/stock/movimientos?${params}`, { headers: this.headers });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw await this.errorDe(res, 'Error obteniendo el historial de stock');
    return this.parseJson(res, 'Error obteniendo el historial de stock');
  },

  // --- Proveedores ----------------------------------------------------------

  async getProveedores(incluirInactivos: boolean = false) {
    const res = await fetch(`${API_URL}/proveedores/?incluir_inactivos=${incluirInactivos}`, { headers: this.headers });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw await this.errorDe(res, 'Error obteniendo proveedores');
    return this.parseJson(res, 'Error obteniendo proveedores');
  },

  async createProveedor(proveedor: any) {
    const res = await fetch(`${API_URL}/proveedores/`, {
      method: 'POST', headers: this.headers, body: JSON.stringify(proveedor)
    });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw await this.errorDe(res, 'Error creando el proveedor');
    return this.parseJson(res, 'Error creando el proveedor');
  },

  async updateProveedor(id: number, proveedor: any) {
    const res = await fetch(`${API_URL}/proveedores/${id}`, {
      method: 'PUT', headers: this.headers, body: JSON.stringify(proveedor)
    });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw await this.errorDe(res, 'Error actualizando el proveedor');
    return this.parseJson(res, 'Error actualizando el proveedor');
  },

  async deleteProveedor(id: number) {
    const res = await fetch(`${API_URL}/proveedores/${id}`, { method: 'DELETE', headers: this.headers });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw await this.errorDe(res, 'Error eliminando el proveedor');
    return;
  },

  // --- Pedidos de reposición ------------------------------------------------

  /** Lo que falta reponer, ya agrupado por proveedor. */
  async getReponer() {
    const res = await fetch(`${API_URL}/pedidos/reponer`, { headers: this.headers });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw await this.errorDe(res, 'Error calculando la reposición');
    return this.parseJson(res, 'Error calculando la reposición');
  },

  async getPedidos(estado?: string) {
    const filtro = estado ? `?estado=${estado}` : '';
    const res = await fetch(`${API_URL}/pedidos/${filtro}`, { headers: this.headers });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw await this.errorDe(res, 'Error obteniendo los pedidos');
    return this.parseJson(res, 'Error obteniendo los pedidos');
  },

  async createPedido(pedido: { proveedor_id: number, notas?: string, detalles: { producto_id: number, cantidad: number }[] }) {
    const res = await fetch(`${API_URL}/pedidos/`, {
      method: 'POST', headers: this.headers, body: JSON.stringify(pedido)
    });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw await this.errorDe(res, 'Error registrando el pedido');
    return this.parseJson(res, 'Error registrando el pedido');
  },

  /** Sin `detalles` se da por recibido todo lo pedido. */
  async recibirPedido(id: number, detalles: { producto_id: number, cantidad_recibida: number }[] = []) {
    const res = await fetch(`${API_URL}/pedidos/${id}/recibir`, {
      method: 'POST', headers: this.headers, body: JSON.stringify({ detalles })
    });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw await this.errorDe(res, 'Error recibiendo el pedido');
    return this.parseJson(res, 'Error recibiendo el pedido');
  },

  async cancelarPedido(id: number) {
    const res = await fetch(`${API_URL}/pedidos/${id}/cancelar`, { method: 'POST', headers: this.headers });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw await this.errorDe(res, 'Error cancelando el pedido');
    return this.parseJson(res, 'Error cancelando el pedido');
  },

  // --- Categorías -----------------------------------------------------------

  async getCategorias() {
    const res = await fetch(`${API_URL}/categorias/`, { headers: this.headers });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw await this.errorDe(res, 'Error obteniendo categorías');
    return this.parseJson(res, 'Error obteniendo categorías');
  },

  async createCategoria(nombre: string) {
    const res = await fetch(`${API_URL}/categorias/`, {
      method: 'POST',
      headers: this.headers,
      body: JSON.stringify({ nombre })
    });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw await this.errorDe(res, 'Error creando la categoría');
    return this.parseJson(res, 'Error creando la categoría');
  },

  async updateCategoria(id: number, nombre: string) {
    const res = await fetch(`${API_URL}/categorias/${id}`, {
      method: 'PUT',
      headers: this.headers,
      body: JSON.stringify({ nombre })
    });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw await this.errorDe(res, 'Error actualizando la categoría');
    return this.parseJson(res, 'Error actualizando la categoría');
  },

  async deleteCategoria(id: number) {
    const res = await fetch(`${API_URL}/categorias/${id}`, {
      method: 'DELETE',
      headers: this.headers
    });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw await this.errorDe(res, 'Error eliminando la categoría');
    return;
  },

  async deleteDescuento(id: number) {
    const res = await fetch(`${API_URL}/descuentos/${id}`, {
      method: 'DELETE',
      headers: this.headers
    });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw new Error('Error eliminando descuento');
    return;
  },
};
