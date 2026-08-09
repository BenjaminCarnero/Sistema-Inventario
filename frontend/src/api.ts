const API_URL = '';

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

    const res = await fetch(`${API_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: formData
    });
    if (!res.ok) throw new Error('Credenciales incorrectas');
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

  async createProducto(producto: {codigo_barras: string, nombre: string, precio_venta: number, costo: number, stock_actual: number, imagen_url?: string | null}) {
    const res = await fetch(`${API_URL}/productos/`, {
      method: 'POST',
      headers: this.headers,
      body: JSON.stringify(producto)
    });
    if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
    if (!res.ok) throw new Error('Error creando producto');
    return res.json();
  },

  async updateProducto(id: number, producto: {codigo_barras?: string, nombre?: string, precio_venta?: number, costo?: number, stock_actual?: number, imagen_url?: string | null}) {
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
    if (!res.ok) throw new Error('Error sincronizando venta');
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
