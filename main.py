import sys, os, json, time,math
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
from PySide6.QtWidgets import QMessageBox, QApplication

pg.setConfigOptions(antialias=True, useOpenGL=False)
version = "1.6.6"

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
        self.worker.error_summary_signal.connect(self.handle_critical_error)
        self.worker.finished_signal.connect(self.on_worker_finished)

        # 3. UI Setup
        self.init_ui()
        self.load_styles()
        self.initial_popup_done = False
        self._is_closing = False

        # 4. Signal Connection
        self.worker.data_signal.connect(self.on_data_received)
        self.worker.error_summary_signal.connect(self.handle_error_summary)
        if hasattr(self, 'error_tab'):
            self.worker.error_summary_signal.connect(self.error_tab.update_error_log)
        
        # 5. Start
        self.worker.start()

        self.ui_refresh_timer = QtCore.QTimer()
        self.ui_refresh_timer.timeout.connect(self.refresh_active_tab)
        self.ui_refresh_timer.start(200)

        self.setWindowTitle("Phoenix Industrial Monitor - Compatibility  "+ version)
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
        # 1. Main Container & Layout
        self.central_widget = QtWidgets.QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QtWidgets.QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 2. Main Tabs
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setStyleSheet("QTabBar::tab { text-align: left; }")
        self.rt_tab = RealTimeHUDTab(self.config, self.data_history, self.time_history)
        self.matrix_tab = AllNodesDashboard(self.config)
        self.history_tab = HistoryViewerTab(self.config)
        self.error_tab = ErrorSummaryTab(self)
        self.bench_tab = BenchmarkPage(self.worker)

        self.tabs.addTab(self.rt_tab, " Real-Time Monitor")
        self.tabs.addTab(self.matrix_tab, "  All Nodes Dashboard")
        self.tabs.addTab(self.history_tab, "  History Viewer")
        self.tabs.addTab(self.error_tab, "  Error Summary")
        self.tabs.addTab(self.bench_tab, "  Benchmark Test")
        self.main_layout.addWidget(self.tabs, stretch=1)

        # 3. Bottom Strip Scroll Area
        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setObjectName("BottomScrollArea") # อ้างอิงใน style.qss
        self.scroll_area.setFixedHeight(125)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)

        self.strip_content = QtWidgets.QWidget()
        self.strip_content.setObjectName("BottomStripContent")
        self.strip_layout = QtWidgets.QHBoxLayout(self.strip_content)
        self.strip_layout.setContentsMargins(15, 12, 15, 12)
        self.strip_layout.setSpacing(15)
      
        # 4. Loop สร้าง Card สำหรับแต่ละ Node
        for node_cfg in self.config.get('nodes', []):
            for ch in node_cfg.get('channels', []):
                if ch.get('enabled', True):
                    display_name = f"{node_cfg['node_name']} - {ch['name']}"
                    ch_key = display_name.replace(" - ", "_")
                    addr = ch.get('address', 0)
                    max_val = ch.get('max_val', 1000)

                    # --- สร้าง Card ---
                    card = QtWidgets.QPushButton()
                    card.setObjectName("NodeCard") # อ้างอิงใน style.qss
                    card.setCheckable(True)
                    card.setFixedSize(190, 90) 
                    card.setCursor(QtCore.Qt.PointingHandCursor)
                    
                    v_layout = QtWidgets.QVBoxLayout(card)
                    v_layout.setContentsMargins(12, 10, 12, 10)
                    v_layout.setSpacing(6)

                    # A. Labels พร้อมชื่อ Object สำหรับ QSS
                    nlbl = QtWidgets.QLabel(f"{node_cfg['node_name']} · {ch['name']}")
                    nlbl.setObjectName("NodeTitle")
                    
                    led_bar = HorizontalLEDBar() # 20 Segments
                    
                    bottom_row = QtWidgets.QHBoxLayout()
                    plbl = QtWidgets.QLabel("0%")
                    plbl.setObjectName("PercDisplay")
                    
                    vlbl = QtWidgets.QLabel("0.00")
                    vlbl.setObjectName("ValueDisplay")

                    bottom_row.addWidget(plbl)
                    bottom_row.addStretch()
                    bottom_row.addWidget(vlbl)

                    v_layout.addWidget(nlbl)
                    v_layout.addWidget(led_bar)
                    v_layout.addLayout(bottom_row)

                    # Signal Connection
                    card.clicked.connect(lambda checked, k=ch_key, a=addr, d=display_name: self.switch_node(k, a, d))

                    self.strip_layout.addWidget(card)

                    # เก็บ Reference
                    self.node_widgets[ch_key] = {
                        "btn": card,
                        "val_lbl": vlbl,
                        "perc_lbl": plbl,
                        "led": led_bar,
                        "max": max_val
                    }

        self.strip_layout.addStretch()
        self.scroll_area.setWidget(self.strip_content)
        self.main_layout.addWidget(self.scroll_area)
        
        # แสดงผลตาม Tab
        self.tabs.currentChanged.connect(lambda idx: self.scroll_area.setVisible(idx == 0))
        
        # เลือก Node แรก
        if self.node_widgets:
            first_key = list(self.node_widgets.keys())[0]
            self.switch_node(first_key, self.config['nodes'][0]['channels'][0].get('address', 0), first_key.replace("_", " - "))
                                   
    def switch_node(self, ch_key, addr, display_name):
        self.current_key = ch_key 
        
        # 1. จัดการปุ่มกดใน Bottom Strip (เดิม)
        for k, widgets in self.node_widgets.items():
            widgets['btn'].setChecked(k == ch_key)
        
        # 2. ตรวจสอบสถานะ Quarantine ของ Node/Channel นี้ก่อนสลับ
        node_name = ch_key.split('_')[0]
        ch_name = ch_key.split('_')[1] if '_' in ch_key else ""
        node_cfg = next((n for n in self.config.get('nodes', []) if n['node_name'] == node_name), None)
        target_ch = next((c for c in node_cfg.get('channels', []) if c['name'] == ch_name), None) if node_cfg else None
        
        is_disabled = target_ch and not target_ch.get('enabled', True)

        # 3. ส่งข้อมูลไปยังหน้า RealTimeHUDTab
        self.rt_tab.current_key = ch_key
        
        if hasattr(self.rt_tab, 'node_addr_lbl'):
            self.rt_tab.node_addr_lbl.setText(f"ADDR: 0x{addr:04X}")
            
        if hasattr(self.rt_tab, 'node_name_lbl'):
            # ถ้าโดน Quarantine ให้ต่อท้ายชื่อว่า (QUARANTINED)
            suffix = " [QUARANTINED]" if is_disabled else ""
            self.rt_tab.node_name_lbl.setText(f"{display_name.upper()}{suffix}")

        # 4. เคลียร์ข้อมูลกราฟ (จุดสำคัญ)
        # หาก Node ถูกปิดการใช้งาน ให้ส่งข้อมูลหลอกที่เป็นค่าว่างไป เพื่อบังคับเคลียร์กราฟ
        if is_disabled:
            if ch_key in self.data_history:
                # เคลียร์ History เฉพาะของ key นี้เพื่อให้กราฟว่างเปล่า
                self.data_history[ch_key] = []
                self.time_history[ch_key] = []
            
            # สั่งเคลียร์เส้นกราฟในหน้า UI
            if hasattr(self.rt_tab, 'curve'):
                self.rt_tab.curve.setData([], [])
                
        # 5. อัปเดต UI ทันที
        self.rt_tab.update_ui()
  
    def handle_critical_error(self, summary_text):
        # เก็บข้อความไว้ใช้ตอนฟังก์ชัน on_worker_finished ทำงาน
        self.last_critical_message = summary_text

    def handle_error_summary(self, summary_text):
        if self._is_closing or not self.worker:
            return

        if not self.initial_popup_done:
            lines = summary_text.split('\n')
            
            # แก้ไขเงื่อนไข Filter: ให้เก็บบรรทัดที่มี Node และ Addr ไว้
            short_summary = [
                line.strip() for line in lines 
                if "❌" in line or "⚠️" in line or "DETECTED" in line or "Addr:" in line
            ]
            
            display_text = "\n".join(short_summary) if short_summary else "Some nodes are offline."
            
            from PySide6.QtWidgets import QMessageBox
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Warning)
            msg.setWindowTitle("System Check")
            # เพิ่มช่องว่างเพื่อให้ขนาด Popup กว้างขึ้นพอดีกับข้อความ Address
            msg.setText("Device Communication Issues" + " " * 15) 
            msg.setInformativeText(display_text)
            msg.setStandardButtons(QMessageBox.Ok)
            
            if msg.exec() == QMessageBox.Ok:
                self.worker.resume_start()
                self.initial_popup_done = True

    def refresh_active_tab(self):
        if self.tabs.currentIndex() == 0:
            self.rt_tab.update_ui()

    def closeEvent(self, event):
        self._is_closing = True
        if hasattr(self, 'worker'):
            self.worker.stop(); self.worker.wait(2000)
        event.accept()

    # ตัวอย่าง Logic ใน Main UI
    def on_worker_finished(self):
        if self._is_closing:
            return
        if not self.initial_popup_done:
            port = self.config['modbus'].get('port_name', 'Unknown Port')
            msg = QMessageBox() 
            msg.setIcon(QMessageBox.Critical)
            msg.setWindowTitle("System Check")
            msg.setText(" Connection Failed! " + " " * 10) # เว้นวรรคเพื่อขยายขนาดหน้าต่าง
            msg.setInformativeText(f" Check ({port})")
            msg.setStandardButtons(QMessageBox.Ok)
            if msg.exec() == QMessageBox.Ok:
                QApplication.quit() # ปิดโปรแกรมหลังจากกด OK

    @QtCore.Slot(dict, float)
    def on_data_received(self, batch, timestamp):
        max_pts = self.config['app_settings'].get('max_points', 300)
        polling_sec = self.config['app_settings'].get('polling_ms', 1000) / 1000.0
        gap_threshold = polling_sec * 2.5

        # 1. วนลูปจัดการข้อมูล History (Logic เดิมทั้งหมด)
        for ch_key, val in batch.items():
            if ch_key not in self.data_history:
                self.data_history[ch_key], self.time_history[ch_key] = [], []
            if self.time_history[ch_key]:
                last_ts = self.time_history[ch_key][-1]
                if (timestamp - last_ts) > gap_threshold:
                    self.data_history[ch_key].append(float('nan'))
                    self.time_history[ch_key].append(last_ts + 0.001)
            self.data_history[ch_key].append(val)
            self.time_history[ch_key].append(timestamp)
            while len(self.data_history[ch_key]) > max_pts:
                self.data_history[ch_key].pop(0)
                self.time_history[ch_key].pop(0)

        # 2. วนลูปอัปเดต UI บน Card (เพิ่มส่วนเช็ค Quarantine)
        for ch_key, w in self.node_widgets.items():

            # 1. ค้นหาแบบแม่นยำ: วนลูปหาใน config ตรงๆ โดยใช้ชื่อที่เก็บไว้ใน card
            target_ch_status = True  # Default คือใช้งานได้
            
            # ดึงข้อมูลที่เก็บไว้ตอน init_ui (ถ้าคุณเก็บ address ไว้ใน w จะแม่นมาก)
            # แต่ถ้าไม่ได้เก็บ เราจะไล่เช็คจาก config['nodes']
            for node in self.config.get('nodes', []):
                for ch in node.get('channels', []):
                    # สร้าง Key แบบเดียวกับที่ใช้สร้าง Card เพื่อเปรียบเทียบ
                    current_key = f"{node['node_name']}_{ch['name']}"
                    if current_key == ch_key:
                        target_ch_status = ch.get('enabled', True)
                        break

            if not target_ch_status:
                # --- กรณีถูก Quarantine ---
                w['btn'].setStyleSheet("""
                    QPushButton#NodeCard {
                        background-color: rgba(30, 30, 30, 200);
                        border: 2px solid #550000;
                    }
                    QLabel { color: #555555; }
                """)
                w['val_lbl'].setText("QUARANTINE")
                w['val_lbl'].setStyleSheet("color: #444444; font-style: normal;")
                w['perc_lbl'].setText("STOP")
                w['perc_lbl'].setStyleSheet("color: #662222; font-weight: bold;")
                w['led'].set_quarantined(True)

            elif ch_key in batch:
                # --- กรณีปกติ (มีข้อมูลใหม่เข้า) ---
                w['btn'].setEnabled(True)
                val = batch[ch_key]
                percent = min(100, max(0, (val / w['max']) * 100))
                w['val_lbl'].setText(f"{val:,.2f}")
                w['val_lbl'].setStyleSheet("") # คืนค่าสีตาม QSS
                w['perc_lbl'].setText(f"{int(percent)}%")
                if percent >= 90:
                    w['perc_lbl'].setStyleSheet("color: #FF3333; font-weight: bold;")
                elif percent >= 70:
                    w['perc_lbl'].setStyleSheet("color: #FFCC00; font-weight: bold;")
                else:
                    w['perc_lbl'].setStyleSheet("color: #2ECC71; font-weight: bold;")
                    w['led'].set_value(val, w['max'])
            else:
                # ปล่อยให้มันแสดง WAITING ตามเดิม หรือจะปรับแต่งนิดหน่อยให้รู้ว่า "กำลังรอ"
                w['val_lbl'].setText("WAITING...")
                w['val_lbl'].setStyleSheet("color: #888888;")
                w['led'].set_value(0, w['max'])

        # Sync หน้าจออื่น (Logic เดิม)
        if hasattr(self, 'matrix_tab'): self.matrix_tab.update_values(batch)
        if self.tabs.currentIndex() == 0: self.rt_tab.update_ui()


class HorizontalLEDBar(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(12)
        self.percent = 0
        self.segments = 20
        self.is_quarantined = False  # เพิ่ม flag สำหรับสถานะกักตัว

    def set_quarantined(self, status=True):
        self.is_quarantined = status
        self.update()

    def set_value(self, value, max_val):
        self.is_quarantined = False # ถ้ามีค่ามา ให้ยกเลิกสถานะ quarantined
        limit = max_val if max_val > 0 else 100
        self.percent = min(100, max(0, (value / limit) * 100))
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        
        spacing = 1.5
        total_spacing = spacing * (self.segments - 1)
        seg_width = (self.width() - total_spacing) / self.segments
        seg_height = self.height()

        active_segments = int(self.percent / (100 / self.segments))

        for i in range(self.segments):
            x_pos = i * (seg_width + spacing)
            rect = QtCore.QRectF(x_pos, 0, seg_width, seg_height)
            
            # --- แก้ไขเฉพาะส่วนการเลือกสี ---
            if self.is_quarantined:
                color = QtGui.QColor(00, 00, 00, 80) # สีเทาเข้มบ่งบอกว่า Offline
            elif i < active_segments:
                if i >= 18: color = QtGui.QColor("#FF3333")    # 90%+
                elif i >= 14: color = QtGui.QColor("#FFCC00")  # 70%+
                else: color = QtGui.QColor("#2ECC71")          # Normal
            else:
                color = QtGui.QColor(255, 255, 255, 12)        # Empty

            painter.setBrush(QtGui.QBrush(color))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRoundedRect(rect, 1, 1)

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = MonitorApp()
    window.show()
    sys.exit(app.exec())
