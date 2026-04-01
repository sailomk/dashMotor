import sys
import os

def get_base_dir():
    """หาโฟลเดอร์หลักที่รันโปรแกรม (รองรับทั้งตอนเป็น script และ .exe)"""
    if getattr(sys, 'frozen', False):
        # ถ้าเป็นไฟล์ .exe (Compiled)
        return os.path.dirname(sys.executable)
    # ถ้าเป็นไฟล์ .py ปกติ
    return os.path.dirname(os.path.abspath(__file__))

def get_log_path(config, key_path=['app_settings', 'log_dir']):
    """ดึง path จาก config มาประกอบกับ base_dir และสร้าง folder ถ้ายังไม่มี"""
    base = get_base_dir()
    
    # ดึงค่าจาก config ตามลำดับชั้นที่ส่งมา
    current = config
    for key in key_path:
        current = current.get(key, 'logs') # default เป็น 'logs'
    
    full_path = os.path.join(base, current)
    
    # สร้าง folder อัตโนมัติถ้าไม่มี
    if not os.path.exists(full_path):
        os.makedirs(full_path)
        
    return full_path