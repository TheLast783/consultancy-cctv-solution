import customtkinter as ctk
import subprocess
import os
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
            python_exe = "python"
            for cand in [r"gpu_env\Scripts\python.exe", r"..\gpu_env\Scripts\python.exe", os.path.join(os.path.dirname(os.path.abspath(__file__)), "gpu_env", "Scripts", "python.exe"), os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gpu_env", "Scripts", "python.exe")]:
                if os.path.exists(cand):
                    python_exe = os.path.abspath(cand)
                    break
            subprocess.run([python_exe, "db.py"])
            
            # 2. Launch the 3 background workers concurrently
            self.processes.append(subprocess.Popen([python_exe, "multi_main.py"]))
            self.processes.append(subprocess.Popen([python_exe, "vlm_worker.py"]))
            self.processes.append(subprocess.Popen([python_exe, "mailer.py"]))
            
            self.is_running = True
            self.label.configure(text="System ACTIVE\n(Tracking 18 Cams & VLM)", text_color="green")
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
    app = SleepMonitorApp()
    app.mainloop()
