/**
 * Acceso al POS cuando no hay forma de llegar al servidor.
 *
 * El POS vende sin red: la cola de ventas y el catálogo viven en el equipo.
 * Pero para *entrar* hacía falta el servidor, así que un comercio que abría a
 * la mañana con el internet caído y sin sesión guardada no podía vender. El
 * escenario que el producto promete cubrir era justo el que no cubría.
 *
 * Cómo funciona: cada vez que alguien entra bien contra el servidor se guarda
 * en el equipo el hash de su PIN. Si después no hay servidor, se valida contra
 * ese hash.
 *
 * ES UN COMPROMISO CONSCIENTE, y conviene tenerlo escrito:
 *
 *  - El hash queda en el dispositivo. Quien se lleve el celular puede intentar
 *    romperlo sin límite de intentos del servidor. Por eso se usa PBKDF2 con
 *    muchas iteraciones y sal por usuario, y no un hash pelado.
 *  - La sesión offline **no da permisos de administración**: sirve para vender
 *    y nada más. El backoffice sigue exigiendo servidor, que es donde el rol se
 *    lee de la base en cada request.
 *  - Vale por tiempo limitado desde el último acceso real. Un dispositivo que
 *    hace un mes que no habla con el servidor no debería seguir abriendo con
 *    credenciales que quizás ya se dieron de baja.
 */

/** Cuánto vale una credencial guardada desde el último acceso contra el servidor. */
export const DIAS_DE_VALIDEZ = 30;

/** Costo del derivado. Alto a propósito: el hash vive en un equipo que se puede perder. */
const ITERACIONES = 210_000;

const CLAVE = 'applify_credenciales_locales';

export interface CredencialLocal {
  usuario: string;
  /** Hash del PIN en hexadecimal. */
  hash: string;
  /** Sal en hexadecimal, distinta por usuario. */
  sal: string;
  /** Rol que tenía la última vez. Sólo para pintar la pantalla, no para dar permisos. */
  rol_id: number;
  /** Último acceso verificado contra el servidor, en ISO. */
  verificado: string;
}

function aHex(datos: ArrayBuffer): string {
  return [...new Uint8Array(datos)].map(b => b.toString(16).padStart(2, '0')).join('');
}

async function derivar(pin: string, salHex: string): Promise<string> {
  const sal = Uint8Array.from(
    salHex.match(/.{2}/g)?.map(b => parseInt(b, 16)) ?? [],
  );
  const material = await crypto.subtle.importKey(
    'raw', new TextEncoder().encode(pin), 'PBKDF2', false, ['deriveBits'],
  );
  const bits = await crypto.subtle.deriveBits(
    { name: 'PBKDF2', salt: sal, iterations: ITERACIONES, hash: 'SHA-256' },
    material,
    256,
  );
  return aHex(bits);
}

function leerTodas(): CredencialLocal[] {
  try {
    const bruto = localStorage.getItem(CLAVE);
    return bruto ? (JSON.parse(bruto) as CredencialLocal[]) : [];
  } catch {
    return [];
  }
}

function guardarTodas(credenciales: CredencialLocal[]) {
  try {
    localStorage.setItem(CLAVE, JSON.stringify(credenciales));
  } catch {
    /* almacenamiento lleno o bloqueado: se sigue sin acceso offline */
  }
}

/**
 * Deja registrado que este usuario entró bien contra el servidor.
 *
 * Se llama después de cada login exitoso, no sólo el primero: así se renueva
 * la fecha de verificación y se actualiza el hash si el PIN cambió.
 */
export async function recordarAcceso(usuario: string, pin: string, rolId: number) {
  const sal = aHex(crypto.getRandomValues(new Uint8Array(16)).buffer);
  const nueva: CredencialLocal = {
    usuario,
    sal,
    hash: await derivar(pin, sal),
    rol_id: rolId,
    verificado: new Date().toISOString(),
  };

  const resto = leerTodas().filter(c => c.usuario !== usuario);
  guardarTodas([...resto, nueva]);
}

/** Saca a un usuario del acceso offline. Se usa al cerrar sesión a propósito. */
export function olvidarAcceso(usuario: string) {
  guardarTodas(leerTodas().filter(c => c.usuario !== usuario));
}

export type ResultadoOffline =
  | { ok: true; credencial: CredencialLocal }
  | { ok: false; motivo: 'sin_credencial' | 'pin_incorrecto' | 'vencida' };

/**
 * Valida usuario y PIN contra lo guardado en el equipo.
 *
 * Sólo tiene sentido llamarla cuando el servidor no responde: mientras haya
 * servidor, manda el servidor, que es el único que sabe si la cuenta sigue
 * activa y con qué rol.
 */
export async function validarOffline(usuario: string, pin: string): Promise<ResultadoOffline> {
  const credencial = leerTodas().find(c => c.usuario === usuario);
  if (!credencial) return { ok: false, motivo: 'sin_credencial' };

  const dias = (Date.now() - new Date(credencial.verificado).getTime()) / 86_400_000;
  if (!Number.isFinite(dias) || dias > DIAS_DE_VALIDEZ) {
    return { ok: false, motivo: 'vencida' };
  }

  const calculado = await derivar(pin, credencial.sal);

  // Comparación de tiempo constante. Es casi teórico acá —el atacante ya tiene
  // el hash en la mano si tiene el equipo— pero no cuesta nada.
  if (!sonIguales(calculado, credencial.hash)) {
    return { ok: false, motivo: 'pin_incorrecto' };
  }

  return { ok: true, credencial };
}

function sonIguales(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diferencia = 0;
  for (let i = 0; i < a.length; i++) diferencia |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diferencia === 0;
}

/** ¿Hay alguna credencial guardada? Sirve para decidir si ofrecer el acceso offline. */
export function hayCredencialesGuardadas(): boolean {
  return leerTodas().length > 0;
}
