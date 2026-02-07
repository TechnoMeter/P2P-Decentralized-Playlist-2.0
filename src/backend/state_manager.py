import threading
from typing import Dict, List, Any
from src.utils.models import Song, Message

class StateManager:
    """Manages the distributed state, including Vector Clocks and Playlist Queue."""
    
    def __init__(self, node_id, logger_callback=None):
        self.node_id = node_id
        self.logger = logger_callback
        
        # Local state
        self.playlist: List[Song] = []
        # peers: node_id -> {ip, port, status, display_name}
        self.peers: Dict[str, Dict[str, Any]] = {} 
        
        # Playback State
        self.current_song = None
        self.current_song_pos = 0
        self.is_playing = False
        self.shuffle_active = False
        
        # Repeat Mode: 0 = Off, 1 = Repeat All, 2 = Repeat One
        self.repeat_mode = 0 
        
        # Vector Clock: {node_id: counter}
        self.vector_clock: Dict[str, int] = {self.node_id: 0}
        
        # Message buffer for causal ordering
        self.pending_messages: List[Message] = []

        self.uptime = 0
        self.lock = threading.Lock()
        self.host_id = None

    def log(self, text):
        if self.logger: self.logger(f"[State] {text}")

    def increment_clock(self):
        """Called before sending a message."""
        with self.lock:
            self.vector_clock[self.node_id] = self.vector_clock.get(self.node_id, 0) + 1
            return self.vector_clock.copy()

    def update_clock(self, incoming_clock: Dict[str, int]):
        """Synchronizes local clock with incoming message clock."""
        with self.lock:
            for uid, count in incoming_clock.items():
                self.vector_clock[uid] = max(self.vector_clock.get(uid, 0), count)

    def can_process(self, msg: Message) -> bool:
        """
        Checks Causal Ordering:
        1. V_msg[sender] == V_local[sender] + 1
        2. V_msg[other] <= V_local[other] for all other keys
        """
        sender = msg.sender_id
        msg_clock = msg.vector_clock
        
        # Check condition 1
        if msg_clock.get(sender, 0) != self.vector_clock.get(sender, 0) + 1:
            return False
            
        # Check condition 2
        for uid, count in msg_clock.items():
            if uid != sender:
                if count > self.vector_clock.get(uid, 0):
                    return False
        return True

    def update_peer(self, node_id, ip, port, display_name=None):
        with self.lock:
            existing = self.peers.get(node_id, {})
            existing['ip'] = ip
            existing['port'] = port
            if display_name:
                existing['display_name'] = display_name
                
            self.peers[node_id] = existing
            
            if node_id not in self.vector_clock:
                self.vector_clock[node_id] = 0
        
        name_str = f" ({display_name})" if display_name else ""
        self.log(f"Updated peer: {node_id}{name_str}")

    def get_peer_name(self, node_id):
        with self.lock:
            return self.peers.get(node_id, {}).get('display_name', 'Unknown')

    def add_song(self, song: Song):
        with self.lock:
            self.playlist.append(song)
            self.log(f"Added to queue: {song.title} by {song.artist}")
            return True
        
    def update_uptime(self, seconds):
        with self.lock:
            self.uptime = seconds

    def get_uptime(self):
        with self.lock:
            return self.uptime

    def set_host(self, node_id):
        with self.lock:
            self.host_id = node_id
            self.log(f"Set host to: {self.host_id}")

    def get_host(self):
        with self.lock:
            return self.host_id
        
    def is_host(self, node_id):
        with self.lock:
            return self.host_id == node_id