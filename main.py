import sys
import uuid
import time
import threading
import socket
import random
import pygame
import os
import hashlib

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from src.backend.discovery import DiscoveryManager
from src.backend.network_node import NetworkNode
from src.backend.state_manager import StateManager
from src.backend.bully_election import ElectionManager
from src.backend.audio_engine import AudioEngine
from src.utils.config import TCP_PORT, HEARTBEAT_INTERVAL
from src.frontend.app_ui import PlaylistUI
from src.utils.models import Song
from src.utils import config

class CollaborativeNode:
    """Main controller for the Decentralized Playlist."""
    
    def __init__(self, display_name=None, password=None):
        # Enforce Password
        if not display_name or not password:
            print("ERROR: Name and Password are required.")
            print("Usage: python main.py [Name] [Password]")
            sys.exit(1)

        # Deterministic ID Generation:
        # Generate a stable UUID based on Name + Password.
        seed = f"{display_name}:{password}"
        full_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, seed)
        self.node_id = str(full_uuid)[:8]
        self.display_name = display_name

        self.tcp_port = self._find_available_port(TCP_PORT)
        
        # Pass Display Name to UI
        self.ui = PlaylistUI(f"{self.display_name} [{self.node_id}]", self.on_add_song_request)
        
        self.state = StateManager(self.node_id, self.ui_log)
        self.state.current_duration = 0 
        self.history = [] 
        
        # Initialize Backend with Display Name
        self.network = NetworkNode(self.node_id, self.state, self.ui_log, display_name=self.display_name)
        self.network.port = self.tcp_port
        
        # Election (Standard Uptime Bully Algo)
        self.election = ElectionManager(
            self.node_id, 
            self.state, 
            self.network, 
            self.ui_log
        )
        self.network.election = self.election 
        
        # Discovery
        self.discovery = DiscoveryManager(self.node_id, self.tcp_port, self.ui_log)
        
        self.audio = AudioEngine(self.ui_log)
        self.network.audio = self.audio
        
        self.is_shuffle_active = False 
        self.last_played_id = None
        self.local_is_paused = False
        self.running = True
        
        self.simulated_battery = 100
        
        # Wire UI Callbacks
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
        p = start_port
        while p < start_port + 100:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('', p))
                    return p
            except: p += 1
        return start_port

    def ui_log(self, message):
        formatted_msg = f"[{time.strftime('%H:%M:%S')}] {message}"
        print(formatted_msg) 
        if hasattr(self, 'ui'): self.ui.log_message(formatted_msg)

    def _get_battery_level(self):
        if HAS_PSUTIL:
            battery = psutil.sensors_battery()
            if battery:
                return int(battery.percent)
        return int(self.simulated_battery)

    def on_add_song_request(self, file_path):
        # Extract just the filename to be OS-agnostic
        filename = os.path.basename(file_path)
        # Store only the filename as the file_path in the Song object
        # We assume the file exists in the local directory or a specific assets folder
        new_song = Song(title=filename, added_by=self.display_name, file_path=filename)
        self.state.add_song(new_song)
        self._broadcast('QUEUE_SYNC', {'song': new_song})

    def on_skip_next(self):
        if not self.election.is_host: return
        self.ui_log("CMD: Skip Next")
        self.audio.stop()
        self.local_is_paused = False
        if len(self.state.playlist) > 0:
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
            self.ui_log("Queue end.")
            self.state.current_song = None
            self.state.current_duration = 0 
            self.state.current_song_pos = 0 
            
            # Reset Play/Pause State
            self.state.is_playing = False
            self.local_is_paused = False
            self.ui.update_play_pause_icon(False)
            
            self._broadcast('NOW_PLAYING', {'song': None})
            self._broadcast('PLAYBACK_SYNC', {'pos': 0, 'dur': 0})
            
            # Broadcast Status Reset
            status_msg = {
                'is_playing': False,
                'shuffle': self.state.shuffle_active,
                'repeat_mode': self.state.repeat_mode
            }
            self._broadcast('PLAYBACK_STATUS', status_msg)
            
            self.last_played_id = None

    def on_skip_prev(self):
        if not self.election.is_host: return
        self.ui_log("CMD: Skip Previous")
        
        # Ensure we have a current song before attempting to seek
        if not self.state.current_song:
            return

        # Use _resolve_path to handle cross-OS path differences
        resolved_path = self._resolve_path(self.state.current_song.file_path)

        # Restart current song if played for more than 5 seconds
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
            # If no history and < 5s, treat as restart (common behavior when previous is clicked at start of track)
             self.audio.seek(0, resolved_path)
             self.state.current_song_pos = 0
             self._broadcast('PLAYBACK_SYNC', {'pos': 0, 'dur': getattr(self.state, 'current_duration', 0)})

    def on_play_pause(self):
        if not self.election.is_host: return
        if not self.state.current_song: return
        
        # toggle_pause returns True if PAUSED, False if PLAYING (RESUMED)
        is_paused = self.audio.toggle_pause()
        self.local_is_paused = is_paused 
        
        # State: Playing = NOT Paused
        self.state.is_playing = not is_paused
        
        action = 'pause' if is_paused else 'resume'
        self.ui_log(f"CMD: {action.upper()}")
        
        status_msg = {
            'is_playing': self.state.is_playing,
            'shuffle': self.state.shuffle_active,
            'repeat_mode': self.state.repeat_mode
        }
        self._broadcast('PLAYBACK_STATUS', status_msg)
        
        # Update UI: Pass True if Playing (shows Pause icon), False if Paused (shows Play icon)
        self.ui.update_play_pause_icon(self.state.is_playing)

    def on_seek(self, value):
        if not self.election.is_host: return
        
        dur = getattr(self.state, 'current_duration', 0)
        if dur > 0:
            seek_sec = (float(value) / 100.0) * dur
            
            # Resolve path before seeking
            resolved_path = self._resolve_path(self.state.current_song.file_path)
            
            # Perform the seek
            self.audio.seek(seek_sec, resolved_path)
            self.state.current_song_pos = seek_sec
            
            # FIX: If currently paused locally, re-apply pause after seeking
            if self.local_is_paused:
                # The seek likely resumed playback (Pygame usually does).
                # Force pause state back.
                self.audio.toggle_pause() 
                # Ensure local variable stays True (Paused)
                self.local_is_paused = True
            
            self._broadcast('PLAYBACK_SYNC', {'pos': seek_sec, 'dur': dur})
            
    def on_volume_change(self, val):
        self.audio.set_volume(val)

    def on_shuffle(self):
        if not self.election.is_host: return
        self.is_shuffle_active = not self.is_shuffle_active
        self.state.shuffle_active = self.is_shuffle_active # Sync with state manager
        self.ui_log(f"CMD: Shuffle {'ON' if self.is_shuffle_active else 'OFF'}")
        if self.is_shuffle_active:
            random.shuffle(self.state.playlist)
            self._broadcast('FULL_STATE_SYNC', {
                'playlist': self.state.playlist, 
                'current_song': self.state.current_song,
                'is_playing': self.state.is_playing,
                'shuffle': self.state.shuffle_active,
                'repeat_mode': self.state.repeat_mode
            })
        self.ui.update_toggles(self.state.repeat_mode, self.is_shuffle_active)

    def on_repeat(self):
        if not self.election.is_host: return
        self.state.repeat_mode = (self.state.repeat_mode + 1) % 3
        modes = ["Off", "Repeat All", "Repeat One"]
        self.ui_log(f"CMD: Repeat Mode set to {modes[self.state.repeat_mode]}")
        self.ui.update_toggles(self.state.repeat_mode, self.is_shuffle_active)
        # Broadcast Status so peers see the toggle
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
        self._broadcast('QUEUE_CLEARED', {}) # Use standard backend message

    def on_remove_song(self, song_id):
        if not self.election.is_host: return
        self.state.playlist = [s for s in self.state.playlist if s.id != song_id]
        self.ui_log(f"Removed ID: {song_id}")
        self._broadcast('REMOVE_SONG', {'song_id': song_id})

    def _broadcast(self, msg_type, payload):
        for pid in list(self.network.connections.keys()):
            self.network.send_to_peer(pid, msg_type, payload=payload)

    def _get_duration(self, file_path):
        try:
            return pygame.mixer.Sound(file_path).get_length()
        except:
            # Fallback attempts using mutagen if available (from previous version)
            return 180.0 

    def _resolve_path(self, file_path):
        """
        Attempts to resolve the file path across different OS environments.
        Assumes audio files are in the same directory as main.py or a known subfolder.
        """
        # If absolute path exists, use it
        if os.path.exists(file_path):
            return file_path
            
        # Try local directory with just the filename
        filename = os.path.basename(file_path)
        if os.path.exists(filename):
            return filename
            
        # Try an 'assets' or 'music' subfolder if you have one
        # assets_path = os.path.join("assets", filename)
        # if os.path.exists(assets_path):
        #     return assets_path
            
        return file_path # Return original if resolution fails

    def _play_song_logic(self, song, start_offset=0):
        # Resolve path for cross-OS compatibility
        resolved_path = self._resolve_path(song.file_path)
        
        if not os.path.exists(resolved_path):
            self.ui_log(f"Error: File missing locally: {resolved_path}")
            self.ui.show_notification(f"Missing File: {song.title}", is_error=True)
            if self.election.is_host:
                self.ui_log("Host missing file. Skipping to next...")
                self.last_played_id = song.id 
                if len(self.state.playlist) > 0:
                    next_song = self.state.playlist.pop(0)
                    self.state.current_song = next_song
                    self.state.current_song_pos = 0
                    self._play_song_logic(next_song)
                else:
                    self.state.current_song = None 
                    self.state.current_duration = 0 # Reset duration
                    self.state.current_song_pos = 0
                    self._broadcast('NOW_PLAYING', {'song': None}) 
                    self._broadcast('PLAYBACK_SYNC', {'pos': 0, 'dur': 0})
                    self.ui_log("Queue ended (last song missing).")
                return
            
        if self.audio.play_song(resolved_path, start_time=start_offset):
            self.local_is_paused = False 
            self.last_played_id = song.id
            self.state.current_duration = self._get_duration(resolved_path)
            self.state.is_playing = True
            
            # Sync to network
            self._broadcast('NOW_PLAYING', {'song': song})
            self._broadcast('PLAYBACK_SYNC', {'pos': start_offset, 'dur': self.state.current_duration})
            
            # Full sync ensures robust state for late joiners
            self._broadcast('FULL_STATE_SYNC', {
                'playlist': self.state.playlist, 
                'current_song': song,
                'is_playing': True,
                'shuffle': self.state.shuffle_active,
                'repeat_mode': self.state.repeat_mode
            })
            self.ui.update_play_pause_icon(True)

    def _refresh_ui(self):
        if not hasattr(self, 'ui'): return
        is_host = self.election.is_host
        leader = self.state.get_host()
        
        # Get Host Name
        host_name = "Unknown"
        if leader:
            host_name = self.state.get_peer_name(leader)
            
        self.ui.set_controls_visible(is_host, host_id=leader, host_name=host_name)
        cp = self.state.current_song
        
        if cp:
            # Check existence using the resolved path logic
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
        time.sleep(2) 
        debug_timer = time.time() + 3
        while self.running:
            try:
                self.state.update_uptime(int(time.time() - self.election.init_time))
                
                self._refresh_ui()
                
                if time.time() > debug_timer:
                    # Optional: Print detailed stats if desired, otherwise suppressed to keep log clean
                    debug_timer = time.time() + 5
                
                if self.election.is_host:
                    for pid in list(self.network.connections.keys()):
                        self.network.send_to_peer(pid, 'HEARTBEAT')
                        self.election.update_heartbeat()

                    if self.audio.is_busy() or self.local_is_paused:
                        current_pos = self.audio.get_current_pos()
                        self.state.current_song_pos = current_pos
                        self._broadcast('PLAYBACK_SYNC', {'pos': current_pos, 'dur': getattr(self.state, 'current_duration', 0)})
                    else:
                        target_song = None
                        start_offset = 0
                        if self.state.current_song and self.state.current_song.id != self.last_played_id:
                            target_song = self.state.current_song
                            start_offset = self.state.current_song_pos
                        elif self.state.repeat_mode == 2 and self.state.current_song:
                            target_song = self.state.current_song
                        elif len(self.state.playlist) > 0:
                            if self.state.repeat_mode == 1 and self.state.current_song:
                                self.state.playlist.append(self.state.current_song)
                            target_song = self.state.playlist.pop(0)
                            if self.state.current_song and self.state.current_song.id != target_song.id:
                                self.history.append(self.state.current_song)
                            self.state.current_song = target_song
                            self.state.current_song_pos = 0
                        elif self.state.current_song is not None:
                            self.ui_log("Playlist complete.")
                            self.state.current_song = None
                            self.state.current_duration = 0 
                            self.state.current_song_pos = 0
                            
                            # RESET Play State Here
                            self.state.is_playing = False
                            self.local_is_paused = False
                            self.ui.update_play_pause_icon(False)
                            
                            self._broadcast('NOW_PLAYING', {'song': None})
                            self._broadcast('PLAYBACK_SYNC', {'pos': 0, 'dur': 0})
                            
                            # Send Status Reset to Peers
                            status_msg = {
                                'is_playing': False,
                                'shuffle': self.state.shuffle_active,
                                'repeat_mode': self.state.repeat_mode
                            }
                            self._broadcast('PLAYBACK_STATUS', status_msg)

                        if target_song:
                            self._play_song_logic(target_song, start_offset)
                    
                else:
                    host = self.state.get_host()
                    # if host and host in self.network.connections:
                        # self.network.send_to_peer(host, 'HEARTBEAT') # Listeners typically don't send heartbeats in basic Bully, but kept from your example

                self.election.check_for_host_failure()
                time.sleep(HEARTBEAT_INTERVAL)
            except Exception as e:
                print(f"Error in maintenance loop: {e}")

    def start(self):
        self.network.start_server()
        self.discovery.start_listener(self.on_peer_discovered)
        self.discovery.broadcast_presence()
        threading.Thread(target=self._maintenance_loop, daemon=True).start()
        self.ui_log(f"Node started. ID: {self.node_id}")
        
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
    name = sys.argv[1] if len(sys.argv) > 1 else None
    pwd = sys.argv[2] if len(sys.argv) > 2 else None
    
    node = CollaborativeNode(name, pwd)
    node.start()