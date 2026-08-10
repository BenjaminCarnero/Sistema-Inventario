/**
 * Levanta el servidor por HTTPS, para poder usar el escáner desde el celular.
 *
 * Los navegadores sólo prestan la cámara en `localhost` o con HTTPS, así que
 * entrando por la IP de la red el escáner queda inutilizable. Con el
 * certificado propio el sitio pasa a contar como seguro.
 *
 * Se arranca Vite desde acá y no con una variable de entorno adelante del
 * comando porque `VAR=valor comando` no funciona en PowerShell ni en cmd, que
 * es donde corre esto la mayor parte del tiempo.
 */
process.env.APPLIFY_HTTPS = '1'

const { createServer } = await import('vite')

const servidor = await createServer()
await servidor.listen()

servidor.printUrls()

if (servidor.config.server.https) {
  console.log(
    '\n  El certificado está firmado por vos mismo, así que la primera vez el\n' +
    '  celular va a avisar que el sitio no es de confianza. Hay que entrar\n' +
    '  igual una vez; después queda aceptado y el escáner funciona.\n'
  )
}
