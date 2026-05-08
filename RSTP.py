"""
RTSP Video Streamer — Tkinter GUI
Requirements: pip install opencv-python Pillow
"""

import tkinter as tk
from tkinter import messagebox, filedialog
import threading
import time
import queue
import cv2
from PIL import Image, ImageTk
import datetime


# ─── Theme ────────────────────────────────────────────────────────────────────
BG        = "#0d0f14"
PANEL     = "#13161e"
ACCENT    = "#00e5ff"
ACCENT2   = "#ff3c6e"
TEXT      = "#e8eaf0"
TEXT_DIM  = "#5a607a"
BORDER    = "#1e2235"
SUCCESS   = "#00e096"
WARNING   = "#ffb300"
FONT_MONO = ("Courier New", 10)
FONT_UI   = ("Helvetica", 10)


# ─── Rounded Button ───────────────────────────────────────────────────────────
class CyberButton(tk.Canvas):
    def __init__(self, parent, text, command, color=ACCENT, width=140, height=36, **kwargs):
        super().__init__(parent, width=width, height=height,
                         bg=PANEL, highlightthickness=0, **kwargs)
        self._cmd   = command
        self._color = color
        self._text  = text
        self._w, self._h = width, height
        self._draw(False)
        self.bind("<Enter>",           lambda e: self._draw(True))
        self.bind("<Leave>",           lambda e: self._draw(False))
        self.bind("<ButtonPress-1>",   lambda e: self._press())
        self.bind("<ButtonRelease-1>", lambda e: self._release())

    def _draw(self, hover):
        self.delete("all")
        fill    = self._color if hover else PANEL
        outline = self._color
        r, w, h = 6, self._w, self._h
        self.create_arc(0,      0,      r*2, r*2, start=90,  extent=90, fill=fill, outline=outline)
        self.create_arc(w-r*2,  0,      w,   r*2, start=0,   extent=90, fill=fill, outline=outline)
        self.create_arc(0,      h-r*2,  r*2, h,   start=180, extent=90, fill=fill, outline=outline)
        self.create_arc(w-r*2,  h-r*2,  w,   h,   start=270, extent=90, fill=fill, outline=outline)
        self.create_rectangle(r, 0,   w-r, h,   fill=fill, outline=fill)
        self.create_rectangle(0, r,   w,   h-r, fill=fill, outline=fill)
        self.create_line(r, 0,   w-r, 0,   fill=outline)
        self.create_line(r, h,   w-r, h,   fill=outline)
        self.create_line(0, r,   0,   h-r, fill=outline)
        self.create_line(w, r,   w,   h-r, fill=outline)
        self.create_text(w//2, h//2, text=self._text,
                         fill=BG if hover else self._color,
                         font=("Helvetica", 10, "bold"))

    def _press(self):   self._draw(True)
    def _release(self):
        self._draw(False)
        if self._cmd: self._cmd()

    def configure_color(self, color):
        self._color = color; self._draw(False)
    def configure_text(self, text):
        self._text = text; self._draw(False)


# ─── Main App ─────────────────────────────────────────────────────────────────
class RTSPStreamer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("RTSP Stream Viewer")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(820, 580)

        self._cap         = None
        self._running     = False
        self._thread      = None
        self._frame_q     : queue.Queue = queue.Queue(maxsize=2)
        self._frame_count = 0
        self._photo       = None
        self._recording   = False
        self._writer      = None

        self._build_ui()
        self._poll_queue()

    # ── Build UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Top bar
        top = tk.Frame(self, bg=PANEL, height=52)
        top.pack(fill="x")
        top.pack_propagate(False)
        tk.Label(top, text="◈  RTSP VIEWER", bg=PANEL, fg=ACCENT,
                 font=("Courier New", 14, "bold")).pack(side="left", padx=20)
        self._status_dot = tk.Label(top, text="●", bg=PANEL, fg=TEXT_DIM,
                                    font=("Helvetica", 18))
        self._status_dot.pack(side="right", padx=6)
        self._status_lbl = tk.Label(top, text="OFFLINE", bg=PANEL, fg=TEXT_DIM,
                                    font=FONT_MONO)
        self._status_lbl.pack(side="right", padx=2)
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # Body
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)

        # Sidebar
        side = tk.Frame(body, bg=PANEL, width=240)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        self._build_sidebar(side)

        tk.Frame(body, bg=BORDER, width=1).pack(side="left", fill="y")

        # Canvas
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True)
        self._canvas = tk.Canvas(right, bg="#070910", highlightthickness=0)
        self._canvas.pack(fill="both", expand=True, padx=8, pady=8)
        self._canvas.create_text(10, 10, anchor="nw", text="NO SIGNAL",
                                 fill=BORDER, font=("Courier New", 48, "bold"),
                                 tags="placeholder")

        # Status bar
        bar = tk.Frame(self, bg=PANEL, height=28)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        self._fps_lbl = tk.Label(bar, text="FPS: --", bg=PANEL, fg=TEXT_DIM, font=FONT_MONO)
        self._fps_lbl.pack(side="left", padx=16)
        self._res_lbl = tk.Label(bar, text="RES: --", bg=PANEL, fg=TEXT_DIM, font=FONT_MONO)
        self._res_lbl.pack(side="left", padx=16)
        self._time_lbl = tk.Label(bar, text="", bg=PANEL, fg=TEXT_DIM, font=FONT_MONO)
        self._time_lbl.pack(side="right", padx=16)
        self._update_clock()

    def _build_sidebar(self, parent):
        # URL input
        tk.Label(parent, text="SOURCE URL", bg=PANEL, fg=TEXT_DIM,
                 font=("Courier New", 9)).pack(anchor="w", padx=16, pady=(18, 2))
        url_wrap = tk.Frame(parent, bg=BORDER, padx=1, pady=1)
        url_wrap.pack(fill="x", padx=14, pady=2)
        inner = tk.Frame(url_wrap, bg=PANEL)
        inner.pack(fill="x")
        self._url_var = tk.StringVar(value="rtsp://")
        entry = tk.Entry(inner, textvariable=self._url_var, bg="#0a0c12", fg=ACCENT,
                         insertbackground=ACCENT, font=FONT_MONO, relief="flat", bd=6,
                         selectbackground=ACCENT, selectforeground=BG)
        entry.pack(fill="x")
        entry.bind("<Return>", lambda e: self._toggle_stream())

        # Presets
        tk.Label(parent, text="QUICK PRESETS", bg=PANEL, fg=TEXT_DIM,
                 font=("Courier New", 9)).pack(anchor="w", padx=16, pady=(14, 2))
        presets = [
            ("  Local Webcam",   "0"),
            ("  Big Buck Bunny", "rtsp://wowzaec2demo.streamlock.net/vod/mp4:BigBuckBunny_115k.mp4"),
            ("  Pattern Stream", "rtsp://rtsp.stream/pattern"),
        ]
        for label, url in presets:
            b = tk.Button(parent, text=label, bg="#0d0f18", fg=TEXT_DIM,
                          font=("Courier New", 9), relief="flat", anchor="w",
                          activebackground=BORDER, activeforeground=ACCENT,
                          cursor="hand2", command=lambda u=url: self._url_var.set(u))
            b.pack(fill="x", padx=14, pady=1)

        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=14, pady=14)

        # Buttons
        self._connect_btn = CyberButton(parent, "▶  CONNECT",
                                        command=self._toggle_stream,
                                        color=SUCCESS, width=210, height=40)
        self._connect_btn.pack(padx=14, pady=4)

        CyberButton(parent, "📷  SNAPSHOT",
                    command=self._snapshot,
                    color=ACCENT, width=210, height=36).pack(padx=14, pady=4)

        self._record_btn = CyberButton(parent, "⏺  RECORD",
                                       command=self._toggle_record,
                                       color=ACCENT2, width=210, height=36)
        self._record_btn.pack(padx=14, pady=4)

        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=14, pady=14)

        # Info labels
        tk.Label(parent, text="STREAM INFO", bg=PANEL, fg=TEXT_DIM,
                 font=("Courier New", 9)).pack(anchor="w", padx=16, pady=(0, 6))
        info = tk.Frame(parent, bg=PANEL)
        info.pack(fill="x", padx=16)
        self._info_vars = {}
        for key in ("FPS", "Width", "Height", "Codec", "Frames"):
            row = tk.Frame(info, bg=PANEL)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=f"{key}:", bg=PANEL, fg=TEXT_DIM,
                     font=("Courier New", 9), width=8, anchor="w").pack(side="left")
            var = tk.StringVar(value="—")
            tk.Label(row, textvariable=var, bg=PANEL, fg=TEXT,
                     font=("Courier New", 9), anchor="w").pack(side="left")
            self._info_vars[key] = var

    # ── Stream control ────────────────────────────────────────────────────────
    def _toggle_stream(self):
        (self._stop_stream if self._running else self._start_stream)()

    def _start_stream(self):
        url = self._url_var.get().strip()
        if not url:
            messagebox.showerror("Error", "Enter an RTSP URL first.")
            return
        src = int(url) if url.isdigit() else url

        self._cap = cv2.VideoCapture(src)
        if not self._cap.isOpened():
            messagebox.showerror("Connection Failed",
                                 f"Could not open stream:\n{url}\n\n"
                                 "Verify the URL and your network.")
            self._cap = None
            return

        self._running = True
        self._frame_count = 0
        self._connect_btn.configure_text("■  DISCONNECT")
        self._connect_btn.configure_color(ACCENT2)
        self._set_status("LIVE", SUCCESS)
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def _stop_stream(self):
        self._running = False
        if self._recording:
            self._recording = False
            if self._writer: self._writer.release(); self._writer = None
            self._record_btn.configure_text("⏺  RECORD")
            self._record_btn.configure_color(ACCENT2)
        if self._cap: self._cap.release(); self._cap = None
        self._connect_btn.configure_text("▶  CONNECT")
        self._connect_btn.configure_color(SUCCESS)
        self._set_status("OFFLINE", TEXT_DIM)
        self._canvas.delete("video")
        self._canvas.itemconfig("placeholder", state="normal")
        for v in self._info_vars.values(): v.set("—")
        self._fps_lbl.config(text="FPS: --")
        self._res_lbl.config(text="RES: --")

    def _read_loop(self):
        cnt, ts, fps = 0, time.time(), 0.0
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
                cc = int(self._cap.get(cv2.CAP_PROP_FOURCC))
                codec = "".join([chr((cc >> 8*i) & 0xFF) for i in range(4)])
                self.after(0, lambda f=fps, ww=w, hh=h, c=codec,
                           fc=self._frame_count: self._update_info(f, ww, hh, c, fc))

            if self._recording and self._writer:
                self._writer.write(frame)

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            try:
                if self._frame_q.full(): self._frame_q.get_nowait()
                self._frame_q.put_nowait(rgb)
            except queue.Empty:
                pass

        if self._running:
            self.after(0, self._stop_stream)

    # ── Frame rendering ───────────────────────────────────────────────────────
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

    # ── Snapshot & Record ─────────────────────────────────────────────────────
    def _snapshot(self):
        if not self._running:
            messagebox.showinfo("Snapshot", "No active stream."); return
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = filedialog.asksaveasfilename(
            defaultextension=".png", initialfile=f"snapshot_{ts}.png",
            filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg")])
        if not path: return
        ret, frame = self._cap.read()
        if ret: cv2.imwrite(path, frame); messagebox.showinfo("Saved", f"Snapshot saved:\n{path}")
        else: messagebox.showerror("Error", "Could not capture frame.")

    def _toggle_record(self):
        if not self._running:
            messagebox.showinfo("Record", "Start a stream first."); return
        if self._recording:
            self._recording = False
            if self._writer: self._writer.release(); self._writer = None
            self._record_btn.configure_text("⏺  RECORD")
            self._record_btn.configure_color(ACCENT2)
            messagebox.showinfo("Recording", "Recording stopped.")
        else:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = filedialog.asksaveasfilename(
                defaultextension=".avi", initialfile=f"rec_{ts}.avi",
                filetypes=[("AVI", "*.avi"), ("MP4", "*.mp4")])
            if not path: return
            w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self._writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"XVID"), 20.0, (w, h))
            self._recording = True
            self._record_btn.configure_text("⏹  STOP REC")
            self._record_btn.configure_color(WARNING)

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _set_status(self, text, color):
        self._status_lbl.config(text=text, fg=color)
        self._status_dot.config(fg=color)

    def _update_info(self, fps, w, h, codec, frames):
        self._info_vars["FPS"].set(f"{fps:.1f}")
        self._info_vars["Width"].set(str(w))
        self._info_vars["Height"].set(str(h))
        self._info_vars["Codec"].set(codec.strip())
        self._info_vars["Frames"].set(str(frames))
        self._fps_lbl.config(text=f"FPS: {fps:.1f}", fg=SUCCESS)
        self._res_lbl.config(text=f"RES: {w}×{h}", fg=TEXT)

    def _update_clock(self):
        self._time_lbl.config(text=datetime.datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))
        self.after(1000, self._update_clock)

    def on_close(self):
        self._stop_stream()
        self.destroy()


if __name__ == "__main__":
    app = RTSPStreamer()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.geometry("1040x660")
    app.mainloop()