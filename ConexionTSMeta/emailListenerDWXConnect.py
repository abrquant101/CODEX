import time
import imaplib
import email
from email.header import decode_header
import re

import csv
import os

import uuid
order_id = str(uuid.uuid4())

# Datos de conexión
IMAP_SERVER = 'imap.gmail.com'  # Ejemplo: 'imap.gmail.com'
EMAIL_ACCOUNT = 'notificacionesdarwinsyo@gmail.com'
PASSWORD = 'ktxzeqagsklsxolp'

def conectar_servidor():
    # Crear una instancia de IMAP4_SSL
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    # Iniciar sesión
    mail.login(EMAIL_ACCOUNT, PASSWORD)
    return mail

def leer_emails():
    mail = conectar_servidor()
    # Seleccionar la bandeja de entrada
    mail.select('inbox')
    # Buscar emails no leídos de TradeStation
    #status, mensajes = mail.search(None, '(UNSEEN FROM "no-reply@tradestation.com")')
    status, mensajes = mail.search(None, '(UNSEEN FROM "notificacionesdarwinsyo@gmail.com")')
    #status, mensajes = mail.search(None, '(UNSEEN FROM "alberto.br@sersansistemas.com")')

    # Convertir los IDs de mensajes en una lista
    mensajes = mensajes[0].split()

    for num in mensajes:
        # Obtener los datos del email
        status, datos = mail.fetch(num, '(RFC822)')
        raw_email = datos[0][1]
        # Procesar el email
        procesar_email(raw_email)
        # Marcar el email como leído
        mail.store(num, '+FLAGS', '\\Seen')

    # Cerrar la conexión
    mail.close()
    mail.logout()

def leer_emails_test():
    mail = conectar_servidor()
    # Seleccionar la bandeja de entrada
    mail.select('inbox')
    # Buscar emails no leídos de TradeStation
    #status, mensajes = mail.search(None, '(UNSEEN FROM "no-reply@tradestation.com")')
    status, mensajes = mail.search(None, '(UNSEEN FROM "notificacionesdarwinsyo@gmail.com")')
    #status, mensajes = mail.search(None, '(UNSEEN FROM "alberto.br@sersansistemas.com")')

    # Convertir los IDs de mensajes en una lista
    mensajes = mensajes[0].split()

    for num in mensajes:
        # Obtener los datos del email
        status, datos = mail.fetch(num, '(RFC822)')
        raw_email = datos[0][1]
        # Procesar el email
        procesar_email_test(raw_email)
        # Marcar el email como leído
        mail.store(num, '+FLAGS', '\\Seen')

    # Cerrar la conexión
    mail.close()
    mail.logout()

def procesar_email(raw_email):
    # Decodificar el email
    email_message = email.message_from_bytes(raw_email)
    # Obtener el asunto
    subject, encoding = decode_header(email_message['Subject'])[0]
    if isinstance(subject, bytes):
        subject = subject.decode(encoding if encoding else 'utf-8')
    # Verificar si es una notificación de orden
    print(subject)
    if 'Strategy Filled Order' in subject:
        # Obtener el cuerpo del email
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get('Content-Disposition'))
                if content_type == 'text/plain' and 'attachment' not in content_disposition:
                    # Obtener el contenido del email
                    email_body = part.get_payload(decode=True).decode()
                    extraer_datos_orden(email_body)
                    break
        else:
            # Email sin adjuntos y no multipart
            email_body = email_message.get_payload(decode=True).decode()
            extraer_datos_orden(email_body)
    else:
        print('El email no es una notificación de orden de TradeStation.')

def procesar_email_test(raw_email):
    # Decodificar el email
    email_message = email.message_from_bytes(raw_email)
    # Obtener el asunto
    subject, encoding = decode_header(email_message['Subject'])[0]
    if isinstance(subject, bytes):
        subject = subject.decode(encoding if encoding else 'utf-8')
    # Verificar si es una notificación de orden
    print(subject)
    if 'TradeStation - Test Message' in subject:
        # Obtener el cuerpo del email
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get('Content-Disposition'))
                if content_type == 'text/plain' and 'attachment' not in content_disposition:
                    # Obtener el contenido del email
                    email_body = part.get_payload(decode=True).decode()
                    extraer_datos_orden(email_body)
                    break
        else:
            # Email sin adjuntos y no multipart
            email_body = email_message.get_payload(decode=True).decode()
            extraer_datos_orden(email_body)
    else:
        print('El email no es una notificación de orden de TradeStation.')

def extraer_datos_orden(email_body):
    # Separar el email en líneas
    lines = email_body.strip().splitlines()

    # Inicializar variables
    order_info = ''
    occurred = ''
    signal = ''
    interval = ''
    workspace = ''

    # Procesar cada línea
    for line in lines:
        line = line.strip()
        if line.startswith('Order:'):
            order_info = line[len('Order:'):].strip()
        elif line.startswith('Occurred:'):
            occurred = line[len('Occurred:'):].strip()
        elif line.startswith('Signal:'):
            signal = line[len('Signal:'):].strip()
        elif line.startswith('Interval:'):
            interval = line[len('Interval:'):].strip()
        elif line.startswith('Workspace:'):
            workspace = line[len('Workspace:'):].strip()

    if order_info and occurred and signal:
        # Desglosar la información de la orden
        # Manejar ambos casos: con precio y tipo de orden, y órdenes al mercado
        # Ejemplos:
        # 'Sell 45 @NQ @ 20068.00 Stop Market'
        # 'Sell 1 @NQ @ Market'

        # Patrón actualizado para manejar ambos casos
        order_regex = r'^(Buy|Sell)\s+(\d+)\s+@?(\S+)\s+@?\s+(Market|[\d\.]+)(?:\s+(.*))?$'
        match = re.match(order_regex, order_info)
        if match:
            action = match.group(1)
            quantity = match.group(2)
            instrument = match.group(3)
            price = match.group(4)
            order_type = match.group(5) if match.group(5) else ''

            # Crear un diccionario con los datos extraídos
            order_data = {
                'action': action,
                'quantity': quantity,
                'instrument': instrument,
                'price': price,
                'order_type': order_type.strip(),
                'occurred': occurred,
                'signal': signal,
                'interval': interval,
                'workspace': workspace
            }

            # Mostrar los datos extraídos
            print('Orden procesada:', order_data)

            # Escribir la orden en el archivo
            escribir_orden_en_archivo(order_data)
        else:
            print('No se pudo analizar la información de la orden.')
    else:
        print('No se pudo extraer toda la información necesaria del email.')

def escribir_orden_en_archivo(order_data):
    archivo_ordenes = 'ordenes.csv'
    existe_archivo = os.path.isfile(archivo_ordenes)

    # Agregar un ID único y estado 'Pending' a la orden
    order_data['order_id'] = str(uuid.uuid4())
    order_data['status'] = 'Pending'

    # Definir el orden de las columnas
    campos = ['order_id', 'action', 'quantity', 'instrument', 'price', 'order_type', 'occurred', 'signal', 'interval', 'workspace', 'status']

    with open(archivo_ordenes, 'a', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=campos)

        # Si el archivo no existía, escribir la cabecera
        if not existe_archivo:
            writer.writeheader()

        writer.writerow(order_data)

if __name__ == "__main__":
    print("RUNNING")
    while True:
        leer_emails()
        # Esperar un tiempo antes de volver a comprobar
        time.sleep(5)  # Espera 60 segundos antes de la siguiente comprobación
        print("//////DURMIENDO//////")

 