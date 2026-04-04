from PySide6 import QtWidgets, QtCore, QtGui
import pyqtgraph as pg
import os, glob, csv, numpy as np
from datetime import datetime

class HistoryViewerTab(QtWidgets.QWidget):
    def __init__(self, conf):
        super().__init__()
        self.conf = conf
        self.init_ui()
        self.plot.installEventFilter(self)
        self.plot.scene().sigMouseMoved.connect(self.mouse_moved)
        #self.plot.scene().sigLeaveEvent.connect(lambda: [self.vLine.hide(), self.hLine.hide(), self.label.hide()])

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

        load_btn = QtWidgets.QPushButton(" 🔍 LOAD HISTORY ")
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
        # 1. Get filter criteria from UI
        target_date = self.date_edit.date().toString("dd-MM-yy")
        sel_node, sel_addr = self.node_sel.currentData()
        
        # 2. Locate files
        log_dir = self.conf['app_settings'].get('log_dir', 'logs')
        search_path = os.path.join(log_dir, f"log_{target_date}_*.csv")
        files = sorted(glob.glob(search_path))
        
        if not files:
            QtWidgets.QMessageBox.information(self, "No Data", f"ไม่พบข้อมูลของวันที่ {target_date}")
            return

        h_time, h_val = [], []
        last_ts = None
        GAP_THRESHOLD = 30 * 60  # 30 minutes in seconds

        # 3. Parse CSV files
        for f_path in files:
            try:
                with open(f_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # Filter by Node ID and Address
                        if int(row['node_id']) == sel_node and int(row['address']) == sel_addr:
                            # Match your format: "dd-mm-yy HH:MM:S"
                            dt = datetime.strptime(row['date/time'], "%d-%m-%y %H:%M:%S")
                            current_ts = dt.timestamp()

                            # Check for gaps > 30 minutes
                            if last_ts is not None and (current_ts - last_ts) > GAP_THRESHOLD:
                                # Insert NaN to break the line connection
                                h_time.append(last_ts + 1) # Insert 1 second after last data
                                h_val.append(np.nan)

                            h_time.append(current_ts)
                            h_val.append(float(row['Value']))
                            last_ts = current_ts
            except Exception as e:
                print(f"Error processing {f_path}: {e}")
                continue

        # 4. Update Plot
        if h_time:
            # connect='finite' ensures the line breaks at NaN values
            self.curve.setData(h_time, h_val, connect='finite')

            # Calculate Y-Axis range with padding
            # We convert to numpy array to easily filter out NaNs for min/max calculation
            np_vals = np.array(h_val)
            valid_vals = np_vals[~np.isnan(np_vals)]
            
            if len(valid_vals) > 0:
                v_min = np.min(valid_vals)
                v_max = np.max(valid_vals)
                v_range = v_max - v_min
                
                # If all values are the same, use a default padding of 1.0
                padding = v_range * 0.2 if v_range != 0 else 1.0
                
                # Set the Y range with top and bottom spacing
                self.plot.setAcceptHoverEvents(True)
                self.plot.setYRange(v_min - padding, v_max + padding, padding=0)
            
            # Keep X-axis auto-scaling to show the time range
            self.plot.enableAutoRange(axis='x')
            
        else:
            self.curve.clear()
            QtWidgets.QMessageBox.warning(self, "Empty", "ไม่มีข้อมูลสำหรับเซนเซอร์ที่เลือกในไฟล์")
 
    def eventFilter(self, source, event):
        # ตรวจสอบว่าเมาส์ "Leave" (ออกจากพื้นที่) หรือไม่
        if event.type() == QtCore.QEvent.Leave and source is self.plot:
            self.vLine.hide()
            self.hLine.hide()
            self.label.hide()
        return super().eventFilter(source, event)

    def mouse_moved(self, evt):
        # 1. รับตำแหน่งเมาส์ (Signal มักส่งพิกัดตรงมาให้)
        pos = evt
        vb = self.plot.getViewBox()
        
        # 2. ตรวจสอบเบื้องต้นว่าเมาส์อยู่ใน Scene หรือไม่
        if self.plot.sceneBoundingRect().contains(pos):
            # 3. คำนวณขอบเขตพื้นที่วาดกราฟด้านใน (Inner Plot Area เท่านั้น)
            # วิธีนี้จะตัดพื้นที่แกน X, แกน Y, และ Margin ขอบขวา/บน ออกทั้งหมด
            inner_rect = vb.mapRectToScene(vb.boundingRect())
            
            # 4. เช็คว่าตำแหน่งเมาส์ (pos) อยู่ในพื้นที่วาดกราฟจริงหรือไม่
            if inner_rect.contains(pos):
                # แปลงพิกัดหน้าจอเป็นค่าในกราฟ (Time/Value)
                mousePoint = vb.mapSceneToView(pos)
                
                # --- แสดงผล Crosshair และ Label ---
                self.vLine.show()
                self.hLine.show()
                self.label.show()
                
                # อัปเดตตำแหน่งเส้น
                self.vLine.setPos(mousePoint.x())
                self.hLine.setPos(mousePoint.y())
                
                # อัปเดตข้อความ Label
                try:
                    ts = datetime.fromtimestamp(mousePoint.x()).strftime('%H:%M:%S')
                    self.label.setHtml(
                        f"<div style='background: rgba(0,0,0,160); color: white; padding: 4px; border-radius: 3px;'>"
                        f"Time: {ts}<br>Value: {mousePoint.y():.2f}</div>"
                    )
                    # วางตำแหน่ง Label ให้ตามเมาส์ (เยื้องไปทางขวาบนเล็กน้อย)
                    self.label.setPos(mousePoint.x(), mousePoint.y())
                except Exception:
                    pass
                
                return # อยู่ในพื้นที่ที่ถูกต้อง -> จบการทำงาน (ไม่ไปทำส่วนซ่อน)

        # 5. หากอยู่นอกพื้นที่กราฟ (รวมถึงพื้นที่แกน X/Y, ขอบขวา, ขอบบน หรือนอกหน้าต่าง) -> ซ่อนทันที
        self.vLine.hide()
        self.hLine.hide()
        self.label.hide()


