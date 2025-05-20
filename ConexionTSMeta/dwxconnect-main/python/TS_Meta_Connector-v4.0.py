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
from typing import Dict, List, Optional, Tuple
from api.dwx_client import dwx_client
import logging

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constantes
IMAP_SERVER = 'imap.gmail.com'
EMAIL_ACCOUNT = 'notificacionesdarwinsyo@gmail.com'
PASSWORD = 'ktxzeqagsklsxolp'  # Considerar mover esto a variables de entorno
AUTOMATIC_RESTART_TIME = "23:59"
MIN_LOT_SIZE = 0.01

class Config:
    """Clase para manejar configuraciones y constantes"""
    SYMBOL_MAPPING = {
        "NQ": "NDX",
        "GC": "XAUUSD"
    }
    BIG_POINT_VALUE_TS = {
        "NQ": 20,
        "GC": 100
    }
    BIG_POINT_VALUE_DWX = {
        "NQ": 10,
        "GC": 100
    }

class MoneyManagement:
    """Clase para cálculos de Money Management"""
    @staticmethod
    def calculate_lots(
        processor,
        capital_ts: float,
        contracts_ts: float,
        big_point_value_ts: float,
        big_point_value_dwx: float,
        price: float,
        default_lots: float = 0.01
    ) -> float:
        try:
            account_equity = processor.dwx.account_info.get('equity', 0)
            account_currency = processor.dwx.account_info.get('currency', 'USD')

            # Conversión de capital según divisa
            if account_currency == "EUR" and price > 0:
                capital_ts /= price
            elif account_currency not in ["USD", "EUR"]:
                logger.warning(f"Divisa desconocida: {account_currency}")

            # Cálculo de lotes
            if capital_ts * big_point_value_dwx == 0:
                return default_lots

            lots = (account_equity * big_point_value_ts * contracts_ts) / (capital_ts * big_point_value_dwx)
            lots_rounded = max(math.floor(lots / MIN_LOT_SIZE) * MIN_LOT_SIZE, MIN_LOT_SIZE)
            
            logger.info(f"Lotes calculados: {lots:.4f} -> Redondeados: {lots_rounded:.2f}")
            return lots_rounded
            
        except Exception as e:
            logger.error(f"Error en cálculo de lotes: {str(e)}")
            return default_lots

class TickProcessor:
    """Clase para procesar ticks y manejar órdenes"""
    def __init__(self, mt_directory_path: str, sleep_delay: float = 0.005,
                 max_retry_command_seconds: int = 10, verbose: bool = True):
        self.mt_directory_path = mt_directory_path
        self.dwx = dwx_client(self, mt_directory_path, sleep_delay,
                            max_retry_command_seconds, verbose=verbose)
        self.eurusd_price = None
        self._initialize()

    def _initialize(self) -> None:
        time.sleep(1)
        self.dwx.start()
        logger.info(f"Información de cuenta: {self.dwx.account_info}")
        self.dwx.subscribe_symbols(['EURUSD'])

    def on_tick(self, symbol: str, bid: float, ask: float) -> None:
        if symbol == "EURUSD":
            self.eurusd_price = (bid + ask) / 2.0

    def on_message(self, message: Dict) -> None:
        if message.get('type') == 'ERROR':
            logger.error(f"{message.get('error_type')} | {message.get('description')}")
        elif message.get('type') == 'INFO':
            logger.info(f"{message.get('message')}")

class EmailTrader:
    """Clase principal para manejar operativa basada en emails"""
    def __init__(self):
        self.running = False
        self.thread_loop = None
        self.workspaces: List[str] = [
            "10-TEST_NQ_Set1L", "10-TEST_NQ_Set2L", # ... resto de workspaces
        ]
        self.workspace_modes: Dict[str, str] = {}
        self.processor_mt4 = None
        self.processor_mt5 = None
        self.last_restart_date = None
        self._setup_gui()

    def _setup_gui(self) -> None:
        self.root = tk.Tk()
        self.root.title("Email Trading System")
        self._create_widgets()

    def log(self, message: str) -> None:
        """Método centralizado para logging"""
        self.text_log.config(state='normal')
        self.text_log.insert(tk.END, f"{message}\n")
        self.text_log.see(tk.END)
        self.text_log.config(state='disabled')
        logger.info(message)

    def connect_imap(self) -> imaplib.IMAP4_SSL:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_ACCOUNT, PASSWORD)
        return mail

    def process_email(self, raw_email: bytes) -> None:
        """Procesar emails y extraer órdenes"""
        try:
            email_message = email.message_from_bytes(raw_email)
            subject = self._decode_header(email_message['Subject'])
            
            if 'Strategy Filled Order' not in subject:
                return

            email_body = self._get_email_body(email_message)
            self._extract_and_process_order(email_body)
            
        except Exception as e:
            self.log(f"Error procesando email: {str(e)}")

    def _decode_header(self, header: str) -> str:
        decoded, encoding = decode_header(header)[0]
        return decoded.decode(encoding or 'utf-8') if isinstance(decoded, bytes) else decoded

    def _get_email_body(self, email_message) -> str:
        if email_message.is_multipart():
            for part in email_message.walk():
                if part.get_content_type() == 'text/plain' and 'attachment' not in str(part.get('Content-Disposition')):
                    return part.get_payload(decode=True).decode()
        return email_message.get_payload(decode=True).decode()

    def _extract_and_process_order(self, email_body: str) -> None:
        order_data = self._parse_order_data(email_body)
        if not order_data:
            return

        if order_data['workspace'] not in self.workspace_modes or self.workspace_modes[order_data['workspace']] == "No operar":
            self.log(f"Orden de {order_data['workspace']} ignorada")
            return

        self._execute_trade(order_data)

    def _parse_order_data(self, email_body: str) -> Optional[Dict]:
        lines = email_body.strip().splitlines()
        order_pattern = r'^(Buy|Sell)\s+(\d+)\s+@?(\S+)\s+@?\s+(Market|[\d\.]+)(?:\s+(.*))?$'
        
        order_data = {}
        for line in lines:
            line = line.strip()
            if line.startswith('Order:'):
                match = re.match(order_pattern, line[len('Order:'):].strip())
                if match:
                    order_data.update({
                        'action': match.group(1),
                        'quantity': match.group(2),
                        'instrument': match.group(3),
                        'price': match.group(4),
                        'order_type': match.group(5) or ''
                    })
            elif line.startswith('Occurred:'): order_data['occurred'] = line[9:].strip()
            elif line.startswith('Signal:'): order_data['signal'] = line[7:].strip()
            elif line.startswith('Interval:'): order_data['interval'] = line[9:].strip()
            elif line.startswith('Workspace:'): order_data['workspace'] = line[10:].strip().split("\\")[-1]

        return order_data if all(k in order_data for k in ['action', 'quantity', 'instrument', 'workspace']) else None

    def _execute_trade(self, order_data: Dict) -> None:
        processors = self._get_active_processors()
        if not processors:
            self.log("No hay procesadores activos")
            return

        symbol = Config.SYMBOL_MAPPING.get(order_data['instrument'], order_data['instrument'])
        capital = float(self.entry_capital.get() or "0")
        
        for processor in processors:
            lots = MoneyManagement.calculate_lots(
                processor,
                capital,
                float(order_data['quantity']),
                Config.BIG_POINT_VALUE_TS.get(order_data['instrument'], 1),
                Config.BIG_POINT_VALUE_DWX.get(order_data['instrument'], 1),
                processor.eurusd_price or 1.0
            )
            self._manage_position(processor, order_data, symbol, lots)

    def _get_active_processors(self) -> List[TickProcessor]:
        plataforma = self.platform_var.get()
        processors = []
        if plataforma in ["MT4", "Ambos"] and self.processor_mt4:
            processors.append(self.processor_mt4)
        if plataforma in ["MT5", "Ambos"] and self.processor_mt5:
            processors.append(self.processor_mt5)
        return processors

    def _manage_position(self, processor: TickProcessor, order_data: Dict, symbol: str, lots: float) -> None:
        existing_ticket, existing_order = self._get_open_order(processor, order_data['workspace'])
        modo = self.workspace_modes[order_data['workspace']]

        if modo == "Largo" and order_data['action'] == "Buy":
            self._handle_long_entry(processor, existing_ticket, existing_order, symbol, lots, order_data['workspace'])
        elif modo == "Corto" and order_data['action'] == "Sell":
            self._handle_short_entry(processor, existing_ticket, existing_order, symbol, lots, order_data['workspace'])
        elif order_data['action'] in ["Buy", "Sell"] and existing_ticket:
            self._close_position(processor, existing_ticket, order_data['workspace'])

    def _handle_long_entry(self, processor, ticket, order, symbol: str, lots: float, workspace: str) -> None:
        if not ticket:
            processor.dwx.open_order(symbol=symbol, order_type='buy', price=0, lots=lots, comment=workspace)
            self.log(f"Abrimos BUY {lots} {symbol} para {workspace}")
        elif order['type'] == 'sell':
            self._close_and_open(processor, ticket, symbol, 'buy', lots, workspace)

    def _handle_short_entry(self, processor, ticket, order, symbol: str, lots: float, workspace: str) -> None:
        if not ticket:
            processor.dwx.open_order(symbol=symbol, order_type='sell', price=0, lots=lots, comment=workspace)
            self.log(f"Abrimos SELL {lots} {symbol} para {workspace}")
        elif order['type'] == 'buy':
            self._close_and_open(processor, ticket, symbol, 'sell', lots, workspace)

    def _close_and_open(self, processor, ticket: int, symbol: str, order_type: str, lots: float, workspace: str) -> None:
        processor.dwx.close_order(ticket)
        processor.dwx.open_order(symbol=symbol, order_type=order_type, price=0, lots=lots, comment=workspace)
        self.log(f"Cerramos posición opuesta y abrimos {order_type.upper()} {lots} {symbol} para {workspace}")

    def _close_position(self, processor, ticket: int, workspace: str) -> None:
        processor.dwx.close_order(ticket)
        self.log(f"Cerrada posición existente para {workspace}")

    def _get_open_order(self, processor, workspace: str) -> Tuple[Optional[int], Optional[Dict]]:
        for ticket, order in processor.dwx.open_orders.items():
            if order.get('comment') == workspace:
                return ticket, order
        return None, None

    def start_trading(self, automatic: bool = False) -> None:
        if self.running:
            if not automatic:
                messagebox.showinfo("Info", "La operativa ya está en marcha")
            return

        plataforma = self.platform_var.get()
        mt4_path = self.entry_mt4_path.get().strip()
        mt5_path = self.entry_mt5_path.get().strip()

        self._initialize_processors(plataforma, mt4_path, mt5_path)
        self.running = True
        self.thread_loop = threading.Thread(target=self._main_loop, daemon=True)
        self.thread_loop.start()
        self.log("Operativa iniciada")

    def _initialize_processors(self, plataforma: str, mt4_path: str, mt5_path: str) -> None:
        if self.processor_mt4:
            self.processor_mt4 = None
        if self.processor_mt5:
            self.processor_mt5 = None

        if plataforma in ["MT4", "Ambos"] and mt4_path:
            self.processor_mt4 = TickProcessor(mt4_path)
        if plataforma in ["MT5", "Ambos"] and mt5_path:
            self.processor_mt5 = TickProcessor(mt5_path)

    def stop_trading(self, automatic: bool = False) -> None:
        if self.running:
            self.running = False
            self.processor_mt4 = None
            self.processor_mt5 = None
            self.log("Operativa detenida")
            if not automatic:
                messagebox.showinfo("Info", "Operativa detenida")
        else:
            self.log("La operativa no estaba en marcha")

    def _main_loop(self) -> None:
        while self.running:
            try:
                mail = self.connect_imap()
                mail.select('inbox')
                status, messages = mail.search(None, '(UNSEEN FROM "notificacionesdarwinsyo@gmail.com")')
                for num in messages[0].split():
                    _, data = mail.fetch(num, '(RFC822)')
                    self.process_email(data[0][1])
                    mail.store(num, '+FLAGS', '\\Seen')
                mail.close()
                mail.logout()
            except Exception as e:
                self.log(f"Error en main loop: {str(e)}")
            time.sleep(5)

    def _create_widgets(self) -> None:
        # Frame superior
        top_frame = tk.Frame(self.root)
        top_frame.pack(pady=10, padx=10, fill='x')
        
        self.entry_workspace = tk.Entry(top_frame)
        self.entry_workspace.pack(side='left', padx=5)
        tk.Button(top_frame, text="Añadir Workspace", command=self.add_workspace).pack(side='left', padx=5)

        # Frame de hora
        hora_frame = tk.Frame(self.root)
        hora_frame.pack(pady=10, padx=10, fill='x')
        tk.Label(hora_frame, text="Hora de reinicio (HH:MM):").pack(side='left', padx=5)
        self.entry_hora_reinicio = tk.Entry(hora_frame, width=10)
        self.entry_hora_reinicio.insert(0, AUTOMATIC_RESTART_TIME)
        self.entry_hora_reinicio.pack(side='left', padx=5)
        tk.Button(hora_frame, text="Actualizar Hora", command=self.update_restart_time).pack(side='left', padx=5)

        # Frame de capital
        capital_frame = tk.Frame(self.root)
        capital_frame.pack(pady=10, padx=10, fill='x')
        tk.Label(capital_frame, text="Capital:").pack(side='left', padx=5)
        self.entry_capital = tk.Entry(capital_frame, width=10)
        self.entry_capital.insert(0, "20000000")
        self.entry_capital.pack(side='left', padx=5)

        # Frame de plataforma
        platform_frame = tk.Frame(self.root)
        platform_frame.pack(pady=10, padx=10, fill='x')
        tk.Label(platform_frame, text="Plataforma:").pack(side='left', padx=5)
        self.platform_var = tk.StringVar(value="MT5")
        ttk.Combobox(platform_frame, textvariable=self.platform_var, 
                    values=["MT4", "MT5", "Ambos"]).pack(side='left', padx=5)
        
        tk.Label(platform_frame, text="Ruta MT4:").pack(side='left', padx=5)
        self.entry_mt4_path = tk.Entry(platform_frame, width=50)
        self.entry_mt4_path.insert(0, r"C:\Path\To\MT4\MQL4\Files")
        self.entry_mt4_path.pack(side='left', padx=5)
        
        tk.Label(platform_frame, text="Ruta MT5:").pack(side='left', padx=5)
        self.entry_mt5_path = tk.Entry(platform_frame, width=50)
        self.entry_mt5_path.insert(0, r"C:\Users\Alberto\AppData\Roaming\MetaQuotes\Terminal\6C3C6A11D1C3791DD4DBF45421BF8028\MQL5\Files")
        self.entry_mt5_path.pack(side='left', padx=5)

        # Frame de botones
        frame_buttons = tk.Frame(self.root)
        frame_buttons.pack(pady=10)
        tk.Button(frame_buttons, text="Buscar WS en email", command=self.search_workspaces).pack(side='left', padx=5)
        tk.Button(frame_buttons, text="Mostrar WS", command=self.display_workspaces).pack(side='left', padx=5)
        tk.Button(frame_buttons, text="Iniciar", command=self.start_trading).pack(side='left', padx=5)
        tk.Button(frame_buttons, text="Parar", command=self.stop_trading).pack(side='left', padx=5)

        # Frame de workspaces
        self.workspaces_frame = tk.Frame(self.root)
        self.workspaces_frame.pack(fill='both', expand=True, padx=10, pady=10)

        # Frame de log
        log_frame = tk.Frame(self.root)
        log_frame.pack(fill='both', expand=True, padx=10, pady=10)
        scrollbar = tk.Scrollbar(log_frame)
        scrollbar.pack(side='right', fill='y')
        self.text_log = tk.Text(log_frame, wrap='word', yscrollcommand=scrollbar.set, state='disabled')
        self.text_log.pack(fill='both', expand=True)
        scrollbar.config(command=self.text_log.yview)

        self.root.after(60000, self.check_automatic_restart)

    def add_workspace(self) -> None:
        new_ws = self.entry_workspace.get().strip()
        if new_ws and new_ws not in self.workspaces:
            self.workspaces.append(new_ws)
            self.display_workspaces()
            self.entry_workspace.delete(0, tk.END)
            self.log(f"Workspace {new_ws} agregado")

    def search_workspaces(self) -> None:
        # Implementación pendiente
        pass

    def display_workspaces(self) -> None:
        # Implementación pendiente
        pass

    def update_restart_time(self) -> None:
        # Implementación pendiente
        pass

    def check_automatic_restart(self) -> None:
        now = datetime.now()
        if now.strftime("%H:%M") == AUTOMATIC_RESTART_TIME and self.last_restart_date != now.date():
            self.stop_trading(automatic=True)
            self.start_trading(automatic=True)
            self.last_restart_date = now.date()
        self.root.after(60000, self.check_automatic_restart)

    def run(self) -> None:
        self.root.mainloop()

if __name__ == "__main__":
    trader = EmailTrader()
    trader.run()