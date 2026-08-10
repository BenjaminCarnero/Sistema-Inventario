import {
  Html5QrcodeScanner,
  Html5QrcodeScannerState,
  Html5QrcodeSupportedFormats,
} from 'html5-qrcode';

/**
 * Resolución que se le pide a la cámara.
 *
 * Un EAN-13 tiene barras finas: a 640x480, que es lo que suele elegir el
 * navegador por su cuenta, cada barra queda en uno o dos píxeles y el
 * decodificador falla salvo que uno acerque mucho el producto. Pidiendo Full HD
 * el código entra con detalle suficiente desde más lejos.
 *
 * Va como `ideal` y no como `exact` a propósito: si la cámara no llega a esa
 * resolución, el navegador entrega la más parecida en lugar de fallar. En una
 * webcam vieja se sigue viendo, sólo que más chico.
 */
export const RESOLUCION_IDEAL: MediaTrackConstraints = {
  width: { ideal: 1920 },
  height: { ideal: 1080 },
};

/** Configuración común del escáner del POS y del alta de productos. */
export const CONFIG_ESCANER = {
  fps: 15,
  qrbox: { width: 250, height: 100 },
  showTorchButtonIfSupported: true,
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
 * Sube la resolución en cuanto la cámara arranca. Devuelve una función para
 * cortar la espera al desmontar el componente.
 *
 * La resolución se aplica sobre el stream ya andando y no en la configuración
 * inicial. Puesta en `videoConstraints`, la librería descarta la cámara elegida
 * en el desplegable y usa sólo esas restricciones: en un celular con cámara
 * frontal y trasera se perdería el poder cambiar de una a otra. Así, lo peor
 * que puede pasar es que la cámara ignore el pedido y todo siga como antes.
 *
 * Hay que esperar a que esté escaneando porque entre `render()` y el primer
 * cuadro está el permiso de cámara, que puede tardar lo que tarde el usuario en
 * aceptarlo.
 */
export function subirResolucion(scanner: Html5QrcodeScanner): () => void {
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
    scanner.applyVideoConstraints(RESOLUCION_IDEAL).catch(error => {
      // Que la cámara no acepte la resolución no es motivo para cortar el
      // escaneo: sigue funcionando con la que haya elegido el navegador.
      console.warn('La cámara no aceptó la resolución pedida:', error);
    });
  }, CADA_MS);

  return () => {
    cancelado = true;
    window.clearInterval(timer);
  };
}
