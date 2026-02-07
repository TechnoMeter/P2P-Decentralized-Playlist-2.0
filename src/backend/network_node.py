"""
NETWORK NODE (TCP)
------------------
Handles the persistent TCP connections between peers.
Responsibilities:
1. Managing socket connections.
2. Sending/Receiving pickled message objects.
3. Routing incoming messages to State, Election, or Audio logic.
4. Implementing Causal Ordering (via StateManager validation).
"""

import socket
import threading
import pickle
import struct
import time
from typing import Dict
from src.utils.config import TCP_PORT
from src.utils.models import Message

class NetworkNode:
    def __init__(self, node_id, state_manager, logger_callback=None, display_name="Unknown"):
        self.node_id = str(node_id) 
        self.state = state_manager
        self.logger = logger_callback
        self.display_name = display_name
        self.running = True
        
        self.port = TCP_PORT 
        
        # Subsystems (injected later)
        self.election = None
        self.audio = None 
        
        self.connections: Dict[str, socket.socket] = {}
        
        # Determine Local IP
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            self.ip = s.getsockname()[0]
            s.close()
        except Exception:
            self.ip = socket.gethostbyname(socket.gethostname())

    def log(self, text):
        if self.logger: self.logger(f"[Network] {text}")

    def start_server(self):
        """Start the background thread that accepts new TCP connections."""
        thread = threading.Thread(target=self._server_loop, daemon=True)
        thread.start()

    def _server_loop(self):
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
                    threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True).start()
                except: pass

    def _recv_all(self, conn, n):
        """Helper to ensure exactly n bytes are read (handling TCP fragmentation)."""
        data = bytearray()
        while len(data) < n:
            packet = conn.recv(n - len(data))
            if not packet: return None
            data.extend(packet)
        return data

    def _handle_client(self, conn, addr):
        """Thread dedicated to listening to a specific connected peer."""
        peer_id = None
        try:
            while self.running:
                # 1. Read Message Length Header (4 bytes)
                header = self._recv_all(conn, 4)
                if not header: break
                msg_len = struct.unpack('>I', header)[0]
                
                # 2. Read Exact Payload
                data = self._recv_all(conn, msg_len)
                if not data: break
                
                # 3. Deserialize
                msg = pickle.loads(data)
                peer_id = str(msg.sender_id)
                
                if peer_id == self.node_id:
                    conn.close()
                    return
                
                if peer_id not in self.connections:
                    self.connections[peer_id] = conn
                
                self._process_message(msg)
        except Exception as e:
            if self.running:
                self.log(f"Peer {peer_id} disconnected: {e}")
                # If Host disconnected, trigger election
                if self.state.is_host(peer_id) and self.election:
                    self.election.start_election()
                
        finally:
            if peer_id in self.connections: self.connections.pop(peer_id)
            conn.close()

    def connect_to_peer(self, node_id, ip, port):
        """Initiates a TCP connection to a discovered peer."""
        node_id = str(node_id)
        if node_id == self.node_id or node_id in self.connections: return
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3.0)
            s.connect((ip, port))
            s.settimeout(None)
            self.connections[node_id] = s
            
            self.state.update_peer(node_id, ip, port)

            # Exchange Identities
            payload = {'id': self.node_id, 'name': self.display_name, 'is_reply': False}
            
            if self.state.is_host(self.node_id):
                self.send_to_peer(node_id, 'WELCOME', payload=payload)

            self.send_to_peer(node_id, 'HELLO', payload=payload)

            threading.Thread(target=self._handle_client, args=(s, (ip, port)), daemon=True).start()
        except Exception as e:
            self.log(f"Connection failed to {node_id}: {e}")

    def send_to_peer(self, node_id, msg_type, payload=None):
        """Sends a pickle-serialized message prefixed with length header."""
        if node_id not in self.connections: return
        
        clock = self.state.vector_clock.copy()
        
        # Increment logical clock for state-changing messages
        if msg_type in ['QUEUE_SYNC', 'FULL_STATE_SYNC', 'REMOVE_SONG', 'PLAYBACK_STATUS']:
            clock = self.state.increment_clock()
            
        msg = Message(self.node_id, self.ip, msg_type, payload, clock)
        try:
            data = pickle.dumps(msg)
            header = struct.pack('>I', len(data))
            self.connections[node_id].sendall(header + data)
        except:
            self.connections.pop(node_id, None)

    def _process_message(self, msg: Message):
        """Routes message based on type and checks Causal Ordering."""
        sender_id = str(msg.sender_id)
        if sender_id == self.node_id: return
        
        if msg.msg_type not in ['HEARTBEAT', 'PLAYBACK_SYNC']:
            self.log(f"Processing {msg.msg_type} from {sender_id}")
        
        # Messages that bypass causal ordering checks (Discovery/Heartbeats)
        bypass_types = ['HELLO','WELCOME', 'HEARTBEAT', 'ELECTION', 'ANSWER', 
                        'COORDINATOR', 'REQUEST_STATE', 'NOW_PLAYING', 
                        'PLAYBACK_SYNC', 'REMOVE_SONG', 'QUEUE_SYNC', 
                        'PLAYBACK_STATUS', 'QUEUE_CLEARED']
                        
        if msg.msg_type in bypass_types or self.state.can_process(msg):
            self.state.update_clock(msg.vector_clock)
            self._handle_logic(msg)
            # After processing one, check if we can process any buffered messages
            self._check_buffer()
        else:
            self.state.pending_messages.append(msg)

    def _handle_logic(self, msg: Message):
        """Executes the actual business logic for a received message."""
        m_type = msg.msg_type
        payload = msg.payload

        if m_type == 'WELCOME': 
            self.state.set_host(msg.sender_id)
            if 'name' in payload:
                self.state.update_peer(msg.sender_id, msg.sender_ip, self.port, payload['name'])

        elif m_type == 'HEARTBEAT':
            if self.election:
                self.election.on_heartbeat_received()

        elif m_type == 'HELLO':
            name = payload.get('name', 'Unknown')
            is_reply = payload.get('is_reply', False)
            self.state.update_peer(msg.sender_id, msg.sender_ip, self.port, name)
            
            if not is_reply:
                reply = {'id': self.node_id, 'name': self.display_name, 'is_reply': True}
                self.send_to_peer(msg.sender_id, 'HELLO', payload=reply)

            if not self.state.get_host() or self.state.is_host(msg.sender_id):
                self.send_to_peer(msg.sender_id, 'REQUEST_STATE')

        elif m_type == 'REQUEST_STATE':
            self.send_to_peer(msg.sender_id, 'FULL_STATE_SYNC', payload={
                'playlist': self.state.playlist,
                'current_song': getattr(self.state, 'current_song', None),
                'is_playing': self.state.is_playing,
                'shuffle': self.state.shuffle_active,
                'repeat_mode': self.state.repeat_mode
            })

        elif m_type == 'FULL_STATE_SYNC':
            incoming = payload.get('playlist', [])
            self.state.current_song = payload.get('current_song')
            self.state.is_playing = payload.get('is_playing', False)
            self.state.shuffle_active = payload.get('shuffle', False)
            self.state.repeat_mode = payload.get('repeat_mode', 0)
            
            with self.state.lock:
                for s in incoming:
                    if not any(local_s.id == s.id for local_s in self.state.playlist):
                        self.state.playlist.append(s)

        elif m_type in ['ELECTION', 'ANSWER', 'COORDINATOR']:
            if self.election:
                if m_type == 'ELECTION': 
                    self.election.on_election_received(msg.sender_id, payload.get('uptime'))
                elif m_type == 'ANSWER': 
                    self.election.on_answer_received()
                elif m_type == 'COORDINATOR': 
                    leader_id = payload['leader_id']
                    self.election.on_coordinator_received(leader_id)
                    if leader_id != self.node_id and self.audio: 
                        self.audio.stop()
        
        elif m_type == 'QUEUE_SYNC':
            song = payload.get('song')
            if song:
                with self.state.lock:
                    if not any(s.id == song.id for s in self.state.playlist):
                        self.state.playlist.append(song)
                        self.log(f"Queue updated: {song.title}")

        elif m_type == 'REMOVE_SONG':
            sid = payload.get('song_id')
            with self.state.lock:
                self.state.playlist = [s for s in self.state.playlist if s.id != sid]

        elif m_type == 'QUEUE_CLEARED':
            with self.state.lock:
                self.state.playlist.clear()

        elif m_type == 'NOW_PLAYING':
            song_obj = payload.get('song')
            self.state.current_song = song_obj
            if song_obj:
                with self.state.lock:
                    self.state.playlist = [s for s in self.state.playlist if s.id != song_obj.id]
        
        elif m_type == 'PLAYBACK_SYNC':
            self.state.current_song_pos = payload.get('pos', 0)
            if 'dur' in payload:
                self.state.current_duration = payload['dur']

        elif m_type == 'PLAYBACK_STATUS':
            self.state.is_playing = payload.get('is_playing', False)
            self.state.shuffle_active = payload.get('shuffle', False)
            self.state.repeat_mode = payload.get('repeat_mode', 0)

    def _check_buffer(self):
        """Re-evaluates pending messages to see if dependencies are now met."""
        changed = True
        while changed:
            changed = False
            for msg in self.state.pending_messages[:]:
                if self.state.can_process(msg):
                    self.state.update_clock(msg.vector_clock)
                    self._handle_logic(msg)
                    self.state.pending_messages.remove(msg)
                    changed = True