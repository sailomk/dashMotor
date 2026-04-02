import os, time, csv, asyncio, json
from datetime import datetime, timedelta
from collections import defaultdict
from PySide6 import QtCore
from pymodbus.client import AsyncModbusSerialClient

from ui.device_drivers import DRIVERS

class ErrorAggregator:
    def __init__(self, aggregation_window_minutes=60, debug_dir="debug_logs"):
        self.debug_dir = debug_dir
        self.errors = []
        os.makedirs(self.debug_dir, exist_ok=True)

    def add_error(self, node_id, address, error_type, message):
        now = datetime.now()
        entry = {
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "node_id": node_id,
            "address": address,
            "type": error_type,
            "message": str(message)
        }
        self.errors.append(entry)
        if len(self.errors) > 500: self.errors.pop(0)

    def get_current_summary(self):
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        summary = [
            f"📊 SYSTEM STATUS REPORT",
            f"📅 Time: {now_str}",
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            ""
        ]
        if not self.errors:
            summary.append("✅ STATUS: ALL NODES ONLINE")
            summary.append("📝 Note: No communication errors detected.")
        else:
            summary.append("⚠️ STATUS: ERRORS DETECTED")
            node_stats = defaultdict(int)
            for e in self.errors:
                node_stats[f"Node {e['node_id']} ({e['type']})"] += 1
            for k, v in node_stats.items():
                summary.append(f"  ❌ {k}: {v} times")
        
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
        self.error_aggregator = ErrorAggregator(debug_dir=self.debug_path)
        self.client = None
        self.loop = None
        self.last_report_time = time.time()

    def stop(self):
        """สั่งหยุดจากภายนอก Thread แบบนุ่มนวล (Flag-based)"""
        self._stopped = True
        print("🛑 Worker stop signal sent. Waiting for main loop to exit...")

    def send_error_summary(self):
        if self.error_aggregator:
            summary = self.error_aggregator.get_current_summary()
            self.error_summary_signal.emit(summary)

    def run(self):
        """จุดเริ่มของ QThread"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        try:
            # รันจนกว่า main_loop จะ Return ออกมาเองเมื่อเจอ _stopped = True
            self.loop.run_until_complete(self.main_loop())
        except Exception as e:
            print(f"ℹ️ Loop Info: {e}")
        finally:
            # Cleanup: กวาดล้าง Tasks ที่ค้างอยู่แบบสุภาพก่อนปิด Loop
            try:
                # 1. ปิด Client ก่อนเพื่อให้ Transport หยุดพยายามรับส่งข้อมูล
                if self.client:
                    self.client.close()
                    print("🔌 Modbus client closed.")

                # 2. ดึง Task ทั้งหมดที่ยังค้างอยู่
                pending = asyncio.all_tasks(self.loop)
                
                if pending:
                    # 3. สั่ง Cancel ทุก Task ทันที
                    for task in pending:
                        task.cancel()
                    
                    # 4. รัน Loop ต่ออีกนิดเพื่อให้ Tasks รับทราบการโดน Cancel
                    # return_exceptions=True เพื่อไม่ให้มันเด้ง Error ตอนเรากำลังจะปิด
                    self.loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
                    print(f"🧹 Cleaned up {len(pending)} tasks.")
            except Exception as cleanup_err:
                print(f"⚠️ Cleanup error: {cleanup_err}")
            
            if self.client:
                self.client.close()
            self.loop.close()
            print("🔒 Event loop closed safely.")
            self.finished_signal.emit()

    async def main_loop(self):
        mb = self.conf['modbus']
        self.client = AsyncModbusSerialClient(
            port=os.path.expanduser(mb['port_name']),
            baudrate=mb['baudrate'],
            timeout=mb['timeout'],
            parity=mb['parity'],
            stopbits=mb['stopbits'],
            bytesize=mb['bytesize']
        )
        
        connected = await self.client.connect()
        if connected:
            print(f"✅ Connected to {mb['port_name']}")
            self.send_error_summary()
        else:
            print(f"❌ Failed to connect to {mb['port_name']}")

        while not self._stopped:
            if self._paused:
                await asyncio.sleep(0.1)
                continue

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

            # --- Responsive Sleeping ---
            # แบ่งการรอเป็นช่วงละ 0.1s เพื่อให้เช็ค _stopped ได้ทันทีที่กดปิดโปรแกรม
            polling_sec = self.conf['app_settings']['polling_ms'] / 1000.0
            wait_time = max(0.01, polling_sec - (time.perf_counter() - start_ts))
            end_wait = time.perf_counter() + wait_time
            
            while time.perf_counter() < end_wait:
                if self._stopped: break
                await asyncio.sleep(0.1)

        print("👋 Main loop exited cleanly.")

    async def read_node_batch(self, node_cfg):
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
                    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    for ch in targets:
                        raw = res.registers[ch['address'] - addr_start]
                        val = round(driver.scale_value(raw, ch), 2)
                        gui_batch[f"{node_cfg['node_name']}_{ch['name']}"] = val
                        log_rows.append([ts, nid, ch['address'], val, ch['name']])
                else:
                    self.error_aggregator.add_error(nid, addr_start, "MODBUS_ERR", "Invalid Response")
            except Exception as e:
                self.error_aggregator.add_error(nid, nid, "TIMEOUT", str(e))
        
        return log_rows, gui_batch

    def save_to_csv(self, rows):
        f_path = os.path.join(self.log_path, f"log_{datetime.now().strftime('%Y-%m-%d_%H')}.csv")
        exists = os.path.isfile(f_path)
        with open(f_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not exists: writer.writerow(["date/time", "node_id", "address", "Value", "name"])
            writer.writerows(rows)