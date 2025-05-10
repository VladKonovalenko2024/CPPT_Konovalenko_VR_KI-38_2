import tkinter as tk
from tkinter import ttk, messagebox
import matplotlib
import subprocess
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np
import psutil
import platform
import datetime
import pyperclip
import wmi
import os
import sys
from config import MAX_HISTORY, CPU_THRESHOLD, RAM_THRESHOLD, GPU_THRESHOLD, DISK_SPACE_THRESHOLD, NET_TRAFFIC_THRESHOLD, UPTIME_THRESHOLD, AUTO_EXPORT_INTERVAL
from utilities import create_plot, update_process_list, update_net_process_list, kill_process, setup_logging

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

class SystemMonitorGUI:
    def __init__(self, root: tk.Tk, monitor):
        self.root = root
        self.monitor = monitor
        self.root.title("System Monitor")
        self.root.geometry("1000x700")
        self.root.minsize(800, 600)
        self.after_ids = []
        self.reboot_history = [datetime.datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S")]
        self.alert_log = []
        
        # Перенаправлення stdout у /dev/null
        self.original_stdout = sys.stdout
        self.devnull_file = open(os.devnull, 'w')
        sys.stdout = self.devnull_file

        self.setup_gui()
        self.monitor.set_callback(self.update_gui)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_gui(self):
        style = ttk.Style()
        style.configure("Treeview", rowheight=25)
        style.configure("Treeview.Heading", font=('Helvetica', 10, 'bold'))

        notebook_frame = ttk.Frame(self.root)
        notebook_frame.pack(fill="both", expand=True)

        self.notebook = ttk.Notebook(notebook_frame)
        self.notebook.pack(fill="both", expand=True)

        self.export_button = ttk.Button(self.root, text="Export Data", command=self.manual_export)
        self.export_button.pack(pady=5)

        # Вкладка CPU
        self.cpu_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.cpu_frame, text="CPU")
        self.cpu_label = ttk.Label(self.cpu_frame, text="Total CPU Usage: 0%", font=('Helvetica', 12))
        self.cpu_label.pack(pady=5)
        self.cores_frame = ttk.LabelFrame(self.cpu_frame, text="CPU Usage per Core (%)")
        self.cores_frame.pack(fill="x", pady=5)
        self.cpu_labels = []
        for i in range(psutil.cpu_count()):
            label = ttk.Label(self.cores_frame, text=f"Core {i}: 0.0%", width=15)
            label.grid(row=0, column=i % 8, padx=5, pady=5)
            self.cpu_labels.append(label)
        self.cpu_fig, self.cpu_ax = create_plot(
            title="CPU Usage per Core", xlabel="Time (s)", ylabel="Usage (%)", ylim=(0, 100), xlim=(0, MAX_HISTORY - 1)
        )
        self.cpu_canvas = FigureCanvasTkAgg(self.cpu_fig, master=self.cpu_frame)
        self.cpu_canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=5)
        self.cpu_lines = []
        colors = plt.cm.tab20(np.linspace(0, 1, psutil.cpu_count()))
        for i in range(psutil.cpu_count()):
            line, = self.cpu_ax.plot(np.arange(MAX_HISTORY), [0] * MAX_HISTORY, label=f"Core {i}", color=colors[i])
            self.cpu_lines.append(line)
        self.cpu_ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        self.cpu_fig.tight_layout()

        # Вкладка RAM
        self.ram_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.ram_frame, text="RAM")
        self.ram_label = ttk.Label(self.ram_frame, text="RAM Usage: 0%", font=('Helvetica', 12))
        self.ram_label.pack(pady=5)
        self.ram_fig, self.ram_ax = create_plot(
            title="RAM Usage Over Time", xlabel="Time (s)", ylabel="Usage (%)", ylim=(0, 100), xlim=(0, MAX_HISTORY - 1)
        )
        self.ram_canvas = FigureCanvasTkAgg(self.ram_fig, master=self.ram_frame)
        self.ram_canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=5)
        self.ram_line, = self.ram_ax.plot(np.arange(MAX_HISTORY), [0] * MAX_HISTORY, label="RAM Usage", color='blue')
        self.ram_ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        self.ram_fig.tight_layout()
        self.process_frame = ttk.LabelFrame(self.ram_frame, text="Running Processes")
        self.process_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.process_tree = ttk.Treeview(
            self.process_frame, columns=("PID", "Name", "Memory_MB", "Memory_Percent", "CPU_Percent"), show="headings", height=5
        )
        self.process_tree.pack(fill="both", expand=True, side=tk.LEFT)
        self.process_tree.heading("PID", text="PID", command=lambda: update_process_list(self.process_tree, "PID"))
        self.process_tree.heading("Name", text="Process Name", command=lambda: update_process_list(self.process_tree, "Name"))
        self.process_tree.heading("Memory_MB", text="Memory (MB)", command=lambda: update_process_list(self.process_tree, "Memory_MB"))
        self.process_tree.heading("Memory_Percent", text="Memory (%)", command=lambda: update_process_list(self.process_tree, "Memory_Percent"))
        self.process_tree.heading("CPU_Percent", text="CPU (%)", command=lambda: update_process_list(self.process_tree, "CPU_Percent"))
        self.process_tree.column("PID", width=80, anchor="center")
        self.process_tree.column("Name", width=300)
        self.process_tree.column("Memory_MB", width=100, anchor="center")
        self.process_tree.column("Memory_Percent", width=100, anchor="center")
        self.process_tree.column("CPU_Percent", width=100, anchor="center")
        scrollbar = ttk.Scrollbar(self.process_frame, orient="vertical", command=self.process_tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill="y")
        self.process_tree.configure(yscrollcommand=scrollbar.set)
        self.kill_button = ttk.Button(self.ram_frame, text="Kill Selected Process", command=lambda: kill_process(self))
        self.kill_button.pack(pady=5)

        # Вкладка GPU
        self.gpu_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.gpu_frame, text="GPU")
        if GPU_AVAILABLE:
            self.gpu_notebook = ttk.Notebook(self.gpu_frame)
            self.gpu_notebook.pack(fill="both", expand=True, padx=10, pady=5)
            self.gpu_usage_frame = ttk.Frame(self.gpu_notebook)
            self.gpu_notebook.add(self.gpu_usage_frame, text="GPU Usage")
            self.gpu_usage_label = ttk.Label(self.gpu_usage_frame, text="Current: N/A", font=('Helvetica', 12))
            self.gpu_usage_label.pack(pady=5)
            self.gpu_usage_fig, self.gpu_usage_ax = create_plot(
                title="GPU Usage", xlabel="Time (s)", ylabel="Usage (%)", ylim=(0, 100), xlim=(0, MAX_HISTORY - 1)
            )
            self.gpu_usage_canvas = FigureCanvasTkAgg(self.gpu_usage_fig, master=self.gpu_usage_frame)
            self.gpu_usage_canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=5)
            self.gpu_usage_line, = self.gpu_usage_ax.plot(np.arange(MAX_HISTORY), [0] * MAX_HISTORY, label="GPU Usage", color='green')
            self.gpu_usage_ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
            self.gpu_usage_fig.tight_layout()
            self.gpu_memory_frame = ttk.Frame(self.gpu_notebook)
            self.gpu_notebook.add(self.gpu_memory_frame, text="GPU Memory")
            self.gpu_memory_label = ttk.Label(self.gpu_memory_frame, text="Used: N/A MB | Total: N/A MB | Percent: N/A%", font=('Helvetica', 12))
            self.gpu_memory_label.pack(pady=5)
            self.gpu_memory_fig, self.gpu_memory_ax = create_plot(
                title="GPU Memory Usage", xlabel="Time (s)", ylabel="Usage (%)", ylim=(0, 100), xlim=(0, MAX_HISTORY - 1)
            )
            self.gpu_memory_canvas = FigureCanvasTkAgg(self.gpu_memory_fig, master=self.gpu_memory_frame)
            self.gpu_memory_canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=5)
            self.gpu_memory_line, = self.gpu_memory_ax.plot(np.arange(MAX_HISTORY), [0] * MAX_HISTORY, label="GPU Memory (%)", color='purple')
            self.gpu_memory_ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
            self.gpu_memory_fig.tight_layout()
            self.gpu_temp_frame = ttk.Frame(self.gpu_notebook)
            self.gpu_notebook.add(self.gpu_temp_frame, text="GPU Temperature")
            self.gpu_temp_label = ttk.Label(self.gpu_temp_frame, text="Current: N/A | Min: N/A | Max: N/A", font=('Helvetica', 12))
            self.gpu_temp_label.pack(pady=5)
            self.gpu_temp_fig, self.gpu_temp_ax = create_plot(
                title="GPU Temperature", xlabel="Time (s)", ylabel="Temp (°C)", ylim=(0, 100), xlim=(0, MAX_HISTORY - 1)
            )
            self.gpu_temp_canvas = FigureCanvasTkAgg(self.gpu_temp_fig, master=self.gpu_temp_frame)
            self.gpu_temp_canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=5)
            self.gpu_temp_line, = self.gpu_temp_ax.plot(np.arange(MAX_HISTORY), [0] * MAX_HISTORY, label="GPU Temp", color='red')
            self.gpu_temp_ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
            self.gpu_temp_fig.tight_layout()
        else:
            ttk.Label(self.gpu_frame, text="GPU monitoring unavailable (GPUtil not installed)", font=('Helvetica', 12)).pack(pady=20)

        # Вкладка Disk
        self.disk_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.disk_frame, text="Disk")
        self.space_frame = ttk.LabelFrame(self.disk_frame, text="Disk Space")
        self.space_frame.pack(fill="x", pady=5, padx=10)
        self.disk_label = ttk.Label(self.space_frame, text="Disk Usage: N/A", font=('Helvetica', 12))
        self.disk_label.pack(pady=5)
        self.smart_frame = ttk.LabelFrame(self.disk_frame, text="Disk Health (SMART)")
        self.smart_frame.pack(fill="x", pady=5, padx=10)
        self.smart_label = ttk.Label(self.smart_frame, text="Temperature: N/A | Health: N/A", font=('Helvetica', 12))
        self.smart_label.pack(pady=5)
        self.disk_fig, self.disk_ax = create_plot(
            title="Disk I/O (MB/s)", xlabel="Time (s)", ylabel="Speed (MB/s)", ylim=(0, 10), xlim=(0, MAX_HISTORY - 1)
        )
        self.disk_canvas = FigureCanvasTkAgg(self.disk_fig, master=self.disk_frame)
        self.disk_canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=5)
        self.disk_read_line, = self.disk_ax.plot(np.arange(MAX_HISTORY), [0] * MAX_HISTORY, label="Read", color='blue')
        self.disk_write_line, = self.disk_ax.plot(np.arange(MAX_HISTORY), [0] * MAX_HISTORY, label="Write", color='orange')
        self.disk_ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        self.disk_fig.tight_layout()

        # Вкладка Network
        self.network_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.network_frame, text="Network")
        self.network_label = ttk.Label(self.network_frame, text="Network: Download 0.0 Mbps | Upload 0.0 Mbps", font=('Helvetica', 12))
        self.network_label.pack(pady=5)
        self.network_fig, self.network_ax = create_plot(
            title="Network Activity (Mbps)", xlabel="Time (s)", ylabel="Speed (Mbps)", ylim=(0, 10), xlim=(0, MAX_HISTORY - 1)
        )
        self.network_canvas = FigureCanvasTkAgg(self.network_fig, master=self.network_frame)
        self.network_canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=5)
        self.network_download_line, = self.network_ax.plot(np.arange(MAX_HISTORY), [0] * MAX_HISTORY, label="Download", color='blue')
        self.network_upload_line, = self.network_ax.plot(np.arange(MAX_HISTORY), [0] * MAX_HISTORY, label="Upload", color='orange')
        self.network_ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        self.network_fig.tight_layout()
        self.net_process_frame = ttk.LabelFrame(self.network_frame, text="Network-Using Processes")
        self.net_process_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.net_process_tree = ttk.Treeview(
            self.net_process_frame, columns=("PID", "Name", "Download_MB", "Upload_MB"), show="headings", height=5
        )
        self.net_process_tree.pack(fill="both", expand=True, side=tk.LEFT)
        self.net_process_tree.heading("PID", text="PID", command=lambda: update_net_process_list(self.net_process_tree, "PID"))
        self.net_process_tree.heading("Name", text="Process Name", command=lambda: update_net_process_list(self.net_process_tree, "Name"))
        self.net_process_tree.heading("Download_MB", text="Download (MB)", command=lambda: update_net_process_list(self.net_process_tree, "Download_MB"))
        self.net_process_tree.heading("Upload_MB", text="Upload (MB)", command=lambda: update_net_process_list(self.net_process_tree, "Upload_MB"))
        self.net_process_tree.column("PID", width=80, anchor="center")
        self.net_process_tree.column("Name", width=300)
        self.net_process_tree.column("Download_MB", width=100, anchor="center")
        self.net_process_tree.column("Upload_MB", width=100, anchor="center")
        net_scrollbar = ttk.Scrollbar(self.net_process_frame, orient="vertical", command=self.net_process_tree.yview)
        net_scrollbar.pack(side=tk.RIGHT, fill="y")
        self.net_process_tree.configure(yscrollcommand=net_scrollbar.set)

        # Вкладка System Info
        self.sysinfo_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.sysinfo_frame, text="System Info")
        canvas = tk.Canvas(self.sysinfo_frame)
        scrollbar = ttk.Scrollbar(self.sysinfo_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.uptime_frame = ttk.LabelFrame(scrollable_frame, text="System Uptime")
        self.uptime_frame.pack(fill="x", pady=5, padx=10)
        self.uptime_label = ttk.Label(self.uptime_frame, text="Uptime: 0d 0h 0m", font=('Helvetica', 10))
        self.uptime_label.pack(anchor="w", pady=2)
        self.last_boot_label = ttk.Label(self.uptime_frame, text="Last Boot: N/A", font=('Helvetica', 10))
        self.last_boot_label.pack(anchor="w", pady=2)
        self.reboot_history_frame = ttk.LabelFrame(scrollable_frame, text="Reboot History")
        self.reboot_history_frame.pack(fill="both", expand=True, pady=5, padx=10)
        self.reboot_tree = ttk.Treeview(self.reboot_history_frame, columns=("DateTime",), show="headings", height=5)
        self.reboot_tree.pack(fill="both", expand=True, side=tk.LEFT)
        self.reboot_tree.heading("DateTime", text="Reboot Date & Time")
        self.reboot_tree.column("DateTime", width=300, anchor="center")
        reboot_scrollbar = ttk.Scrollbar(self.reboot_history_frame, orient="vertical", command=self.reboot_tree.yview)
        reboot_scrollbar.pack(side=tk.RIGHT, fill="y")
        self.reboot_tree.configure(yscrollcommand=reboot_scrollbar.set)
        self.hardware_frame = ttk.LabelFrame(scrollable_frame, text="Hardware Information")
        self.hardware_frame.pack(fill="x", pady=5, padx=10)
        self.cpu_info_label = ttk.Label(self.hardware_frame, text="CPU: N/A", font=('Helvetica', 10))
        self.cpu_info_label.pack(anchor="w", pady=2)
        self.cpu_freq_label = ttk.Label(self.hardware_frame, text="CPU Frequency: N/A", font=('Helvetica', 10))
        self.cpu_freq_label.pack(anchor="w", pady=2)
        self.ram_info_label = ttk.Label(self.hardware_frame, text="RAM: N/A", font=('Helvetica', 10))
        self.ram_info_label.pack(anchor="w", pady=2)
        self.gpu_info_label = ttk.Label(self.hardware_frame, text="GPU: N/A", font=('Helvetica', 10))
        self.gpu_info_label.pack(anchor="w", pady=2)
        self.os_frame = ttk.LabelFrame(scrollable_frame, text="Operating System")
        self.os_frame.pack(fill="x", pady=5, padx=10)
        self.os_info_label = ttk.Label(self.os_frame, text="OS: N/A", font=('Helvetica', 10))
        self.os_info_label.pack(anchor="w", pady=2)
        self.drivers_frame = ttk.LabelFrame(scrollable_frame, text="Installed Drivers")
        self.drivers_frame.pack(fill="both", expand=True, pady=5, padx=10)
        self.drivers_tree = ttk.Treeview(self.drivers_frame, columns=("Name", "Version", "Status"), show="headings", height=10)
        self.drivers_tree.pack(fill="both", expand=True, side=tk.LEFT)
        self.drivers_tree.heading("Name", text="Driver Name")
        self.drivers_tree.heading("Version", text="Version")
        self.drivers_tree.heading("Status", text="Status")
        self.drivers_tree.column("Name", width=300)
        self.drivers_tree.column("Version", width=100, anchor="center")
        self.drivers_tree.column("Status", width=100, anchor="center")
        drivers_scrollbar = ttk.Scrollbar(self.drivers_frame, orient="vertical", command=self.drivers_tree.yview)
        drivers_scrollbar.pack(side=tk.RIGHT, fill="y")
        self.drivers_tree.configure(yscrollcommand=drivers_scrollbar.set)
        self.alert_frame = ttk.LabelFrame(scrollable_frame, text="Alert Log")
        self.alert_frame.pack(fill="both", expand=True, pady=5, padx=10)
        self.alert_tree = ttk.Treeview(self.alert_frame, columns=("Time", "Message"), show="headings", height=5)
        self.alert_tree.pack(fill="both", expand=True, side=tk.LEFT)
        self.alert_tree.heading("Time", text="Time")
        self.alert_tree.heading("Message", text="Message")
        self.alert_tree.column("Time", width=150, anchor="center")
        self.alert_tree.column("Message", width=400)
        alert_scrollbar = ttk.Scrollbar(self.alert_frame, orient="vertical", command=self.alert_tree.yview)
        alert_scrollbar.pack(side=tk.RIGHT, fill="y")
        self.alert_tree.configure(yscrollcommand=alert_scrollbar.set)
        self.copy_button = ttk.Button(scrollable_frame, text="Copy to Clipboard", command=self.copy_system_info)
        self.copy_button.pack(pady=5)

        self.after_ids.append(self.root.after(1000, self.schedule_auto_export))
        self.update_system_info()

    def update_gui(self, data):
        # CPU
        total_cpu, cpu_percent = data['cpu']
        self.cpu_label.config(text=f"Total CPU Usage: {total_cpu:.1f}%")
        recommendation = "Recommendation: Close high-CPU processes."
        if total_cpu > CPU_THRESHOLD:
            self.cpu_label.config(foreground="red")
            messagebox.showwarning("CPU Warning", f"CPU usage exceeded {CPU_THRESHOLD}%: {total_cpu:.1f}%\n{recommendation}")
        else:
            self.cpu_label.config(foreground="black")
        for i, percent in enumerate(cpu_percent):
            color = "red" if percent > 90 else "orange" if percent > 70 else "black"
            self.cpu_labels[i].config(text=f"Core {i}: {percent:.1f}%", foreground=color)
        cpu_history = self.monitor.get_cpu_history()
        for i, line in enumerate(self.cpu_lines):
            cpu_data = cpu_history[i] + [0] * (MAX_HISTORY - len(cpu_history[i]))
            line.set_ydata(cpu_data)
        self.cpu_ax.relim()
        self.cpu_ax.autoscale_view()
        self.cpu_canvas.draw()

        # RAM
        ram = data['ram']
        self.ram_label.config(
            text=f"RAM Usage: {ram.percent:.1f}% ({ram.used/(1024**3):.2f}/{ram.total/(1024**3):.2f} GB, Free: {ram.free/(1024**3):.2f} GB)"
        )
        recommendation = "Recommendation: Close high-memory processes."
        if ram.percent > RAM_THRESHOLD:
            self.ram_label.config(foreground="red")
            messagebox.showwarning("RAM Warning", f"RAM usage exceeded {RAM_THRESHOLD}%: {ram.percent:.1f}%\n{recommendation}")
        else:
            self.ram_label.config(foreground="black")
        ram_history = self.monitor.get_ram_history()
        ram_data = ram_history + [0] * (MAX_HISTORY - len(ram_history))
        self.ram_line.set_ydata(ram_data)
        self.ram_ax.relim()
        self.ram_ax.autoscale_view()
        self.ram_canvas.draw()
        update_process_list(self.process_tree)

        # GPU
        if GPU_AVAILABLE and data['gpu']:
            gpu_usage, gpu_memory_used, gpu_memory_total, gpu_memory_percent, gpu_temp, gpu_temp_min, gpu_temp_max = data['gpu']
            recommendation = "Recommendation: Reduce GPU-intensive tasks."
            self.gpu_usage_label.config(text=f"Current: {gpu_usage:.1f}%", foreground="red" if gpu_usage > 90 else "black")
            gpu_usage_history = self.monitor.get_gpu_usage_history()
            gpu_usage_data = gpu_usage_history + [0] * (MAX_HISTORY - len(gpu_usage_history))
            self.gpu_usage_line.set_ydata(gpu_usage_data)
            self.gpu_usage_ax.relim()
            self.gpu_usage_ax.autoscale_view()
            self.gpu_usage_canvas.draw()
            self.gpu_memory_label.config(
                text=f"Used: {gpu_memory_used:.1f} MB | Total: {gpu_memory_total:.1f} MB | Percent: {gpu_memory_percent:.1f}%",
                foreground="red" if gpu_memory_percent > 90 else "black"
            )
            gpu_memory_history = self.monitor.get_gpu_memory_history()
            gpu_memory_data = gpu_memory_history + [0] * (MAX_HISTORY - len(gpu_memory_history))
            self.gpu_memory_line.set_ydata(gpu_memory_data)
            self.gpu_memory_ax.relim()
            self.gpu_memory_ax.autoscale_view()
            self.gpu_memory_canvas.draw()
            self.gpu_temp_label.config(
                text=f"Current: {gpu_temp:.1f} | Min: {gpu_temp_min:.1f} | Max: {gpu_temp_max:.1f}",
                foreground="red" if gpu_temp > GPU_THRESHOLD else "black"
            )
            if gpu_temp > GPU_THRESHOLD:
                messagebox.showwarning("GPU Warning", f"GPU temperature exceeded {GPU_THRESHOLD}°C: {gpu_temp:.1f}°C\n{recommendation}")
            gpu_temp_history = self.monitor.get_gpu_temp_history()
            gpu_temp_data = gpu_temp_history + [0] * (MAX_HISTORY - len(gpu_temp_history))
            self.gpu_temp_line.set_ydata(gpu_temp_data)
            self.gpu_temp_ax.relim()
            self.gpu_temp_ax.autoscale_view()
            self.gpu_temp_canvas.draw()

        # Disk
        disk, read_speed, write_speed, disk_temp, disk_health = data['disk']
        free_percent = 100 - disk.percent
        self.disk_label.config(
            text=f"Disk Usage: {disk.percent:.1f}% ({disk.used/(1024**3):.2f}/{disk.total/(1024**3):.2f} GB, Free: {disk.free/(1024**3):.2f} GB)",
            foreground="red" if free_percent < DISK_SPACE_THRESHOLD else "black"
        )
        recommendation = "Recommendation: Free up disk space."
        if free_percent < DISK_SPACE_THRESHOLD:
            messagebox.showwarning("Disk Space Warning", f"Free disk space is below {DISK_SPACE_THRESHOLD}%: {free_percent:.1f}%\n{recommendation}")
        self.smart_label.config(text=f"Temperature: {disk_temp} | Health: {disk_health}")
        disk_read_history, disk_write_history = self.monitor.get_disk_io_history()
        disk_read_data = disk_read_history + [0] * (MAX_HISTORY - len(disk_read_history))
        disk_write_data = disk_write_history + [0] * (MAX_HISTORY - len(disk_write_history))
        self.disk_read_line.set_ydata(disk_read_data)
        self.disk_write_line.set_ydata(disk_write_data)
        self.disk_ax.relim()
        self.disk_ax.autoscale_view()
        self.disk_canvas.draw()

        # Network
        download_speed, upload_speed = data['network']
        self.network_label.config(
            text=f"Network: Download {download_speed:.1f} Mbps | Upload {upload_speed:.1f} Mbps",
            foreground="red" if (download_speed > NET_TRAFFIC_THRESHOLD or upload_speed > NET_TRAFFIC_THRESHOLD) else "black"
        )
        recommendation = "Recommendation: Check network-intensive processes."
        if download_speed > NET_TRAFFIC_THRESHOLD or upload_speed > NET_TRAFFIC_THRESHOLD:
            messagebox.showwarning("Network Warning", f"Unusual network activity: Download {download_speed:.1f} Mbps, Upload {upload_speed:.1f} Mbps\n{recommendation}")
        download_history, upload_history = self.monitor.get_network_history()
        download_data = download_history + [0] * (MAX_HISTORY - len(download_history))
        upload_data = upload_history + [0] * (MAX_HISTORY - len(upload_history))
        self.network_download_line.set_ydata(download_data)
        self.network_upload_line.set_ydata(upload_data)
        self.network_ax.relim()
        self.network_ax.autoscale_view()
        self.network_canvas.draw()
        update_net_process_list(self.net_process_tree)

        # System Info
        uptime_seconds, days, hours, minutes = data['uptime']
        self.uptime_label.config(text=f"Uptime: {days}d {hours}h {minutes}m")
        recommendation = "Recommendation: Consider rebooting the system."
        if uptime_seconds > UPTIME_THRESHOLD:
            alert_msg = f"System running for over 7 days: {days}d {hours}h {minutes}m"
            self.alert_log.append(f"{datetime.datetime.now()}: {alert_msg}")
            messagebox.showwarning("Uptime Warning", f"{alert_msg}\n{recommendation}")
        self.update_system_info()

    def update_system_info(self):
        cpu_model = platform.processor() or "N/A"
        self.cpu_info_label.config(text=f"CPU: {cpu_model}")
        try:
            cpu_freq = psutil.cpu_freq()
            freq_text = f"{cpu_freq.current:.2f} MHz (Max: {cpu_freq.max:.2f} MHz)" if cpu_freq else "N/A"
        except:
            freq_text = "N/A"
        self.cpu_freq_label.config(text=f"CPU Frequency: {freq_text}")
        ram_total = psutil.virtual_memory().total / (1024**3)
        self.ram_info_label.config(text=f"RAM: {ram_total:.2f} GB")
        gpu_info = "N/A"
        if GPU_AVAILABLE:
            try:
                gpus = GPUtil.getGPUs()
                if gpus:
                    gpu_info = f"{gpus[0].name} ({gpus[0].memoryTotal:.1f} MB)"
            except:
                pass
        self.gpu_info_label.config(text=f"GPU: {gpu_info}")
        os_info = f"{platform.system()} {platform.release()} ({platform.architecture()[0]})"
        self.os_info_label.config(text=f"OS: {os_info}")
        self.reboot_tree.delete(*self.reboot_tree.get_children())
        for reboot_time in self.reboot_history:
            self.reboot_tree.insert("", "end", values=(reboot_time,))
        self.drivers_tree.delete(*self.drivers_tree.get_children())
        if platform.system() == "Windows" and wmi:
            try:
                c = wmi.WMI()
                drivers = c.Win32_PnPSignedDriver()
                for driver in drivers:
                    name = driver.DeviceName or "Unknown"
                    version = driver.DriverVersion or "N/A"
                    status = driver.Status or "N/A"
                    self.drivers_tree.insert("", "end", values=(name, version, status))
            except Exception as e:
                self.drivers_tree.insert("", "end", values=("Error retrieving drivers", str(e), "N/A"))
        elif platform.system() == "Linux":
            try:
                result = subprocess.run(['lsmod'], capture_output=True, text=True)
                modules = result.stdout.splitlines()[1:]
                for module in modules:
                    name = module.split()[0]
                    self.drivers_tree.insert("", "end", values=(name, "N/A", "Loaded"))
            except Exception as e:
                self.drivers_tree.insert("", "end", values=("Error retrieving modules", str(e), "N/A"))
        else:
            self.drivers_tree.insert("", "end", values=("Driver info not fully supported", "N/A", "N/A"))
        self.alert_tree.delete(*self.alert_tree.get_children())
        for alert in self.alert_log[-10:]:
            time_str, message = alert.split(": ", 1)
            self.alert_tree.insert("", "end", values=(time_str, message))

    def copy_system_info(self):
        info_text = (
            f"CPU: {self.cpu_info_label['text'].split(': ')[1]}\n"
            f"CPU Frequency: {self.cpu_freq_label['text'].split(': ')[1]}\n"
            f"RAM: {self.ram_info_label['text'].split(': ')[1]}\n"
            f"GPU: {self.gpu_info_label['text'].split(': ')[1]}\n"
            f"OS: {self.os_info_label['text'].split(': ')[1]}\n"
            f"Uptime: {self.uptime_label['text'].split(': ')[1]}\n"
            f"Last Boot: {self.last_boot_label['text'].split(': ')[1]}\n"
            "\nInstalled Drivers:\n"
        )
        for item in self.drivers_tree.get_children():
            values = self.drivers_tree.item(item, "values")
            info_text += f"Name: {values[0]}, Version: {values[1]}, Status: {values[2]}\n"
        info_text += "\nAlert Log:\n"
        for item in self.alert_tree.get_children():
            values = self.alert_tree.item(item, "values")
            info_text += f"{values[0]}: {values[1]}\n"
        pyperclip.copy(info_text)
        messagebox.showinfo("Success", "System information copied to clipboard!")

    def manual_export(self):
        from tkinter import simpledialog
        time_range = simpledialog.askinteger("Export", "Enter time range (minutes, 0 for current data):", minvalue=0, maxvalue=60)
        from utilities import export_data
        filename = export_data(self, time_range if time_range else None)
        messagebox.showinfo("Success", f"Data exported to {filename}")

    def schedule_auto_export(self):
        from utilities import export_data
        try:
            filename = export_data(self, time_range_minutes=5)
            setup_logging().info(f"Auto-exported data to {filename}")
        except Exception as e:
            setup_logging().error(f"Error in auto_export: {e}")
        self.after_ids.append(self.root.after(AUTO_EXPORT_INTERVAL * 1000, self.schedule_auto_export))

    def on_closing(self):
        setup_logging().info("Initiating application shutdown")
        for after_id in self.after_ids:
            try:
                self.root.after_cancel(after_id)
                setup_logging().info(f"Cancelled after_id: {after_id}")
            except tk.TclError as e:
                setup_logging().error(f"Error cancelling after_id {after_id}: {e}")
        self.after_ids.clear()
        try:
            self.devnull_file.close()
            sys.stdout = self.original_stdout
            setup_logging().info("Restored sys.stdout")
        except Exception as e:
            setup_logging().error(f"Error restoring sys.stdout: {e}")
        try:
            self.root.destroy()
            setup_logging().info("Destroyed Tkinter root")
        except Exception as e:
            setup_logging().error(f"Error destroying Tkinter root: {e}")
        self.root.after(2000, lambda: os._exit(0))

    def run(self):
        self.root.mainloop()