import math
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import time
import imaplib
import email
from email.header import decode_header
import re
import threading
from datetime import datetime, timezone, timedelta
import logging

# Se asume que existe la implementación de dwx_client en el paquete correspondiente.
from api.dwx_client import dwx_client

#######################################
# Configuración del logger
#######################################
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("operativa.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

#######################################
# Constantes globales
#######################################
IMAP_SERVER = 'imap.gmail.com'
EMAIL_ACCOUNT = 'notificacionesdarwinsyo@gmail.com'
PASSWORD = 'ktxzeqagsklsxolp'
AUTOMATIC_RESTART_TIME = "23:59"  # Hora por defecto de reinicio automático

#######################################
# Clase para el Money Management
#######################################
class MoneyManagement:
    @staticmethod
    def calcula_lotes(processor, capital_ts, contratos_ts, bpv_ts, bpv_dwx, precio_conversion, lote_min=0.01):
        """
        Calcula los lotes a operar en base al money management.
        """
        try:
            account_equity = processor.dwx.account_info.get('equity', 0)
            account_currency = processor.dwx.account_info.get('currency', 'USD')
            logger.debug(f"Cuenta operando en {account_currency}")

            # Conversión de capital si la cuenta está en EUR
            if account_currency == "EUR":
                if precio_conversion > 0:
                    capital_ts = capital_ts / precio_conversion
                else:
                    logger.error("Precio EURUSD inválido para conversión de capital.")
            # En USD se usa capital_ts directamente

            if capital_ts * bpv_dwx != 0:
                lotes_sin_redondear = (account_equity * bpv_ts * contratos_ts) / (capital_ts * bpv_dwx)
            else:
                lotes_sin_redondear = lote_min

            lotes_redondeados = math.floor(lotes_sin_redondear / lote_min) * lote_min
            if lotes_redondeados < lote_min:
                lotes_redondeados = lote_min

            logger.debug(f"Lotes sin redondear: {lotes_sin_redondear}, Lotes redondeados: {lotes_redondeados}")
            return lotes_redondeados
        except Exception as e:
            logger.exception("Error en cálculo de money management")
            return lote_min

#######################################
# Clase para procesar ticks desde MT
#######################################
class TickProcessor:
    def __init__(self, mt_directory_path, sleep_delay=0.005, max_retry_command_seconds=10, verbose=True):
        self.MT_directory_path = mt_directory_path
        self.dwx = dwx_client(self, mt_directory_path, sleep_delay, max_retry_command_seconds, verbose=verbose)
        time.sleep(1)
        self.dwx.start()
        logger.info(f"Información de la cuenta: {self.dwx.account_info}")
        # Suscribirse a EURUSD para la tasa de conversión
        self.dwx.subscribe_symbols(['EURUSD'])
        self.eurusd_price = None

    def on_tick(self, symbol, bid, ask):
        if symbol == "EURUSD":
            self.eurusd_price = (bid + ask) / 2.0

    def on_message(self, message):
        if message.get('type') == 'ERROR':
            logger.error(f"ERROR | {message.get('error_type')} | {message.get('description')}")
        elif message.get('type') == 'INFO':
            logger.info(f"INFO | {message.get('message')}")

    def on_order_event(self):
        logger.info(f"Evento de orden. Órdenes abiertas: {len(self.dwx.open_orders)}")

    def stop(self):
        self.dwx.stop()

#######################################
# Clase para procesar emails y extraer órdenes
#######################################
class EmailProcessor:
    def __init__(self, imap_server, email_account, password):
        self.imap_server = imap_server
        self.email_account = email_account
        self.password = password

    def conectar(self):
        try:
            mail = imaplib.IMAP4_SSL(self.imap_server)
            mail.login(self.email_account, self.password)
            return mail
        except Exception as e:
            logger.exception("Error conectando al servidor IMAP")
            return None

    def leer_emails_no_leidos(self):
        mail = self.conectar()
        if not mail:
            return []
        try:
            mail.select('inbox')
            status, mensajes = mail.search(None, '(UNSEEN FROM "notificacionesdarwinsyo@gmail.com")')
            if status != 'OK':
                logger.error("No se pudieron buscar emails")
                return []
            emails = []
            for num in mensajes[0].split():
                status, datos = mail.fetch(num, '(RFC822)')
                if status == 'OK':
                    emails.append((num, datos[0][1]))
                    mail.store(num, '+FLAGS', '\\Seen')
            return emails
        except Exception as e:
            logger.exception("Error leyendo emails")
            return []
        finally:
            mail.close()
            mail.logout()

    def extraer_datos_orden(self, email_body):
        lines = email_body.strip().splitlines()
        order_info = None
        occurred = None
        signal = None
        interval = None
        workspace = None

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
                order_data = {
                    'action': action,
                    'quantity': float(quantity),
                    'instrument': instrument,
                    'price': price,
                    'order_type': order_type.strip(),
                    'occurred': occurred,
                    'signal': signal,
                    'interval': interval,
                    'workspace': ws_name
                }
                logger.info(f"Orden extraída: {order_data}")
                return order_data
        logger.warning("No se pudieron extraer todos los datos de la orden")
        return None

    def procesar_email(self, raw_email):
        try:
            email_message = email.message_from_bytes(raw_email)
            subject, encoding = decode_header(email_message['Subject'])[0]
            if isinstance(subject, bytes):
                subject = subject.decode(encoding if encoding else 'utf-8')

            logger.info(f"Asunto del email: {subject}")
            if 'Strategy Filled Order' in subject:
                if email_message.is_multipart():
                    for part in email_message.walk():
                        content_type = part.get_content_type()
                        content_disposition = str(part.get('Content-Disposition'))
                        if content_type == 'text/plain' and 'attachment' not in content_disposition:
                            email_body = part.get_payload(decode=True).decode()
                            return self.extraer_datos_orden(email_body)
                else:
                    email_body = email_message.get_payload(decode=True).decode()
                    return self.extraer_datos_orden(email_body)
            else:
                logger.info("Email no es una notificación de orden válida.")
        except Exception as e:
            logger.exception("Error procesando el email")
        return None

#######################################
# Clase para ejecutar órdenes en MetaTrader
#######################################
class OrderExecutor:
    """
    Ejecuta las órdenes en la(s) plataforma(s) MetaTrader.
    """
    def __init__(self, platforma, processor_mt4=None, processor_mt5=None):
        self.platforma = platforma
        self.processor_mt4 = processor_mt4
        self.processor_mt5 = processor_mt5

    @staticmethod
    def map_symbol(instrument_ts):
        mapping = {
            "NQ": "NDX",
            "GC": "XAUUSD"
        }
        return mapping.get(instrument_ts, instrument_ts)

    @staticmethod
    def big_point_value_ts(instrument_ts):
        mapping = {
            "NQ": 20,
            "GC": 100
        }
        return mapping.get(instrument_ts, 1)

    @staticmethod
    def big_point_value_dwx(instrument_ts):
        mapping = {
            "NQ": 10,
            "GC": 100
        }
        return mapping.get(instrument_ts, 1)

    def get_targets(self):
        targets = []
        if self.platforma == "MT4" and self.processor_mt4 is not None:
            targets.append(self.processor_mt4)
        elif self.platforma == "MT5" and self.processor_mt5 is not None:
            targets.append(self.processor_mt5)
        elif self.platforma == "Ambos":
            if self.processor_mt4 is not None:
                targets.append(self.processor_mt4)
            if self.processor_mt5 is not None:
                targets.append(self.processor_mt5)
        return targets

    def execute_order(self, order_data, capital):
        targets = self.get_targets()
        if not targets:
            logger.error("No hay procesadores activos para la plataforma seleccionada.")
            return

        instrument_ts = order_data['instrument']
        symbol = self.map_symbol(instrument_ts)
        bpv_ts = self.big_point_value_ts(instrument_ts)
        bpv_dwx = self.big_point_value_dwx(instrument_ts)
        action = order_data['action']
        quantity = order_data['quantity']
        workspace = order_data['workspace']
        modo = "Largo" if action == "Buy" else "Corto"  # Simplificación

        # Ejecutar la orden en cada plataforma destino
        for processor in targets:
            # Utilizar tasa de EURUSD (si está disponible) para conversión
            eurusd_rate = processor.eurusd_price if processor.eurusd_price is not None else 1.0
            calculated_lots = MoneyManagement.calcula_lotes(processor, capital, quantity, bpv_ts, bpv_dwx, eurusd_rate)
            price = 0  # Precio de mercado
            comment = workspace

            # Verificar si ya existe orden abierta para este workspace
            ticket, existing_order = self.get_open_order(processor, workspace)

            if modo == "Largo":
                if action == "Buy":
                    if ticket is None:
                        processor.dwx.open_order(symbol=symbol, order_type='buy', price=price, lots=calculated_lots, comment=comment)
                        logger.info(f"[{self.platforma}] Abrir BUY {calculated_lots} {symbol} para {workspace}")
                    else:
                        if existing_order['type'] == 'sell':
                            processor.dwx.close_order(ticket, lots=existing_order['lots'])
                            processor.dwx.open_order(symbol=symbol, order_type='buy', price=price, lots=calculated_lots, comment=comment)
                            logger.info(f"[{self.platforma}] Cambio de SELL a BUY en {workspace}")
                        else:
                            logger.info(f"[{self.platforma}] Ya existe BUY en {workspace}, sin acción.")
                elif action == "Sell":
                    if ticket is not None and existing_order['type'] == 'buy':
                        processor.dwx.close_order(ticket, lots=existing_order['lots'])
                        logger.info(f"[{self.platforma}] Cerrada posición BUY en {workspace}")
                    else:
                        logger.info(f"[{self.platforma}] No hay BUY para cerrar en {workspace}")
            elif modo == "Corto":
                if action == "Sell":
                    if ticket is None:
                        processor.dwx.open_order(symbol=symbol, order_type='sell', price=price, lots=calculated_lots, comment=comment)
                        logger.info(f"[{self.platforma}] Abrir SELL {calculated_lots} {symbol} para {workspace}")
                    else:
                        if existing_order['type'] == 'buy':
                            processor.dwx.close_order(ticket, lots=existing_order['lots'])
                            processor.dwx.open_order(symbol=symbol, order_type='sell', price=price, lots=calculated_lots, comment=comment)
                            logger.info(f"[{self.platforma}] Cambio de BUY a SELL en {workspace}")
                        else:
                            logger.info(f"[{self.platforma}] Ya existe SELL en {workspace}, sin acción.")
                elif action == "Buy":
                    if ticket is not None and existing_order['type'] == 'sell':
                        processor.dwx.close_order(ticket, lots=existing_order['lots'])
                        logger.info(f"[{self.platforma}] Cerrada posición SELL en {workspace}")
                    else:
                        logger.info(f"[{self.platforma}] No hay SELL para cerrar en {workspace}")

    def get_open_order(self, processor, workspace):
        """
        Verifica si ya existe una orden abierta para el workspace dado.
        """
        for ticket, order_info in processor.dwx.open_orders.items():
            if order_info.get('comment') == workspace:
                return ticket, order_info
        return None, None

#######################################
# Clase que orquesta la interfaz gráfica y la operativa
#######################################
class TradeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Operativa con Emails para MetaTrader")
        self.running = False
        self.processor_mt4 = None
        self.processor_mt5 = None
        self.email_processor = EmailProcessor(IMAP_SERVER, EMAIL_ACCOUNT, PASSWORD)
        self.order_executor = None
        self.all_workspaces = {}  # Diccionario: workspace -> modo ("Largo", "Corto", "No operar")
        self.last_restart_date = None

        self.create_widgets()
        # Inicia el chequeo periódico para reinicio automático
        self.root.after(60000, self.check_automatic_restart)

    def create_widgets(self):
        top_frame = tk.Frame(self.root)
        top_frame.pack(pady=10, padx=10, fill='x')

        self.entry_workspace = tk.Entry(top_frame)
        self.entry_workspace.pack(side='left', padx=5)
        btn_add_ws = tk.Button(top_frame, text="Añadir Workspace", command=self.agregar_workspace)
        btn_add_ws.pack(side='left', padx=5)

        hora_frame = tk.Frame(self.root)
        hora_frame.pack(pady=10, padx=10, fill='x')
        tk.Label(hora_frame, text="Hora de reinicio (HH:MM):").pack(side='left', padx=5)
        self.entry_hora_reinicio = tk.Entry(hora_frame, width=10)
        self.entry_hora_reinicio.insert(0, AUTOMATIC_RESTART_TIME)
        self.entry_hora_reinicio.pack(side='left', padx=5)
        btn_actualizar_hora = tk.Button(hora_frame, text="Actualizar Hora Reinicio", command=self.actualizar_hora_reinicio)
        btn_actualizar_hora.pack(side='left', padx=5)

        capital_frame = tk.Frame(self.root)
        capital_frame.pack(pady=10, padx=10, fill='x')
        tk.Label(capital_frame, text="Capital:").pack(side='left', padx=5)
        self.entry_capital = tk.Entry(capital_frame, width=10)
        self.entry_capital.insert(0, "20000000")
        self.entry_capital.pack(side='left', padx=5)

        platform_frame = tk.Frame(self.root)
        platform_frame.pack(pady=10, padx=10, fill='x')
        tk.Label(platform_frame, text="Plataforma:").pack(side='left', padx=5)
        self.platform_var = tk.StringVar()
        self.platform_combo = ttk.Combobox(platform_frame, textvariable=self.platform_var, values=["MT4", "MT5", "Ambos"])
        self.platform_combo.set("MT5")
        self.platform_combo.pack(side='left', padx=5)

        tk.Label(platform_frame, text="Ruta MT4:").pack(side='left', padx=5)
        self.entry_mt4_path = tk.Entry(platform_frame, width=50)
        self.entry_mt4_path.insert(0, r"C:\Path\To\MT4\MQL4\Files")
        self.entry_mt4_path.pack(side='left', padx=5)

        tk.Label(platform_frame, text="Ruta MT5:").pack(side='left', padx=5)
        self.entry_mt5_path = tk.Entry(platform_frame, width=50)
        self.entry_mt5_path.insert(0, r"C:\Path\To\MT5\MQL5\Files")
        self.entry_mt5_path.pack(side='left', padx=5)

        frame_buttons = tk.Frame(self.root)
        frame_buttons.pack(pady=10)
        btn_buscar_ws = tk.Button(frame_buttons, text="Buscar WS en email", command=self.buscar_workspaces)
        btn_buscar_ws.pack(side='left', padx=5)
        btn_iniciar = tk.Button(frame_buttons, text="Iniciar Operativa", command=self.iniciar_operativa)
        btn_iniciar.pack(side='left', padx=5)
        btn_parar = tk.Button(frame_buttons, text="Parar", command=self.parar_operativa)
        btn_parar.pack(side='left', padx=5)

        self.frame_workspaces = tk.Frame(self.root)
        self.frame_workspaces.pack(fill='both', expand=True, padx=10, pady=10)

        log_frame = tk.Frame(self.root)
        log_frame.pack(fill='both', expand=True, padx=10, pady=10)
        self.text_log = tk.Text(log_frame, wrap='word', state='disabled')
        scrollbar = tk.Scrollbar(log_frame, command=self.text_log.yview)
        scrollbar.pack(side='right', fill='y')
        self.text_log.config(yscrollcommand=scrollbar.set)
        self.text_log.pack(fill='both', expand=True)

    def log_message(self, msg):
        self.text_log.config(state='normal')
        self.text_log.insert(tk.END, msg + "\n")
        self.text_log.see(tk.END)
        self.text_log.config(state='disabled')
        logger.info(msg)

    def agregar_workspace(self):
        nuevo_ws = self.entry_workspace.get().strip()
        if nuevo_ws and nuevo_ws not in self.all_workspaces:
            self.all_workspaces[nuevo_ws] = "No operar"  # Por defecto
            self.mostrar_workspaces()
            self.entry_workspace.delete(0, tk.END)
            self.log_message(f"Workspace {nuevo_ws} agregado manualmente.")
        elif nuevo_ws in self.all_workspaces:
            messagebox.showinfo("Info", "El workspace ya existe.")
            self.log_message(f"Workspace {nuevo_ws} ya existe.")
        else:
            self.log_message("No se ingresó ningún workspace.")

    def mostrar_workspaces(self):
        for widget in self.frame_workspaces.winfo_children():
            widget.destroy()
        if not self.all_workspaces:
            tk.Label(self.frame_workspaces, text="No se encontraron workspaces.").pack()
            return
        for ws, modo in self.all_workspaces.items():
            fr = tk.Frame(self.frame_workspaces)
            fr.pack(anchor='w', pady=2, fill='x')
            lbl = tk.Label(fr, text=ws)
            lbl.pack(side='left', padx=5)
            combo = ttk.Combobox(fr, values=["Largo", "Corto", "No operar"])
            combo.set(modo)
            combo.pack(side='left')
            combo._workspace = ws
            btn_del = tk.Button(fr, text="Eliminar", command=lambda w=ws: self.eliminar_workspace(w))
            btn_del.pack(side='left', padx=5)
            btn_sync = tk.Button(fr, text="Sincronizar", command=lambda w=ws, c=combo: self.sincronizar_workspace(w, c.get()))
            btn_sync.pack(side='left', padx=5)

    def eliminar_workspace(self, ws):
        if ws in self.all_workspaces:
            del self.all_workspaces[ws]
            self.mostrar_workspaces()
            self.log_message(f"Workspace {ws} eliminado.")

    def sincronizar_workspace(self, workspace, modo):
        cantidad = simpledialog.askstring("Sincronizar", f"Introduce la cantidad de contratos abiertos para {workspace}:", parent=self.root)
        if cantidad is None:
            return
        try:
            cantidad = float(cantidad)
        except ValueError:
            messagebox.showerror("Error", "La cantidad debe ser un número.")
            return
        instrumento_ts = simpledialog.askstring("Sincronizar", f"Introduce el instrumento TS (ej. NQ, GC) para {workspace}:", parent=self.root)
        if instrumento_ts is None or instrumento_ts.strip() == "":
            messagebox.showerror("Error", "Debes introducir un instrumento.")
            return
        instrumento_ts = instrumento_ts.strip().upper()
        if modo == "No operar":
            messagebox.showinfo("Info", "El workspace está en modo 'No operar'.")
            return
        plataforma = self.platform_var.get()
        capital = self.entry_capital.get().strip()
        try:
            capital = float(capital)
        except ValueError:
            messagebox.showerror("Error", "Capital inválido.")
            return
        executor = OrderExecutor(plataforma, self.processor_mt4, self.processor_mt5)
        # Construir una orden de sincronización
        order_data = {
            'action': "Buy" if modo == "Largo" else "Sell",
            'quantity': cantidad,
            'instrument': instrumento_ts,
            'price': 0,
            'order_type': '',
            'occurred': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'signal': 'Sync',
            'interval': '',
            'workspace': workspace
        }
        executor.execute_order(order_data, capital)
        self.log_message(f"Sincronizado {modo} en {workspace} con instrumento {instrumento_ts}.")

    def buscar_workspaces(self):
        mail = self.email_processor.conectar()
        if not mail:
            self.log_message("Error conectando para buscar workspaces.")
            return
        try:
            mail.select('inbox')
            status, mensajes = mail.search(None, 'ALL')
            if status != 'OK':
                self.log_message("Error buscando emails.")
                return
            nuevos_ws = {}
            for num in mensajes[0].split():
                status, datos = mail.fetch(num, '(RFC822)')
                if status == 'OK':
                    raw_email = datos[0][1]
                    order_data = self.email_processor.procesar_email(raw_email)
                    if order_data:
                        ws = order_data.get('workspace')
                        if ws and ws not in self.all_workspaces:
                            nuevos_ws[ws] = "No operar"
            if nuevos_ws:
                self.all_workspaces.update(nuevos_ws)
                self.log_message("Nuevos workspaces agregados desde emails.")
            else:
                self.log_message("No se encontraron nuevos workspaces.")
            self.mostrar_workspaces()
        except Exception as e:
            logger.exception("Error buscando workspaces en emails")
        finally:
            mail.close()
            mail.logout()

    def iniciar_operativa(self):
        if self.running:
            messagebox.showinfo("Info", "Operativa ya está en marcha.")
            return

        plataforma = self.platform_var.get()
        mt4_path = self.entry_mt4_path.get().strip()
        mt5_path = self.entry_mt5_path.get().strip()

        # Detener procesadores anteriores si existen
        if self.processor_mt4:
            self.processor_mt4.stop()
            self.processor_mt4 = None
        if self.processor_mt5:
            self.processor_mt5.stop()
            self.processor_mt5 = None

        if plataforma in ["MT4", "Ambos"] and mt4_path:
            self.processor_mt4 = TickProcessor(mt4_path)
        elif plataforma in ["MT4", "Ambos"]:
            self.log_message("No se estableció ruta para MT4.")

        if plataforma in ["MT5", "Ambos"] and mt5_path:
            self.processor_mt5 = TickProcessor(mt5_path)
        elif plataforma in ["MT5", "Ambos"]:
            self.log_message("No se estableció ruta para MT5.")

        self.running = True
        self.order_executor = OrderExecutor(plataforma, self.processor_mt4, self.processor_mt5)
        # Iniciar un hilo para leer emails periódicamente
        self.thread_loop = threading.Thread(target=self.main_loop, daemon=True)
        self.thread_loop.start()
        self.log_message("Operativa iniciada. Escuchando nuevos correos.")
        messagebox.showinfo("Info", "Operativa iniciada.")

    def parar_operativa(self):
        if self.running:
            self.running = False
            if self.processor_mt4:
                # Si dwx_client no tiene un método stop, no se llama a él
                # self.processor_mt4.dwx.stop()
                self.processor_mt4 = None
            if self.processor_mt5:
                # self.processor_mt5.stop()
                self.processor_mt5 = None
            self.log_message("Operativa detenida.")
            messagebox.showinfo("Info", "Operativa detenida.")
        else:
            self.log_message("Operativa no estaba en marcha.")
            messagebox.showinfo("Info", "Operativa no estaba en marcha.")

    def main_loop(self):
        self.log_message("Iniciando ciclo de lectura de emails.")
        while self.running:
            emails = self.email_processor.leer_emails_no_leidos()
            for num, raw_email in emails:
                order_data = self.email_processor.procesar_email(raw_email)
                if order_data:
                    try:
                        capital = float(self.entry_capital.get().strip())
                    except ValueError:
                        capital = 0
                    self.order_executor.execute_order(order_data, capital)
            time.sleep(5)

    def check_automatic_restart(self):
        now = datetime.now()
        current_time_str = now.strftime("%H:%M")
        current_date = now.date()
        if current_time_str == self.entry_hora_reinicio.get().strip() and (self.last_restart_date != current_date):
            self.log_message("Ejecutando reinicio automático...")
            if self.running:
                self.parar_operativa()
            self.iniciar_operativa()
            self.last_restart_date = current_date
        self.root.after(60000, self.check_automatic_restart)

    def actualizar_hora_reinicio(self):
        nueva_hora = self.entry_hora_reinicio.get().strip()
        if re.match(r"^\d{2}:\d{2}$", nueva_hora):
            global AUTOMATIC_RESTART_TIME
            AUTOMATIC_RESTART_TIME = nueva_hora
            self.log_message(f"Hora de reinicio actualizada a {nueva_hora}")
            messagebox.showinfo("Info", f"Hora de reinicio actualizada a {nueva_hora}")
        else:
            messagebox.showerror("Error", "El formato de la hora debe ser HH:MM")
            self.log_message("Error al actualizar la hora de reinicio: formato inválido.")

#######################################
# Bloque principal de ejecución
#######################################
if __name__ == "__main__":
    root = tk.Tk()
    app = TradeApp(root)
    root.mainloop()
