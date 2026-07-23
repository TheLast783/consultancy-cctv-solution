import cv2
import time
import os
import math
import logging
import re
import threading
from dotenv import load_dotenv
from ultralytics import YOLO
import sqlite3

# Force OpenCV/FFmpeg to use TCP instead of UDP for RTSP streams.
# This perfectly fixes the "[rtsp] RTP: PT=60: bad cseq" network dropped-packet warnings!
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

# Silence the internal YOLO logger
logging.getLogger("ultralytics").setLevel(logging.ERROR)

os.makedirs('sleeping images', exist_ok=True)
os.makedirs('pending_review', exist_ok=True)

# 1. Extract and Sanitize URLs from .env
load_dotenv()
urls = []
try:
    with open(".env", "r") as f:
        for line in f:
            line = line.strip().strip(',')
            if line.startswith("rtsp://"):
                fixed_url = re.sub(r'(rtsp://[^:]+:)([^@]+)@([^@]+@.*)', r'\1\2%40\3', line)
                urls.append(fixed_url)
except Exception as e:
    print(f"Error reading .env: {e}")

if not urls:
    print("WARNING: No valid rtsp:// lines found in .env. Falling back to webcam 0.")
    urls = [0]

# 2. Load Independent TensorRT Engines (Bypasses all Batching Restrictions)
model_path = 'yolov8m.engine' if os.path.exists('yolov8m.engine') else 'yolov8m.pt'
print(f"Loading {len(urls)} independent {model_path} instances into GPU RAM...")
models = {url: YOLO(model_path, task='detect') for url in urls}

# 3. Threaded Camera Grabbers
class LiveCamera:
    def __init__(self, src):
        self.src = src
        self.ret, self.frame = False, None
        self.cap = None
        self._connect()
        threading.Thread(target=self._update, daemon=True).start()

    def _connect(self):
        self.cap = cv2.VideoCapture(self.src)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
        self.ret, self.frame = self.cap.read()
        if self.cap.isOpened() and self.ret:
            print(f"[{time.strftime('%H:%M:%S')}] Camera connected: {self.src}")
        else:
            print(f"[{time.strftime('%H:%M:%S')}] FAILED to connect: {self.src}")

    def _update(self):
        while True:
            # cap.read() automatically blocks until a new frame arrives over the network.
            # By not sleeping here, we drain the FFmpeg buffer as fast as physically possible,
            # ensuring 0 accumulation of lag over time!
            if not self.cap.isOpened():
                time.sleep(5)
                self._connect()
                continue
            try:
                self.ret, self.frame = self.cap.read()
                if not self.ret:
                    self.cap.release()
            except: pass

    def read(self): 
        return self.ret, self.frame

cameras = [LiveCamera(url) for url in urls]
global_state = {url: {} for url in urls}
spatial_cooldowns = {url: [] for url in urls}

print(f"\nStarting GPU Pre-Flight: Allocating {len(urls)} engines into VRAM (Takes ~1 minute)...\n")

import numpy as np
dummy_frame = np.zeros((640, 640, 3), dtype=np.uint8)

for i, url in enumerate(urls, 1):
    safe_name = "".join(c if c.isalnum() else "_" for c in str(url)[-20:])
    print(f"[{i}/{len(urls)}] Booting AI Core for Camera: {safe_name}...")
    # Force TensorRT to allocate execution context immediately
    models[url].predict(source=dummy_frame, verbose=False)

print("\nAll AI Cores Online! Starting Live Multi-Engine Inference...\n")

last_heartbeat = 0

# Helper function to create clean 2-panel temporal image strip (t-30s vs t-0s) for Ollama
def create_temporal_strip(img_start, img_now):
    try:
        if img_start is None or img_start.size == 0:
            return img_now
        if img_now is None or img_now.size == 0:
            return img_start
            
        h1, w1 = img_start.shape[:2]
        h2, w2 = img_now.shape[:2]
        target_h = max(h1, h2, 200)
        
        w1_new = max(1, int(w1 * (target_h / float(h1))))
        w2_new = max(1, int(w2 * (target_h / float(h2))))
        
        r1 = cv2.resize(img_start, (w1_new, target_h))
        r2 = cv2.resize(img_now, (w2_new, target_h))
        
        # Add timestamp labels to panels
        cv2.putText(r1, "t-30s (Start)", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        cv2.putText(r2, "t-0s (Current)", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        
        divider = np.zeros((target_h, 6, 3), dtype=np.uint8)
        return np.hstack([r1, divider, r2])
    except Exception as e:
        print(f"Strip creation warning: {e}")
        return img_now if img_now is not None else img_start

while True:
    now = time.time()
    
    if int(now) % 5 == 0 and last_heartbeat != int(now):
        print(f"[{time.strftime('%H:%M:%S')}] Live: Engines running. Looking for humans...", end='\r', flush=True)
        last_heartbeat = int(now)

    for cam in cameras:
        ret, frame = cam.read()
        if not ret or frame is None:
            continue
            
        # Run inference sequentially through the dedicated camera engine at ~10 FPS
        results = models[cam.src].track(
            source=frame,
            persist=True,
            tracker="botsort.yaml",
            classes=[0],
            conf=0.45,           # Raised to 0.45 to eliminate weak non-human ghost box detections
            iou=0.40,
            verbose=False
        )
        
        result = results[0]
        camera_id = str(cam.src)
        track_state = global_state[camera_id]
        current_ids_this_frame = set()
        
        # Clean up spatial cooldowns older than 300s (5 minutes) for this camera
        spatial_cooldowns[camera_id] = [p for p in spatial_cooldowns.get(camera_id, []) if now - p['time'] < 300.0]
        
        if result.boxes is not None and result.boxes.id is not None:
            boxes = result.boxes.xyxy.cpu().numpy().astype(int)
            tids = result.boxes.id.cpu().numpy().astype(int)
            
            for box, tid in zip(boxes, tids):
                raw_x1, raw_y1, raw_x2, raw_y2 = box
                box_width = raw_x2 - raw_x1
                box_height = raw_y2 - raw_y1
                
                # Restored original ghost box filter
                if box_width >= 30 and box_height >= 40:
                    current_ids_this_frame.add(tid)
                    
                    if tid not in track_state:
                        track_state[tid] = {'alerted': False, 'last_center': None, 'still_start_time': now}
                    state = track_state[tid]
                    state['last_seen'] = now
                    
                    # Bounding Box EMA Coordinate Smoothing (Eliminates raw YOLO jitter)
                    alpha = 0.4
                    if 'ema_box' not in state or state['ema_box'] is None:
                        state['ema_box'] = (float(raw_x1), float(raw_y1), float(raw_x2), float(raw_y2))
                    else:
                        ex1, ey1, ex2, ey2 = state['ema_box']
                        state['ema_box'] = (
                            alpha * raw_x1 + (1 - alpha) * ex1,
                            alpha * raw_y1 + (1 - alpha) * ey1,
                            alpha * raw_x2 + (1 - alpha) * ex2,
                            alpha * raw_y2 + (1 - alpha) * ey2
                        )
                    
                    x1, y1, x2, y2 = [int(v) for v in state['ema_box']]
                    s_w, s_h = max(1, x2 - x1), max(1, y2 - y1)
                    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
                    
                    # Extract clean unannotated crop for Ollama (NO red box drawn on it!)
                    pad_x = int(s_w * 0.5)
                    pad_y = int(s_h * 0.5)
                    cy1, cy2 = max(0, y1 - pad_y), min(frame.shape[0], y2 + pad_y)
                    cx1, cx2 = max(0, x1 - pad_x), min(frame.shape[1], x2 + pad_x)
                    
                    clean_crop = frame[cy1:cy2, cx1:cx2].copy() if (cy2 > cy1 and cx2 > cx1) else None
                    if ('initial_crop' not in state or state['initial_crop'] is None) and clean_crop is not None:
                        state['initial_crop'] = clean_crop
                    
                    # 1 FPS Sleep Detection & Geometric Edge Math
                    if 'last_box' not in state or state['last_box'] is None:
                        state['last_center'] = (cx, cy)
                        state['last_box'] = (x1, y1, x2, y2)
                        state['last_eval_time'] = now
                    else:
                        if now - state['last_eval_time'] >= 1.0:
                            prev_cx, prev_cy = state['last_center']
                            px1, py1, px2, py2 = state['last_box']
                            
                            move_dist = math.dist((cx, cy), (prev_cx, prev_cy))
                            
                            # Calculate shift along width and height independently.
                            # Fixing bug: max(s_w, s_h) previously inflated threshold to ~20px for tall standing people!
                            dx1 = abs(x1 - px1)
                            dy1 = abs(y1 - py1)
                            dx2 = abs(x2 - px2)
                            dy2 = abs(y2 - py2)
                            
                            # 4% aspect-proportional thresholds (typically ~3-5px for width and ~6-10px for height)
                            thresh_w = max(3.0, s_w * 0.04)
                            thresh_h = max(4.0, s_h * 0.04)
                            
                            # If torso center moved, OR if any corner/hand/head shifted beyond the tight threshold
                            if move_dist > thresh_w or dx1 > thresh_w or dx2 > thresh_w or dy1 > thresh_h or dy2 > thresh_h:
                                state['still_start_time'] = now
                                state['alerted'] = False
                                if clean_crop is not None:
                                    state['initial_crop'] = clean_crop
                                
                            state['last_center'] = (cx, cy)
                            state['last_box'] = (x1, y1, x2, y2)
                            state['last_eval_time'] = now
                    
                    seconds_still = now - state['still_start_time']
                    current_sec = int(seconds_still)
                    
                    if current_sec > 0 and current_sec != state.get('last_printed_sec', -1) and not state.get('alerted', False):
                        print(f"Cam:{camera_id[-10:]} | Tracking ID:{tid} | Still for: {current_sec}s / 50s")
                        state['last_printed_sec'] = current_sec
                    
                    if seconds_still >= 50.0 and not state.get('alerted', False):
                        state['alerted'] = True
                        
                        # Spatial Position Cooldown: Check if this (X, Y) spot on this camera was triggered in the last 5 minutes
                        in_spatial_cooldown = False
                        for past in spatial_cooldowns.get(camera_id, []):
                            if math.dist((cx, cy), (past['cx'], past['cy'])) < 120.0:
                                in_spatial_cooldown = True
                                break
                                
                        if in_spatial_cooldown:
                            continue
                            
                        # Record new trigger position with timestamp
                        spatial_cooldowns.setdefault(camera_id, []).append({'cx': cx, 'cy': cy, 'time': now})
                        
                        safe_cam_name = "".join(c if c.isalnum() else "_" for c in camera_id[-20:])
                        pending_dir = os.path.abspath('pending_review')
                        os.makedirs(pending_dir, exist_ok=True)
                        
                        img_path = os.path.join(pending_dir, f"sleep_{safe_cam_name}_ID{tid}_{int(now)}.jpg")
                        full_img_path = os.path.join(pending_dir, f"full_sleep_{safe_cam_name}_ID{tid}_{int(now)}.jpg")
                        
                        crop_start = state.get('initial_crop')
                        crop_now = clean_crop if clean_crop is not None else frame
                        
                        # Generate clean 2-panel temporal strip (t-30s vs t-0s) for Ollama
                        temporal_strip = create_temporal_strip(crop_start, crop_now)
                        cv2.imwrite(img_path, temporal_strip)
                        
                        # Save the FULL wide-angle frame with RED box for the boss's email
                        saved_frame = frame.copy()
                        cv2.rectangle(saved_frame, (x1, y1), (x2, y2), (0, 0, 255), 4)
                        cv2.putText(saved_frame, f"SLEEPING ID:{tid}", (x1, max(0, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 3)
                        cv2.imwrite(full_img_path, saved_frame)
                        
                        try:
                            conn = sqlite3.connect('sleep_monitor.db')
                            c = conn.cursor()
                            c.execute("INSERT INTO events (camera_id, person_id, image_path) VALUES (?, ?, ?)", 
                                      (camera_id, tid, img_path))
                            conn.commit()
                            conn.close()
                        except Exception as e:
                            print(f"DB Error: {e}")
                        
                        print(f"\n[{time.strftime('%H:%M:%S')}] SLEEPING — Cam: {safe_cam_name} | ID: {tid} (Sent 2-Panel Temporal Strip to VLM)")

        current_human_count = len(current_ids_this_frame)
        if current_human_count > 0:
            safe_cam_name = "".join(c if c.isalnum() else "_" for c in camera_id[-20:])
            print(f"[{time.strftime('%H:%M:%S')}] Active Detection -> Cam: {safe_cam_name} | Contours (Humans): {current_human_count}")

        # Memory Cleanup
        global_state[camera_id] = {k: v for k, v in track_state.items() if now - v.get('last_seen', 0) <= 5.0}

    # Yield back to OS and cap the global inference loop to 10 FPS to save GPU power
    time.sleep(0.1)
