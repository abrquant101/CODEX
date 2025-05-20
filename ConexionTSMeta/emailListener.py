import time
import imaplib
import email
from email.header import decode_header
import re
import csv
import os
import uuid
from filelock import FileLock

# Datos de conexión
IMAP_SERVER = 'imap.gmail.com'
EMAIL_ACCOUNT = 'notificacionesdarwinsyo@gmail.com'
PASSWORD = 'ktxzeqagsklsxolp'

# Archivo de órdenes
#ARCHIVO_ORDENES = 'ordenes.csv'
#LOCK_FILE = 'ordenes.csv.lock'

# Definir la ruta donde deseas guardar el archivo .csv
ARCHIVO_ORDENES = r"C:\Users\Alberto\AppData\Roaming\MetaQuotes\Terminal\F0DEBE9BA569B53E62B00FE1DE068813\MQL4\Files\ordenes.csv"  # Ruta personalizada para guardar el archivo
#C:\Users\Alberto\AppData\Roaming\MetaQuotes\Terminal\F0DEBE9BA569B53E62B00FE1DE068813\MQL4\Files
LOCK_FILE = ARCHIVO_ORDENES + ".lock"
LOCK_FILE_MQL4 = r"C:\Users\Alberto\AppData\Roaming\MetaQuotes\Terminal\F0DEBE9BA569B53E62B00FE1DE068813\MQL4\Files\ordenes.csv.lock"


def conectar_servidor():
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(EMAIL_ACCOUNT, PASSWORD)
    return mail

def leer_emails():
    mail = conectar_servidor()
    mail.select('inbox')
    status, mensajes = mail.search(None, '(UNSEEN FROM "notificacionesdarwinsyo@gmail.com")')
    mensajes = mensajes[0].split()

    for num in mensajes:
        status, datos = mail.fetch(num, '(RFC822)')
        raw_email = datos[0][1]
        procesar_email(raw_email)
        mail.store(num, '+FLAGS', '\\Seen')

    mail.close()
    mail.logout()

def procesar_email(raw_email):
    email_message = email.message_from_bytes(raw_email)
    subject, encoding = decode_header(email_message['Subject'])[0]
    if isinstance(subject, bytes):
        subject = subject.decode(encoding if encoding else 'utf-8')

    print(subject)
    if 'Strategy Filled Order' in subject:
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get('Content-Disposition'))
                if content_type == 'text/plain' and 'attachment' not in content_disposition:
                    email_body = part.get_payload(decode=True).decode()
                    extraer_datos_orden(email_body)
                    break
        else:
            email_body = email_message.get_payload(decode=True).decode()
            extraer_datos_orden(email_body)
    else:
        print('El email no es una notificación de orden de TradeStation.')

def extraer_datos_orden(email_body):
    lines = email_body.strip().splitlines()
    order_info = ''
    occurred = ''
    signal = ''
    interval = ''
    workspace = ''

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
        order_regex = r'^(Buy|Sell)\s+(\d+)\s+@?(\S+)\s+@?\s+(Market|[\d\.]+)(?:\s+(.*))?$'
        match = re.match(order_regex, order_info)
        if match:
            action = match.group(1)
            quantity = match.group(2)
            instrument = match.group(3)
            price = match.group(4)
            order_type = match.group(5) if match.group(5) else ''

            order_data = {
                'action': action,
                'quantity': quantity,
                'instrument': instrument,
                'price': price,
                'order_type': order_type.strip(),
                'occurred': occurred,
                'signal': signal,
                'interval': interval,
                'workspace': workspace.split("\\")[-1]
            }

            print('Orden procesada:', order_data)

            escribir_orden_en_archivo(order_data)
        else:
            print('No se pudo analizar la información de la orden.')
    else:
        print('No se pudo extraer toda la información necesaria del email.')

def escribir_orden_en_archivo(order_data):
    existe_archivo = os.path.isfile(ARCHIVO_ORDENES)
    order_data['order_id'] = str(uuid.uuid4())
    order_data['status'] = 'Pending'

    campos = ['order_id', 'action', 'quantity', 'instrument', 'price', 'order_type', 'occurred', 'signal', 'interval', 'workspace', 'status']

    # Comprobar si el archivo.lock de MQL4 existe y esperar
    while os.path.exists(LOCK_FILE_MQL4):
        print("Archivo .lock de MQL4 encontrado. Esperando...")
        time.sleep(0.2)  # Espera antes de volver a comprobar

    # Crear y adquirir el lock para Python
    lock = FileLock(LOCK_FILE)
    with lock:
        with open(ARCHIVO_ORDENES, 'a', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=campos)

            if not existe_archivo:
                writer.writeheader()

            writer.writerow(order_data)

if __name__ == "__main__":
    print("RUNNING")
    while True:
        leer_emails()
        time.sleep(1)
        #print("//////DURMIENDO//////")
