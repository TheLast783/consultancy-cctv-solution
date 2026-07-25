import customtkinter as ctk
import subprocess
import os
import sys
import signal
import threading
from tkinter import messagebox
from version import __version__
from updater import check_for_updates, apply_update

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0

class SleepMonitorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("CCTV Sleep Monitor AI")
        self.geometry("540x560")
        
        self.processes = []
        self.is_running = False
        
        # Header / Version Frame
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=20, pady=10)
        
        self.title_lbl = ctk.CTkLabel(self.header_frame, text="CCTV Sleep Monitor AI", font=("Roboto", 20, "bold"))
        self.title_lbl.pack(side="left")
        
        self.ver_lbl = ctk.CTkLabel(self.header_frame, text=f"v{__version__}", font=("Roboto", 12), text_color="gray70")
        self.ver_lbl.pack(side="right")
        
        # Main Status Label
        self.label = ctk.CTkLabel(self, text="System Offline", font=("Roboto", 22, "bold"), text_color="red")
        self.label.pack(pady=15)
        
        # Buttons
        self.start_btn = ctk.CTkButton(self, text="START MONITORING", font=("Roboto", 18), height=45, command=self.start_system)
        self.start_btn.pack(pady=5, padx=40, fill="x")
        
        self.stop_btn = ctk.CTkButton(self, text="STOP", font=("Roboto", 18), height=45, fg_color="red", hover_color="darkred", state="disabled", command=self.stop_system)
        self.stop_btn.pack(pady=5, padx=40, fill="x")
        
        # Live Startup & System Status Log Area
        self.log_box = ctk.CTkTextbox(self, height=160, font=("Consolas", 11), wrap="word")
        self.log_box.pack(pady=15, padx=20, fill="both", expand=True)
        self.log_box.insert("end", "System Status Log Ready. Click START MONITORING to begin...\n")
        self.log_box.configure(state="disabled")
        
        # Update Button
        self.update_btn = ctk.CTkButton(self, text="Check for GitHub Updates", font=("Roboto", 12), fg_color="gray30", hover_color="gray40", command=self.run_update_check)
        self.update_btn.pack(pady=10)

    def log(self, text):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def run_update_check(self):
        self.update_btn.configure(text="Checking for updates...", state="disabled")
        self.update()
        has_update, latest_ver, download_url = check_for_updates()
        if has_update:
            msg = f"A new version (v{latest_ver}) is available on GitHub!\nWould you like to update now?"
            if messagebox.askyesno("Update Available", msg):
                self.stop_system()
                self.update_btn.configure(text="Updating App...")
                self.update()
                apply_update(download_url)
                messagebox.showinfo("Update Complete", "Update downloaded successfully!")
        else:
            messagebox.showinfo("No Updates", f"You are running the latest version (v{__version__}).")
        self.update_btn.configure(text="Check for GitHub Updates", state="normal")

    def monitor_stream(self, proc, prefix=""):
        try:
            for line in iter(proc.stdout.readline, ''):
                if not line:
                    break
                line_str = line.strip()
                # Filter out noisy per-person tracking logs
                if any(k in line_str for k in ["Tracking ID", "Still for:", "Contours", "Active Detection"]):
                    continue
                if line_str:
                    self.after(0, self.log, f"{prefix}{line_str}")
        except:
            pass

    def start_system(self):
        if not self.is_running:
            self.log_box.configure(state="normal")
            self.log_box.delete("1.0", "end")
            self.log_box.configure(state="disabled")
            self.log("[System] Initializing SQLite Database...")
            
            base = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__))
            
            if getattr(sys, 'frozen', False):
                exe = sys.executable
                subprocess.run([exe, "db"], cwd=base, creationflags=CREATE_NO_WINDOW)
                self.log("[System] SQLite Database Initialized.")
                self.log("[System] Loading YOLO GPU Engine & Camera Grabbers...")
                
                p_multi = subprocess.Popen([exe, "multi_main"], cwd=base, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, creationflags=CREATE_NO_WINDOW)
                p_vlm = subprocess.Popen([exe, "vlm_worker"], cwd=base, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, creationflags=CREATE_NO_WINDOW)
                p_mail = subprocess.Popen([exe, "mailer"], cwd=base, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, creationflags=CREATE_NO_WINDOW)
            else:
                python_exe = "python"
                candidates = [
                    os.path.join(base, "gpu_env", "Scripts", "python.exe"),
                    os.path.join(base, "..", "gpu_env", "Scripts", "python.exe"),
                    os.path.join(base, "..", "..", "gpu_env", "Scripts", "python.exe"),
                ]
                for cand in candidates:
                    if os.path.exists(cand):
                        python_exe = os.path.abspath(cand)
                        break
                subprocess.run([python_exe, os.path.join(base, "db.py")], cwd=base, creationflags=CREATE_NO_WINDOW)
                self.log("[System] SQLite Database Initialized.")
                self.log("[System] Loading YOLO GPU Engine & Camera Grabbers...")
                
                p_multi = subprocess.Popen([python_exe, os.path.join(base, "multi_main.py")], cwd=base, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, creationflags=CREATE_NO_WINDOW)
                p_vlm = subprocess.Popen([python_exe, os.path.join(base, "vlm_worker.py")], cwd=base, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, creationflags=CREATE_NO_WINDOW)
                p_mail = subprocess.Popen([python_exe, os.path.join(base, "mailer.py")], cwd=base, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, creationflags=CREATE_NO_WINDOW)
            
            self.processes = [p_multi, p_vlm, p_mail]
            
            # Launch background thread monitors to display high-level startup logs
            threading.Thread(target=self.monitor_stream, args=(p_multi, ""), daemon=True).start()
            threading.Thread(target=self.monitor_stream, args=(p_vlm, "[VLM] "), daemon=True).start()
            threading.Thread(target=self.monitor_stream, args=(p_mail, "[Mail] "), daemon=True).start()
            
            self.is_running = True
            self.label.configure(text="System ACTIVE\n(Tracking RTSP Feeds & VLM)", text_color="green")
            self.start_btn.configure(state="disabled")
            self.stop_btn.configure(state="normal")

    def stop_system(self):
        if self.is_running:
            for p in self.processes:
                try:
                    p.terminate()
                except:
                    pass
            self.processes = []
            self.is_running = False
            self.log("[System] System Stopped. All Workers Offline.")
            self.label.configure(text="System Offline", text_color="red")
            self.start_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        base = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__))
        if cmd == "db":
            import db
            db.init_db()
        elif cmd in ["multi_main", "vlm_worker", "mailer"]:
            import runpy
            script = os.path.join(base, f"{cmd}.py")
            runpy.run_path(script, run_name="__main__")
    else:
        app = SleepMonitorApp()
        app.mainloop()
