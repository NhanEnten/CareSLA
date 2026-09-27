"""
CareSLA — Monitor GUI
Giao diện desktop Python: xem sóng MPU6050 qua MQTT, cảnh báo AI và hủy FALL qua USB.

Cài: pip install matplotlib paho-mqtt pyserial
Chạy: python monitor.py
      hoặc: MQTT_HOST=broker.emqx.io MQTT_USER=xx MQTT_PASS=yy python monitor.py
"""

import json
import argparse
import re
import math
import os
import queue
import struct
import threading
import time
import tkinter as tk
from tkinter import font as tkfont
from datetime import datetime

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.animation import FuncAnimation
import paho.mqtt.client as mqtt

# ── Cấu hình MQTT (sửa tại đây hoặc dùng biến môi trường) ────────────────────
MQTT_HOST  = os.getenv("MQTT_HOST", "test.mosquitto.org")
MQTT_PORT  = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER  = os.getenv("MQTT_USER", "")
MQTT_PASS  = os.getenv("MQTT_PASS", "")
MQTT_TOPIC = "carensla/#"

# Số điểm hiển thị trên đồ thị (10 Hz × 20 giây = 200 điểm)
MAX_POINTS = 200
ACCEL_LSB_PER_G = 2048

# ── Màu sắc ───────────────────────────────────────────────────────────────────
BG         = "#0d0f14"
SURFACE    = "#151820"
BORDER     = "#23283a"
ACCENT     = "#6c8eff"
GREEN      = "#2ecc71"
RED        = "#e74c3c"
YELLOW     = "#f1c40f"
TEXT       = "#e2e8f0"
MUTED      = "#7f8fa6"

ACCEL_COLORS = ["#6c8eff", "#2ecc71", "#e67e22"]
GYRO_COLORS  = ["#9b59b6", "#1abc9c", "#e74c3c"]


# ── Hàng đợi giao tiếp MQTT → GUI (thread-safe) ───────────────────────────────
msg_queue: queue.Queue = queue.Queue()
serial_command_queue: queue.Queue = queue.Queue(maxsize=1)

AI_PATTERN = re.compile(
    r"AI_LIVE p_fall=([0-9.]+) candidate=([01]) invoke_us=(\d+) golden=([01]) window_end_us=(\d+)"
)
FALL_WINDOW_PATTERN = re.compile(r"FALL_WINDOW_OPEN seconds=(\d+)")


def parse_ai_line(line):
    match = AI_PATTERN.search(line)
    if not match:
        return None
    probability, candidate, duration, golden, window_end_us = match.groups()
    probability = float(probability)
    if not math.isfinite(probability) or not 0 <= probability <= 1:
        return None
    return probability, int(candidate), int(duration), int(golden), int(window_end_us)


def parse_ai_control_line(line):
    if "DEVICE_READY" in line:
        return "device_ready",
    window = FALL_WINDOW_PATTERN.search(line)
    if window:
        return "fall_window_open", int(window.group(1))
    if "FALL_CANDIDATE_CLEARED" in line:
        return "fall_candidate_cleared",
    if "CANCEL_COMMAND_ACCEPTED" in line:
        return "cancel_command_accepted",
    if "CANCEL_COMMAND_REJECTED" in line:
        return "cancel_command_rejected",
    return None


def read_ai_serial(port):
    try:
        import serial
        # Khong dung RTS/DTR de reset board khi mo cong.
        connection = serial.Serial(port=None, baudrate=115200, timeout=0.1)
        connection.dtr = False
        connection.rts = False
        connection.port = port
        connection.open()
        msg_queue.put(("serial_status", True, port))
        with connection:
            while True:
                try:
                    command = serial_command_queue.get_nowait()
                except queue.Empty:
                    command = None
                if command is not None:
                    connection.write(command)
                    connection.flush()
                    msg_queue.put(("serial_command_sent",))
                line = connection.readline().decode("utf-8", errors="replace")
                result = parse_ai_line(line)
                if result is not None:
                    msg_queue.put(("ai_live", result))
                    continue
                control = parse_ai_control_line(line)
                if control is not None:
                    msg_queue.put(control)
    except Exception as exc:
        msg_queue.put(("serial_status", False, port))
        msg_queue.put(("ai_error", f"USB AI: {exc}. Đóng idf.py monitor và kiểm tra cổng COM."))

# ── Dữ liệu vẽ đồ thị ────────────────────────────────────────────────────────
accel_data = [[] for _ in range(3)]  # ax, ay, az
gyro_data  = [[] for _ in range(3)]  # gx, gy, gz
sample_timestamps_us = []


# ══════════════════════════════════════════════════════════════════════════════
#  MQTT
# ══════════════════════════════════════════════════════════════════════════════
def on_connect(client, userdata, flags, rc, props=None):
    if rc == 0:
        client.subscribe(MQTT_TOPIC)
        msg_queue.put(("status", "connected", f"Đã kết nối {MQTT_HOST}:{MQTT_PORT}"))
    else:
        msg_queue.put(("status", "error", f"Kết nối thất bại rc={rc}"))


def on_disconnect(client, userdata, flags, rc, props=None):
    msg_queue.put(("status", "disconnected", "Mất kết nối MQTT — đang thử lại…"))


def on_message(client, userdata, msg):
    parts = msg.topic.split("/")
    if len(parts) < 3:
        return
    suffix = parts[2]
    try:
        payload = msg.payload.decode("utf-8", errors="replace")
    except Exception:
        return

    if suffix == "stream":
        try:
            stream_data = json.loads(payload)
            if isinstance(stream_data, dict):
                samples = stream_data.get("samples", [])
                timestamps = stream_data.get("timestamps_us")
                if not isinstance(timestamps, list) or len(timestamps) != len(samples):
                    timestamps = None
            else:
                samples = stream_data  # Legacy [[ax,ay,az,gx,gy,gz], ...]
                timestamps = None
            if isinstance(samples, list):
                msg_queue.put(("stream", samples, timestamps))
        except Exception:
            pass

    elif suffix == "event":
        try:
            data = json.loads(payload)
            msg_queue.put(("event", data, msg.topic))
        except Exception:
            pass

    elif suffix == "raw":
        try:
            data      = json.loads(payload)
            b64       = data.get("samples_b64", "")
            import base64
            raw_bytes = base64.b64decode(b64)
            n = len(raw_bytes) // 12
            samples = []
            for i in range(n):
                vals = struct.unpack_from("<6h", raw_bytes, i * 12)
                samples.append(list(vals))
            msg_queue.put(("raw_window", samples))
        except Exception:
            pass

    elif suffix == "heartbeat":
        try:
            data = json.loads(payload)
            msg_queue.put(("heartbeat", data))
        except Exception:
            pass


def start_mqtt():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect
    client.on_message    = on_message
    client.connect_async(MQTT_HOST, MQTT_PORT, 60)
    client.loop_forever()


# ══════════════════════════════════════════════════════════════════════════════
#  GUI
# ══════════════════════════════════════════════════════════════════════════════
class MonitorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("CareSLA — MPU6050 Monitor")
        self.root.configure(bg=BG)
        self.root.minsize(1100, 650)

        self.real_fall = None
        self.pending_ai_fall = None
        self.serial_connected = False
        self._build_ui()
        self.ai_seen_at = 0
        self.pending_ai_window_end_us = None
        self.ai_window_range_us = None
        self.ai_chart_snapshot = None
        self.ai_label = tk.Label(self.root, text="AI ESP32: chờ USB (--serial COM5) | Kết quả chưa kiểm chứng",
                                 bg=SURFACE, fg=YELLOW, anchor="w", padx=12)
        self.ai_label.pack(fill=tk.X, before=self.root.winfo_children()[0])
        self._setup_charts()
        self._start_animation()
        # Kiểm tra hàng đợi mỗi 80ms
        self.root.after(80, self._process_queue)

    # ── Build UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        mono = tkfont.Font(family="Consolas", size=10)
        bold = tkfont.Font(family="Consolas", size=11, weight="bold")

        # ── Header ────────────────────────────────────────────────────────────
        header = tk.Frame(self.root, bg=SURFACE, height=52)
        header.pack(fill=tk.X, side=tk.TOP)
        header.pack_propagate(False)

        tk.Label(header, text="Care", bg=SURFACE, fg=TEXT,
                 font=tkfont.Font(family="Consolas", size=16, weight="bold")).pack(side=tk.LEFT, padx=(18, 0))
        tk.Label(header, text="SLA", bg=SURFACE, fg=ACCENT,
                 font=tkfont.Font(family="Consolas", size=16, weight="bold")).pack(side=tk.LEFT)
        tk.Label(header, text=" — MPU6050 Monitor", bg=SURFACE, fg=MUTED,
                 font=tkfont.Font(family="Consolas", size=13)).pack(side=tk.LEFT)

        # Trạng thái MQTT
        self.status_lbl = tk.Label(header, text="⬤  Đang kết nối…",
                                   bg=SURFACE, fg=YELLOW,
                                   font=bold, padx=16)
        self.status_lbl.pack(side=tk.RIGHT, padx=10)

        # ── Alert bar (ẩn lúc đầu) ────────────────────────────────────────────
        self.alert_frame = tk.Frame(self.root, bg=RED, height=70)
        self.alert_lbl = tk.Label(self.alert_frame,
                                  text="⚠  AI PHÁT HIỆN NGUY CƠ TÉ NGÃ",
                                  bg=RED, fg="white",
                                  font=tkfont.Font(family="Consolas", size=18, weight="bold"))
        self.alert_lbl.pack(side=tk.LEFT, padx=24)

        self.alert_meta = tk.Label(self.alert_frame, text="",
                                   bg=RED, fg="#ffd0cc",
                                   font=mono)
        self.alert_meta.pack(side=tk.LEFT)

        self.btn_cancel_fall = tk.Button(
            self.alert_frame,
            text="Hủy trên ESP32",
            bg="white", fg=RED,
            font=tkfont.Font(family="Consolas", size=11, weight="bold"),
            relief=tk.FLAT,
            padx=12, pady=6,
            cursor="hand2",
            state=tk.DISABLED,
            command=self._send_cancel_command,
        )

        # ── Body: charts trái + info phải ─────────────────────────────────────
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=(6, 10))

        # Chart container
        self.chart_frame = tk.Frame(body, bg=BG)
        self.chart_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Right panel
        right = tk.Frame(body, bg=SURFACE, width=230,
                         highlightbackground=BORDER, highlightthickness=1)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        right.pack_propagate(False)

        tk.Label(right, text="TRẠNG THÁI", bg=SURFACE, fg=MUTED,
                 font=tkfont.Font(family="Consolas", size=9, weight="bold"),
                 pady=10).pack(fill=tk.X)

        self.stat_device = self._stat_row(right, "Device", "—")
        self.stat_nonce  = self._stat_row(right, "Nonce", "—")
        self.stat_hb     = self._stat_row(right, "Heartbeat", "—")
        self.stat_hz     = self._stat_row(right, "Hz thực tế", "—")
        self.stat_count  = self._stat_row(right, "Tổng mẫu", "0")
        self.stat_impact = self._stat_row(right, "Accel norm", "— g")

        # State badge
        self.state_badge = tk.Label(right,
                                    text="● BÌNH THƯỜNG",
                                    bg="#0d2b1a", fg=GREEN,
                                    font=tkfont.Font(family="Consolas", size=11, weight="bold"),
                                    pady=10)
        self.state_badge.pack(fill=tk.X, padx=10, pady=12)

        # Log box
        tk.Label(right, text="NHẬT KÝ SỰ KIỆN", bg=SURFACE, fg=MUTED,
                 font=tkfont.Font(family="Consolas", size=9, weight="bold")).pack(fill=tk.X)

        log_frame = tk.Frame(right, bg=BG)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        scroll = tk.Scrollbar(log_frame)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.log_box = tk.Text(log_frame, bg=BG, fg=MUTED,
                               font=tkfont.Font(family="Consolas", size=9),
                               wrap=tk.WORD, state=tk.DISABLED,
                               yscrollcommand=scroll.set,
                               relief=tk.FLAT, borderwidth=0)
        self.log_box.pack(fill=tk.BOTH, expand=True)
        scroll.config(command=self.log_box.yview)

        # Tag màu cho log
        self.log_box.tag_config("ok",   foreground=GREEN)
        self.log_box.tag_config("warn", foreground=YELLOW)
        self.log_box.tag_config("err",  foreground=RED)

        # Đếm samples và Hz
        self._total_samples = 0
        self._hz_samples    = 0
        self._hz_t0         = datetime.now()

    def _stat_row(self, parent, label, default):
        """Tạo 1 dòng label: tên + giá trị."""
        row = tk.Frame(parent, bg=SURFACE)
        row.pack(fill=tk.X, padx=10, pady=2)
        tk.Label(row, text=label, bg=SURFACE, fg=MUTED,
                 font=tkfont.Font(family="Consolas", size=9), width=10, anchor=tk.W).pack(side=tk.LEFT)
        val = tk.Label(row, text=default, bg=SURFACE, fg=ACCENT,
                       font=tkfont.Font(family="Consolas", size=9, weight="bold"), anchor=tk.E)
        val.pack(side=tk.RIGHT)
        return val

    # ── Matplotlib charts ─────────────────────────────────────────────────────
    def _setup_charts(self):
        self.fig = plt.Figure(figsize=(9, 5), facecolor=BG)
        gs = gridspec.GridSpec(2, 1, figure=self.fig, hspace=0.45)

        # Accel
        self.ax_a = self.fig.add_subplot(gs[0])
        self._style_ax(self.ax_a, "Gia tốc kế  ax · ay · az  (LSB thô)")
        self.lines_a = [
            self.ax_a.plot([], [], color=ACCEL_COLORS[i], lw=1.2, label=lbl)[0]
            for i, lbl in enumerate(["ax", "ay", "az"])
        ]
        self.ax_a.legend(loc="upper right", facecolor=SURFACE, edgecolor=BORDER,
                         labelcolor=TEXT, fontsize=8)
        self.ai_span_accel = self.ax_a.axvspan(0, 0, color=RED, alpha=0.28, visible=False, zorder=1)
        self.ai_window_label = self.ax_a.text(
            0.01, 0.88, "AI FALL WINDOW", transform=self.ax_a.transAxes,
            color="white", fontsize=8, weight="bold", visible=False,
        )

        # Gyro
        self.ax_g = self.fig.add_subplot(gs[1])
        self._style_ax(self.ax_g, "Con quay hồi chuyển  gx · gy · gz  (LSB thô)")
        self.lines_g = [
            self.ax_g.plot([], [], color=GYRO_COLORS[i], lw=1.2, label=lbl)[0]
            for i, lbl in enumerate(["gx", "gy", "gz"])
        ]
        self.ax_g.legend(loc="upper right", facecolor=SURFACE, edgecolor=BORDER,
                         labelcolor=TEXT, fontsize=8)
        self.ai_span_gyro = self.ax_g.axvspan(0, 0, color=RED, alpha=0.28, visible=False, zorder=1)

        # Embed vào tkinter
        canvas = FigureCanvasTkAgg(self.fig, master=self.chart_frame)
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.canvas = canvas

    @staticmethod
    def _style_ax(ax, title):
        ax.set_facecolor(SURFACE)
        ax.set_title(title, color=MUTED, fontsize=9, loc="left", pad=6)
        ax.tick_params(colors=MUTED, labelsize=8)
        for spine in ax.spines.values():
            spine.set_edgecolor(BORDER)
        ax.yaxis.label.set_color(MUTED)
        ax.xaxis.set_visible(False)

    def _start_animation(self):
        self._anim = FuncAnimation(self.fig, self._update_chart,
                                   interval=100, blit=True, cache_frame_data=False)

    def _update_chart(self, _frame):
        """Được gọi mỗi 100ms bởi FuncAnimation."""
        chart_accel, chart_gyro, chart_timestamps = self.ai_chart_snapshot or (
            accel_data, gyro_data, sample_timestamps_us
        )
        for i, line in enumerate(self.lines_a):
            d = chart_accel[i][-MAX_POINTS:]
            line.set_data(range(len(d)), d)
        for i, line in enumerate(self.lines_g):
            d = chart_gyro[i][-MAX_POINTS:]
            line.set_data(range(len(d)), d)

        visible_timestamps = chart_timestamps[-MAX_POINTS:]
        visible_indices = []
        if self.ai_window_range_us is not None:
            window_start, window_end = self.ai_window_range_us
            visible_indices = [
                index for index, timestamp in enumerate(visible_timestamps)
                if timestamp is not None and window_start <= timestamp <= window_end
            ]
        if visible_indices:
            left = visible_indices[0] - 0.5
            width = visible_indices[-1] - visible_indices[0] + 1
            for span in (self.ai_span_accel, self.ai_span_gyro):
                span.set_x(left)
                span.set_width(width)
                span.set_visible(True)
            self.ai_window_label.set_visible(True)
        else:
            self.ai_span_accel.set_visible(False)
            self.ai_span_gyro.set_visible(False)
            self.ai_window_label.set_visible(False)

        # Tự scale Y
        for ax, data in [(self.ax_a, chart_accel), (self.ax_g, chart_gyro)]:
            flat = [v for series in data for v in series[-MAX_POINTS:]]
            if flat:
                mn, mx = min(flat), max(flat)
                pad = max((mx - mn) * 0.1, 100)
                ax.set_xlim(0, MAX_POINTS)
                ax.set_ylim(mn - pad, mx + pad)

        return self.lines_a + self.lines_g + [self.ai_span_accel, self.ai_span_gyro, self.ai_window_label]

    # ── Xử lý hàng đợi MQTT → GUI ─────────────────────────────────────────────
    def _process_queue(self):
        if self.ai_seen_at and time.monotonic() - self.ai_seen_at > 3:
            self.ai_label.config(text="AI ESP32: không có kết quả mới quá 3 giây — kiểm tra USB / firmware", fg=YELLOW)
            self.ai_seen_at = 0
        try:
            while True:
                item = msg_queue.get_nowait()
                kind = item[0]

                if kind == "ai_live":
                    probability, candidate, duration, golden, window_end_us = item[1]
                    self.ai_seen_at = time.monotonic()
                    if candidate:
                        self._show_ai_pending(probability, window_end_us)
                    self.ai_label.config(text=f"AI ESP32 | điểm FALL: {probability:.1%} | candidate: {candidate} | "
                                             f"Invoke: {duration / 1000:.1f} ms | "
                                             + ("Golden bật" if golden else "THỬ NGHIỆM — golden tắt, chưa kiểm chứng"), fg=YELLOW)
                    continue
                if kind == "device_ready":
                    self._discard_cancel_commands()
                    self.real_fall = None
                    self.pending_ai_fall = None
                    self._clear_ai_window()
                    self.ai_seen_at = 0
                    self._refresh_alert()
                    self._set_state("IDLE")
                    self.ai_label.config(text="AI ESP32: thiết bị đã khởi động, chờ dữ liệu", fg=YELLOW)
                    self._log("ESP32 khởi động lại; banner monitor đã reset. Không gửi ARRIVAL/CANCEL.", "warn")
                    continue
                if kind == "fall_window_open":
                    if self.pending_ai_fall is not None:
                        self.pending_ai_fall["phase"] = "cancel_window"
                        self.pending_ai_fall["cancel_seconds"] = item[1]
                        self._refresh_alert()
                        self._set_state("CANCEL_WINDOW")
                        self._log(f"ESP32 mở cửa sổ hủy {item[1]} giây; bấm Hủy trên monitor để hủy", "warn")
                    continue
                if kind == "serial_status":
                    self.serial_connected = item[1]
                    if not self.serial_connected:
                        self._discard_cancel_commands()
                    if not self.serial_connected and self.pending_ai_fall is not None:
                        self._refresh_alert()
                    continue
                if kind == "serial_command_sent":
                    if self.pending_ai_fall is not None:
                        self.pending_ai_fall["command_sent"] = True
                        self._refresh_alert()
                        self._log("Đã gửi lệnh hủy qua USB; đang chờ ESP32 xác nhận", "warn")
                    continue
                if kind == "cancel_command_accepted":
                    self._log("ESP32 nhận lệnh hủy; chờ MQTT CANCEL", "warn")
                    continue
                if kind == "cancel_command_rejected":
                    if self.pending_ai_fall is not None:
                        self.pending_ai_fall["command_sent"] = False
                        self._refresh_alert()
                    self._log("ESP32 từ chối lệnh hủy vì cửa sổ không còn mở", "warn")
                    continue
                if kind == "fall_candidate_cleared":
                    self._discard_cancel_commands()
                    if self.pending_ai_fall is not None and self.real_fall is None:
                        self.pending_ai_fall = None
                        self._clear_ai_window()
                        self._refresh_alert()
                        self._set_state("IDLE")
                        self._log("ESP32 trở về IDLE; cảnh báo AI chờ đã được gỡ", "ok")
                    continue
                if kind == "ai_error":
                    self._clear_ai_window()
                    self.ai_label.config(text=item[1], fg=RED)
                    self._log(item[1], "warn")
                    continue

                if kind == "status":
                    _, state, text = item
                    color = {"connected": GREEN, "error": RED}.get(state, YELLOW)
                    self.status_lbl.config(text=f"⬤  {text}", fg=color)
                    self._log(text, "ok" if state == "connected" else "warn")

                elif kind == "stream":
                    samples = item[1]  # [[ax,ay,az,gx,gy,gz], ...]
                    timestamps = item[2] if len(item) > 2 else None
                    latest_accel_norm = None
                    for sample_index, s in enumerate(samples):
                        for i in range(3):
                            accel_data[i].append(s[i])
                            gyro_data[i].append(s[i + 3])
                        timestamp = None
                        if timestamps is not None:
                            try:
                                timestamp = int(timestamps[sample_index])
                            except (TypeError, ValueError):
                                pass
                        sample_timestamps_us.append(timestamp)
                        latest_accel_norm = math.sqrt(sum(s[index] * s[index] for index in range(3))) / ACCEL_LSB_PER_G
                    self._resolve_ai_window()
                    if latest_accel_norm is not None:
                        self.stat_impact.config(text=f"{latest_accel_norm:.2f} g")
                    # Giới hạn bộ nhớ
                    for lst in accel_data + gyro_data:
                        if len(lst) > MAX_POINTS * 2:
                            del lst[:-MAX_POINTS]
                    if len(sample_timestamps_us) > MAX_POINTS * 2:
                        del sample_timestamps_us[:-MAX_POINTS]
                    self._total_samples += len(samples)
                    self._hz_samples    += len(samples)
                    self.stat_count.config(text=str(self._total_samples))
                    # Cập nhật Hz mỗi giây
                    dt = (datetime.now() - self._hz_t0).total_seconds()
                    if dt >= 1.0:
                        self.stat_hz.config(text=f"{self._hz_samples/dt:.1f}")
                        self._hz_samples = 0
                        self._hz_t0 = datetime.now()
                    # Thông báo gửi MQTT lên log khi vừa nhận batch đầu tiên
                    # (chỉ log mỗi 50 batch để tránh ngập log)
                    if self._total_samples % 500 == 0:
                        self._log(f"Stream batch: tổng {self._total_samples} mẫu")

                elif kind == "event":
                    data = item[1]
                    topic = item[2] if len(item) > 2 else "carensla/+/event"
                    etype = data.get("eventType")
                    nonce = data.get("nonce", "?")
                    dev   = data.get("device", "")
                    ts_raw = data.get("timestamp", 0)
                    ts_str = datetime.fromtimestamp(ts_raw).strftime("%H:%M:%S") if ts_raw else "?"

                    if dev:
                        self.stat_device.config(text=dev[:10] + "…")
                    self.stat_nonce.config(text=str(nonce))

                    if etype == 1:   # FALL
                        self._discard_cancel_commands()
                        self.pending_ai_fall = None
                        self._show_alert(dev, nonce, ts_str)
                        self._set_state("FALL")
                        self._log(f"✓ MQTT FALL  topic={topic}  nonce={nonce}  ts={ts_str}", "ok")

                    elif etype == 2:  # ARRIVAL
                        self._dismiss_alert()
                        self._set_state("ARRIVAL")
                        self._log(f"✓ ARRIVAL  nonce={nonce}", "ok")
                        self.root.after(3000, lambda: self._set_state("IDLE"))

                    elif etype == 3:  # CANCEL
                        self._discard_cancel_commands()
                        self._dismiss_alert()
                        self._set_state("IDLE")
                        self._log(f"↩ ESP32 đã hủy FALL  nonce={nonce}", "warn")

                elif kind == "raw_window":
                    samples = item[1]
                    # Thay toàn bộ buffer bằng cửa sổ 400 mẫu
                    for i in range(3):
                        accel_data[i][:] = [s[i]     for s in samples]
                        gyro_data[i][:]  = [s[i + 3] for s in samples]
                    sample_timestamps_us[:] = [None] * len(samples)
                    self._log(f"Raw window: {len(samples)} mẫu", "warn")

                elif kind == "heartbeat":
                    data = item[1]
                    ts   = data.get("timestamp", 0)
                    t    = datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts else "?"
                    self.stat_hb.config(text=t)
                    self._log(f"Heartbeat  ts={t}", "ok")

        except queue.Empty:
            pass
        finally:
            self.root.after(80, self._process_queue)

    # ── Alert helpers ──────────────────────────────────────────────────────────
    def _show_ai_pending(self, probability, window_end_us):
        if self.real_fall is not None:
            return
        self.pending_ai_window_end_us = window_end_us
        self._resolve_ai_window()
        if self.pending_ai_fall is None:
            self.pending_ai_fall = {"phase": "checking", "probability": probability, "command_sent": False}
            self._log("AI candidate FALL; đang chờ state machine và nút hủy trên ESP32", "warn")
        else:
            self.pending_ai_fall["probability"] = probability
        self._refresh_alert()
        state = "CANCEL_WINDOW" if self.pending_ai_fall["phase"] == "cancel_window" else "AI_PENDING"
        self._set_state(state)

    def _send_cancel_command(self):
        pending = self.pending_ai_fall
        if pending is None or pending["phase"] != "cancel_window" or not self.serial_connected:
            return
        if pending.get("command_sent"):
            return
        try:
            serial_command_queue.put_nowait(b"CANCEL_FALL\n")
        except queue.Full:
            self._log("Lệnh hủy đang chờ gửi qua USB", "warn")
            return
        pending["command_sent"] = True
        self._refresh_alert()
        self._log("Đang gửi lệnh hủy tới ESP32 qua USB", "warn")

    @staticmethod
    def _discard_cancel_commands():
        while True:
            try:
                serial_command_queue.get_nowait()
            except queue.Empty:
                return

    def _clear_ai_window(self):
        self.pending_ai_window_end_us = None
        self.ai_window_range_us = None
        self.ai_chart_snapshot = None

    def _resolve_ai_window(self):
        target = self.pending_ai_window_end_us
        if target is None:
            return

        end_index = next(
            (index for index in range(len(sample_timestamps_us) - 1, -1, -1)
             if sample_timestamps_us[index] == target),
            None,
        )
        if end_index is None:
            latest_timestamp = next(
                (timestamp for timestamp in reversed(sample_timestamps_us) if timestamp is not None),
                None,
            )
            if latest_timestamp is not None and latest_timestamp > target + 100_000:
                self.pending_ai_window_end_us = None
                self._log("Không tìm thấy đủ mẫu stream cho cửa sổ AI FALL", "warn")
            return

        start_index = end_index - 49
        if start_index < 0:
            return
        window_timestamps = sample_timestamps_us[start_index:end_index + 1]
        if any(timestamp is None for timestamp in window_timestamps) or any(
            window_timestamps[index] - window_timestamps[index - 1] > 30_000
            for index in range(1, len(window_timestamps))
        ):
            self.pending_ai_window_end_us = None
            self._log("Cửa sổ AI FALL có mẫu stream bị thiếu; không tô vùng ước lượng", "warn")
            return

        chart_end = min(len(sample_timestamps_us), end_index + (MAX_POINTS - 50) // 2 + 1)
        chart_start = max(0, chart_end - MAX_POINTS)
        if end_index - 49 < chart_start:
            chart_start = max(0, end_index - MAX_POINTS // 2)
            chart_end = min(len(sample_timestamps_us), chart_start + MAX_POINTS)
            chart_start = max(0, chart_end - MAX_POINTS)

        self.ai_chart_snapshot = (
            [series[chart_start:chart_end] for series in accel_data],
            [series[chart_start:chart_end] for series in gyro_data],
            sample_timestamps_us[chart_start:chart_end],
        )
        self.ai_window_range_us = (window_timestamps[0], window_timestamps[-1])
        self.pending_ai_window_end_us = None

    def _show_alert(self, device, nonce, ts_str):
        self.pending_ai_fall = None
        self.real_fall = {
            "device": device,
            "nonce": nonce,
            "timestamp": ts_str,
        }
        self._refresh_alert()

    def _dismiss_alert(self):
        self.real_fall = None
        self.pending_ai_fall = None
        self._clear_ai_window()
        self._refresh_alert()

    def _refresh_alert(self):
        if self.real_fall is not None:
            fall = self.real_fall
            self.alert_lbl.config(text="🚨  TÉ NGÃ ĐÃ ĐƯỢC ESP32 XÁC NHẬN")
            self.alert_meta.config(
                text=f"  thiết bị: {fall['device'][:12]}…  ·  nonce: {fall['nonce']}  ·  lúc: {fall['timestamp']}"
            )
        elif self.pending_ai_fall is not None:
            pending = self.pending_ai_fall
            if pending["phase"] == "cancel_window":
                self.alert_lbl.config(text="⚠  NGHI TÉ NGÃ — CỬA SỔ HỦY ĐANG MỞ")
                if pending.get("command_sent"):
                    detail = "Đã gửi lệnh; chờ ESP32 xác nhận hủy qua MQTT"
                elif self.serial_connected:
                    detail = f"ESP32 đang kêu còi; còn {pending['cancel_seconds']} giây để hủy"
                else:
                    detail = "USB chưa kết nối; không thể gửi lệnh hủy"
                self.btn_cancel_fall.pack(side=tk.RIGHT, padx=16)
                self.btn_cancel_fall.config(
                    state=tk.NORMAL if self.serial_connected and not pending.get("command_sent") else tk.DISABLED,
                )
            else:
                self.alert_lbl.config(text="⚠  AI PHÁT HIỆN NGUY CƠ TÉ NGÃ")
                detail = "ESP32 đang kiểm tra bất động; chờ còi và cửa sổ hủy trên thiết bị"
                self.btn_cancel_fall.pack_forget()
            self.alert_meta.config(text=f"  điểm FALL: {pending['probability']:.1%}  ·  {detail}")
        else:
            self.btn_cancel_fall.pack_forget()
            self.alert_frame.pack_forget()
            return
        if self.real_fall is not None:
            self.btn_cancel_fall.pack_forget()

        if not self.alert_frame.winfo_manager():
            self.alert_frame.pack(fill=tk.X, after=self.root.winfo_children()[0])
        self.alert_frame.config(bg=RED)
        self.alert_lbl.config(bg=RED)
        self.alert_meta.config(bg=RED)

    # ── State badge ────────────────────────────────────────────────────────────
    def _set_state(self, state):
        cfg = {
            "IDLE":    ("● BÌNH THƯỜNG", "#0d2b1a", GREEN),
            "FALL":    ("🚨 TÉ NGÃ",     "#2b0d0d", RED),
            "ARRIVAL": ("✓ ĐÃ ĐẾN",      "#0d2b1a", GREEN),
            "AI_PENDING": ("⚠ AI NGHI TÉ NGÃ", "#392b08", YELLOW),
            "CANCEL_WINDOW": ("⏱ CHỜ HỦY TRÊN ESP32", "#392b08", YELLOW),
        }.get(state, ("● BÌNH THƯỜNG", "#0d2b1a", GREEN))
        self.state_badge.config(text=cfg[0], bg=cfg[1], fg=cfg[2])
        lbl_map = {"IDLE": "IDLE", "FALL": "FALL !", "ARRIVAL": "ARRIVAL", "AI_PENDING": "AI FALL?", "CANCEL_WINDOW": "HỦY FALL"}
        # cập nhật title thanh tiêu đề
        self.root.title(f"CareSLA — {lbl_map.get(state, state)}")

    # ── Log helper ─────────────────────────────────────────────────────────────
    def _log(self, msg, tag=""):
        t = datetime.now().strftime("%H:%M:%S")
        self.log_box.config(state=tk.NORMAL)
        self.log_box.insert("1.0", f"[{t}] {msg}\n", tag)
        # Giữ tối đa 200 dòng
        lines = int(self.log_box.index("end-1c").split(".")[0])
        if lines > 200:
            self.log_box.delete(f"{lines - 200}.0", tk.END)
        self.log_box.config(state=tk.DISABLED)


# ══════════════════════════════════════════════════════════════════════════════
#  Entrypoint
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Monitor MQTT, AI và lệnh hủy qua USB ESP32")
    parser.add_argument("--serial", help="Cổng USB ESP32, ví dụ COM5; đóng idf.py monitor trước")
    args = parser.parse_args()
    if args.serial:
        threading.Thread(target=read_ai_serial, args=(args.serial,), daemon=True).start()
    # Khởi MQTT ở thread nền
    t = threading.Thread(target=start_mqtt, daemon=True)
    t.start()

    root = tk.Tk()
    app  = MonitorApp(root)
    root.mainloop()
