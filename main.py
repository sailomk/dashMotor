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

        # 1. Main Tabs
        self.tabs = QtWidgets.QTabWidget()
        self.rt_tab = RealTimeHUDTab(self.config, self.data_history, self.time_history)
        
        # --- [CRITICAL HACK] ---
        # สร้าง QListWidget ซ่อนไว้ใน rt_tab เพื่อหลอกโค้ดเก่าใน dashboard_tab.py
        if not hasattr(self.rt_tab, 'node_list') or self.rt_tab.node_list is None:
            self.rt_tab.node_list = QtWidgets.QListWidget()
        
        self.matrix_tab = AllNodesDashboard(self.config)
        self.history_tab = HistoryViewerTab(self.config)
        self.error_tab = ErrorSummaryTab(self)
        self.bench_tab = BenchmarkPage(self.worker)

        self.tabs.addTab(self.rt_tab, " Real-Time Monitor")
        self.tabs.addTab(self.matrix_tab, " All Nodes Dashboard")
        self.tabs.addTab(self.history_tab, " History Viewer")
        self.tabs.addTab(self.error_tab, " Error Summary")
        self.tabs.addTab(self.bench_tab, " Benchmark Test")
        self.main_layout.addWidget(self.tabs, stretch=1)

        # 2. Bottom Strip Selection
        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setFixedHeight(105)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("background: #050505; border: none; border-top: 1px solid #222;")

        self.strip_content = QtWidgets.QWidget()
        self.strip_layout = QtWidgets.QHBoxLayout(self.strip_content)
        self.strip_layout.setContentsMargins(15, 10, 15, 10)
        self.strip_layout.setSpacing(12)

        for node_cfg in self.config.get('nodes', []):
            for ch in node_cfg.get('channels', []):
                if ch.get('enabled', True):
                    display_name = f"{node_cfg['node_name']} - {ch['name']}"
                    ch_key = display_name.replace(" - ", "_")
                    
                    card = QtWidgets.QPushButton()
                    card.setCheckable(True)
                    card.setFixedSize(185, 75)
                    
                    c_layout = QtWidgets.QVBoxLayout(card)
                    c_layout.setContentsMargins(12, 8, 12, 8)
                    
                    nlbl = QtWidgets.QLabel(node_cfg['node_name'])
                    nlbl.setStyleSheet("color: #666; font-size: 7.5pt; font-weight: bold;")
                    vlbl = QtWidgets.QLabel("---")
                    vlbl.setStyleSheet("color: #2ECC71; font-size: 14pt; font-weight: bold;")
                    
                    c_layout.addWidget(nlbl)
                    c_layout.addWidget(QtWidgets.QLabel(ch['name'], styleSheet="color:#bbb; font-size:9pt;"))
                    c_layout.addWidget(vlbl)
                    
                    card.setStyleSheet("QPushButton{background:#121212; border:1px solid #333; border-radius:8px;} "
                                     "QPushButton:checked{background:rgba(46,204,113,0.12); border:2px solid #2ECC71;}")
                    
                    card.clicked.connect(lambda checked, d=display_name: self.switch_node(d))
                    self.strip_layout.addWidget(card)
                    self.node_widgets[ch_key] = {"btn": card, "val": vlbl}

        self.strip_layout.addStretch()
        self.scroll_area.setWidget(self.strip_content)
        self.main_layout.addWidget(self.scroll_area)

        # Tab Visibility Logic
        self.tabs.currentChanged.connect(lambda idx: self.scroll_area.setVisible(idx == 0))

        # เริ่มต้นเลือกตัวแรก
        if self.node_widgets:
            first_key = list(self.node_widgets.keys())[0]
            self.switch_node(first_key.replace("_", " - "))

    def switch_node(self, display_name):
        """ ฟังก์ชันส่งชื่อ Node เข้าไปที่หน้ากราฟโดยตรง """
        ch_key = display_name.replace(" - ", "_")
        
        # 1. อัปเดตสถานะปุ่มการ์ดด้านล่าง
        for k, widgets in self.node_widgets.items():
            widgets['btn'].setChecked(k == ch_key)
        
        # 2. ส่งข้อมูลเข้าหน้า Tab โดยตรง (Direct Injection)
        if hasattr(self.rt_tab, 'set_active_node'):
            self.rt_tab.set_active_node(display_name)
        else:
            # กรณีที่ยังไม่ได้แก้ไฟล์ dashboard_tab.py ให้ใช้แผนสำรอง (Mock List)
            self.rt_tab.node_list.clear()
            item = QtWidgets.QListWidgetItem(display_name)
            self.rt_tab.node_list.addItem(item)
            self.rt_tab.node_list.setCurrentItem(item)
            self.rt_tab.update_ui()

    @QtCore.Slot(dict, float)
    def on_data_received(self, batch, timestamp):
        for ch_key, val in batch.items():
            if ch_key not in self.data_history:
                self.data_history[ch_key], self.time_history[ch_key] = [], []
            self.data_history[ch_key].append(val)
            self.time_history[ch_key].append(timestamp)
            if len(self.data_history[ch_key]) > 300:
                self.data_history[ch_key].pop(0); self.time_history[ch_key].pop(0)
            
            if ch_key in self.node_widgets:
                self.node_widgets[ch_key]['val'].setText(f"{val:,.2f}")
                
        if hasattr(self, 'matrix_tab'):
            self.matrix_tab.update_values(batch)

    def refresh_active_tab(self):
        if self.tabs.currentIndex() == 0:
            self.rt_tab.update_ui()

    def closeEvent(self, event):
        if hasattr(self, 'worker'):
            self.worker.stop(); self.worker.wait(2000)
        event.accept()

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = MonitorApp()
    window.show()
    sys.exit(app.exec())
