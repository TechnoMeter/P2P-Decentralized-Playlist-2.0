import threading
import time
from src.utils.config import ELECTION_TIMEOUT, HOST_TIMEOUT, UPTIME_THRESHOLD

class WeightedBullyElection:
    """
    Implements the Weighted Bully Algorithm with Uptime Threshold.

    This algorithm combines username-based authority with stability preference:

    1. ROUTING: ELECTION messages sent only to higher-username peers
       (standard Bully Algorithm structure)

    2. UPTIME VETO: When receiving ELECTION, if sender has significantly
       more uptime (> UPTIME_THRESHOLD), we YIELD and let them win.
       This prevents newly joined high-username nodes from disrupting
       stable leaders.

    3. STANDARD BULLY: If uptime difference is within threshold,
       standard Bully behavior applies (higher username wins).

    Configuration:
        UPTIME_THRESHOLD (config.py): seconds difference to trigger yield
        - 30s  = stability strongly preferred
        - 60s  = balanced (default)
        - 120s = username strongly preferred

    The node_id (hash) is only used for network identification.
    Election comparison uses username + uptime veto mechanism.
    """

    def __init__(self, node_id, display_name, state, network_node, logger_callback=None):
        self.node_id = node_id          # Hash ID for network identification
        self.display_name = display_name # Username for election comparison
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
        Initiates an election using Bully Algorithm.
        Only sends ELECTION to nodes with HIGHER usernames (proper Bully).
        Only starts if no valid host exists.
        """
        with self.lock:
            # Check if there's already a valid host - skip election if so
            current_host = self.state.get_host()
            if current_host and current_host in self.network.connections:
                self.log(f"Host {current_host} already exists. Skipping election.")
                return

            self.leader_id = current_host
            self.log(f"Starting election. Username: {self.display_name}, ID: {self.node_id}")
            self.is_election_running = True
            self.received_answer = False

        # BULLY ALGORITHM: Only send to nodes with HIGHER usernames
        higher_peers = self.state.get_higher_username_peers(self.display_name)
        # Filter to only connected peers
        higher_connected = [pid for pid in higher_peers if pid in self.network.connections]

        self.log(f"Higher username peers: {higher_connected}")

        if not higher_connected:
            # No higher-username peers exist - I win!
            self.log("No higher-username peers. Declaring victory.")
            self.declare_victory()
        else:
            for pid in higher_connected:
                payload = {
                    'uptime': self.state.get_uptime(),
                    'username': self.display_name
                }
                self.network.send_to_peer(pid, 'ELECTION', payload=payload)

            # Wait for ANSWER messages
            threading.Timer(ELECTION_TIMEOUT, self._check_election_results).start()

    def _check_election_results(self):
        """Checks if any higher-weight node responded during the timeout."""
        with self.lock:
            self.log("Election timeout reached.")
            if not self.received_answer and self.is_election_running:
                self.declare_victory()
            self.is_election_running = False

    def on_election_received(self, sender_id, sender_uptime, sender_username):
        """
        Handle incoming election message with Uptime Veto mechanism.

        If sender has significantly more uptime (> UPTIME_THRESHOLD),
        we YIELD and let the more stable node win.
        Otherwise, standard Bully behavior applies.
        """
        my_uptime = self.state.get_uptime()

        self.log(f"Election from {sender_username}({sender_id}). "
                 f"Sender uptime: {sender_uptime}s, My uptime: {my_uptime}s")

        # UPTIME VETO: If sender is significantly more stable, yield
        if sender_uptime > my_uptime + UPTIME_THRESHOLD:
            self.log(f"YIELDING to {sender_username} (uptime {sender_uptime}s >> {my_uptime}s, "
                     f"difference {sender_uptime - my_uptime}s > threshold {UPTIME_THRESHOLD}s)")
            # Don't send ANSWER, don't start election - let stable node win
            return

        # Standard Bully: I have higher authority (username), respond and take over
        self.network.send_to_peer(sender_id, 'ANSWER')
        self.log(f"Sent ANSWER to {sender_username} (uptime difference within threshold)")

        # Start own election to propagate
        if not self.is_election_running:
            self.start_election()

    def on_answer_received(self):
        """Called when a higher-weight node acknowledges it is taking over."""
        with self.lock:
            self.received_answer = True
            self.log("Higher-weight node answered. Waiting for coordinator...")

    def declare_victory(self):
        """Declares self as the new Leader/Host."""
        with self.lock:
            self.is_host = True
            self.leader_id = self.node_id
            self.state.set_host(self.node_id)
            self.log("I am the new Host!")
        
        # Notify everyone
        for pid in self.network.connections.keys():
            self.network.send_to_peer(pid, 'COORDINATOR', payload={'leader_id': self.node_id})

    def on_coordinator_received(self, leader_id):
        """Updated when a new coordinator is announced."""
        with self.lock:
            self.leader_id = leader_id
            self.state.set_host(leader_id)
            self.is_host = (leader_id == self.node_id)
            self.is_election_running = False
            self.update_heartbeat()
            self.log(f"New Host: {leader_id}")

    def on_heartbeat_received(self):
        """Resets the failure detection timer."""
        self.update_heartbeat()

    def check_for_host_failure(self):
        """Continuously monitors if the current Host is alive."""
        if self.is_host:
            return  # I am the host, no need to check

        current_host = self.state.get_host()
        if not current_host:
            # No host exists - trigger election
            if not self.is_election_running:
                self.log("No host found. Starting election...")
                self.start_election()
        elif current_host != self.node_id:
            # There's a host and it's not me - check for timeout
            if time.time() - self.last_heartbeat > HOST_TIMEOUT:
                self.log(f"Host {current_host} timed out! Starting election...")
                self.state.set_host(None)
                self.leader_id = None
                if not self.is_election_running:
                    self.start_election()

    def update_heartbeat(self):
        with self.lock:
            self.last_heartbeat = time.time()
            self.state.update_uptime(int(self.last_heartbeat - self.init_time))
            self.log(f"Updated heartbeat. Uptime: {self.state.uptime} seconds")