import grpc
from concurrent import futures
import time
import random
import threading
import argparse
import sys
import os

# Add the generated protos to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'generated'))

import raft_node_pb2
import raft_node_pb2_grpc

class RaftState:
    FOLLOWER = "FOLLOWER"
    CANDIDATE = "CANDIDATE"
    LEADER = "LEADER"

class RaftNode(raft_node_pb2_grpc.RaftNodeServicer):
    def __init__(self, node_id, port, peers):
        self.node_id = node_id
        self.port = port
        self.peers = peers  # {node_id: "localhost:port"}
        
        # Raft state
        self.state = RaftState.FOLLOWER
        self.current_term = 0
        self.voted_for = None
        self.log = []
        self.commit_index = 0
        self.last_applied = 0
        
        # Leader state
        self.next_index = {}
        self.match_index = {}
        
        # Timing
        self.last_heartbeat = time.time()
        self.election_timeout = random.uniform(1.5, 3.0)
        self.heartbeat_interval = 0.5
        
        # Chat state
        self.messages = {}  # {room: [messages]}
        self.message_subscribers = {}  # {room: [queues]}
        
        # Start threads
        self.running = True
        self.election_thread = threading.Thread(target=self._election_timer, daemon=True)
        self.election_thread.start()
        
        print(f"[Node {self.node_id}] Started on port {self.port}")
        print(f"[Node {self.node_id}] Peers: {self.peers}")
    
    def _election_timer(self):
        """Background thread to monitor election timeout"""
        while self.running:
            time.sleep(0.1)
            
            if self.state == RaftState.LEADER:
                # Send heartbeats
                if time.time() - self.last_heartbeat > self.heartbeat_interval:
                    self._send_heartbeats()
                    self.last_heartbeat = time.time()
            else:
                # Check election timeout
                if time.time() - self.last_heartbeat > self.election_timeout:
                    self._start_election()
    
    def _start_election(self):
        """Start a new election"""
        self.state = RaftState.CANDIDATE
        self.current_term += 1
        self.voted_for = self.node_id
        self.last_heartbeat = time.time()
        self.election_timeout = random.uniform(1.5, 3.0)
        
        print(f"[Node {self.node_id}] Starting election for term {self.current_term}")
        
        votes = 1  # Vote for self
        
        # Request votes from all peers
        for peer_id, peer_address in self.peers.items():
            if peer_id == self.node_id:
                continue
            
            try:
                channel = grpc.insecure_channel(peer_address)
                stub = raft_node_pb2_grpc.RaftNodeStub(channel)
                
                last_log_index = len(self.log) - 1
                last_log_term = self.log[-1].term if self.log else 0
                
                request = raft_node_pb2.VoteRequest(
                    term=self.current_term,
                    candidate_id=self.node_id,
                    last_log_index=last_log_index,
                    last_log_term=last_log_term
                )
                
                response = stub.RequestVote(request, timeout=0.5)
                
                if response.term > self.current_term:
                    self.current_term = response.term
                    self.state = RaftState.FOLLOWER
                    self.voted_for = None
                    return
                
                if response.vote_granted:
                    votes += 1
                    print(f"[Node {self.node_id}] Received vote from node {peer_id}")
                
                channel.close()
            except Exception as e:
                print(f"[Node {self.node_id}] Failed to get vote from {peer_id}: {e}")
        
        # Check if won election
        if votes > len(self.peers) // 2:
            self._become_leader()
    
    def _become_leader(self):
        """Transition to leader state"""
        print(f"[Node {self.node_id}] Became LEADER for term {self.current_term}")
        self.state = RaftState.LEADER
        
        # Initialize leader state
        for peer_id in self.peers:
            if peer_id != self.node_id:
                self.next_index[peer_id] = len(self.log)
                self.match_index[peer_id] = -1
        
        # Send immediate heartbeat
        self._send_heartbeats()
        self.last_heartbeat = time.time()
    
    def _send_heartbeats(self):
        """Send heartbeat to all followers"""
        for peer_id, peer_address in self.peers.items():
            if peer_id == self.node_id:
                continue
            
            threading.Thread(target=self._send_append_entries, args=(peer_id, peer_address), daemon=True).start()
    
    def _send_append_entries(self, peer_id, peer_address):
        """Send AppendEntries RPC to a peer"""
        try:
            channel = grpc.insecure_channel(peer_address)
            stub = raft_node_pb2_grpc.RaftNodeStub(channel)
            
            prev_log_index = self.next_index.get(peer_id, 0) - 1
            prev_log_term = self.log[prev_log_index].term if prev_log_index >= 0 and prev_log_index < len(self.log) else 0
            
            entries = []
            if self.next_index.get(peer_id, 0) < len(self.log):
                entries = self.log[self.next_index[peer_id]:]
            
            request = raft_node_pb2.AppendEntriesRequest(
                term=self.current_term,
                leader_id=self.node_id,
                prev_log_index=prev_log_index,
                prev_log_term=prev_log_term,
                entries=entries,
                leader_commit=self.commit_index
            )
            
            response = stub.AppendEntries(request, timeout=0.5)
            
            if response.term > self.current_term:
                self.current_term = response.term
                self.state = RaftState.FOLLOWER
                self.voted_for = None
                return
            
            if response.success:
                if entries:
                    self.match_index[peer_id] = prev_log_index + len(entries)
                    self.next_index[peer_id] = self.match_index[peer_id] + 1
            else:
                self.next_index[peer_id] = max(0, self.next_index[peer_id] - 1)
            
            channel.close()
        except Exception as e:
            pass  # Ignore timeout/connection errors
    
    def RequestVote(self, request, context):
        """Handle RequestVote RPC"""
        print(f"[Node {self.node_id}] Received vote request from {request.candidate_id} for term {request.term}")
        
        if request.term > self.current_term:
            self.current_term = request.term
            self.state = RaftState.FOLLOWER
            self.voted_for = None
        
        vote_granted = False
        
        if request.term == self.current_term:
            if self.voted_for is None or self.voted_for == request.candidate_id:
                # Check log is up-to-date
                last_log_index = len(self.log) - 1
                last_log_term = self.log[-1].term if self.log else 0
                
                log_ok = (request.last_log_term > last_log_term or 
                         (request.last_log_term == last_log_term and request.last_log_index >= last_log_index))
                
                if log_ok:
                    vote_granted = True
                    self.voted_for = request.candidate_id
                    self.last_heartbeat = time.time()
                    print(f"[Node {self.node_id}] Granted vote to {request.candidate_id}")
        
        return raft_node_pb2.VoteResponse(term=self.current_term, vote_granted=vote_granted)
    
    def AppendEntries(self, request, context):
        """Handle AppendEntries RPC"""
        if request.term > self.current_term:
            self.current_term = request.term
            self.state = RaftState.FOLLOWER
            self.voted_for = None
        
        success = False
        
        if request.term == self.current_term:
            self.state = RaftState.FOLLOWER
            self.last_heartbeat = time.time()
            
            # Log consistency check
            if request.prev_log_index == -1 or (
                request.prev_log_index < len(self.log) and 
                self.log[request.prev_log_index].term == request.prev_log_term
            ):
                success = True
                
                # Append new entries
                if request.entries:
                    insert_index = request.prev_log_index + 1
                    self.log = self.log[:insert_index] + list(request.entries)
                
                # Update commit index
                if request.leader_commit > self.commit_index:
                    self.commit_index = min(request.leader_commit, len(self.log) - 1)
                    self._apply_committed_entries()
        
        return raft_node_pb2.AppendEntriesResponse(term=self.current_term, success=success)
    
    def _apply_committed_entries(self):
        """Apply committed log entries to state machine"""
        while self.last_applied < self.commit_index:
            self.last_applied += 1
            entry = self.log[self.last_applied]
            
            if entry.command == "SEND_MESSAGE":
                import json
                data = json.loads(entry.data)
                room = data['room']
                
                if room not in self.messages:
                    self.messages[room] = []
                
                self.messages[room].append({
                    'user': data['user'],
                    'message': data['message'],
                    'timestamp': data['timestamp']
                })
    
    def SendMessage(self, request, context):
        """Handle SendMessage RPC"""
        if self.state != RaftState.LEADER:
            return raft_node_pb2.ChatMessageResponse(
                success=False,
                message="Not the leader"
            )
        
        # Create log entry
        import json
        timestamp = int(time.time() * 1000)
        data = json.dumps({
            'user': request.user,
            'message': request.message,
            'room': request.room,
            'timestamp': timestamp
        })
        
        entry = raft_node_pb2.LogEntry(
            term=self.current_term,
            command="SEND_MESSAGE",
            data=data
        )
        
        self.log.append(entry)
        
        # Wait for replication
        replicated = 1
        for _ in range(10):  # Try for 1 second
            replicated = 1
            for peer_id in self.peers:
                if peer_id != self.node_id and self.match_index.get(peer_id, -1) >= len(self.log) - 1:
                    replicated += 1
            
            if replicated > len(self.peers) // 2:
                self.commit_index = len(self.log) - 1
                self._apply_committed_entries()
                break
            
            time.sleep(0.1)
        
        return raft_node_pb2.ChatMessageResponse(
            success=True,
            message=request.message,
            user=request.user,
            room=request.room,
            timestamp=timestamp
        )
    
    def GetMessages(self, request, context):
        """Handle GetMessages RPC"""
        messages = self.messages.get(request.room, [])
        
        response_messages = []
        for msg in messages:
            response_messages.append(raft_node_pb2.ChatMessageResponse(
                success=True,
                message=msg['message'],
                user=msg['user'],
                room=request.room,
                timestamp=msg['timestamp']
            ))
        
        return raft_node_pb2.GetMessagesResponse(messages=response_messages)
    
    def StreamMessages(self, request, context):
        """Handle StreamMessages RPC"""
        import queue
        q = queue.Queue()
        
        room = request.room
        if room not in self.message_subscribers:
            self.message_subscribers[room] = []
        
        self.message_subscribers[room].append(q)
        
        try:
            while True:
                msg = q.get()
                yield msg
        except:
            if room in self.message_subscribers:
                self.message_subscribers[room].remove(q)
    
    def GetLeader(self, request, context):
        """Handle GetLeader RPC"""
        if self.state == RaftState.LEADER:
            return raft_node_pb2.GetLeaderResponse(
                leader_id=self.node_id,
                leader_address=f"localhost:{self.port}"
            )
        else:
            return raft_node_pb2.GetLeaderResponse(
                leader_id=-1,
                leader_address=""
            )

def serve(node_id, port):
    # Define cluster configuration
    peers = {
        1: "localhost:50051",
        2: "localhost:50052",
        3: "localhost:50053"
    }
    
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    raft_node = RaftNode(node_id, port, peers)
    raft_node_pb2_grpc.add_RaftNodeServicer_to_server(raft_node, server)
    
    server.add_insecure_port(f'[::]:{port}')
    server.start()
    
    print(f"Raft node {node_id} started on port {port}")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        raft_node.running = False
        server.stop(0)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Raft Node')
    parser.add_argument('--node-id', type=int, required=True, help='Node ID (1, 2, or 3)')
    parser.add_argument('--port', type=int, required=True, help='Port number')
    
    args = parser.parse_args()
    serve(args.node_id, args.port)
