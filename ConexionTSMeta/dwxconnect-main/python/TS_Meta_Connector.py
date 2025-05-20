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
from time import sleep
from random import random
from datetime import timezone, timedelta

# Asegúrate de que dwx_client.py y api/dwx_client.py estén disponibles en tu entorno.
from api.dwx_client import dwx_client

##########################
# Código de conexión a MT5
##########################

class tick_processor():

    def __init__(self, MT_directory_path, 
                 sleep_delay=0.005,
                 max_retry_command_seconds=10,
                 verbose=True):

        self.open_test_trades = False
        self.last_open_time = datetime.now(timezone.utc)
        self.last_modification_time = datetime.now(timezone.utc)

        self.dwx = dwx_client(self, MT_directory_path, sleep_delay, 
                              max_retry_command_seconds, verbose=verbose)
        sleep(1)

        self.dwx.start()        
        print("Account info:", self.dwx.account_info)

        # Ejemplo: Suscribir a símbolos para recibir ticks
        self.dwx.subscribe_symbols(['NDX', 'XAUUSD'])
        # Puedes agregar más lógica aquí si lo deseas.

    def on_tick(self, symbol, bid, ask):
        # Aquí recibes los ticks de los símbolos suscritos.
        # De momento, no haremos nada especial.
        # print("Tick:", symbol, bid, ask)
        pass

    def on_bar_data(self, symbol, time_frame, time, open_price, high, low, close_price, tick_volume):
        # Datos de velas si te suscribes
        pass

    def on_historic_data(self, symbol, time_frame, data):
        # Datos históricos
        pass

    def on_historic_trades(self):
        pass

    def on_message(self, message):
        if message['type'] == 'ERROR':
            print("ERROR |", message['error_type'], "|", message['description'])
        elif message['type'] == 'INFO':
            print("INFO |", message['message'])

    def on_order_event(self):
        print(f'on_order_event. open_orders: {len(self.dwx.open_orders)} open orders')


#################################
# Código de lectura de emails y GUI
#################################

IMAP_SERVER = 'imap.gmail.com'
EMAIL_ACCOUNT = 'notificacionesdarwinsyo@gmail.com'
PASSWORD = 'ktxzeqagsklsxolp'

# Archivo de órdenes (aunque no sea relevante ahora, lo mantenemos)
ARCHIVO_ORDENES = r"C:\Users\Alberto\AppData\Roaming\MetaQuotes\Terminal\F0DEBE9BA569B53E62B00FE1DE068813\MQL4\Files\ordenesTest.csv"
LOCK_FILE = ARCHIVO_ORDENES + ".lock"
LOCK_FILE_MQL4 = LOCK_FILE

workspace_modes = {}
running = False
thread_loop = None
all_workspaces = []

AUTOMATIC_RESTART_TIME = "06:00"
last_restart_date = None

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

            ws_name = workspace.split("\\")[-1] if workspace else ''
            modo = workspace_modes.get(ws_name, '')

            if ws_name not in workspace_modes or modo == "No operar":
                log_message(f"Orden de {ws_name} ignorada (No operar o no en lista).")
                return

            capital = entry_capital.get().strip()
            if not capital:
                capital = "0"

            hora_procesamiento = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            order_data = {
                'action': action,
                'quantity': quantity,
                'capital': capital,
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
            # Aquí es donde en el futuro podrás generar el comando para MT5.
            # De momento seguimos con la lógica original de escribir en CSV, 
            # pero realmente ahora no es relevante. Solo queremos tener 
            # los datos. Puedes comentar la siguiente línea si no quieres CSV.
            #escribir_orden_en_archivo(order_data)
            # --- Comienzo del bloque para generar la orden a MQL5 ---

            # Funciones auxiliares adaptadas a Python

            def map_symbol_to_darwinex(instrument):
                # Mapear símbolos igual que en MQL4:
                if instrument == "NQ":
                    return "NDX"      # Ejemplo: NQ -> NDX
                elif instrument == "GC":
                    return "XAUUSD"   # Ejemplo: GC -> XAUUSD
                # Si no hay mapeo específico, retornar el mismo
                return instrument

            def big_point_value_ts(instrument):
                # Igual que en MQL4:
                if instrument == "NQ":
                    return 20
                elif instrument == "GC":
                    return 100
                return 1

            def big_point_value_dwx(instrument):
                if instrument == "NQ":
                    return 10
                elif instrument == "GC":
                    return 100
                return 1

            def calculaMM_DesdeCuentaTS(processor, CapitalTS, ContratosTS, BigPointValueTS, BigPointValueDWX, Precio, LotesCalculoRiesgo=0.01):
                account_equity = processor.dwx.account_info['equity']
                # Evitar divisiones por cero
                if CapitalTS * BigPointValueDWX != 0:
                    lotes = (account_equity * BigPointValueTS * ContratosTS) / (CapitalTS * BigPointValueDWX)
                else:
                    lotes = LotesCalculoRiesgo
                
                # Ajustar a un múltiplo del tamaño mínimo. El EA no hace esta lógica exacta, pero podemos suponer:
                # Suponemos un step mínimo de 0.01 lotes (microlotes)
                lot_step = 0.01
                lotes = max(round(lotes / lot_step) * lot_step, lot_step)
                print(f" Lotes sin redondear: {lotes}, Lotes redondeados: {lotes}")
                return lotes

            def get_open_order_by_workspace(dwx, workspace):
                # Busca una orden abierta cuyo comment coincida con 'workspace'
                # open_orders es un dict {ticket: {datos}}
                for ticket, order_info in dwx.open_orders.items():
                    if order_info['comment'] == workspace:
                        return ticket, order_info
                return None, None

            # Lógica para ejecutar la orden en Python
            # Recordemos que tenemos: order_data con keys:
            # 'action' (Buy/Sell), 'quantity', 'capital', 'instrument', 'modo' (Largo/Corto), 'workspace', etc.

            # Extraer datos
            action = order_data['action']          # Buy o Sell
            quantity = float(order_data['quantity'])
            capital_ts = float(order_data['capital'])
            instrument_ts = order_data['instrument']
            modo = order_data['modo']              # Largo, Corto o No operar
            workspace = order_data['workspace']

            # Mapear símbolo
            symbol = map_symbol_to_darwinex(instrument_ts)

            # Obtener valores para el cálculo de lotes
            bpv_ts = big_point_value_ts(instrument_ts)
            bpv_dwx = big_point_value_dwx(instrument_ts)

            # Suponemos precio a mercado. Para buy en largo se usa ask, para sell en corto se usa bid.
            # Por ahora, ya que es a mercado, podemos setear price=0. 
            # El EA receptor (dwx) abrirá orden a mercado si price=0.

            price = 0  # El EA de MQL5 con DWX_server aceptará price=0 para mercado
            sl = 0
            tp = 0
            magic = 1234
            comment = workspace
            expiration = 0

            # Calcular lotes
            lots = calculaMM_DesdeCuentaTS(processor, capital_ts, quantity, bpv_ts, bpv_dwx, 0.0)  # 0.0 como placeholder de precio

            # Decidir qué hacer en función de modo y acción
            # Regla: 
            # - Modo Largo: 
            #   action=Buy -> Abrir BUY si no hay ya BUY. Si hay SELL, cerrar SELL.
            #   action=Sell -> Si hay BUY abierta, cerrarla; si no hay nada, no hacer nada (sería cerrar posición)
            # - Modo Corto: 
            #   action=Sell -> Abrir SELL si no hay ya SELL. Si hay BUY, cerrar BUY.
            #   action=Buy -> Si hay SELL abierta, cerrarla; si no hay nada, no hacer nada.

            ticket_existing, existing_order = get_open_order_by_workspace(processor.dwx, workspace)

            def close_order_if_exists(processor, ticket):
                if ticket is not None:
                    # Cerrar la orden completa
                    # Obtenemos el lote de la orden actual:
                    existing_lots = existing_order['lots']
                    processor.dwx.close_order(ticket, lots=existing_lots)
                    print(f"Cerrada posición existente del workspace {workspace}")
                    return True
                return False

            if modo == "Largo":
                if action == "Buy":
                    # Queremos estar largos
                    if ticket_existing is None:
                        # No hay posición -> abrir BUY
                        processor.dwx.open_order(symbol=symbol, order_type='buy', price=price, lots=lots, comment=comment)
                        print(f"Abrimos BUY {lots} {symbol} para workspace {workspace}")
                    else:
                        # Ya hay algo abierto
                        # Si es una SELL abierta, cerrarla, luego abrir la BUY
                        # Revisamos existing_order['type']: 'buy' o 'sell'
                        if existing_order['type'] == 'sell':
                            # Cerrar sell
                            close_order_if_exists(processor, ticket_existing)
                            # Abrir buy
                            processor.dwx.open_order(symbol=symbol, order_type='buy', price=price, lots=lots, comment=comment)
                            print(f"Cerramos SELL y abrimos BUY {lots} {symbol} para workspace {workspace}")
                        else:
                            # Ya hay un BUY abierto, no hacemos nada
                            print(f"Ya existe un BUY abierto para {workspace}, no hacemos nada.")

                elif action == "Sell":
                    # Queremos cerrar la posición larga si la hay
                    if ticket_existing is not None and existing_order['type'] == 'buy':
                        # Cerrar la BUY
                        close_order_if_exists(processor, ticket_existing)
                    else:
                        print(f"No hay BUY que cerrar para {workspace}")

            elif modo == "Corto":
                if action == "Sell":
                    # Queremos estar cortos
                    if ticket_existing is None:
                        # No hay posición -> abrir SELL
                        processor.dwx.open_order(symbol=symbol, order_type='sell', price=price, lots=lots, comment=comment)
                        print(f"Abrimos SELL {lots} {symbol} para workspace {workspace}")
                    else:
                        # Si hay BUY abierta, cerrarla y luego abrir SELL
                        if existing_order['type'] == 'buy':
                            close_order_if_exists(processor, ticket_existing)
                            processor.dwx.open_order(symbol=symbol, order_type='sell', price=price, lots=lots, comment=comment)
                            print(f"Cerramos BUY y abrimos SELL {lots} {symbol} para workspace {workspace}")
                        else:
                            # Ya hay un SELL abierto, no hacemos nada
                            print(f"Ya existe un SELL abierto para {workspace}, no hacemos nada.")
                elif action == "Buy":
                    # Cerrar posición corta si existe
                    if ticket_existing is not None and existing_order['type'] == 'sell':
                        close_order_if_exists(processor, ticket_existing)
                    else:
                        print(f"No hay SELL que cerrar para {workspace}")

            else:
                print(f"Modo {modo} no válido o 'No operar'. No se hace nada.")


            # --- Fin del bloque para generar la orden a MQL5 ---

        else:
            log_message('No se pudo analizar la información de la orden.')
    else:
        log_message('No se pudo extraer toda la información necesaria del email.')

def escribir_orden_en_archivo(order_data):
    # Esta función ya no es crítica, pero la dejamos por si luego la usas.
    existe_archivo = os.path.isfile(ARCHIVO_ORDENES)
    order_data['order_id'] = str(uuid.uuid4())
    order_data['status'] = 'Pending'

    campos = ['order_id', 'action', 'quantity', 'capital', 'instrument', 'price', 'order_type',
              'occurred', 'signal', 'interval', 'workspace', 'modo', 'status']
    
    while os.path.exists(LOCK_FILE_MQL4):
        print("Archivo .lock de MQL4 encontrado. Esperando...")
        time.sleep(0.2)

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
        combo.set("No operar")
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
    local_modes = {}
    for child in workspaces_frame.winfo_children():
        for w in child.winfo_children():
            if isinstance(w, ttk.Combobox):
                ws = w._workspace
                modo = w.get()
                local_modes[ws] = modo

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
        time.sleep(5)

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
        if running:
            parar_operativa(True)
        set_modes_and_start(automatic=True)  
        last_restart_date = current_date

    root.after(60000, check_automatic_restart)

def actualizar_hora_reinicio():
    global AUTOMATIC_RESTART_TIME
    nueva_hora = entry_hora_reinicio.get().strip()
    if re.match(r"^\d{2}:\d{2}$", nueva_hora):
        AUTOMATIC_RESTART_TIME = nueva_hora
        log_message(f"Hora de reinicio actualizada a {AUTOMATIC_RESTART_TIME}")
        messagebox.showinfo("Info", f"Hora de reinicio actualizada a {AUTOMATIC_RESTART_TIME}")
    else:
        messagebox.showerror("Error", "El formato de la hora debe ser HH:MM")
        log_message("Error al actualizar la hora de reinicio: formato inválido.")

####################
# INICIO DEL PROGRAMA
####################

# Iniciar la conexión a MT5
#MT5_files_dir = 'C:/Users/Alberto/AppData/Roaming/MetaQuotes/Terminal/6C3C6A11D1C3791DD4DBF45421BF8028/MQL5/Files'
MT4_files_dir = 'C:/Users/Alberto/AppData/Roaming/MetaQuotes/Terminal/F0DEBE9BA569B53E62B00FE1DE068813/MQL4/Files'

#processor = tick_processor(MT5_files_dir)
processor = tick_processor(MT4_files_dir)

# Iniciar la interfaz gráfica
root = tk.Tk()
root.title("Programa de Operativa con Emails")

top_frame = tk.Frame(root)
top_frame.pack(pady=10, padx=10, fill='x')

entry_workspace = tk.Entry(top_frame)
entry_workspace.pack(side='left', padx=5)
add_ws_button = tk.Button(top_frame, text="Añadir Workspace", command=agregar_workspace)
add_ws_button.pack(side='left', padx=5)

hora_frame = tk.Frame(root)
hora_frame.pack(pady=10, padx=10, fill='x')

tk.Label(hora_frame, text="Hora de reinicio (HH:MM):").pack(side='left', padx=5)
entry_hora_reinicio = tk.Entry(hora_frame, width=10)
entry_hora_reinicio.insert(0, AUTOMATIC_RESTART_TIME)
entry_hora_reinicio.pack(side='left', padx=5)
btn_actualizar_hora = tk.Button(hora_frame, text="Actualizar Hora Reinicio", command=actualizar_hora_reinicio)
btn_actualizar_hora.pack(side='left', padx=5)

capital_frame = tk.Frame(root)
capital_frame.pack(pady=10, padx=10, fill='x')

tk.Label(capital_frame, text="Capital:").pack(side='left', padx=5)
entry_capital = tk.Entry(capital_frame, width=10)
entry_capital.insert(0, "20000000")
entry_capital.pack(side='left', padx=5)

frame_buttons = tk.Frame(root)
frame_buttons.pack(pady=10)

buscar_ws_button = tk.Button(frame_buttons, text="Buscar WS en email", command=buscar_ws_en_email)
buscar_ws_button.pack(side='left', padx=5)

start_button = tk.Button(frame_buttons, text="InicioOperativa", command=set_modes_and_start)
start_button.pack(side='left', padx=5)

stop_button = tk.Button(frame_buttons, text="Parar", command=parar_operativa)
stop_button.pack(side='left', padx=5)

workspaces_frame = tk.Frame(root)
workspaces_frame.pack(fill='both', expand=True, padx=10, pady=10)

log_frame = tk.Frame(root)
log_frame.pack(fill='both', expand=True, padx=10, pady=10)

scrollbar = tk.Scrollbar(log_frame)
scrollbar.pack(side='right', fill='y')

text_log = tk.Text(log_frame, wrap='word', yscrollcommand=scrollbar.set, state='disabled')
text_log.pack(fill='both', expand=True)
scrollbar.config(command=text_log.yview)

root.after(60000, check_automatic_restart)
root.mainloop()


