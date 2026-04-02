import sys, os, json, time,math
import numpy as np
from datetime import datetime
from PySide6 import QtWidgets, QtCore, QtGui
import pyqtgraph as pg

# --- 1. RealTimeHUDTab: กู้คืน UI ดั้งเดิมทั้งหมด ---
class RealTimeHUDTab(QtWidgets.QWidget):
    def __init__(self, config, data_hist, time_hist):
        super().__init__()
        self.config = config
        self.data_history = data_hist
        self.time_history = time_hist
        self.current_key = ""
        self.init_ui()

    def init_ui(self):
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Container สำหรับกราฟและ HUD
        self.view_container = QtWidgets.QFrame()
        self.view_container.setStyleSheet("background-color: #0a0a0a; border: none;")
        self.view_layout = QtWidgets.QGridLayout(self.view_container)
        self.view_layout.setContentsMargins(0, 0, 0, 0)

        # --- กู้คืน Grid และสไตล์กราฟดั้งเดิม ---
        self.plot_widget = pg.PlotWidget(axisItems={'bottom': pg.DateAxisItem()})
        self.plot_widget.setBackground('#0a0a0a')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.1) # Grid กลับมาแล้ว
        self.gap_curve = self.plot_widget.plot(
            pen=pg.mkPen(color='#FF3333', width=1, style=QtCore.Qt.DashLine)
        )
        self.gap_curve.setZValue(-1)
        self.curve = self.plot_widget.plot(
            pen=pg.mkPen(color='#2ECC71', width=2.5), antialias=True,connect='finite' 
        )
        
        # Crosshair ดั้งเดิม
        self.rt_vLine = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('#FFCC00', width=1, style=QtCore.Qt.DashLine))
        self.rt_hLine = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('#FFCC00', width=1, style=QtCore.Qt.DashLine))
        self.rt_hover_label = pg.TextItem(anchor=(0,1), color='#EEE', fill=(0,0,0,200))
        self.plot_widget.addItem(self.rt_vLine, ignoreBounds=True)
        self.plot_widget.addItem(self.rt_hLine, ignoreBounds=True)
        self.plot_widget.addItem(self.rt_hover_label, ignoreBounds=True)
        self.plot_widget.scene().sigMouseMoved.connect(self.rt_mouseMoved)

        self.view_layout.addWidget(self.plot_widget, 0, 0)

        # --- กู้คืน Floating HUD Panel ดั้งเดิม (ครบทุก Label) ---
        self.hud_panel = QtWidgets.QFrame(self.view_container)
        self.hud_panel.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.hud_panel.setFixedSize(320, 160)
        self.hud_panel.setStyleSheet("""
            QFrame {
                background-color: rgba(0, 0, 0, 0.3); 
                border-radius: 15px;
                border: 1px solid rgba(255, 255, 255, 0.05);
            }
            QLabel {
                background: transparent;
                border: none;
            }
        """)
        hud_info_layout = QtWidgets.QVBoxLayout(self.hud_panel)
        hud_info_layout.setContentsMargins(0, 0, 20, 0)
        hud_info_layout.setSpacing(1)
        hud_info_layout.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignTop)

        self.status_badge = QtWidgets.QLabel("● WAITING")
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

        self.main_layout.addWidget(self.view_container)

    def rt_mouseMoved(self, evt):
        # 1. เช็คก่อนว่ามีการเลือก Node และมีข้อมูลใน History หรือไม่
        if not hasattr(self, 'current_key') or not self.current_key:
            self.hide_crosshair()
            return
            
        ch_key = self.current_key
        if ch_key not in self.time_history or len(self.time_history[ch_key]) == 0:
            self.hide_crosshair()
            return

        # 2. ตรวจสอบว่าเมาส์อยู่ในพื้นที่ของ PlotWidget หรือไม่
        if self.plot_widget.sceneBoundingRect().contains(evt):
            # แปลงตำแหน่งเมาส์จาก Scene เป็นพิกัดในกราฟ (Data Coordinates)
            mousePoint = self.plot_widget.getViewBox().mapSceneToView(evt)
            
            t_data = list(self.time_history[ch_key])
            v_data = list(self.data_history[ch_key])
            
            # กำหนดระยะ Threshold (ความไวในการดูดเข้าหาจุด) 
            # คำนวณจาก Polling Rate เพื่อให้ Mouse Snap ได้แม่นยำ
            polling_ms = self.config['app_settings'].get('polling_ms', 1000)
            threshold = (polling_ms * 5.0) / 1000.0 
            
            # 3. เช็คว่าตำแหน่งเมาส์อยู่ในช่วงเวลาที่มีข้อมูล (X-Axis) หรือไม่
            if t_data[0] - threshold <= mousePoint.x() <= t_data[-1] + threshold:
                # ใช้ numpy หา Index ของจุดที่ใกล้เมาส์ที่สุด
                import numpy as np
                t_array = np.array(t_data)
                idx = (np.abs(t_array - mousePoint.x())).argmin()
                
                ax, ay = t_data[idx], v_data[idx]
                
                # อัปเดตตำแหน่งเส้น Crosshair
                self.rt_vLine.setPos(ax)
                self.rt_hLine.setPos(ay)
                
                # แสดงเส้น
                self.rt_vLine.show()
                self.rt_hLine.show()
                
                # อัปเดต Label (เวลา และ ค่า)
                from datetime import datetime
                ts = datetime.fromtimestamp(ax).strftime('%H:%M:%S')
                label_html = f"""
                    <div style='background: rgba(0, 0, 0, 180); 
                                border: 1px solid #2ECC71; 
                                color: white; 
                                padding: 4px; 
                                border-radius: 4px;
                                font-family: Consolas;'>
                        <b>Time:</b> {ts}<br>
                        <b>Value:</b> {ay:.2f}
                    </div>
                """
                self.rt_hover_label.setHtml(label_html)
                self.rt_hover_label.setPos(ax, ay)
                self.rt_hover_label.show()
                return # จบการทำงานแบบโชว์เส้น

        # 4. หากไม่เข้าเงื่อนไขใดๆ (เมาส์ออกนอกกราฟ) ให้ซ่อนเส้นทั้งหมด
        self.hide_crosshair()

    def hide_crosshair(self):
        """ฟังก์ชันช่วยซ่อนเส้น Crosshair ทั้งหมด"""
        if hasattr(self, 'rt_vLine'): self.rt_vLine.hide()
        if hasattr(self, 'rt_hLine'): self.rt_hLine.hide()
        if hasattr(self, 'rt_hover_label'): self.rt_hover_label.hide()
        
    def update_ui(self):
        # --- 1. ตรวจสอบว่ามีการเลือก Node หรือยัง ---
        if not hasattr(self, 'current_key') or not self.current_key:
            self.status_badge.setText("● WAITING")
            return

        ch_key = self.current_key
        
        # --- 2. อัปเดตข้อมูล Static บน HUD (Name & Addr) ---
        try:
            found = False
            for node_cfg in self.config.get('nodes', []):
                for ch in node_cfg.get('channels', []):
                    check_key = f"{node_cfg['node_name']}_{ch['name']}"
                    if check_key == ch_key:
                        self.node_name_lbl.setText(node_cfg['node_name'].upper())
                        self.node_addr_lbl.setText(f"ADDR: 0x{ch.get('address', 0):04X}")
                        found = True
                        break
                if found: break
        except Exception as e:
            print(f"Error updating static HUD: {e}")

        # --- 3. ตรวจสอบข้อมูลใน History (Data Check) ---
        polling_ms = self.config['app_settings'].get('polling_ms', 1000)
        staleness_timeout = (polling_ms * 2.5) / 1000.0 
        now = time.time()
        
        has_data = ch_key in self.data_history and len(self.data_history[ch_key]) > 0
        
        if has_data:
            t_raw = list(self.time_history[ch_key])
            v_raw = list(self.data_history[ch_key])
            
            # --- [NEW] กรองข้อมูลสำหรับเส้นประสีแดง (Gap Line) ---
            # กรองเอาเฉพาะจุดที่เป็นตัวเลขจริง (ไม่ใช่ NaN) เพื่อวาดเส้นประเชื่อมช่องว่าง
            gap_x = [t for i, t in enumerate(t_raw) if not math.isnan(v_raw[i])]
            gap_y = [v for v in v_raw if not math.isnan(v)]
            
            if not gap_y: return # ป้องกันกรณีข้อมูลมีแต่ NaN

            latest_time, latest_val = gap_x[-1], gap_y[-1]
            global_max_y = max(gap_y)
            
            # --- 4. Dynamic Headroom ---
            y_upper_limit = global_max_y * 1.35 if global_max_y > 0 else 100
            self.plot_widget.setYRange(0, y_upper_limit, padding=0)

            # --- 5. Style Logic (Freshness & Alarm) ---
            is_fresh = (now - latest_time) < staleness_timeout
            alarm_val = self.config['app_settings'].get('alarm_threshold', 500)
            is_alarm = latest_val >= alarm_val

            # กำหนดสีตามสถานะ
            val_color_str = "rgba(46, 204, 113, 0.8)" # เขียว (ปกติ)
            graph_qcolor = QtGui.QColor(46, 204, 113, 230)
            
            if not is_fresh:
                val_color_str = "rgba(150, 150, 150, 0.3)" # เทา (Offline)
                self.status_badge.setText("● OFFLINE")
            elif is_alarm:
                val_color_str = "rgba(255, 51, 51, 0.8)"   # แดง (Alarm)
                self.status_badge.setText("● ALARM")
            else:
                self.status_badge.setText("● LIVE DATA")

            # อัปเดตตัวเลขและ Badge
            self.value_lbl.setText(f"{latest_val:,.2f}")
            self.value_lbl.setStyleSheet(f"color: {val_color_str}; font-size: 42pt; font-weight: 800; background: transparent;")
            self.status_badge.setStyleSheet(f"color: {val_color_str}; background: rgba(255,255,255,0.05); border-radius:4px; padding:2px 8px;")

            # --- 6. วาดเส้นกราฟ (Dual Plotting) ---
            
            # A. วาดเส้นประสีแดง (เลเยอร์หลัง)
            if hasattr(self, 'gap_curve'):
                self.gap_curve.setData(gap_x, gap_y)
            
            # B. วาดเส้นหลัก (สีตามสถานะ) - เส้นนี้จะแหว่งตรงที่มี NaN
            self.curve.setData(t_raw, v_raw)
            self.curve.setPen(pg.mkPen(color=graph_qcolor, width=2.5))

            # --- 7. Dynamic HUD Position ---
            def reposition_hud():
                if not hasattr(self, 'hud_panel'): return
                target_x = self.view_container.width() - self.hud_panel.width() - 25
                
                if global_max_y <= 0.01:
                    target_y = 20
                else:
                    vb = self.plot_widget.getViewBox()
                    scene_pt = vb.mapViewToScene(QtCore.QPointF(latest_time, global_max_y))
                    local_pt = self.view_container.mapFromGlobal(self.plot_widget.mapToGlobal(scene_pt.toPoint()))
                    val_bottom_offset = 135 
                    target_y = local_pt.y() - val_bottom_offset - 15

                if target_y < 10: target_y = 10
                if target_y > self.view_container.height() - self.hud_panel.height():
                    target_y = self.view_container.height() - self.hud_panel.height() - 10
                
                self.hud_panel.move(int(target_x), int(target_y))
                self.hud_panel.raise_()

            QtCore.QTimer.singleShot(1, reposition_hud)

            # --- 8. X-AXIS Logic ---
            view_range = self.config['app_settings'].get('view_range_s', 120)
            if (latest_time - gap_x[0]) < view_range:
                self.plot_widget.setXRange(gap_x[0], gap_x[0] + view_range, padding=0)
            else:
                self.plot_widget.setXRange(latest_time - view_range, latest_time, padding=0)
        else:
            self.value_lbl.setText("0.00")
            self.status_badge.setText("● WAITING")
            self.status_badge.setStyleSheet("color: rgba(150,150,150,0.8); background: rgba(255,255,255,0.05); border-radius:4px; padding:2px 8px;")
            
            def init_hud_pos():
                if hasattr(self, 'view_container'):
                    target_x = self.view_container.width() - self.hud_panel.width() - 25
                    self.hud_panel.move(int(target_x), 20)
            QtCore.QTimer.singleShot(1, init_hud_pos)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # ตำแหน่งเริ่มต้น HUD เมื่อ resize
        self.hud_panel.move(self.width() - 345, 20)
    
    def set_active_node(self, display_name):
        self.current_display_name = display_name
        self.current_key = display_name.replace(" - ", "_")
        self.update_ui()

