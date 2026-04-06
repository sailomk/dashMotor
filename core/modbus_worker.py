import os, time, csv, asyncio, json
from datetime import datetime, timedelta
from collections import defaultdict
from PySide6 import QtCore
from pymodbus.client import AsyncModbusSerialClient

from ui.device_drivers import DRIVERS

class ErrorAggregator:
    def __init__(self, debug_conf, error_json_path="error.json"):
        # 1. โหลดการตั้งค่าจาก Config (Requirement 1)
        self.debug_dir = debug_conf.get("log_dir", "debug_logs")
        self.log_level = str(debug_conf.get("level", "OFF")).upper()
        os.makedirs(self.debug_dir, exist_ok=True)
        
        # 2. โหลด Error Mapping (Requirement 4)
        try:
            with open(error_json_path, 'r', encoding='utf-8') as f:
                self.error_map = json.load(f)
        except Exception as e:
            print(f"❌ Failed to load error.json: {e}")
            self.error_map = {"ERR_TYPE": {}, "ERR_MOD": {}}

        self.errors = [] # สำหรับ Summary รายงานหน้าจอ (Feature เดิม)
        
        # 3. State สำหรับ Tracking Error
        self.error_tracker = {}
        
        # รองรับ Severity และ ALL/OFF (Requirement 2 & 3)
        self.severity_order = {"OFF": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4, "ALL": 99}

    def _should_log(self, severity):
        if self.log_level == "OFF": return False
        if self.log_level == "ALL": return True
        
        target_val = self.severity_order.get(self.log_level, 0)
        current_val = self.severity_order.get(severity.upper(), 0)
        return current_val >= target_val

    def clear_resolved_errors(self):
        """เงื่อนไขข้อ 1: ถ้า Error หายไปเกิน 1 นาที ให้ Reset Count"""
        now = datetime.now()
        to_delete = [k for k, v in self.error_tracker.items() if (now - v["last_seen"]).total_seconds() > 60]
        for k in to_delete:
            del self.error_tracker[k]

    def add_error(self, node_id, address, err_type_key, err_mod_key=None):
        now = datetime.now()
        self.clear_resolved_errors() 

        # ค้นหาข้อมูลจาก error.json
        e_type_info = self.error_map["ERR_TYPE"].get(err_type_key, self.error_map["ERR_TYPE"].get("U_ERR", {}))
        severity = e_type_info.get("severity", "ERROR")
        
        # กำหนด Description
        description = e_type_info.get("name", "Unknown")
        if err_mod_key:
            mod_info = self.error_map["ERR_MOD"].get(err_mod_key)
            if mod_info: 
                description = mod_info.get("description", mod_info.get("name")).replace("{addr:04X}", f"{address:04X}")

        # --- Feature เดิม: เก็บลง Summary List สำหรับ GUI ---
        entry = {"timestamp": now.strftime("%Y-%m-%d %H:%M:%S"), "node_id": node_id, 
                 "address": address, "type": err_type_key, "message": description}
        self.errors.append(entry)
        if len(self.errors) > 500: self.errors.pop(0)

        # --- ส่วน Debug Log ---
        if not self._should_log(severity): return

        # เงื่อนไขข้อ 4: ERR_Type ให้ใส่ค่า Type (เช่น T_ERR) และ Err_Mod ใส่รหัส Modbus (ถ้ามี)
        log_err_type = err_type_key
        log_err_mod = err_mod_key if err_mod_key else "-"

        error_key = (node_id, address, err_type_key, err_mod_key)
        
        if error_key not in self.error_tracker:
            # Record ที่ 1: พบครั้งแรกบันทึกทันที count = 1
            self.error_tracker[error_key] = {"count": 1, "first_seen": now, "last_seen": now}
            self._write_log_file(node_id, address, severity, log_err_type, log_err_mod, description, 1)
        else:
            # อัปเดตข้อมูลการพบซ้ำ
            self.error_tracker[error_key]["count"] += 1
            self.error_tracker[error_key]["last_seen"] = now
            
            # Record ที่ 2: ถ้าผ่านไป 1 นาทีแล้วยังไม่หาย บันทึก count ล่าสุด
            first_seen = self.error_tracker[error_key]["first_seen"]
            if (now - first_seen).total_seconds() >= 60:
                current_count = self.error_tracker[error_key]["count"]
                self._write_log_file(node_id, address, severity, log_err_type, log_err_mod, description, current_count)
                # Reset รอบการนับใหม่
                self.error_tracker[error_key] = {"count": 0, "first_seen": now, "last_seen": now}

    def _write_log_file(self, nid, addr, sev, e_type, e_mod, desc, count):
        """บันทึกข้อมูลลงไฟล์พร้อม Header"""
        now = datetime.now()
        filename = f"debug_{now.strftime('%d_%m_%y')}.log"
        filepath = os.path.join(self.debug_dir, filename)
        
        file_exists = os.path.isfile(filepath)
        
        # Header: eventT,node_ID,node_ADDR,Severity,ERR_Type,Err_Mod,Description,Err_Count
        header = "eventT,node_ID,node_ADDR,Severity,ERR_Type,Err_Mod,Description,Err_Count\n"
        log_line = f"{now.strftime('%d-%m-%y %H:%M:%S')},{nid},{addr},{sev},{e_type},{e_mod},{desc},{count}\n"
        
        try:
            with open(filepath, "a", encoding="utf-8") as f:
                if not file_exists:
                    f.write(header)
                f.write(log_line)
        except Exception as e:
            print(f"⚠️ Log Write Error: {e}")

    def get_current_summary(self):
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        summary = [f"📊 SYSTEM STATUS REPORT", f"📅 Time: {now_str}", f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", ""]
        if not self.errors:
            summary.append("✅ STATUS: ALL NODES ONLINE")
        else:
            summary.append("⚠️ STATUS: ERRORS DETECTED")
            node_stats = defaultdict(int)
            for e in self.errors: node_stats[f"Node {e['node_id']} ({e['type']})"] += 1
            for k, v in node_stats.items(): summary.append(f"  ❌ {k}: {v} times")
        summary.append("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(summary)

class AsyncPollWorker(QtCore.QThread):
    data_signal = QtCore.Signal(dict, float)
    error_summary_signal = QtCore.Signal(str)
    finished_signal = QtCore.Signal()

    def __init__(self, conf, log_path, debug_path):
        super().__init__()
        self.conf = conf
        self.log_path = log_path
        self.debug_path = debug_path
        self._stopped = False
        self._paused = False
        
        debug_cfg = self.conf.get("debug", {"log_dir": "debug_logs", "level": "OFF"})
        self.error_aggregator = ErrorAggregator(debug_conf=debug_cfg)
        
        self.client = None
        self.loop = None
        self.last_report_time = time.time()

        self.start_event = None

    def resume_start(self):
        """เรียกจาก UI เมื่อกด OK ที่ Popup เพื่อให้ Worker เดินหน้าต่อ"""
        if self.loop:
            self.loop.call_soon_threadsafe(self.start_event.set)

    def stop(self):
        self._stopped = True

    def send_error_summary(self):
        if self.error_aggregator:
            summary = self.error_aggregator.get_current_summary()
            self.error_summary_signal.emit(summary)

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self.main_loop())
        except Exception as e:
            print(f"ℹ️ Worker Thread Info: {e}")
        finally:
            try:
                if self.client: self.client.close()
                pending = asyncio.all_tasks(self.loop)
                if pending:
                    for task in pending: task.cancel()
                    self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except: pass
            self.loop.close()
            self.finished_signal.emit()
    
    async def quarantine_check(self):
        """ตรวจสอบ Node ทุกตัวก่อนเริ่มงานจริง ถ้าพังให้ Quarantine"""
        for node in self.conf.get('nodes', []):
            # ข้าม Node ที่ถูกปิดใช้งานมาจาก config อยู่แล้ว
            if not node.get('enabled', True):
                continue
                
            nid = node['node_id']
            # เลือกตรวจสอบจาก Channel แรกที่เจอ
            if not node.get('channels'): continue
            ch = node['channels'][0]
            addr = ch['address']
            
            try:
                if ch.get('type', 'input') == 'input':
                    res = await self.client.read_input_registers(address=addr, count=1, slave=nid)
                else:
                    res = await self.client.read_holding_registers(address=addr, count=1, slave=nid)

                # ถ้าติดต่อไม่ได้ หรือ Modbus คืนค่า Error Exception
                if not res or res.isError():
                    node['enabled'] = False # Quarantine ทันที
                    self.error_aggregator.add_error(nid, addr, "Q_ERR")
                    print(f"⚠️ Node {nid} Quarantined: Communication Failed during startup.")
            
            except Exception:
                node['enabled'] = False
                self.error_aggregator.add_error(nid, addr, "Q_ERR")
                print(f"⚠️ Node {nid} Quarantined: Exception during startup check.")
                
    async def main_loop(self):
        self.start_event = asyncio.Event()
        
        mb = self.conf['modbus']
        self.client = AsyncModbusSerialClient(
            port=os.path.expanduser(mb['port_name']),
            baudrate=mb['baudrate'], timeout=mb['timeout'],
            parity=mb['parity'], stopbits=mb['stopbits'], bytesize=mb['bytesize']
        )
        
        # 1. เชื่อมต่อ Serial Port
        try:
            connected = await self.client.connect()
        except Exception:
            connected = False

        if not connected:
            self.error_aggregator.add_error("SYS", 0, "C_ERR")
            self.send_error_summary() # ส่งสัญญาณเพื่อให้ UI แสดง Popup และปิดโปรแกรม
            return 

        # 2. ตรวจสอบและ Quarantine อุปกรณ์ที่พัง
        # เก็บจำนวน Error ก่อนเช็ค
        initial_error_count = len(self.error_aggregator.errors)
        
        await self.quarantine_check()
        
        # ตรวจสอบว่ามี Node โดน Quarantine (Q_ERR) เพิ่มขึ้นมาไหม
        has_quarantine = len(self.error_aggregator.errors) > initial_error_count

        if has_quarantine:
            self.send_error_summary() # ส่งสัญญาณ Popup ครั้งเดียวตอนเริ่ม
            print("System: Waiting for user to acknowledge quarantined nodes...")
            await self.start_event.wait() 
        else:
            # ถ้าไม่มีปัญหา ให้เริ่มทำงานทันทีโดยไม่ต้องมี Popup
            self.start_event.set()
            print("System: Normal operation started.")
        
        while not self._stopped:
            if self._paused:
                await asyncio.sleep(0.1); continue

            start_ts = time.perf_counter()
            batch_data, log_buffer = {}, []

            for node in self.conf.get('nodes', []):
                if self._stopped: break
                node_log, node_gui = await self.read_node_batch(node)
                batch_data.update(node_gui)
                log_buffer.extend(node_log)
                await asyncio.sleep(0.01)

            if batch_data and not self._stopped: 
                self.data_signal.emit(batch_data, time.time())
            
            if log_buffer and not self._stopped: 
                self.save_to_csv(log_buffer)

            if time.time() - self.last_report_time > 60:
                self.send_error_summary()
                self.last_report_time = time.time()

            polling_sec = self.conf['app_settings']['polling_ms'] / 1000.0
            wait_time = max(0.01, polling_sec - (time.perf_counter() - start_ts))
            end_wait = time.perf_counter() + wait_time
            while time.perf_counter() < end_wait:
                if self._stopped: break
                await asyncio.sleep(0.1)
                
    async def read_node_batch(self, node_cfg):
        if not node_cfg.get('enabled', True):
            return [], {} # คืนค่าว่างกลับไปทันที ไม่ต้องเสียเวลา Modbus Read
        
        nid = node_cfg['node_id']
        driver = DRIVERS.get(node_cfg.get('driver', 'DEFAULT').upper(), DRIVERS['DEFAULT'])
        gui_batch, log_rows = {}, []
        chs = [c for c in node_cfg['channels'] if c.get('enabled', True)]
        
        for r_type in ['input', 'holding']:
            targets = [c for c in chs if c.get('type', 'input') == r_type]
            if not targets: continue
            
            addr_start = min(c['address'] for c in targets)
            addr_count = max(c['address'] for c in targets) - addr_start + 1

            try:
                if r_type == 'input':
                    res = await self.client.read_input_registers(address=addr_start, count=addr_count, slave=nid)
                else:
                    res = await self.client.read_holding_registers(address=addr_start, count=addr_count, slave=nid)

                if res and not res.isError():
                    ts = datetime.now().strftime("%d-%m-%y %H:%M:%S")
                    for ch in targets:
                        raw = res.registers[ch['address'] - addr_start]
                        val = round(driver.scale_value(raw, ch), 2)
                        gui_batch[f"{node_cfg['node_name']}_{ch['name']}"] = val
                        log_rows.append([ts, nid, ch['address'], val, ch['name']])
                else:
                    err_code = hex(res.exception_code) if hasattr(res, 'exception_code') else "0x00"
                    self.error_aggregator.add_error(nid, addr_start, "M_ERR", err_code)
            except Exception as e:
                self.error_aggregator.add_error(nid, addr_start, "T_ERR")
        
        return log_rows, gui_batch

    def save_to_csv(self, rows):
        f_path = os.path.join(self.log_path, f"log_{datetime.now().strftime('%d-%m-%y_%H')}.csv")
        exists = os.path.isfile(f_path)
        with open(f_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not exists: writer.writerow(["date/time", "node_id", "address", "Value", "name"])
            writer.writerows(rows)

          