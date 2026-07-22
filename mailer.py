import sqlite3
import time
import smtplib
from email.message import EmailMessage
import os
from dotenv import load_dotenv

load_dotenv()

DB_PATH = 'sleep_monitor.db'

# === CONFIGURE THESE ===
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")
RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL")
# =======================

def send_email(img_path, camera_id, person_id):
    msg = EmailMessage()
    msg['Subject'] = f"Alert: Sleeping Detected on Camera {camera_id}"
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL
    msg.set_content(f"The VLM AI has visually confirmed a sleeping event on camera '{camera_id}' for Tracking ID {person_id}. Please review the attached image.")
    
    with open(img_path, 'rb') as f:
        img_data = f.read()
        img_name = os.path.basename(img_path)
        
    msg.add_attachment(img_data, maintype='image', subtype='jpeg', filename=img_name)
    
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(SENDER_EMAIL, SENDER_PASSWORD)
        smtp.send_message(msg)

def process_emails():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Find all events where VLM said YES, but we haven't sent the email yet
    c.execute("SELECT id, camera_id, person_id, image_path FROM events WHERE vlm_verdict = 'YES' AND email_sent = 0")
    rows = c.fetchall()
    
    for row in rows:
        event_id, cam_id, person_id, img_path = row
        try:
            print(f"Sending email alert for confirmed event {event_id}...")
            send_email(img_path, cam_id, person_id)
            
            # Mark as sent
            c.execute("UPDATE events SET email_sent = 1 WHERE id = ?", (event_id,))
            conn.commit()
            print(f"Email sent successfully for event {event_id}.")
        except Exception as e:
            print(f"Failed to send email (Check your App Password!): {e}")
            
    conn.close()

if __name__ == "__main__":
    print("Mailer Worker started. Waiting for VLM confirmed events...")
    while True:
        process_emails()
        time.sleep(10)
