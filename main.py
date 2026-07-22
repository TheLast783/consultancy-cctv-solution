import cv2
import time
import threading
import os
import math
from ultralytics import YOLO
from dotenv import load_dotenv

os.makedirs('sleeping images', exist_ok=True)

# 1. Detection Model ONLY
yolo = YOLO('yolov8m.pt')

load_dotenv()
RTSP_URL = os.getenv('RTSP_URL')
src = int(RTSP_URL) if RTSP_URL and RTSP_URL.isdigit() else (RTSP_URL or 0)

class LiveCamera:
    def __init__(self, src):
        self.src = src
        self.ret, self.frame = False, None
        self._connect()
        threading.Thread(target=self._update, daemon=True).start()

    def _connect(self):
        self.cap = cv2.VideoCapture(self.src)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
        self.ret, self.frame = self.cap.read()
        if self.cap.isOpened() and self.ret:
            print(f"[{time.strftime('%H:%M:%S')}] Camera connected: {self.src}")

    def _update(self):
        while True:
            if not self.cap.isOpened():
                time.sleep(5)
                self._connect()
                continue
            try:
                self.ret, self.frame = self.cap.read()
                if not self.ret:
                    self.cap.release()
            except: pass
            time.sleep(0.01)

    def read(self): return self.ret, self.frame
    def isOpened(self): return self.cap.isOpened() and self.ret
    def release(self): self.cap.release()

cap = LiveCamera(src)

track_state = {}

# Timer for EXACTLY 1 FPS
last_pose_time = time.time()

print("CCTV Perfect Sleep Monitor (BoT-SORT + Centroid Movement) running. Press Ctrl+C to stop.\n")

while cap.isOpened():
    ret, frame = cap.read()
    if not ret or frame is None:
        time.sleep(0.1)
        continue

    now = time.time()
    frame = cv2.convertScaleAbs(frame, alpha=1.2, beta=20)
    frame = cv2.resize(frame, (1280, 720))
    display_frame = frame.copy()

    # =========================================================================
    # FAST LOOP (Runs at ~10 FPS)
    # Native BoT-SORT Tracking (With iou=0.40 built in!)
    # =========================================================================
    # iou=0.40 perfectly replaces your clean_labels script, deleting overlapping ghost boxes natively!
    res = yolo.track(frame, persist=True, tracker="botsort.yaml",
                     classes=[0], conf=0.30, iou=0.40, imgsz=1280, device=0, verbose=False)
                     
    current_ids_this_frame = set()
    boxes_dict = {}

    if res[0].boxes.id is not None:
        new_boxes = res[0].boxes.xyxy.cpu().numpy().astype(int)
        tids = res[0].boxes.id.cpu().numpy().astype(int)
        
        for box, tid in zip(new_boxes, tids):
            # Filter out tiny ghost boxes (must be at least 30x40 pixels)
            if (box[2]-box[0]) >= 30 and (box[3]-box[1]) >= 40:
                current_ids_this_frame.add(tid)
                boxes_dict[tid] = box
                cv2.rectangle(display_frame, (box[0], box[1]), (box[2], box[3]), (0, 255, 0), 2)
                cv2.putText(display_frame, f"ID: {tid}", (box[0], box[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    # Initialize new IDs
    for tid in current_ids_this_frame:
        track_state.setdefault(tid, {'still': 0, 'alerted': False, 'last_center': None})['last_seen'] = now

    # =========================================================================
    # SLOW LOOP (Runs EXACTLY 1 time per second)
    # Centroid Movement Math
    # =========================================================================
    if now - last_pose_time >= 1.0:
        last_pose_time += 1.0  
        
        for tid in list(current_ids_this_frame):
            box = boxes_dict[tid]
            x1, y1, x2, y2 = box
            
            state = track_state[tid]
            is_moving = False
            
            box_width = x2 - x1
            box_height = y2 - y1
            
            # --- 1. PROPORTIONAL MOVEMENT MATH ---
            # Calculate the exact center point (cx, cy) of the green box.
            cx = (x1 + x2) / 2.0
            cy = (y1 + y2) / 2.0
            
            move_dist = 0.0
            if state['last_center'] is not None:
                prev_cx, prev_cy = state['last_center']
                move_dist = math.dist((cx, cy), (prev_cx, prev_cy))
                
                # We only trigger movement if the box moves by more than 10% of its OWN size.
                threshold = max(box_width, box_height) * 0.10
                
                if move_dist > threshold:
                    is_moving = True
                    print(f"  [Reset ID:{tid:2d}] Moved ({move_dist:.1f} px | thresh: {threshold:.1f})")
            
            state['last_center'] = (cx, cy)

            # --- 2. APPLY LOGIC ---
            if is_moving:
                state['still'] = 0
                state['alerted'] = False
                continue

            state['still'] += 1

            print(f"ID:{tid:2d} | Still:{state['still']:2d}/50 | Move:{move_dist:4.1f}px")

            # --- 3. SLEEP TRIGGERS ---
            if state['still'] >= 50 and not state['alerted']:
                print(f"[{time.strftime('%H:%M:%S')}] SLEEPING — ID:{tid}  (still={state['still']}s)")
                saved = display_frame.copy()
                cv2.rectangle(saved, (x1, y1), (x2, y2), (0, 0, 255), 4)
                cv2.putText(saved, f"SLEEPING ID:{tid}", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 3)
                cv2.imwrite(f"sleeping images/sleep_{tid}_{int(now)}.jpg", saved)
                state['alerted'] = True

    # ── Memory Cleanup ──
    track_state = {k: v for k, v in track_state.items() if now - v['last_seen'] <= 5.0}

cap.release()
