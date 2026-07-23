import PyInstaller.__main__
import os
import shutil

print("==========================================")
print("Building Standalone CCTVSleepMonitor.exe")
print("==========================================\n")

opts = [
    'app.py',
    '--name=CCTVSleepMonitor',
    '--onedir',
    '--noconfirm',
    '--clean',
    '--hidden-import=customtkinter',
    '--hidden-import=ultralytics',
    '--hidden-import=cv2',
    '--hidden-import=sqlite3',
    '--hidden-import=dotenv',
    '--hidden-import=requests',
    '--hidden-import=smtplib',
    '--collect-all=customtkinter',
    '--collect-all=ultralytics'
]

PyInstaller.__main__.run(opts)

# Copy TensorRT model engine, .env settings, and python worker scripts into dist folder
dist_dir = os.path.join('dist', 'CCTVSleepMonitor')
if os.path.exists(dist_dir):
    if os.path.exists('yolov8m.engine'):
        print("Copying yolov8m.engine to executable directory...")
        shutil.copy('yolov8m.engine', os.path.join(dist_dir, 'yolov8m.engine'))
    if os.path.exists('yolov8m.pt'):
        shutil.copy('yolov8m.pt', os.path.join(dist_dir, 'yolov8m.pt'))
    if os.path.exists('.env'):
        print("Copying .env configuration to executable directory...")
        shutil.copy('.env', os.path.join(dist_dir, '.env'))
    
    # Copy python worker scripts so app.py subprocess.Popen calls find them
    for script in ['multi_main.py', 'vlm_worker.py', 'mailer.py', 'db.py']:
        if os.path.exists(script):
            shutil.copy(script, os.path.join(dist_dir, script))

print("\n==========================================")
print("Build Successful!")
print("Executable created at: dist\\CCTVSleepMonitor\\CCTVSleepMonitor.exe")
print("==========================================\n")
