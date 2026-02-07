"""
PEER DISCOVERY (UDP)
--------------------
Handles finding other nodes on the LAN.
1. Broadcasts 'HELLO' packets to UDP broadcast address.
2. Listens for 'HELLO' packets from others.
"""

import socket
import threading
import pickle
from src.utils.config import UDP_PORT, get_local_ip
from src.utils.models import Message

class DiscoveryManager:
    def __init__(self, node_id, tcp_port, logger_callback=None):
        self.node_id = node_id
        self.tcp_port = tcp_port
        self.local_ip = get_local_ip()
        self.logger = logger_callback
        self.running = True

    def log(self, text):
        if self.logger:
            self.logger(f"[Discovery] {text}")
        else:
            print(f"[Discovery] {text}")

    def start_listener(self, on_peer_found):
        """Spawns the background UDP listening thread."""
        thread = threading.Thread(target=self._listen_loop, args=(on_peer_found,), daemon=True)
        thread.start()
        self.log(f"Listener active on {self.local_ip}:{UDP_PORT}")

    def _listen_loop(self, on_peer_found):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Allow multiple instances on same machine (Linux/Mac specific)
            if hasattr(socket, 'SO_REUSEPORT'):
                try:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except OSError:
                    pass 

            try:
                # Binding to empty string implies INADDR_ANY (all interfaces)
                s.bind(('', UDP_PORT))
            except OSError as e:
                self.log(f"Critical Bind Error: {e}. Another instance might be blocking the port.")
                return
            
            while self.running:
                try:
                    data, addr = s.recvfrom(4096)
                    msg = pickle.loads(data)

                    if msg.sender_id == self.node_id:
                        continue 
                    
                    if msg.msg_type == 'HELLO':
                        self.log(f"Peer {msg.sender_id} found at {addr[0]}")
                        # Callback to Main to establish TCP connection
                        on_peer_found(msg.sender_id, addr[0], msg.payload.get('tcp_port'))
                except Exception as e:
                    if self.running:
                        self.log(f"Error in listen loop: {e}")

    def broadcast_presence(self):
        """Sends a UDP packet announcing self to the subnet."""
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            
            msg = Message(
                sender_id=self.node_id,
                sender_ip=self.local_ip,
                msg_type='HELLO',
                payload={'tcp_port': self.tcp_port}
            )
            
            try:
                # 255.255.255.255 generic broadcast
                s.sendto(pickle.dumps(msg), ('<broadcast>', UDP_PORT))
                # Localhost fallback for single-machine testing
                s.sendto(pickle.dumps(msg), ('127.0.0.1', UDP_PORT))
                self.log("Broadcasted presence to network.")
            except Exception as e:
                self.log(f"Broadcast failed: {e}")

    def stop(self):
        self.running = False