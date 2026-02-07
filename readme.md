# **🎵 Decentralized P2P Collaborative Playlist**

A serverless, LAN-based collaborative jukebox application. This project allows multiple users on the same network to vote on a "Host" via a distributed election algorithm, share a synchronized music queue, and control playback in real-time.

Built with **Python**, **Tkinter** (Frutiger Aero/Vista style UI), and **Pygame**.

## **✨ Key Features**

### **🎧 Collaborative Audio**

* **Shared Queue:** Any peer can add songs to the global playlist.  
* **Synchronized State:** Playback status, seek position, shuffle, and repeat modes are synced across all nodes using Vector Clocks to ensure causal consistency.  
* **Smart Path Resolution:** Automatically resolves file paths across different machines (handling \\ vs / and common music folders).

### **🤖 Distributed Systems Architecture**

* **Serverless:** No central server required. Nodes discover each other automatically via **UDP Broadcasting**.  
* **Bully Election Algorithm (Hybrid):** A robust leader election system that selects a Host based on **Uptime** (stability) and Node ID.  
* **Fault Tolerance:** If the Host crashes or disconnects, the remaining peers automatically detect the failure and elect a new Host within seconds.  
* **TCP Mesh:** Persistent TCP connections handle state synchronization and command propagation.

### **🖥️ "Frutiger Aero" UI**

* **Graphical Login:** Simple startup dialog for identity creation.  
* **Dual Modes:**  
  * **Host Mode:** Full playback controls (Seek, Play/Pause, Skip).  
  * **Listener Mode:** Real-time visualization of the current track and queue.  
* **Debug Console:** Built-in terminal for monitoring network traffic and election states.

## **🛠️ Installation**

### **Prerequisites**

* Python 3.8 or higher.  
* A Local Area Network (LAN) (Wi-Fi or Ethernet).

### **Dependencies**

Install the required Python libraries:

pip install pygame psutil

*(Note: psutil is optional but recommended for system metrics).*

## **🚀 How to Run**

### **1\. Structure**

Ensure your directory structure looks like this (based on the imports):

project\_root/  
│  
├── main.py                \# Entry Point  
├── README.md  
│  
└── src/  
    ├── backend/  
    │   ├── audio\_engine.py  
    │   ├── bully\_election.py  
    │   ├── discovery.py  
    │   ├── network\_node.py  
    │   └── state\_manager.py  
    │  
    ├── frontend/  
    │   ├── app\_ui.py  
    │   └── styles.py  
    │  
    └── utils/  
        ├── config.py  
        └── models.py

### **2\. Start a Node**

Run the application from the project root:

python main.py

### **3\. Login**

A dialog box will appear.

* **Display Name:** Your username (visible to others).  
* **Password:** Acts as a "seed" to generate your unique Node ID. Using the same name+password on different runs will result in the same ID.

### **4\. Join the Network**

Start the application on multiple computers (or multiple terminals) on the same network. They will automatically:

1. Discover each other via UDP.  
2. Elect a Host (the node with the highest uptime/ID).  
3. Sync the playlist.

## **🧠 Architecture Deep Dive**

### **Discovery (UDP)**

Nodes broadcast HELLO packets on Port 5000 to find peers. When a peer is found, a persistent TCP connection is established on Port 5001\.

### **Consensus: The Host (Bully Algorithm)**

Only one node (the **Host**) actually plays audio through speakers. All other nodes act as remote controls.

* **Election Trigger:** Happens on startup or when the current Host stops sending heartbeats.  
* **Logic:** Nodes compare (Uptime, NodeID). The node with the highest metric bullies others into submission and becomes the Coordinator.  
* **Split-Brain Protection:** If a node receives an election message from a stronger peer while campaigning, it immediately yields.

### **Consistency (Vector Clocks)**

To prevent "ghost" songs or out-of-order commands (e.g., removing a song before it's added), the system uses **Vector Clocks**.

* Every message carries a clock signature.  
* Nodes buffer messages that arrive "too early" (i.e., if a dependency is missing) and process them only when the causal history is complete.

## **🕹️ Controls**

| Icon | Action | Host Only? |
| :---- | :---- | :---- |
| **\+ ADD TRACK** | Open file dialog to add MP3/WAV to queue. | No (Anyone) |
| ▶ / ⏸ | Toggle Play / Pause. | **Yes** |
| ⏮ / ⏭ | Skip to Previous / Next track. | **Yes** |
| 🔀 | Toggle Shuffle Mode. | **Yes** |
| 🔁 / 🔂 | Toggle Repeat (All / One / Off). | **Yes** |
| **CMD 💻** | Open/Close the Debug Terminal. | No |

## **🔧 Configuration**

You can tweak network settings in src/utils/config.py:

UDP\_PORT \= 5000          \# Discovery Port  
TCP\_PORT \= 5001          \# Data Port  
HEARTBEAT\_INTERVAL \= 1.0 \# How often the Host says "I'm alive"  
HOST\_TIMEOUT \= 3.1       \# Seconds before a Host is considered dead

## **🐛 Troubleshooting**

**1\. Nodes aren't finding each other:**

* Ensure all devices are on the same **Subnet**.  
* Check Firewall settings. Allow Python to access UDP/TCP ports 5000-5010.  
* Some university/corporate networks block UDP broadcasts.

**2\. "Missing File" Notification:**

* The system sends *commands* and *metadata*, not the actual audio files (to save bandwidth).  
* Ensure all peers have the music files in a folder named music/, assets/, or songs/ relative to the script, or use the exact same absolute paths.

**3\. Audio not playing:**

* Only the **HOST** plays audio. Check the status bar: if it says "LISTENER mode", sound is muted on your device intentionally.

## **🎵 Credits**

* **Music:** Sample tracks provided by [NoCopyrightSounds (NCS)](https://ncs.io/).

## **📜 License**

This project is open-source. Feel free to modify and distribute.