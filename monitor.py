import psutil
import threading
import time
import os
import sys
import subprocess
import platform
from typing import Callable
from config import UPDATE_INTERVAL, MAX_HISTORY
from utilities import setup_logging

try:
    import GPUtil
    GPU_AVAILABLE = True
except ImportError:
    GPU_AVAILABLE = False

try:
    from pySMART import Device
    SMART_AVAILABLE = True
except ImportError:
    SMART_AVAILABLE = False

class ResourceMonitor:
    def __init__(self):
        self.update_interval = UPDATE_INTERVAL
        self.stop_event = threading.Event()
        self.max_history = MAX_HISTORY
        self.cpu_usage_history = [[] for _ in range(psutil.cpu_count())]
        self.ram_usage_history = []
        self.gpu_usage_history = []
        self.gpu_memory_history = []
        self.gpu_temp_history = []
        self.gpu_temp_min = float('inf') if GPU_AVAILABLE else None
        self.gpu_temp_max = float('-inf') if GPU_AVAILABLE else None
        self.disk_io_history_read = []
        self.disk_io_history_write = []
        self.net_download_history = []
        self.net_upload_history = []
        self.last_read_bytes = 0
        self.last_write_bytes = 0
        self.last_bytes_sent = 0
        self.last_bytes_recv = 0
        self.smartctl_path = self._get_smartctl_path()
        self.callback: Callable[[dict], None] = None

    def _get_smartctl_path(self):
        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
            return os.path.join(base_path, 'smartctl.exe')
        return r"C:\Program Files\gsmartcontrol\smartctl.exe"

    def set_callback(self, callback: Callable[[dict], None]):
        self.callback = callback

    def start(self):
        threading.Thread(target=self._monitor, daemon=True).start()

    def _monitor(self):
        while not self.stop_event.is_set():
            try:
                # CPU
                cpu_percent = psutil.cpu_percent(percpu=True)
                total_cpu = psutil.cpu_percent()
                self._update_cpu_history(cpu_percent)

                # RAM
                ram = psutil.virtual_memory()
                self._update_ram_history(ram)

                # GPU
                gpu_data = None
                if GPU_AVAILABLE:
                    gpus = GPUtil.getGPUs()
                    if gpus:
                        gpu = gpus[0]
                        gpu_usage = gpu.load * 100
                        gpu_memory_used = gpu.memoryUsed
                        gpu_memory_total = gpu.memoryTotal
                        gpu_memory_percent = (gpu_memory_used / gpu_memory_total) * 100
                        gpu_temp = gpu.temperature
                        self.gpu_temp_min = min(self.gpu_temp_min, gpu_temp)
                        self.gpu_temp_max = max(self.gpu_temp_max, gpu_temp)
                        self._update_gpu_history(gpu_usage, gpu_memory_percent, gpu_temp)
                        gpu_data = (gpu_usage, gpu_memory_used, gpu_memory_total, gpu_memory_percent, gpu_temp, self.gpu_temp_min, self.gpu_temp_max)

                # Disk
                disk = psutil.disk_usage('/')
                io = psutil.disk_io_counters()
                disk_temp, disk_health = self._get_smart_data()
                read_speed = (io.read_bytes - self.last_read_bytes) / (1024 * 1024) if io else 0
                write_speed = (io.write_bytes - self.last_write_bytes) / (1024 * 1024) if io else 0
                self.last_read_bytes = io.read_bytes if io else 0
                self.last_write_bytes = io.write_bytes if io else 0
                self._update_disk_history(read_speed, write_speed)

                # Network
                net_io = psutil.net_io_counters()
                download_speed = (net_io.bytes_recv - self.last_bytes_recv) * 8 / (1024 * 1024)
                upload_speed = (net_io.bytes_sent - self.last_bytes_sent) * 8 / (1024 * 1024)
                self.last_bytes_recv = net_io.bytes_recv
                self.last_bytes_sent = net_io.bytes_sent
                self._update_network_history(download_speed, upload_speed)

                # Uptime
                uptime_seconds = int(time.time() - psutil.boot_time())
                days, remainder = divmod(uptime_seconds, 86400)
                hours, remainder = divmod(remainder, 3600)
                minutes, seconds = divmod(remainder, 60)

                # Передача даних у GUI cetology
                if self.callback:
                    self.callback({
                        'cpu': (total_cpu, cpu_percent),
                        'ram': ram,
                        'gpu': gpu_data,
                        'disk': (disk, read_speed, write_speed, disk_temp, disk_health),
                        'network': (download_speed, upload_speed),
                        'uptime': (uptime_seconds, days, hours, minutes)
                    })
            except Exception as e:
                setup_logging().error(f"Error in ResourceMonitor: {e}")
            time.sleep(self.update_interval)

    def _update_cpu_history(self, cpu_percent):
        for i, percent in enumerate(cpu_percent):
            self.cpu_usage_history[i].append(percent)
            if len(self.cpu_usage_history[i]) > self.max_history:
                self.cpu_usage_history[i].pop(0)

    def _update_ram_history(self, ram):
        self.ram_usage_history.append(ram.percent)
        if len(self.ram_usage_history) > self.max_history:
            self.ram_usage_history.pop(0)

    def _update_gpu_history(self, gpu_usage, gpu_memory_percent, gpu_temp):
        self.gpu_usage_history.append(gpu_usage)
        self.gpu_memory_history.append(gpu_memory_percent)
        self.gpu_temp_history.append(gpu_temp)
        if len(self.gpu_usage_history) > self.max_history:
            self.gpu_usage_history.pop(0)
            self.gpu_memory_history.pop(0)
            self.gpu_temp_history.pop(0)

    def _update_disk_history(self, read_speed, write_speed):
        self.disk_io_history_read.append(read_speed)
        self.disk_io_history_write.append(write_speed)
        if len(self.disk_io_history_read) > self.max_history:
            self.disk_io_history_read.pop(0)
            self.disk_io_history_write.pop(0)

    def _update_network_history(self, download_speed, upload_speed):
        self.net_download_history.append(download_speed)
        self.net_upload_history.append(upload_speed)
        if len(self.net_download_history) > self.max_history:
            self.net_download_history.pop(0)
            self.net_upload_history.pop(0)

    def _get_smart_data(self):
        disk_temp = disk_health = "N/A"
        if platform.system() == "Windows":
            try:
                cmd = [self.smartctl_path, '-A', '-d', 'nvme', '/dev/sda']
                result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=5)
                for line in result.stdout.splitlines():
                    if "Temperature:" in line:
                        temp_value = [word for word in line.split() if word.isdigit()]
                        disk_temp = temp_value[0] + "°C" if temp_value else "N/A"
                        break
                cmd = [self.smartctl_path, '-H', '-d', 'nvme', '/dev/sda']
                result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=5)
                disk_health = "OK" if "PASSED" in result.stdout else "Warning"
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass
        elif platform.system() == "Linux" and SMART_AVAILABLE:
            try:
                disk_device = Device('/dev/sda')
                disk_temp = str(disk_device.temperature) + "°C" if disk_device.temperature else "N/A"
                disk_health = disk_device.health if disk_device.health else "N/A"
            except Exception:
                pass
        return disk_temp, disk_health

    def stop(self):
        self.stop_event.set()

    def get_cpu_history(self):
        return self.cpu_usage_history

    def get_ram_history(self):
        return self.ram_usage_history

    def get_gpu_usage_history(self):
        return self.gpu_usage_history

    def get_gpu_memory_history(self):
        return self.gpu_memory_history

    def get_gpu_temp_history(self):
        return self.gpu_temp_history

    def get_disk_io_history(self):
        return self.disk_io_history_read, self.disk_io_history_write

    def get_network_history(self):
        return self.net_download_history, self.net_upload_history