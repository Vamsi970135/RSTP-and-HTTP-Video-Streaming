"""
RTSP + HTTP Video Streamer — Tkinter GUI
Requirements: pip install opencv-python Pillow requests
"""

import tkinter as tk
from tkinter import messagebox, filedialog
import threading
import time
import queue
import cv2
from PIL import Image, ImageTk
import datetime
import urllib.request
import io
import re

# ── Theme ──────────────────────────────────────────────────────────────────────
BG       = "#0d0f14"
PANEL    = "#13161e"
ACCENT   = "#00e5ff"
ACCENT2  = "#ff3c6e"
TEXT     = "#e8eaf0"
TEXT_DIM = "#5a607a"
BORDER   = "#1e2235"
SUCCESS  = "#00e096"
WARNING  = "#ffb300"
MONO     = ("Courier New", 10)


def make_btn(parent, text, command, fg=SUCCESS, bg=PANEL):
    return tk.Button(
        parent, text=text, command=command,
        bg=bg, fg=fg, activebackground=BORDER, activeforeground=fg,
        font=("Helvetica", 10, "bold"), relief="flat",
        bd=0, padx=10, pady=8, cursor="hand2",
        highlightthickness=1, highlightbackground=fg, highlightcolor=fg,
    )


def detect_stream_type(url: str) -> str:
    """Return 'rtsp', 'mjpeg', 'hls', or 'generic'."""
    u = url.lower().strip()
    if u.isdigit():
        return "generic"
    if u.startswith("rtsp://") or u.startswith("rtsps://"):
        return "rtsp"
    if u.endswith(".m3u8"):
        return "hls"
    if "mjpeg" in u or "mjpg" in u or "video.mjpg" in u or "videostream" in u:
        return "mjpeg"
    if u.startswith("http://") or u.startswith("https://"):
        return "http_cv"   # try OpenCV first, fall back to MJPEG parser
    return "generic"


# ── MJPEG HTTP reader ──────────────────────────────────────────────────────────
class MJPEGReader:
    """Reads a raw multipart/x-mixed-replace MJPEG HTTP stream."""
    def __init__(self, url):
        self._url    = url
        self._stream = None
        self._buf    = b""
        self._open()

    def _open(self):
        req = urllib.request.Request(self._url, headers={"User-Agent": "Mozilla/5.0"})
        self._stream = urllib.request.urlopen(req, timeout=10)

    def read_frame(self):
        """Return next JPEG bytes or None."""
        while True:
            chunk = self._stream.read(4096)
            if not chunk:
                return None
            self._buf += chunk
            start = self._buf.find(b"\xff\xd8")
            end   = self._buf.find(b"\xff\xd9")
            if start != -1 and end != -1 and end > start:
                jpg = self._buf[start:end + 2]
                self._buf = self._buf[end + 2:]
                return jpg

    def release(self):
        if self._stream:
            try: self._stream.close()
            except: pass


# ── Main App ───────────────────────────────────────────────────────────────────
class StreamViewer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("RTSP / HTTP Stream Viewer")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(860, 580)

        self._cap         = None   # cv2.VideoCapture or None
        self._mjpeg       = None   # MJPEGReader or None
        self._running     = False
        self._thread      = None
        self._frame_q     = queue.Queue(maxsize=2)
        self._frame_count = 0
        self._photo       = None
        self._recording   = False
        self._writer      = None
        self._stream_type = "—"

        self._build_ui()
        self._poll_queue()

    # ── UI ─────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Top bar
        top = tk.Frame(self, bg=PANEL, height=52)
        top.pack(fill="x")
        top.pack_propagate(False)
        tk.Label(top, text="◈  STREAM VIEWER  [ RTSP · HTTP · MJPEG · HLS ]",
                 bg=PANEL, fg=ACCENT,
                 font=("Courier New", 12, "bold")).pack(side="left", padx=20)
        self._status_dot = tk.Label(top, text="●", bg=PANEL, fg=TEXT_DIM,
                                    font=("Helvetica", 18))
        self._status_dot.pack(side="right", padx=6)
        self._status_lbl = tk.Label(top, text="OFFLINE", bg=PANEL, fg=TEXT_DIM,
                                    font=MONO)
        self._status_lbl.pack(side="right", padx=2)
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)

        # Sidebar
        side = tk.Frame(body, bg=PANEL, width=250)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        self._build_sidebar(side)
        tk.Frame(body, bg=BORDER, width=1).pack(side="left", fill="y")

        # Video canvas
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True)
        self._canvas = tk.Canvas(right, bg="#070910", highlightthickness=0)
        self._canvas.pack(fill="both", expand=True, padx=8, pady=8)
        self._canvas.create_text(10, 10, anchor="nw", text="NO SIGNAL",
                                 fill=BORDER, font=("Courier New", 44, "bold"),
                                 tags="placeholder")

        # Status bar
        bar = tk.Frame(self, bg=PANEL, height=28)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        self._fps_lbl  = tk.Label(bar, text="FPS: --",  bg=PANEL, fg=TEXT_DIM, font=MONO)
        self._fps_lbl.pack(side="left", padx=14)
        self._res_lbl  = tk.Label(bar, text="RES: --",  bg=PANEL, fg=TEXT_DIM, font=MONO)
        self._res_lbl.pack(side="left", padx=14)
        self._type_lbl = tk.Label(bar, text="TYPE: --", bg=PANEL, fg=TEXT_DIM, font=MONO)
        self._type_lbl.pack(side="left", padx=14)
        self._time_lbl = tk.Label(bar, text="", bg=PANEL, fg=TEXT_DIM, font=MONO)
        self._time_lbl.pack(side="right", padx=14)
        self._update_clock()

    def _build_sidebar(self, parent):
        # Protocol selector
        tk.Label(parent, text="PROTOCOL", bg=PANEL, fg=TEXT_DIM,
                 font=("Courier New", 9)).pack(anchor="w", padx=16, pady=(16, 2))
        self._proto_var = tk.StringVar(value="Auto-Detect")
        proto_frame = tk.Frame(parent, bg=PANEL)
        proto_frame.pack(fill="x", padx=14, pady=2)
        for p in ("Auto-Detect", "RTSP", "HTTP / MJPEG", "Webcam"):
            rb = tk.Radiobutton(proto_frame, text=p, variable=self._proto_var,
                                value=p, bg=PANEL, fg=TEXT_DIM, selectcolor=BG,
                                activebackground=PANEL, activeforeground=ACCENT,
                                font=("Courier New", 9), cursor="hand2",
                                command=self._on_proto_change)
            rb.pack(anchor="w")

        # URL input
        tk.Label(parent, text="STREAM URL", bg=PANEL, fg=TEXT_DIM,
                 font=("Courier New", 9)).pack(anchor="w", padx=16, pady=(12, 2))
        url_wrap = tk.Frame(parent, bg=ACCENT, padx=1, pady=1)
        url_wrap.pack(fill="x", padx=14, pady=2)
        inner = tk.Frame(url_wrap, bg=PANEL)
        inner.pack(fill="x")
        self._url_var = tk.StringVar(value="rtsp://")
        entry = tk.Entry(inner, textvariable=self._url_var,
                         bg="#0a0c12", fg=ACCENT, insertbackground=ACCENT,
                         font=MONO, relief="flat", bd=6,
                         selectbackground=ACCENT, selectforeground=BG)
        entry.pack(fill="x")
        entry.bind("<Return>", lambda e: self._toggle_stream())

        # Presets
        tk.Label(parent, text="PRESETS", bg=PANEL, fg=TEXT_DIM,
                 font=("Courier New", 9)).pack(anchor="w", padx=16, pady=(12, 2))
        self._presets = {
            "Auto-Detect": [
                ("  Local Webcam",    "0"),
                ("  RTSP Demo",       "rtsp://wowzaec2demo.streamlock.net/vod/mp4:BigBuckBunny_115k.mp4"),
                ("  HTTP MJPEG Demo", "http://webcam.mchcares.com/mjpg/video.mjpg"),
                ("  HTTP MP4 Demo",   "http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"),
            ],
            "RTSP": [
                ("  RTSP Demo",      "rtsp://wowzaec2demo.streamlock.net/vod/mp4:BigBuckBunny_115k.mp4"),
                ("  Pattern Stream", "rtsp://rtsp.stream/pattern"),
            ],
            "HTTP / MJPEG": [
                ("  MJPEG Webcam",  "http://webcam.mchcares.com/mjpg/video.mjpg"),
                ("  HTTP MP4",      "http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"),
                ("  HTTP Sample 2", "http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ElephantsDream.mp4"),
            ],
            "Webcam": [
                ("  Webcam 0", "0"),
                ("  Webcam 1", "1"),
            ],
        }
        self._preset_frame = tk.Frame(parent, bg=PANEL)
        self._preset_frame.pack(fill="x", padx=14)
        self._render_presets("Auto-Detect")

        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=14, pady=12)

        # Buttons
        self._connect_btn = make_btn(parent, "▶  CONNECT", self._toggle_stream, fg=SUCCESS)
        self._connect_btn.pack(fill="x", padx=14, pady=3)

        make_btn(parent, "📷  SNAPSHOT", self._snapshot, fg=ACCENT).pack(
            fill="x", padx=14, pady=3)

        self._record_btn = make_btn(parent, "⏺  RECORD", self._toggle_record, fg=ACCENT2)
        self._record_btn.pack(fill="x", padx=14, pady=3)

        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=14, pady=12)

        # Info
        tk.Label(parent, text="STREAM INFO", bg=PANEL, fg=TEXT_DIM,
                 font=("Courier New", 9)).pack(anchor="w", padx=16, pady=(0, 4))
        info = tk.Frame(parent, bg=PANEL)
        info.pack(fill="x", padx=16)
        self._info_vars = {}
        for key in ("Protocol", "FPS", "Width", "Height", "Frames"):
            row = tk.Frame(info, bg=PANEL)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=f"{key}:", bg=PANEL, fg=TEXT_DIM,
                     font=("Courier New", 9), width=10, anchor="w").pack(side="left")
            var = tk.StringVar(value="—")
            tk.Label(row, textvariable=var, bg=PANEL, fg=TEXT,
                     font=("Courier New", 9), anchor="w").pack(side="left")
            self._info_vars[key] = var

    def _on_proto_change(self):
        proto = self._proto_var.get()
        defaults = {
            "RTSP":        "rtsp://",
            "HTTP / MJPEG": "http://",
            "Webcam":      "0",
            "Auto-Detect": "rtsp://",
        }
        self._url_var.set(defaults.get(proto, ""))
        self._render_presets(proto)

    def _render_presets(self, proto):
        for w in self._preset_frame.winfo_children():
            w.destroy()
        for label, url in self._presets.get(proto, []):
            b = tk.Button(self._preset_frame, text=label, bg="#0d0f18", fg=TEXT_DIM,
                          font=("Courier New", 9), relief="flat", anchor="w",
                          activebackground=BORDER, activeforeground=ACCENT,
                          cursor="hand2", command=lambda u=url: self._url_var.set(u))
            b.pack(fill="x", pady=1)

    # ── Stream control ─────────────────────────────────────────────────────────
    def _toggle_stream(self):
        (self._stop_stream if self._running else self._start_stream)()

    def _start_stream(self):
        url   = self._url_var.get().strip()
        proto = self._proto_var.get()
        if not url:
            messagebox.showerror("Error", "Enter a stream URL first.")
            return

        # Determine mode
        if proto == "Webcam" or url.isdigit():
            mode = "generic"
            src  = int(url)
        elif proto == "RTSP":
            mode = "rtsp"
            src  = url
        elif proto == "HTTP / MJPEG":
            u = url.lower()
            mode = "mjpeg" if ("mjpeg" in u or "mjpg" in u) else "http_cv"
            src  = url
        else:  # Auto-Detect
            mode = detect_stream_type(url)
            src  = int(url) if url.isdigit() else url

        self._stream_type = mode.upper()
        self._info_vars["Protocol"].set(self._stream_type)

        ok = False
        if mode == "mjpeg":
            ok = self._open_mjpeg(src)
        else:
            ok = self._open_cv(src)

        if not ok:
            return

        self._running     = True
        self._frame_count = 0
        self._connect_btn.config(text="■  DISCONNECT", fg=ACCENT2,
                                 highlightbackground=ACCENT2, highlightcolor=ACCENT2)
        self._set_status("LIVE", SUCCESS)
        self._type_lbl.config(text=f"TYPE: {self._stream_type}", fg=ACCENT)

        self._thread = threading.Thread(
            target=self._read_mjpeg_loop if self._mjpeg else self._read_cv_loop,
            daemon=True)
        self._thread.start()

    def _open_cv(self, src):
        self._cap = cv2.VideoCapture(src)
        if not self._cap.isOpened():
            messagebox.showerror("Connection Failed",
                                 f"OpenCV could not open:\n{src}\n\n"
                                 "Check URL / network / format.")
            self._cap = None
            return False
        return True

    def _open_mjpeg(self, url):
        try:
            self._mjpeg = MJPEGReader(url)
            return True
        except Exception as e:
            messagebox.showerror("Connection Failed",
                                 f"Could not connect to MJPEG stream:\n{url}\n\n{e}")
            self._mjpeg = None
            return False

    def _stop_stream(self):
        self._running = False
        if self._recording:
            self._recording = False
            if self._writer:
                self._writer.release(); self._writer = None
            self._record_btn.config(text="⏺  RECORD", fg=ACCENT2,
                                    highlightbackground=ACCENT2, highlightcolor=ACCENT2)
        if self._cap:
            self._cap.release(); self._cap = None
        if self._mjpeg:
            self._mjpeg.release(); self._mjpeg = None
        self._connect_btn.config(text="▶  CONNECT", fg=SUCCESS,
                                 highlightbackground=SUCCESS, highlightcolor=SUCCESS)
        self._set_status("OFFLINE", TEXT_DIM)
        self._type_lbl.config(text="TYPE: --", fg=TEXT_DIM)
        self._canvas.delete("video")
        self._canvas.itemconfig("placeholder", state="normal")
        for v in self._info_vars.values(): v.set("—")
        self._fps_lbl.config(text="FPS: --")
        self._res_lbl.config(text="RES: --")

    # ── Read loops ─────────────────────────────────────────────────────────────
    def _read_cv_loop(self):
        cnt, ts = 0, time.time()
        while self._running and self._cap and self._cap.isOpened():
            ret, frame = self._cap.read()
            if not ret:
                self.after(0, lambda: self._set_status("LOST", WARNING))
                time.sleep(0.05); continue
            cnt += 1; self._frame_count += 1
            now = time.time()
            if now - ts >= 1.0:
                fps = cnt / (now - ts); cnt = 0; ts = now
                h, w = frame.shape[:2]
                self.after(0, lambda f=fps, ww=w, hh=h,
                           fc=self._frame_count: self._update_info(f, ww, hh, fc))
            if self._recording and self._writer:
                self._writer.write(frame)
            self._push_frame(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        if self._running:
            self.after(0, self._stop_stream)

    def _read_mjpeg_loop(self):
        cnt, ts = 0, time.time()
        while self._running and self._mjpeg:
            try:
                jpg = self._mjpeg.read_frame()
            except Exception:
                self.after(0, lambda: self._set_status("LOST", WARNING))
                time.sleep(0.1); continue
            if jpg is None:
                self.after(0, self._stop_stream); break
            cnt += 1; self._frame_count += 1
            img = Image.open(io.BytesIO(jpg))
            frame_rgb = cv2.cvtColor(
                cv2.imdecode(
                    __import__("numpy").frombuffer(jpg, dtype="uint8"),
                    cv2.IMREAD_COLOR),
                cv2.COLOR_BGR2RGB)
            now = time.time()
            if now - ts >= 1.0:
                fps = cnt / (now - ts); cnt = 0; ts = now
                h, w = frame_rgb.shape[:2]
                self.after(0, lambda f=fps, ww=w, hh=h,
                           fc=self._frame_count: self._update_info(f, ww, hh, fc))
            self._push_frame(frame_rgb)
        if self._running:
            self.after(0, self._stop_stream)

    def _push_frame(self, rgb):
        try:
            if self._frame_q.full():
                self._frame_q.get_nowait()
            self._frame_q.put_nowait(rgb)
        except queue.Empty:
            pass

    # ── Render ─────────────────────────────────────────────────────────────────
    def _poll_queue(self):
        try:
            frame = self._frame_q.get_nowait()
            self._render_frame(frame)
        except queue.Empty:
            pass
        self.after(15, self._poll_queue)

    def _render_frame(self, rgb):
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        if cw < 2 or ch < 2: return
        fh, fw = rgb.shape[:2]
        scale = min(cw / fw, ch / fh)
        nw, nh = int(fw * scale), int(fh * scale)
        img = Image.fromarray(rgb).resize((nw, nh), Image.BILINEAR)
        self._photo = ImageTk.PhotoImage(img)
        x0, y0 = (cw - nw) // 2, (ch - nh) // 2
        self._canvas.delete("video")
        self._canvas.itemconfig("placeholder", state="hidden")
        self._canvas.create_image(x0, y0, anchor="nw", image=self._photo, tags="video")

    # ── Snapshot & Record ──────────────────────────────────────────────────────
    def _snapshot(self):
        if not self._running:
            messagebox.showinfo("Snapshot", "No active stream."); return
        ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = filedialog.asksaveasfilename(
            defaultextension=".png", initialfile=f"snapshot_{ts}.png",
            filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg")])
        if not path: return
        try:
            frame = self._frame_q.queue[-1] if not self._frame_q.empty() else None
        except Exception:
            frame = None
        if frame is not None:
            bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            cv2.imwrite(path, bgr)
            messagebox.showinfo("Saved", f"Snapshot saved:\n{path}")
        else:
            messagebox.showerror("Error", "No frame available yet.")

    def _toggle_record(self):
        if not self._running:
            messagebox.showinfo("Record", "Start a stream first."); return
        if self._recording:
            self._recording = False
            if self._writer: self._writer.release(); self._writer = None
            self._record_btn.config(text="⏺  RECORD", fg=ACCENT2,
                                    highlightbackground=ACCENT2, highlightcolor=ACCENT2)
            messagebox.showinfo("Recording", "Recording stopped.")
        else:
            ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = filedialog.asksaveasfilename(
                defaultextension=".avi", initialfile=f"rec_{ts}.avi",
                filetypes=[("AVI", "*.avi"), ("MP4", "*.mp4")])
            if not path: return
            # get resolution from last frame or cap
            w, h = 640, 480
            if self._cap:
                w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            elif not self._frame_q.empty():
                try:
                    fr = self._frame_q.queue[-1]
                    h, w = fr.shape[:2]
                except Exception:
                    pass
            self._writer = cv2.VideoWriter(
                path, cv2.VideoWriter_fourcc(*"XVID"), 20.0, (w, h))
            self._recording = True
            self._record_btn.config(text="⏹  STOP REC", fg=WARNING,
                                    highlightbackground=WARNING, highlightcolor=WARNING)

    # ── Helpers ────────────────────────────────────────────────────────────────
    def _set_status(self, text, color):
        self._status_lbl.config(text=text, fg=color)
        self._status_dot.config(fg=color)

    def _update_info(self, fps, w, h, frames):
        self._info_vars["FPS"].set(f"{fps:.1f}")
        self._info_vars["Width"].set(str(w))
        self._info_vars["Height"].set(str(h))
        self._info_vars["Frames"].set(str(frames))
        self._fps_lbl.config(text=f"FPS: {fps:.1f}", fg=SUCCESS)
        self._res_lbl.config(text=f"RES: {w}×{h}", fg=TEXT)

    def _update_clock(self):
        self._time_lbl.config(
            text=datetime.datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))
        self.after(1000, self._update_clock)

    def on_close(self):
        self._stop_stream()
        self.destroy()


if __name__ == "__main__":
    app = StreamViewer()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.geometry("1100x680")
    app.mainloop()