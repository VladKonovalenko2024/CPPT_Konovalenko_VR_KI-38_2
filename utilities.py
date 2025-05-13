import logging
import psutil
import tkinter as tk
from tkinter import ttk, messagebox
import time
import datetime
from config import AUTO_EXPORT_INTERVAL
import matplotlib.pyplot as plt

# Логування
def setup_logging():
    logging.basicConfig(
        filename='monitor.log',
        level=logging.DEBUG,
        format='%(asctime)s %(levelname)s: %(message)s'
    )
    return logging

# Побудова графіків
def create_plot(title: str, xlabel: str, ylabel: str, ylim: tuple, xlim: tuple):
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_ylim(*ylim)
    ax.set_xlim(*xlim)
    ax.grid(True)
    return fig, ax

# Управління процесами
_process_data = {}
_net_process_data = {}
_sort_column = "Memory_MB"
_net_sort_column = "Download_MB"
_sort_reverse = True
_net_sort_reverse = True
_process_limit_warning_shown = False

def update_process_list(tree: ttk.Treeview, column: str = None):
    global _sort_column, _sort_reverse, _process_data, _process_limit_warning_shown
    if column:
        if _sort_column == column:
            _sort_reverse = not _sort_reverse
        else:
            _sort_column = column
            _sort_reverse = False

    selected = tree.selection()
    selected_pid = None
    if selected:
        selected_pid = tree.item(selected[0])['values'][0]

    new_process_data = {}
    try:
        process_list = list(psutil.process_iter(['pid', 'name', 'memory_percent', 'memory_info', 'cpu_percent']))
        if len(process_list) > 3000 and not _process_limit_warning_shown:
            _process_limit_warning_shown = True
            messagebox.showwarning("Warning", "Too many processes detected. Displaying top 3000 processes to optimize performance.")

        for proc in process_list[:3000]:
            try:
                pid = proc.info['pid']
                new_process_data[pid] = {
                    'name': proc.info['name'],
                    'memory_mb': proc.info['memory_info'].rss / (1024 * 1024),
                    'memory_percent': proc.info['memory_percent'],
                    'cpu_percent': proc.info['cpu_percent']
                }
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as e:
        setup_logging().error(f"Error in update_process_list: {e}")
        return

    current_pids = set(_process_data.keys())
    new_pids = set(new_process_data.keys())

    for pid in current_pids - new_pids:
        for item in tree.get_children():
            if int(tree.item(item)['values'][0]) == pid:
                tree.delete(item)
                break

    sorted_processes = sorted(
        new_process_data.items(),
        key=lambda x: _get_sort_key(x[1], x[0]),
        reverse=_sort_reverse
    )

    tree.delete(*tree.get_children())
    for pid, data in sorted_processes:
        values = (
            pid,
            data['name'],
            f"{data['memory_mb']:.2f}",
            f"{data['memory_percent']:.2f}",
            f"{data['cpu_percent']:.2f}"
        )
        item = tree.insert("", "end", values=values)
        if data['cpu_percent'] > 90 or data['memory_percent'] > 90:
            tree.item(item, tags=('high_load',))
        if pid not in _process_data:
            tree.item(item, tags=('new',))
        elif _process_data.get(pid) != data:
            tree.item(item, tags=('updated',))

    tree.tag_configure('new', background='#90EE90')
    tree.tag_configure('updated', background='#FFFFE0')
    tree.tag_configure('high_load', background='#FF6347')

    if selected_pid:
        for item in tree.get_children():
            if int(tree.item(item)['values'][0]) == selected_pid:
                tree.selection_set(item)
                break

    _process_data = new_process_data

def update_net_process_list(tree: ttk.Treeview, column: str = None):
    global _net_sort_column, _net_sort_reverse, _net_process_data
    if column:
        if _net_sort_column == column:
            _net_sort_reverse = not _net_sort_reverse
        else:
            _net_sort_column = column
            _net_sort_reverse = False

    selected = tree.selection()
    selected_pid = None
    if selected:
        selected_pid = tree.item(selected[0])['values'][0]

    new_net_process_data = {}
    try:
        for proc in list(psutil.process_iter(['pid', 'name']))[:50]:
            try:
                pid = proc.info['pid']
                net_connections = proc.net_connections()
                if net_connections:
                    download_mb = sum(conn.bytes_recv for conn in net_connections if hasattr(conn, 'bytes_recv')) / (1024 * 1024)
                    upload_mb = sum(conn.bytes_sent for conn in net_connections if hasattr(conn, 'bytes_sent')) / (1024 * 1024)
                    new_net_process_data[pid] = {
                        'name': proc.info['name'],
                        'download_mb': download_mb,
                        'upload_mb': upload_mb
                    }
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as e:
        setup_logging().error(f"Error in update_net_process_list: {e}")
        return

    current_pids = set(_net_process_data.keys())
    new_pids = set(new_net_process_data.keys())

    for pid in current_pids - new_pids:
        for item in tree.get_children():
            if int(tree.item(item)['values'][0]) == pid:
                tree.delete(item)
                break

    sorted_net_processes = sorted(
        new_net_process_data.items(),
        key=lambda x: _get_net_sort_key(x[1], x[0]),
        reverse=_net_sort_reverse
    )

    tree.delete(*tree.get_children())
    for pid, data in sorted_net_processes:
        values = (
            pid,
            data['name'],
            f"{data['download_mb']:.2f}",
            f"{data['upload_mb']:.2f}"
        )
        item = tree.insert("", "end", values=values)
        if pid not in _net_process_data:
            tree.item(item, tags=('new',))
        elif _net_process_data.get(pid) != data:
            tree.item(item, tags=('updated',))

    tree.tag_configure('new', background='#90EE90')
    tree.tag_configure('updated', background='#FFFFE0')

    if selected_pid:
        for item in tree.get_children():
            if int(tree.item(item)['values'][0]) == selected_pid:
                tree.selection_set(item)
                break

    _net_process_data = new_net_process_data

def _get_sort_key(data, pid):
    if _sort_column == "PID":
        return pid
    elif _sort_column == "Name":
        return data['name'].lower()
    elif _sort_column == "Memory_MB":
        return data['memory_mb']
    elif _sort_column == "Memory_Percent":
        return data['memory_percent']
    elif _sort_column == "CPU_Percent":
        return data['cpu_percent']
    return 0

def _get_net_sort_key(data, pid):
    if _net_sort_column == "PID":
        return pid
    elif _net_sort_column == "Name":
        return data['name'].lower()
    elif _net_sort_column == "Download_MB":
        return data['download_mb']
    elif _net_sort_column == "Upload_MB":
        return data['upload_mb']
    return 0

def kill_process(gui):
    selected = gui.process_tree.selection()
    if not selected:
        messagebox.showwarning("Warning", "Please select a process to terminate")
        return

    pid = int(gui.process_tree.item(selected[0])['values'][0])
    if messagebox.askyesno("Confirm", f"Are you sure you want to terminate process PID {pid}?"):
        try:
            process = psutil.Process(pid)
            process.terminate()
            time.sleep(0.5)
            if process.is_running():
                process.kill()
            messagebox.showinfo("Success", f"Process {pid} terminated")
            update_process_list(gui.process_tree)
        except psutil.NoSuchProcess:
            messagebox.showerror("Error", "Process no longer exists")
            update_process_list(gui.process_tree)
        except psutil.AccessDenied:
            messagebox.showerror("Error", "Access denied to terminate this process")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to terminate process: {str(e)}")
            update_process_list(gui.process_tree)

# Експорт даних
def export_data(gui, time_range_minutes=None):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"system_report_{timestamp}.txt"

    with open(filename, 'w', encoding='utf-8') as f:
        f.write("System Monitoring Report\n")
        f.write(f"Date: {timestamp}\n")
        if time_range_minutes:
            f.write(f"Time Range: Last {time_range_minutes} minutes\n")
        f.write("\n")

        # Системна інформація
        f.write(f"CPU: {gui.cpu_info_label['text'].split(': ')[1]}\n")
        f.write(f"RAM: {gui.ram_info_label['text'].split(': ')[1]}\n")
        f.write(f"GPU: {gui.gpu_info_label['text'].split(': ')[1]}\n")
        f.write(f"OS: {gui.os_info_label['text'].split(': ')[1]}\n")
        f.write(f"Uptime: {gui.uptime_label['text'].split(': ')[1]}\n")
        f.write(f"Last Boot: {gui.last_boot_label['text'].split(': ')[1]}\n")

        # CPU
        f.write(f"\nCPU Usage: {psutil.cpu_percent()}%\n")
        if time_range_minutes:
            history_points = min(len(gui.monitor.get_cpu_history()[0]), int(time_range_minutes * 60 / 3))
            avg_cpu = [sum(core[i] for core in gui.monitor.get_cpu_history()) / len(gui.monitor.get_cpu_history())
                       for i in range(-history_points, 0)] if gui.monitor.get_cpu_history() else []
            f.write(f"Average CPU Usage (last {time_range_minutes} min): {sum(avg_cpu)/len(avg_cpu):.1f}%\n" if avg_cpu else "N/A\n")

        # RAM
        ram = psutil.virtual_memory()
        f.write(f"RAM Usage: {ram.percent}% ({ram.used/(1024**3):.2f}/{ram.total/(1024**3):.2f} GB, Free: {ram.free/(1024**3):.2f} GB)\n")
        if time_range_minutes:
            history_points = min(len(gui.monitor.get_ram_history()), int(time_range_minutes * 60 / 3))
            avg_ram = gui.monitor.get_ram_history()[-history_points:] if gui.monitor.get_ram_history() else []
            f.write(f"Average RAM Usage (last {time_range_minutes} min): {sum(avg_ram)/len(avg_ram):.1f}%\n" if avg_ram else "N/A\n")

        # Disk
        f.write(f"Disk Usage: {gui.disk_label['text']}\n")
        f.write(f"Disk Health: {gui.smart_label['text']}\n")
        if time_range_minutes:
            history_points = min(len(gui.monitor.get_disk_io_history()[0]), int(time_range_minutes * 60 / 3))
            avg_read = gui.monitor.get_disk_io_history()[0][-history_points:] if gui.monitor.get_disk_io_history()[0] else []
            avg_write = gui.monitor.get_disk_io_history()[1][-history_points:] if gui.monitor.get_disk_io_history()[1] else []
            f.write(f"Average Disk Read (last {time_range_minutes} min): {sum(avg_read)/len(avg_read):.2f} MB/s\n" if avg_read else "N/A\n")
            f.write(f"Average Disk Write (last {time_range_minutes} min): {sum(avg_write)/len(avg_write):.2f} MB/s\n" if avg_write else "N/A\n")

        # GPU
        try:
            import GPUtil
            GPU_AVAILABLE = True
        except ImportError:
            GPU_AVAILABLE = False
        if GPU_AVAILABLE:
            f.write(f"GPU Usage: {gui.gpu_usage_label['text']}\n")
            f.write(f"GPU Memory: {gui.gpu_memory_label['text']}\n")
            f.write(f"GPU Temp: {gui.gpu_temp_label['text']}\n")
            if time_range_minutes:
                history_points = min(len(gui.monitor.get_gpu_usage_history()), int(time_range_minutes * 60 / 3))
                avg_gpu = gui.monitor.get_gpu_usage_history()[-history_points:] if gui.monitor.get_gpu_usage_history() else []
                f.write(f"Average GPU Usage (last {time_range_minutes} min): {sum(avg_gpu)/len(avg_gpu):.1f}%\n" if avg_gpu else "N/A\n")

        # Network
        f.write(f"Network: {gui.network_label['text']}\n")
        if time_range_minutes:
            history_points = min(len(gui.monitor.get_network_history()[0]), int(time_range_minutes * 60 / 3))
            avg_download = gui.monitor.get_network_history()[0][-history_points:] if gui.monitor.get_network_history()[0] else []
            avg_upload = gui.monitor.get_network_history()[1][-history_points:] if gui.monitor.get_network_history()[1] else []
            f.write(f"Average Download (last {time_range_minutes} min): {sum(avg_download)/len(avg_download):.2f} Mbps\n" if avg_download else "N/A\n")
            f.write(f"Average Upload (last {time_range_minutes} min): {sum(avg_upload)/len(avg_upload):.2f} Mbps\n" if avg_upload else "N/A\n")

        # Процеси
        f.write("\nRunning Processes:\n")
        f.write("-" * 70 + "\n")
        f.write(f"{'PID':<8} {'Memory (MB)':<12} {'Memory (%)':<12} {'CPU (%)':<12} {'Process Name':<30}\n")
        for item in gui.process_tree.get_children()[:10]:
            values = gui.process_tree.item(item, "values")
            f.write(f"{values[0]:<8} {values[2]:<12} {values[3]:<12} {values[4]:<12} {values[1]:<30}\n")
        f.write("\nNetwork-Using Processes:\n")
        f.write("-" * 70 + "\n")
        f.write(f"{'PID':<8} {'Download (MB)':<15} {'Upload (MB)':<15} {'Process Name':<30}\n")
        for item in gui.net_process_tree.get_children()[:10]:
            values = gui.net_process_tree.item(item, "values")
            f.write(f"{values[0]:<8} {values[2]:<15} {values[3]:<15} {values[1]:<30}\n")
        f.write("\nReboot History:\n")
        f.write("-" * 70 + "\n")
        for reboot_time in gui.reboot_history:
            f.write(f"{reboot_time}\n")
        f.write("\nAlert Log:\n")
        f.write("-" * 70 + "\n")
        for alert in gui.alert_log[-10:]:
            f.write(f"{alert}\n")

    return filename