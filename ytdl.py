#!/usr/bin/env python3

"""
ytdl-gui v1
"""

import os
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:  #CERTIFICATE_VERIFY_FAILED
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
except ImportError:
    pass

try:
    import yt_dlp
    from yt_dlp.utils import DownloadCancelled, download_range_func
except ImportError:
    yt_dlp = None

try:
    from PIL import Image, ImageSequence, ImageTk 
except ImportError:
    Image = ImageSequence = ImageTk = None

# crisp 
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    try:  # taskbar identity
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ytdl.simple.downloader")
    except Exception:
        pass

GIF_DELAY_MS = 100  
QUALITIES = ["Best", "2160", "1440", "1080", "720", "480", "360", "240", "144"]
VIDEO_FORMATS = ["mp4", "mkv", "webm", "mov", "avi", "flv", "gif"]
NATIVE_VIDEO = ("mp4", "mkv", "webm")  
AUDIO_FORMATS = ["mp3", "m4a", "opus", "flac", "wav", "aac", "vorbis", "alac", "ogg", "aiff", "mka", "best"]  
EXTRACT_AUDIO = ("mp3", "m4a", "opus", "flac", "wav", "aac", "vorbis", "alac", "best")  
LOSSLESS = ("flac", "wav", "alac", "aiff")
AUDIO_QUALITIES = ["Best", "320", "256", "192", "128", "96"]  

# dropdown
FORMAT_CHOICES = {}
for _f in VIDEO_FORMATS:
    FORMAT_CHOICES[_f] = ("video", _f)
for _f in AUDIO_FORMATS:
    if _f == "best":
        FORMAT_CHOICES["original audio (no conversion)"] = ("audio", "best")
    elif _f in LOSSLESS:
        FORMAT_CHOICES[f"{_f} (audio, lossless)"] = ("audio", _f)
    else:
        FORMAT_CHOICES[f"{_f} (audio)"] = ("audio", _f)
BROWSERS = ["None", "chrome", "firefox", "edge", "brave", "opera", "safari", "chromium", "vivaldi"]
SPONSOR_CATEGORIES = ["sponsor", "selfpromo", "interaction", "intro", "outro", "preview"]


def parse_time(text):

    text = text.strip()
    if not text:
        return None
    seconds = 0.0
    for part in text.split(":"):
        seconds = seconds * 60 + float(part)
    return seconds


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def open_folder(path):
    if sys.platform == "win32":
        os.startfile(path)  # noqa
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


class App:
    def __init__(self, root):
        self.root = root
        root.title("ytdl-gui")
        root.minsize(620, 520)

        self.setup_native_theme()
        self.set_icon()

        self.events = queue.Queue()
        self.worker = None
        self.cancel_flag = threading.Event()

        self.build_vars()
        self.build_ui()
        self.root.after(100, self.poll_events)

        if yt_dlp is None:
            messagebox.showerror(
                "Missing dependency",
                "yt-dlp is not installed.\n\nRun:  pip install -U yt-dlp",
            )
        if not shutil.which("ffmpeg"):
            self.log("WARNING: ffmpeg was not found. Merging, audio conversion, "
                     "embedding and cutting will not work until it is installed.")

    # ------------------------------------------------------------------- icon
    def set_icon(self):
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        ico = os.path.join(base, "icon.ico")
        png = os.path.join(base, "icon.png")
        try:
            if sys.platform == "win32" and os.path.exists(ico):
                self.root.iconbitmap(ico)
            elif os.path.exists(png):
                self._icon = tk.PhotoImage(file=png) 
                self.root.iconphoto(True, self._icon)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------ theme
    def setup_native_theme(self):
        style = ttk.Style()
        available = style.theme_names()
        if sys.platform == "win32" and "vista" in available:
            style.theme_use("vista")
        elif sys.platform == "darwin" and "aqua" in available:
            style.theme_use("aqua")
        elif "clam" in available: 
            style.theme_use("clam")

    # -------------------------------------------------------------- variables
    def build_vars(self):
        self.mode = tk.StringVar(value="video")
        self.quality = tk.StringVar(value="Best")
        self.container = tk.StringVar(value="mp4")
        self.audio_bitrate = tk.StringVar(value="Best")
        self.format_label = tk.StringVar(value="mp4")
        self.folder = tk.StringVar(value=self.default_folder())
        self.template = tk.StringVar(value="%(title)s [%(id)s].%(ext)s")

        self.playlist = tk.BooleanVar(value=False)
        self.playlist_items = tk.StringVar()
        self.subs = tk.BooleanVar(value=False)
        self.sub_langs = tk.StringVar(value="en")
        self.auto_subs = tk.BooleanVar(value=False)
        self.embed_subs = tk.BooleanVar(value=False)
        self.thumbnail = tk.BooleanVar(value=False)
        self.metadata = tk.BooleanVar(value=True)
        self.sponsorblock = tk.BooleanVar(value=False)
        self.archive = tk.BooleanVar(value=False)
        self.write_desc = tk.BooleanVar(value=False)
        self.write_info = tk.BooleanVar(value=False)
        self.open_when_done = tk.BooleanVar(value=False)

        self.start_time = tk.StringVar()
        self.end_time = tk.StringVar()
        self.rate_limit = tk.StringVar()
        self.proxy = tk.StringVar()
        self.cookies_browser = tk.StringVar(value="None")
        self.cookies_file = tk.StringVar()
        self.retries = tk.StringVar(value="10")
        self.no_cert_check = tk.BooleanVar(value=False)

        self.status = tk.StringVar(value="Ready")
        self.info_text = tk.StringVar(value="")
        self.progress = tk.DoubleVar(value=0)

    @staticmethod
    def default_folder():
        d = os.path.join(os.path.expanduser("~"), "Downloads")
        return d if os.path.isdir(d) else os.path.expanduser("~")

    # --------------------------------------------------------------------- UI
    def build_ui(self):
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=8, pady=(8, 0))

        main = ttk.Frame(nb, padding=8)
        opts = ttk.Frame(nb, padding=8)
        adv = ttk.Frame(nb, padding=8)
        imgf = ttk.Frame(nb, padding=8)
        logf = ttk.Frame(nb, padding=8)
        nb.add(main, text="Download")
        nb.add(opts, text="Options")
        nb.add(adv, text="Advanced")
        nb.add(imgf, text="Chimata shrine")
        nb.add(logf, text="Log")

        self.build_main(main)
        self.build_options(opts)
        self.build_advanced(adv)
        self.build_image(imgf)
        self.build_log(logf)

        bottom = ttk.Frame(self.root, padding=8)
        bottom.pack(fill="x")
        ttk.Progressbar(bottom, variable=self.progress, maximum=100).pack(fill="x")
        ttk.Label(bottom, textvariable=self.status).pack(anchor="w", pady=(4, 0))

    def build_main(self, f):
        f.columnconfigure(1, weight=1)
        f.rowconfigure(1, weight=1)

        ttk.Label(f, text="URL(s), one per line:").grid(row=0, column=0, columnspan=3, sticky="w")

        box = ttk.Frame(f)
        box.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=4)
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)
        self.urls = tk.Text(box, height=6, undo=True, wrap="none")
        sb = ttk.Scrollbar(box, command=self.urls.yview)
        self.urls.configure(yscrollcommand=sb.set)
        self.urls.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")

        row = ttk.Frame(f)
        row.grid(row=2, column=0, columnspan=3, sticky="w", pady=(0, 6))
        ttk.Button(row, text="Paste", command=self.paste).pack(side="left")
        ttk.Button(row, text="Clear", command=lambda: self.urls.delete("1.0", "end")).pack(side="left", padx=4)
        ttk.Button(row, text="Get info", command=self.fetch_info).pack(side="left")
        ttk.Button(row, text="Load list from file…", command=self.load_list).pack(side="left", padx=4)

        ttk.Label(f, textvariable=self.info_text, wraplength=560, justify="left").grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(0, 6))

        ttk.Label(f, text="Format:").grid(row=4, column=0, sticky="w", pady=2)
        self.format_cb = ttk.Combobox(f, textvariable=self.format_label, values=list(FORMAT_CHOICES),
                                      state="readonly", width=30)
        self.format_cb.grid(row=4, column=1, sticky="w")
        self.format_cb.bind("<<ComboboxSelected>>", lambda e: self.on_format_change())

        ttk.Label(f, text="Video quality:").grid(row=5, column=0, sticky="w", pady=2)
        self.quality_cb = ttk.Combobox(f, textvariable=self.quality, values=QUALITIES, state="readonly", width=10)
        self.quality_cb.grid(row=5, column=1, sticky="w")

        ttk.Label(f, text="Audio quality:").grid(row=6, column=0, sticky="w", pady=2)
        self.audioq_cb = ttk.Combobox(f, textvariable=self.audio_bitrate, values=AUDIO_QUALITIES,
                                      state="disabled", width=10)
        self.audioq_cb.grid(row=6, column=1, sticky="w")

        ttk.Label(f, text="Save to:").grid(row=7, column=0, sticky="w", pady=2)
        ttk.Entry(f, textvariable=self.folder).grid(row=7, column=1, sticky="ew")
        ttk.Button(f, text="Browse…", command=self.pick_folder).grid(row=7, column=2, padx=(4, 0))

        btns = ttk.Frame(f)
        btns.grid(row=8, column=0, columnspan=3, sticky="w", pady=(10, 0))
        self.dl_btn = ttk.Button(btns, text="Download", command=self.start)
        self.dl_btn.pack(side="left")
        self.cancel_btn = ttk.Button(btns, text="Cancel", command=self.cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=4)
        ttk.Button(btns, text="Open folder", command=self.open_dest).pack(side="left")

    def build_options(self, f):
        f.columnconfigure(1, weight=1)
        r = 0

        ttk.Checkbutton(f, text="Download whole playlist if the link is one", variable=self.playlist).grid(row=r, column=0, columnspan=2, sticky="w", pady=(8, 0))
        r += 1
        ttk.Label(f, text="Playlist items (e.g. 1-5,8):").grid(row=r, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.playlist_items, width=20).grid(row=r, column=1, sticky="w")
        r += 1

        ttk.Checkbutton(f, text="Download subtitles", variable=self.subs).grid(row=r, column=0, columnspan=2, sticky="w", pady=(8, 0))
        r += 1
        ttk.Label(f, text="Subtitle languages (comma sep.):").grid(row=r, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.sub_langs, width=20).grid(row=r, column=1, sticky="w")
        r += 1
        ttk.Checkbutton(f, text="Include auto-generated subtitles", variable=self.auto_subs).grid(row=r, column=0, columnspan=2, sticky="w")
        r += 1
        ttk.Checkbutton(f, text="Embed subtitles in the video", variable=self.embed_subs).grid(row=r, column=0, columnspan=2, sticky="w")
        r += 1

        ttk.Checkbutton(f, text="Embed thumbnail", variable=self.thumbnail).grid(row=r, column=0, columnspan=2, sticky="w", pady=(8, 0))
        r += 1
        ttk.Checkbutton(f, text="Embed metadata and chapters", variable=self.metadata).grid(row=r, column=0, columnspan=2, sticky="w")
        r += 1
        ttk.Checkbutton(f, text="Remove sponsor segments (SponsorBlock)", variable=self.sponsorblock).grid(row=r, column=0, columnspan=2, sticky="w")
        r += 1
        ttk.Checkbutton(f, text="Save description (.description)", variable=self.write_desc).grid(row=r, column=0, columnspan=2, sticky="w")
        r += 1
        ttk.Checkbutton(f, text="Save info (.info.json)", variable=self.write_info).grid(row=r, column=0, columnspan=2, sticky="w")
        r += 1
        ttk.Checkbutton(f, text="Skip videos already downloaded (archive)", variable=self.archive).grid(row=r, column=0, columnspan=2, sticky="w")
        r += 1
        ttk.Checkbutton(f, text="Open folder when finished", variable=self.open_when_done).grid(row=r, column=0, columnspan=2, sticky="w")

    def build_advanced(self, f):
        f.columnconfigure(1, weight=1)
        r = 0

        def entry(label, var, hint=""):
            nonlocal r
            ttk.Label(f, text=label).grid(row=r, column=0, sticky="w", pady=2)
            ttk.Entry(f, textvariable=var).grid(row=r, column=1, sticky="ew")
            if hint:
                ttk.Label(f, text=hint).grid(row=r, column=2, sticky="w", padx=(6, 0))
            r += 1

        entry("Filename template:", self.template)
        entry("Cut start:", self.start_time, "e.g. 1:30")
        entry("Cut end:", self.end_time, "e.g. 2:45")
        entry("Speed limit:", self.rate_limit, "e.g. 500K or 2M")
        entry("Proxy:", self.proxy, "e.g. http://host:port")
        entry("Retries:", self.retries)

        ttk.Label(f, text="Cookies from browser:").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Combobox(f, textvariable=self.cookies_browser, values=BROWSERS, state="readonly", width=12).grid(row=r, column=1, sticky="w")
        r += 1
        ttk.Label(f, text="Cookies file:").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Entry(f, textvariable=self.cookies_file).grid(row=r, column=1, sticky="ew")
        ttk.Button(f, text="Browse…", command=self.pick_cookies).grid(row=r, column=2, padx=(6, 0))
        r += 1

        ttk.Checkbutton(f, text="Ignore SSL certificate errors (insecure, last resort)",
                        variable=self.no_cert_check).grid(row=r, column=0, columnspan=3, sticky="w", pady=(10, 0))
        r += 1

        ttk.Button(f, text="Update yt-dlp", command=self.update_ytdlp).grid(row=r, column=0, sticky="w", pady=(14, 0))

    def build_image(self, f):

        f.columnconfigure(0, weight=1)
        f.rowconfigure(0, weight=1)

  
        try:
            bg = ttk.Style().lookup("TFrame", "background") or "white"
            self.root.winfo_rgb(bg)
        except tk.TclError:
            bg = "white"
        self.canvas = tk.Canvas(f, highlightthickness=0, bg=bg)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", lambda e: self.center_image())

        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(base, "img", "image.gif")

        self.frames, self.delays = [], []
        self.frame_index = 0
        self.canvas_item = None
        if os.path.exists(path):
            try:
                self.load_gif(path, bg)
            except Exception as e:  # noqa
                self.events.put(("log", f"Could not load gif: {e}"))
        if not Image and self.frames:
            self.events.put(("log", "Tip: pip install pillow for correct gif rendering."))

        if self.frames:
            self.canvas_item = self.canvas.create_image(0, 0, image=self.frames[0], anchor="center")
            self.center_image()
            if len(self.frames) > 1:
                self.root.after(self.delays[0], self.next_frame)
        else:
            self.canvas_item = self.canvas.create_text(0, 0, text="img/image.gif not found", anchor="center")
            self.center_image()

    def load_gif(self, path, bg):
        if Image:
            r, g, b = [c // 257 for c in self.root.winfo_rgb(bg)]
            with Image.open(path) as im:
                for frame in ImageSequence.Iterator(im):
                    rgba = frame.convert("RGBA")
                    canvas = Image.new("RGBA", rgba.size, (r, g, b, 255))
                    canvas.alpha_composite(rgba)  
                    self.frames.append(ImageTk.PhotoImage(canvas.convert("RGB")))
                    self.delays.append(max(20, frame.info.get("duration", GIF_DELAY_MS) or GIF_DELAY_MS))
        else:  # anywaaayyyyyyyyys anywaaaaaaays
            try:
                while True:
                    self.frames.append(tk.PhotoImage(file=path, format=f"gif -index {len(self.frames)}"))
                    self.delays.append(GIF_DELAY_MS)
            except tk.TclError:
                pass

    def center_image(self):
        if self.canvas_item:
            self.canvas.coords(self.canvas_item, self.canvas.winfo_width() // 2, self.canvas.winfo_height() // 2)

    def next_frame(self):
        self.frame_index = (self.frame_index + 1) % len(self.frames)
        self.canvas.itemconfigure(self.canvas_item, image=self.frames[self.frame_index])
        self.root.after(self.delays[self.frame_index], self.next_frame)

    def build_log(self, f):
        f.columnconfigure(0, weight=1)
        f.rowconfigure(0, weight=1)
        self.logbox = tk.Text(f, height=10, state="disabled", wrap="word")
        sb = ttk.Scrollbar(f, command=self.logbox.yview)
        self.logbox.configure(yscrollcommand=sb.set)
        self.logbox.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")

    # ---------------------------------------------------------------- helpers
    def on_format_change(self):
        mode, fmt = FORMAT_CHOICES[self.format_label.get()]
        self.mode.set(mode)
        self.container.set(fmt)

        
        self.quality_cb.configure(state="readonly" if mode == "video" else "disabled")

        
        if mode == "video":
            self.audio_bitrate.set("Best")
            self.audioq_cb.configure(values=AUDIO_QUALITIES, state="disabled")
        elif fmt in LOSSLESS:
            self.audioq_cb.configure(values=["Lossless"], state="disabled")
            self.audio_bitrate.set("Lossless")
        elif fmt == "best":
            self.audioq_cb.configure(values=["Original"], state="disabled")
            self.audio_bitrate.set("Original")
        else:
            if self.audio_bitrate.get() not in AUDIO_QUALITIES:
                self.audio_bitrate.set("Best")
            self.audioq_cb.configure(values=AUDIO_QUALITIES, state="readonly")

    def log(self, msg):
        self.logbox.configure(state="normal")
        self.logbox.insert("end", msg + "\n")
        self.logbox.see("end")
        self.logbox.configure(state="disabled")

    def paste(self):
        try:
            self.urls.insert("insert", self.root.clipboard_get().strip() + "\n")
        except tk.TclError:
            pass

    def pick_folder(self):
        d = filedialog.askdirectory(initialdir=self.folder.get())
        if d:
            self.folder.set(d)

    def pick_cookies(self):
        p = filedialog.askopenfilename(title="Select cookies.txt")
        if p:
            self.cookies_file.set(p)

    def load_list(self):
        p = filedialog.askopenfilename(title="Text file with URLs", filetypes=[("Text", "*.txt"), ("All files", "*")])
        if p:
            with open(p, encoding="utf-8", errors="ignore") as fh:
                self.urls.insert("end", fh.read().strip() + "\n")

    def open_dest(self):
        d = self.folder.get()
        if os.path.isdir(d):
            open_folder(d)
        else:
            messagebox.showinfo("Folder", "That folder does not exist yet.")

    def get_urls(self):
        return [u.strip() for u in self.urls.get("1.0", "end").splitlines() if u.strip()]

    # ------------------------------------------------------------ option build
    def build_opts(self):
        folder = self.folder.get().strip()
        os.makedirs(folder, exist_ok=True)

        o = {
            "outtmpl": os.path.join(folder, self.template.get().strip() or "%(title)s [%(id)s].%(ext)s"),
            "noplaylist": not self.playlist.get(),
            "progress_hooks": [self.hook],
            "logger": QuietLogger(self),
            "retries": int(self.retries.get() or 10),
            "ignoreerrors": False,
            "windowsfilenames": sys.platform == "win32",
            "noprogress": True,
            "no_color": True,  
            "nocheckcertificate": self.no_cert_check.get(),
        }

        pps = []
        h = self.quality.get()
        if self.mode.get() == "video":
            cont = self.container.get()
            cap = "" if h == "Best" else f"[height<={h}]"
            if cont in ("mp4", "mov"):
                o["format"] = (f"bv*{cap}[ext=mp4]+ba[ext=m4a]/bv*{cap}+ba/b{cap}")
            else:
                o["format"] = f"bv*{cap}+ba/b{cap}"
            if cont in NATIVE_VIDEO:
                o["merge_output_format"] = cont
            else:  #hey its alright my life has neverrr been a bed of roseeeeeeees this way's better 4 me idc to live the life i've choooseeen
                o["merge_output_format"] = "mkv"
                pps.append({"key": "FFmpegVideoConvertor", "preferedformat": cont})
        else:
            o["format"] = "bestaudio/best"
            fmt = self.container.get()
            if fmt in EXTRACT_AUDIO:
                q = self.audio_bitrate.get()
                if q == "Best" or not q.isdigit():
                    q = "0" if fmt == "mp3" else "320"  
                pps.append({
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": fmt,
                    "preferredquality": q,
                })
            else:  
                pps.append({"key": "FFmpegVideoConvertor", "preferedformat": fmt})

        if self.sponsorblock.get():
            pps.append({"key": "SponsorBlock", "categories": SPONSOR_CATEGORIES, "when": "after_filter"})
            pps.append({"key": "ModifyChapters", "remove_sponsor_segments": SPONSOR_CATEGORIES,
                        "remove_chapters_patterns": [], "remove_ranges": [], "sponsorblock_chapter_title": "",
                        "force_keyframes": False})

        if self.subs.get() and self.mode.get() == "video":
            langs = [x.strip() for x in self.sub_langs.get().split(",") if x.strip()] or ["en"]
            o["writesubtitles"] = True
            o["writeautomaticsub"] = self.auto_subs.get()
            o["subtitleslangs"] = langs
            if self.embed_subs.get():
                pps.append({"key": "FFmpegEmbedSubtitle"})

        if self.metadata.get():
            pps.append({"key": "FFmpegMetadata", "add_chapters": True, "add_metadata": True})
        if self.thumbnail.get():
            o["writethumbnail"] = True
            pps.append({"key": "EmbedThumbnail"})

        o["postprocessors"] = pps
        o["writedescription"] = self.write_desc.get()
        o["writeinfojson"] = self.write_info.get()

        if self.playlist.get() and self.playlist_items.get().strip():
            o["playlist_items"] = self.playlist_items.get().strip()

        if self.archive.get():
            o["download_archive"] = os.path.join(folder, "archive.txt")

        start, end = parse_time(self.start_time.get()), parse_time(self.end_time.get())
        if start is not None or end is not None:
            o["download_ranges"] = download_range_func(None, [(start or 0, end or float("inf"))])
            o["force_keyframes_at_cuts"] = True

        if self.rate_limit.get().strip():
            o["ratelimit"] = yt_dlp.utils.parse_bytes(self.rate_limit.get().strip())
        if self.proxy.get().strip():
            o["proxy"] = self.proxy.get().strip()
        if self.cookies_file.get().strip():
            o["cookiefile"] = self.cookies_file.get().strip()
        elif self.cookies_browser.get() != "None":
            o["cookiesfrombrowser"] = (self.cookies_browser.get(),)

        return o

    # ---------------------------------------------------------------- actions
    def fetch_info(self):
        urls = self.get_urls()
        if not urls:
            messagebox.showinfo("Get info", "Paste a URL first.")
            return
        if yt_dlp is None:
            return
        self.info_text.set("Fetching…")

        def work():
            try:
                with yt_dlp.YoutubeDL({"quiet": True, "noplaylist": not self.playlist.get(),
                                       "extract_flat": "in_playlist", "skip_download": True}) as ydl:
                    info = ydl.extract_info(urls[0], download=False)
                if info.get("_type") == "playlist":
                    text = f"Playlist: {info.get('title')}  ({len(info.get('entries') or [])} items)"
                else:
                    dur = info.get("duration") or 0
                    text = (f"{info.get('title')}\n{info.get('uploader', '')}  •  "
                            f"{int(dur // 60)}:{int(dur % 60):02d}  •  "
                            f"{info.get('view_count', 0):,} views")
                self.events.put(("info", text))
            except Exception as e:  # noqa
                self.events.put(("info", f"Could not fetch info: {e}"))

        threading.Thread(target=work, daemon=True).start()

    def start(self):
        if yt_dlp is None:
            messagebox.showerror("Missing dependency", "Install yt-dlp:  pip install -U yt-dlp")
            return
        urls = self.get_urls()
        if not urls:
            messagebox.showinfo("Download", "Paste at least one URL.")
            return
        try:
            opts = self.build_opts()
        except Exception as e:  # noqa
            messagebox.showerror("Invalid options", str(e))
            return

        self.cancel_flag.clear()
        self.dl_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.progress.set(0)
        self.worker = threading.Thread(target=self.run, args=(urls, opts), daemon=True)
        self.worker.start()

    def cancel(self):
        self.cancel_flag.set()
        self.status.set("Cancelling…")

    def run(self, urls, opts):
        ok = fail = 0
        for i, url in enumerate(urls, 1):
            if self.cancel_flag.is_set():
                break
            self.events.put(("status", f"Item {i}/{len(urls)}: starting…"))
            self.events.put(("log", f"--- {url}"))
            self.current = (i, len(urls))
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])
                ok += 1
            except DownloadCancelled:
                self.events.put(("log", "Cancelled."))
                break
            except Exception as e:  # noqa
                fail += 1
                self.events.put(("log", f"ERROR: {e}"))
        self.events.put(("done", (ok, fail)))

    def hook(self, d):
        if self.cancel_flag.is_set():
            raise DownloadCancelled()
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes", 0)
            pct = (done / total * 100) if total else 0
            speed = d.get("speed")
            eta = d.get("eta")
            i, n = getattr(self, "current", (1, 1))
            msg = f"Item {i}/{n}: {pct:.1f}%  {human_size(done)}"
            if total:
                msg += f" of {human_size(total)}"
            if speed:
                msg += f"  at {human_size(speed)}/s"
            if eta is not None:
                msg += f"  ETA {int(eta // 60)}:{int(eta % 60):02d}"
            self.events.put(("progress", (pct, msg)))
        elif d["status"] == "finished":
            self.events.put(("log", f"Downloaded: {os.path.basename(d.get('filename', ''))}"))
            self.events.put(("status", "Processing…"))

    def update_ytdlp(self):
        self.log("Updating yt-dlp…")

        def work():
            try:
                p = subprocess.run([sys.executable, "-m", "pip", "install", "-U", "yt-dlp"],
                                   capture_output=True, text=True)
                self.events.put(("log", (p.stdout + p.stderr).strip()))
                self.events.put(("status", "yt-dlp update finished. Restart the app."))
            except Exception as e:  # noqa
                self.events.put(("log", f"Update failed: {e}"))

        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------- UI updates
    def poll_events(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "log":
                    self.log(data)
                elif kind == "status":
                    self.status.set(data)
                elif kind == "info":
                    self.info_text.set(data)
                elif kind == "progress":
                    self.progress.set(data[0])
                    self.status.set(data[1])
                elif kind == "done":
                    ok, fail = data
                    self.dl_btn.configure(state="normal")
                    self.cancel_btn.configure(state="disabled")
                    if self.cancel_flag.is_set():
                        self.status.set("Cancelled")
                    else:
                        self.progress.set(100 if ok else 0)
                        self.status.set(f"Finished: {ok} succeeded, {fail} failed")
                        if fail:
                            messagebox.showwarning("Done", f"{ok} succeeded, {fail} failed.\nSee the Log tab.")
                        elif self.open_when_done.get():
                            self.open_dest()
        except queue.Empty:
            pass
        self.root.after(100, self.poll_events)


class QuietLogger:
   

    def __init__(self, app):
        self.app = app

    def debug(self, msg):
        if not msg.startswith("[debug]") and not msg.startswith("[download]"):
            self.app.events.put(("log", msg))

    def info(self, msg):
        pass

    def warning(self, msg):
        self.app.events.put(("log", f"WARNING: {msg}"))

    def error(self, msg):
        pass  


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
#dont care