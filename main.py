import sys
import uuid
import time
import threading
import socket
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
    
    def __init__(self, node_id=None):
        self.node_id = node_id or str(uuid.uuid4())[:8]
        self.tcp_port = self._find_available_port(TCP_PORT)
        
        self.ui = PlaylistUI(self.node_id, self.on_add_song_request)
        self.state = StateManager(self.node_id, self.ui_log)
        self.state.current_song = None
        self.state.current_song_pos = 0 
        
        self.network = NetworkNode(self.node_id, self.state, self.ui_log)
        self.network.port = self.tcp_port
        
        self.election = ElectionManager(self.node_id, self.state, self.network, self.ui_log)
        self.network.election = self.election 
        
        self.discovery = DiscoveryManager(self.node_id, self.tcp_port, self.ui_log)
        self.audio = AudioEngine(self.ui_log)
        self.network.audio = self.audio
        
        self.ui.on_skip = self.on_skip_request
        self.ui.on_volume = self.audio.set_volume
        
        self.last_played_id = None
        self.running = True

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

    def on_add_song_request(self, file_path):
        title = file_path.replace("\\", "/").split("/")[-1]
        new_song = Song(title=title, added_by=self.node_id, file_path=file_path)
        self.state.add_song(new_song)
        for pid in list(self.network.connections.keys()):
            self.network.send_to_peer(pid, 'QUEUE_SYNC', payload={'song': new_song})

    def on_skip_request(self):
        if not self.election.is_host:
            self.ui_log("Skip ignored: Only the Host can control playback.")
            return
        self.ui_log("Skip requested...")
        self.audio.stop()

    def _refresh_ui(self):
        if not hasattr(self, 'ui'): return
        
        is_host = self.election.is_host
        leader = self.state.get_host()
        
        # Update Role and toggle controls visibility
        self.ui.set_controls_visible(is_host)
        
        if is_host:
            status = "HOST (Leader)"
        elif leader:
            status = f"Follower (Host: {leader})"
        else:
            status = "Election in progress..."
        self.ui.status_label.config(text=f"Role: {status}")
        # self.ui_log(f"Role updated: {status}, {is_host}, {leader}")
        cp = self.state.current_song
        self.ui.now_playing_label.config(text=cp.title if cp else "Nothing is playing")

        current_children = self.ui.tree.get_children()
        if len(current_children) != len(self.state.playlist):
            for item in current_children: self.ui.tree.delete(item)
            for song in self.state.playlist:
                self.ui.tree.insert("", "end", values=(song.title, "Unknown", song.added_by))

    def _maintenance_loop(self):
        time.sleep(2) 
        while self.running:
            self._refresh_ui()
            
            if self.election.is_host:
                for pid in list(self.network.connections.keys()):
                    self.network.send_to_peer(pid, 'HEARTBEAT')
                
                higher_nodes = [pid for pid in self.network.state.peers.keys() if pid > self.node_id]
                if higher_nodes and not self.election.is_election_running:
                    self.election.is_host = False
                    self.ui_log(f"_maintenance_loop: ELECTION")
                    self.election.start_election()

                if self.audio.is_busy():
                    current_pos = self.audio.get_current_pos()
                    self.state.current_song_pos = current_pos
                    for pid in list(self.network.connections.keys()):
                        self.network.send_to_peer(pid, 'PLAYBACK_SYNC', payload={'pos': current_pos})
                else:
                    target_song = None
                    start_offset = 0
                    
                    if self.state.current_song and self.state.current_song.id != self.last_played_id:
                        target_song = self.state.current_song
                        start_offset = getattr(self.state, 'current_song_pos', 0)
                    elif len(self.state.playlist) > 0:
                        target_song = self.state.playlist.pop(0)
                        self.state.current_song = target_song
                        self.state.current_song_pos = 0
                        for pid in list(self.network.connections.keys()):
                            self.network.send_to_peer(pid, 'NOW_PLAYING', payload={'song': target_song})
                            self.network.send_to_peer(pid, 'REMOVE_SONG', payload={'song_id': target_song.id})
                    elif self.state.current_song is not None:
                        # PLAYLIST COMPLETE: Clear state and notify peers
                        self.ui_log("Playlist complete.")
                        self.state.current_song = None
                        self.state.current_song_pos = 0
                        for pid in list(self.network.connections.keys()):
                            self.network.send_to_peer(pid, 'NOW_PLAYING', payload={'song': None})

                    if target_song:
                        if self.audio.play_song(target_song.file_path, start_time=start_offset):
                            self.last_played_id = target_song.id

            self.election.check_for_host_failure()
            time.sleep(HEARTBEAT_INTERVAL)

    def start(self):
        self.network.start_server()
        self.discovery.start_listener(self.on_peer_discovered)
        self.discovery.broadcast_presence()
        threading.Thread(target=self._maintenance_loop, daemon=True).start()
        self.ui_log(f"Node started. {self.state.peers}")
        def delayed_election():
            time.sleep(1.0)
            self.ui_log(f"start: ELECTION")
            self.election.start_election()
        threading.Thread(target=delayed_election, daemon=True).start()
        self.ui.run()

    def on_peer_discovered(self, pid, ip, port):
        if str(pid) != str(self.node_id):
            self.network.connect_to_peer(pid, ip, port)
            if self.election.is_host and str(pid) > str(self.node_id):
                self.ui_log(f"on_peer_discovered: ELECTION")
                # self.election.start_election()

if __name__ == "__main__":
    cid = sys.argv[1] if len(sys.argv) > 1 else None
    node = CollaborativeNode(cid)
    node.start()