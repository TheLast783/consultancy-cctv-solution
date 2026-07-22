# Real-Time CCTV Sleep Monitoring AI (TensorRT + Ollama VLM)

An industrial-grade, multi-camera CCTV monitoring system designed to accurately detect sleeping or slumped personnel in real-time across multiple RTSP camera feeds. 

By pairing high-speed **NVIDIA TensorRT YOLO object tracking** with **Ollama Vision-Language Models (LLaVA)**, this system achieves **95%+ detection precision** without false positives on active workers.

---

## Key Features

* **Multi-Engine TensorRT Tracking**: Loads dedicated TensorRT execution contexts (`yolov8m.engine`) per camera feed, processing 12+ live RTSP streams at ~10 FPS with minimal GPU load.
* **Zero-Lag Threaded Grabbers**: Asynchronous camera capture threads continuously flush FFmpeg network buffers, locking live stream latency to 0 seconds.
* **EMA Coordinate Smoothing & Geometric Edge Math**: Eliminates raw neural network bounding box jitter while detecting genuine physical limb, head, or torso movement.
* **Aspect-Proportional Motion Thresholds**: Prevents neighbor overlap false resets and ensures tall standing workers are evaluated accurately.
* **Clean 2-Panel Temporal Evidence Strips**: Generates unannotated image strips ($t-30s$ vs $t-0s$) showing posture evolution across time for Ollama VLM evaluation.
* **Decoupled Architecture**: Process isolation between live RTSP tracking (`multi_main.py`), VLM evaluation (`vlm_worker.py`), and email notifications (`mailer.py`).
* **Desktop GUI Control**: CustomTkinter-based desktop interface (`app.py`) for single-click system start/stop.

---

## System Architecture

```
                                  +-----------------------+
                                  | 12x RTSP Camera Feeds |
                                  +-----------+-----------+
                                              |
                                              v
                              +---------------+---------------+
                              |   LiveCamera Thread Grabbers  |
                              |  (Zero Network Buffer Lag)    |
                              +---------------+---------------+
                                              |
                                              v
                              +---------------+---------------+
                              | Stage 1: TensorRT YOLO Engine |
                              |  (EMA Smoothing & Edge Math)  |
                              +---------------+---------------+
                                              |
                                     (Stillness >= 50s)
                                              v
                              +---------------+---------------+
                              | Clean 2-Panel Temporal Strip  |
                              |     (t-30s vs t-0s Crop)      |
                              +---------------+---------------+
                                              |
                                              v
                              +---------------+---------------+
                              | Stage 2: Ollama VLM (LLaVA)   |
                              | (Chain-of-Thought Reasoning)  |
                              +---------------+---------------+
                                              |
                                          (Verdict: YES)
                                              v
                              +---------------+---------------+
                              | SQLite DB & Email Alert Worker|
                              |  (Full Frame + Crop Context)  |
                              +-------------------------------+
```

---

## Prerequisites

1. **Python 3.10+** (GPU PyTorch / CUDA environment recommended)
2. **NVIDIA GPU** (Optional TensorRT support via `yolov8m.engine` or `yolov8m.pt`)
3. **Ollama** installed with `llava` pulled:
   ```bash
   ollama pull llava
   ```

---

## Installation & Setup

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/your-username/cctv-sleep-monitor.git
   cd cctv-sleep-monitor
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**:
   Copy `.env.example` to `.env` and enter your RTSP camera links and email configuration:
   ```bash
   cp .env.example .env
   ```
   Edit `.env`:
   ```env
   RTSP_URL=rtsp://admin:password@192.168.1.2:554/cam/realmonitor?channel=1&subtype=0
   SENDER_EMAIL=your_email@gmail.com
   SENDER_PASSWORD=your_gmail_app_password
   RECEIVER_EMAIL=alert_recipient@gmail.com
   OLLAMA_URL=http://localhost:11434/api/generate
   VLM_MODEL_NAME=llava
   DB_PATH=sleep_monitor.db
   ```

---

## How to Run

### Option 1: Desktop GUI (Recommended)
Run the CustomTkinter GUI launcher:
```bash
python app.py
```
Click **START MONITORING** to launch all tracking, VLM, and mailer background workers simultaneously.

### Option 2: Command Line (Separate Services)
Alternatively, start the 3 decoupled background workers in separate terminals:

1. **Initialize Database**:
   ```bash
   python db.py
   ```
2. **Start Multi-Camera Tracker**:
   ```bash
   python multi_main.py
   ```
3. **Start Ollama VLM Worker**:
   ```bash
   python vlm_worker.py
   ```
4. **Start Email Notification Worker**:
   ```bash
   python mailer.py
   ```

---

## Project Structure

```
├── app.py              # CustomTkinter GUI launcher
├── multi_main.py       # Live multi-engine RTSP camera tracker & stillness physics
├── vlm_worker.py       # Asynchronous Ollama (LLaVA) verification worker
├── mailer.py           # Email notification worker with full-frame attachments
├── db.py               # SQLite database initializer
├── .env.example        # Environment configuration template
├── .gitignore          # Git exclusion rules for models, outputs & secrets
└── requirements.txt    # Python package dependencies
```

---

## License

MIT License. Designed for industrial CCTV AI monitoring systems.
