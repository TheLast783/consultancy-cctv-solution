import sqlite3
import time
import requests
import base64
import os
import shutil
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "sleep_monitor.db")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL_NAME = os.getenv("VLM_MODEL_NAME", "llava")

os.makedirs('ai_detected_sleeping', exist_ok=True)
os.makedirs('false_positives', exist_ok=True)

def process_pending():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, image_path FROM events WHERE vlm_verdict = 'PENDING'")
    rows = c.fetchall()
    
    for row in rows:
        event_id, img_path = row
        if not os.path.exists(img_path):
            c.execute("UPDATE events SET vlm_verdict = 'SKIPPED_MISSING' WHERE id = ?", (event_id,))
            conn.commit()
            continue
            
        with open(img_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            
        payload = {
            "model": MODEL_NAME,
            "prompt": (
                "You are an expert CCTV security AI analyzing a 2-panel crop of a worker over time (Left panel: 30-50s ago, Right panel: current moment).\n\n"
                "Follow this EXACT Sequential Decision Tree:\n"
                "1. HUMAN PRESENCE: Is a real human visible?\n"
                "   - If NO (empty chair, jacket, shadow, object) -> STOP immediately and output 'Verdict: NO'.\n"
                "   - If YES -> Proceed to Step 2.\n"
                "2. STANDING CHECK: Is the person standing upright?\n"
                "   - If YES (standing upright) -> STOP immediately and output 'Verdict: NO'.\n"
                "   - If NO (sitting or lying down) -> Proceed to Step 3.\n"
                "3. SLEEPING POSTURE: Is the person asleep? (Head resting on desk/arms/hands, head slumped forward/back/sideways, eyes closed, dormant posture)\n"
                "   - If YES (sleeping) -> STOP immediately and output 'Verdict: YES'.\n"
                "   - If NO -> Proceed to Step 4.\n"
                "4. ACTIVE WORK CHECK: Is the sitting person actively working? (Typing, writing, actively operating a phone, or working)\n"
                "   - If YES (actively working) -> Output 'Verdict: NO'.\n"
                "   - If NO (sitting inactive/dormant/resting) -> Output 'Verdict: YES'.\n\n"
                "First, state a 1-sentence visual observation explaining your step-by-step decision.\n"
                "On the very last line, write exactly: 'Verdict: YES' or 'Verdict: NO'."
            ),
            "images": [encoded_string],
            "stream": False,
            "options": {"temperature": 0.1}
        }
        
        try:
            print(f"VLM ({MODEL_NAME}) analyzing {img_path}...", flush=True)
            # Set a 90-second timeout to accommodate slower laptop GPU/CPU inference without false timeouts
            response = requests.post(OLLAMA_URL, json=payload, timeout=90)
            response.raise_for_status()
            raw_answer = response.json().get("response", "").strip()
            answer = raw_answer.upper()
            
            # Print the RAW output for full audit visibility
            print(f"  -> Raw AI Output:\n{raw_answer}\n", flush=True)
            
            if "VERDICT: YES" in answer or "VERDICT:YES" in answer:
                verdict = "YES"
            elif "VERDICT: NO" in answer or "VERDICT:NO" in answer:
                verdict = "NO"
            elif "YES" in answer and "NO" not in answer:
                verdict = "YES"
            else:
                verdict = "NO"
            
            filename = os.path.basename(img_path)
            full_filename = filename.replace("sleep_", "full_sleep_", 1)
            full_img_path = os.path.join(os.path.dirname(img_path), full_filename)
            
            if verdict == "YES":
                new_path = os.path.join("ai_detected_sleeping", filename)
                new_full_path = os.path.join("ai_detected_sleeping", full_filename)
            else:
                new_path = os.path.join("false_positives", filename)
                new_full_path = os.path.join("false_positives", full_filename)
                
            shutil.move(img_path, new_path)
            if os.path.exists(full_img_path):
                shutil.move(full_img_path, new_full_path)
            
            # Update database to point to FULL frame for emailer
            final_db_path = new_full_path if os.path.exists(new_full_path) else new_path
            
            c.execute("UPDATE events SET vlm_verdict = ?, image_path = ? WHERE id = ?", (verdict, final_db_path, event_id))
            conn.commit()
            print(f"  -> Final Verdict: {verdict}\n", flush=True)
            
        except requests.exceptions.Timeout:
            print(f"VLM Timeout Warning: Ollama did not respond within 40s. Unblocking queue for {img_path}...", flush=True)
            c.execute("UPDATE events SET vlm_verdict = 'TIMEOUT' WHERE id = ?", (event_id,))
            conn.commit()
            # Move file to false_positives to prevent queue blockage
            try:
                filename = os.path.basename(img_path)
                shutil.move(img_path, os.path.join("false_positives", filename))
            except: pass
        except Exception as e:
            print(f"VLM Error: {e}", flush=True)
            
    conn.close()

if __name__ == "__main__":
    print("VLM Worker started. Waiting for YOLO to flag pending images...")
    while True:
        process_pending()
        time.sleep(5)
