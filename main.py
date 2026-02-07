"""
MAIN ENTRY POINT
----------------
Orchestrates the entire application. It initializes the UI, Network,
State Manager, and Election systems. It runs a maintenance loop on a 
background thread to handle heartbeats, UI updates, and playback logic.

UPDATES:
- Fixed Graphical Login: Now uses the primary window context to ensure visibility.
- Patched compatibility with older backend nodes.
- Removed unused battery metrics.
- Fixed Listener Timer: Added PatchedNetworkNode and dead reckoning logic.
"""

import sys
import uuid
import time
import threading
import socket
import random
import pygame
import os
import hashlib
import tkinter as tk
from tkinter import messagebox

from src.backend.discovery import DiscoveryManager
from src.backend.network_node import NetworkNode
from src.backend.state_manager import StateManager
from src.backend.bully_election import ElectionManager
from src.backend.audio_engine import AudioEngine
from src.utils.config import TCP_PORT, HEARTBEAT_INTERVAL
from src.frontend.app_ui import PlaylistUI
from src.utils.models import Song
from src.utils import config

# --- PATCHED NETWORK CLASS ---
class PatchedNetworkNode(NetworkNode):
    """
    Extends NetworkNode to handle message payloads that the original 
    backend implementation ignores (specifically duration and play status).
    """
    def _handle_logic(self, msg):
        # Allow base class to handle standard logic (pos, queue, etc.)
        super()._handle_logic(msg)
        
        if msg.msg_type == 'PLAYBACK_SYNC':
            # Patch: Extract duration and play state which base class ignores
            dur = msg.payload.get('dur')
            if dur is not None:
                self.state.current_duration = dur
            
            # Sync playing state if provided
            if 'is_playing' in msg.payload:
                self.state.is_playing = msg.payload['is_playing']

class CollaborativeNode:
    """
    Central controller class that binds the backend logic (Network, Election, Audio)
    to the frontend UI.
    """
    
    def __init__(self, display_name=None, password=None):
        if not display_name or not password:
            print("ERROR: Name and Password are required.")
            sys.exit(1)

        # Generate a deterministic Node ID based on the user's credentials
        seed = f"{display_name}:{password}"
        full_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, seed)
        self.node_id = str(full_uuid)[:8]
        self.display_name = display_name

        self.tcp_port = self._find_available_port(TCP_PORT)
        
        # Initialize UI with masked ID
        self.ui = PlaylistUI(f"{self.display_name} [{self.node_id} ...]", self.on_add_song_request)
        
        # Initialize State Management
        self.state = StateManager(self.node_id, self.ui_log)
        
        # --- COMPATIBILITY PATCH START ---
        # Explicitly initialize state variables expected by the newer main.py
        # because the older StateManager doesn't have them in __init__
        self.state.current_duration = 0 
        self.state.current_song = None
        self.state.current_song_pos = 0
        self.state.is_playing = False
        self.state.shuffle_active = False
        self.state.repeat_mode = 0
        # --- COMPATIBILITY PATCH END ---
        
        self.history = [] 
        
        # Initialize Networking
        # Use PatchedNetworkNode to ensure duration/status syncs are processed
        self.network = PatchedNetworkNode(self.node_id, self.state, self.ui_log)
        self.network.port = self.tcp_port
        
        # Initialize Election System (Bully Algorithm)
        self.election = ElectionManager(
            self.node_id, 
            self.state, 
            self.network, 
            self.ui_log
        )
        self.network.election = self.election 
        
        # Initialize UDP Discovery
        self.discovery = DiscoveryManager(self.node_id, self.tcp_port, self.ui_log)
        
        # Initialize Audio
        self.audio = AudioEngine(self.ui_log)
        self.network.audio = self.audio
        
        # Local Playback Flags
        self.is_shuffle_active = False 
        self.last_played_id = None
        self.local_is_paused = False
        self.running = True
        
        # Map UI buttons to Class Methods
        self.ui.on_skip_next = self.on_skip_next
        self.ui.on_skip_prev = self.on_skip_prev
        self.ui.on_play_pause = self.on_play_pause
        self.ui.on_seek = self.on_seek
        self.ui.on_shuffle = self.on_shuffle
        self.ui.on_repeat = self.on_repeat
        self.ui.on_clear_queue = self.on_clear_queue
        self.ui.on_remove_song = self.on_remove_song
        self.ui.on_volume_change = self.on_volume_change

    def _find_available_port(self, start_port):
        """Scans for an open TCP port starting from the config default."""
        p = start_port
        while p < start_port + 100:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('', p))
                    return p
            except: 
                p += 1
        return start_port

    def ui_log(self, message):
        """Thread-safe logging to both console and UI terminal."""
        formatted_msg = f"[{time.strftime('%H:%M:%S')}] {message}"
        print(formatted_msg) 
        if hasattr(self, 'ui'): self.ui.log_message(formatted_msg)

    def on_add_song_request(self, file_path):
        """Handles user action to add a file to the playlist."""
        title = os.path.basename(file_path)
        new_song = Song(title=title, added_by=self.display_name, file_path=file_path)
        
        self.state.add_song(new_song)
        self._broadcast('QUEUE_SYNC', {'song': new_song})

    def on_skip_next(self):
        """Logic for skipping to the next track. Only runs if this node is Host."""
        if not self.election.is_host: return
        self.ui_log("CMD: Skip Next")
        self.audio.stop()
        self.local_is_paused = False

        if len(self.state.playlist) > 0:
            # Handle repeat all mode
            if self.state.repeat_mode == 1 and self.state.current_song:
                self.state.playlist.append(self.state.current_song)
            
            target_song = self.state.playlist.pop(0)
            if self.state.current_song:
                self.history.append(self.state.current_song)
                
            self.state.current_song = target_song
            self.state.current_song_pos = 0
            self.last_played_id = None 
            self._play_song_logic(target_song)
        else:
            self._handle_queue_end()

    def on_skip_prev(self):
        """Logic for going to previous track or restarting current."""
        if not self.election.is_host: return
        self.ui_log("CMD: Skip Previous")
        
        if not self.state.current_song: return

        resolved_path = self._resolve_path(self.state.current_song.file_path)

        # Restart song if played > 5 seconds
        if self.state.current_song_pos > 5.0:
            self.audio.seek(0, resolved_path)
            self.state.current_song_pos = 0
            self._broadcast('PLAYBACK_SYNC', {'pos': 0, 'dur': getattr(self.state, 'current_duration', 0)})
            return
            
        if self.history:
            prev_song = self.history.pop()
            if self.state.current_song:
                self.state.playlist.insert(0, self.state.current_song)
            self.state.current_song = prev_song
            self.state.current_song_pos = 0
            self.last_played_id = None 
            self.local_is_paused = False
            self._play_song_logic(prev_song)
        else:
             self.audio.seek(0, resolved_path)
             self.state.current_song_pos = 0
             self._broadcast('PLAYBACK_SYNC', {'pos': 0, 'dur': getattr(self.state, 'current_duration', 0)})

    def on_play_pause(self):
        """Toggles playback state and notifies peers."""
        if not self.election.is_host: return
        if not self.state.current_song: return
        
        is_paused = self.audio.toggle_pause()
        self.local_is_paused = is_paused 
        self.state.is_playing = not is_paused
        
        action = 'pause' if is_paused else 'resume'
        self.ui_log(f"CMD: {action.upper()}")
        
        status_msg = {
            'is_playing': self.state.is_playing,
            'shuffle': self.state.shuffle_active,
            'repeat_mode': self.state.repeat_mode
        }
        self._broadcast('PLAYBACK_STATUS', status_msg)
        self.ui.update_play_pause_icon(self.state.is_playing)

    def on_seek(self, value):
        """Handles seek bar changes."""
        if not self.election.is_host: return
        
        dur = getattr(self.state, 'current_duration', 0)
        if dur > 0:
            seek_sec = (float(value) / 100.0) * dur
            resolved_path = self._resolve_path(self.state.current_song.file_path)
            
            self.audio.seek(seek_sec, resolved_path)
            self.state.current_song_pos = seek_sec
            
            # Maintain pause state if applicable
            if self.local_is_paused:
                self.audio.toggle_pause() 
                self.local_is_paused = True
            
            self._broadcast('PLAYBACK_SYNC', {'pos': seek_sec, 'dur': dur})
            
    def on_volume_change(self, val):
        self.audio.set_volume(val)

    def on_shuffle(self):
        if not self.election.is_host: return
        self.is_shuffle_active = not self.is_shuffle_active
        self.state.shuffle_active = self.is_shuffle_active
        self.ui_log(f"CMD: Shuffle {'ON' if self.is_shuffle_active else 'OFF'}")
        
        if self.is_shuffle_active:
            random.shuffle(self.state.playlist)
            self._broadcast_full_state()
            
        self.ui.update_toggles(self.state.repeat_mode, self.is_shuffle_active)

    def on_repeat(self):
        if not self.election.is_host: return
        self.state.repeat_mode = (self.state.repeat_mode + 1) % 3
        modes = ["Off", "Repeat All", "Repeat One"]
        self.ui_log(f"CMD: Repeat Mode set to {modes[self.state.repeat_mode]}")
        self.ui.update_toggles(self.state.repeat_mode, self.is_shuffle_active)
        
        status_msg = {
            'is_playing': self.state.is_playing,
            'shuffle': self.state.shuffle_active,
            'repeat_mode': self.state.repeat_mode
        }
        self._broadcast('PLAYBACK_STATUS', status_msg)

    def on_clear_queue(self):
        if not self.election.is_host: return
        self.ui_log("CMD: Clear Queue")
        self.state.playlist.clear()
        self._broadcast('QUEUE_CLEARED', {})

    def on_remove_song(self, song_id):
        if not self.election.is_host: return
        self.state.playlist = [s for s in self.state.playlist if s.id != song_id]
        self.ui_log(f"Removed ID: {song_id}")
        self._broadcast('REMOVE_SONG', {'song_id': song_id})

    def _broadcast(self, msg_type, payload):
        """Helper to send a message to all connected TCP peers."""
        for pid in list(self.network.connections.keys()):
            self.network.send_to_peer(pid, msg_type, payload=payload)

    def _broadcast_full_state(self):
        """Sends the entire playlist and status state to all peers."""
        self._broadcast('FULL_STATE_SYNC', {
            'playlist': self.state.playlist, 
            'current_song': self.state.current_song,
            'is_playing': self.state.is_playing,
            'shuffle': self.state.shuffle_active,
            'repeat_mode': self.state.repeat_mode
        })

    def _get_duration(self, file_path):
        try:
            return pygame.mixer.Sound(file_path).get_length()
        except:
            return 180.0 

    def _resolve_path(self, file_path):
        """
        Robust path resolution handling:
        1. Cross-platform separators (Windows \ vs Unix /)
        2. Relative paths (music/, assets/, songs/)
        3. Case-insensitivity (Song.mp3 vs song.mp3) to support cross-OS sync.
        """
        if not file_path: return ""
        # 1. Exact match (Absolute path or relative to CWD)
        if os.path.exists(file_path): 
            return file_path
            
        # 2. Extract clean filename
        # Handles mixed separators from different OSs
        normalized_name = file_path.replace('\\', '/').split('/')[-1]
        
        # 3. Define directories to search
        search_dir = './src/assets/music'
        
        # A. Check exact match in directory
        self.ui_log(f"normalized name: {normalized_name} in directory {search_dir}")
        candidate = os.path.join(search_dir, normalized_name)
        self.ui_log(f"candidate path: {candidate}")
        if os.path.exists(candidate):
            return os.path.abspath(candidate)
            
        return file_path

    def _play_song_logic(self, song, start_offset=0):
        resolved_path = self._resolve_path(song.file_path)
        
        if not os.path.exists(resolved_path):
            self.ui_log(f"Error: File missing locally: {resolved_path}")
            self.ui.show_notification(f"Missing File: {song.title}", is_error=True)
            
            # If host misses file, try next one
            if self.election.is_host:
                self.ui_log("Host missing file. Skipping to next...")
                self.last_played_id = song.id 
                if len(self.state.playlist) > 0:
                    next_song = self.state.playlist.pop(0)
                    self.state.current_song = next_song
                    self.state.current_song_pos = 0
                    self._play_song_logic(next_song)
                else:
                    self._handle_queue_end()
                return
            
        if self.audio.play_song(resolved_path, start_time=start_offset):
            self.local_is_paused = False 
            self.last_played_id = song.id
            self.state.current_duration = self._get_duration(resolved_path)
            self.state.is_playing = True
            
            self._broadcast('NOW_PLAYING', {'song': song})
            self._broadcast('PLAYBACK_SYNC', {'pos': start_offset, 'dur': self.state.current_duration})
            
            self._broadcast_full_state()
            self.ui.update_play_pause_icon(True)

    def _handle_queue_end(self):
        """Resets state when playlist finishes."""
        self.ui_log("Queue ended.")
        self.state.current_song = None
        self.state.current_duration = 0 
        self.state.current_song_pos = 0 
        
        self.state.is_playing = False
        self.local_is_paused = False
        self.ui.update_play_pause_icon(False)
        
        self._broadcast('NOW_PLAYING', {'song': None})
        self._broadcast('PLAYBACK_SYNC', {'pos': 0, 'dur': 0})
        
        status_msg = {
            'is_playing': False,
            'shuffle': self.state.shuffle_active,
            'repeat_mode': self.state.repeat_mode
        }
        self._broadcast('PLAYBACK_STATUS', status_msg)
        self.last_played_id = None

    def _refresh_ui(self):
        """Periodic UI update called from maintenance loop."""
        if not hasattr(self, 'ui'): return
        is_host = self.election.is_host
        leader = self.state.get_host()
        
        # PATCH: Use new safety method because older backend doesn't sync names
        host_name = self.state.get_peer_name(leader) if leader else "Unknown"
            
        self.ui.set_controls_visible(is_host, host_id=leader, host_name=host_name)
        cp = self.state.current_song
        
        if cp:
            resolved = self._resolve_path(cp.file_path)
            if not os.path.exists(resolved):
                self.ui.update_now_playing(f"[MISSING] {cp.title}", cp.artist)
            else:
                self.ui.update_now_playing(cp.title, cp.artist)
        else:
            self.ui.update_now_playing(None, "Unknown")
            
        self.ui.update_playlist(self.state.playlist, current_song_id=cp.id if cp else None)
        self.ui.update_progress(self.state.current_song_pos, getattr(self.state, 'current_duration', 0))
        self.ui.update_toggles(self.state.repeat_mode, self.is_shuffle_active)

    def _maintenance_loop(self):
        """Background thread for keeping state, UI, and Network in sync."""
        time.sleep(2) 
        while self.running:
            try:
                self.state.update_uptime(int(time.time() - self.election.init_time))
                self._refresh_ui()
                
                if self.election.is_host:
                    # Host Logic: Send Heartbeats and Manage Audio Queue
                    for pid in list(self.network.connections.keys()):
                        self.network.send_to_peer(pid, 'HEARTBEAT')
                        self.election.update_heartbeat()

                    if self.audio.is_busy():
                        # Update playback position while playing
                        current_pos = self.audio.get_current_pos()
                        self.state.current_song_pos = current_pos
                        # Piggyback is_playing state for listeners
                        payload = {
                            'pos': current_pos, 
                            'dur': getattr(self.state, 'current_duration', 0),
                            'is_playing': self.state.is_playing
                        }
                        self._broadcast('PLAYBACK_SYNC', payload)
                    elif self.local_is_paused:
                        # If paused, broadcast last known position
                        payload = {
                            'pos': self.state.current_song_pos, 
                            'dur': getattr(self.state, 'current_duration', 0),
                            'is_playing': self.state.is_playing
                        }
                        self._broadcast('PLAYBACK_SYNC', payload)
                    else:
                        # Song finished, select next
                        self._process_auto_next_song()
                else:
                    # Listener Logic: Dead reckoning for smooth UI
                    # If state says playing, increment local timer by the heartbeat interval
                    if self.state.is_playing and self.state.current_duration > 0:
                        self.state.current_song_pos += HEARTBEAT_INTERVAL
                        # Clamp to duration
                        if self.state.current_song_pos > self.state.current_duration:
                            self.state.current_song_pos = self.state.current_duration
                    
                self.election.check_for_host_failure()
                time.sleep(HEARTBEAT_INTERVAL)
            except Exception as e:
                print(f"Error in maintenance loop: {e}")

    def _process_auto_next_song(self):
        """Determines the next song when audio finishes naturally."""
        target_song = None
        start_offset = 0
        
        # Case 1: Current song needs to resume/seek
        if self.state.current_song and self.state.current_song.id != self.last_played_id:
            target_song = self.state.current_song
            start_offset = self.state.current_song_pos
        # Case 2: Repeat One
        elif self.state.repeat_mode == 2 and self.state.current_song:
            target_song = self.state.current_song
        # Case 3: Play next in queue
        elif len(self.state.playlist) > 0:
            if self.state.repeat_mode == 1 and self.state.current_song:
                self.state.playlist.append(self.state.current_song)
            target_song = self.state.playlist.pop(0)
            if self.state.current_song and self.state.current_song.id != target_song.id:
                self.history.append(self.state.current_song)
            self.state.current_song = target_song
            self.state.current_song_pos = 0
        # Case 4: Queue empty
        elif self.state.current_song is not None:
            self._handle_queue_end()

        if target_song:
            self._play_song_logic(target_song, start_offset)

    def start(self):
        self.network.start_server()
        self.discovery.start_listener(self.on_peer_discovered)
        self.discovery.broadcast_presence()
        
        threading.Thread(target=self._maintenance_loop, daemon=True).start()
        self.ui_log(f"Node started. ID: {self.node_id}")
        
        # Delay election to allow discovery
        def delayed_election():
            time.sleep(3.0) 
            self.ui_log(f"start: ELECTION (Score-Based)")
            self.election.start_election()
        threading.Thread(target=delayed_election, daemon=True).start()
        
        self.ui.run()

    def on_peer_discovered(self, pid, ip, port):
        if str(pid) != str(self.node_id):
            self.network.connect_to_peer(pid, ip, port)

if __name__ == "__main__":
    name = None
    pwd = None
    
    # Check command line args first (Backward compatibility)
    if len(sys.argv) > 2:
        name = sys.argv[1]
        pwd = sys.argv[2]
    else:
        # Launch Graphical Input Dialog using ROOT window
        # (Avoids 'withdraw' + 'toplevel' issues on some systems)
        login_root = tk.Tk()
        login_root.title("P2P Login")
        login_root.geometry("350x250")
        
        # Center Dialog
        screen_width = login_root.winfo_screenwidth()
        screen_height = login_root.winfo_screenheight()
        x = (screen_width - 350) // 2
        y = (screen_height - 250) // 2
        login_root.geometry(f"350x250+{x}+{y}")
        login_root.resizable(False, False)

        # Theme Colors
        BG_COLOR = "#051024"
        ACCENT_COLOR = "#00FF99"
        TEXT_COLOR = "#FFFFFF"
        ENTRY_BG = "#111111"
        
        login_root.configure(bg=BG_COLOR)

        # UI Components
        tk.Label(login_root, text="P2P PLAYLIST", font=("Segoe UI", 16, "bold"), bg=BG_COLOR, fg=ACCENT_COLOR).pack(pady=(20, 10))

        tk.Label(login_root, text="Display Name:", font=("Segoe UI", 10), bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="w", padx=40)
        entry_name = tk.Entry(login_root, bg=ENTRY_BG, fg=TEXT_COLOR, insertbackground=TEXT_COLOR, relief="flat", font=("Segoe UI", 10))
        entry_name.pack(fill="x", padx=40, pady=(0, 10), ipady=3)
        entry_name.focus_set()

        tk.Label(login_root, text="Network Password:", font=("Segoe UI", 10), bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="w", padx=40)
        entry_pwd = tk.Entry(login_root, show="*", bg=ENTRY_BG, fg=TEXT_COLOR, insertbackground=TEXT_COLOR, relief="flat", font=("Segoe UI", 10))
        entry_pwd.pack(fill="x", padx=40, pady=(0, 20), ipady=3)

        user_credentials = {"name": None, "pwd": None}

        def on_submit(event=None):
            n = entry_name.get().strip()
            p = entry_pwd.get().strip()
            if not n or not p:
                messagebox.showerror("Error", "Please enter both Name and Password.", parent=login_root)
                return
            user_credentials["name"] = n
            user_credentials["pwd"] = p
            login_root.destroy()

        def on_close():
            login_root.destroy()
            sys.exit(0)

        btn_submit = tk.Button(login_root, text="JOIN NETWORK", command=on_submit, bg=ACCENT_COLOR, fg="black", font=("Segoe UI", 10, "bold"), relief="flat", cursor="hand2")
        btn_submit.pack(fill="x", padx=40, ipady=5)

        login_root.bind('<Return>', on_submit)
        login_root.protocol("WM_DELETE_WINDOW", on_close)
        
        # Start the Login UI loop
        login_root.mainloop()

        name = user_credentials.get("name")
        pwd = user_credentials.get("pwd")

    if name and pwd:
        # Launch Main Application
        node = CollaborativeNode(name, pwd)
        node.start()
    else:
        sys.exit(0)