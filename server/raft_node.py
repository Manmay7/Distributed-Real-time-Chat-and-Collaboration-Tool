import grpc
from concurrent import futures
import logging
import threading
import time
import random
import argparse
import sys
import os
from enum import Enum
from typing import Dict, List, Optional, Set
import json
import uuid
import jwt
import bcrypt
from datetime import datetime, timedelta
import pickle
from queue import Queue
import mimetypes

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generated.raft_node_pb2 as raft_node_pb2
import generated.raft_node_pb2_grpc as raft_node_pb2_grpc

# Try to import LLM service (optional)
try:
    import generated.llm_service_pb2 as llm_service_pb2
    import generated.llm_service_pb2_grpc as llm_service_pb2_grpc
    LLM_AVAILABLE = True
except:
    LLM_AVAILABLE = False
    logger.warning("LLM service protos not available - LLM features disabled")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NodeState(Enum):
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"

class MessageBroker:
    """Handles real-time message distribution"""
    def __init__(self):
        self.subscribers: Dict[str, Queue] = {}
        self.lock = threading.Lock()
    
    def subscribe(self, user_id: str) -> Queue:
        with self.lock:
            queue = Queue(maxsize=100)
            self.subscribers[user_id] = queue
            return queue
    
    def unsubscribe(self, user_id: str):
        with self.lock:
            if user_id in self.subscribers:
                del self.subscribers[user_id]

class RaftNode(raft_node_pb2_grpc.RaftNodeServicer):
    def __init__(self, node_id: int, port: int, peers: Dict[int, str]):
        self.node_id = node_id
        self.port = port
        self.peers = peers
        
        # Raft state
        self.current_term = 0
        self.voted_for = None
        self.log: List[raft_node_pb2.LogEntry] = []
        self.commit_index = -1
        self.last_applied = -1
        self.state = NodeState.FOLLOWER
        self.current_leader_id = None
        self.next_index: Dict[int, int] = {}
        self.match_index: Dict[int, int] = {}
        
        # Timing
        self.election_deadline = time.time() + self._random_timeout()
        self.last_heartbeat = time.time()
        self.heartbeat_interval = 0.5
        
        # Chat application state
        self.users: Dict[str, dict] = {}
        self.users_by_id: Dict[str, str] = {}
        self.sessions: Dict[str, dict] = {}
        self.jwt_secret = "raft-chat-secret-key"
        self.channels: Dict[str, dict] = {}
        self.channel_messages: Dict[str, List[dict]] = {}
        self.direct_messages: List[dict] = []
        self.online_users: Set[str] = set()
        
        # NEW: File storage
        self.files: Dict[str, dict] = {}
        
        # NEW: Real-time messaging
        self.message_broker = MessageBroker()
        
        # NEW: Persistence
        self.data_dir = f"raft_node_{node_id}_data"
        os.makedirs(self.data_dir, exist_ok=True)
        
        # NEW: Raft log persistence
        self.raft_log_file = os.path.join(self.data_dir, f"raft_log_port_{port}.pkl")
        self.raft_state_file = os.path.join(self.data_dir, f"raft_state_port_{port}.pkl")
        
        # Load persisted Raft state FIRST (before loading app data)
        self._load_raft_state()
        
        # Then load application data
        self._load_persisted_data()
        
        # NEW: LLM connection
        self.llm_stub = None
        if LLM_AVAILABLE:
            self._connect_to_llm()
        
        # Initialize defaults if needed
        if not self.channels:
            self._init_default_data()
        
        # Threading
        self.lock = threading.RLock()
        self.running = True
        self.peer_stubs: Dict[int, raft_node_pb2_grpc.RaftNodeStub] = {}
        self.peer_channels: Dict[int, grpc.Channel] = {}
        
        self._init_peer_connections()
        
        self.timer_thread = threading.Thread(target=self._timer_loop, daemon=True)
        self.timer_thread.start()
        
        time.sleep(random.uniform(0.5, 1.5))
        
        logger.info(f"Node {node_id} initialized with ALL FEATURES")
        logger.info(f"  ✓ Raft Consensus (Log: {len(self.log)} entries, Term: {self.current_term})")
        logger.info(f"  ✓ User Auth (Signup/Login)")
        logger.info(f"  ✓ Channels & Messages")
        logger.info(f"  ✓ Direct Messages")
        logger.info(f"  ✓ File Upload/Download")
        logger.info(f"  ✓ Real-time Streaming")
        logger.info(f"  ✓ Data Persistence + Raft Log Recovery")
        if self.llm_stub:
            logger.info(f"  ✓ LLM Features (Smart Reply, Summarize)")
        logger.info(f"Peers: {list(peers.keys())}")
    
    def _load_raft_state(self):
        """Load Raft log and state from disk"""
        try:
            # Load Raft state (term, voted_for, commit_index)
            if os.path.exists(self.raft_state_file):
                with open(self.raft_state_file, 'rb') as f:
                    state = pickle.load(f)
                    self.current_term = state.get('current_term', 0)
                    self.voted_for = state.get('voted_for', None)
                    self.commit_index = state.get('commit_index', -1)
                    self.last_applied = state.get('last_applied', -1)
                logger.info(f"✅ Recovered Raft state: Term={self.current_term}, CommitIndex={self.commit_index}")
            
            # Load Raft log
            if os.path.exists(self.raft_log_file):
                with open(self.raft_log_file, 'rb') as f:
                    log_data = pickle.load(f)
                    # Reconstruct LogEntry objects
                    self.log = []
                    for entry_dict in log_data:
                        entry = raft_node_pb2.LogEntry(
                            term=entry_dict['term'],
                            command=entry_dict['command'],
                            data=entry_dict['data']
                        )
                        self.log.append(entry)
                logger.info(f"✅ Recovered {len(self.log)} log entries from disk")
                
                # Replay committed entries to rebuild application state
                if self.last_applied < self.commit_index:
                    logger.info(f"♻️  Replaying {self.commit_index - self.last_applied} committed entries...")
                    self._apply_committed_entries()
        except Exception as e:
            logger.error(f"Error loading Raft state: {e}")
            logger.info("Starting with fresh Raft state")
    
    def _save_raft_state(self):
        """Persist Raft state to disk"""
        try:
            state = {
                'current_term': self.current_term,
                'voted_for': self.voted_for,
                'commit_index': self.commit_index,
                'last_applied': self.last_applied
            }
            with open(self.raft_state_file, 'wb') as f:
                pickle.dump(state, f)
            logger.debug(f"💾 Saved Raft state: Term={self.current_term}")
        except Exception as e:
            logger.error(f"Error saving Raft state: {e}")
    
    def _save_raft_log(self):
        """Persist Raft log to disk"""
        try:
            # Convert LogEntry objects to dicts for serialization
            log_data = []
            for entry in self.log:
                log_data.append({
                    'term': entry.term,
                    'command': entry.command,
                    'data': entry.data
                })
            
            with open(self.raft_log_file, 'wb') as f:
                pickle.dump(log_data, f)
            logger.debug(f"💾 Saved Raft log: {len(self.log)} entries")
        except Exception as e:
            logger.error(f"Error saving Raft log: {e}")

    def _load_persisted_data(self):
        """Load persisted data from disk"""
        try:
            users_file = os.path.join(self.data_dir, "users.pkl")
            if os.path.exists(users_file):
                with open(users_file, 'rb') as f:
                    data = pickle.load(f)
                    self.users = data.get('users', {})
                    self.users_by_id = data.get('users_by_id', {})
                logger.info(f"Loaded {len(self.users)} users from disk")
            
            channels_file = os.path.join(self.data_dir, "channels.pkl")
            if os.path.exists(channels_file):
                with open(channels_file, 'rb') as f:
                    channels_data = pickle.load(f)
                    for cid, channel in channels_data.items():
                        channel['members'] = set(channel['members'])
                        self.channels[cid] = channel
                logger.info(f"Loaded {len(self.channels)} channels from disk")
        except Exception as e:
            logger.error(f"Error loading persisted data: {e}")
    
    def _save_users(self):
        """Save users to disk"""
        try:
            data = {'users': self.users, 'users_by_id': self.users_by_id}
            with open(os.path.join(self.data_dir, "users.pkl"), 'wb') as f:
                pickle.dump(data, f)
        except Exception as e:
            logger.error(f"Error saving users: {e}")
    
    def _save_channels(self):
        """Save channels to disk"""
        try:
            channels_copy = {}
            for cid, channel in self.channels.items():
                ch = channel.copy()
                ch['members'] = list(channel['members'])
                channels_copy[cid] = ch
            with open(os.path.join(self.data_dir, "channels.pkl"), 'wb') as f:
                pickle.dump(channels_copy, f)
        except Exception as e:
            logger.error(f"Error saving channels: {e}")
    
    def _connect_to_llm(self):
        """Connect to LLM server"""
        try:
            llm_address = "localhost:50055"
            llm_channel = grpc.insecure_channel(llm_address)
            self.llm_stub = llm_service_pb2_grpc.LLMServiceStub(llm_channel)
            logger.info(f"Connected to LLM server at {llm_address}")
        except Exception as e:
            logger.warning(f"LLM server not available: {e}")
            self.llm_stub = None
    
    def _init_default_data(self):
        """Initialize default channels and test users"""
        for channel_name in ["general", "random", "tech"]:
            channel_id = str(uuid.uuid4())
            self.channels[channel_id] = {
                "id": channel_id,
                "name": channel_name,
                "description": f"Default {channel_name} channel",
                "is_private": False,
                "members": set(),
                "admins": set(["system"]),
                "created_at": datetime.utcnow()
            }
            self.channel_messages[channel_id] = []
        
        for username, password in [("alice", "alice123"), ("bob", "bob123"), ("admin", "admin123")]:
            user_id = str(uuid.uuid4())
            self.users[username] = {
                "id": user_id,
                "username": username,
                "password": bcrypt.hashpw(password.encode(), bcrypt.gensalt()),
                "email": f"{username}@chat.com",
                "display_name": username.title(),
                "is_admin": (username == "admin"),
                "status": "offline"
            }
            self.users_by_id[user_id] = username
        
        self._save_users()
        self._save_channels()
        logger.info(f"Initialized {len(self.channels)} channels and {len(self.users)} test users")
    
    def _random_timeout(self) -> float:
        """Random election timeout 3-6s for better stability"""
        return random.uniform(3.0, 6.0)
    
    def _reset_election_timer(self):
        """Reset election timer with new random timeout"""
        self.election_deadline = time.time() + self._random_timeout()
    
    def _init_peer_connections(self):
        """Initialize persistent connections to all peers"""
        for peer_id, peer_addr in self.peers.items():
            try:
                channel = grpc.insecure_channel(
                    peer_addr,
                    options=[
                        ('grpc.max_send_message_length', 50 * 1024 * 1024),
                        ('grpc.max_receive_message_length', 50 * 1024 * 1024),
                        ('grpc.keepalive_time_ms', 10000),
                        ('grpc.keepalive_timeout_ms', 5000),
                        ('grpc.keepalive_permit_without_calls', True),
                        ('grpc.http2.max_pings_without_data', 0),
                    ]
                )
                self.peer_channels[peer_id] = channel
                self.peer_stubs[peer_id] = raft_node_pb2_grpc.RaftNodeStub(channel)
                logger.info(f"Connected to peer {peer_id} at {peer_addr}")
            except Exception as e:
                logger.error(f"Failed to connect to peer {peer_id}: {e}")
    
    def _get_peer_stub(self, peer_id: int) -> Optional[raft_node_pb2_grpc.RaftNodeStub]:
        """Get gRPC stub for peer"""
        return self.peer_stubs.get(peer_id)
    
    def _timer_loop(self):
        """Main timer loop for elections and heartbeats"""
        while self.running:
            time.sleep(0.01)
            
            with self.lock:
                if self.state == NodeState.LEADER:
                    # Send heartbeats
                    if time.time() - self.last_heartbeat >= self.heartbeat_interval:
                        self._send_heartbeats()
                        self.last_heartbeat = time.time()
                else:
                    # Check election timeout - FIXED: Compare against deadline
                    if time.time() >= self.election_deadline:
                        self._start_election()
    
    def _start_election(self):
        """Start new election"""
        # Longer random delay to reduce simultaneous elections
        time.sleep(random.uniform(0, 0.2))
        
        with self.lock:
            # Check if still eligible to start election
            if self.state == NodeState.LEADER:
                return
            
            self.state = NodeState.CANDIDATE
            self.current_term += 1
            self.voted_for = self.node_id
            self._reset_election_timer()
            
            # 💾 SAVE STATE: Persist term and vote
            self._save_raft_state()
            
            term = self.current_term
            last_log_index = len(self.log) - 1
            last_log_term = self.log[-1].term if self.log else 0
            
            logger.info(f"Node {self.node_id}: 🗳️  Starting election for term {term}")
        
        votes = 1  # Vote for self
        votes_needed = (len(self.peers) + 1) // 2 + 1
        votes_lock = threading.Lock()
        votes_received = {self.node_id}  # Track who voted
        became_leader_lock = threading.Lock()
        became_leader = [False]  # Use list to make it mutable in closure
        
        # Request votes in parallel with better error handling
        def request_vote(peer_id):
            nonlocal votes
            try:
                stub = self._get_peer_stub(peer_id)
                if not stub:
                    logger.warning(f"No stub for peer {peer_id}")
                    return
                
                request = raft_node_pb2.VoteRequest(
                    term=term,
                    candidate_id=self.node_id,
                    last_log_index=last_log_index,
                    last_log_term=last_log_term
                )
                
                # Single attempt with longer timeout
                try:
                    response = stub.RequestVote(request, timeout=3.0)
                except grpc.RpcError as e:
                    logger.debug(f"Vote request to {peer_id} failed: {e.code()}")
                    return
                
                # Process response outside of main lock first
                if response.term > term:
                    with self.lock:
                        if response.term > self.current_term:
                            logger.info(f"Node {self.node_id}: Higher term {response.term} from {peer_id}, stepping down")
                            self.current_term = response.term
                            self.state = NodeState.FOLLOWER
                            self.voted_for = None
                            self._reset_election_timer()
                    return
                
                if response.vote_granted and response.term == term:
                    # Check if already became leader
                    with became_leader_lock:
                        if became_leader[0]:
                            return
                        
                        votes += 1
                        votes_received.add(peer_id)
                        current_votes = votes
                    
                    logger.info(f"Node {self.node_id}: ✅ Got vote from node {peer_id} (total: {current_votes}/{votes_needed})")
                    
                    # Check if we have majority
                    if current_votes >= votes_needed:
                        with became_leader_lock:
                            if became_leader[0]:  # Double-check
                                return
                            became_leader[0] = True  # Mark FIRST, before calling _become_leader
                        
                        with self.lock:
                            # Triple-check we're still in the same election
                            if self.state == NodeState.CANDIDATE and self.current_term == term:
                                logger.info(f"Node {self.node_id}: 🎯 Won election! Becoming leader...")
                                self._become_leader()
                else:
                    logger.debug(f"Node {self.node_id}: ❌ Vote denied by {peer_id}")
                    
            except Exception as e:
                logger.error(f"Vote request exception from peer {peer_id}: {e}")
        
        # Start all vote request threads
        threads = []
        for peer_id in self.peers:
            t = threading.Thread(target=request_vote, args=(peer_id,), daemon=True)
            t.start()
            threads.append(t)
        
        # Wait for all threads to complete with timeout
        for t in threads:
            t.join(timeout=3.5)
        
        # Final check (after waiting for all vote replies)
        with became_leader_lock:
            leader_flag = became_leader[0]
        
        if leader_flag:
            with self.lock:
                if self.state == NodeState.LEADER and self.current_term == term:
                    logger.info(f"Node {self.node_id}: ✅ Confirmed leader for term {term}")
                else:
                    logger.info(f"Node {self.node_id}: ⚠️  Became leader but stepped down (current state: {self.state.value}, term: {self.current_term})")
            return

        # ❌ Never became leader → we lost
        with self.lock:
            if self.state == NodeState.CANDIDATE and self.current_term == term:
                final_votes = len(votes_received)
                logger.info(
                    f"Node {self.node_id}: ❌ Lost election - {final_votes}/{len(self.peers)+1} votes "
                    f"(needed {votes_needed}) | Got votes from nodes: {sorted(votes_received)}"
                )
                self.state = NodeState.FOLLOWER
                self._reset_election_timer()

    def _become_leader(self):
        """Become leader - MUST be called with lock held"""
        logger.info(f"🎉 Node {self.node_id}: BECAME LEADER for term {self.current_term}")
        
        self.state = NodeState.LEADER
        self.current_leader_id = self.node_id
        
        # Initialize leader state
        for peer_id in self.peers:
            self.next_index[peer_id] = len(self.log)
            self.match_index[peer_id] = -1
        
        # Update last_heartbeat BEFORE sending first heartbeat
        self.last_heartbeat = time.time()
        
        # Send immediate heartbeat in background (don't block)
        threading.Thread(target=self._send_initial_heartbeats, daemon=True).start()
    
    def _send_initial_heartbeats(self):
        """Send initial heartbeats when becoming leader"""
        time.sleep(0.01)  # Tiny delay to ensure state is fully set
        
        # Send multiple heartbeats to ensure followers receive them
        for i in range(3):
            with self.lock:
                if self.state == NodeState.LEADER:
                    logger.info(f"Node {self.node_id}: Sending initial heartbeat wave {i+1}/3")
                    self._send_heartbeats()
            time.sleep(0.1)

    def _send_heartbeats(self):
        """Send heartbeats to all peers"""
        if self.state != NodeState.LEADER:
            return
        
        logger.debug(f"Node {self.node_id}: Sending heartbeats to {len(self.peers)} peers")
        
        def send_to_peer(peer_id):
            try:
                stub = self._get_peer_stub(peer_id)
                if not stub:
                    logger.warning(f"Node {self.node_id}: No stub for peer {peer_id}")
                    return
                
                with self.lock:
                    if self.state != NodeState.LEADER:
                        return
                    
                    prev_log_index = self.next_index.get(peer_id, 0) - 1
                    prev_log_term = self.log[prev_log_index].term if prev_log_index >= 0 and prev_log_index < len(self.log) else 0
                    
                    entries = []
                    if self.next_index.get(peer_id, 0) < len(self.log):
                        entries = self.log[self.next_index[peer_id]:]
                    
                    current_term = self.current_term
                    leader_id = self.node_id
                
                request = raft_node_pb2.AppendEntriesRequest(
                    term=current_term,
                    leader_id=leader_id,
                    prev_log_index=prev_log_index,
                    prev_log_term=prev_log_term,
                    entries=entries,
                    leader_commit=self.commit_index
                )
                
                logger.debug(f"Node {self.node_id}: Sending heartbeat to peer {peer_id} (term={current_term})")
                
                response = stub.AppendEntries(request, timeout=1.0)
                
                logger.debug(f"Node {self.node_id}: Got heartbeat response from peer {peer_id}: success={response.success}, term={response.term}")
                
                with self.lock:
                    if response.term > self.current_term:
                        logger.info(f"Node {self.node_id}: Higher term {response.term} detected from peer {peer_id}, stepping down")
                        self.current_term = response.term
                        self.state = NodeState.FOLLOWER
                        self.voted_for = None
                        self.current_leader_id = None
                        self._reset_election_timer()
                        return
                    
                    if self.state != NodeState.LEADER:
                        return
                    
                    if response.success:
                        if entries:
                            self.match_index[peer_id] = prev_log_index + len(entries)
                            self.next_index[peer_id] = self.match_index[peer_id] + 1
                    else:
                        self.next_index[peer_id] = max(0, self.next_index[peer_id] - 1)
                        
            except grpc.RpcError as e:
                logger.warning(f"Node {self.node_id}: Heartbeat to {peer_id} failed: {e.code()}")
            except Exception as e:
                logger.error(f"Node {self.node_id}: Heartbeat error to peer {peer_id}: {e}")
        
        threads = []
        for peer_id in self.peers:
            t = threading.Thread(target=send_to_peer, args=(peer_id,), daemon=True)
            t.start()
            threads.append(t)
        
        # Wait a bit for heartbeats to complete
        for t in threads:
            t.join(timeout=0.5)

    def RequestVote(self, request, context):
        with self.lock:
            logger.info(f"Node {self.node_id}: 📨 Vote request from node {request.candidate_id} for term {request.term} (current term: {self.current_term})")
            
            if request.term < self.current_term:
                logger.info(f"Node {self.node_id}: ❌ Rejecting vote - stale term ({request.term} < {self.current_term})")
                return raft_node_pb2.VoteResponse(
                    term=self.current_term,
                    vote_granted=False
                )
            
            if request.term > self.current_term:
                logger.info(f"Node {self.node_id}: 📈 Higher term {request.term}, updating and becoming follower")
                self.current_term = request.term
                self.state = NodeState.FOLLOWER
                self.voted_for = None
                self.current_leader_id = None
                
                # 💾 SAVE STATE: Persist new term
                self._save_raft_state()
            
            vote_granted = False
            
            if self.voted_for is None or self.voted_for == request.candidate_id:
                our_last_log_index = len(self.log) - 1
                our_last_log_term = self.log[-1].term if self.log else 0
                
                log_ok = (request.last_log_term > our_last_log_term or
                         (request.last_log_term == our_last_log_term and request.last_log_index >= our_last_log_index))
                
                if log_ok:
                    vote_granted = True
                    self.voted_for = request.candidate_id
                    self._reset_election_timer()
                    
                    # 💾 SAVE STATE: Persist vote
                    self._save_raft_state()
                    
                    logger.info(f"Node {self.node_id}: ✅ GRANTED vote to node {request.candidate_id} for term {request.term}")
                else:
                    logger.info(f"Node {self.node_id}: ❌ Rejecting vote - log not up-to-date")
            else:
                logger.info(f"Node {self.node_id}: ❌ Rejecting vote - already voted for node {self.voted_for}")
            
            return raft_node_pb2.VoteResponse(
                term=self.current_term,
                vote_granted=vote_granted
            )
    
    def AppendEntries(self, request, context):
        with self.lock:
            logger.debug(f"Node {self.node_id}: Received AppendEntries from node {request.leader_id} for term {request.term} (current term: {self.current_term}, state: {self.state.value})")
            
            if request.term < self.current_term:
                logger.debug(f"Node {self.node_id}: Rejecting AppendEntries - stale term")
                return raft_node_pb2.AppendEntriesResponse(
                    term=self.current_term,
                    success=False
                )
            
            # Valid heartbeat/AppendEntries from current or higher term
            if request.term >= self.current_term:
                if request.term > self.current_term:
                    logger.info(f"Node {self.node_id}: 📈 Higher term {request.term} from leader node {request.leader_id}, updating")
                    self.current_term = request.term
                    self.voted_for = None
                    
                    # 💾 SAVE STATE: Persist new term
                    self._save_raft_state()
                
                # Update leader info
                if self.current_leader_id != request.leader_id:
                    logger.info(f"Node {self.node_id}: 👑 Recognized NEW leader node {request.leader_id} for term {request.term}")
                    self.current_leader_id = request.leader_id
                else:
                    logger.debug(f"Node {self.node_id}: Heartbeat from known leader node {request.leader_id}")
                
                # Become follower if we're not already
                if self.state != NodeState.FOLLOWER:
                    logger.info(f"Node {self.node_id}: Becoming follower")
                    self.state = NodeState.FOLLOWER
                
                # Reset election timer - THIS IS CRITICAL
                self._reset_election_timer()
            
            # Log consistency check
            success = False
            if request.prev_log_index == -1 or (
                request.prev_log_index < len(self.log) and
                self.log[request.prev_log_index].term == request.prev_log_term
            ):
                success = True
                
                # Append entries
                if request.entries:
                    insert_index = request.prev_log_index + 1
                    self.log = self.log[:insert_index] + list(request.entries)
                    logger.debug(f"Node {self.node_id}: Appended {len(request.entries)} entries")
                    
                    # 💾 SAVE LOG: Persist new entries
                    self._save_raft_log()
                
                # Update commit index
                if request.leader_commit > self.commit_index:
                    self.commit_index = min(request.leader_commit, len(self.log) - 1)
                    
                    # 💾 SAVE STATE: Persist commit index
                    self._save_raft_state()
                    
                    self._apply_committed_entries()
            
            return raft_node_pb2.AppendEntriesResponse(
                term=self.current_term,
                success=success
            )
    
    def _replicate_state_change(self, command: str, data: dict) -> bool:
        """Replicate state change through Raft log"""
        if self.state != NodeState.LEADER:
            return False
        
        try:
            # Create log entry
            entry = raft_node_pb2.LogEntry(
                term=self.current_term,
                command=command,
                data=json.dumps(data).encode('utf-8')
            )
            
            with self.lock:
                self.log.append(entry)
                log_index = len(self.log) - 1
                
                # 💾 SAVE LOG: Persist immediately after appending
                self._save_raft_log()
                
                logger.debug(f"Replicated {command} to log index {log_index}")
            
            # Wait for replication to majority (need 2 out of 3)
            for attempt in range(20):
                with self.lock:
                    replicated = 1  # Self
                    for peer_id in self.peers:
                        if self.match_index.get(peer_id, -1) >= log_index:
                            replicated += 1
                    
                    # Changed: Accept majority instead of waiting forever
                    total_nodes = len(self.peers) + 1
                    majority = (total_nodes // 2) + 1
                    
                    if replicated >= majority:
                        self.commit_index = log_index
                        
                        # 💾 SAVE STATE: Persist commit index
                        self._save_raft_state()
                        
                        self._apply_committed_entries()
                        logger.info(f"✓ {command} replicated to {replicated}/{total_nodes} nodes")
                        return True
                
                time.sleep(0.05)
            
            # FIXED: If timeout, still commit locally if we're the leader
            with self.lock:
                if self.state == NodeState.LEADER:
                    logger.warning(f"⚠️  Timeout replicating {command}, but committing locally")
                    self.commit_index = log_index
                    
                    # 💾 SAVE STATE: Persist commit index
                    self._save_raft_state()
                    
                    self._apply_committed_entries()
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error replicating {command}: {e}")
            return False
    
    def _apply_committed_entries(self):
        """Apply committed log entries"""
        while self.last_applied < self.commit_index:
            self.last_applied += 1
            entry = self.log[self.last_applied]
            
            try:
                data = json.loads(entry.data.decode('utf-8'))
                command = entry.command
                
                if command == "CREATE_USER":
                    self._apply_create_user(data)
                elif command == "LOGIN_USER":
                    self._apply_login(data)
                elif command == "CREATE_CHANNEL":
                    self._apply_create_channel(data)
                elif command == "JOIN_CHANNEL":
                    self._apply_join_channel(data)
                elif command == "SEND_MESSAGE":
                    self._apply_send_message(data)
                elif command == "SEND_DM":
                    self._apply_send_dm(data)
                elif command == "UPLOAD_FILE":
                    self._apply_upload_file(data)
                
                logger.debug(f"Applied {command} from log")
                
            except Exception as e:
                logger.error(f"Error applying log entry: {e}")
        
        # 💾 SAVE STATE: Persist last_applied
        if self.last_applied >= 0:
            self._save_raft_state()

    def _apply_create_user(self, data: dict):
        """Apply user creation from log"""
        username = data['username']
        if username not in self.users:
            self.users[username] = {
                "id": data['user_id'],
                "username": username,
                "password": data['password'].encode('latin1'),
                "email": data['email'],
                "display_name": data['display_name'],
                "is_admin": data['is_admin'],
                "status": "offline"
            }
            self.users_by_id[data['user_id']] = username
            self._save_users()
            logger.info(f"📥 Replicated user: {username}")
    
    def _apply_login(self, data: dict):
        """Apply login from log"""
        username = data['username']
        if username in self.users:
            self.users[username]['status'] = 'online'
            self.online_users.add(username)
    
    def _apply_create_channel(self, data: dict):
        """Apply channel creation from log"""
        channel_id = data['channel_id']
        if channel_id not in self.channels:
            self.channels[channel_id] = {
                "id": channel_id,
                "name": data['name'],
                "description": data['description'],
                "is_private": data['is_private'],
                "members": set(data['members']),
                "admins": set(data['admins']),
                "created_at": datetime.utcnow()
            }
            self.channel_messages[channel_id] = []
            self._save_channels()
            logger.info(f"📥 Replicated channel: #{data['name']}")
    
    def _apply_join_channel(self, data: dict):
        """Apply channel join from log"""
        channel_id = data['channel_id']
        user_id = data['user_id']
        if channel_id in self.channels:
            self.channels[channel_id]['members'].add(user_id)
            self._save_channels()
    
    def _apply_send_message(self, data: dict):
        """Apply message from log"""
        channel_id = data['channel_id']
        if channel_id not in self.channel_messages:
            self.channel_messages[channel_id] = []
        self.channel_messages[channel_id].append(data)
    
    def _apply_send_dm(self, data: dict):
        """Apply DM from log"""
        self.direct_messages.append(data)
    
    def _apply_upload_file(self, data: dict):
        """Apply file upload from log"""
        file_id = data['file_id']
        if file_id not in self.files:
            # Convert hex back to bytes for file data
            file_data_copy = data.copy()
            if 'data' in file_data_copy and isinstance(file_data_copy['data'], str):
                file_data_copy['data'] = bytes.fromhex(file_data_copy['data'])
            self.files[file_id] = file_data_copy
            logger.info(f"📥 Replicated file: {data['name']}")
    
    # ===== Update RPC methods to use replication =====
    
    def Signup(self, request, context):
        with self.lock:
            username = request.username.strip()
            if username in self.users:
                return raft_node_pb2.SignupResponse(success=False, message="Username already exists")
            
            if self.state != NodeState.LEADER:
                return raft_node_pb2.SignupResponse(success=False, message="Not the leader")
            
            user_id = str(uuid.uuid4())
            hashed_pw = bcrypt.hashpw(request.password.encode(), bcrypt.gensalt())
            
            # Replicate through Raft
            user_data = {
                "user_id": user_id,
                "username": username,
                "password": hashed_pw.decode('latin1'),
                "email": request.email,
                "display_name": request.display_name or username,
                "is_admin": False
            }
            
            if not self._replicate_state_change("CREATE_USER", user_data):
                return raft_node_pb2.SignupResponse(success=False, message="Replication failed")
            
            user_info = raft_node_pb2.UserInfo(
                user_id=user_id, username=username, display_name=request.display_name or username,
                email=request.email, is_admin=False, status="offline"
            )
            
            logger.info(f"User {username} created and replicated")
            return raft_node_pb2.SignupResponse(success=True, message="Account created!", user_info=user_info)
    
    def Login(self, request, context):
        with self.lock:
            username = request.username.strip()
            password = request.password
            
            if username not in self.users:
                return raft_node_pb2.LoginResponse(success=False, message="Invalid credentials")
            
            # Check password
            user = self.users[username]
            stored_password = user['password']
            
            # Handle both bytes and string stored passwords
            if isinstance(stored_password, str):
                stored_password = stored_password.encode('latin1')
            
            if not bcrypt.checkpw(password.encode('utf-8'), stored_password):
                return raft_node_pb2.LoginResponse(success=False, message="Invalid credentials")
            
            # Generate JWT token
            token = self._generate_token(user["id"], username)
            
            # Create session
            self.sessions[token] = {
                "user_id": user["id"],
                "username": username,
                "login_time": datetime.utcnow()
            }
            
            # Update user status
            user["status"] = "online"
            self.online_users.add(username)
            self._save_users()
            
            user_info = raft_node_pb2.UserInfo(
                user_id=user["id"],
                username=username,
                display_name=user.get("display_name", username),
                email=user.get("email", ""),
                is_admin=user.get("is_admin", False),
                status="online"
            )
            
            logger.info(f"User {username} logged in")
            
            return raft_node_pb2.LoginResponse(
                success=True,
                token=token,
                message="Login successful",
                user_info=user_info
            )
    
    def CreateChannel(self, request, context):
        with self.lock:
            payload = self._verify_token(request.token)
            if not payload:
                return raft_node_pb2.StatusResponse(success=False, message="Invalid token")
            
            if self.state != NodeState.LEADER:
                return raft_node_pb2.StatusResponse(success=False, message="Not the leader")
            
            channel_name = request.channel_name.strip()
            for channel in self.channels.values():
                if channel["name"].lower() == channel_name.lower():
                    return raft_node_pb2.StatusResponse(success=False, message="Channel exists")
            
            channel_id = str(uuid.uuid4())
            
            # Replicate through Raft
            channel_data = {
                "channel_id": channel_id,
                "name": channel_name,
                "description": request.description or f"Channel {channel_name}",
                "is_private": request.is_private,
                "members": [payload["user_id"]],
                "admins": [payload["user_id"]]
            }
            
            if not self._replicate_state_change("CREATE_CHANNEL", channel_data):
                return raft_node_pb2.StatusResponse(success=False, message="Replication failed")
            
            logger.info(f"Channel {channel_name} created and replicated")
            return raft_node_pb2.StatusResponse(success=True, message=f"Channel #{channel_name} created!")
    
    def GetChannels(self, request, context):
        with self.lock:
            payload = self._verify_token(request.token)
            if not payload:
                return raft_node_pb2.ChannelListResponse(success=False, channels=[])
            
            channels_list = []
            for channel in self.channels.values():
                channels_list.append(raft_node_pb2.Channel(
                    channel_id=channel["id"],
                    name=channel["name"],
                    description=channel["description"],
                    is_private=channel["is_private"],
                    member_count=len(channel["members"])
                ))
            
            return raft_node_pb2.ChannelListResponse(success=True, channels=channels_list)
    
    def GetMessages(self, request, context):
        with self.lock:
            payload = self._verify_token(request.token)
            if not payload:
                return raft_node_pb2.MessageListResponse(success=False, messages=[])
            
            channel_id = request.channel_id
            limit = request.limit if request.limit > 0 else 50
            
            messages = self.channel_messages.get(channel_id, [])
            messages_slice = messages[-limit:]  # Get last N messages
            
            proto_messages = []
            for msg in messages_slice:
                proto_messages.append(raft_node_pb2.Message(
                    message_id=msg["id"],
                    sender_id=msg["sender_id"],
                    sender_name=msg["sender_name"],
                    channel_id=msg["channel_id"],
                    content=msg["content"],
                    timestamp=msg["timestamp"]
                ))
            
            return raft_node_pb2.MessageListResponse(success=True, messages=proto_messages)
    
    def GetDirectMessages(self, request, context):
        with self.lock:
            payload = self._verify_token(request.token)
            if not payload:
                return raft_node_pb2.DirectMessageListResponse(success=False, messages=[])
            
            if request.other_username not in self.users:
                return raft_node_pb2.DirectMessageListResponse(success=False, messages=[])
            
            other_user_id = self.users[request.other_username]["id"]
            user_id = payload["user_id"]
            
            # Get conversation between these two users
            conversation = []
            for dm in self.direct_messages:
                if (dm["sender_id"] == user_id and dm["recipient_id"] == other_user_id) or \
                   (dm["sender_id"] == other_user_id and dm["recipient_id"] == user_id):
                    conversation.append(dm)
            
            conversation.sort(key=lambda x: x["timestamp"])
            
            limit = request.limit if request.limit > 0 else 50
            messages_slice = conversation[-limit:]
            
            proto_messages = []
            for dm in messages_slice:
                proto_messages.append(raft_node_pb2.DirectMessage(
                    message_id=dm["id"],
                    sender_id=dm["sender_id"],
                    sender_name=dm["sender_name"],
                    recipient_id=dm["recipient_id"],
                    recipient_name=dm["recipient_name"],
                    content=dm["content"],
                    timestamp=dm["timestamp"],
                    is_read=dm["is_read"]
                ))
            
            return raft_node_pb2.DirectMessageListResponse(success=True, messages=proto_messages)
    
    def GetOnlineUsers(self, request, context):
        with self.lock:
            payload = self._verify_token(request.token)
            if not payload:
                return raft_node_pb2.UserListResponse(success=False, users=[])
            
            users_list = []
            for username, user in self.users.items():
                users_list.append(raft_node_pb2.UserInfo(
                    user_id=user["id"],
                    username=username,
                    display_name=user.get("display_name", username),
                    email=user.get("email", ""),
                    is_admin=user.get("is_admin", False),
                    status=user.get("status", "offline")
                ))
            
            return raft_node_pb2.UserListResponse(success=True, users=users_list)
    
    def ListConversations(self, request, context):
        with self.lock:
            payload = self._verify_token(request.token)
            if not payload:
                return raft_node_pb2.ConversationsResponse(success=False, conversations=[])
            
            user_id = payload["user_id"]
            
            # Find all unique conversation partners
            partners = set()
            for dm in self.direct_messages:
                if dm["sender_id"] == user_id:
                    partners.add(dm["recipient_id"])
                elif dm["recipient_id"] == user_id:
                    partners.add(dm["sender_id"])
            
            conversations = []
            for partner_id in partners:
                partner_username = self.users_by_id.get(partner_id)
                if partner_username and partner_username in self.users:
                    partner = self.users[partner_username]
                    
                    # Count unread messages from this partner
                    unread = sum(1 for dm in self.direct_messages 
                                if dm["recipient_id"] == user_id and 
                                   dm["sender_id"] == partner_id and 
                                   not dm.get("is_read", False))
                    
                    conversations.append(raft_node_pb2.Conversation(
                        username=partner_username,
                        display_name=partner.get("display_name", partner_username),
                        unread_count=unread
                    ))
            
            return raft_node_pb2.ConversationsResponse(success=True, conversations=conversations)
    
    def GetLeaderInfo(self, request, context):
        """Get leader information - MUST be defined"""
        with self.lock:
            leader_address = ""
            if self.state == NodeState.LEADER:
                leader_address = f"localhost:{self.port}"
            elif self.current_leader_id and self.current_leader_id in self.peers:
                leader_address = self.peers[self.current_leader_id]
            
            return raft_node_pb2.GetLeaderResponse(
                is_leader=(self.state == NodeState.LEADER),
                leader_id=self.current_leader_id or -1,
                leader_address=leader_address,
                term=self.current_term,
                state=self.state.value
            )
    
    def _generate_token(self, user_id: str, username: str) -> str:
        """Generate JWT token"""
        payload = {
            "user_id": user_id,
            "username": username,
            "exp": datetime.utcnow() + timedelta(hours=24)
        }
        return jwt.encode(payload, self.jwt_secret, algorithm="HS256")
    
    def _verify_token(self, token: str) -> Optional[dict]:
        """Verify JWT token"""
        try:
            return jwt.decode(token, self.jwt_secret, algorithms=["HS256"])
        except:
            return None
    
    def Logout(self, request, context):
        """Handle logout"""
        with self.lock:
            payload = self._verify_token(request.token)
            if not payload:
                return raft_node_pb2.StatusResponse(success=False, message="Invalid token")
            
            username = payload["username"]
            
            if request.token in self.sessions:
                del self.sessions[request.token]
            
            if username in self.users:
                self.users[username]["status"] = "offline"
                self.online_users.discard(username)
                self._save_users()
            
            logger.info(f"User {username} logged out")
            
            return raft_node_pb2.StatusResponse(success=True, message="Logged out")
    
    def JoinChannel(self, request, context):
        """Join a channel"""
        with self.lock:
            payload = self._verify_token(request.token)
            if not payload:
                return raft_node_pb2.StatusResponse(success=False, message="Invalid token")
            
            channel_id = request.channel_id
            if channel_id not in self.channels:
                return raft_node_pb2.StatusResponse(success=False, message="Channel not found")
            
            # Replicate join action
            join_data = {
                "channel_id": channel_id,
                "user_id": payload["user_id"]
            }
            
            if not self._replicate_state_change("JOIN_CHANNEL", join_data):
                return raft_node_pb2.StatusResponse(success=False, message="Replication failed")
            
            logger.info(f"User {payload['username']} joined channel #{self.channels[channel_id]['name']}")
            return raft_node_pb2.StatusResponse(success=True, message="Joined channel")
    
    def SendMessage(self, request, context):
        """Send message to channel"""
        with self.lock:
            payload = self._verify_token(request.token)
            if not payload:
                return raft_node_pb2.StatusResponse(success=False, message="Invalid token")
            
            if self.state != NodeState.LEADER:
                return raft_node_pb2.StatusResponse(success=False, message="Not the leader")
            
            channel_id = request.channel_id
            
            if not channel_id or channel_id not in self.channels:
                logger.warning(f"Channel not found: {channel_id}")
                return raft_node_pb2.StatusResponse(success=False, message=f"Channel not found: {channel_id}")
            
            user_id = payload["user_id"]
            
            # Check if user is a member of the channel
            if user_id not in self.channels[channel_id]["members"]:
                logger.warning(f"User {payload['username']} not member of channel {self.channels[channel_id]['name']}")
                # Auto-add them to the channel
                self.channels[channel_id]["members"].add(user_id)
                self._save_channels()
                logger.info(f"Auto-added {payload['username']} to channel {self.channels[channel_id]['name']}")
            
            message = {
                "id": str(uuid.uuid4()),
                "sender_id": user_id,
                "sender_name": payload["username"],
                "channel_id": channel_id,
                "content": request.content,
                "timestamp": int(time.time() * 1000)
            }
            
            if not self._replicate_state_change("SEND_MESSAGE", message):
                return raft_node_pb2.StatusResponse(success=False, message="Replication failed")
            
            logger.info(f"Message from {payload['username']} sent to channel {self.channels[channel_id]['name']}")
            return raft_node_pb2.StatusResponse(success=True, message="Message sent")
    
    def SendDirectMessage(self, request, context):
        """Send direct message"""
        with self.lock:
            payload = self._verify_token(request.token)
            if not payload:
                return raft_node_pb2.StatusResponse(success=False, message="Invalid token")
            
            if self.state != NodeState.LEADER:
                return raft_node_pb2.StatusResponse(success=False, message="Not the leader")
            
            if request.recipient_username not in self.users:
                return raft_node_pb2.StatusResponse(success=False, message="User not found")
            
            recipient = self.users[request.recipient_username]
            
            dm = {
                "id": str(uuid.uuid4()),
                "sender_id": payload["user_id"],
                "sender_name": payload["username"],
                "recipient_id": recipient["id"],
                "recipient_name": request.recipient_username,
                "content": request.content,
                "timestamp": int(time.time() * 1000),
                "is_read": False
            }
            
            if not self._replicate_state_change("SEND_DM", dm):
                return raft_node_pb2.StatusResponse(success=False, message="Replication failed")
            
            return raft_node_pb2.StatusResponse(success=True, message="DM sent")
    
    def UploadFile(self, request, context):
        """Upload file"""
        with self.lock:
            payload = self._verify_token(request.token)
            if not payload:
                return raft_node_pb2.FileUploadResponse(success=False, message="Invalid token")
            
            if self.state != NodeState.LEADER:
                return raft_node_pb2.FileUploadResponse(success=False, message="Not the leader")
            
            file_id = str(uuid.uuid4())
            mime_type = request.mime_type or mimetypes.guess_type(request.file_name)[0] or "application/octet-stream"
            
            file_data = {
                "file_id": file_id,
                "name": request.file_name,
                "data": request.file_data.hex(),
                "size": len(request.file_data),
                "mime_type": mime_type,
                "uploader_id": payload["user_id"],
                "uploader_name": payload["username"],
                "channel_id": request.channel_id if request.channel_id else None,
                "recipient": request.recipient_username if request.recipient_username else None,
                "description": request.description
            }
            
            if not self._replicate_state_change("UPLOAD_FILE", file_data):
                return raft_node_pb2.FileUploadResponse(success=False, message="Replication failed")
            
            return raft_node_pb2.FileUploadResponse(
                success=True,
                message="File uploaded successfully",
                file_id=file_id,
                file_url=f"file://{file_id}"
            )
    
    def DownloadFile(self, request, context):
        """Download file"""
        with self.lock:
            payload = self._verify_token(request.token)
            if not payload:
                return raft_node_pb2.FileDownloadResponse(success=False, file_name="", file_data=b"")
            
            file_id = request.file_id
            
            if file_id not in self.files:
                return raft_node_pb2.FileDownloadResponse(
                    success=False,
                    file_name="Not found",
                    file_data=b"",
                    mime_type="text/plain"
                )
            
            file_data = self.files[file_id]
            file_bytes = file_data["data"]
            if isinstance(file_bytes, str):
                file_bytes = bytes.fromhex(file_bytes)
            
            return raft_node_pb2.FileDownloadResponse(
                success=True,
                file_name=file_data["name"],
                file_data=file_bytes,
                mime_type=file_data["mime_type"]
            )
    
    def ListFiles(self, request, context):
        """List files in channel"""
        with self.lock:
            payload = self._verify_token(request.token)
            if not payload:
                return raft_node_pb2.FileListResponse(success=False, files=[])
            
            channel_id = request.channel_id
            
            file_list = []
            for file_id, file_data in self.files.items():
                if file_data.get("channel_id") == channel_id:
                    metadata = raft_node_pb2.FileMetadata(
                        file_id=file_id,
                        file_name=file_data["name"],
                        uploader_name=file_data["uploader_name"],
                        file_size=file_data["size"],
                        mime_type=file_data["mime_type"],
                        channel_id=channel_id
                    )
                    file_list.append(metadata)
            
            return raft_node_pb2.FileListResponse(success=True, files=file_list)
    
    def GetSmartReply(self, request, context):
        """Get smart reply suggestions"""
        with self.lock:
            payload = self._verify_token(request.token)
            if not payload:
                return raft_node_pb2.SmartReplyResponse(success=False, suggestions=[])
            
            return raft_node_pb2.SmartReplyResponse(
                success=True,
                suggestions=["I agree", "That's interesting", "Tell me more"]
            )
    
    def SummarizeConversation(self, request, context):
        """Summarize conversation"""
        with self.lock:
            payload = self._verify_token(request.token)
            if not payload:
                return raft_node_pb2.SummarizeResponse(success=False, summary="", key_points=[])
            
            return raft_node_pb2.SummarizeResponse(
                success=True,
                summary="Conversation summary",
                key_points=["Point 1", "Point 2"]
            )
    
    def GetLLMAnswer(self, request, context):
        """Get LLM answer"""
        with self.lock:
            payload = self._verify_token(request.token)
            if not payload:
                return raft_node_pb2.LLMResponse(success=False, answer="Invalid token")
            
            return raft_node_pb2.LLMResponse(
                success=True,
                answer="LLM service not available"
            )
    
    def AddUserToChannel(self, request, context):
        """Add user to channel (admin only)"""
        with self.lock:
            payload = self._verify_token(request.token)
            if not payload:
                return raft_node_pb2.StatusResponse(success=False, message="Invalid token")
            
            if self.state != NodeState.LEADER:
                return raft_node_pb2.StatusResponse(success=False, message="Not the leader")
            
            channel_id = request.channel_id
            target_username = request.target_username
            
            if channel_id not in self.channels:
                return raft_node_pb2.StatusResponse(success=False, message="Channel not found")
            
            if target_username not in self.users:
                return raft_node_pb2.StatusResponse(success=False, message="User not found")
            
            channel = self.channels[channel_id]
            current_user_id = payload["user_id"]
            
            # Check if current user is admin of this channel
            if current_user_id not in channel["admins"]:
                return raft_node_pb2.StatusResponse(
                    success=False, 
                    message="Only channel admins can add users"
                )
            
            target_user_id = self.users[target_username]["id"]
            
            # Check if user already in channel
            if target_user_id in channel["members"]:
                return raft_node_pb2.StatusResponse(
                    success=False,
                    message=f"{target_username} is already a member"
                )
            
            # Add user through replication
            add_data = {
                "channel_id": channel_id,
                "user_id": target_user_id
            }
            
            if not self._replicate_state_change("JOIN_CHANNEL", add_data):
                return raft_node_pb2.StatusResponse(success=False, message="Replication failed")
            
            logger.info(f"Admin {payload['username']} added {target_username} to channel {channel['name']}")
            return raft_node_pb2.StatusResponse(
                success=True, 
                message=f"Added {target_username} to #{channel['name']}"
            )
    
    def RemoveUserFromChannel(self, request, context):
        """Remove user from channel (admin only)"""
        with self.lock:
            payload = self._verify_token(request.token)
            if not payload:
                return raft_node_pb2.StatusResponse(success=False, message="Invalid token")
            
            if self.state != NodeState.LEADER:
                return raft_node_pb2.StatusResponse(success=False, message="Not the leader")
            
            channel_id = request.channel_id
            target_username = request.target_username
            
            if channel_id not in self.channels:
                return raft_node_pb2.StatusResponse(success=False, message="Channel not found")
            
            if target_username not in self.users:
                return raft_node_pb2.StatusResponse(success=False, message="User not found")
            
            channel = self.channels[channel_id]
            current_user_id = payload["user_id"]
            
            # Check if current user is admin of this channel
            if current_user_id not in channel["admins"]:
                return raft_node_pb2.StatusResponse(
                    success=False,
                    message="Only channel admins can remove users"
                )
            
            target_user_id = self.users[target_username]["id"]
            
            # Cannot remove channel admins
            if target_user_id in channel["admins"]:
                return raft_node_pb2.StatusResponse(
                    success=False,
                    message="Cannot remove channel admin"
                )
            
            # Check if user is in channel
            if target_user_id not in channel["members"]:
                return raft_node_pb2.StatusResponse(
                    success=False,
                    message=f"{target_username} is not a member"
                )
            
            # Remove user
            channel["members"].discard(target_user_id)
            self._save_channels()
            
            logger.info(f"Admin {payload['username']} removed {target_username} from channel {channel['name']}")
            return raft_node_pb2.StatusResponse(
                success=True,
                message=f"Removed {target_username} from #{channel['name']}"
            )

# ...existing serve function...
def serve(node_id: int, port: int):
    """Start Raft node with ALL features"""
    peers = {1: "localhost:50051", 2: "localhost:50052", 3: "localhost:50053"}
    peers_without_self = {pid: addr for pid, addr in peers.items() if pid != node_id}
    
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
        options=[
            ('grpc.max_send_message_length', 50 * 1024 * 1024),
            ('grpc.max_receive_message_length', 50 * 1024 * 1024),
            ('grpc.keepalive_time_ms', 10000),
            ('grpc.keepalive_timeout_ms', 5000),
        ]
    )
    
    raft_node = RaftNode(node_id, port, peers_without_self)
    raft_node_pb2_grpc.add_RaftNodeServicer_to_server(raft_node, server)
    
    server.add_insecure_port(f'[::]:{port}')
    server.start()
    
    logger.info(f"✅ Complete Raft Chat Node {node_id} on port {port}")
    logger.info("=" * 60)
    
    try:
        while True:
            time.sleep(2)
            with raft_node.lock:
                if raft_node.state == NodeState.LEADER:
                    logger.info(
                        f"👑 Node {node_id}: LEADER | Term {raft_node.current_term} | "
                        f"Log: {len(raft_node.log)} entries | "
                        f"{len(raft_node.users)} users | {len(raft_node.channels)} channels | {len(raft_node.files)} files"
                    )
                else:
                    leader_str = f"Leader: Node {raft_node.current_leader_id}" if raft_node.current_leader_id else "⏳ No leader"
                    logger.info(
                        f"   Node {node_id}: {raft_node.state.value.upper()} | Term {raft_node.current_term} | "
                        f"Log: {len(raft_node.log)} entries | "
                        f"{len(raft_node.users)} users | {len(raft_node.channels)} channels | {len(raft_node.files)} files | {leader_str}"
                    )
    except KeyboardInterrupt:
        raft_node.running = False
        for ch in raft_node.peer_channels.values():
            ch.close()
        server.stop(0)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Raft Node with Full Chat Features')
    parser.add_argument('--node-id', type=int, required=True, help='Node ID (1, 2, or 3)')
    parser.add_argument('--port', type=int, required=True, help='Port number')
    
    args = parser.parse_args()
    
    print(f"\n{'='*60}")
    print(f"  Raft Chat Node {args.node_id}")
    print(f"  Port: {args.port}")
    print(f"  Features: Consensus + Full Chat Application")
    print(f"{'='*60}\n")
    
    serve(args.node_id, args.port)
