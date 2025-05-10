import tkinter as tk
from gui import SystemMonitorGUI
from monitor import ResourceMonitor
from utilities import setup_logging

def main():
    setup_logging()
    root = tk.Tk()
    monitor = ResourceMonitor()
    app = SystemMonitorGUI(root, monitor)
    monitor.start()
    app.run()

if __name__ == "__main__":
    main()