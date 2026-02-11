# P2P Decentralized Playlist - Complete Technical Theory & Documentation

## Table of Contents
1. [Executive Summary](#1-executive-summary)
2. [System Architecture Overview](#2-system-architecture-overview)
3. [Core Distributed Systems Concepts](#3-core-distributed-systems-concepts)
4. [Component Deep Dive](#4-component-deep-dive)
5. [Communication Protocols](#5-communication-protocols)
6. [Data Structures & Models](#6-data-structures--models)
7. [Function Reference](#7-function-reference)
8. [Message Flow Diagrams](#8-message-flow-diagrams)
9. [Fault Tolerance Mechanisms](#9-fault-tolerance-mechanisms)
10. [UI Architecture](#10-ui-architecture)

---

## 1. Executive Summary

### 1.1 What is This Project?

This is a **serverless, peer-to-peer collaborative music playlist application** designed for Local Area Networks (LANs). Multiple users on the same network can:

- Discover each other automatically (no manual IP configuration)
- Elect a "Host" who controls audio playback
- Share a synchronized music queue
- Control playback in real-time (play, pause, seek, skip, shuffle, repeat)

### 1.2 Key Design Principles

| Principle | Implementation |
|-----------|----------------|
| **Serverless** | No central server; all peers are equal until election |
| **Automatic Discovery** | UDP broadcasting finds peers without configuration |
| **Leader Election** | Bully Algorithm selects a single Host for playback |
| **Causal Consistency** | Vector Clocks ensure correct message ordering |
| **Fault Tolerance** | Automatic re-election when Host fails |

### 1.3 Technology Stack

- **Language**: Python 3.8+
- **UI Framework**: Tkinter (ttk themed widgets)
- **Audio Engine**: Pygame (mixer module)
- **Serialization**: Python Pickle
- **Networking**: Raw sockets (TCP + UDP)

---

## 2. System Architecture Overview

### 2.1 High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              LOCAL AREA NETWORK                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐   │
│   │     NODE A       │     │     NODE B       │     │     NODE C       │   │
│   │   (LISTENER)     │     │     (HOST)       │     │   (LISTENER)     │   │
│   │                  │     │                  │     │                  │   │
│   │ ┌──────────────┐ │     │ ┌──────────────┐ │     │ ┌──────────────┐ │   │
│   │ │  PlaylistUI  │ │     │ │  PlaylistUI  │ │     │ │  PlaylistUI  │ │   │
│   │ └──────┬───────┘ │     │ └──────┬───────┘ │     │ └──────┬───────┘ │   │
│   │        │         │     │        │         │     │        │         │   │
│   │ ┌──────▼───────┐ │     │ ┌──────▼───────┐ │     │ ┌──────▼───────┐ │   │
│   │ │Collaborative │ │     │ │Collaborative │ │     │ │Collaborative │ │   │
│   │ │    Node      │ │     │ │    Node      │ │     │ │    Node      │ │   │
│   │ └──────┬───────┘ │     │ └──────┬───────┘ │     │ └──────┬───────┘ │   │
│   │        │         │     │        │         │     │        │         │   │
│   │ ┌──────▼───────┐ │     │ ┌──────▼───────┐ │     │ ┌──────▼───────┐ │   │
│   │ │ StateManager │ │     │ │ StateManager │ │     │ │ StateManager │ │   │
│   │ │ NetworkNode  │ │     │ │ NetworkNode  │ │     │ │ NetworkNode  │ │   │
│   │ │ Election     │ │     │ │ Election     │ │     │ │ Election     │ │   │
│   │ │ Discovery    │ │     │ │ Discovery    │ │     │ │ Discovery    │ │   │
│   │ │ AudioEngine  │ │     │ │ AudioEngine  │◄──────┤ │ AudioEngine  │ │   │
│   │ └──────────────┘ │     │ └──────────────┘ │     │ └──────────────┘ │   │
│   │                  │     │    (PLAYS AUDIO)│     │                  │   │
│   └────────┬─────────┘     └────────┬────────┘     └────────┬─────────┘   │
│            │                        │                       │             │
│            │    TCP Connections     │    TCP Connections    │             │
│            │◄───────────────────────┼───────────────────────►             │
│            │                        │                       │             │
│            │         UDP Broadcast Discovery                │             │
│            ◄────────────────────────┼───────────────────────►             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Layer Architecture

```
┌─────────────────────────────────────────────────────┐
│              PRESENTATION LAYER                      │
│  ┌─────────────────────────────────────────────┐    │
│  │           PlaylistUI (app_ui.py)            │    │
│  │   - Tkinter window management               │    │
│  │   - User input handling                     │    │
│  │   - Real-time display updates               │    │
│  └─────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────┤
│              APPLICATION LAYER                       │
│  ┌─────────────────────────────────────────────┐    │
│  │       CollaborativeNode (main.py)           │    │
│  │   - Orchestrates all subsystems             │    │
│  │   - Business logic for playback             │    │
│  │   - Event routing                           │    │
│  └─────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────┤
│              COORDINATION LAYER                      │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │
│  │ StateManager│ │  Election   │ │ AudioEngine │   │
│  │  - Playlist │ │  - Bully    │ │  - Pygame   │   │
│  │  - Clock    │ │    Algorithm│ │  - Playback │   │
│  └─────────────┘ └─────────────┘ └─────────────┘   │
├─────────────────────────────────────────────────────┤
│              NETWORK LAYER                           │
│  ┌─────────────────────┐ ┌─────────────────────┐    │
│  │   NetworkNode       │ │  DiscoveryManager   │    │
│  │   (TCP Mesh)        │ │  (UDP Broadcast)    │    │
│  └─────────────────────┘ └─────────────────────┘    │
└─────────────────────────────────────────────────────┘
```

### 2.3 File Structure

```
project_root/
│
├── main.py                    # Entry point & CollaborativeNode controller
│
└── src/
    ├── backend/
    │   ├── audio_engine.py    # Pygame audio wrapper
    │   ├── bully_election.py  # Leader election algorithm
    │   ├── discovery.py       # UDP peer discovery
    │   ├── network_node.py    # TCP communication backbone
    │   └── state_manager.py   # Distributed state & vector clocks
    │
    ├── frontend/
    │   ├── app_ui.py          # Tkinter UI implementation
    │   └── styles.py          # Color palette & fonts
    │
    ├── utils/
    │   ├── config.py          # Network constants & helper functions
    │   └── models.py          # Data classes (Song, Message)
    │
    └── assets/
        └── music/             # Default music directory
```

---

## 3. Core Distributed Systems Concepts

### 3.1 Peer-to-Peer (P2P) Architecture

#### Theory
In a P2P system, all nodes are equal participants. There is no central server that coordinates communication. Each node can act as both a client (requesting data) and a server (providing data).

#### Implementation in This Project
- **Discovery**: Nodes broadcast their presence using UDP
- **Mesh Topology**: Each node maintains direct TCP connections to all other known peers
- **Role Differentiation**: While all nodes are architecturally equal, one node is dynamically elected as "Host" to prevent audio playback conflicts

### 3.2 Leader Election: The Bully Algorithm

#### Theory
The Bully Algorithm is a distributed election algorithm that selects a coordinator (leader) among a set of processes. The process with the highest process ID (or metric) wins.

**Steps**:
1. A process initiates an election by sending ELECTION messages to all processes with higher IDs
2. If no higher process responds with ANSWER, the initiator declares itself the coordinator
3. If a higher process responds, it takes over the election
4. The winner sends COORDINATOR messages to all processes

#### Implementation Details

```
Election Flow:

    Node A (ID=5)        Node B (ID=8)        Node C (ID=3)
         │                    │                    │
         │   ELECTION         │                    │
         │──────────────────► │                    │
         │                    │                    │
         │   ANSWER           │                    │
         │◄────────────────── │                    │
         │                    │                    │
         │                    │   COORDINATOR      │
         │◄───────────────────│────────────────────│
         │                    │                    │
         │  (B becomes Host)  │                    │
```

**Code Location**: `src/backend/bully_election.py`

**Metric Used**: `(node_id, uptime)` tuple - Higher node ID wins; uptime is secondary

### 3.3 Vector Clocks for Causal Ordering

#### Theory
Vector Clocks are a mechanism to capture causality in distributed systems. Each process maintains a vector of logical clocks, one entry per process.

**Rules**:
1. Before sending, increment your own clock entry
2. Include the entire vector in the message
3. On receive, update your vector by taking the maximum of each entry
4. A message can only be processed if it satisfies causal ordering rules

#### Causal Ordering Rules
A message `m` from process `j` can be delivered at process `i` if:
- `V_m[j] = V_i[j] + 1` (this is the next expected message from `j`)
- `V_m[k] <= V_i[k]` for all `k != j` (no missing dependencies)

#### Implementation

```python
# StateManager.can_process() - Checks causal ordering
def can_process(self, msg: Message) -> bool:
    sender = msg.sender_id
    msg_clock = msg.vector_clock

    # Rule 1: Next expected message from sender
    if msg_clock.get(sender, 0) != self.vector_clock.get(sender, 0) + 1:
        return False

    # Rule 2: No missing dependencies from other senders
    for uid, count in msg_clock.items():
        if uid != sender:
            if count > self.vector_clock.get(uid, 0):
                return False
    return True
```

**Buffering**: Messages that arrive "too early" are stored in `pending_messages` and processed when their dependencies arrive.

### 3.4 Heartbeat-Based Failure Detection

#### Theory
In distributed systems, a process is considered failed if it doesn't respond within a timeout period. The Host sends periodic HEARTBEAT messages to prove it's alive.

#### Implementation
- **Heartbeat Interval**: 1.0 second (configurable in `config.py`)
- **Host Timeout**: 6.0 seconds (if no heartbeat received, Host is considered dead)
- **Action on Failure**: Remaining nodes initiate a new election

```
Heartbeat Timeline:

    HOST                      LISTENER
      │                          │
      │   HEARTBEAT              │
      │──────────────────────────►│ (t=0s)
      │                          │
      │   HEARTBEAT              │
      │──────────────────────────►│ (t=1s)
      │                          │
      │   HEARTBEAT              │
      │──────────────────────────►│ (t=2s)
      │                          │
      X (HOST CRASHES)           │
                                 │ (t=3s, 4s, 5s - no heartbeat)
                                 │
                                 │ (t=6s - TIMEOUT!)
                                 │ LISTENER starts ELECTION
```

---

## 4. Component Deep Dive

### 4.1 CollaborativeNode (main.py)

The `CollaborativeNode` class is the central controller that ties together all subsystems.

#### Responsibilities
- Initialize all subsystems (UI, Network, State, Election, Audio)
- Route user actions (play, pause, skip) to appropriate handlers
- Run the maintenance loop for heartbeats and UI updates
- Broadcast state changes to all connected peers

#### Key Attributes

| Attribute | Type | Purpose |
|-----------|------|---------|
| `node_id` | str | Unique 8-character identifier derived from name+password |
| `display_name` | str | Human-readable name for UI display |
| `tcp_port` | int | Port used for TCP connections |
| `ui` | PlaylistUI | Reference to the UI subsystem |
| `state` | StateManager | Shared state (playlist, clocks) |
| `network` | PatchedNetworkNode | TCP communication handler |
| `election` | ElectionManager | Bully algorithm implementation |
| `discovery` | DiscoveryManager | UDP broadcast handler |
| `audio` | AudioEngine | Pygame audio wrapper |
| `history` | list | Stack of previously played songs (for "Previous" button) |
| `local_is_paused` | bool | Local playback state flag |
| `current_offset` | float | Offset tracking for accurate seek positions |

#### Node ID Generation
```python
# Deterministic ID based on credentials
seed = f"{display_name}:{password}"
full_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, seed)
self.node_id = str(full_uuid)[:8]  # First 8 characters
```

This ensures the same user always gets the same ID across sessions.

### 4.2 PatchedNetworkNode (main.py)

A subclass of `NetworkNode` that adds additional message handling for fields the base class ignores.

#### Purpose
Handles `duration` and `is_playing` fields in `PLAYBACK_SYNC` messages that the original `NetworkNode` doesn't process.

```python
def _handle_logic(self, msg):
    super()._handle_logic(msg)  # Call base implementation

    if msg.msg_type == 'PLAYBACK_SYNC':
        # Extract duration (base class ignores this)
        dur = msg.payload.get('dur')
        if dur is not None:
            self.state.current_duration = dur

        # Sync playing state
        if 'is_playing' in msg.payload:
            self.state.is_playing = msg.payload['is_playing']
```

### 4.3 StateManager (state_manager.py)

Manages all shared state and implements Vector Clock logic.

#### Data Structures Maintained

```python
self.playlist: List[Song] = []              # Shared queue
self.peers: Dict[str, Dict] = {}            # Known peers: {id: {ip, port, status}}
self.vector_clock: Dict[str, int] = {}      # {node_id: counter}
self.pending_messages: List[Message] = []   # Buffered out-of-order messages
self.host_id: str = None                    # Current leader ID
self.uptime: int = 0                        # Node uptime in seconds
```

#### Thread Safety
All state modifications are protected by `threading.Lock()`:

```python
def add_song(self, song: Song):
    with self.lock:
        self.playlist.append(song)
```

### 4.4 NetworkNode (network_node.py)

The TCP communication backbone handling all peer-to-peer messaging.

#### Connection Management

```
TCP Server Architecture:

    ┌─────────────────────────────────────────┐
    │            NetworkNode                   │
    │                                          │
    │   ┌─────────────────────────────────┐   │
    │   │      _server_loop()              │   │
    │   │   (Main Accept Thread)           │   │
    │   └──────────────┬──────────────────┘   │
    │                  │                       │
    │         accept() │ (blocking)            │
    │                  │                       │
    │   ┌──────────────▼──────────────────┐   │
    │   │    _handle_client()              │   │
    │   │   (Per-Connection Thread)        │   │
    │   └─────────────────────────────────┘   │
    │                                          │
    │   connections: {node_id: socket}        │
    └─────────────────────────────────────────┘
```

#### Message Framing Protocol
TCP is a stream protocol, so message boundaries must be explicit:

```
Message Frame:
┌──────────────┬──────────────────────────┐
│ 4 bytes      │ Variable Length          │
│ Length (Big  │ Pickled Message Object   │
│ Endian)      │                          │
└──────────────┴──────────────────────────┘
```

```python
# Sending
data = pickle.dumps(msg)
header = struct.pack('>I', len(data))  # 4-byte big-endian length
self.connections[node_id].sendall(header + data)

# Receiving
header = self._recv_all(conn, 4)
msg_len = struct.unpack('>I', header)[0]
data = self._recv_all(conn, msg_len)
msg = pickle.loads(data)
```

### 4.5 DiscoveryManager (discovery.py)

Handles automatic peer discovery via UDP broadcast.

#### How UDP Discovery Works

```
UDP Discovery Sequence:

    Node A                    Network                    Node B
       │                        │                           │
       │  HELLO (UDP Broadcast) │                           │
       │───────────────────────►│◄──────────────────────────│
       │                        │   HELLO (UDP Broadcast)   │
       │                        │                           │
       │◄──────────────────────────────────────────────────►│
       │                        │                           │
       │         (Both nodes receive each other's HELLO)    │
       │                        │                           │
       │   TCP Connection       │    TCP Connection         │
       │◄──────────────────────►│◄─────────────────────────►│
       │                        │                           │
```

#### Broadcast Mechanism
```python
def broadcast_presence(self):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        msg = Message(
            sender_id=self.node_id,
            sender_ip=self.local_ip,
            msg_type='HELLO',
            payload={'tcp_port': self.tcp_port}
        )

        # Broadcast to entire subnet
        s.sendto(pickle.dumps(msg), ('<broadcast>', UDP_PORT))
        # Also localhost for multiple instances on same machine
        s.sendto(pickle.dumps(msg), ('127.0.0.1', UDP_PORT))
```

### 4.6 ElectionManager (bully_election.py)

Implements the Bully Algorithm for leader election.

#### State Machine

```
Election State Machine:

                    ┌─────────────┐
                    │   IDLE      │
                    └──────┬──────┘
                           │
            (timeout/peer join/host failure)
                           │
                    ┌──────▼──────┐
                    │  ELECTION   │───────────────────┐
                    │  RUNNING    │                   │
                    └──────┬──────┘                   │
                           │                          │
          ┌────────────────┼────────────────┐         │
          │                │                │         │
    (no answer)      (ANSWER recv)    (higher node    │
          │                │           takes over)    │
          │                │                │         │
    ┌─────▼─────┐    ┌─────▼─────┐    ┌─────▼─────┐  │
    │ DECLARE   │    │ WAIT FOR  │    │  YIELD    │  │
    │ VICTORY   │    │COORDINATOR│    │           │  │
    └─────┬─────┘    └─────┬─────┘    └─────┬─────┘  │
          │                │                │         │
          └────────────────┼────────────────┘         │
                           │                          │
                    ┌──────▼──────┐                   │
                    │   HOST or   │◄──────────────────┘
                    │  LISTENER   │
                    └─────────────┘
```

#### Election Metric Comparison
```python
# Composite metric: (node_id, uptime)
my_metric = (self.node_id, self.state.get_uptime())
sender_metric = (sender_id, sender_uptime)

# Python tuple comparison: compares element by element
# Higher node_id wins; if equal, higher uptime wins
if sender_metric < my_metric:
    self.network.send_to_peer(sender_id, 'ANSWER')
```

### 4.7 AudioEngine (audio_engine.py)

Wraps Pygame's mixer module for audio playback.

#### Pygame Mixer Limitations

1. **get_pos()**: Returns milliseconds since `play()` was called, not absolute position
2. **set_pos()**: Unreliable for many audio formats
3. **Seeking**: Implemented by stopping and restarting at offset

```python
def seek(self, time_sec, file_path):
    """Simulates seeking by restarting playback at offset."""
    self.stop()
    self.play_song(file_path, start_time=time_sec)
```

#### Offset Tracking
Because `get_pos()` resets on `play()`, the main.py tracks a `current_offset`:

```python
# When seeking
self.current_offset = seek_sec
self.audio.seek(seek_sec, resolved_path)

# When reading position
current_pos = self.audio.get_current_pos() + self.current_offset
```

---

## 5. Communication Protocols

### 5.1 Message Types Reference

| Type | Direction | Payload | Purpose |
|------|-----------|---------|---------|
| `HELLO` | UDP/TCP | `{tcp_port}` | Announce presence to network |
| `WELCOME` | TCP | `{id}` | Host acknowledges new peer |
| `ELECTION` | TCP | `{uptime}` | Initiate leader election |
| `ANSWER` | TCP | None | Acknowledge election from lower node |
| `COORDINATOR` | TCP | `{leader_id}` | Announce new leader |
| `HEARTBEAT` | TCP | None | Host liveness check |
| `REQUEST_STATE` | TCP | None | Request full state sync |
| `FULL_STATE_SYNC` | TCP | `{playlist, current_song, ...}` | Complete state transfer |
| `QUEUE_SYNC` | TCP | `{song}` | Add single song to queue |
| `REMOVE_SONG` | TCP | `{song_id}` | Remove song from queue |
| `QUEUE_CLEARED` | TCP | None | Clear entire queue |
| `NOW_PLAYING` | TCP | `{song}` | Announce current track |
| `PLAYBACK_SYNC` | TCP | `{pos, dur, is_playing}` | Sync playback position |
| `PLAYBACK_STATUS` | TCP | `{is_playing, shuffle, repeat_mode}` | Sync playback state |

### 5.2 Connection Establishment Flow

```
New Peer Joining Sequence:

    NEW_NODE                    EXISTING_HOST
        │                            │
        │   UDP: HELLO               │
        │───────────────────────────►│
        │                            │
        │   (DiscoveryManager receives, triggers connect_to_peer)
        │                            │
        │   TCP: Connect             │
        │───────────────────────────►│
        │                            │
        │   TCP: HELLO               │
        │◄───────────────────────────│
        │                            │
        │   TCP: WELCOME             │
        │◄───────────────────────────│
        │                            │
        │   TCP: REQUEST_STATE       │
        │───────────────────────────►│
        │                            │
        │   TCP: FULL_STATE_SYNC     │
        │◄───────────────────────────│
        │                            │
        │   (Playlist synchronized)   │
        │                            │
```

### 5.3 Playback Synchronization

```
Host Playback Broadcasting:

    HOST                         LISTENERS
      │                              │
      │ (maintenance_loop runs)      │
      │                              │
      │   HEARTBEAT                  │
      │─────────────────────────────►│
      │                              │
      │   PLAYBACK_SYNC              │
      │   {pos: 45.2, dur: 180.0,    │
      │    is_playing: true}         │
      │─────────────────────────────►│
      │                              │
      │ (1 second later...)          │
      │                              │
      │   HEARTBEAT                  │
      │─────────────────────────────►│
      │                              │
      │   PLAYBACK_SYNC              │
      │   {pos: 46.2, dur: 180.0,    │
      │    is_playing: true}         │
      │─────────────────────────────►│
```

### 5.4 Dead Reckoning for Listeners

Listeners don't receive audio - they estimate position locally:

```python
# In maintenance_loop for non-host nodes
if self.state.is_playing and self.state.current_duration > 0:
    self.state.current_song_pos += HEARTBEAT_INTERVAL
    # Clamp to duration
    if self.state.current_song_pos > self.state.current_duration:
        self.state.current_song_pos = self.state.current_duration
```

This provides smooth UI updates between sync messages.

---

## 6. Data Structures & Models

### 6.1 Song Model (models.py)

```python
@dataclass
class Song:
    id: str          # UUID, auto-generated
    title: str       # Track name (from filename)
    artist: str      # Default: "Unknown Artist"
    file_path: str   # Absolute or relative path to audio file
    added_by: str    # Display name of user who added
    timestamp: float # Unix timestamp when added
```

#### Song Lifecycle

```
Song Creation → Broadcast → Display → Playback → History/Removal

1. User clicks "+ ADD TRACK"
2. File dialog opens, user selects MP3
3. Song object created with UUID
4. QUEUE_SYNC broadcast to all peers
5. Song appears in all UI playlist views
6. When played, moves to "Now Playing"
7. After playback, added to history stack
```

### 6.2 Message Model (models.py)

```python
@dataclass
class Message:
    sender_id: str              # Node ID of sender
    sender_ip: str              # IP address (for reference)
    msg_type: str               # Message type (see table above)
    payload: Any                # Type-specific data (dict)
    vector_clock: Dict[str, int]  # Causal ordering metadata
```

#### Message Serialization
Messages are serialized using Python's `pickle` module:

```python
# Sending
data = pickle.dumps(msg)

# Receiving
msg = pickle.loads(data)
```

**Security Note**: Pickle can execute arbitrary code. This system is designed for trusted LANs only.

### 6.3 Peer Registry

```python
# StateManager.peers structure
self.peers: Dict[str, Dict[str, Any]] = {
    "a1b2c3d4": {
        "ip": "192.168.1.100",
        "port": 5001,
        "status": "alive"
    },
    "e5f6g7h8": {
        "ip": "192.168.1.101",
        "port": 5002,
        "status": "alive"
    }
}
```

### 6.4 Vector Clock Structure

```python
# StateManager.vector_clock structure
self.vector_clock: Dict[str, int] = {
    "a1b2c3d4": 5,   # This node has processed 5 messages from a1b2c3d4
    "e5f6g7h8": 3,   # This node has processed 3 messages from e5f6g7h8
    "i9j0k1l2": 7    # This node has processed 7 messages from i9j0k1l2
}
```

---

## 7. Function Reference

### 7.1 main.py - CollaborativeNode

#### `__init__(self, display_name, password)`
Initializes all subsystems and generates node ID.

#### `_find_available_port(self, start_port) -> int`
Scans for an open TCP port starting from config default (5001).

#### `ui_log(self, message)`
Thread-safe logging to console and UI debug terminal.

#### `on_add_song_request(self, file_path)`
Handles user adding a song via file dialog.

#### `on_skip_next(self)`
Advances to next track in queue. Host-only.

#### `on_skip_prev(self)`
Returns to previous track or restarts current. Host-only.

#### `on_play_pause(self)`
Toggles playback state. Host-only.

#### `on_seek(self, value)`
Handles seek bar changes (0-100 percentage). Host-only.

#### `on_volume_change(self, val)`
Sets audio volume (0.0-1.0).

#### `on_shuffle(self)`
Toggles shuffle mode and reorders playlist. Host-only.

#### `on_repeat(self)`
Cycles through repeat modes (Off→All→One). Host-only.

#### `on_clear_queue(self)`
Clears the entire playlist. Host-only.

#### `on_remove_song(self, song_id)`
Removes a specific song by ID. Host-only.

#### `_broadcast(self, msg_type, payload)`
Sends a message to all connected TCP peers.

#### `_broadcast_full_state(self)`
Sends complete playlist and status to all peers.

#### `_get_duration(self, file_path) -> float`
Returns song duration in seconds using Pygame.

#### `_resolve_path(self, file_path) -> str`
Robust path resolution handling cross-platform separators and relative paths.

#### `_play_song_logic(self, song, start_offset=0)`
Internal method to start playback of a song.

#### `_handle_queue_end(self)`
Resets state when playlist finishes.

#### `_refresh_ui(self)`
Periodic UI update called from maintenance loop.

#### `_maintenance_loop(self)`
Background thread for heartbeats, UI updates, and auto-next logic.

#### `_process_auto_next_song(self)`
Determines next song when audio finishes naturally.

#### `start(self)`
Starts network server, discovery, and UI main loop.

#### `on_peer_discovered(self, pid, ip, port)`
Callback when UDP discovery finds a new peer.

### 7.2 state_manager.py - StateManager

#### `increment_clock(self) -> Dict[str, int]`
Increments local clock entry before sending. Returns copy of clock.

#### `update_clock(self, incoming_clock)`
Merges incoming clock with local clock (max of each entry).

#### `can_process(self, msg) -> bool`
Checks if message satisfies causal ordering rules.

#### `update_peer(self, node_id, ip, port)`
Adds or updates peer in registry.

#### `get_peer_name(self, node_id) -> str`
Returns human-readable name for peer (backwards compatibility).

#### `add_song(self, song) -> bool`
Adds song to local playlist.

#### `update_uptime(self, seconds)`
Updates node uptime counter.

#### `get_uptime(self) -> int`
Returns current uptime in seconds.

#### `set_host(self, node_id)`
Sets the current leader ID.

#### `get_host(self) -> str`
Returns current leader ID.

#### `is_host(self, node_id) -> bool`
Checks if given node is the current host.

### 7.3 network_node.py - NetworkNode

#### `start_server(self)`
Starts background TCP server thread.

#### `_server_loop(self)`
Main accept loop for incoming connections.

#### `_recv_all(self, conn, n) -> bytes`
Receives exactly n bytes from connection.

#### `_handle_client(self, conn, addr)`
Per-connection message receive loop.

#### `connect_to_peer(self, node_id, ip, port)`
Initiates outgoing TCP connection to peer.

#### `send_to_peer(self, node_id, msg_type, payload=None)`
Sends a message to specific peer.

#### `_process_message(self, msg)`
Routes message to appropriate handler with causal ordering check.

#### `_handle_logic(self, msg)`
Processes message based on type.

#### `_check_buffer(self)`
Attempts to process buffered out-of-order messages.

### 7.4 bully_election.py - ElectionManager

#### `start_election(self)`
Initiates election by notifying higher-ID nodes.

#### `_check_election_results(self)`
Timer callback to check if election won.

#### `on_election_received(self, sender_id, sender_uptime)`
Handles incoming ELECTION message.

#### `on_answer_received(self)`
Handles ANSWER from higher-ID node.

#### `declare_victory(self)`
Declares self as new coordinator.

#### `on_coordinator_received(self, leader_id)`
Handles COORDINATOR announcement.

#### `on_heartbeat_received(self)`
Resets failure detection timer.

#### `check_for_host_failure(self)`
Monitors if current host is alive.

#### `update_heartbeat(self)`
Updates last heartbeat timestamp.

### 7.5 discovery.py - DiscoveryManager

#### `start_listener(self, on_peer_found)`
Starts UDP listening thread.

#### `_listen_loop(self, on_peer_found)`
UDP receive loop.

#### `broadcast_presence(self)`
Sends HELLO to subnet broadcast address.

#### `stop(self)`
Stops discovery listener.

### 7.6 audio_engine.py - AudioEngine

#### `play_song(self, song_path, start_time=0) -> bool`
Plays audio file, optionally from offset.

#### `get_current_pos(self) -> float`
Returns playback position in seconds (since last play()).

#### `set_volume(self, volume)`
Sets volume (0.0-1.0).

#### `is_busy(self) -> bool`
Returns True if audio is currently playing.

#### `stop(self)`
Stops playback.

#### `toggle_pause(self) -> bool`
Toggles pause state. Returns True if now paused.

#### `seek(self, time_sec, file_path)`
Seeks by restarting playback at offset.

### 7.7 app_ui.py - PlaylistUI

#### `show_notification(self, message, is_error=True)`
Shows temporary notification banner.

#### `set_controls_visible(self, is_host, host_id, host_name)`
Switches between Host and Listener layouts.

#### `update_play_pause_icon(self, is_playing)`
Updates play/pause button icon.

#### `update_progress(self, current_seconds, total_seconds)`
Updates seek bar and time labels.

#### `update_toggles(self, repeat_mode, is_shuffle)`
Updates shuffle/repeat button states.

#### `update_now_playing(self, title, artist)`
Updates currently playing track display.

#### `update_playlist(self, songs, current_song_id)`
Refreshes playlist treeview.

#### `log_message(self, message)`
Adds message to debug terminal queue.

#### `toggle_debug(self)`
Shows/hides debug panel.

#### `run(self)`
Starts Tkinter main loop.

---

## 8. Message Flow Diagrams

### 8.1 New Node Joining Network

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         NEW NODE JOINING SEQUENCE                            │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   NEW_NODE                HOST                    PEER_A                     │
│      │                     │                        │                        │
│      │ ── UDP HELLO ──────►│◄─── UDP HELLO ────────►│                        │
│      │    (broadcast)      │     (broadcast)        │                        │
│      │                     │                        │                        │
│      │◄── TCP Connect ─────│                        │                        │
│      │                     │                        │                        │
│      │◄── WELCOME ─────────│                        │                        │
│      │    (host_id)        │                        │                        │
│      │                     │                        │                        │
│      │── REQUEST_STATE ───►│                        │                        │
│      │                     │                        │                        │
│      │◄── FULL_STATE_SYNC ─│                        │                        │
│      │    (playlist, etc)  │                        │                        │
│      │                     │                        │                        │
│      │ (Synced! Shows in UI)                        │                        │
│      │                     │                        │                        │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 8.2 Song Addition Flow

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          SONG ADDITION FLOW                                  │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   USER_NODE               HOST                    PEER_A                     │
│      │                     │                        │                        │
│      │ (clicks +ADD TRACK) │                        │                        │
│      │                     │                        │                        │
│      │ (file dialog)       │                        │                        │
│      │                     │                        │                        │
│      │ (Song object created with UUID)              │                        │
│      │                     │                        │                        │
│      │── QUEUE_SYNC ──────►│── QUEUE_SYNC ─────────►│                        │
│      │   {song: {...}}     │   {song: {...}}        │                        │
│      │                     │                        │                        │
│      │ (All nodes update playlist UI)               │                        │
│      │                     │                        │                        │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 8.3 Host Failure & Re-Election

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                      HOST FAILURE & RE-ELECTION                              │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   OLD_HOST (ID=5)        NODE_A (ID=8)          NODE_B (ID=3)                │
│      │                     │                        │                        │
│      │── HEARTBEAT ───────►│── HEARTBEAT ──────────►│                        │
│      │                     │                        │                        │
│      X (CRASH!)            │                        │                        │
│                            │                        │                        │
│                   (6 sec timeout)                   │                        │
│                            │                        │                        │
│                            │── ELECTION ───────────►│                        │
│                            │   (to all lower IDs)   │                        │
│                            │                        │                        │
│                            │ (no ANSWER - A is highest)                      │
│                            │                        │                        │
│                            │── COORDINATOR ────────►│                        │
│                            │   {leader_id: 8}       │                        │
│                            │                        │                        │
│                   (NODE_A becomes new HOST)         │                        │
│                            │                        │                        │
│                            │── HEARTBEAT ──────────►│                        │
│                            │                        │                        │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 8.4 Playback Control Flow

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                        PLAYBACK CONTROL FLOW                                 │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   HOST_UI             CollaborativeNode         LISTENERS                    │
│      │                      │                        │                       │
│      │ (user clicks ▶)      │                        │                       │
│      │                      │                        │                       │
│      │──on_play_pause()────►│                        │                       │
│      │                      │                        │                       │
│      │                      │──AudioEngine.play()    │                       │
│      │                      │                        │                       │
│      │                      │──PLAYBACK_STATUS──────►│                       │
│      │                      │  {is_playing: true}    │                       │
│      │                      │                        │                       │
│      │                      │  (maintenance loop)    │                       │
│      │                      │                        │                       │
│      │                      │──PLAYBACK_SYNC────────►│                       │
│      │                      │  {pos: X, dur: Y}      │                       │
│      │                      │                        │                       │
│      │                      │                        │(update UI progress)   │
│      │                      │                        │                       │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 9. Fault Tolerance Mechanisms

### 9.1 Host Failure Detection

**Mechanism**: Heartbeat-based timeout

```python
# config.py
HEARTBEAT_INTERVAL = 1.0  # Host sends every 1 second
HOST_TIMEOUT = 6.0        # Listener declares failure after 6 seconds

# bully_election.py
def check_for_host_failure(self):
    if not self.is_host and self.leader_id:
        if time.time() - self.last_heartbeat > HOST_TIMEOUT:
            self.log(f"Host {self.leader_id} timed out!")
            self.start_election()
```

### 9.2 Connection Failure Handling

```python
# network_node.py - _handle_client()
except Exception as e:
    if self.running:
        self.log(f"Peer {peer_id} disconnected: {e}")
        # If disconnected peer was host, trigger election
        if self.state.is_host(peer_id) and self.election:
            self.election.start_election()
finally:
    if peer_id in self.connections:
        self.connections.pop(peer_id)
    conn.close()
```

### 9.3 Missing File Handling

```python
# main.py - _play_song_logic()
if not os.path.exists(resolved_path):
    self.ui_log(f"Error: File missing locally: {resolved_path}")
    self.ui.show_notification(f"Missing File: {song.title}", is_error=True)

    # Host auto-skips to next song
    if self.election.is_host:
        if len(self.state.playlist) > 0:
            next_song = self.state.playlist.pop(0)
            self._play_song_logic(next_song)
```

### 9.4 Duplicate Prevention

```python
# network_node.py - QUEUE_SYNC handling
elif m_type == 'QUEUE_SYNC':
    song = msg.payload.get('song')
    if song:
        with self.state.lock:
            # Check if song already exists
            if not any(s.id == song.id for s in self.state.playlist):
                self.state.playlist.append(song)
```

### 9.5 Out-of-Order Message Buffering

```python
# network_node.py - _process_message()
if msg.msg_type in bypass_types or self.state.can_process(msg):
    self.state.update_clock(msg.vector_clock)
    self._handle_logic(msg)
    self._check_buffer()  # Try to process buffered messages
else:
    # Message arrived too early - buffer it
    self.state.pending_messages.append(msg)
```

---

## 10. UI Architecture

### 10.1 Layout Structure

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              HEADER (BG_HEADER)                             │
│  ┌───────────────┐  ┌──────────────────────────┐  ┌─────────┐  ┌─────────┐ │
│  │ P2P PLAYLIST  │  │ ** HOST mode ** | Name   │  │+ADD TRACK│ │ CMD 💻  │ │
│  └───────────────┘  └──────────────────────────┘  └─────────┘  └─────────┘ │
├─────────────────────────────────────────────────────────────────────────────┤
│                         MIDDLE CONTAINER (BG_MAIN)                          │
│  ┌───────────────────────────────────────────────┐  ┌─────────────────────┐│
│  │              PLAYLIST PANEL                    │  │   DEBUG PANEL       ││
│  │  ┌─────────────────────────────────────────┐  │  │   (BG_TERM)         ││
│  │  │ Current Queue                           │  │  │                     ││
│  │  ├─────────────────────────────────────────┤  │  │ [14:32:05] Node...  ││
│  │  │ ☐ │ Song Title      │ Artist  │ Added   │  │  │ [14:32:06] Peer...  ││
│  │  │ ☐ │ Another Song    │ Artist  │ By Who  │  │  │ [14:32:07] Playing..││
│  │  │ ☐ │ Third Song      │ Artist  │ Name    │  │  │                     ││
│  │  └─────────────────────────────────────────┘  │  │                     ││
│  │                                                │  │                     ││
│  │  ┌───────────────┐  ┌────────────────┐        │  │                     ││
│  │  │Remove Selected│  │ Clear Playlist │        │  │                     ││
│  │  └───────────────┘  └────────────────┘        │  │                     ││
│  └───────────────────────────────────────────────┘  └─────────────────────┘│
├─────────────────────────────────────────────────────────────────────────────┤
│                           PLAYER FRAME (BG_PLAYER)                          │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  0:45  ═══════════●══════════════════════════════════════════  3:30    ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  Now Playing:         🔀   ⏮   ▶   ⏭   🔁              🔊 ═══●════   ││
│  │  Song Title                                                             ││
│  │  Artist Name                                                            ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

### 10.2 Host vs Listener Mode

**Host Mode**:
- Full playback controls visible (play, pause, skip, seek, shuffle, repeat)
- Volume slider enabled
- Toolbar buttons enabled (Remove, Clear)
- Seek bar interactive

**Listener Mode**:
- Controls hidden
- Centered "Now Playing" display
- Larger time display
- Progress shown but not interactive
- Status shows current Host's ID

### 10.3 Color Palette (styles.py)

| Constant | Hex | Usage |
|----------|-----|-------|
| `BG_MAIN` | #000000 | Main background |
| `BG_PANEL` | #111111 | Panel backgrounds |
| `BG_PLAYER` | #051024 | Player bar |
| `BG_HEADER` | #051024 | Header bar |
| `BG_TERM` | #033A53 | Debug terminal |
| `ACCENT` | #00FF99 | Primary green |
| `ACCENT_HOVER` | #00CC7A | Button hover |
| `ACCENT_DANGER` | #E81123 | Error/warning |
| `TEXT_MAIN` | #FFFFFF | Primary text |
| `TEXT_SUB` | #A0A0A0 | Secondary text |
| `TEXT_HOST` | #FF6600 | Host highlight |

### 10.4 Thread-Safe Logging

UI updates must happen on the main thread. The logging system uses a queue:

```python
class PlaylistUI:
    def __init__(self):
        self.msg_queue = queue.Queue()
        self._start_queue_listener()

    def log_message(self, message):
        # Called from any thread
        self.msg_queue.put(message)

    def _start_queue_listener(self):
        # Runs on main thread via after()
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                self.log_box.insert("end", f"{msg}\n")
        except queue.Empty:
            pass
        self.root.after(100, self._start_queue_listener)
```

---

## Appendix A: Configuration Reference

### config.py Constants

| Constant | Default | Description |
|----------|---------|-------------|
| `UDP_PORT` | 5000 | Port for UDP peer discovery |
| `TCP_PORT` | 5001 | Default port for TCP connections |
| `BUFFER_SIZE` | 8192 | Socket buffer size |
| `HEARTBEAT_INTERVAL` | 1.0 | Seconds between heartbeats |
| `HOST_TIMEOUT` | 6.0 | Seconds before host declared dead |
| `ELECTION_TIMEOUT` | 3.0 | Seconds to wait for ANSWER |

### get_local_ip() Function

```python
def get_local_ip():
    """Finds local LAN IP by connecting to external address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # Google DNS - doesn't actually connect
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"
```

---

## Appendix B: Troubleshooting Guide

### B.1 Nodes Not Discovering Each Other

**Causes**:
1. Different subnets (check IP addresses)
2. Firewall blocking UDP port 5000
3. Network blocking broadcast packets

**Solutions**:
- Ensure all devices on same WiFi/subnet
- Allow Python through firewall
- Use wired network if wireless blocks broadcasts

### B.2 "Missing File" Errors

**Cause**: Audio files are NOT transferred over network - only metadata.

**Solution**: Ensure all peers have the same files in:
- `./src/assets/music/`
- Or use identical absolute paths

### B.3 Audio Only on One Machine

**Cause**: By design - only HOST plays audio.

**Explanation**: This prevents cacophony of out-of-sync playback. Listeners see progress and can add songs, but HOST controls speakers.

### B.4 Election Never Completes

**Cause**: Network partition or timing issues.

**Solution**:
- Increase `ELECTION_TIMEOUT` in config.py
- Ensure TCP connections succeed (check firewall)

---

## Appendix C: Security Considerations

### C.1 Pickle Serialization

**Risk**: Python pickle can execute arbitrary code during deserialization.

**Mitigation**: This system is designed for **trusted LANs only**. Do not expose to untrusted networks.

### C.2 No Authentication

**Risk**: Any node can join and become Host.

**Mitigation**: The password is only used for deterministic ID generation, not authentication. Use network-level security (VPN, firewalled subnet).

### C.3 No Encryption

**Risk**: All traffic is plaintext.

**Mitigation**: For sensitive environments, use VPN or encrypted tunnel.

---

## Appendix D: Future Enhancement Ideas

1. **File Transfer**: Implement chunked file transfer for missing songs
2. **Authentication**: Add proper password verification for network join
3. **Encryption**: TLS for TCP connections
4. **Persistence**: Save playlist to disk between sessions
5. **Web UI**: Alternative React/Vue frontend
6. **Mobile App**: iOS/Android companion for adding songs
7. **Voice Chat**: Integrated voice communication
8. **Visualizations**: Audio spectrum display

---

*Document generated for P2P Decentralized Playlist v2.0*
*Last Updated: 2026*

---

## Appendix E: Vector Clocks Deep Dive with Detailed Examples

### E.1 The Problem Vector Clocks Solve

In distributed systems, events happen concurrently across different nodes. There's **no global clock** - each node has its own view of time. Vector clocks answer: *"Did event A happen before event B, or were they concurrent?"*

### E.2 How It Works

Each node maintains a **vector** (dictionary) with one counter per known node:

```
Node A's clock: {A: 5, B: 3, C: 2}
Node B's clock: {A: 4, B: 7, C: 2}
Node C's clock: {A: 4, B: 6, C: 4}
```

### E.3 The Three Rules

| Rule | When | Action |
|------|------|--------|
| **1. Increment** | Before sending a message | Increment YOUR OWN counter |
| **2. Attach** | When sending | Include entire vector in message |
| **3. Merge** | On receive | Take `max()` of each entry |

---

### E.4 Key Files and Functions

| File | Function | Purpose |
|------|----------|---------|
| `src/utils/models.py:24` | `Message.vector_clock` | Every message carries a clock |
| `src/backend/state_manager.py:32-36` | `increment_clock()` | Bumps counter before sending |
| `src/backend/state_manager.py:38-42` | `update_clock()` | Merges incoming clock |
| `src/backend/state_manager.py:44-62` | `can_process()` | Checks causal ordering |
| `src/backend/network_node.py:147-159` | `_process_message()` | Routes based on causality check |
| `src/backend/network_node.py:226-235` | `_check_buffer()` | Processes buffered messages |

---

### E.5 Detailed Example: Three Nodes Adding Songs

#### Initial State

Three nodes join the network. Each has a vector clock initialized:

```
Node A: {A: 0}
Node B: {B: 0}
Node C: {C: 0}
```

After peer discovery, clocks expand:
```
Node A: {A: 0, B: 0, C: 0}
Node B: {A: 0, B: 0, C: 0}
Node C: {A: 0, B: 0, C: 0}
```

---

#### Scenario: Node A Adds "Song1"

**Step 1: A calls `increment_clock()`** (`state_manager.py:32-36`)
```python
def increment_clock(self):
    with self.lock:
        self.vector_clock[self.node_id] = self.vector_clock.get(self.node_id, 0) + 1
        return self.vector_clock.copy()
```
Node A's clock: `{A: 1, B: 0, C: 0}`

**Step 2: A sends QUEUE_SYNC** (`network_node.py:134-145`)
```python
def send_to_peer(self, node_id, msg_type, payload=None):
    clock = self.state.vector_clock.copy()
    if msg_type in ['QUEUE_SYNC', 'FULL_STATE_SYNC', 'REMOVE_SONG']:
        clock = self.state.increment_clock()  # <-- Called here
    msg = Message(self.node_id, self.ip, msg_type, payload, clock)
```

Message sent to B and C:
```
Message {
    sender_id: "A",
    msg_type: "QUEUE_SYNC",
    payload: {song: "Song1"},
    vector_clock: {A: 1, B: 0, C: 0}
}
```

---

#### Step 3: Node B Receives the Message

**In `_process_message()`** (`network_node.py:147-159`):

```python
def _process_message(self, msg: Message):
    bypass_types = ['HELLO', 'WELCOME', 'HEARTBEAT', ...]

    if msg.msg_type in bypass_types or self.state.can_process(msg):
        self.state.update_clock(msg.vector_clock)  # Merge clocks
        self._handle_logic(msg)                     # Process message
        self._check_buffer()                        # Check buffered messages
    else:
        self.state.pending_messages.append(msg)     # Buffer for later
```

**The `can_process()` check** (`state_manager.py:44-62`):

```python
def can_process(self, msg: Message) -> bool:
    sender = msg.sender_id        # "A"
    msg_clock = msg.vector_clock  # {A: 1, B: 0, C: 0}

    # Rule 1: Is this the NEXT expected message from A?
    # V_msg[A] == V_local[A] + 1
    # 1 == 0 + 1 ✓
    if msg_clock.get(sender, 0) != self.vector_clock.get(sender, 0) + 1:
        return False

    # Rule 2: No missing dependencies from other senders
    # V_msg[B] <= V_local[B] → 0 <= 0 ✓
    # V_msg[C] <= V_local[C] → 0 <= 0 ✓
    for uid, count in msg_clock.items():
        if uid != sender:
            if count > self.vector_clock.get(uid, 0):
                return False
    return True  # Can process!
```

**After `update_clock()`** (`state_manager.py:38-42`):
```python
def update_clock(self, incoming_clock: Dict[str, int]):
    with self.lock:
        for uid, count in incoming_clock.items():
            self.vector_clock[uid] = max(self.vector_clock.get(uid, 0), count)
```

Node B's clock becomes: `{A: 1, B: 0, C: 0}`

---

### E.6 Complex Scenario: Out-of-Order Messages

Now B and C both add songs **concurrently**:

```
Timeline:
   A                    B                    C
   │                    │                    │
   │                    │ adds "Song2"       │ adds "Song3"
   │                    │ clock: {A:1,B:1,C:0}│ clock: {A:1,B:0,C:1}
   │                    │                    │
   │                    │─── QUEUE_SYNC ────►│ (arrives LATE)
   │                    │                    │
   │◄── QUEUE_SYNC ─────│                    │
   │◄──────────────────────────────────────── │
   │                    │                    │
```

**At Node A, C's message arrives BEFORE B's message:**

C's message: `{A:1, B:0, C:1}` arrives first at A
B's message: `{A:1, B:1, C:0}` arrives second at A

**Processing C's message at Node A:**
```
A's clock: {A: 1, B: 0, C: 0}
C's message clock: {A: 1, B: 0, C: 1}

can_process() check:
  - sender = "C"
  - Rule 1: V_msg[C] == V_local[C] + 1 → 1 == 0 + 1 ✓
  - Rule 2: V_msg[A] <= V_local[A] → 1 <= 1 ✓
           V_msg[B] <= V_local[B] → 0 <= 0 ✓
  - Result: CAN PROCESS ✓

A's clock after: {A: 1, B: 0, C: 1}
```

**Processing B's message at Node A:**
```
A's clock: {A: 1, B: 0, C: 1}
B's message clock: {A: 1, B: 1, C: 0}

can_process() check:
  - sender = "B"
  - Rule 1: V_msg[B] == V_local[B] + 1 → 1 == 0 + 1 ✓
  - Rule 2: V_msg[A] <= V_local[A] → 1 <= 1 ✓
           V_msg[C] <= V_local[C] → 0 <= 1 ✓
  - Result: CAN PROCESS ✓

A's clock after: {A: 1, B: 1, C: 1}
```

**Both messages processed correctly!** Order doesn't matter because they're *concurrent* events.

---

### E.7 Scenario: True Causal Dependency Violation

What if C's message depended on B's? Say C received B's Song2 and then added Song3:

```
B's clock when sending:     {A:1, B:1, C:0}
C receives B's message
C's clock after receive:    {A:1, B:1, C:0}
C increments and sends:     {A:1, B:1, C:1}
```

**Now at Node A, if C's message arrives BEFORE B's:**

```
A's clock: {A: 1, B: 0, C: 0}
C's message clock: {A: 1, B: 1, C: 1}

can_process() check:
  - sender = "C"
  - Rule 1: V_msg[C] == V_local[C] + 1 → 1 == 0 + 1 ✓
  - Rule 2: V_msg[B] <= V_local[B] → 1 <= 0 ✗ FAILS!

  Result: CANNOT PROCESS - BUFFER IT
```

The message goes to `pending_messages` (`network_node.py:159`):
```python
else:
    self.state.pending_messages.append(msg)
```

**Later, B's message arrives:**
```
A processes B's message: clock becomes {A:1, B:1, C:0}
Then _check_buffer() runs:
```

**The `_check_buffer()` function** (`network_node.py:226-235`):
```python
def _check_buffer(self):
    changed = True
    while changed:
        changed = False
        for msg in self.state.pending_messages[:]:
            if self.state.can_process(msg):      # Re-check C's message
                self.state.update_clock(msg.vector_clock)
                self._handle_logic(msg)
                self.state.pending_messages.remove(msg)
                changed = True
```

Now C's message passes:
```
A's clock: {A: 1, B: 1, C: 0}
C's message clock: {A: 1, B: 1, C: 1}

can_process() re-check:
  - Rule 1: 1 == 0 + 1 ✓
  - Rule 2: B: 1 <= 1 ✓, A: 1 <= 1 ✓
  - Result: CAN PROCESS ✓
```

---

### E.8 Visual Flow Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    VECTOR CLOCK MESSAGE FLOW                              │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   SENDER (Node A)                           RECEIVER (Node B)            │
│                                                                          │
│   1. User adds song                                                      │
│         │                                                                │
│         ▼                                                                │
│   ┌─────────────────┐                                                    │
│   │ increment_clock()│  A's clock: {A:0,B:0} → {A:1,B:0}                 │
│   └────────┬────────┘                                                    │
│            │                                                             │
│            ▼                                                             │
│   ┌─────────────────┐                                                    │
│   │ send_to_peer()  │  Message with clock {A:1,B:0}                      │
│   └────────┬────────┘                                                    │
│            │                                                             │
│            │  ─────────── TCP ───────────►  ┌─────────────────────┐     │
│            │                                │ _process_message()   │     │
│            │                                └──────────┬──────────┘     │
│            │                                           │                 │
│            │                                           ▼                 │
│            │                                ┌─────────────────────┐     │
│            │                                │   can_process()?    │     │
│            │                                └──────────┬──────────┘     │
│            │                                           │                 │
│            │                           YES ◄───────────┼───────► NO      │
│            │                            │              │          │      │
│            │                            ▼              │          ▼      │
│            │                   ┌──────────────┐       │  ┌─────────────┐│
│            │                   │update_clock()│       │  │pending_msgs ││
│            │                   │B:{A:1,B:0}   │       │  │.append(msg) ││
│            │                   └──────┬───────┘       │  └─────────────┘│
│            │                          │               │                 │
│            │                          ▼               │                 │
│            │                   ┌──────────────┐       │                 │
│            │                   │_handle_logic()│      │                 │
│            │                   │(add song)     │      │                 │
│            │                   └──────┬───────┘       │                 │
│            │                          │               │                 │
│            │                          ▼               │                 │
│            │                   ┌──────────────┐       │                 │
│            │                   │_check_buffer()│◄─────┘                 │
│            │                   │(retry pending)│                        │
│            │                   └──────────────┘                         │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

### E.9 Which Messages Use Vector Clocks?

From `network_node.py:136-138`:

```python
if msg_type in ['QUEUE_SYNC', 'FULL_STATE_SYNC', 'REMOVE_SONG']:
    clock = self.state.increment_clock()  # Only these increment
```

From `network_node.py:153`:
```python
bypass_types = ['HELLO','WELCOME', 'HEARTBEAT', 'ELECTION', 'ANSWER',
                'COORDINATOR', 'REQUEST_STATE', 'NOW_PLAYING',
                'PLAYBACK_SYNC', 'REMOVE_SONG', 'QUEUE_SYNC']
```

**Key insight**: Most messages **bypass** the causal check for real-time responsiveness (heartbeats, playback sync). Only playlist-modifying operations enforce strict ordering.

---

### E.10 Summary Table

| Concept | Implementation Location |
|---------|------------------------|
| Clock data structure | `state_manager.py:17` - `Dict[str, int]` |
| Increment before send | `state_manager.py:32-36` - `increment_clock()` |
| Merge on receive | `state_manager.py:38-42` - `update_clock()` |
| Causality check | `state_manager.py:44-62` - `can_process()` |
| Message buffering | `state_manager.py:21` - `pending_messages` |
| Buffer processing | `network_node.py:226-235` - `_check_buffer()` |
| Routing decision | `network_node.py:154-159` - process or buffer |
