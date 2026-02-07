"""
DATA MODELS
-----------
Simple dataclasses used for serialization across the network.
"""

from dataclasses import dataclass, field
import uuid
import time
from typing import Dict, Any, Optional

@dataclass
class Song:
    """Represents a single track in the shared playlist."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = "Unknown Title"
    artist: str = "Unknown Artist"
    file_path: str = ""
    added_by: str = ""
    timestamp: float = field(default_factory=time.time)

@dataclass
class Message:
    """
    Standard envelope for network communication.
    Includes Vector Clock for causal consistency.
    """
    sender_id: str
    sender_ip: str
    msg_type: str  # e.g., 'HELLO', 'ELECTION', 'QUEUE_SYNC'
    payload: Any = None
    vector_clock: Dict[str, int] = field(default_factory=dict)

    def __post_init__(self):
        if self.payload is None:
            self.payload = {}