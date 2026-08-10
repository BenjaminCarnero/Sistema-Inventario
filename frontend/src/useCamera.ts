import { useEffect, useState } from 'react';

/** `inseguro`: hay cámara, pero el navegador no la presta fuera de HTTPS. */
export type CameraStatus = 'checking' | 'available' | 'unavailable' | 'inseguro';

/**
 * Detecta si el dispositivo tiene cámara SIN disparar el diálogo de permisos.
 *
 * `Html5Qrcode.getCameras()` llama internamente a `getUserMedia()`, así que pide
 * permiso incluso en equipos que no tienen cámara (el caso típico de una PC de
 * escritorio con lector de barras USB). `enumerateDevices()` no pide permiso:
 * sin autorización devuelve los dispositivos con `label` vacío, pero el `kind`
 * sigue siendo confiable para saber si existe una cámara.
 */
export function useCameraAvailability(): CameraStatus {
  const [status, setStatus] = useState<CameraStatus>('checking');

  useEffect(() => {
    let cancelado = false;

    const detectar = async () => {
      if (!navigator.mediaDevices?.enumerateDevices) {
        // Fuera de un contexto seguro el navegador no expone `mediaDevices`.
        // Pasa al entrar por la IP de la red desde el celular: el equipo sí
        // tiene cámara, así que decir "no hay cámara" confundiría.
        if (!cancelado) setStatus(window.isSecureContext ? 'unavailable' : 'inseguro');
        return;
      }
      try {
        const dispositivos = await navigator.mediaDevices.enumerateDevices();
        const tieneCamara = dispositivos.some(d => d.kind === 'videoinput');
        if (!cancelado) setStatus(tieneCamara ? 'available' : 'unavailable');
      } catch {
        if (!cancelado) setStatus('unavailable');
      }
    };

    detectar();

    // Si el usuario enchufa o desenchufa una webcam, revisamos de nuevo.
    navigator.mediaDevices?.addEventListener?.('devicechange', detectar);
    return () => {
      cancelado = true;
      navigator.mediaDevices?.removeEventListener?.('devicechange', detectar);
    };
  }, []);

  return status;
}
