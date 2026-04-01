import sys, os, json, time
from PySide6 import QtWidgets, QtCore, QtGui
import pyqtgraph as pg

# Import Modules
from core.modbus_worker import AsyncPollWorker
from ui.dashboard_tab import RealTimeHUDTab
from ui.all_nodes_view import AllNodesDashboard
from ui.history_tab import HistoryViewerTab
from ui.error_tab import ErrorSummaryTab
from ui.benchmark_page import BenchmarkPage

class MonitorApp(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        
        # 1. Config & Paths
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.config = self.load_config()
        self.data_history = {} 
        self.time_history = {} 
        
        self.log_path = self.prepare_dir(self.config['app_settings']['log_dir'])
        self.debug_path = self.prepare_dir(self.config['debug']['log_dir'])

        # 2. Worker Setup
        self.worker = AsyncPollWorker(self.config, self.log_path, self.debug_path)

        # 3. UI Setup (Latest Layout)
        self.init_ui()
        self.load_styles()

        # 4. Signal Connection
        self.worker.data_signal.connect(self.on_data_received)
        self.worker.error_summary_signal.connect(self.error_tab.update_error_log)
        
        # 5. Start
        self.worker.start()

        self.ui_refresh_timer = QtCore.QTimer()
        self.ui_refresh_timer.timeout.connect(self.refresh_active_tab)
        self.ui_refresh_timer.start(200)

        self.setWindowTitle("Phoenix Industrial Monitor - v1.2.0")
        self.resize(1280, 850)

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
                print("✅ Stylesheet applied!")

    def init_ui(self):
        self.central_widget = QtWidgets.QWidget()
        self.setCentralWidget(self.central_widget)
        main_vbox = QtWidgets.QVBoxLayout(self.central_widget)
        main_vbox.setContentsMargins(0, 0, 0, 0)
        main_vbox.setSpacing(0)

        self.tabs = QtWidgets.QTabWidget()
        main_vbox.addWidget(self.tabs)

        # Create Tabs
        self.rt_tab = RealTimeHUDTab(self.config, self.data_history, self.time_history)
        self.matrix_tab = AllNodesDashboard(self.config)
        self.history_tab = HistoryViewerTab(self.config)
        self.error_tab = ErrorSummaryTab(self) 
        self.bench_tab = BenchmarkPage(self.worker)

        """     
        self.tabs.addTab(self.rt_tab, "🚀 Real-Time Monitor")
        self.tabs.addTab(self.matrix_tab, "📊 All Nodes Dashboard")
        self.tabs.addTab(self.history_tab, "📜 History Viewer")
        self.tabs.addTab(self.error_tab, "🚨 Error Summary")
        self.tabs.addTab(self.bench_tab, "📡 Benchmark Test") 
        """


        self.tabs.addTab(self.rt_tab, " Real-Time Monitor")
        self.tabs.addTab(self.matrix_tab, " All Nodes Dashboard")
        self.tabs.addTab(self.history_tab, " History Viewer")
        self.tabs.addTab(self.error_tab, " Error Summary")
        self.tabs.addTab(self.bench_tab, " Benchmark Test")
        pg.setConfigOptions(antialias=True)

    def request_error_summary(self):
        if self.worker: self.worker.send_error_summary()

    def clear_error_stats(self):
        if self.worker:
            from core.modbus_worker import ErrorAggregator
            self.worker.error_aggregator = ErrorAggregator(debug_dir=self.worker.debug_path)
            self.worker.send_error_summary()

    @QtCore.Slot(dict, float)
    def on_data_received(self, batch, timestamp):
        max_pts = self.config['app_settings'].get('max_points', 300)
        for ch_key, val in batch.items():
            if ch_key not in self.data_history:
                self.data_history[ch_key], self.time_history[ch_key] = [], []
            self.data_history[ch_key].append(val)
            self.time_history[ch_key].append(timestamp)
            if len(self.data_history[ch_key]) > max_pts:
                self.data_history[ch_key].pop(0)
                self.time_history[ch_key].pop(0)
        self.matrix_tab.update_values(batch)

    def refresh_active_tab(self):
        if self.tabs.currentIndex() == 0:
            self.rt_tab.update_ui()

    def closeEvent(self, event):
        """ปิดแบบ Clean Exit 100%"""
        print("\nShutting down system...")
        if hasattr(self, 'ui_refresh_timer'):
            self.ui_refresh_timer.stop()
            
        if hasattr(self, 'worker'):
            self.worker.stop()
            # รอให้ Thread จบงานฟังก์ชัน run() เอง (Timeout 3 วิ)
            if not self.worker.wait(3000): 
                print("⚠️ Worker force termination...")
                self.worker.terminate()
                self.worker.wait()

        print("✅ Shutdown complete.")
        event.accept()

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    
    # ธีมพื้นฐาน
    app.setStyle("Windows")
    palette = QtGui.QPalette()
    palette.setColor(QtGui.QPalette.Window, QtGui.QColor(25, 25, 25))
    palette.setColor(QtGui.QPalette.WindowText, QtCore.Qt.white)
    app.setPalette(palette)

    window = MonitorApp()
    window.show()
    sys.exit(app.exec())