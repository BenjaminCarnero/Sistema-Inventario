/**
 * Levanta el servidor de desarrollo.
 *
 *     node scripts/servidor.mjs            → HTTP, para trabajar en esta PC
 *     node scripts/servidor.mjs --https    → HTTPS, para el celular con cámara
 *
 * Se arranca Vite desde acá en lugar de con una variable de entorno adelante
 * del comando porque `VAR=valor comando` no funciona en PowerShell ni en cmd,
 * que es donde esto corre casi siempre.
 *
 * Se puede ejecutar desde cualquier carpeta: la raíz del proyecto se resuelve
 * a partir de la ubicación de este archivo y no del directorio actual.
 */
import { fileURLToPath } from 'node:url'

const raiz = fileURLToPath(new URL('..', import.meta.url))

// Hay que pararse en la carpeta del frontend antes de arrancar. Tailwind
// resuelve sus rutas de `content` contra el directorio actual y no contra la
// raíz que se le pasa a Vite: lanzando el script desde otra carpeta no
// encuentra ningún archivo y la página sale sin estilos.
process.chdir(raiz)

if (process.argv.includes('--https')) process.env.APPLIFY_HTTPS = '1'

const { createServer } = await import('vite')

const servidor = await createServer({ root: raiz, configFile: `${raiz}vite.config.ts` })
await servidor.listen()

servidor.printUrls()

if (servidor.config.server.https) {
  console.log(
    '\n  El certificado está firmado por vos mismo, así que la primera vez el\n' +
    '  celular va a avisar que el sitio no es de confianza. Hay que entrar\n' +
    '  igual una vez; después queda aceptado y el escáner funciona.\n'
  )
}
