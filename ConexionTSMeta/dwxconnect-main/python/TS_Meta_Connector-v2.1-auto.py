import math
<<<<<<< HEAD
=======
import os
>>>>>>> 7d709c099e307ef42f68df025c33187e9dfe813b
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import time
import imaplib
import email
from email.header import decode_header
import re
import threading
from datetime import datetime
from time import sleep
from datetime import timezone, timedelta

from api.dwx_client import dwx_client
<<<<<<< HEAD
=======
from config import load_account_config
>>>>>>> 7d709c099e307ef42f68df025c33187e9dfe813b

######################################
# Función de cálculo de Money Management
######################################
def calculaMM_DesdeCuentaTS(processor, CapitalTS, ContratosTS, BigPointValueTS, BigPointValueDWX, Precio, LotesCalculoRiesgo=0.01):
    account_equity = processor.dwx.account_info['equity']
    account_currency = processor.dwx.account_info['currency']

    print(f"Operando en la cuenta con divisa: {account_currency}")

    # Convertir capital si la cuenta está en EUR
    if account_currency == "EUR":
        if Precio > 0:
            CapitalTS = CapitalTS / Precio
        else:
            print("Precio EURUSD inválido, no se puede convertir el capital. Usando CapitalTS tal cual.")
    elif account_currency == "USD":
        pass
    else:
        print("Cuenta en divisa desconocida, no se realiza conversión de capital.")

    if CapitalTS * BigPointValueDWX != 0:
        lotes_no_redondear = (account_equity * BigPointValueTS * ContratosTS) / (CapitalTS * BigPointValueDWX)
    else:
        lotes_no_redondear = LotesCalculoRiesgo

    lot_step = 0.01
    lotes_rounded = math.floor(lotes_no_redondear / lot_step) * lot_step

    if lotes_rounded < lot_step:
        lotes_rounded = lot_step

    print(f"Lotes sin redondear: {lotes_no_redondear}, Lotes redondeados (floor): {lotes_rounded}")

    return lotes_rounded

######################################
# Clase para procesar ticks
######################################
class tick_processor():
    def __init__(self, MT_directory_path, 
                 sleep_delay=0.005,
                 max_retry_command_seconds=10,
                 verbose=True):

        self.open_test_trades = False
        self.last_open_time = datetime.now(timezone.utc)
        self.last_modification_time = datetime.now(timezone.utc)
        self.MT_directory_path = MT_directory_path

        self.dwx = dwx_client(self, MT_directory_path, sleep_delay, 
                              max_retry_command_seconds, verbose=verbose)
        sleep(1)
        self.dwx.start()        
        print("Account info:", self.dwx.account_info)

        # Suscribirse a EURUSD para el precio de conversión
        self.dwx.subscribe_symbols(['EURUSD'])

        self.eurusd_price = None

    def on_tick(self, symbol, bid, ask):
        if symbol == "EURUSD":
            mid_price = (bid + ask) / 2.0
            self.eurusd_price = mid_price

    def on_bar_data(self, symbol, time_frame, time, open_price, high, low, close_price, tick_volume):
        pass

    def on_historic_data(self, symbol, time_frame, data):
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

######################################
# Variables globales
######################################
IMAP_SERVER = 'imap.gmail.com'
<<<<<<< HEAD
EMAIL_ACCOUNT = 'cuentareceptoraordenes@gmail.com'
=======
EMAIL_ACCOUNT = 'recepcionordenes@gmail.com'
>>>>>>> 7d709c099e307ef42f68df025c33187e9dfe813b
PASSWORD = 'password'

workspace_modes = {}
running = False
thread_loop = None

<<<<<<< HEAD
all_workspaces_dict = {"10-Operativa-AS1" : "Corto", "10-Operativa-AS2": "Corto", "10-Operativa-AS3": "Corto", "10-Operativa-AS4" : "Corto", "10-Operativa-AS5": "Corto"}
=======
#all_workspaces_dict = {"10-Operativa-AS1" : "Corto", "10-Operativa-AS2": "Corto", "10-Operativa-AS3": "Corto", "10-Operativa-AS4" : "Corto", "10-Operativa-AS5": "Corto"}
# Load account specific configuration
account_cfg = load_account_config(os.environ.get('TS_ACCOUNT'))

# Mapping of workspace name to default mode
all_workspaces_dict = account_cfg.get('workspaces', {})
>>>>>>> 7d709c099e307ef42f68df025c33187e9dfe813b
AUTOMATIC_RESTART_TIME = "23:59" #OJO!! SI OPERAMOS EN SERVIDOR CON HORA DE NUEVA YORK: 17:15
last_restart_date = None

processor_mt4 = None
processor_mt5 = None

######################################
# Funciones auxiliares
######################################
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

######################################
# Procesar emails y órdenes
######################################
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

            plataforma = platform_var.get()
            global processor_mt4, processor_mt5
            targets = []

            if plataforma == "MT4" and processor_mt4 is not None:
                targets.append(processor_mt4)
            elif plataforma == "MT5" and processor_mt5 is not None:
                targets.append(processor_mt5)
            elif plataforma == "Ambos":
                if processor_mt4 is not None:
                    targets.append(processor_mt4)
                if processor_mt5 is not None:
                    targets.append(processor_mt5)

            if not targets:
                log_message("No hay procesador activo para la plataforma seleccionada.")
                return

            def map_symbol_to_darwinex(instr):
                if instr == "NQ":
                    return "NDX"
                elif instr == "GC":
                    return "XAUUSD"
                return instr

            def big_point_value_ts(instr):
                if instr == "NQ":
                    return 20
                elif instr == "GC":
                    return 100
                return 1

            def big_point_value_dwx(instr):
                if instr == "NQ":
                    return 10
                elif instr == "GC":
                    return 100
                return 1

            action_ = order_data['action']
            quantity_ = float(order_data['quantity'])
            capital_ts = float(order_data['capital'])
            instrument_ts = order_data['instrument']
            modo_ = order_data['modo']
            workspace_ = order_data['workspace']

            symbol = map_symbol_to_darwinex(instrument_ts)
            bpv_ts = big_point_value_ts(instrument_ts)
            bpv_dwx = big_point_value_dwx(instrument_ts)

            price = 0
            comment = workspace_

            for processor in targets:
                eurusd_rate = processor.eurusd_price if processor.eurusd_price is not None else 1.0
                calculated_lots = calculaMM_DesdeCuentaTS(processor, capital_ts, quantity_, bpv_ts, bpv_dwx, eurusd_rate)

                def get_open_order_by_workspace(dwx, wsp):
                    for ticket, order_info in dwx.open_orders.items():
                        if order_info['comment'] == wsp:
                            return ticket, order_info
                    return None, None

                ticket_existing, existing_order = get_open_order_by_workspace(processor.dwx, workspace_)

                def close_order_if_exists(proc, ticket):
                    if ticket is not None and existing_order is not None:
                        existing_lots = existing_order['lots']
                        proc.dwx.close_order(ticket, lots=existing_lots)
                        print(f"Cerrada posición existente del workspace {workspace_} en {plataforma}")
                        return True
                    return False

                if modo_ == "Largo":
                    if action_ == "Buy":
                        if ticket_existing is None:
                            processor.dwx.open_order(symbol=symbol, order_type='buy', price=price, lots=calculated_lots, comment=comment)
                            print(f"[{plataforma}] Abrimos BUY {calculated_lots} {symbol} para workspace {workspace_}")
                        else:
                            if existing_order['type'] == 'sell':
                                close_order_if_exists(processor, ticket_existing)
                                processor.dwx.open_order(symbol=symbol, order_type='buy', price=price, lots=calculated_lots, comment=comment)
                                print(f"[{plataforma}] Cerramos SELL y abrimos BUY {calculated_lots} {symbol} para workspace {workspace_}")
                            else:
                                print(f"[{plataforma}] Ya existe un BUY abierto para {workspace_}, no hacemos nada.")
                    elif action_ == "Sell":
                        if ticket_existing is not None and existing_order['type'] == 'buy':
                            close_order_if_exists(processor, ticket_existing)
                        else:
                            print(f"[{plataforma}] No hay BUY que cerrar para {workspace_}")
                elif modo_ == "Corto":
                    if action_ == "Sell":
                        if ticket_existing is None:
                            processor.dwx.open_order(symbol=symbol, order_type='sell', price=price, lots=calculated_lots, comment=comment)
                            print(f"[{plataforma}] Abrimos SELL {calculated_lots} {symbol} para workspace {workspace_}")
                        else:
                            if existing_order['type'] == 'buy':
                                close_order_if_exists(processor, ticket_existing)
                                processor.dwx.open_order(symbol=symbol, order_type='sell', price=price, lots=calculated_lots, comment=comment)
                                print(f"[{plataforma}] Cerramos BUY y abrimos SELL {calculated_lots} {symbol} para workspace {workspace_}")
                            else:
                                print(f"[{plataforma}] Ya existe un SELL abierto para {workspace_}, no hacemos nada.")
                    elif action_ == "Buy":
                        if ticket_existing is not None and existing_order['type'] == 'sell':
                            close_order_if_exists(processor, ticket_existing)
                        else:
                            print(f"[{plataforma}] No hay SELL que cerrar para {workspace_}")
                else:
                    print(f"[{plataforma}] Modo {modo_} no válido o 'No operar'. No se hace nada.")
        else:
            log_message('No se pudo analizar la información de la orden.')
    else:
        log_message('No se pudo extraer toda la información necesaria del email.')

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
        
        if ws not in all_workspaces_dict.keys():
            all_workspaces_dict[ws] = "No operar"
            #workspace_modes[ws] = "No operar"
            added = True
    

        # if ws not in all_workspaces:
        #     all_workspaces.append(ws)
        #     added = True

    if added:
        log_message("Nuevos workspaces agregados.")
    else:
        log_message("No se encontraron nuevos workspaces o ya estaban agregados.")

    mostrar_workspaces_en_frame()

def eliminar_workspace(ws):
    # if ws in all_workspaces:
    #     all_workspaces.remove(ws)
    #     mostrar_workspaces_en_frame()
    #     log_message(f"Workspace {ws} eliminado de la lista.")
    if ws in all_workspaces_dict:
        del all_workspaces_dict[ws]
        log_message(f"Workspace {ws} eliminado del diccionario.")        
        mostrar_workspaces_en_frame()
        


def mostrar_workspaces_en_frame():
    for w in workspaces_frame.winfo_children():
        w.destroy()

    # if not all_workspaces:
    #     tk.Label(workspaces_frame, text="No se encontraron workspaces.").pack()
    #     return
    if not all_workspaces_dict.keys():
        tk.Label(workspaces_frame, text="No se encontraron workspaces.").pack()
        return

    #for ws in all_workspaces:
    for ws in all_workspaces_dict.keys():
        fr = tk.Frame(workspaces_frame)
        fr.pack(anchor='w', pady=2, fill='x')

        lbl = tk.Label(fr, text=ws)
        lbl.pack(side='left', padx=5)
        
        combo = ttk.Combobox(fr, values=["Largo", "Corto", "No operar"])
        #if ws in all_workspaces:
        if ws in all_workspaces_dict.keys():
            combo.set(workspace_modes.get(ws, all_workspaces_dict[ws]))
        else: 
            combo.set(workspace_modes.get(ws, "No operar"))

        combo.pack(side='left')
        combo._workspace = ws

        btn_del = tk.Button(fr, text="Eliminar", command=lambda w=ws: eliminar_workspace(w))
        btn_del.pack(side='left', padx=5)

        btn_sync = tk.Button(fr, text="Sincronizar", command=lambda w=ws, c=combo: sincronizar_workspace(w, c.get()))
        btn_sync.pack(side='left', padx=5)

def sincronizar_workspace(workspace, modo):
    cantidad = simpledialog.askstring("Sincronizar", f"Introduce la cantidad de contratos abiertos externamente para {workspace}:", parent=root)
    if cantidad is None:
        return
    try:
        cantidad = float(cantidad)
    except ValueError:
        messagebox.showerror("Error", "La cantidad debe ser un número.")
        return

    instrumento_ts = simpledialog.askstring("Sincronizar", f"Introduce el instrumento TS (ej. NQ, GC) para {workspace}:", parent=root)
    if instrumento_ts is None or instrumento_ts.strip() == "":
        messagebox.showerror("Error", "Debes introducir un instrumento.")
        return
    instrumento_ts = instrumento_ts.strip().upper()

    if modo == "No operar":
        messagebox.showinfo("Info", "El modo del workspace es 'No operar', no se hará nada.")
        return

    plataforma = platform_var.get()

    targets = []
    if plataforma == "MT4" and processor_mt4 is not None:
        targets.append(processor_mt4)
    elif plataforma == "MT5" and processor_mt5 is not None:
        targets.append(processor_mt5)
    elif plataforma == "Ambos":
        if processor_mt4 is not None:
            targets.append(processor_mt4)
        if processor_mt5 is not None:
            targets.append(processor_mt5)

    if not targets:
        messagebox.showinfo("Info", "No hay plataformas iniciadas para sincronizar.")
        return

    capital = entry_capital.get().strip()
    if not capital:
        capital = "0"
    capital = float(capital)

    def map_symbol_to_darwinex(instrument_ts):
        if instrument_ts == "NQ":
            return "NDX"
        elif instrument_ts == "GC":
            return "XAUUSD"
        return instrument_ts

    def big_point_value_ts(instrument_ts):
        if instrument_ts == "NQ":
            return 20
        elif instrument_ts == "GC":
            return 100
        return 1

    def big_point_value_dwx(instrument_ts):
        if instrument_ts == "NQ":
            return 10
        elif instrument_ts == "GC":
            return 100
        return 1

    symbol = map_symbol_to_darwinex(instrumento_ts)
    bpv_ts = big_point_value_ts(instrumento_ts)
    bpv_dwx = big_point_value_dwx(instrumento_ts)

    action = "Buy" if modo == "Largo" else "Sell"
    price = 0
    comment = workspace

    for processor in targets:
        eurusd_rate = processor.eurusd_price if processor.eurusd_price is not None else 1.0
        lots = calculaMM_DesdeCuentaTS(processor, capital, cantidad, bpv_ts, bpv_dwx, eurusd_rate)
        order_type = 'buy' if action == 'Buy' else 'sell'

        processor.dwx.open_order(symbol=symbol, order_type=order_type, price=price, lots=lots, comment=comment)
        log_message(f"Sincronizado {modo} en {workspace}. Abrimos {order_type.upper()} {lots} {symbol}. (Instrumento TS: {instrumento_ts})")

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
    global running, thread_loop, processor_mt4, processor_mt5

    if running:
        if not automatic:
            messagebox.showinfo("Info", "La operativa ya está en marcha.")
        return

    plataforma = platform_var.get()
    mt4_path = entry_mt4_path.get().strip()
    mt5_path = entry_mt5_path.get().strip()

    if processor_mt4:
        #processor_mt4.dwx.stop()
        processor_mt4 = None
    if processor_mt5:
        #processor_mt5.dwx.stop()
        processor_mt5 = None

    if plataforma == "MT4":
        if mt4_path:
            processor_mt4 = tick_processor(mt4_path)
        else:
            log_message("No se estableció ruta para MT4.")
    elif plataforma == "MT5":
        if mt5_path:
            processor_mt5 = tick_processor(mt5_path)
        else:
            log_message("No se estableció ruta para MT5.")
    elif plataforma == "Ambos":
        if mt4_path:
            processor_mt4 = tick_processor(mt4_path)
        else:
            log_message("No se estableció ruta para MT4.")
        if mt5_path:
            processor_mt5 = tick_processor(mt5_path)
        else:
            log_message("No se estableció ruta para MT5.")
    else:
        log_message("Plataforma no válida.")
        return

    running = True
    thread_loop = threading.Thread(target=main_loop, daemon=True)
    thread_loop.start()
    log_message("Operativa iniciada. Escuchando nuevos correos...")
    if not automatic:
        messagebox.showinfo("Info", "Operativa iniciada. Escuchando nuevos correos...")

def parar_operativa(automatic=False):
    global running, processor_mt4, processor_mt5
    if running:
        running = False
        if processor_mt4:
            #processor_mt4.dwx.stop()
            processor_mt4 = None
        if processor_mt5:
            #processor_mt5.dwx.stop()
            processor_mt5 = None
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
    #if nuevo_ws and nuevo_ws not in all_workspaces:
    #   all_workspaces.append(nuevo_ws)
    if nuevo_ws and nuevo_ws not in all_workspaces_dict.keys():
        all_workspaces_dict[nuevo_ws] = "No operar"

        mostrar_workspaces_en_frame()
        entry_workspace.delete(0, tk.END)
        log_message(f"Workspace {nuevo_ws} agregado manualmente.")
    #elif nuevo_ws in all_workspaces:
    elif nuevo_ws in all_workspaces_dict.keys():
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

platform_frame = tk.Frame(root)
platform_frame.pack(pady=10, padx=10, fill='x')

tk.Label(platform_frame, text="Plataforma:").pack(side='left', padx=5)
platform_var = tk.StringVar()
platform_combo = ttk.Combobox(platform_frame, textvariable=platform_var, values=["MT4", "MT5", "Ambos"])
platform_combo.set("MT4")  
platform_combo.pack(side='left', padx=5)

tk.Label(platform_frame, text="Ruta MT4:").pack(side='left', padx=5)
entry_mt4_path = tk.Entry(platform_frame, width=50)
#entry_mt4_path.insert(0, r"C:\Path\To\MT4\MQL4\Files")
<<<<<<< HEAD
entry_mt4_path.insert(0, r"C:\Users\Alberto\AppData\Roaming\MetaQuotes\Terminal\F0DEBE9BA569B53E62B00FE1DE068813\MQL4\Files")
=======
#entry_mt4_path.insert(0, r"C:\Users\Alberto\AppData\Roaming\MetaQuotes\Terminal\F0DEBE9BA569B53E62B00FE1DE068813\MQL4\Files")
entry_mt4_path.insert(0, account_cfg.get('mt4_path', ''))
>>>>>>> 7d709c099e307ef42f68df025c33187e9dfe813b

entry_mt4_path.pack(side='left', padx=5)

tk.Label(platform_frame, text="Ruta MT5:").pack(side='left', padx=5)
entry_mt5_path = tk.Entry(platform_frame, width=50)
<<<<<<< HEAD
entry_mt5_path.insert(0, r"C:\Users\Alberto\AppData\Roaming\MetaQuotes\Terminal\6C3C6A11D1C3791DD4DBF45421BF8028\MQL5\Files")
=======
#entry_mt5_path.insert(0, r"C:\Users\Alberto\AppData\Roaming\MetaQuotes\Terminal\6C3C6A11D1C3791DD4DBF45421BF8028\MQL5\Files")
entry_mt5_path.insert(0, account_cfg.get('mt5_path', ''))
>>>>>>> 7d709c099e307ef42f68df025c33187e9dfe813b
entry_mt5_path.pack(side='left', padx=5)

frame_buttons = tk.Frame(root)
frame_buttons.pack(pady=10)

buscar_ws_button = tk.Button(frame_buttons, text="Buscar WS en email", command=buscar_ws_en_email)
buscar_ws_button.pack(side='left', padx=5)

#boton display workspaces
display_ws_button = tk.Button(frame_buttons, text="Mostrar lista WS", command=mostrar_workspaces_en_frame)
display_ws_button.pack(side='left', padx=5)

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

# mostrar los workspaces
mostrar_workspaces_en_frame()

# iniciamos operativa automática
set_modes_and_start(automatic=True)  
root.after(60000, check_automatic_restart)
root.mainloop()
