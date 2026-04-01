from PySide6 import QtWidgets, QtCore, QtGui

class AllNodesDashboard(QtWidgets.QWidget):
    def __init__(self, conf):
        super().__init__()
        self.conf = conf
        self.node_cards = {} # เก็บ reference ของ label เพื่อใช้ update ค่า
        self.init_ui()

    def init_ui(self):
        self.setObjectName("MainContent")
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # Header
        title = QtWidgets.QLabel("Nodes & Registers Matrix")
        title.setStyleSheet("color: #FFFFFF; font-size: 20pt; font-weight: bold;")
        main_layout.addWidget(title)

        # Scroll Area
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        container = QtWidgets.QWidget()
        self.grid_layout = QtWidgets.QGridLayout(container)
        self.grid_layout.setSpacing(20)
        self.grid_layout.setAlignment(QtCore.Qt.AlignTop)

        nodes = self.conf.get('nodes', [])
        # วางการ์ดแบบ 2 คอลัมน์ (Index // 2, Index % 2)
        for i, node_cfg in enumerate(nodes):
            card = self.create_node_card(node_cfg)
            self.grid_layout.addWidget(card, i // 2, i % 2)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    def create_node_card(self, node_cfg):
        node_id = node_cfg.get('node_id')
        node_name = node_cfg.get('node_name', f'Node {node_id}')
        
        card_frame = QtWidgets.QFrame()
        card_frame.setObjectName("NodeCard")
        # สไตล์ของการ์ด (สามารถย้ายไปไว้ใน QSS ได้)
        card_frame.setStyleSheet("""
            QFrame#NodeCard {
                background-color: #1a1a1a;
                border: 1px solid #333;
                border-radius: 12px;
            }
        """)
        
        layout = QtWidgets.QVBoxLayout(card_frame)
        
        # หัวการ์ด
        header = QtWidgets.QLabel(f"ID: {node_id:02} • {node_name}")
        header.setStyleSheet("color: #00FF00; font-weight: bold; font-size: 12pt; border: none;")
        layout.addWidget(header)

        # Grid สำหรับ Registers ภายในแผง
        reg_layout = QtWidgets.QGridLayout()
        reg_layout.setSpacing(10)
        

        enabled_chs = [ch for ch in node_cfg.get('channels', []) if ch.get('enabled', True)]
        for idx, ch in enumerate(enabled_chs):
            ch_name = ch.get('name', 'Unknown')
            ch_key = f"{node_name}_{ch_name}"
            
            # ช่องแสดงผลย่อย (Register Box)
            reg_box = QtWidgets.QFrame()
            reg_box.setStyleSheet("background: rgba(255,255,255,0.05); border-radius: 6px; border: 1px solid #222;")
            box_vbox = QtWidgets.QVBoxLayout(reg_box)
            
            val_lbl = QtWidgets.QLabel("--")
            val_lbl.setMinimumHeight(50) 
            val_lbl.setAlignment(QtCore.Qt.AlignCenter)

            val_lbl.setStyleSheet("font-size: 24pt; font-weight: bold; color: #00FF00; border: none;")
            
            info_lbl = QtWidgets.QLabel(f"{ch_name} ({ch.get('unit','')})")
            info_lbl.setFixedHeight(25)            
            info_lbl.setAlignment(QtCore.Qt.AlignCenter)
            info_lbl.setStyleSheet("color: #666; font-size: 15; border: none;")
            
            box_vbox.addWidget(val_lbl)
            box_vbox.addWidget(info_lbl)
            
            reg_layout.addWidget(reg_box, idx // 2, idx % 2)
            
            # เก็บ reference ไว้สำหรับ update_values
            self.node_cards[ch_key] = val_lbl

        layout.addLayout(reg_layout)
        return card_frame

    def update_values(self, data_batch):
        """รับข้อมูลจาก Signal แล้วกระจายไปตาม Label ต่างๆ"""
        # ปิดการวาดชั่วคราวเพื่อลดการกระพริบ (CPU Optimize)
        self.setUpdatesEnabled(False)
        try:
            for ch_key, value in data_batch.items():
                if ch_key in self.node_cards:
                    lbl = self.node_cards[ch_key]
                    lbl.setText(f"{value:,.2f}")
                    
                    # Alarm Color Logic (อ้างอิงจาก config)
                    threshold = self.conf['app_settings'].get('alarm_threshold', 500)
                    color = "#FF3333" if value >= threshold else "#00FF00"
                    lbl.setStyleSheet(f"font-size: 24pt; font-weight: bold; color: {color}; border: none;")
        finally:
            self.setUpdatesEnabled(True)