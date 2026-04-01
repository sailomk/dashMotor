from PySide6 import QtWidgets, QtCore, QtGui
import pyqtgraph as pg
import os, glob, csv, time
from datetime import datetime

class HistoryViewerTab(QtWidgets.QWidget):
    def __init__(self, conf):
        super().__init__()
        self.conf = conf
        self.init_ui()

    def init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        
        # --- Control Panel ---
        ctrl_layout = QtWidgets.QHBoxLayout()
        self.date_edit = QtWidgets.QDateEdit(QtCore.QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        
        self.node_sel = QtWidgets.QComboBox()
        # Populate selector จาก config
        for node in self.conf.get('nodes', []):
            nid = node.get('node_id')
            for ch in node.get('channels', []):
                if ch.get('enabled', True):
                    display = f"Node {nid} | {node.get('node_name')} - {ch.get('name')}"
                    self.node_sel.addItem(display, (nid, ch.get('address')))

        load_btn = QtWidgets.QPushButton("🔍 LOAD HISTORY")
        load_btn.clicked.connect(self.load_data)
        load_btn.setMinimumHeight(35)
        load_btn.setStyleSheet("background: #3399ff; color: white; font-weight: bold; border-radius: 4px;")

        ctrl_layout.addWidget(QtWidgets.QLabel("Date:"))
        ctrl_layout.addWidget(self.date_edit)
        ctrl_layout.addWidget(QtWidgets.QLabel("Sensor:"))
        ctrl_layout.addWidget(self.node_sel)
        ctrl_layout.addWidget(load_btn)
        ctrl_layout.addStretch()
        layout.addLayout(ctrl_layout)

        # --- Graph Area ---
        self.plot = pg.PlotWidget(axisItems={'bottom': pg.DateAxisItem()})
        self.plot.setBackground('#050505')
        self.plot.showGrid(x=True, y=True, alpha=0.2)
        self.curve = self.plot.plot(pen=pg.mkPen(color='#3399ff', width=2))
        
        # Crosshair สำหรับหน้า History
        self.vLine = pg.InfiniteLine(angle=90, movable=False, pen='#888')
        self.hLine = pg.InfiniteLine(angle=0, movable=False, pen='#888')
        self.plot.addItem(self.vLine, ignoreBounds=True)
        self.plot.addItem(self.hLine, ignoreBounds=True)
        self.label = pg.TextItem(anchor=(0,1), color='#EEE', fill=(0,0,0,200))
        self.plot.addItem(self.label, ignoreBounds=True)
        
        self.plot.scene().sigMouseMoved.connect(self.mouse_moved)
        layout.addWidget(self.plot)

    def load_data(self):
        target_date = self.date_edit.date().toString("yyyy-MM-dd")
        sel_node, sel_addr = self.node_sel.currentData()
        
        log_dir = self.conf['app_settings'].get('log_dir', 'logs')
        files = sorted(glob.glob(os.path.join(log_dir, f"log_{target_date}_*.csv")))
        
        if not files:
            QtWidgets.QMessageBox.information(self, "No Data", f"ไม่พบข้อมูลของวันที่ {target_date}")
            return

        h_time, h_val = [], []
        for f_path in files:
            try:
                with open(f_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if int(row['node_id']) == sel_node and int(row['address']) == sel_addr:
                            dt = datetime.strptime(row['date/time'], "%Y-%m-%d %H:%M:%S.%f")
                            h_time.append(dt.timestamp())
                            h_val.append(float(row['Value']))
            except: continue

        if h_time:
            self.curve.setData(h_time, h_val)
            self.plot.enableAutoRange()
        else:
            self.curve.clear()
            QtWidgets.QMessageBox.warning(self, "Empty", "ไม่มีข้อมูลสำหรับเซนเซอร์ที่เลือกในไฟล์")

    def mouse_moved(self, evt):
        if self.plot.sceneBoundingRect().contains(evt):
            mousePoint = self.plot.getViewBox().mapSceneToView(evt)
            self.vLine.setPos(mousePoint.x())
            self.hLine.setPos(mousePoint.y())
            ts = datetime.fromtimestamp(mousePoint.x()).strftime('%H:%M:%S')
            self.label.setHtml(f"<div style='color:white;'>Time: {ts}<br>Value: {mousePoint.y():.2f}</div>")
            self.label.setPos(mousePoint.x(), mousePoint.y())