import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import queue
from src.frontend.styles import *

class PlaylistUI:
    """
    Frutiger Aero / Vista inspired UI implementation.
    Features a pinned bottom player skin (Deep Blue), checkbox-based selection,
    and aero-styled management buttons.
    """
    
    def __init__(self, window_title, on_add_song_callback):
        self.root = tk.Tk()
        self.root.title(f"P2P Playlist - {window_title}")
        self.root.geometry("850x650")
        self.root.configure(bg=BG_MAIN)
        
        # Callbacks
        self.on_add_song = on_add_song_callback
        self.on_skip_next = None
        self.on_skip_prev = None
        self.on_play_pause = None
        self.on_seek = None
        self.on_shuffle = None
        self.on_repeat = None
        self.on_clear_queue = None
        self.on_remove_song = None
        self.on_volume_change = None
        
        self.msg_queue = queue.Queue()
        self.controls_visible = None # Force initial layout update
        self.debug_visible = False
        self.is_dragging_seek = False 
        
        # Internal map to store song IDs for Treeview items: {iid: song_id}
        self.tree_map = {} 
        
        self._setup_styles()
        self._setup_layout()
        self._start_queue_listener()

    def _setup_styles(self):
        """Configures ttk styles for a glossy/aero look."""
        style = ttk.Style()
        style.theme_use('clam') 
        
        # Treeview (Playlist)
        style.configure("Treeview", 
                        background=BG_MAIN, 
                        foreground=TEXT_MAIN, 
                        fieldbackground=BG_MAIN,
                        borderwidth=0,
                        font=FONT_NORMAL,
                        rowheight=28)
        
        style.configure("Treeview.Heading", 
                        background=BG_PANEL, 
                        foreground=ACCENT, 
                        font=("Segoe UI", 9, "bold"),
                        relief="raised") 
        
        style.map("Treeview", 
                  background=[('selected', '#333333')], 
                  foreground=[('selected', 'white')])
        
        # Slider
        style.configure("Horizontal.TScale", 
                        background=BG_PLAYER, 
                        troughcolor="#002244", 
                        sliderlength=20,
                        sliderthickness=15,
                        borderwidth=1,
                        relief="raised")
        
        style.map("Horizontal.TScale",
                  troughcolor=[('disabled', '#2b2b2b')],
                  sliderrelief=[('disabled', 'flat')],
                  background=[('disabled', BG_PLAYER)])

    def _setup_layout(self):
        # --- 1. Header (Top Bar) ---
        self.header = tk.Frame(self.root, bg=BG_HEADER, height=50, bd=1, relief="raised")
        self.header.pack(side="top", fill="x")
        
        tk.Label(self.header, text="P2P PLAYLIST", bg=BG_HEADER, fg=ACCENT, font=("Segoe UI", 14, "bold", "italic")).pack(side="left", padx=PAD_L)
        
        self.status_label = tk.Label(self.header, text="Connecting...", bg=BG_HEADER, fg=TEXT_SUB, font=FONT_SMALL)
        self.status_label.pack(side="left", padx=PAD_M)
        
        # Notification Label (Initially Hidden)
        self.notify_label = tk.Label(self.header, text="", bg=ACCENT_DANGER, fg="white", font=("Segoe UI", 9, "bold"), padx=10)
        
        # Updated CMD Button Style to match Add Track
        self.debug_btn = tk.Button(self.header, text="CMD 💻", bg=ACCENT, fg="#000000",
                                 font=("Segoe UI", 9, "bold"), relief="raised", bd=2, padx=15,
                                 activebackground=ACCENT_HOVER, activeforeground="#000000",
                                 command=self.toggle_debug)
        self.debug_btn.pack(side="right", padx=PAD_M, pady=PAD_M)
        
        add_btn = tk.Button(self.header, text="+ ADD TRACK", bg=ACCENT, fg="#000000",
                           font=("Segoe UI", 9, "bold"), relief="raised", bd=2, padx=15,
                           activebackground=ACCENT_HOVER, activeforeground="#000000",
                           command=self._add_song_dialog)
        add_btn.pack(side="right", padx=PAD_M, pady=PAD_M)

        # --- 2. Pinned Player Skin (Bottom) ---
        self.player_frame = tk.Frame(self.root, bg=BG_PLAYER, bd=0)
        self.player_frame.pack(side="bottom", fill="x")
        
        tk.Frame(self.player_frame, bg=ACCENT, height=2).pack(side="top", fill="x")
        
        self._setup_player_ui()

        # --- 3. Main Content Container ---
        self.middle_container = tk.Frame(self.root, bg=BG_MAIN)
        self.middle_container.pack(side="top", fill="both", expand=True)

        # Playlist Panel
        self.playlist_panel = tk.Frame(self.middle_container, bg=BG_MAIN)
        self.playlist_panel.pack(side="left", fill="both", expand=True, padx=PAD_M, pady=PAD_M)
        
        list_header = tk.Frame(self.playlist_panel, bg=BG_MAIN)
        list_header.pack(fill="x", pady=(0, 5))
        
        tk.Label(list_header, text="Current Queue", bg=BG_MAIN, fg=TEXT_MAIN, font=FONT_TITLE).pack(side="left")

        # Treeview with Checkbox Column
        columns = ("select", "title", "artist", "added_by")
        self.tree = ttk.Treeview(self.playlist_panel, columns=columns, show="headings", selectmode="browse")
        
        self.tree.heading("select", text="✔")
        self.tree.column("select", width=40, anchor="center")
        self.tree.heading("title", text="Title")
        self.tree.heading("artist", text="Artist")
        self.tree.heading("added_by", text="Added By")
        self.tree.column("title", width=300)
        self.tree.column("artist", width=150)
        self.tree.column("added_by", width=100)
        
        self.tree.pack(side="top", fill="both", expand=True)
        self.tree.bind("<Button-1>", self._on_tree_click)
        
        scrollbar = ttk.Scrollbar(self.tree, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        # --- 4. Aero Toolbar (Bottom of Playlist) ---
        # We'll create it but manage packing in set_controls_visible
        self.toolbar_frame = tk.Frame(self.playlist_panel, bg=BG_MAIN, height=50)
        
        self.btn_style = {"font": ("Segoe UI", 9, "bold"), "relief": "raised", "bd": 2, "padx": 15, "pady": 5, "activebackground": ACCENT_HOVER}
        
        self.remove_btn = tk.Button(self.toolbar_frame, text="Remove Selected", bg=BTN_DISABLED_BG, fg=TEXT_DISABLED,
                                  state="disabled", command=self._handle_remove_checked, **self.btn_style)
        self.remove_btn.pack(side="left", padx=(0, 10))

        self.btn_clear_list = tk.Button(self.toolbar_frame, text="Clear Playlist", bg=ACCENT, fg="#000000",
                                      state="disabled", command=lambda: self._trigger(self.on_clear_queue), **self.btn_style)
        self.btn_clear_list.pack(side="left")

        # --- Debug Panel ---
        self.debug_panel = tk.Frame(self.middle_container, bg=BG_TERM, width=300, bd=2, relief="sunken")
        
        term_header = tk.Frame(self.debug_panel, bg=BG_TERM)
        term_header.pack(fill="x", pady=2, padx=2)
        tk.Label(term_header, text="SYSTEM TERMINAL", bg=BG_TERM, fg=TEXT_TERM, font=("Consolas", 10, "bold")).pack(side="left")
        
        # Updated Copy Button Styles to match "Add Track"
        copy_opts = {
            "bg": ACCENT, 
            "fg": "#000000", 
            "relief": "raised", 
            "bd": 1,
            "font": ("Segoe UI", 8, "bold"), 
            "padx": 10, 
            "pady": 0,
            "activebackground": ACCENT_HOVER
        }
        tk.Button(term_header, text="Copy All", command=self._copy_all_logs, **copy_opts).pack(side="right", padx=2)
        tk.Button(term_header, text="Copy Sel", command=self._copy_selection_logs, **copy_opts).pack(side="right", padx=2)

        log_frame = tk.Frame(self.debug_panel, bg=BG_TERM)
        log_frame.pack(fill="both", expand=True, padx=2, pady=2)

        term_scrollbar = ttk.Scrollbar(log_frame, orient="vertical")
        self.log_box = tk.Text(log_frame, bg=BG_TERM, fg=TEXT_TERM, font=FONT_MONO, borderwidth=0, state="disabled", 
                               yscrollcommand=term_scrollbar.set, selectbackground="#333333", selectforeground="white")
        term_scrollbar.config(command=self.log_box.yview)
        
        term_scrollbar.pack(side="right", fill="y")
        self.log_box.pack(side="left", fill="both", expand=True)

    def _setup_player_ui(self):
        # A. Seek Bar Row
        self.seek_frame = tk.Frame(self.player_frame, bg=BG_PLAYER, pady=5)
        self.seek_frame.pack(fill="x", padx=PAD_L)
        
        self.lbl_current_time = tk.Label(self.seek_frame, text="0:00", bg=BG_PLAYER, fg=ACCENT, font=FONT_SMALL)
        self.lbl_current_time.pack(side="left")
        
        self.seek_slider = ttk.Scale(self.seek_frame, from_=0, to=100, orient="horizontal")
        self.seek_slider.bind("<ButtonPress-1>", self._on_seek_start)
        self.seek_slider.bind("<ButtonRelease-1>", self._on_seek_end)
        self.seek_slider.pack(side="left", fill="x", expand=True, padx=PAD_M)
        
        self.lbl_total_time = tk.Label(self.seek_frame, text="0:00", bg=BG_PLAYER, fg=TEXT_SUB, font=FONT_SMALL)
        self.lbl_total_time.pack(side="right")

        # B. Controls Row
        # Store as self.controls_frame to allow manipulation
        self.controls_frame = tk.Frame(self.player_frame, bg=BG_PLAYER, pady=10)
        self.controls_frame.pack(fill="x", padx=PAD_L, pady=(0, 10))

        # B1. Song Info
        self.info_sub = tk.Frame(self.controls_frame, bg=BG_PLAYER, width=220)
        self.info_sub.pack(side="left", fill="y")
        self.info_sub.pack_propagate(False)
        self.now_playing_title = tk.Label(self.info_sub, text="Waiting for Host...", bg=BG_PLAYER, fg=ACCENT, font=("Segoe UI", 11, "bold"), anchor="w")
        self.now_playing_title.pack(fill="x")
        self.now_playing_artist = tk.Label(self.info_sub, text="--", bg=BG_PLAYER, fg=TEXT_MAIN, font=FONT_SMALL, anchor="w")
        self.now_playing_artist.pack(fill="x")

        # B2. Playback Controls
        self.host_controls = tk.Frame(self.controls_frame, bg=BG_PLAYER)
        self.host_controls.pack(side="left", expand=True)
        
        btn_opts = {'bg': BG_PLAYER, 'fg': ACCENT, 'relief': 'flat', 'activebackground': BG_PLAYER, 'bd': 0, 'font': ("Segoe UI Symbol", 14)}
        
        self.btn_shuffle = tk.Button(self.host_controls, text="🔀", **btn_opts, command=lambda: self._trigger(self.on_shuffle))
        self.btn_shuffle.pack(side="left", padx=8)
        self.btn_prev = tk.Button(self.host_controls, text="⏮", **btn_opts, command=lambda: self._trigger(self.on_skip_prev))
        self.btn_prev.pack(side="left", padx=8)
        self.btn_play = tk.Button(self.host_controls, text="▶", bg=ACCENT, fg="#000000", font=("Segoe UI Symbol", 16), 
                                relief="raised", bd=3, width=4, activebackground=ACCENT_HOVER,
                                command=lambda: self._trigger(self.on_play_pause))
        self.btn_play.pack(side="left", padx=15)
        self.btn_next = tk.Button(self.host_controls, text="⏭", **btn_opts, command=lambda: self._trigger(self.on_skip_next))
        self.btn_next.pack(side="left", padx=8)
        self.btn_repeat = tk.Button(self.host_controls, text="🔁", **btn_opts, command=lambda: self._trigger(self.on_repeat))
        self.btn_repeat.pack(side="left", padx=8)

        # B3. Volume
        self.vol_frame = tk.Frame(self.controls_frame, bg=BG_PLAYER)
        self.vol_frame.pack(side="right")
        tk.Label(self.vol_frame, text="🔊", bg=BG_PLAYER, fg=ACCENT).pack(side="left", padx=2)
        self.vol_slider = ttk.Scale(self.vol_frame, from_=0, to=100, orient="horizontal", command=self._handle_volume)
        self.vol_slider.set(70)
        self.vol_slider.pack(side="left", padx=5)

    # --- Notification System ---
    
    def show_notification(self, message, is_error=True):
        """Displays a temporary banner in the header for errors/status."""
        bg_color = ACCENT_DANGER if is_error else ACCENT
        self.notify_label.config(text=message, bg=bg_color)
        # Pack after status label
        self.notify_label.pack(side="left", padx=PAD_M, after=self.status_label)
        
        # Auto-hide after 3 seconds
        self.root.after(3000, self.notify_label.pack_forget)

    # --- Interaction Logic ---
    
    def _on_seek_start(self, event):
        self.is_dragging_seek = True
        
    def _on_seek_end(self, event):
        self.is_dragging_seek = False
        if self.on_seek and self.controls_visible:
            val = self.seek_slider.get()
            self.on_seek(float(val))

    def _on_tree_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            col = self.tree.identify_column(event.x)
            if col == "#1":
                item_id = self.tree.identify_row(event.y)
                if item_id:
                    current_values = self.tree.item(item_id, "values")
                    current_status = current_values[0]
                    new_status = "☑" if current_status == "☐" else "☐"
                    new_values = (new_status,) + current_values[1:]
                    self.tree.item(item_id, values=new_values)
                    self._check_selection_state()

    def _check_selection_state(self):
        if not self.controls_visible: return
        has_checked = False
        for child in self.tree.get_children():
            if self.tree.item(child, "values")[0] == "☑":
                has_checked = True
                break
        
        if has_checked:
            self.remove_btn.config(state="normal", bg=ACCENT, fg="#000000")
        else:
            self.remove_btn.config(state="disabled", bg=BTN_DISABLED_BG, fg=TEXT_DISABLED)

    def _handle_remove_checked(self):
        if not self.on_remove_song: return
        items_to_remove = []
        for child in self.tree.get_children():
            val = self.tree.item(child, "values")
            if val[0] == "☑":
                song_id = self.tree_map.get(child)
                if song_id:
                     items_to_remove.append(song_id)
        
        # Call remove for each ID (Backend expects ID)
        for song_id in items_to_remove:
            self.on_remove_song(song_id)
        
        # Manually reset UI state to avoid visual lag before sync
        self.remove_btn.config(state="disabled", bg=BTN_DISABLED_BG, fg=TEXT_DISABLED)

    def set_controls_visible(self, is_host, host_id=None, host_name=None):
        # 1. Update Header Info
        current_title = self.root.title()
        try:
             # Title is "P2P Playlist - Name [ID]" -> Extract "Name [ID]"
             my_identity = current_title.split(' - ')[1]
        except:
             my_identity = f"Unknown [{self.node_id}]"

        if is_host:
            # Format: HOST mode | Peer: MyName [MyID] (You)
            # Since I am host, Host info is same as Peer info
            role_text = f"[ HOST mode ] |  {my_identity} (You)"
            fg_color = TEXT_HOST
        elif host_id:
            # Format: LISTENER mode | Peer: MyName [MyID] | Host: HostName [HostID]
            h_name = host_name if host_name else "Unknown"
            role_text = f"[ LISTENER mode ] |  {my_identity} (You) |  HOST: {h_name} [{host_id}]"
            fg_color = TEXT_HOST
        else:
            role_text = f"Finding Host...  |  {my_identity}"
            fg_color = ACCENT_WARNING
            
        font = ("Segoe UI", 9, "bold") 
        self.status_label.config(text=role_text, fg=fg_color, font=font)

        # 2. Check for Role Change (Prevents Glitching)
        if self.controls_visible == is_host:
            return 
        
        self.controls_visible = is_host
        
        # 3. Update Layout
        if is_host:
            # --- HOST MODE ---
            # Remove all from packing to re-order cleanly
            self.info_sub.pack_forget()
            self.host_controls.pack_forget()
            self.vol_frame.pack_forget()
            self.toolbar_frame.pack_forget() # Temporarily remove toolbar

            # 1. Info (Left)
            self.info_sub.config(width=220)
            self.info_sub.pack_propagate(False)
            self.info_sub.pack(side="left", fill="y")
            
            self.now_playing_title.config(anchor="w", justify="left", font=("Segoe UI", 11, "bold"))
            self.now_playing_artist.config(anchor="w", justify="left")
            self.now_playing_title.pack(side="top", fill="x")
            self.now_playing_artist.pack(side="top", fill="x")

            # 2. Controls (Left, Expand)
            self.host_controls.pack(side="left", expand=True)
            
            # 3. Volume (Right)
            self.vol_frame.pack(side="right")

            # 4. Restore Toolbar buttons
            self.toolbar_frame.pack(fill="x", pady=10) 
            self.btn_clear_list.pack(side="left")
            self.remove_btn.pack(side="left", padx=(0, 10))

            # Restore Sliders
            if not self.seek_slider.winfo_ismapped():
                self.seek_slider.pack(side="left", fill="x", expand=True, padx=PAD_M)
            
            # Reset font size for small seekbar labels
            self.lbl_current_time.config(font=FONT_SMALL)
            self.lbl_total_time.config(font=FONT_SMALL)

            # Enable Interactions
            for widget in self.host_controls.winfo_children():
                widget.configure(state="normal")
            self.btn_clear_list.configure(state="normal")
            self._check_selection_state() 
            self.seek_slider.configure(state="normal")
            self.vol_slider.configure(state="normal")

        else:
            # --- LISTENER MODE ---
            # Hide Toolbar completely
            self.btn_clear_list.pack_forget()
            self.remove_btn.pack_forget()
            self.toolbar_frame.pack_forget() 
            
            # Hide Controls & Sliders
            self.host_controls.pack_forget()
            self.seek_slider.pack_forget()
            self.vol_frame.pack_forget()
            
            # Center the Song Info beautifully
            self.info_sub.pack_forget() 
            self.info_sub.config(width=0) # Unset fixed width
            self.info_sub.pack(side="top", fill="both", expand=True) 
            self.info_sub.pack_propagate(True) 
            
            self.now_playing_title.config(anchor="center", justify="center", font=("Segoe UI", 14, "bold"))
            self.now_playing_artist.config(anchor="center", justify="center")
            self.now_playing_title.pack(side="top", fill="both", expand=True)
            self.now_playing_artist.pack(side="top", fill="both", expand=True)
            
            # Bigger Timer
            self.lbl_current_time.config(font=("Segoe UI", 12, "bold"))
            self.lbl_total_time.config(font=("Segoe UI", 12, "bold"))

    # --- UI Update Methods ---
    
    def update_play_pause_icon(self, is_playing):
        icon = "⏸" if is_playing else "▶"
        self.btn_play.config(text=icon)

    def update_progress(self, current_seconds, total_seconds):
        def fmt_time(s):
            m, s = divmod(int(s), 60)
            return f"{m}:{s:02d}"

        # FIX: Explicitly check for 0 total seconds or extremely small duration
        if total_seconds <= 0.1:
             time_str_cur = "0:00"
             time_str_tot = "0:00"
             pct = 0
        else:
             time_str_cur = fmt_time(current_seconds)
             time_str_tot = fmt_time(total_seconds)
             pct = (current_seconds / total_seconds) * 100

        self.lbl_current_time.config(text=time_str_cur)
        self.lbl_total_time.config(text=time_str_tot)
        
        if not self.is_dragging_seek and self.controls_visible:
            self.seek_slider.set(pct)

    def update_toggles(self, repeat_mode, is_shuffle):
        if repeat_mode == 0:
            self.btn_repeat.config(bg=BG_PLAYER, relief="flat", text="🔁")
        elif repeat_mode == 1:
            self.btn_repeat.config(bg=BTN_ACTIVE_BG, relief="sunken", text="🔁")
        else:
            self.btn_repeat.config(bg=BTN_ACTIVE_BG, relief="sunken", text="🔂") 

        if is_shuffle:
            self.btn_shuffle.config(bg=BTN_ACTIVE_BG, relief="sunken")
        else:
            self.btn_shuffle.config(bg=BG_PLAYER, relief="flat")

    def update_now_playing(self, title, artist="Unknown"):
        self.now_playing_title.config(text=title if title else "Nothing Playing")
        self.now_playing_artist.config(text=artist)

    def update_playlist(self, songs, current_song_id=None):
        # 1. Capture Checkbox State
        current_items = self.tree.get_children()
        checked_ids = set()
        
        for item_id in current_items:
            vals = self.tree.item(item_id, "values")
            if vals and vals[0] == "☑":
                 sid = self.tree_map.get(item_id)
                 if sid: checked_ids.add(sid)
        
        # 2. Clear
        self.tree.delete(*self.tree.get_children())
        self.tree_map.clear()

        # 3. Rebuild
        for song in songs:
            check_mark = "☑" if song.id in checked_ids else "☐"
            tags = ("playing",) if current_song_id == song.id else ()
            
            iid = self.tree.insert("", "end", values=(check_mark, song.title, song.artist, song.added_by), tags=tags)
            self.tree_map[iid] = song.id # Store ID map
            
        self.tree.tag_configure("playing", foreground=ACCENT, font=("Segoe UI", 10, "bold"))
        self._check_selection_state()

    def _trigger(self, callback):
        if callback and self.controls_visible:
            callback()

    def _handle_volume(self, value):
        if self.on_volume_change:
            self.on_volume_change(float(value) / 100.0)

    def _add_song_dialog(self):
        file_path = filedialog.askopenfilename(filetypes=[("Audio Files", "*.mp3 *.wav *.ogg")])
        if file_path:
            self.on_add_song(file_path)

    def log_message(self, message):
        self.msg_queue.put(message)

    def _copy_all_logs(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.log_box.get("1.0", "end-1c"))
        
    def _copy_selection_logs(self):
        try:
            sel = self.log_box.get("sel.first", "sel.last")
            if sel:
                self.root.clipboard_clear()
                self.root.clipboard_append(sel)
        except tk.TclError:
            pass 

    def toggle_debug(self):
        if self.debug_visible:
            self.debug_panel.pack_forget()
            self.root.geometry("850x650")
            # FIX: Ensure button retains accent style when reverting
            self.debug_btn.config(relief="raised", bg=ACCENT, fg="#000000")
        else:
            self.debug_panel.pack(side="right", fill="both", padx=(0, 0), pady=0)
            self.root.geometry("1150x650") 
            # FIX: Active/Pressed state visual feedback
            self.debug_btn.config(relief="sunken", bg=ACCENT_HOVER, fg="#000000")
            self.log_box.see("end")
        self.debug_visible = not self.debug_visible

    def _start_queue_listener(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                # Check scroll BEFORE inserting
                should_scroll = self.log_box.yview()[1] == 1.0
                
                self.log_box.config(state="normal")
                self.log_box.insert("end", f"{msg}\n")
                
                if should_scroll:
                    self.log_box.see("end")
                self.log_box.config(state="disabled")
        except queue.Empty:
            pass
        self.root.after(100, self._start_queue_listener)

    def run(self):
        self.root.mainloop()