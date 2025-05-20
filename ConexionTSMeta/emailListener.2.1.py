import time
import imaplib
import email
from email.header import decode_header
import re
import csv
import os
import uuid
from filelock import FileLock
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime

# Datos de conexión
IMAP_SERVER = 'imap.gmail.com'
EMAIL_ACCOUNT = 'notificacionesdarwinsyo@gmail.com'
PASSWORD = 'ktxzeqagsklsxolp'

# Archivo de órdenes
#ARCHIVO_ORDENES = r"C:\Users\Alberto\AppData\Roaming\MetaQuotes\Terminal\F0DEBE9BA569B53E62B00FE1DE068813\MQL4\Files\ordenes.csv"
ARCHIVO_ORDENES = r"C:\Users\Alberto\AppData\Roaming\MetaQuotes\Terminal\F0DEBE9BA569B53E62B00FE1DE068813\MQL4\Files\ordenesTest.csv"
#ARCHIVO_ORDENES = r"C:\Users\Alberto\Desktop\ConexiónTSMeta\ordenesTest.csv"

LOCK_FILE = ARCHIVO_ORDENES + ".lock"
#LOCK_FILE_MQL4 = r"C:\Users\Alberto\AppData\Roaming\MetaQuotes\Terminal\F0DEBE9BA569B53E62B00FE1DE068813\MQL4\Files\ordenes.csv.lock"
LOCK_FILE_MQL4 = LOCK_FILE

# Diccionario global para almacenar el modo (Largo/Corto/No operar) por workspace
workspace_modes = {}

# Controlar el hilo principal de escucha
running = False
thread_loop = None

# Lista global de workspaces (agregados manualmente y detectados)
all_workspaces = []

# Hora de reinicio automático (HH:MM) - Por defecto
AUTOMATIC_RESTART_TIME = "06:00"
last_restart_date = None  # Para no reiniciar varias veces el mismo día

def log_message(msg):
    text_log.config(state='normal')
    text_log.insert(tk.END, msg + "\n")
    text_log.see(tk.END)
    text_log.config(state='disabled')
    print(msg)

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

    log_message(f"Asunto: {subject}")
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
        log_message('El email no es una notificación de orden de TradeStation.')

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

            # Tomar el nombre del workspace sin ruta
            ws_name = workspace.split("\\")[-1] if workspace else ''
            # Obtener modo del workspace
            modo = workspace_modes.get(ws_name, '')

            # Si el workspace no está en la lista o modo es "No operar", no escribir la orden
            if ws_name not in workspace_modes or modo == "No operar":
                log_message(f"Orden de {ws_name} ignorada (No operar o no en lista).")
                return

            # Obtener capital del campo en la GUI
            capital = entry_capital.get().strip()
            if not capital:
                capital = "0"  # Valor por defecto si está vacío

            # Hora de procesamiento
            hora_procesamiento = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            order_data = {
                'action': action,
                'quantity': quantity,
                'capital': capital,  # Nuevo campo agregado justo después de 'quantity'
                'instrument': instrument,
                'price': price,
                'order_type': order_type.strip(),
                'occurred': occurred,
                'signal': signal,
                'interval': interval,
                'workspace': ws_name,
                'modo': modo
            }

            log_message(f'Orden procesada a las {hora_procesamiento}: {order_data}')
            escribir_orden_en_archivo(order_data)
        else:
            log_message('No se pudo analizar la información de la orden.')
    else:
        log_message('No se pudo extraer toda la información necesaria del email.')

def escribir_orden_en_archivo(order_data):
    existe_archivo = os.path.isfile(ARCHIVO_ORDENES)
    order_data['order_id'] = str(uuid.uuid4())
    order_data['status'] = 'Pending'

    # Ahora el campo 'capital' va después de 'quantity'
    campos = ['order_id', 'action', 'quantity', 'capital', 'instrument', 'price', 'order_type',
              'occurred', 'signal', 'interval', 'workspace', 'modo', 'status']
    
    # Comprobar si el archivo.lock de MQL4 existe y esperar
    while os.path.exists(LOCK_FILE_MQL4):
        print("Archivo .lock de MQL4 encontrado. Esperando...")
        time.sleep(0.2)  # Espera antes de volver a comprobar

    lock = FileLock(LOCK_FILE)
    with lock:
        with open(ARCHIVO_ORDENES, 'a', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=campos)

            if not existe_archivo:
                writer.writeheader()

            writer.writerow(order_data)
    log_message("Orden escrita en el CSV.")

def obtener_todos_los_workspaces():
    mail = conectar_servidor()
    mail.select('inbox')
    status, mensajes = mail.search(None, 'ALL')
    mensajes = mensajes[0].split()

    workspaces = set()

    for num in mensajes:
        status, datos = mail.fetch(num, '(RFC822)')
        raw_email = datos[0][1]
        email_message = email.message_from_bytes(raw_email)
        subject, encoding = decode_header(email_message['Subject'])[0]
        if isinstance(subject, bytes):
            subject = subject.decode(encoding if encoding else 'utf-8')

        if 'Strategy Filled Order' in subject:
            # Extraer workspace
            email_body = ""
            if email_message.is_multipart():
                for part in email_message.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get('Content-Disposition'))
                    if content_type == 'text/plain' and 'attachment' not in content_disposition:
                        email_body = part.get_payload(decode=True).decode()
                        break
            else:
                email_body = email_message.get_payload(decode=True).decode()

            ws = extraer_workspace(email_body)
            if ws:
                workspaces.add(ws)

    mail.close()
    mail.logout()

    return list(workspaces)

def extraer_workspace(email_body):
    lines = email_body.strip().splitlines()
    for line in lines:
        line = line.strip()
        if line.startswith('Workspace:'):
            workspace = line[len('Workspace:'):].strip()
            return workspace.split("\\")[-1]
    return ''

def buscar_ws_en_email():
    ws_list = obtener_todos_los_workspaces()
    log_message("Buscando Workspaces en emails...")

    # Añadir a la lista global los detectados que aún no estén
    added = False
    for ws in ws_list:
        if ws not in all_workspaces:
            all_workspaces.append(ws)
            added = True

    if added:
        log_message("Nuevos workspaces agregados.")
    else:
        log_message("No se encontraron nuevos workspaces o ya estaban agregados.")

    mostrar_workspaces_en_frame()

def mostrar_workspaces_en_frame():
    # Limpiar el frame
    for w in workspaces_frame.winfo_children():
        w.destroy()

    if not all_workspaces:
        tk.Label(workspaces_frame, text="No se encontraron workspaces.").pack()
        return

    for ws in all_workspaces:
        fr = tk.Frame(workspaces_frame)
        fr.pack(anchor='w', pady=2, fill='x')

        lbl = tk.Label(fr, text=ws)
        lbl.pack(side='left', padx=5)

        combo = ttk.Combobox(fr, values=["Largo", "Corto", "No operar"])
        combo.set("No operar")  # Valor por defecto "No operar"
        combo.pack(side='left')
        combo._workspace = ws

        btn_del = tk.Button(fr, text="Eliminar", command=lambda w=ws: eliminar_workspace(w))
        btn_del.pack(side='left', padx=5)

def eliminar_workspace(ws):
    if ws in all_workspaces:
        all_workspaces.remove(ws)
        mostrar_workspaces_en_frame()
        log_message(f"Workspace {ws} eliminado de la lista.")

def set_modes_and_start(automatic=False):
    # Leer los combos
    local_modes = {}
    for child in workspaces_frame.winfo_children():
        for w in child.winfo_children():
            if isinstance(w, ttk.Combobox):
                ws = w._workspace
                modo = w.get()
                local_modes[ws] = modo

    # Actualizar el diccionario global
    workspace_modes.clear()
    workspace_modes.update(local_modes)

    iniciar_operativa(automatic=automatic)

def iniciar_operativa(automatic=False):
    global running, thread_loop
    if running:
        if not automatic:
            messagebox.showinfo("Info", "La operativa ya está en marcha.")
        return

    running = True
    thread_loop = threading.Thread(target=main_loop, daemon=True)
    thread_loop.start()
    log_message("Operativa iniciada. Escuchando nuevos correos...")
    # Solo mostramos mensaje si no es automático
    if not automatic:
        messagebox.showinfo("Info", "Operativa iniciada. Escuchando nuevos correos...")

def parar_operativa(automatic=False):
    global running
    if running:
        running = False        
        log_message("Operativa detenida.")
        if not automatic:
            messagebox.showinfo("Info", "Operativa detenida.")
    else:
        log_message("La operativa no estaba en marcha.")
        messagebox.showinfo("Info", "La operativa no estaba en marcha.")

def main_loop():
    log_message("RUNNING LOOP")
    while running:
        leer_emails()
        time.sleep(5)  # Espera 5 segundos antes de volver a leer

def agregar_workspace():
    nuevo_ws = entry_workspace.get().strip()
    if nuevo_ws and nuevo_ws not in all_workspaces:
        all_workspaces.append(nuevo_ws)
        mostrar_workspaces_en_frame()
        entry_workspace.delete(0, tk.END)
        log_message(f"Workspace {nuevo_ws} agregado manualmente.")
    elif nuevo_ws in all_workspaces:
        messagebox.showinfo("Info", "El workspace ya existe en la lista.")
        log_message(f"Intento de agregar {nuevo_ws}, pero ya existe.")
    else:
        log_message("No se ingresó ningún workspace para agregar.")

def check_automatic_restart():
    global last_restart_date
    now = datetime.now()
    current_time_str = now.strftime("%H:%M")
    current_date = now.date()

    if current_time_str == AUTOMATIC_RESTART_TIME and (last_restart_date != current_date):
        log_message("Ejecutando reinicio automático...")
        # Reiniciar la operativa sin pedir confirmación
        if running:
            parar_operativa(True)  # Esta acción detiene la operativa sin pedir confirmación

        # Reiniciar la operativa automáticamente: 
        # Pasamos automatic=True para no mostrar messagebox.
        set_modes_and_start(automatic=True)  
        last_restart_date = current_date

    # Volver a programar esta función en 60 segundos
    root.after(60000, check_automatic_restart)

def actualizar_hora_reinicio():
    global AUTOMATIC_RESTART_TIME
    nueva_hora = entry_hora_reinicio.get().strip()
    # Validar formato HH:MM
    if re.match(r"^\d{2}:\d{2}$", nueva_hora):
        AUTOMATIC_RESTART_TIME = nueva_hora
        log_message(f"Hora de reinicio actualizada a {AUTOMATIC_RESTART_TIME}")
        messagebox.showinfo("Info", f"Hora de reinicio actualizada a {AUTOMATIC_RESTART_TIME}")
    else:
        messagebox.showerror("Error", "El formato de la hora debe ser HH:MM")
        log_message("Error al actualizar la hora de reinicio: formato inválido.")

####################
# INTERFAZ GRÁFICA #
####################

root = tk.Tk()
root.title("Programa de Operativa con Emails")

top_frame = tk.Frame(root)
top_frame.pack(pady=10, padx=10, fill='x')

# Campo para añadir manualmente workspaces
entry_workspace = tk.Entry(top_frame)
entry_workspace.pack(side='left', padx=5)
add_ws_button = tk.Button(top_frame, text="Añadir Workspace", command=agregar_workspace)
add_ws_button.pack(side='left', padx=5)

# Campo para hora de reinicio automático
hora_frame = tk.Frame(root)
hora_frame.pack(pady=10, padx=10, fill='x')

tk.Label(hora_frame, text="Hora de reinicio (HH:MM):").pack(side='left', padx=5)
entry_hora_reinicio = tk.Entry(hora_frame, width=10)
entry_hora_reinicio.insert(0, AUTOMATIC_RESTART_TIME)
entry_hora_reinicio.pack(side='left', padx=5)
btn_actualizar_hora = tk.Button(hora_frame, text="Actualizar Hora Reinicio", command=actualizar_hora_reinicio)
btn_actualizar_hora.pack(side='left', padx=5)

# Campo para el capital
capital_frame = tk.Frame(root)
capital_frame.pack(pady=10, padx=10, fill='x')

tk.Label(capital_frame, text="Capital:").pack(side='left', padx=5)
entry_capital = tk.Entry(capital_frame, width=10)
entry_capital.insert(0, "20000000")  # Valor inicial
entry_capital.pack(side='left', padx=5)

frame_buttons = tk.Frame(root)
frame_buttons.pack(pady=10)

buscar_ws_button = tk.Button(frame_buttons, text="Buscar WS en email", command=buscar_ws_en_email)
buscar_ws_button.pack(side='left', padx=5)

start_button = tk.Button(frame_buttons, text="InicioOperativa", command=set_modes_and_start)
start_button.pack(side='left', padx=5)

stop_button = tk.Button(frame_buttons, text="Parar", command=parar_operativa)
stop_button.pack(side='left', padx=5)

# Ventana de workspaces
workspaces_frame = tk.Frame(root)
workspaces_frame.pack(fill='both', expand=True, padx=10, pady=10)

# Zona de log
log_frame = tk.Frame(root)
log_frame.pack(fill='both', expand=True, padx=10, pady=10)

scrollbar = tk.Scrollbar(log_frame)
scrollbar.pack(side='right', fill='y')

text_log = tk.Text(log_frame, wrap='word', yscrollcommand=scrollbar.set, state='disabled')
text_log.pack(fill='both', expand=True)
scrollbar.config(command=text_log.yview)

# Iniciar el chequeo del reinicio automático
root.after(60000, check_automatic_restart)  # Comprobar cada minuto

root.mainloop()
