import sys
import json
import sqlite3
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QVBoxLayout, QHBoxLayout, QGridLayout,
    QWidget, QLineEdit, QMessageBox, QMenuBar, QMenu,
    QStatusBar, QPushButton, QDialog, QFormLayout, QTableWidget,
    QTableWidgetItem, QPlainTextEdit, QListWidget, QListWidgetItem, QComboBox, QSpinBox, QDoubleSpinBox
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import QThread, pyqtSignal, Qt

from binance.exceptions import BinanceAPIException, BinanceOrderException
from TraderBot import TraderBot
from MonitorBot import MonitorBot
from TradeJewel import TradeJewel
import time
import datetime
import os

CONFIG_FILE = "config.json"
DB_FILE = "trader.db"

# Funções de inicialização e conexão com o banco SQLite
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS purchase_objects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, 
        quantity REAL, 
        value REAL,
        buy_price REAL, 
        sell_price REAL,
        min_appreciation REAL,
        validity INTEGER
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS operations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        inventory_id INTEGER,
        action TEXT,
        quantity REAL,
        price REAL,
        gain REAL,
        date TEXT,
        FOREIGN KEY(inventory_id) REFERENCES inventory(id)
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        object_id INTEGER,
        purchase_price REAL,
        purchase_date TEXT,
        sale_price REAL,
        sale_date TEXT,
        purchase_order_id REAL,
        sale_order_id INTEGER DEFAULT 0,
        status TEXT,
        date TEXT,
        FOREIGN KEY(object_id) REFERENCES purchase_objects(id)
    )
    """)
    conn.commit()
    conn.close() 


class TraderApp(QMainWindow):
    global btc_price
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dashboard do Bot Trader de Bitcoin")
        self.setGeometry(100, 100, 800, 600)
        btc_price = "0.0"
        self.bot = TraderBot()
        self.monitor_bot = MonitorBot()
        self.monitor_bot.update_signal.connect(self.update_price)
        self.bot.balance_signal.connect(self.update_balance)
        self.bot.inventory_update_signal.connect(self.update_inventory)
        self.bot.log_signal.connect(self.update_log)

        main_layout = QGridLayout()

        # Seção Esquerda - Operação do Bot e Configurações
        left_section = QVBoxLayout()
        start_bot_button = QPushButton("Iniciar Bot")
        start_bot_button.clicked.connect(self.start_bot)
        stop_bot_button = QPushButton("Parar Bot")
        stop_bot_button.clicked.connect(self.stop_bot)
        config_button = QPushButton("Configurações")
        config_button.clicked.connect(self.show_api_settings)
        add_purchase_object_button = QPushButton("Cadastrar Objeto de Compra")
        add_purchase_object_button.clicked.connect(self.add_purchase_object)

        left_section.addWidget(start_bot_button)
        left_section.addWidget(stop_bot_button)
        left_section.addWidget(config_button)
        left_section.addWidget(add_purchase_object_button)

        # Seção Direita - Compra, Venda e Informações
        right_section = QVBoxLayout()
        buy_button = QPushButton("Comprar")
        buy_button.clicked.connect(self.show_purchase_selection)
        sell_button = QPushButton("Vender")
        sell_button.clicked.connect(self.select_object_to_sell)
        self.price_label = QLabel("BTC Price: R$0.00")
        self.balance_label = QLabel("Saldo BTC: 0.00 | Saldo BRL: R$0.00")
        self.purchase_list = QListWidget()  # Lista para exibir objetos comprados
        self.purchase_list.setStyleSheet("background-color:#DDDDDD;")
       

        
        
        
        #.itemDoubleClicked.connect(self.open_sell_dialog)
        self.purchase_list.itemClicked.connect(self.select_object_to_sell)
        

        right_section.addWidget(self.price_label)
        right_section.addWidget(self.balance_label)
        right_section.addWidget(buy_button)
        right_section.addWidget(sell_button)
        right_section.addWidget(QLabel("Objetos Comprados:"))
        right_section.addWidget(self.purchase_list)

        # Seção Central - Indicadores e Log
        center_section = QVBoxLayout()

        # Indicadores de Desempenho
        self.performance_label = QLabel("Operações: 0 | Lucro Total: R$0.00")
        center_section.addWidget(self.performance_label)

        # Log das Operações
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        center_section.addWidget(self.log_output)

        # Estrutura e disposição das seções
        main_layout.addLayout(left_section, 0, 0)
        main_layout.addLayout(center_section, 0, 1)
        main_layout.addLayout(right_section, 0, 2)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Status: Aguardando...")

        self.load_api_keys()
        init_db()  # Inicializar banco de dados

    def show_api_settings(self):
        dialog = ConfigDialog()
        dialog.exec()

    def add_purchase_object(self):
        dialog = PurchaseObjectDialog(self.bot)
        dialog.exec()
        self.load_purchased_objects()

    def start_bot(self):
        api_key, secret_key, timeout = self.load_api_keys()
        if not api_key or not secret_key:
            QMessageBox.warning(self, "Erro", "API Key e Secret Key são obrigatórios!")
            return

        self.bot.setup_client(api_key, secret_key)
        self.monitor_bot.setup_client(api_key, secret_key)
        self.bot.start()
        self.monitor_bot.start()
        self.status_bar.showMessage("Status: Bots em execução...")

    def stop_bot(self):
        self.bot.stop()
        self.status_bar.showMessage("Status: Bot parado")

    def show_purchase_selection(self):
        dialog = PurchaseSelectionDialog(self.bot)
        dialog.exec()
        self.load_purchased_objects()
        
    def select_object_to_sell(self):
        obj_id = int(self.purchase_list.currentItem().text().split(" ")[0].split("#")[1])
        print(int(obj_id))
        
        obj = self.load_purchase_object(obj_id)
        #obj = ''
        # for item in self.bot.inventory:
            # if item['id'] == obj_id:
                # obj = item
                # print(item)
                # break
        dialog = SellDialog(obj,self.bot)
        dialog.exec()
        self.load_purchased_objects()

    def update_price(self, message):
        self.price_label.setText(message)
        
    def update_balance(self, message):
        self.balance_label.setText(message)

    def update_inventory(self, inventory):
        
        self.purchase_list.clear()
       
        for jewel in inventory:
            #price = self.bot.client.get_symbol_ticker(symbol="BTCBRL")["price"]
            #print(f'STATUS: {jewel.get_status()}')
            if jewel.get_status() != "Cancelado":
                if jewel.get_status() != "Vendido":
                    
                    self.purchase_list.addItem(
                        f"#{jewel.get_id()} - {jewel.name} | Valor: {jewel.get_value()} | Ganho: {jewel.get_gain(self.monitor_bot.btc_price)} | Status: {jewel.get_status() }")
                

    def load_purchased_objects(self):
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT name, buy_price, sell_price FROM purchase_objects")
        purchased_objects = cursor.fetchall()
        print(purchased_objects)
        
        conn.close()
        # Atualizar a lista de objetos comprados
        
    
    def load_purchase_object(self, object_id):
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT i.id, po.name, po.value, po.quantity, i.purchase_price, i.purchase_order_id, i.sale_order_id, date FROM purchase_objects po left join inventory i on po.id = i.object_id WHERE i.id = ?", (object_id,))
        item = cursor.fetchone()
        obj = {'id': item[0], 'name': item[1], 'value': item[2], 'quantity': item[3], 'purchase_price': item[4], 'purchase_order_id': item[5], 'sell_order_id': item[6], 'date': item[7]}
        conn.close()
        return obj
        

    def update_log(self, log_message):
        self.log_output.appendPlainText(log_message)

    def load_api_keys(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE) as config_file:
                config = json.load(config_file)
                return config.get("api_key"), config.get("secret_key"), config.get("timeout", 10)
        return None, None, 10  # Retornar valores padrão

class ConfigDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Configurações da API")
        layout = QFormLayout()

        self.api_key_input = QLineEdit()
        self.secret_key_input = QLineEdit()
        self.timeout_input = QSpinBox()
        self.timeout_input.setMinimum(1)

        self.save_button = QPushButton("Salvar")
        self.save_button.clicked.connect(self.save_config)

        layout.addRow("API Key", self.api_key_input)
        layout.addRow("Secret Key", self.secret_key_input)
        layout.addRow("Timeout (segundos)", self.timeout_input)
        layout.addRow(self.save_button)
        self.setLayout(layout)

    def save_config(self):
        config = {
            "api_key": self.api_key_input.text(),
            "secret_key": self.secret_key_input.text(),
            "timeout": self.timeout_input.value(),
        }
        with open(CONFIG_FILE, 'w') as config_file:
            json.dump(config, config_file)
        QMessageBox.information(self, "Configuração", "Configuração salva com sucesso!")

class PurchaseObjectDialog(QDialog):
    def __init__(self, bot):
        super().__init__()
        self.setWindowTitle("Cadastro de Objeto de Compra")
        layout = QFormLayout()

        self.bot = bot
        self.name_input = QLineEdit()
        self.quantity_input = QDoubleSpinBox()
        self.value_input = QDoubleSpinBox()
        self.buy_price_input = QDoubleSpinBox()
        self.sell_price_input = QDoubleSpinBox()
        self.min_appreciation_input = QDoubleSpinBox()
        self.validity_input = QSpinBox()

        self.save_button = QPushButton("Salvar")
        self.save_button.clicked.connect(self.save_purchase_object)
        self.delete_button = QPushButton("Excluir")
        self.delete_button.clicked.connect(self.delete_purchase_object)

        self.object_list = QListWidget()
        self.object_list.itemClicked.connect(self.load_object_for_editing)
        self.load_objects()

        layout.addRow("Nome", self.name_input)
        layout.addRow("Quantidade", float(self.quantity_input))
        layout.addRow("Valor", self.value_input)
        layout.addRow("Preço de Compra", self.buy_price_input)
        layout.addRow("Preço de Venda", self.sell_price_input)
        layout.addRow("Valorização Mínima", self.min_appreciation_input)
        layout.addRow("Validade (dias)", self.validity_input)

        layout.addRow(self.object_list)
        layout.addRow(self.save_button, self.delete_button)
        self.setLayout(layout)

        self.current_edit_id = None  # Para rastrear qual objeto está sendo editado

    def load_objects(self):
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM purchase_objects")
        objects = cursor.fetchall()
        self.object_list.clear()
        for obj_id, name in objects:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, obj_id)
            self.object_list.addItem(item)
        conn.close()

    def load_object_for_editing(self, item):
        obj_id = item.data(Qt.ItemDataRole.UserRole)
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT name, quantity, value, buy_price, sell_price, min_appreciation, validity FROM purchase_objects WHERE id = ?", (obj_id,))
        obj = cursor.fetchone()
        conn.close()
        if obj:
            self.current_edit_id = obj_id  # Armazenar ID do objeto atual
            self.name_input.setText(obj[0])
            self.quantity_input.setValue(obj[1])
            self.value_input.setValue(obj[2])
            self.buy_price_input.setValue(obj[3])
            self.sell_price_input.setValue(obj[4])
            self.min_appreciation_input.setValue(obj[5])
            self.validity_input.setValue(obj[6])

    def save_purchase_object(self):
        name = self.name_input.text()
        quantity = float(self.quantity_input.value())
        value = self.value_input.value()
        buy_price = self.buy_price_input.value()
        sell_price = self.sell_price_input.value()
        min_appreciation = self.min_appreciation_input.value()
        validity = self.validity_input.value()

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Verificar se estamos atualizando um objeto existente ou criando um novo
        if self.current_edit_id:
            cursor.execute("""
            UPDATE purchase_objects 
            SET name = ?, quantity = ?, value = ?, buy_price = ?, sell_price = ?, min_appreciation = ?, validity = ? 
            WHERE id = ?
            """, (name, quantity, value, buy_price, sell_price, min_appreciation, validity, self.current_edit_id))
        else:
            cursor.execute("""
            INSERT INTO purchase_objects (name, quantity, value, buy_price, sell_price, min_appreciation, validity) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (name, quantity, value, buy_price, sell_price, min_appreciation, validity))

        conn.commit()
        conn.close()
        self.load_objects()
        QMessageBox.information(self, "Objeto de Compra", "Objeto salvo com sucesso!")

    def delete_purchase_object(self):
        selected_item = self.object_list.currentItem()
        if selected_item:
            obj_id = selected_item.data(Qt.ItemDataRole.UserRole)
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM purchase_objects WHERE id = ?", (obj_id,))
            conn.commit()
            conn.close()
            self.load_objects()
            QMessageBox.information(self, "Objeto de Compra", "Objeto excluído com sucesso!")

class PurchaseSelectionDialog(QDialog):
    def __init__(self, bot):
        super().__init__()
        self.setWindowTitle("Comprar Objeto")
        self.bot = bot
        layout = QVBoxLayout()

        self.purchase_combo = QComboBox()
        self.load_purchase_objects()

        buy_button = QPushButton("Comprar")
        buy_button.clicked.connect(self.buy_selected_object)
        cancel_button = QPushButton("Cancelar")
        cancel_button.clicked.connect(self.reject)

        layout.addWidget(self.purchase_combo)
        layout.addWidget(buy_button)
        layout.addWidget(cancel_button)
        self.setLayout(layout)

    def load_purchase_objects(self):
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, value, quantity FROM purchase_objects")
        objects = cursor.fetchall()
        for obj_id, name, value, quantity in objects:
            self.purchase_combo.addItem(f"{name}({quantity * 100000}) - R${value:.2f}", userData=obj_id)
        conn.close()

    def buy_selected_object(self):
        obj_id = self.purchase_combo.currentData()
        
        if obj_id:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT quantity FROM purchase_objects WHERE id = ?", (obj_id,))
            quantity = cursor.fetchone()[0]
            inventory_id = self.bot.buy_object(obj_id, f'{quantity:.5f}')  # Adicionar ao inventário do bot
            cursor.execute("""
            INSERT INTO operations (inventory_id, action, quantity, price, date) 
            VALUES (?, ?, ?, ?, datetime('now'))
            """, (inventory_id, 'buy', quantity, 0))  # Exemplo de compra com a quantidade total
            conn.commit()
            conn.close()
            QMessageBox.information(self, "Compra Realizada", "Objeto comprado com sucesso!")
            self.close()
            
            
class SellDialog(QDialog):
    def __init__(self, obj, bot):
        super().__init__()
        
        self.bot = bot
        self.object_selected = obj
        self.setWindowTitle("Venda de Item")

        # Layout principal
        layout = QVBoxLayout()
        
        # Exibe o nome do item e quantidade fixa
        self.label_item = QLabel(f"Item selecionado: {obj['name']}")
        layout.addWidget(self.label_item)

        self.label_quantity = QLabel(f"Quantidade: {obj['quantity']:.5f}")
        layout.addWidget(self.label_quantity)
        
        self.label_custo = QLabel(f"Custo: {(obj['quantity'] * obj['purchase_price']):.5f}")
        layout.addWidget(self.label_custo)
        price = bot.client.get_symbol_ticker(symbol="BTCBRL")["price"]
        self.label_ganho = QLabel(f"Ganho: {((float(price) * obj['quantity']) - obj['quantity'] * obj['purchase_price']):.5f}")
        layout.addWidget(self.label_ganho)


        # Layout para os botões de confirmação e cancelamento
        button_layout = QHBoxLayout()
        
        # Botão para confirmar venda
        self.sell_button = QPushButton("Confirmar Venda")
        self.sell_button.clicked.connect(self.confirm_sale)
        button_layout.addWidget(self.sell_button)

        # Botão para cancelar
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)
    
 

    def confirm_sale(self):
        
        if self.bot.sell_object(self.object_selected['id']):
            
            print(f"Venda confirmada para o item: {self.label_item.text()}, {self.label_quantity.text()}")
            self.accept()
if __name__ == "__main__":
    init_db()
    app = QApplication(sys.argv)
    window = TraderApp()
    window.show()
    sys.exit(app.exec())
