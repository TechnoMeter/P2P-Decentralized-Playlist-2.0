# P2P Decentralized Playlist

A peer-to-peer collaborative music playlist application built with Python. Multiple users on the same network can discover each other, elect a host, and collaboratively manage a shared playlist queue with synchronized playback.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Technical Implementation](#technical-implementation)
- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [Working Cases](#working-cases)
- [Edge Cases & Error Handling](#edge-cases--error-handling)
- [Module Documentation](#module-documentation)
- [Configuration](#configuration)
- [Limitations & TODOs](#limitations--todos)

---

## Overview

This application implements a fully decentralized peer-to-peer music playlist system where:

- **No central server** - All nodes are equal participants
- **Automatic peer discovery** - Uses UDP broadcast to find peers on the local network
- **Democratic host election** - Implements the Bully Algorithm for leader election
- **Synchronized playback** - Only the host controls playback; listeners receive state updates
- **Causal ordering** - Uses Vector Clocks to ensure consistent message ordering across nodes

### Core Concepts

| Concept | Description |
|---------|-------------|
| **Node** | A single instance of the application running on a machine |
| **Host** | The elected leader who controls playback and sends heartbeats |
| **Listener** | Non-host nodes that receive state updates and can add songs |
| **Playlist Queue** | Shared list of songs synchronized across all nodes |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CollaborativeNode                         │
│                         (main.py)                                │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Controller Layer                       │   │
│  │  - Coordinates all subsystems                            │   │
│  │  - Handles UI callbacks                                  │   │
│  │  - Runs maintenance loop                                 │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│     ┌────────────────────────┼────────────────────────┐         │
│     │                        │                        │         │
│     ▼                        ▼                        ▼         │
│ ┌─────────┐           ┌─────────────┐          ┌───────────┐   │
│ │Discovery│           │NetworkNode  │          │  AudioEngine│  │
│ │Manager  │           │(TCP Comms)  │          │  (Pygame)  │   │
│ └─────────┘           └─────────────┘          └───────────┘   │
│     │                        │                        │         │
│     │ UDP                    │ TCP                    │         │
│     │ Broadcast              │ Messages               │ Local   │
│     │                        │                        │ Playback│
│     │                        ▼                        │         │
│     │                 ┌─────────────┐                │         │
│     │                 │StateManager │◄───────────────┘         │
│     │                 │(Shared State)│                          │
│     │                 └─────────────┘                          │
│     │                        │                                   │
│     │                        ▼                                   │
│     │                 ┌─────────────┐                           │
│     └────────────────►│  Election   │                           │
│                       │  Manager    │                           │
│                       │(Bully Algo) │                           │
│                       └─────────────┘                           │
│                              │                                   │
│                              ▼                                   │
│                       ┌─────────────┐                           │
│                       │ PlaylistUI  │                           │
│                       │ (Tkinter)   │                           │
│                       └─────────────┘                           │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
1. PEER DISCOVERY (UDP)
   Node A ──[HELLO broadcast]──► Network
                                    │
   Node B ◄─────────────────────────┘
   Node B ──[TCP Connection]──► Node A

2. LEADER ELECTION (Bully Algorithm)
   Node A ──[ELECTION]──► Higher ID Nodes
                              │
   Node B ◄───[ANSWER]────────┘  (if higher)
   Node B ──[COORDINATOR]──► All Nodes

3. PLAYLIST SYNC
   Any Node ──[QUEUE_SYNC]──► Host ──► All Peers
   Host ──[NOW_PLAYING]──► All Peers
   Host ──[PLAYBACK_SYNC]──► All Peers (position updates)

4. HEARTBEAT & FAILOVER
   Host ──[HEARTBEAT]──► All Peers (every 1s)
   If missed 3+ heartbeats → New Election
```

---

## Technical Implementation

### 1. Peer Discovery (UDP Broadcast)

**File:** `src/backend/discovery.py`

- Uses UDP broadcast on port `5000` to announce presence
- Sends `HELLO` messages containing `node_id` and `tcp_port`
- Supports `SO_REUSEPORT` for multiple instances on same machine (macOS/Linux)
- Broadcasts to both `<broadcast>` and `127.0.0.1` for local testing

```python
# Message format
Message(
    sender_id="abc123",
    sender_ip="192.168.1.100",
    msg_type="HELLO",
    payload={"tcp_port": 5001}
)
```

### 2. TCP Communication

**File:** `src/backend/network_node.py`

- Persistent TCP connections between peers on port `5001+`
- Length-prefixed message protocol (4-byte header + pickled data)
- Automatic port allocation if default port is busy
- Handles connection failures and peer disconnections

**Message Types:**

| Type | Direction | Purpose |
|------|-----------|---------|
| `HELLO` | Any → Any | Initial handshake after TCP connect |
| `WELCOME` | Host → New Peer | Confirms host identity |
| `HEARTBEAT` | Host → All | Keep-alive signal |
| `ELECTION` | Candidate → Higher IDs | Start election |
| `ANSWER` | Higher ID → Candidate | Acknowledge election |
| `COORDINATOR` | Winner → All | Announce new host |
| `QUEUE_SYNC` | Any → All | Add song to queue |
| `REMOVE_SONG` | Host → All | Remove song from queue |
| `NOW_PLAYING` | Host → All | Current playing song |
| `PLAYBACK_SYNC` | Host → All | Current playback position |
| `FULL_STATE_SYNC` | Host → New Peer | Complete state transfer |
| `REQUEST_STATE` | New Peer → Host | Request full state |

### 3. Vector Clocks (Causal Ordering)

**File:** `src/backend/state_manager.py`

Ensures consistent message ordering across distributed nodes.

**Rules:**
1. Before sending: increment own counter
2. On receive: merge clocks (take max for each node)
3. Process only if causally ready:
   - `V_msg[sender] == V_local[sender] + 1`
   - `V_msg[other] <= V_local[other]` for all others

**Example:**
```
Node A: {A:1, B:0} sends QUEUE_SYNC
Node B: {A:0, B:1} receives → merges to {A:1, B:1}
```

Messages that arrive "too early" are buffered in `pending_messages` until dependencies are satisfied.

### 4. Bully Algorithm (Leader Election)

**File:** `src/backend/bully_election.py`

Elects the node with the highest composite metric as host.

**Election Metric:** `(uptime, node_id)` - Primary: uptime seconds, Tiebreaker: node ID

**Process:**
1. Node initiates election by sending `ELECTION` to all higher-metric nodes
2. If any respond with `ANSWER`, wait for `COORDINATOR`
3. If no responses within timeout (3s), declare self as coordinator
4. Winner broadcasts `COORDINATOR` to all peers

**Failure Detection:**
- Host sends heartbeats every 1 second
- If 3+ heartbeats missed (3.1s timeout), listeners trigger new election

### 5. Audio Playback

**File:** `src/backend/audio_engine.py`

- Uses `pygame.mixer` for audio playback
- Supports MP3, WAV, OGG formats
- Features: play, stop, volume control, position tracking
- Start playback from specific offset (for sync on rejoin)

### 6. User Interface

**File:** `src/frontend/app_ui.py`, `src/frontend/styles.py`

- Built with Tkinter
- Deep blue "aero" aesthetic theme
- Features:
  - Now playing display with seek bar
  - Queue list with checkbox selection
  - Playback controls (play/pause, next, prev, shuffle, repeat)
  - Volume slider
  - System terminal/debug panel (toggle with CMD button)
  - Role indicator (HOST/LISTENER)

**Host-Only Controls:**
- Playback controls only enabled when node is host
- Queue management (remove, clear) restricted to host

---

## Features

### Implemented

- [x] Automatic peer discovery via UDP broadcast
- [x] TCP-based reliable communication
- [x] Bully algorithm leader election
- [x] Vector clock causal ordering
- [x] Shared playlist queue synchronization
- [x] Audio playback with pygame
- [x] Modern dark-themed UI
- [x] Host/Listener role management
- [x] Heartbeat-based failure detection
- [x] Automatic re-election on host failure
- [x] Add songs from local filesystem
- [x] Volume control
- [x] Debug terminal panel
- [x] Multiple instances on same machine support

### Partially Implemented (TODOs in code)

- [ ] Skip Previous (history tracking exists but not wired)
- [ ] Play/Pause toggle
- [ ] Seek functionality
- [ ] Shuffle queue
- [ ] Repeat mode
- [ ] Remove selected songs sync

---

## Installation

### Prerequisites

- Python 3.8+
- pip package manager

### Dependencies

```bash
pip install pygame
```

Or use requirements file:
```bash
pip install -r requirements.txt
```

### System Requirements

- Same local network (LAN) for peer discovery
- UDP port 5000 available for discovery
- TCP port 5001+ available for communication
- Audio output device for playback

---

## Usage

### Starting a Node

```bash
# Default (auto-generated node ID)
python main.py

# Custom node ID
python main.py my_node_id
```

### Running Multiple Instances (Testing)

Each instance automatically finds an available port:
```bash
# Terminal 1
python main.py node1

# Terminal 2
python main.py node2

# Terminal 3
python main.py node3
```

### UI Controls

| Action | Description |
|--------|-------------|
| **+ ADD TRACK** | Opens file dialog to add MP3/WAV/OGG |
| **CMD** | Toggle debug terminal panel |
| **Play/Pause** | Toggle playback (host only) |
| **⏮ ⏭** | Previous/Next track (host only) |
| **🔀** | Shuffle queue (host only) |
| **🔁** | Toggle repeat (host only) |
| **🔊 Slider** | Volume control (all nodes) |
| **Seek Bar** | Jump to position (host only) |
| **☐ Checkbox** | Select songs for removal |
| **Remove Selected** | Delete selected from queue (host only) |
| **Clear Playlist** | Remove all songs (host only) |

---

## Working Cases

### Case 1: Single Node Startup
1. Node starts and broadcasts UDP `HELLO`
2. No peers respond
3. Election timeout triggers self-declaration as host
4. UI shows "HOST (You: node_id)"
5. Can add songs and play locally

### Case 2: Peer Joins Existing Network
1. New node broadcasts `HELLO`
2. Existing nodes receive and establish TCP connections
3. Host sends `WELCOME` message
4. New node requests `FULL_STATE_SYNC`
5. Receives current playlist and now_playing
6. UI shows "LISTENER (Host: host_id)"

### Case 3: Host Failure & Re-election
1. Host node crashes/disconnects
2. Listeners miss 3+ heartbeats (>3.1s)
3. Each listener triggers election
4. Highest (uptime, node_id) wins
5. Winner broadcasts `COORDINATOR`
6. New host resumes playback control

### Case 4: Song Addition by Any Node
1. Any node (host or listener) clicks "+ ADD TRACK"
2. Selects audio file from filesystem
3. `QUEUE_SYNC` message sent to all peers
4. Song appears in all nodes' queues
5. Host auto-plays when current song ends

### Case 5: Auto-Play Queue
1. Host finishes playing current song
2. Maintenance loop detects `audio.is_busy() == False`
3. Pops next song from queue
4. Sends `NOW_PLAYING` to all peers
5. Sends `REMOVE_SONG` to sync queue
6. Starts playback

### Case 6: State Sync on Late Join
1. New node joins after songs already added
2. Connects to existing peers
3. Receives `FULL_STATE_SYNC` with:
   - Complete playlist
   - Current playing song
4. Queue synchronized immediately

---

## Edge Cases & Error Handling

### Network Edge Cases

| Scenario | Handling |
|----------|----------|
| **Port already in use** | Auto-increment from 5001 up to 5100 |
| **UDP bind failure** | Logs error, discovery disabled but TCP still works |
| **TCP connection timeout** | 3-second timeout, logs failure |
| **Peer disconnects mid-message** | Exception caught, peer removed from connections |
| **Self-connection attempt** | Ignored (node_id check) |
| **Duplicate song sync** | Checked by song ID before adding |

### Election Edge Cases

| Scenario | Handling |
|----------|----------|
| **Simultaneous elections** | Higher metric node wins, others back off |
| **No higher nodes respond** | Self-declares as coordinator after 3s |
| **Host disconnects during election** | Election proceeds normally |
| **New node joins during election** | Receives `COORDINATOR` when settled |
| **Equal uptime** | Node ID used as tiebreaker |

### State Synchronization Edge Cases

| Scenario | Handling |
|----------|----------|
| **Message arrives out of order** | Buffered in `pending_messages` |
| **Causal dependency missing** | Message held until dependency arrives |
| **Concurrent song additions** | Vector clock ensures ordering |
| **File path not found** | Logs error, skips to next song |
| **Playlist modified during sync** | Lock-protected atomic operations |

### UI Edge Cases

| Scenario | Handling |
|----------|----------|
| **Non-host tries control** | Buttons disabled, callbacks check `is_host` |
| **Rapid checkbox toggling** | Debounced state checks |
| **Empty queue** | Displays "Nothing Playing" |
| **Long song title** | Truncated by fixed-width label |
| **Debug panel overflow** | Scrollable with auto-scroll to bottom |

### Audio Edge Cases

| Scenario | Handling |
|----------|----------|
| **Invalid audio file** | Caught exception, returns `False` |
| **Pygame init failure** | Logged, audio features disabled |
| **Playback position drift** | Position synced every heartbeat interval |
| **Volume at 0** | Still plays, just silent |

---

## Module Documentation

### `main.py` - CollaborativeNode

Main controller class that orchestrates all subsystems.

**Key Methods:**
- `__init__()` - Initializes all managers and UI
- `start()` - Launches server, discovery, and maintenance loop
- `_maintenance_loop()` - Periodic tasks (heartbeat, playback sync, UI refresh)
- `on_add_song_request()` - Handles song addition from UI
- `on_peer_discovered()` - Callback when UDP discovers new peer

### `src/backend/discovery.py` - DiscoveryManager

Handles UDP-based peer discovery.

**Key Methods:**
- `start_listener(callback)` - Starts UDP listener thread
- `broadcast_presence()` - Sends HELLO to network
- `_listen_loop()` - Continuous UDP receive loop

### `src/backend/network_node.py` - NetworkNode

TCP communication backbone.

**Key Methods:**
- `start_server()` - Starts TCP listener thread
- `connect_to_peer(node_id, ip, port)` - Initiates outbound connection
- `send_to_peer(node_id, msg_type, payload)` - Sends message to specific peer
- `_process_message(msg)` - Routes incoming messages
- `_handle_logic(msg)` - Executes message-specific logic

### `src/backend/state_manager.py` - StateManager

Manages distributed state with vector clocks.

**Key Methods:**
- `increment_clock()` - Called before sending messages
- `update_clock(incoming)` - Merge received clock
- `can_process(msg)` - Checks causal ordering conditions
- `add_song(song)` - Thread-safe queue addition
- `set_host(node_id)` / `get_host()` - Host management

### `src/backend/bully_election.py` - ElectionManager

Implements Bully Algorithm for leader election.

**Key Methods:**
- `start_election()` - Initiates election process
- `declare_victory()` - Announces self as coordinator
- `on_election_received()` - Handles incoming election message
- `check_for_host_failure()` - Monitors heartbeat timeout

### `src/backend/audio_engine.py` - AudioEngine

Audio playback using pygame.

**Key Methods:**
- `play_song(path, start_time)` - Start playback
- `stop()` - Stop playback
- `get_current_pos()` - Returns position in seconds
- `set_volume(0.0-1.0)` - Adjust volume
- `is_busy()` - Check if playing

### `src/frontend/app_ui.py` - PlaylistUI

Tkinter-based user interface.

**Key Methods:**
- `update_now_playing(title, artist)` - Updates display
- `update_playlist(songs)` - Refreshes queue (diff-based)
- `set_controls_visible(is_host)` - Enable/disable host controls
- `log_message(msg)` - Add to debug terminal

### `src/utils/models.py` - Data Models

**Song:**
- `id` - UUID string
- `title` - Display name
- `artist` - Artist name
- `file_path` - Local filesystem path
- `added_by` - Node ID that added it
- `timestamp` - When added

**Message:**
- `sender_id` - Origin node
- `sender_ip` - Origin IP
- `msg_type` - Protocol message type
- `payload` - Type-specific data
- `vector_clock` - Causal ordering clock

### `src/utils/config.py` - Configuration

**Network Constants:**
- `UDP_PORT = 5000`
- `TCP_PORT = 5001`
- `BUFFER_SIZE = 8192`

**Timing Constants:**
- `HEARTBEAT_INTERVAL = 1.0s`
- `HOST_TIMEOUT = 3.1s`
- `ELECTION_TIMEOUT = 3.0s`

---

## Configuration

### Modifying Network Ports

Edit `src/utils/config.py`:
```python
UDP_PORT = 5000  # Discovery broadcast port
TCP_PORT = 5001  # Base TCP port (auto-increments if busy)
```

### Adjusting Timing

```python
HEARTBEAT_INTERVAL = 1.0  # Seconds between host heartbeats
HOST_TIMEOUT = 3.1        # Seconds before declaring host dead
ELECTION_TIMEOUT = 3.0    # Seconds to wait for election responses
```

### UI Theming

Edit `src/frontend/styles.py` to customize colors:
```python
BG_MAIN = "#000000"      # Main background
ACCENT = "#00FF99"       # Primary accent color
TEXT_MAIN = "#FFFFFF"    # Primary text
```

---

## Limitations & TODOs

### Current Limitations

1. **Local files only** - Songs must exist on local filesystem; no streaming
2. **Same LAN required** - UDP broadcast doesn't cross subnets
3. **No persistence** - Playlist lost on restart
4. **Single playlist** - No multiple rooms/channels
5. **Basic security** - No authentication or encryption

### Planned Improvements

```python
# From code TODOs:
- Implement pause/unpause in AudioEngine
- Wire up seek functionality
- Implement shuffle (random.shuffle + sync)
- Implement repeat mode
- Skip Previous using history list
- Send REMOVE_ALL sync for clear queue
- Battery-based host assignment consideration
```

### Known Issues

1. Playback position may drift slightly on listeners
2. Large audio files may cause brief UI freeze during load
3. Checkbox state resets if playlist structure changes significantly

---

## Project Structure

```
P2P-Decentralized-Playlist-2.0/
├── main.py                 # Application entry point
├── requirements.txt        # Python dependencies
├── readme.md              # This documentation
├── .gitignore             # Git ignore rules
└── src/
    ├── assets/
    │   └── music/         # Sample audio files
    │       ├── Alex Hagen - Superhero [NCS Release].mp3
    │       ├── Crumb Pit - Just The Way It Goes [NCS Release].mp3
    │       ├── MXZI, Deno - FAVELA [NCS Release].mp3
    │       └── waera - harinezumi [NCS Release].mp3
    ├── backend/
    │   ├── audio_engine.py     # Pygame audio playback
    │   ├── bully_election.py   # Leader election algorithm
    │   ├── discovery.py        # UDP peer discovery
    │   ├── network_node.py     # TCP communication
    │   └── state_manager.py    # Distributed state & vector clocks
    ├── frontend/
    │   ├── app_ui.py          # Tkinter UI implementation
    │   └── styles.py          # Theme constants
    └── utils/
        ├── config.py          # Network & timing configuration
        └── models.py          # Song & Message data classes
```

---

## License

This project is for educational purposes demonstrating distributed systems concepts including:
- Peer-to-peer networking
- Leader election algorithms
- Causal ordering with vector clocks
- Distributed state synchronization

---

## Contributing

Contributions welcome! Key areas needing work:
1. Implement TODO features (seek, shuffle, repeat)
2. Add unit tests
3. Improve error handling
4. Add persistence layer
5. Cross-subnet discovery (mDNS/Bonjour)
