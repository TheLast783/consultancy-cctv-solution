# Core Architecture & System Memory (`memory.md`)

This document serves as the immutable reference for the CCTV Sleep Monitoring AI System logic, parameters, and multi-engine tracking pipeline.

---

## 1. Multi-Camera RTSP & Tracking Engine (`multi_main.py`)

### Core Parameters & Rules:
- **Confidence Threshold**: `conf = 0.45`
- **IOU Threshold**: `iou = 0.40`
- **Tracker**: `tracker = "botsort.yaml"`
- **Target Class**: `classes = [0]` (Person class only)
- **RTSP Network Transport**: `os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"` (Forces TCP transport to prevent dropped UDP packet warnings).

### Bounding Box EMA & Movement Math:
1. **EMA Coordinate Smoothing**: $\alpha = 0.4$
   $$\text{EMA}_{\text{box}} = \alpha \times \text{Box}_{\text{raw}} + (1 - \alpha) \times \text{EMA}_{\text{box\_prev}}$$
2. **Ghost Box Filter**: `box_width >= 30` and `box_height >= 40`
3. **Aspect-Proportional Shift Thresholds**:
   $$\text{thresh}_w = \max(3.0, s_w \times 0.04)$$
   $$\text{thresh}_h = \max(4.0, s_h \times 0.04)$$
4. **Movement Reset Rule**:
   $$\text{Reset } \text{still\_start\_time} \iff (\text{move\_dist} > \text{thresh}_w) \lor (dx_1 > \text{thresh}_w) \lor (dx_2 > \text{thresh}_w) \lor (dy_1 > \text{thresh}_h) \lor (dy_2 > \text{thresh}_h)$$
5. **Stillness Trigger**: Continuous stillness $\ge 50.0$ seconds.

---

## 2. Decoupled Vision-Language AI Verifier (`vlm_worker.py`)

- **Model**: Ollama LLaVA (`MODEL_NAME = "llava"`, loaded via `.env`).
- **Input**: Clean 2-panel temporal evidence strip ($t-30s$ vs $t-0s$, 0 annotations/boxes on crop).
- **Prompt Priming**: Chain-of-Thought (1-sentence visual observation followed by `Verdict: YES` or `Verdict: NO`).

---

## 3. Database & Alert Engine (`db.py` & `mailer.py`)

- **Database**: SQLite (`sleep_monitor.db`).
- **Alert Trigger**: Full wide-angle annotated frame sent via SMTP mailer upon `vlm_verdict = 'YES'`.
