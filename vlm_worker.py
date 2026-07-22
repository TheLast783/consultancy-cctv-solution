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
            continue
            
        with open(img_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            
        payload = {
            "model": MODEL_NAME,
            "prompt": (
                "This is a 2-panel CCTV crop showing a person over time (Left panel: 30-50s ago, Right panel: current moment).\n"
                "Analyze the person's posture carefully:\n\n"
                "STRICT RULE 1: If the person is STANDING UPRIGHT (at a counter, stove, desk, machine, or room), they are WORKING/ACTIVE and NOT sleeping. Reply 'Verdict: NO'.\n"
                "STRICT RULE 2: ONLY reply 'Verdict: YES' if the person is physically SLUMPED OVER, head resting flat on a desk/table/arms, lying down, or collapsed.\n\n"
                "Evaluate step-by-step:\n"
                "1. Is the person standing upright or sitting/slumped over?\n"
                "2. Is their head resting flat on a surface/arms or held up while working?\n\n"
                "End your response on the final line with exactly: 'Verdict: YES' or 'Verdict: NO'."
            ),
            "images": [encoded_string],
            "stream": False,
            "options": {"temperature": 0.1}
        }
        
        try:
            print(f"VLM ({MODEL_NAME}) analyzing {img_path}...", flush=True)
            # Set a 40-second timeout to prevent Ollama from hanging the worker process indefinitely
            response = requests.post(OLLAMA_URL, json=payload, timeout=40)
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
