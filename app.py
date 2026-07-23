import customtkinter as ctk
import subprocess
import os
import sys
import signal

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class SleepMonitorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("CCTV Sleep Monitor AI")
        self.geometry("500x350")
        
        self.processes = []
        self.is_running = False
        
        self.label = ctk.CTkLabel(self, text="System Offline", font=("Roboto", 24, "bold"), text_color="red")
        self.label.pack(pady=40)
        
        self.start_btn = ctk.CTkButton(self, text="START MONITORING", font=("Roboto", 18), height=50, command=self.start_system)
        self.start_btn.pack(pady=10)
        
        self.stop_btn = ctk.CTkButton(self, text="STOP", font=("Roboto", 18), height=50, fg_color="red", hover_color="darkred", state="disabled", command=self.stop_system)
        self.stop_btn.pack(pady=10)

    def start_system(self):
        if not self.is_running:
            # Determine base directory (exe folder when frozen, script folder otherwise)
            base = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__))
            
            if getattr(sys, 'frozen', False):
                exe = sys.executable
                subprocess.run([exe, "db"], cwd=base)
                self.processes.append(subprocess.Popen([exe, "multi_main"], cwd=base))
                self.processes.append(subprocess.Popen([exe, "vlm_worker"], cwd=base))
                self.processes.append(subprocess.Popen([exe, "mailer"], cwd=base))
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
                subprocess.run([python_exe, os.path.join(base, "db.py")], cwd=base)
                self.processes.append(subprocess.Popen([python_exe, os.path.join(base, "multi_main.py")], cwd=base))
                self.processes.append(subprocess.Popen([python_exe, os.path.join(base, "vlm_worker.py")], cwd=base))
                self.processes.append(subprocess.Popen([python_exe, os.path.join(base, "mailer.py")], cwd=base))
            
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
