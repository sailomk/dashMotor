import time
import asyncio
from PySide6 import QtWidgets, QtCore, QtGui

class BenchmarkPage(QtWidgets.QWidget):
    # row_update_signal: (index ของแถว, ข้อมูล latencies)
    row_update_signal = QtCore.Signal(int, list)
    finished_signal = QtCore.Signal()

    def __init__(self, poller_thread):
        super().__init__()
        self.poller = poller_thread
        self.is_running = False
        self.total_bench_time = 0.0
        
        # เชื่อมต่อ Signals
        self.row_update_signal.connect(self.update_row_ui)
        self.finished_signal.connect(self.finalize_ui)
        
        self.init_ui()

    def init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        self.setStyleSheet("background-color: #0a0a0a; color: #eee;")

        # --- Header Section ---
        header = QtWidgets.QHBoxLayout()
        self.title = QtWidgets.QLabel("📡 MODBUS NETWORK HEALTH BENCHMARK")
        self.title.setStyleSheet("font-size: 18px; font-weight: bold; color: #00FF00;")
        
        self.btn_start = QtWidgets.QPushButton("🚀 START TEST (5 ROUNDS)")
        self.btn_start.clicked.connect(self.start_benchmark)
        self.btn_start.setFixedSize(220, 45)
        self.btn_start.setStyleSheet("""
            QPushButton { background-color: #27ae60; color: white; font-weight: bold; border-radius: 5px; }
            QPushButton:hover { background-color: #2ecc71; }
            QPushButton:disabled { background-color: #444; color: #888; }
        """)
        
        header.addWidget(self.title)
        header.addStretch()
        header.addWidget(self.btn_start)
        layout.addLayout(header)

        # --- Table Configuration ---
        self.nodes_config = self.poller.conf.get('nodes', [])
        num_nodes = len(self.nodes_config)
        
        # จำนวนแถว = จำนวน nodes + 1 (แถวสรุปผลรวม)
        self.table = QtWidgets.QTableWidget(num_nodes + 1, 5)
        self.table.setHorizontalHeaderLabels(["Node ID", "Status", "Avg (ms)", "Max (ms)", "Health"])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet("""
            QTableWidget { background-color: #111; gridline-color: #333; color: white; font-size: 11pt; border: none; }
            QHeaderView::section { background-color: #222; color: #00FF00; font-weight: bold; border: 1px solid #333; }
        """)

        # สร้างแถวข้อมูลสำหรับแต่ละ Node
        for i, node in enumerate(self.nodes_config):
            nid = node.get('node_id')
            name = node.get('node_name', f"Node {nid}")
            is_enabled = any(ch.get('enabled', False) for ch in node.get('channels', []))
            
            id_item = QtWidgets.QTableWidgetItem(f"[{nid:02}] {name}")
            self.table.setItem(i, 0, id_item)
            
            for j in range(1, 5):
                item = QtWidgets.QTableWidgetItem("-")
                item.setTextAlignment(QtCore.Qt.AlignCenter)
                self.table.setItem(i, j, item)
            
            if not is_enabled:
                for j in range(5):
                    self.table.item(i, j).setForeground(QtGui.QColor("#555555"))
                self.table.item(i, 1).setText("DISABLED")

        # --- Summary Row (Last Row) ---
        summary_idx = num_nodes
        summary_name = QtWidgets.QTableWidgetItem("📊 SCAN CYCLE SUMMARY")
        summary_name.setBackground(QtGui.QColor("#1a1a1a"))
        summary_name.setForeground(QtGui.QColor("#fffa65"))
        summary_name.setFont(QtGui.QFont("Arial", weight=QtGui.QFont.Bold))
        self.table.setItem(summary_idx, 0, summary_name)
        
        for j in range(1, 5):
            item = QtWidgets.QTableWidgetItem("-")
            item.setTextAlignment(QtCore.Qt.AlignCenter)
            item.setBackground(QtGui.QColor("#1a1a1a"))
            item.setForeground(QtGui.QColor("#fffa65"))
            self.table.setItem(summary_idx, j, item)

        layout.addWidget(self.table)

    def start_benchmark(self):
        if self.is_running or not self.poller.loop: return
        
        # Reset ตารางก่อนเริ่มใหม่
        num_nodes = len(self.nodes_config)
        for i in range(num_nodes + 1):
            for j in range(1, 5):
                self.table.item(i, j).setText("-")
                self.table.item(i, j).setForeground(QtGui.QColor("#eee"))

        self.is_running = True
        self.btn_start.setEnabled(False)
        self.btn_start.setText("⏳ TESTING...")

        # Pause Dashboard หลัก
        self.poller._paused = True 
        
        # รันใน Loop ของ Worker Thread
        asyncio.run_coroutine_threadsafe(self.run_test_logic(), self.poller.loop)

    async def run_test_logic(self):
        num_rounds = 5
        stats = {node['node_id']: [] for node in self.nodes_config}
        start_bench_ts = time.perf_counter()

        try:
            for r in range(num_rounds):
                for i, node in enumerate(self.nodes_config):
                    if self.poller._stopped: return
                    
                    sid = node['node_id']
                    active_ch = next((ch for ch in node.get('channels', []) if ch.get('enabled')), None)
                    
                    if not active_ch: continue

                    test_addr = active_ch.get('address', 0)
                    is_input = (active_ch.get('type') == 'input')

                    t1 = time.perf_counter()
                    try:
                        if is_input:
                            res = await self.poller.client.read_input_registers(address=test_addr, count=1, slave=sid)
                        else:
                            res = await self.poller.client.read_holding_registers(address=test_addr, count=1, slave=sid)
                        
                        duration = (time.perf_counter() - t1) * 1000
                        stats[sid].append(duration if res and not res.isError() else None)
                            
                    except:
                        stats[sid].append(None)
                    
                    self.row_update_signal.emit(i, list(stats[sid]))
                    await asyncio.sleep(0.02) 

            self.total_bench_time = time.perf_counter() - start_bench_ts
            
        finally:
            self.finished_signal.emit()
            
    @QtCore.Slot(int, list)
    def update_row_ui(self, row_idx, latencies):
        valid_data = [l for l in latencies if l is not None]
        
        status_item = self.table.item(row_idx, 1)
        if not latencies or latencies[-1] is None:
            status_item.setText("❌ TIMEOUT")
            status_item.setForeground(QtGui.QColor("#ff4757"))
        else:
            status_item.setText("✅ ACTIVE")
            status_item.setForeground(QtGui.QColor("#2ed573"))

        if valid_data:
            avg = sum(valid_data) / len(valid_data)
            mx = max(valid_data)
            self.table.item(row_idx, 2).setText(f"{avg:.2f}")
            self.table.item(row_idx, 3).setText(f"{mx:.2f}")
            
            h_item = self.table.item(row_idx, 4)
            if avg < 60:
                h_item.setText("🟢 EXCELLENT")
                h_item.setForeground(QtGui.QColor("#2ed573"))
            elif avg < 150:
                h_item.setText("🟡 LATENCY")
                h_item.setForeground(QtGui.QColor("#e8a03c"))
            else:
                h_item.setText("🔴 CRITICAL")
                h_item.setForeground(QtGui.QColor("#ff4757"))

    @QtCore.Slot()
    def finalize_ui(self):
        self.is_running = False
        self.btn_start.setEnabled(True)
        self.btn_start.setText("🚀 START TEST (5 ROUNDS)")
        
        sum_of_avgs = 0.0
        peak_latency = 0.0
        num_nodes = len(self.nodes_config)

        for i in range(num_nodes):
            avg_txt = self.table.item(i, 2).text()
            max_txt = self.table.item(i, 3).text()
            
            if avg_txt != "-":
                try:
                    v_avg = float(avg_txt)
                    sum_of_avgs += v_avg
                    v_max = float(max_txt)
                    if v_max > peak_latency: peak_latency = v_max
                except: continue

        # อัปเดตแถวสรุปผล (แถวสุดท้าย) ให้เหมือนเดิม 100%
        self.table.item(num_nodes, 1).setText(f"⏱️ Total: {self.total_bench_time:.2f}s")
        self.table.item(num_nodes, 1).setForeground(QtGui.QColor("#00d2d3"))
        
        self.table.item(num_nodes, 2).setText(f"Sum: {sum_of_avgs:.2f}")
        self.table.item(num_nodes, 2).setForeground(QtGui.QColor("#2ecc71"))
        
        self.table.item(num_nodes, 3).setText(f"Peak: {peak_latency:.2f}")
        self.table.item(num_nodes, 3).setForeground(QtGui.QColor("#fffa65"))
        
        self.table.item(num_nodes, 4).setText("✅ FINISHED")
        self.table.item(num_nodes, 4).setForeground(QtGui.QColor("#00FF00"))

        if self.poller:
            self.poller._paused = False
            print("✅ Benchmark Finished, Dashboard Resumed.")