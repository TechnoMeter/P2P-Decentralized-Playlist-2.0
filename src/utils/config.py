"""
CONFIGURATION
-------------
Network ports, timing constants, and utility helpers.
"""

import socket

# --- Networking ---
UDP_PORT = 5000          # Peer Discovery
TCP_PORT = 5001          # State Synchronization (Default, increments if busy)
BUFFER_SIZE = 8192       # Socket buffer

# --- Timing (Seconds) ---
HEARTBEAT_INTERVAL = 1.0 
HOST_TIMEOUT = 3.1       # Failure threshold (~3 missed heartbeats)
ELECTION_TIMEOUT = 3.0   # Wait time for election responses

# --- Legacy Theme Dict (kept for compatibility) ---
THEME = {
    "bg": "#121212",
    "primary": "#1DB954",
    "secondary": "#212121",
    "text": "#FFFFFF",
    "accent": "#535353"
}

def get_local_ip():
    """Dynamically finds the local IP on the LAN via Google DNS check."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"