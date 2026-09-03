# Qué falta para salir a producción

> **Estado: 2 de septiembre de 2026.** Este documento es la lista de trabajo, no el análisis.
> El *por qué* de cada punto y la evidencia están en `ANALISIS-PRE-VENTA.md`; acá está el *qué* y
> el *en qué orden*. Todo lo que se afirma acá se verificó contra el código el 02/09/2026.
>
> **Punto de partida:** la parte de código está bien. 295 funciones de test en el backend (334 casos en la última corrida), los 6 bloqueantes de
> seguridad y contabilidad cerrados, índices puestos, login offline andando, auditoría y respaldos
> con pantalla. **Lo que falta no es programar el sistema: es poder entregarlo, actualizarlo y
> sostenerlo.**

## Cómo leer esto

| Marca | Significa |
|---|---|
| 🔴 **BLOQUEA** | Sin esto no se instala en un comercio real. Ni siquiera gratis |
| 🟡 **NECESARIO** | Se puede pilotear sin esto, pero no cobrar |
| 🟢 **PUEDE ESPERAR** | Deuda conocida y acotada. No frena nada hoy |

---

## 0 · Antes que nada — 1 día

- [x] 🔴 **Mergear `arreglos-pre-venta` a `main`.** Hecho el 02/09/2026: fast-forward limpio, sin
      conflictos, pusheado a `origin/main`.
- [x] 🔴 Correr la suite completa en `main` ya mergeado — verde en las dos configuraciones, con y sin
      `frontend/dist`, más el ciclo de migraciones `up/down/up`. Se repitió después de cada tanda de
      cambios de esta sesión y siguió verde.
- [ ] 🔴 **Decidir el alcance fiscal** (ver §10). Sigue sin decidirse. No se puede escribir una
      propuesta comercial sin esta decisión, y condiciona el precio y el segmento.

---

## 1 · Que se pueda instalar 🔴 — 2 semanas

Hoy no existe `Dockerfile`, ni `docker-compose`, ni servicio de Windows, ni instalador, ni script de
puesta en marcha. Instalar es: clonar el repo, crear un venv, correr alembic, levantar uvicorn a mano
y `pnpm dev` en otra consola. **Eso lo puede hacer quien escribió el código. No lo puede hacer el
dueño de una verdulería, y no se puede repetir en veinte locales.**

- [ ] 🔴 Un solo ejecutable o instalador (Inno Setup o NSIS, ambos gratis) que deje: Python
      embebido o venv armado, la base migrada, el `.env` generado y el frontend ya compilado.
      **Borrador escrito y parcialmente probado en `installer/`** (`setup.iss` + los tres scripts de
      `installer/scripts/`): `generar-env.ps1` corrió de verdad y el `.env` que produce pasa la
      validación estricta de `config.py`; encontró y corrigió dos bugs reales de compatibilidad con
      Windows PowerShell 5.1 al probarlo. **Falta lo que no se puede hacer sin instalar software de
      terceros ni tocar el sistema**: preparar `vendor/` (Python embebido + NSSM), compilar con
      `iscc` y probar el instalador entero en una VM limpia. Ver `installer/README.md`.
- [ ] 🔴 **Servicio de Windows** que levante la aplicación al prender la máquina y la reinicie si se
      cae (NSSM sirve). Un POS que hay que arrancar a mano se apaga el día que el dueño reinicia.
      **Borrador en `installer/scripts/instalar-servicio.ps1`**, con el `AppDirectory` puesto a
      propósito en `backend/` (si no, la base y los logs se crean vacíos en el lugar equivocado la
      primera vez que arranca). Sin NSSM instalado en esta máquina, no se probó instalando un
      servicio real — sólo se verificó que frena correctamente sin permisos de administrador.
- [x] 🔴 Un solo puerto y un solo proceso: FastAPI ya sirve el `dist` (`FRONTEND_DIST` en el
      `.env`, catch-all en `main.py:231`), y `installer/setup.iss` empaqueta `frontend/dist` y nunca
      levanta Vite — usa este mismo camino.
- [x] 🔴 Primer arranque asistido — **crear el administrador inicial y el nombre del comercio, hecho
      y verificado en el navegador** (`GET /auth/estado-inicial` + pantalla en `App.tsx`, en vez de
      `seed_admin.py` a mano). La **zona horaria** la pide `installer/scripts/generar-env.ps1` al
      instalar, porque es una variable de entorno del proceso y no algo que se pueda cambiar desde
      una pantalla web sin reiniciar el servicio.
- [ ] 🟡 Desinstalación limpia que **no borre la base ni los respaldos**. Diseñado en `setup.iss`
      (la base, `.env`, `logs/` y `respaldos/` nunca se declaran en `[Files]`, así que el
      desinstalador de Inno Setup no los conoce y no los borra) — sin compilar el instalador todavía
      no hay una desinstalación real que probar.
- [ ] 🟢 Firma de código (~USD 100-400/año). Sin esto Windows muestra el aviso de SmartScreen. Se
      puede vivir con eso al principio; a los diez clientes ya no.

## 2 · Que se pueda actualizar 🔴 — 3 días

Esto es lo más importante de todo el documento y lo más fácil de postergar.

**Hoy no hay ningún mecanismo para llevar un arreglo hasta la máquina del local 7.** Si mañana
aparece un bug en el arqueo, la única forma es ir o pedir escritorio remoto, local por local.

- [x] 🔴 Comando de actualización que baja la versión nueva, **hace un respaldo antes**, corre
      `alembic upgrade head` y reinicia el servicio — **`installer/scripts/actualizar.ps1`, probado
      de punta a punta dos veces** (camino feliz y camino de falla) en una instalación aislada con
      datos reales. `.github/workflows/release.yml` es el otro lado: arma el `.zip` que este script
      baja de GitHub Releases cuando se publica un tag `vX.Y.Z`. Detalle completo en
      `installer/README.md`. Falta probarlo bajando un release real (todavía no se publicó ninguno) y
      con un servicio NSSM real en vez de `-OmitirServicio`.
- [x] 🔴 Vuelta atrás: si la migración falla, restaurar el respaldo y volver a la versión anterior —
      **integrada en el mismo `actualizar.ps1` y probada de verdad**: se le dio una migración rota a
      propósito, y solo revirtió código, `VERSION` y base de datos (incluidos los `-wal`/`-shm`) al
      estado exacto de antes de intentar la actualización. `restaurar_respaldo.py` sigue existiendo
      aparte para la restauración manual e interactiva (§5).
- [x] 🔴 Versión visible en la interfaz — **hecho y verificado en el navegador**. Un archivo `VERSION`
      en la raíz, expuesto en `GET /health` y mostrado al pie de Configuración › Parámetros del
      sistema.
- [x] 🟡 Que el sistema avise cuándo hay versión nueva — **hecho y verificado**. `GET
      /actualizaciones/disponible` compara `VERSION` contra el último release de GitHub (falla
      abierto: si GitHub no contesta, no avisa nada, nunca bloquea); el panel de Configuración
      muestra un banner cuando corresponde.

## 3 · El mostrador: impresora y lector 🔴 — 1 semana

- [x] 🔴 **Impresora térmica ESC/POS — hecha para el ticket del POS (`App.tsx`) y verificada de
      punta a punta con una impresora simulada.** `backend/app/ticket_escpos.py` arma los comandos
      crudos (corte y apertura de cajón incluidos) y `backend/app/impresora.py` los manda por red al
      puerto 9100 (el "raw"/JetDirect que trae casi toda térmica con Ethernet o WiFi) — no por USB
      todavía, ver abajo. Se probó real: un socket TCP local haciendo de impresora, una venta hecha en
      el navegador de punta a punta, "Imprimir" apretado de verdad, y los bytes recibidos —484 de
      ellos— verificados uno por uno (arrancan con reset, tienen el corte parcial y terminan en la
      apertura del cajón). En el camino se encontraron y corrigieron dos bugs reales: `/impresion` y
      `/actualizaciones` faltaban en el proxy de desarrollo de Vite (mismo error histórico que ya
      había pasado con `/auditoria` y `/respaldos`), y sin eso "Imprimir" caía en `window.print()`
      *silencioso*, que en un navegador sin operador puede quedarse esperando un diálogo que nunca
      llega. **Falta USB local** (necesitaría `pywin32`, sin impresora real no se puede probar) y
      reemplazar los otros dos `window.print()` (`Admin.tsx:1374` reimpresión, `Admin.tsx:3212`
      remito a proveedor) — quedaron con el diálogo del navegador.
- [x] 🔴 Ticket con el formato real del comercio — **ya estaba resuelto en el HTML y ahora también en
      el ESC/POS**: nombre, dirección, CUIT/teléfono si están cargados, detalle con cantidad y
      precio, descuento aplicado, desglose de IVA, total, forma de pago (recibido/vuelto en efectivo,
      "Abonado con X" en el resto) y número de operación.
- [ ] 🟡 Reimpresión del último ticket. Se pide el primer día de uso, siempre.
- [ ] 🟢 Comprar una impresora propia (~$70.000 a $80.000, una sola vez) para desarrollar y para las
      demos.

**Lector de código de barras:** el escáner por cámara ya está (`escaner.ts` con `html5-qrcode`), pero
en el mostrador se usa un lector USB tipo *wedge*, que escribe en el campo como si fuera un teclado.
Conviene probar explícitamente que el foco del POS lo acepte sin configuración.

## 4 · La red del local 🔴 — 2 días

Esto no está en ninguna lista previa y se descubre el día de la instalación.

**El escáner por cámara necesita contexto seguro.** `useCamera.ts:26` ya lo contempla y devuelve
`'inseguro'`, pero el problema es de despliegue: si el servidor corre en la PC del mostrador y el
celular entra por `http://192.168.0.x`, **el navegador no da acceso a la cámara**. En desarrollo se
resuelve con `pnpm dev:celular` y un certificado autofirmado; en un comercio, un certificado
autofirmado es una pantalla roja de advertencia que el cajero va a aprender a ignorar.

- [ ] 🔴 Definir cómo se sirve HTTPS en la red del local (una CA local instalada en los equipos con
      `mkcert`, o un nombre y certificado propios). **O** documentar que en celular se usa lector USB
      y no cámara.
- [ ] 🔴 Documentar la configuración de red: IP fija en la PC servidor, puerto abierto en el firewall
      de Windows, y qué hacer cuando el router reparte otra IP.
- [x] 🟡 Pantalla de diagnóstico — **hecho y verificado en el navegador**. Un link discreto en el
      login ("¿No podés entrar? Diagnóstico de conexión", `components/DiagnosticoRed.tsx`) muestra la
      dirección a la que está hablando el equipo, si el servidor contesta y en cuánto, la versión, y
      una lista de qué revisar si no llega. Probados los dos estados reales: servidor arriba y
      servidor apagado.

## 5 · Respaldos que alguien probó restaurar 🔴 — 2 días

El sistema hace respaldos automáticos al cerrar caja y tiene pantalla propia. Bien. Pero:

- [x] 🔴 **Probar una restauración completa, de punta a punta.** Hecho el 02/09/2026 en una carpeta
      aislada (backend copiado aparte, migrado desde cero — lo más parecido a una máquina limpia sin
      levantar una VM): servidor real arriba, alta del primer admin, un producto, una venta de
      verdad (con sus movimientos de stock), respaldo por el mismo endpoint que usa el botón de
      Configuración, base "rota" a mano, `restaurar_respaldo.py` corrido de punta a punta con la
      confirmación real. Verificado con el archivo restaurado leído directo (no confiando en la
      salida del script): usuario, producto con el stock ya descontado y la venta, los tres intactos.
      Los `-wal`/`-shm` de la base vieja se borraron solos, como corresponde, y quedó una copia
      `.reemplazada_<fecha>` de la base rota antes de pisarla. El backend volvió a arrancar sobre la
      base restaurada y el login siguió andando. Sigue pendiente probarlo en una VM de Windows limpia
      de verdad — esto prueba que el mecanismo funciona, no reemplaza esa prueba antes de vender.
- [ ] 🔴 Que el instalador configure `RESPALDO_EXTERNO` apuntando a OneDrive, Drive o un pendrive.
      Hoy depende de que el dueño edite el `.env`, o sea que **no va a pasar nunca** y las copias van
      a quedar en el mismo disco que se puede romper.
- [ ] 🟡 Aviso visible cuando hace más de X días que no se hace un respaldo externo.
- [ ] 🟢 Cifrado de los respaldos (M-09). Sigue abierto a propósito: hay que decidir dónde vive la
      frase de paso, y perderla es peor que el problema que resuelve.

## 6 · Configuración de producción — checklist por instalación 🔴

`config.py` **aborta el arranque** si esto está mal, que es lo correcto. Que el instalador lo deje
resuelto, no el manual.

- [ ] `ENTORNO=produccion` — exige `SECRET_KEY`, prohíbe CORS `*`, oculta `/docs`, activa HSTS
- [ ] `SECRET_KEY` generada **única por instalación** (nunca la misma en dos locales)
- [ ] `CORS_ORIGINS` con la dirección real, nunca `*`
- [ ] `ZONA_HORARIA=America/Argentina/Buenos_Aires` — sin esto el arqueo corta el día donde no es
- [ ] `FRONTEND_URL` con la dirección pública real: apuntando a `localhost`, el que paga por QR desde
      su celular termina en una página que sólo existe en la máquina de la caja
- [ ] `MERCADOPAGO_ACCESS_TOKEN` productivo (`APP_USR-`), no el de pruebas (`TEST-`)
- [ ] `RESPALDO_EXTERNO` apuntando a una carpeta que se sincroniza sola
- [ ] `PROXIES_CONFIABLES=1` **sólo** si hay un reverse proxy adelante
- [ ] `FRONTEND_DIST` apuntando al `dist` compilado

## 7 · Operación y soporte 🟡 — 1 semana

No hay monitoreo, ni alertas, ni procedimiento de qué hacer cuando llama un local. Los logs rotan a
disco (bien) pero nadie los mira desde afuera. **Con cinco clientes, esto es el trabajo de todos los
días si no se resuelve antes.**

- [ ] 🟡 Un canal de soporte que exista de verdad (WhatsApp alcanza) y un horario declarado
- [ ] 🟡 Forma de traerte los logs de un local sin pedirle al dueño que busque carpetas
- [ ] 🟡 Aviso cuando un local deja de reportar (indica servicio caído, no local cerrado)
- [ ] 🟡 Manual del comerciante de una página: cómo abrir caja, vender, cerrar, y qué hacer si no
      anda internet
- [ ] 🟢 Rotación de `SECRET_KEY` documentada (cierra todas las sesiones: hacerlo fuera de horario)

## 8 · Legal y comercial 🟡 — antes de la primera venta

Nada de esto existe hoy y todo es barato de resolver.

- [ ] 🟡 Archivo `LICENSE` en el repositorio
- [ ] 🟡 Contrato de licencia: qué incluye, qué no, y **límite de responsabilidad si se pierde la
      base**
- [ ] 🟡 Política de datos: los datos son del comercio, dónde viven, qué pasa si deja de pagar
- [ ] 🟡 Precio y forma de cobro definidos (ver §9.7 de `ANALISIS-PRE-VENTA.md`)
- [ ] 🟡 Qué pasa con los datos cuando un cliente se va: **exportación garantizada**. Que exista y
      esté escrita es argumento de venta, no un riesgo

## 9 · Licenciamiento 🟡 — antes de cobrar, no antes de pilotear

No hay clave de activación ni forma de saber cuántas instalaciones hay. Un cliente que deja de pagar
sigue usando el sistema, con el código en su máquina.

- [ ] 🟡 Activación por clave contra un servidor propio (un VPS de ~USD 5/mes alcanza)
- [ ] 🔴 **El chequeo falla abierto.** Si el servidor de licencias no responde, el POS vende igual y
      reintenta 7 a 14 días. Un sistema que deja al comercio sin cobrar porque se cayó un VPS
      contradice la promesa central del producto y es un problema legal, no un bug
- [ ] 🟡 Panel propio con las instalaciones activas, su versión y su última señal

## 10 · Lo fiscal — la decisión 🔴

Verificado: **cero** referencias a AFIP/ARCA, CAE, punto de venta fiscal o tipos de comprobante en
todo el código. `cuit` es un campo de texto en la ficha del proveedor. El sistema emite un ticket
interno, no un comprobante.

Hay dos caminos y **hay que elegir uno ahora**, no descubrirlo en la demo:

- [ ] **A** — Implementar WSFEv1: certificado, homologación, tipos A/B/C y notas de crédito para las
      devoluciones que ya existen. **4 a 8 semanas** y hay que hacerlo bien: un comprobante mal
      emitido es un problema del cliente con el fisco.
- [ ] **B** — Salir como **sistema de gestión e inventario con ticket no fiscal**, integrable
      después. Es un producto legítimo y más chico, pero **tiene que estar escrito en la propuesta
      comercial**, no aclararse cuando el cliente pregunta.

> Si se elige A, antes hay que migrar el dinero de `FLOAT` a centavos enteros (§11). Con
> comprobantes fiscales de por medio, ese redondeo deja de ser teórico.

## 11 · Deuda técnica que puede esperar 🟢

Ninguna de estas frena una instalación. Están acá para que no se olviden ni se agranden.

| | Qué es | Cuándo encararlo |
|---|---|---|
| M-09 | Respaldos sin cifrar | Cuando se decida dónde vive la frase de paso |
| M-12 | Dinero en `FLOAT` (desvío medido: 5 × 10⁻⁹) | **Antes** de emitir comprobantes fiscales |
| T-53 | Accesibilidad: **0** `aria-` y **0** `role=` en 7.164 líneas | Antes de vender al Estado o a una cadena |
| T-52 | Lint: 148 hallazgos, 118 son `any` en `api.ts` y `exportExcel.ts` | Cuando se toque ese código |
| — | `Admin.tsx` con 3.000+ líneas y `App.tsx` con 1.600 | Al agregar algo grande: sacarlo a un módulo |

## 12 · Definición de "listo para producción"

El sistema está listo para instalarse en un comercio real cuando **las nueve cosas** se cumplen a la
vez:

1. `main` tiene todo mergeado y CI en verde en las dos configuraciones
2. Se instala con un ejecutable, sin consola, en una máquina limpia
3. Arranca solo al prender la PC y se levanta solo si se cae
4. Se puede actualizar a distancia, con respaldo previo y vuelta atrás
5. Imprime en térmica con corte, y abre el cajón
6. El celular escanea, o está documentado que se usa lector USB
7. Un respaldo se restauró de verdad en una máquina limpia, al menos una vez
8. Hay un teléfono al que llamar y un horario declarado
9. La decisión fiscal está tomada y escrita

## 13 · Cronograma realista

| Etapa | Qué entra | Tiempo |
|---|---|---|
| **Semana 1** | Merge, §0, arranque del instalador | 1 semana |
| **Semanas 2-3** | Instalador, servicio, actualización remota | 2 semanas |
| **Semana 4** | Impresora térmica, HTTPS del local, prueba de restauración | 1 semana |
| **Semanas 5-8** | **Piloto en un local real, gratis**, mirando los logs todos los días | 1 mes |
| **Semanas 9-10** | Arreglos del piloto, soporte, legal, licenciamiento | 2 semanas |
| **Después** | Lo fiscal (si es el camino A) o la propuesta comercial (camino B) | 4 a 8 semanas |

**Total hasta la primera instalación paga: dos meses y medio, aproximadamente.** El piloto no es
tiempo perdido: es el control de calidad más barato que se puede comprar, y cuesta una impresora.

## 14 · Lo que NO hay que hacer todavía

- **No cobrar una suscripción a un local al que no se le puede llevar un arreglo.** Es el error caro
  de esta etapa: te ata a soporte manual eterno justo cuando querés crecer.
- **No arrancar la facturación electrónica antes del piloto.** Son 4 a 8 semanas invertidas en un
  módulo que todavía no sabés si el cliente quiere como lo imaginás.
- **No convertir el sistema a multi-tenant.** Rompe el offline, que es el único diferencial real
  frente a lo que ya está en el mercado. La decisión está en la §9 de `ANALISIS-PRE-VENTA.md`.
- **No agregar funciones nuevas hasta el piloto.** Todo lo que falta en esta lista es entrega y
  operación, no producto.
