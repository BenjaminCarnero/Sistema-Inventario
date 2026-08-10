import {
  Html5QrcodeScanner,
  Html5QrcodeScannerState,
  Html5QrcodeSupportedFormats,
} from 'html5-qrcode';

/**
 * Recuadro de lectura.
 *
 * Se calcula sobre el tamaño real del visor en lugar de dejarlo fijo: un
 * cuadro chico obliga a centrar el código con precisión, y con una cámara
 * mediocre eso es justo lo que no se puede hacer. Un código de barras es ancho
 * y bajo, así que el recuadro lo acompaña en vez de ser cuadrado.
 */
function recuadroDeLectura(anchoVisor: number, altoVisor: number) {
  const ancho = Math.floor(Math.min(anchoVisor * 0.92, 420));
  const alto = Math.floor(Math.min(ancho * 0.45, altoVisor * 0.7));
  return { width: ancho, height: alto };
}

/** Configuración común del escáner del POS y del alta de productos. */
export const CONFIG_ESCANER = {
  fps: 15,
  qrbox: recuadroDeLectura,
  showTorchButtonIfSupported: true,
  // Con una cámara floja, acercar la imagen es lo que más ayuda: el código
  // ocupa más píxeles sin que haya que arrimar el producto al lente, que es
  // donde muchas cámaras pierden el foco.
  showZoomSliderIfSupported: true,
  // Usa el decodificador de códigos del propio navegador cuando existe
  // (Android). Aguanta mucho mejor la imagen borrosa o con poca luz que el
  // decodificador en JavaScript. Donde no está, la librería sigue usando el de
  // siempre como respaldo, así que no se pierde nada.
  useBarCodeDetectorIfSupported: true,
  formatsToSupport: [
    Html5QrcodeSupportedFormats.EAN_13,
    Html5QrcodeSupportedFormats.EAN_8,
    Html5QrcodeSupportedFormats.UPC_A,
    Html5QrcodeSupportedFormats.UPC_E,
    Html5QrcodeSupportedFormats.CODE_128,
    Html5QrcodeSupportedFormats.QR_CODE,
  ],
};

/**
 * Resolución que se le pide a la cámara.
 *
 * Un EAN-13 tiene barras finas: a 640x480, que es lo que suele elegir el
 * navegador por su cuenta, cada barra queda en uno o dos píxeles. Va como
 * `ideal` y no como `exact` para que una cámara que no llegue entregue lo más
 * parecido en lugar de fallar.
 *
 * Ojo que subir la resolución no arregla una cámara mala: una imagen borrosa
 * con más píxeles sigue siendo borrosa. Lo que de verdad cambia las cosas es
 * el enfoque continuo de acá abajo.
 */
const RESOLUCION_IDEAL = { width: { ideal: 1920 }, height: { ideal: 1080 } };

/** Lo que se le pide a la cámara según lo que diga que sabe hacer. */
export function ajustesParaLaCamara(capacidades: MediaTrackCapabilities | undefined) {
  const ajustes: Record<string, unknown> = { ...RESOLUCION_IDEAL };
  const avanzados: Record<string, unknown>[] = [];

  // El motivo número uno por el que un código no engancha es que la imagen
  // está fuera de foco. Muchas cámaras enfocan una vez al abrirse y se quedan
  // así; pidiendo enfoque continuo vuelven a enfocar cuando acercás el
  // producto. `focusMode` no está en los tipos del navegador todavía.
  const modosDeFoco = (capacidades as Record<string, unknown> | undefined)?.focusMode;
  if (Array.isArray(modosDeFoco) && modosDeFoco.includes('continuous')) {
    avanzados.push({ focusMode: 'continuous' });
  }

  if (avanzados.length > 0) ajustes.advanced = avanzados;
  return ajustes as MediaTrackConstraints;
}

/**
 * Mejora la imagen en cuanto la cámara arranca. Devuelve una función para
 * cortar la espera al desmontar el componente.
 *
 * Se aplica sobre el stream ya andando y no en la configuración inicial:
 * puesto en `videoConstraints`, html5-qrcode descarta la cámara elegida en el
 * desplegable y usa sólo esas restricciones, con lo cual en un celular se
 * perdería el poder cambiar de la trasera a la frontal. Así, lo peor que puede
 * pasar es que la cámara ignore el pedido y todo siga como estaba.
 *
 * Hay que esperar a que esté escaneando porque entre `render()` y el primer
 * cuadro está el permiso de cámara, que tarda lo que tarde la persona en
 * aceptarlo.
 */
export function mejorarImagen(scanner: Html5QrcodeScanner): () => void {
  const CADA_MS = 150;
  const ESPERA_MAXIMA_MS = 30_000; // el permiso lo da una persona, no un script

  let cancelado = false;
  let esperado = 0;

  const timer = window.setInterval(() => {
    if (cancelado) return;

    esperado += CADA_MS;
    if (esperado > ESPERA_MAXIMA_MS) {
      window.clearInterval(timer);
      return;
    }

    let estado: Html5QrcodeScannerState;
    try {
      estado = scanner.getState();
    } catch {
      return; // todavía no hay cámara montada
    }
    if (estado !== Html5QrcodeScannerState.SCANNING) return;

    window.clearInterval(timer);

    let capacidades: MediaTrackCapabilities | undefined;
    try {
      capacidades = scanner.getRunningTrackCapabilities();
    } catch {
      capacidades = undefined; // hay cámaras que no las informan
    }

    scanner.applyVideoConstraints(ajustesParaLaCamara(capacidades)).catch(error => {
      // Que la cámara no acepte algo no es motivo para cortar el escaneo:
      // sigue funcionando con lo que haya elegido el navegador.
      console.warn('La cámara no aceptó los ajustes pedidos:', error);
    });
  }, CADA_MS);

  return () => {
    cancelado = true;
    window.clearInterval(timer);
  };
}
