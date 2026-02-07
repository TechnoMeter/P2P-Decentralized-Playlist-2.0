"""
ELECTION MANAGER
----------------
Handles the distributed leader election process using a variant of the Bully Algorithm.
Nodes compare metrics (Uptime + Node ID) to determine the Host.
"""

import threading
import time
from src.utils.config import ELECTION_TIMEOUT, HOST_TIMEOUT

class ElectionManager:
    """
    Manages the election state machine. 
    It handles sending election requests, processing answers, declaring victory, 
    and monitoring the health of the current leader (Host).
    """
    
    def __init__(self, node_id, state, network_node, logger_callback=None):
        self.node_id = node_id
        self.network = network_node
        self.logger = logger_callback
        self.state = state
        
        self.leader_id = None
        self.is_election_running = False
        self.received_answer = False
        
        self.init_time = time.time()
        self.last_heartbeat = self.init_time
        self.is_host = False
        
        self.lock = threading.RLock()

    def log(self, text):
        if self.logger: self.logger(f"[Election] {text}")

    def start_election(self):
        """
        Begins the election process.
        Sets internal state to 'Running' and broadcasts an ELECTION message
        to all peers with a higher Node ID to challenge them.
        """
        # Skip election if host already exists and is connected

        with self.lock:
            self.leader_id = self.state.get_host()
            self.log(self.state.peers)
            self.log(f"Starting election. My ID: {self.node_id}")
            self.is_election_running = True
            self.received_answer = False
            
        higher_nodes = [pid for pid in self.network.state.peers.keys() if pid > self.node_id]
        
        if not higher_nodes:
            self.declare_victory()
        else:
            for pid in higher_nodes:
                payload={
                    'uptime': self.state.get_uptime()
                }
                self.network.send_to_peer(pid, 'ELECTION', payload=payload)
            
            threading.Timer(ELECTION_TIMEOUT, self._check_election_results).start()

    def _check_election_results(self):
        """
        Callback triggered after the election timeout.
        If no higher-priority node has sent an ANSWER (silencing us), 
        this node declares itself the winner.
        """
        with self.lock:
            self.log("Election timeout reached.")
            if not self.received_answer and self.is_election_running:
                self.declare_victory()
            self.is_election_running = False

    def on_election_received(self, sender_id, sender_uptime):
        """
        Processes an incoming ELECTION message.
        Compares the sender's metric (Uptime + ID) against the local metric.
        If local metric is higher, sends an ANSWER to stop the sender and 
        potentially starts a new election to assert dominance.
        """
        my_metric = (self.state.get_uptime(), self.node_id)
        sender_metric = (sender_uptime, sender_id)
        self.log(f"Election received from {sender_id}. My metric: {my_metric}, Sender metric: {sender_metric}")
        
        if sender_metric < my_metric:
            self.network.send_to_peer(sender_id, 'ANSWER')
            self.log(f"Sent ANSWER to {sender_id}")
            
            if not self.is_election_running:
                self.start_election()

    def on_answer_received(self):
        """
        Handles an ANSWER message.
        Indicates a node with a higher metric is active; this node yields 
        and waits for a COORDINATOR message.
        """
        with self.lock:
            self.received_answer = True
            self.log("Higher-ID node answered. Waiting for coordinator...")

    def declare_victory(self):
        """
        Promotes this node to Host.
        Updates local state and broadcasts the COORDINATOR message to all peers.
        """
        with self.lock:
            self.is_host = True
            self.leader_id = self.node_id
            self.state.set_host(self.node_id)
            self.log("I am the new Host!")
        
        for pid in self.network.connections.keys():
            self.network.send_to_peer(pid, 'COORDINATOR', payload={'leader_id': self.node_id})

    def on_coordinator_received(self, leader_id):
        """
        Handles a COORDINATOR message.
        Updates the local knowledge of the current Host and stops any running election.
        """
        with self.lock:
            self.leader_id = leader_id
            self.state.set_host(leader_id)
            self.is_host = (leader_id == self.node_id)
            self.is_election_running = False
            self.update_heartbeat()
            self.log(f"New Host: {leader_id}")

    def on_heartbeat_received(self):
        """Wrapper to refresh the heartbeat timer when a message is received."""
        self.update_heartbeat()

    def check_for_host_failure(self):
        """
        Periodic check to ensure the Host is still responsive.
        If the heartbeat timer exceeds the threshold, a new election is triggered.
        """
        if not self.is_host and self.leader_id:
            if time.time() - self.last_heartbeat > HOST_TIMEOUT:
                self.log(f"Host {self.leader_id} timed out! Starting election...")
                self.leader_id = None
                if (not self.is_election_running):
                    self.start_election()

    def update_heartbeat(self):
        """Updates the last contact timestamp and recalculates local uptime."""
        with self.lock:
            self.last_heartbeat = time.time()
            self.state.update_uptime(int(self.last_heartbeat - self.init_time))
            self.log(f"Updated heartbeat. Uptime: {self.state.uptime} seconds")