import time
from PySide6 import QtWidgets, QtCore, QtGui
import pyqtgraph as pg

class RealTimeHUDTab(QtWidgets.QWidget):
    def __init__(self, conf, data_hist, time_hist):
        super().__init__()
        self.conf = conf
        self.data_history = data_hist
        self.time_history = time_hist
        self.init_ui()

    def init_ui(self):
        # --- Main Layout ---
        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- ส่วนที่ 1: Sidebar (Left) ---
        self.node_list = QtWidgets.QListWidget()
        self.node_list.setObjectName("ModernList")
        self.node_list.setFixedWidth(220)
        
        for node_cfg in self.conf.get('nodes', []):
            for ch in node_cfg.get('channels', []):
                if ch.get('enabled', True):
                    self.node_list.addItem(f"{node_cfg['node_name']} - {ch['name']}")
        
        if self.node_list.count() > 0:
            self.node_list.setCurrentRow(0)
        
        main_layout.addWidget(self.node_list)

        # --- ส่วนที่ 2: HUD Container ---
        self.graph_container = QtWidgets.QFrame()
        self.graph_container.setStyleSheet("background-color: #0a0a0a; border: none;")
        hud_layout = QtWidgets.QGridLayout(self.graph_container)
        hud_layout.setContentsMargins(0, 0, 0, 0)

        self.plot_widget = pg.PlotWidget(axisItems={'bottom': pg.DateAxisItem()})
        self.plot_widget.setBackground('#0a0a0a')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.1)
        
        self.curve = self.plot_widget.plot(pen=pg.mkPen(color='#2ECC71', width=2.5), antialias=True)
        hud_layout.addWidget(self.plot_widget, 0, 0)

        self.rt_vLine = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('#FFCC00', width=1, style=QtCore.Qt.DashLine))
        self.rt_hLine = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('#FFCC00', width=1, style=QtCore.Qt.DashLine))
        self.plot_widget.addItem(self.rt_vLine, ignoreBounds=True)
        self.plot_widget.addItem(self.rt_hLine, ignoreBounds=True)
        self.rt_hover_label = pg.TextItem(anchor=(0,1), color='#EEE', fill=(0,0,0,200))
        self.plot_widget.addItem(self.rt_hover_label, ignoreBounds=True)
        
        self.plot_widget.scene().sigMouseMoved.connect(self.rt_mouseMoved)

        # 2.2 Floating HUD Panel
        self.hud_panel = QtWidgets.QFrame(self.graph_container) 
        self.hud_panel.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents) 
        self.hud_panel.setFixedSize(320, 160)
        self.hud_panel.setStyleSheet("background: transparent; border: none;")
        
        hud_info_layout = QtWidgets.QVBoxLayout(self.hud_panel)
        hud_info_layout.setContentsMargins(0, 0, 20, 0)
        hud_info_layout.setSpacing(1)
        hud_info_layout.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignTop)

        self.status_badge = QtWidgets.QLabel("● WAITING")
        self.status_badge.setStyleSheet("color: rgba(150,150,150,0.8); background: rgba(255,255,255,0.05); border-radius:4px; padding:2px 8px; font-size: 8pt;")
        
        self.node_name_lbl = QtWidgets.QLabel("SELECT NODE")
        self.node_name_lbl.setStyleSheet("color: rgba(255, 255, 255, 0.4); font-size: 11pt; font-weight: bold;")
        
        self.node_addr_lbl = QtWidgets.QLabel("0x0000")
        self.node_addr_lbl.setStyleSheet("color: rgba(46, 204, 113, 0.4); font-size: 9pt; font-family: 'Consolas';")
        
        self.value_lbl = QtWidgets.QLabel("0.00")
        self.value_lbl.setStyleSheet("color: rgba(46, 204, 113, 0.9); font-size: 42pt; font-weight: 800;")

        hud_info_layout.addWidget(self.status_badge, 0, QtCore.Qt.AlignRight)
        hud_info_layout.addWidget(self.node_name_lbl, 0, QtCore.Qt.AlignRight)
        hud_info_layout.addWidget(self.node_addr_lbl, 0, QtCore.Qt.AlignRight)
        hud_info_layout.addWidget(self.value_lbl, 0, QtCore.Qt.AlignRight)

        main_layout.addWidget(self.graph_container)

    def update_ui(self):
        current_item = self.node_list.currentItem()
        if not current_item: return
            
        display_text = current_item.text()
        ch_key = display_text.replace(" - ", "_")
        
        # 1. Update Static HUD Text
        try:
            parts = display_text.split(" - ")
            self.node_name_lbl.setText(parts[0].upper())
            for node_cfg in self.conf.get('nodes', []):
                if node_cfg.get('node_name') == parts[0]:
                    for ch in node_cfg.get('channels', []):
                        if ch.get('name') == parts[1]:
                            self.node_addr_lbl.setText(f"ADDR: 0x{ch.get('address', 0):04X}")
                            break
        except: pass

        # 2. Data Check
        polling_ms = self.conf['app_settings'].get('polling_ms', 1000)
        staleness_timeout = (polling_ms * 2.5) / 1000.0 
        now = time.time()
        has_data = ch_key in self.data_history and len(self.data_history[ch_key]) > 0
        
        if has_data:
            t_data = list(self.time_history[ch_key])
            v_data = list(self.data_history[ch_key])
            latest_time, latest_val = t_data[-1], v_data[-1]
            global_max_y = max(v_data)
            
            # 3. Dynamic Headroom
            y_upper_limit = global_max_y * 1.35 if global_max_y > 0 else 100
            self.plot_widget.setYRange(0, y_upper_limit, padding=0)

            # 4. Style Logic
            is_fresh = (now - latest_time) < staleness_timeout
            alarm_val = self.conf['app_settings'].get('alarm_threshold', 500)
            is_alarm = latest_val >= alarm_val

            val_color_str = "rgba(46, 204, 113, 0.9)"
            graph_qcolor = QtGui.QColor(46, 204, 113, 230)
            
            if not is_fresh:
                val_color_str = "rgba(150, 150, 150, 0.4)"
                graph_qcolor = QtGui.QColor(150, 150, 150, 100)
                self.status_badge.setText("● OFFLINE")
            elif is_alarm:
                val_color_str = "rgba(255, 51, 51, 0.9)"
                graph_qcolor = QtGui.QColor(255, 51, 51, 230)
                self.status_badge.setText("● ALARM")
            else:
                self.status_badge.setText("● LIVE DATA")

            self.value_lbl.setText(f"{latest_val:,.2f}")
            self.value_lbl.setStyleSheet(f"color: {val_color_str}; font-size: 42pt; font-weight: 800; background: transparent;")
            self.status_badge.setStyleSheet(f"color: {val_color_str}; background: rgba(255,255,255,0.05); border-radius:4px; padding:2px 8px;")

            self.curve.setData(t_data, v_data)
            self.curve.setPen(pg.mkPen(color=graph_qcolor, width=2.5))

            # 5. Dynamic Floating Position (FIXED Logic)
            def reposition_hud():
                if not hasattr(self, 'hud_panel'): return
                
                target_x = self.graph_container.width() - self.hud_panel.width() - 25
                
                # ถ้าข้อมูลเป็น 0 หรือน้อยมาก ให้ HUD อยู่มุมขวาบนคงที่
                if global_max_y <= 0.01:
                    target_y = 20
                else:
                    vb = self.plot_widget.getViewBox()
                    # ใช้ค่า global_max_y เป็นเพดานในการวาง HUD
                    scene_pt = vb.mapViewToScene(QtCore.QPointF(latest_time, global_max_y))
                    local_pt = self.graph_container.mapFromGlobal(self.plot_widget.mapToGlobal(scene_pt.toPoint()))
                    
                    val_bottom_offset = 135 
                    target_y = local_pt.y() - val_bottom_offset - 15

                # Clamp ตำแหน่งไม่ให้หลุดขอบบน-ล่าง
                if target_y < 10: target_y = 10
                if target_y > self.graph_container.height() - self.hud_panel.height():
                    target_y = self.graph_container.height() - self.hud_panel.height() - 10
                
                self.hud_panel.move(int(target_x), int(target_y))
                self.hud_panel.raise_()

            QtCore.QTimer.singleShot(1, reposition_hud)

            # 6. X-AXIS Logic
            view_range = self.conf['app_settings'].get('view_range_s', 120)
            if (latest_time - t_data[0]) < view_range:
                self.plot_widget.setXRange(t_data[0], t_data[0] + view_range, padding=0)
            else:
                self.plot_widget.setXRange(latest_time - view_range, latest_time, padding=0)
        else:
            # --- เมื่อไม่มีข้อมูลเลย (Starting State) ---
            self.value_lbl.setText("0.00")
            self.status_badge.setText("● WAITING")
            self.status_badge.setStyleSheet("color: rgba(150,150,150,0.8); background: rgba(255,255,255,0.05); border-radius:4px; padding:2px 8px;")
            
            # บังคับให้ HUD ไปอยู่ที่มุมขวาบนเมื่อไม่มีข้อมูล
            def init_hud_pos():
                target_x = self.graph_container.width() - self.hud_panel.width() - 25
                self.hud_panel.move(int(target_x), 20)
            QtCore.QTimer.singleShot(1, init_hud_pos)

    def rt_mouseMoved(self, evt):
        if self.plot_widget.sceneBoundingRect().contains(evt):
            current_item = self.node_list.currentItem()
            if not current_item: return
            ch_key = current_item.text().replace(" - ", "_")
            
            if ch_key in self.time_history and len(self.time_history[ch_key]) > 0:
                mousePoint = self.plot_widget.getViewBox().mapSceneToView(evt)
                t_data = self.time_history[ch_key]
                v_data = self.data_history[ch_key]
                
                polling_ms = self.conf['app_settings'].get('polling_ms', 1000)
                threshold = (polling_ms * 5.0) / 1000.0 
                
                if t_data[0] - threshold <= mousePoint.x() <= t_data[-1] + threshold:
                    import numpy as np
                    t_array = np.array(t_data)
                    idx = (np.abs(t_array - mousePoint.x())).argmin()
                    
                    ax, ay = t_data[idx], v_data[idx]
                    self.rt_vLine.setPos(ax)
                    self.rt_hLine.setPos(ay)
                    self.rt_vLine.show()
                    self.rt_hLine.show()
                    
                    from datetime import datetime
                    ts = datetime.fromtimestamp(ax).strftime('%H:%M:%S')
                    label_html = f"<div style='background:rgba(0,0,0,150);color:white;padding:3px;'>T: {ts}<br>V: {ay:.2f}</div>"
                    self.rt_hover_label.setHtml(label_html)
                    self.rt_hover_label.setPos(ax, ay)
                    self.rt_hover_label.show()
                    return
        self.rt_vLine.hide()
        self.rt_hLine.hide()
        self.rt_hover_label.hide()