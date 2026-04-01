import sys, os, json, time
import numpy as np
from datetime import datetime
from PySide6 import QtWidgets, QtCore, QtGui
import pyqtgraph as pg

# --- Import Modules (Original) ---
from core.modbus_worker import AsyncPollWorker
from ui.dashboard_tab import RealTimeHUDTab
from ui.all_nodes_view import AllNodesDashboard
from ui.history_tab import HistoryViewerTab
from ui.error_tab import ErrorSummaryTab
from ui.benchmark_page import BenchmarkPage

class MonitorApp(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        
        # 1. Config & Data Initialization
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.config = self.load_config()
        self.data_history = {} 
        self.time_history = {} 
        self.node_widgets = {} 
        
        self.log_path = self.prepare_dir(self.config['app_settings']['log_dir'])
        self.debug_path = self.prepare_dir(self.config['debug']['log_dir'])

        # 2. Worker Setup
        self.worker = AsyncPollWorker(self.config, self.log_path, self.debug_path)

        # 3. UI Setup
        self.init_ui()
        self.load_styles()

        # 4. Signal Connection
        self.worker.data_signal.connect(self.on_data_received)
        if hasattr(self, 'error_tab'):
            self.worker.error_summary_signal.connect(self.error_tab.update_error_log)
        
        # 5. Start
        self.worker.start()

        self.ui_refresh_timer = QtCore.QTimer()
        self.ui_refresh_timer.timeout.connect(self.refresh_active_tab)
        self.ui_refresh_timer.start(200)

        self.setWindowTitle("Phoenix Industrial Monitor - Compatibility v1.6.3")
        self.resize(1280, 850)

    # --- [ CORE FUNCTIONS ] ---

    def request_error_summary(self):
        if hasattr(self, 'worker'): self.worker.send_error_summary()

    def clear_error_stats(self):
        if hasattr(self, 'worker'):
            from core.modbus_worker import ErrorAggregator
            self.worker.error_aggregator = ErrorAggregator(debug_dir=self.worker.debug_path)
            self.worker.send_error_summary()

    def load_config(self):
        path = os.path.join(self.base_dir, "config.json")
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def prepare_dir(self, dir_name):
        path = os.path.join(self.base_dir, dir_name)
        os.makedirs(path, exist_ok=True)
        return path

    def load_styles(self):
        qss_path = os.path.join(self.base_dir, "style.qss")
        if os.path.exists(qss_path):
            with open(qss_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

    def init_ui(self):
        self.central_widget = QtWidgets.QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QtWidgets.QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # --- ส่วนที่ 1: Main Tabs (พื้นที่กราฟหลัก) ---
        self.tabs = QtWidgets.QTabWidget()
        self.rt_tab = RealTimeHUDTab(self.config, self.data_history, self.time_history)
        self.matrix_tab = AllNodesDashboard(self.config)
        self.history_tab = HistoryViewerTab(self.config)
        self.error_tab = ErrorSummaryTab(self) 
        self.bench_tab = BenchmarkPage(self.worker)

        self.tabs.addTab(self.rt_tab, " 🚀 Real-Time Monitor")
        self.tabs.addTab(self.matrix_tab, " 📊 All Nodes Dashboard")
        self.tabs.addTab(self.history_tab, " 📜 History Viewer")
        self.tabs.addTab(self.error_tab, " 🚨 Error Summary")
        self.tabs.addTab(self.bench_tab, " 📡 Benchmark Test")
        
        self.main_layout.addWidget(self.tabs, stretch=1)

        # --- ส่วนที่ 2: Bottom Fast-Scroll Strip (Horizontal LED Cards) ---
        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setFixedHeight(115) # ปรับความสูงให้พอดีกับแนวนอน
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.scroll_area.setStyleSheet("background: #080808; border: none; border-top: 1px solid #222;")

        self.strip_content = QtWidgets.QWidget()
        self.strip_layout = QtWidgets.QHBoxLayout(self.strip_content)
        self.strip_layout.setContentsMargins(15, 10, 15, 10)
        self.strip_layout.setSpacing(12)

        # สร้างการ์ดสำหรับแต่ละ Node จาก Config
        for node_cfg in self.config.get('nodes', []):
            for ch in node_cfg.get('channels', []):
                if ch.get('enabled', True):
                    # สร้าง Key สำหรับดึงข้อมูล (Node_Channel)
                    display_name = f"{node_cfg['node_name']} - {ch['name']}"
                    ch_key = display_name.replace(" - ", "_")
                    
                    # สร้างปุ่มการ์ด
                    card = QtWidgets.QPushButton()
                    card.setCheckable(True)
                    card.setFixedSize(195, 85)
                    card.setCursor(QtCore.Qt.PointingHandCursor)
                    
                    # Layout แนวตั้งภายใน Card
                    card_v_layout = QtWidgets.QVBoxLayout(card)
                    card_v_layout.setContentsMargins(12, 10, 12, 10)
                    card_v_layout.setSpacing(5)
                    
                    # 1. หัวข้อ (ชื่อ Node)
                    nlbl = QtWidgets.QLabel(f"{node_cfg['node_name']} · {ch['name']}")
                    nlbl.setStyleSheet("color: #777; font-size: 7pt; font-weight: bold; text-transform: uppercase;")
                    
                    # 2. แถบ LED แนวนอน (Custom Widget)
                    led_bar = HorizontalLEDBar()
                    
                    # 3. ตัวเลขค่าปัจจุบัน (Live Value)
                    vlbl = QtWidgets.QLabel("0.00")
                    vlbl.setStyleSheet("color: #eee; font-size: 13pt; font-weight: bold; font-family: 'Consolas';")
                    
                    card_v_layout.addWidget(nlbl)
                    card_v_layout.addWidget(led_bar)
                    card_v_layout.addWidget(vlbl, 0, QtCore.Qt.AlignRight | QtCore.Qt.AlignBottom)
                    
                    card.setStyleSheet("""
                        QPushButton { 
                            background: #121212; 
                            border: 1px solid #333; 
                            border-radius: 10px; 
                        }
                        QPushButton:hover { background: #1a1a1a; }
                        QPushButton:checked { 
                            background: rgba(46, 204, 113, 0.08); 
                            border: 2px solid #2ECC71; 
                        }
                    """)
                    
                    # เชื่อมต่อการคลิกเพื่อสลับกราฟ
                    addr = ch.get('address', 0)
                    card.clicked.connect(lambda checked, k=ch_key, a=addr, d=display_name: self.switch_node(k, a, d))
                    
                    self.strip_layout.addWidget(card)
                    
                    # เก็บ Reference เพื่อใช้อัปเดตใน on_data_received
                    # ต้องมี 'max' ใน config หรือ default เป็น 1000
                    self.node_widgets[ch_key] = {
                        "btn": card, 
                        "val_lbl": vlbl, 
                        "led": led_bar, 
                        "max": ch.get('max_val', 1000) 
                    }

        self.strip_layout.addStretch()
        self.scroll_area.setWidget(self.strip_content)
        self.main_layout.addWidget(self.scroll_area)

        # แสดงแถบด้านล่างเฉพาะหน้าแรก
        self.tabs.currentChanged.connect(lambda idx: self.scroll_area.setVisible(idx == 0))

        # เลือกตัวแรกอัตโนมัติเมื่อเปิดโปรแกรม
        if self.node_widgets:
            first_key = list(self.node_widgets.keys())[0]
            # ค้นหาชื่อและที่อยู่ตัวแรก
            fn = self.config['nodes'][0]
            fc = fn['channels'][0]
            self.switch_node(first_key, fc.get('address', 0), f"{fn['node_name']} - {fc['name']}")

    def switch_node(self, ch_key, addr, display_name):
        """
        สลับการแสดงผลกราฟและอัปเดต HUD ข้อมูล
        ch_key: Key สำหรับดึง data_history (เช่น Node_Temp)
        addr: ที่อยู่ Modbus (Address)
        display_name: ชื่อที่ใช้แสดงบน HUD (เช่น Node - Temp)
        """
        # 1. เก็บชื่อที่เลือกไว้ในตัวแปรหลัก (ถ้ามี)
        self.current_key = ch_key 
        
        # 2. จัดการสถานะปุ่ม (Checked/Unchecked) ใน Bottom Strip
        for k, widgets in self.node_widgets.items():
            # ถ้า key ตรงกันให้ปุ่มยุบลง (Checked) ถ้าไม่ตรงให้ยกขึ้น
            widgets['btn'].setChecked(k == ch_key)
        
        # 3. ส่งข้อมูลไปยังหน้า RealTimeHUDTab (หน้ากราฟ)
        # ส่ง Key เพื่อให้กราฟรู้ว่าต้องวาดเส้นไหน
        self.rt_tab.current_key = ch_key
        
        # ส่ง Address ไปแสดงที่ Label บน HUD
        if hasattr(self.rt_tab, 'node_addr_lbl'):
            self.rt_tab.node_addr_lbl.setText(f"ADDR: 0x{addr:04X}")
            
        # ส่งชื่อเต็มไปแสดงที่ Label บน HUD
        if hasattr(self.rt_tab, 'node_name_lbl'):
            self.rt_tab.node_name_lbl.setText(display_name.upper())

        # 4. บังคับให้หน้ากราฟอัปเดต UI ทันทีไม่ต้องรอ Timer
        self.rt_tab.update_ui()
        

    @QtCore.Slot(dict, float)
    def on_data_received(self, batch, timestamp):
        """
        รับข้อมูลชุดใหญ่ (batch) จาก Worker 
        batch: { 'Node_Channel': value, ... }
        """
        max_pts = self.config['app_settings'].get('max_points', 300)
        
        for ch_key, val in batch.items():
            # 1. เก็บข้อมูลลงในหน่วยความจำ (History) สำหรับวาดกราฟ
            if ch_key not in self.data_history:
                self.data_history[ch_key], self.time_history[ch_key] = [], []
            
            self.data_history[ch_key].append(val)
            self.time_history[ch_key].append(timestamp)
            
            # ลบข้อมูลเก่าทิ้งถ้าเกินจำนวนที่กำหนด
            if len(self.data_history[ch_key]) > max_pts:
                self.data_history[ch_key].pop(0)
                self.time_history[ch_key].pop(0)
            
            # 2. อัปเดตข้อมูลบนปุ่มการ์ด (Bottom Strip)
            if ch_key in self.node_widgets:
                widgets = self.node_widgets[ch_key]
                
                # อัปเดตตัวเลข Live Value
                widgets['val_lbl'].setText(f"{val:,.2f}")
                
                # อัปเดตแถบ LED แนวนอน และคำนวณสี (เขียว/เหลือง/แดง)
                max_val = widgets['max']
                widgets['led'].set_value(val, max_val)
                
        # 3. อัปเดตหน้า Matrix Dashboard (All Nodes View)
        if hasattr(self, 'matrix_tab'):
            self.matrix_tab.update_values(batch)
            
        # 4. หากกำลังดูหน้ากราฟ (Index 0) ให้สั่งอัปเดตกราฟทันทีเพื่อให้เส้นขยับ
        if self.tabs.currentIndex() == 0:
            self.rt_tab.update_ui()

    def refresh_active_tab(self):
        if self.tabs.currentIndex() == 0:
            self.rt_tab.update_ui()

    def closeEvent(self, event):
        if hasattr(self, 'worker'):
            self.worker.stop(); self.worker.wait(2000)
        event.accept()

class HorizontalLEDBar(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(8)  # ความสูงของแถบ LED
        self.percent = 0
        self.bar_color = QtGui.QColor("#2ECC71")

    def set_value(self, value, max_val):
        # คำนวณ % โดยจำกัดไม่ให้เกิน 100 และไม่น้อยกว่า 0
        limit = max_val if max_val > 0 else 100
        self.percent = min(100, max(0, (value / limit) * 100))
        
        # Logic เปลี่ยนสี: เขียว -> เหลือง (70%) -> แดง (90%)
        if self.percent >= 90:
            self.bar_color = QtGui.QColor("#FF3333") # แดง
        elif self.percent >= 70:
            self.bar_color = QtGui.QColor("#FFCC00") # เหลือง
        else:
            self.bar_color = QtGui.QColor("#2ECC71") # เขียว
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        
        # วาด Background Track (ร่องสีเทาจางๆ)
        bg_rect = QtCore.QRectF(0, 0, self.width(), self.height())
        painter.setBrush(QtGui.QBrush(QtGui.QColor(255, 255, 255, 15)))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(bg_rect, 4, 4)
        
        # วาดแถบพลังงาน (Progress) ตาม %
        if self.percent > 0:
            bar_width = (self.percent / 100) * self.width()
            bar_rect = QtCore.QRectF(0, 0, bar_width, self.height())
            painter.setBrush(QtGui.QBrush(self.bar_color))
            painter.drawRoundedRect(bar_rect, 4, 4)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = MonitorApp()
    window.show()
    sys.exit(app.exec())
