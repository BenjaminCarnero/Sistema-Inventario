import { useEffect, useState } from 'react';

export type CameraStatus = 'checking' | 'available' | 'unavailable';

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
        if (!cancelado) setStatus('unavailable');
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
