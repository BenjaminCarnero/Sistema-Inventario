"""El formato ESC/POS se prueba byte a byte: es un protocolo binario, no HTML,
así que "se ve bien" no alcanza — hay que verificar los comandos exactos que
recibiría la impresora."""
from app.ticket_escpos import (
    DatosTicket, ItemTicket, generar_ticket,
    RESET, TABLA_WPC1252, CORTE_PARCIAL, ABRIR_CAJON,
    _linea_dos_columnas, _moneda,
)


def _datos(**cambios):
    base = dict(
        negocio_nombre="Almacén Don José",
        items=[ItemTicket(cantidad=2, nombre="Coca Cola 500ml", precio_unitario=800.0, subtotal=1600.0)],
        total=1600.0,
        metodo_pago="EFECTIVO",
        numero_operacion=42,
    )
    base.update(cambios)
    return DatosTicket(**base)


class TestEstructuraBasica:
    def test_arranca_con_reset_y_tabla_de_caracteres(self):
        ticket = generar_ticket(_datos())
        assert ticket.startswith(RESET + TABLA_WPC1252)

    def test_termina_con_el_corte(self):
        ticket = generar_ticket(_datos(abrir_cajon=False))
        assert ticket.endswith(CORTE_PARCIAL)

    def test_el_nombre_del_negocio_esta_en_los_bytes(self):
        ticket = generar_ticket(_datos(negocio_nombre="Kiosco 24hs"))
        assert "Kiosco 24hs".encode("cp1252") in ticket

    def test_acentos_y_enie_no_rompen_la_codificacion(self):
        """cp1252 cubre español; si algún carácter no entrara, se reemplaza
        en vez de tirar una excepción que corte la impresión entera."""
        ticket = generar_ticket(_datos(negocio_nombre="Almacén Ñoño's"))
        assert "Almacén Ñoño's".encode("cp1252") in ticket

    def test_no_abre_el_cajon_si_no_se_pidio(self):
        ticket = generar_ticket(_datos(abrir_cajon=False))
        assert ABRIR_CAJON not in ticket

    def test_abre_el_cajon_si_se_pidio(self):
        ticket = generar_ticket(_datos(abrir_cajon=True))
        assert ABRIR_CAJON in ticket
        # Después del corte: no tiene sentido pedir el cajón antes de cortar el papel
        assert ticket.index(CORTE_PARCIAL) < ticket.index(ABRIR_CAJON)


class TestContenidoDelTicket:
    def test_el_numero_de_operacion_aparece(self):
        ticket = generar_ticket(_datos(numero_operacion=12345))
        assert b"12345" in ticket

    def test_cada_item_aparece_con_cantidad_y_nombre(self):
        datos = _datos(items=[
            ItemTicket(cantidad=3, nombre="Fideos", precio_unitario=500.0, subtotal=1500.0),
            ItemTicket(cantidad=1, nombre="Aceite", precio_unitario=2000.0, subtotal=2000.0),
        ])
        ticket = generar_ticket(datos)
        assert "3x Fideos".encode("cp1252") in ticket
        assert "1x Aceite".encode("cp1252") in ticket

    def test_sin_descuento_no_aparece_la_linea(self):
        ticket = generar_ticket(_datos(descuento_nombre="", descuento_monto=0))
        assert b"-$" not in ticket

    def test_con_descuento_aparece_restando(self):
        ticket = generar_ticket(_datos(descuento_nombre="Promo jubilados", descuento_monto=150.0))
        assert "Promo jubilados".encode("cp1252") in ticket
        assert "-$150.00".encode("cp1252") in ticket

    def test_iva_no_se_desglosa_si_esta_apagado(self):
        ticket = generar_ticket(_datos(mostrar_iva=False, iva_monto=200.0))
        assert "Neto gravado".encode("cp1252") not in ticket

    def test_iva_no_se_desglosa_si_no_hay_monto(self):
        """mostrar_iva_en_ticket prendido pero la venta no tiene IVA cargado
        (por ejemplo, un país sin ese impuesto): no debe imprimir un renglón
        con $0.00 que no significa nada."""
        ticket = generar_ticket(_datos(mostrar_iva=True, iva_monto=0))
        assert "Neto gravado".encode("cp1252") not in ticket

    def test_iva_se_desglosa_cuando_corresponde(self):
        ticket = generar_ticket(_datos(mostrar_iva=True, iva_monto=336.0, iva_porcentaje=21, iva_nombre="IVA"))
        assert "Neto gravado".encode("cp1252") in ticket
        assert "IVA 21%".encode("cp1252") in ticket

    def test_efectivo_muestra_recibido_y_vuelto(self):
        ticket = generar_ticket(_datos(metodo_pago="EFECTIVO", monto_recibido=2000.0, vuelto=400.0))
        assert "Recibido".encode("cp1252") in ticket
        assert "VUELTO".encode("cp1252") in ticket
        assert "$400.00".encode("cp1252") in ticket

    def test_otro_metodo_de_pago_no_muestra_vuelto(self):
        ticket = generar_ticket(_datos(metodo_pago="TARJETA", monto_recibido=None, vuelto=None))
        assert "VUELTO".encode("cp1252") not in ticket
        assert "Abonado con TARJETA".encode("cp1252") in ticket

    def test_el_mensaje_de_pie_aparece(self):
        ticket = generar_ticket(_datos(mensaje_pie="¡Gracias por su compra!"))
        assert "¡Gracias por su compra!".encode("cp1252") in ticket

    def test_sin_mensaje_de_pie_no_rompe(self):
        generar_ticket(_datos(mensaje_pie=""))  # no debe lanzar


class TestFormatoDeColumnas:
    def test_moneda_formatea_con_dos_decimales_y_separador_de_miles(self):
        assert _moneda(1234.5, "$") == "$1,234.50"

    def test_dos_columnas_alinea_el_importe_a_la_derecha(self):
        linea = _linea_dos_columnas("Producto", "$100.00", ancho=20)
        texto = linea.decode("cp1252").rstrip("\n")
        assert len(texto) == 20
        assert texto.endswith("$100.00")
        assert texto.startswith("Producto")

    def test_etiqueta_larga_se_recorta_en_vez_de_partir_la_linea(self):
        """Una línea de más rompe el resto del ticket en una impresora real
        (offset de bytes, no de caracteres): mejor recortar que desalinear."""
        linea = _linea_dos_columnas("Un producto con un nombre carísimo y larguísimo", "$1.00", ancho=20)
        texto = linea.decode("cp1252").rstrip("\n")
        assert len(texto) == 20
        assert texto.endswith("$1.00")
