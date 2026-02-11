import threading
import time
from typing import Dict, List, Any, Set
from src.utils.models import Song, Message

# Reliable Multicast Configuration
ACK_TIMEOUT = 2.0          # Seconds to wait before retransmitting
MAX_RETRIES = 3            # Maximum retransmission attempts
RELIABLE_MSG_TYPES = {'QUEUE_SYNC', 'REMOVE_SONG', 'FULL_STATE_SYNC'}  # Message types that require ACKs

class StateManager:
    """Manages the distributed state, including Vector Clocks and Playlist Queue."""

    def __init__(self, node_id, logger_callback=None):
        self.node_id = node_id
        self.logger = logger_callback

        # Local state
        self.playlist: List[Song] = []
        self.peers: Dict[str, Dict[str, Any]] = {} # node_id -> {ip, port, last_seen}

        # Vector Clock: {node_id: counter}
        self.vector_clock: Dict[str, int] = {self.node_id: 0}

        # Message buffer for causal ordering
        # Stores messages that arrived too early (waiting for dependencies)
        self.pending_messages: List[Message] = []

        # ============ RELIABLE MULTICAST STRUCTURES ============
        # Tracks messages awaiting ACKs: {msg_id: {msg, timestamp, pending_peers, retries}}
        self.pending_acks: Dict[str, Dict[str, Any]] = {}

        # Tracks received message IDs to filter duplicates (retransmissions)
        self.seen_messages: Set[str] = set()

        # Lock for reliable multicast structures
        self.ack_lock = threading.Lock()
        # =======================================================

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

    def update_peer(self, node_id, ip, port):
        with self.lock:
            self.peers[node_id] = {'ip': ip, 'port': port, 'status': 'alive'}
            if node_id not in self.vector_clock:
                self.vector_clock[node_id] = 0
        self.log(f"Updated peer list: {self.peers}")
    
    def get_peer_name(self, node_id):
        """
        Backwards compatibility method.
        Since older NetworkNodes don't exchange names, we return the node ID.
        """
        return f"Node {node_id}"

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
            self.log(f"Checking if {node_id} is host: {self.host_id}")
            return self.host_id == node_id

    # ============ RELIABLE MULTICAST METHODS ============

    def register_pending_ack(self, msg_id: str, msg: Message, target_peers: List[str]):
        """
        Registers a message that requires ACKs from target peers.
        Called after sending a reliable message.
        """
        with self.ack_lock:
            self.pending_acks[msg_id] = {
                'msg': msg,
                'timestamp': time.time(),
                'pending_peers': set(target_peers),
                'retries': 0
            }
            self.log(f"[Reliable] Registered msg_id={msg_id}, awaiting ACKs from {target_peers}")

    def record_ack(self, msg_id: str, peer_id: str) -> bool:
        """
        Records an ACK received from a peer.
        Returns True if all ACKs received (message fully acknowledged).
        """
        with self.ack_lock:
            if msg_id not in self.pending_acks:
                return True  # Already completed or unknown

            entry = self.pending_acks[msg_id]
            entry['pending_peers'].discard(peer_id)
            self.log(f"[Reliable] ACK received for msg_id={msg_id} from {peer_id}. Remaining: {entry['pending_peers']}")

            if len(entry['pending_peers']) == 0:
                del self.pending_acks[msg_id]
                self.log(f"[Reliable] msg_id={msg_id} fully acknowledged!")
                return True
            return False

    def get_messages_to_retransmit(self) -> List[Dict[str, Any]]:
        """
        Returns list of messages that need retransmission (timed out, not max retries).
        Each entry: {msg_id, msg, peers}
        """
        retransmit = []
        current_time = time.time()

        with self.ack_lock:
            expired_ids = []
            for msg_id, entry in self.pending_acks.items():
                if current_time - entry['timestamp'] > ACK_TIMEOUT:
                    if entry['retries'] < MAX_RETRIES:
                        entry['retries'] += 1
                        entry['timestamp'] = current_time  # Reset timer
                        retransmit.append({
                            'msg_id': msg_id,
                            'msg': entry['msg'],
                            'peers': list(entry['pending_peers'])
                        })
                        self.log(f"[Reliable] Retransmit #{entry['retries']} for msg_id={msg_id} to {entry['pending_peers']}")
                    else:
                        # Max retries exceeded - give up
                        expired_ids.append(msg_id)
                        self.log(f"[Reliable] GAVE UP on msg_id={msg_id} after {MAX_RETRIES} retries")

            for msg_id in expired_ids:
                del self.pending_acks[msg_id]

        return retransmit

    def is_duplicate_message(self, msg_id: str) -> bool:
        """
        Checks if we've already processed this message (duplicate/retransmission).
        If not seen, marks it as seen and returns False.
        """
        with self.ack_lock:
            if msg_id in self.seen_messages:
                self.log(f"[Reliable] Duplicate msg_id={msg_id} detected, ignoring")
                return True
            self.seen_messages.add(msg_id)

            # Cleanup old entries (keep last 1000)
            if len(self.seen_messages) > 1000:
                # Remove oldest entries (convert to list, slice, convert back)
                self.seen_messages = set(list(self.seen_messages)[-500:])

            return False