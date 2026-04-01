from PySide6 import QtWidgets, QtCore, QtGui
from datetime import datetime

class ErrorSummaryTab(QtWidgets.QWidget):
    def __init__(self, main_app): # รับตัวแปร main_app เข้ามา
        super().__init__()
        self.main_app = main_app
        self.init_ui()

    def init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        
        # Title
        title_lbl = QtWidgets.QLabel("🚨 ERROR LOG MONITORING")
        title_lbl.setStyleSheet("color: #FF3333; font-size: 20pt; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title_lbl)
        
        # Text Edit (ส่วนแสดงผลหลัก)
        self.error_summary_text = QtWidgets.QTextEdit()
        self.error_summary_text.setReadOnly(True)
        self.error_summary_text.setStyleSheet("""
            QTextEdit {
                background-color: #000000;
                color: #00FF00;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 13pt; 
                border: 2px solid #333;
                border-radius: 8px;
                padding: 15px;
            }
        """)
        layout.addWidget(self.error_summary_text)
        
        # ส่วนปุ่มกด
        btn_layout = QtWidgets.QHBoxLayout()
        
        # ปุ่ม Refresh (เชื่อมกับฟังก์ชันขอข้อมูล)
        refresh_btn = QtWidgets.QPushButton("🔄 REFRESH NOW")
        refresh_btn.setMinimumHeight(45)
        refresh_btn.clicked.connect(self.main_app.request_error_summary) # เรียกกลับไปที่ main.py
        refresh_btn.setStyleSheet("background-color: #FF3333; color: white; font-weight: bold; font-size: 11pt; border-radius: 5px;")
        
        # ปุ่ม Clear
        clear_btn = QtWidgets.QPushButton("🗑️ CLEAR STATISTICS")
        clear_btn.setMinimumHeight(45)
        clear_btn.clicked.connect(self.main_app.clear_error_stats) # เรียกกลับไปที่ main.py
        clear_btn.setStyleSheet("background-color: #444; color: white; font-size: 11pt; border-radius: 5px;")
        
        btn_layout.addWidget(refresh_btn)
        btn_layout.addWidget(clear_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    @QtCore.Slot(str)
    def update_error_log(self, summary):
        """ฟังก์ชันนี้จะถูกเรียกเมื่อ Worker ส่งสัญญาณ error_summary_signal มา"""  
        print(f"DEBUG: UI received summary!") #
        self.error_summary_text.setText(summary)
        self.error_summary_text.moveCursor(QtGui.QTextCursor.Start)
        self.error_summary_text.repaint()