import socket
import threading
import pickle
import time
from typing import Dict
from src.utils.config import TCP_PORT, BUFFER_SIZE
from src.utils.models import Message

class NetworkNode:
    """
    The communication backbone of the decentralized playlist.
    Handles TCP connections, message routing, causal ordering via Vector Clocks,
    and coordinates between discovery, election, and audio subsystems.
    """
    
    def __init__(self, node_id, state_manager, logger_callback=None):
        self.node_id = str(node_id) 
        self.state = state_manager
        self.logger = logger_callback
        self.running = True
        
        # This port is dynamically assigned by CollaborativeNode in main.py
        self.port = TCP_PORT 
        
        # Subsystem references (populated by main.py)
        self.election = None
        self.audio = None 
        
        # Active peer connections: {node_id: socket}
        self.connections: Dict[str, socket.socket] = {}
        
        # Resolve local IP address
        try:
            # Connect to a dummy external address to find the primary local interface IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            self.ip = s.getsockname()[0]
            s.close()
        except Exception:
            self.ip = socket.gethostbyname(socket.gethostname())

    def log(self, text):
        """Standardized logging for the network subsystem."""
        if self.logger:
            self.logger(f"[Network] {text}")

    def start_server(self):
        """Starts the background thread to listen for incoming TCP connections."""
        thread = threading.Thread(target=self._server_loop, daemon=True)
        thread.start()

    def _server_loop(self):
        """TCP Server loop to accept connections from other peers on the LAN."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(('', self.port))
            except Exception as e:
                self.log(f"CRITICAL: Bind failed on {self.port}: {e}")
                return
                
            s.listen(5)
            self.log(f"Server listening on {self.port}")
            
            while self.running:
                try:
                    conn, addr = s.accept()
                    # Dedicated handler for each peer connection
                    thread = threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True)
                    thread.start()
                except Exception as e:
                    if self.running:
                        self.log(f"Server accept error: {e}")

    def _handle_client(self, conn, addr):
        """Listens for and deserializes incoming Message objects from a peer."""
        peer_id = None
        try:
            while self.running:
                data = conn.recv(BUFFER_SIZE)
                if not data:
                    break # Connection closed by remote node
                
                msg = pickle.loads(data)
                peer_id = str(msg.sender_id)
                
                # GUARD: Ignore any node connecting to itself (loopback)
                if peer_id == self.node_id:
                    conn.close()
                    return
                
                # Register connection mapping if new
                if peer_id not in self.connections:
                    self.connections[peer_id] = conn
                
                self._process_message(msg)
        except Exception as e:
            if self.running:
                self.log(f"Peer {peer_id or addr[0]} disconnected: {e}")
        finally:
            if peer_id and peer_id in self.connections:
                self.connections.pop(peer_id, None)
            conn.close()

    def connect_to_peer(self, node_id, ip, port):
        """Initiates a persistent TCP connection to a newly discovered peer."""
        node_id = str(node_id)
        
        # GUARD: Prevent redundant or self-connections
        if node_id == self.node_id or node_id in self.connections:
            return

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3.0)
            s.connect((ip, port))
            s.settimeout(None) # Revert to blocking mode
            
            self.connections[node_id] = s
            
            # Send initial WELCOME handshake to identify ourselves
            self.send_to_peer(node_id, 'WELCOME', payload={'id': self.node_id})
            self.log(f"Link established to: {node_id} ({ip}:{port})")
            
            # Start a listener for this specific socket
            thread = threading.Thread(target=self._handle_client, args=(s, (ip, port)), daemon=True)
            thread.start()
        except Exception as e:
            self.log(f"Failed to connect to {node_id} at {ip}:{port} - {e}")

    def send_to_peer(self, node_id, msg_type, payload=None):
        """Sends a Message object, handling Vector Clock logic for causal state sync."""
        if node_id not in self.connections:
            return
        
        # Clone the current clock for the message envelope
        clock = self.state.vector_clock.copy()
        
        # Increment clock for state-altering messages (playlist modifications)
        causal_types = ['QUEUE_SYNC', 'FULL_STATE_SYNC', 'REMOVE_SONG']
        if msg_type in causal_types:
            clock = self.state.increment_clock()
            
        msg = Message(self.node_id, self.ip, msg_type, payload, clock)
        
        try:
            data = pickle.dumps(msg)
            self.connections[node_id].sendall(data)
        except Exception as e:
            self.log(f"Send failure to {node_id}. Closing connection.")
            self.connections.pop(node_id, None)

    def _process_message(self, msg: Message):
        """Validates causal sequence using Vector Clocks and routes messages."""
        sender_id = str(msg.sender_id)
        
        # GUARD: Filter out loopback messages that reached this point
        if sender_id == self.node_id:
            return

        # Quiet logs for frequent heartbeat messages
        if msg.msg_type != 'HEARTBEAT':
            self.log(f"Received {msg.msg_type} from {sender_id}")
        
        # Control messages bypass causal ordering to ensure real-time responsiveness
        bypass_types = [
            'WELCOME', 'HEARTBEAT', 'ELECTION', 'ANSWER', 
            'COORDINATOR', 'REQUEST_STATE', 'NOW_PLAYING', 'PLAYBACK_SYNC'
        ]
        
        if msg.msg_type in bypass_types or self.state.can_process(msg):
            # Update our knowledge of the system-wide event counter
            self.state.update_clock(msg.vector_clock)
            self._handle_logic(msg)
            # Try to release any messages that were waiting for this specific clock tick
            self._check_buffer()
        else:
            self.log(f"Buffering out-of-order {msg.msg_type} from {sender_id}")
            self.state.pending_messages.append(msg)

    def _handle_logic(self, msg: Message):
        """Distributes messages to specific subsystem logic and updates shared state."""
        m_type = msg.msg_type
        
        if m_type == 'WELCOME':
            self.state.update_peer(msg.sender_id, msg.sender_ip, self.port)
            # Newly connected? Ask for the current playlist state immediately
            self.send_to_peer(msg.sender_id, 'REQUEST_STATE')
            
        elif m_type == 'REQUEST_STATE':
            # Peer asked for our playlist; provide current queue and now-playing data
            self.send_to_peer(msg.sender_id, 'FULL_STATE_SYNC', payload={
                'playlist': self.state.playlist,
                'current_song': getattr(self.state, 'current_song', None)
            })

        elif m_type == 'FULL_STATE_SYNC':
            # Initial state synchronization (usually triggered on join)
            incoming = msg.payload.get('playlist', [])
            self.state.current_song = msg.payload.get('current_song')
            for s in incoming:
                if not any(local_s.id == s.id for local_s in self.state.playlist):
                    self.state.add_song(s)
            self.log(f"Full state synchronized. Queue size: {len(self.state.playlist)}")

        elif m_type in ['ELECTION', 'ANSWER', 'COORDINATOR']:
            if self.election:
                if m_type == 'ELECTION': self.election.on_election_received(msg.sender_id)
                elif m_type == 'ANSWER': self.election.on_answer_received()
                elif m_type == 'COORDINATOR': 
                    leader_id = msg.payload['leader_id']
                    self.election.on_coordinator_received(leader_id)
                    # LEADERSHIP CHANGE: If we aren't leader, stop our local audio engine
                    if leader_id != self.node_id and self.audio:
                        self.audio.stop()
            
        elif m_type == 'HEARTBEAT':
            if self.election: self.election.on_heartbeat_received()
            
        elif m_type == 'QUEUE_SYNC':
            # Single song added to the global queue
            song = msg.payload.get('song')
            if song and not any(s.id == song.id for s in self.state.playlist):
                self.state.add_song(song)
                self.log(f"Queue updated: {song.title}")

        elif m_type == 'REMOVE_SONG':
            # Song finished playing or was skipped; remove from upcoming list
            sid = msg.payload.get('song_id')
            self.state.playlist = [s for s in self.state.playlist if s.id != sid]

        elif m_type == 'NOW_PLAYING':
            # Host notified everyone of a track starting
            song_obj = msg.payload.get('song')
            self.state.current_song = song_obj
            if song_obj:
                # Update shared metadata for UI and remove from upcoming queue
                self.state.now_playing_title = song_obj.title
                self.state.playlist = [s for s in self.state.playlist if s.id != song_obj.id]
                self.log(f"Host is now playing: {song_obj.title}")

        elif m_type == 'PLAYBACK_SYNC':
            # Continuous updates from host about current playback timestamp
            self.state.current_song_pos = msg.payload.get('pos', 0)

    def _check_buffer(self):
        """Processes buffered messages iteratively as causal gaps are filled."""
        changed = True
        while changed:
            changed = False
            for msg in self.state.pending_messages[:]:
                if self.state.can_process(msg):
                    self.state.update_clock(msg.vector_clock)
                    self._handle_logic(msg)
                    self.state.pending_messages.remove(msg)
                    changed = True