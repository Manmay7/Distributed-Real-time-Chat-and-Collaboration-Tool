# client/chat_client.py
import grpc
import sys
import os
import threading
import time
from datetime import datetime
import getpass
from typing import Optional
import cmd
import logging
from collections import deque
import hashlib

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generated.raft_node_pb2 as raft_node_pb2
import generated.raft_node_pb2_grpc as raft_node_pb2_grpc

# Add logger at the top of the file
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

class ChatClient(cmd.Cmd):
    intro = """
    ╔══════════════════════════════════════════════╗
    ║     Distributed Chat & Collaboration Tool    ║
    ║         Raft Consensus + Real-time Chat      ║
    ╚══════════════════════════════════════════════╝
    
    Commands: 'signup' | 'login <username>' | 'help'
    Test users: alice/alice123, bob/bob123, charlie/charlie123
    """
    prompt = '(chat) > '
    
    def __init__(self, server_address: str = "localhost:50051"):
        super().__init__()
        self.server_address = server_address
        self.channel = None
        self.stub = None
        self.token = None
        self.username = None
        self.current_channel = None
        self.current_channel_name = None
        self.running = True
        self.dm_mode = False
        self.dm_partner = None
        
        # Raft cluster configuration
        self.cluster_nodes = [
            "localhost:50051",
            "localhost:50052", 
            "localhost:50053"
        ]
        
        self.last_smart_replies = []
        self.last_context_suggestions = []
        
        # NEW: Message deduplication with longer window
        self.pending_messages = deque(maxlen=100)
        self.send_lock = threading.Lock()
        self.last_send_time = {}  # Track last send time per content hash
        
        self._connect_to_raft_leader()
    
    def _connect_to_raft_leader(self):
        """Find and connect to Raft leader"""
        print("🔍 Discovering Raft leader...")
        
        for attempt in range(5):
            for node_addr in self.cluster_nodes:
                try:
                    # Longer timeout for initial connection (5 seconds)
                    channel = grpc.insecure_channel(
                        node_addr,
                        options=[
                            ('grpc.max_connection_idle_ms', 30000),
                            ('grpc.max_connection_age_ms', 60000),
                        ]
                    )
                    stub = raft_node_pb2_grpc.RaftNodeStub(channel)
                    
                    # Increase timeout to 5 seconds
                    response = stub.GetLeaderInfo(raft_node_pb2.GetLeaderRequest(), timeout=5.0)
                    
                    if response.is_leader:
                        print(f"✓ Found leader at {node_addr} (Node {response.leader_id}, Term {response.term})")
                        self.channel = channel
                        self.stub = stub
                        self.server_address = node_addr
                        return True
                    elif response.leader_address and response.leader_id > 0:
                        print(f"→ Node {node_addr} reports leader at {response.leader_address}")
                        
                        # Try to connect to the reported leader with longer timeout
                        try:
                            leader_channel = grpc.insecure_channel(
                                response.leader_address,
                                options=[
                                    ('grpc.max_connection_idle_ms', 30000),
                                    ('grpc.max_connection_age_ms', 60000),
                                ]
                            )
                            leader_stub = raft_node_pb2_grpc.RaftNodeStub(leader_channel)
                            
                            # Verify with 5 second timeout
                            verify = leader_stub.GetLeaderInfo(raft_node_pb2.GetLeaderRequest(), timeout=5.0)
                            
                            if verify.is_leader:
                                print(f"✓ Connected to leader at {response.leader_address}")
                                self.channel = leader_channel
                                self.stub = leader_stub
                                self.server_address = response.leader_address
                                channel.close()
                                return True
                            else:
                                print(f"  Leader changed, retrying...")
                                leader_channel.close()
                        except grpc.RpcError as e:
                            print(f"  Could not reach reported leader ({e.code()}), trying next node...")
                        except Exception as e:
                            print(f"  Error connecting to reported leader: {str(e)[:50]}")
                    else:
                        print(f"  Node {node_addr}: {response.state} (waiting for leader election)")
                    
                    channel.close()
                    
                except grpc.RpcError as e:
                    if e.code() != grpc.StatusCode.UNAVAILABLE:
                        print(f"  Node {node_addr}: {e.code()}")
                except Exception as e:
                    # Silently skip unreachable nodes
                    pass
            
            if attempt < 4:
                print(f"⚠️  No leader found, waiting 3s before retry {attempt+1}/5...")
                time.sleep(3)
        
        print("\n❌ Could not find Raft leader")
        print("   Make sure all 3 Raft nodes are running:")
        print("   python server/raft_node.py --node-id 1 --port 50051")
        print("   python server/raft_node.py --node-id 2 --port 50052")
        print("   python server/raft_node.py --node-id 3 --port 50053")
        print("\n   Nodes need 3-6 seconds to elect a leader after startup.")
        sys.exit(1)
    
    def _reconnect_to_leader(self) -> bool:
        """Reconnect to current Raft leader"""
        print("\n⚠️  Connection lost. Finding new leader...")
        
        for attempt in range(3):
            for node_addr in self.cluster_nodes:
                try:
                    test_channel = grpc.insecure_channel(
                        node_addr,
                        options=[
                            ('grpc.max_connection_idle_ms', 30000),
                        ]
                    )
                    test_stub = raft_node_pb2_grpc.RaftNodeStub(test_channel)
                    
                    # Longer timeout for reconnection (5 seconds)
                    response = test_stub.GetLeaderInfo(raft_node_pb2.GetLeaderRequest(), timeout=5.0)
                    
                    if response.is_leader:
                        print(f"✓ Reconnected to new leader at {node_addr}")
                        
                        # Close old connection
                        if self.channel:
                            self.channel.close()
                        
                        self.channel = test_channel
                        self.stub = test_stub
                        self.server_address = node_addr
                        
                        # RECOVERY FIX: Test if token is still valid on new node
                        token_valid = False
                        remembered_username = self.username
                        remembered_channel = self.current_channel_name
                        
                        if self.token:
                            try:
                                test_req = raft_node_pb2.GetOnlineUsersRequest(token=self.token)
                                test_resp = test_stub.GetOnlineUsers(test_req, timeout=2.0)
                                token_valid = test_resp.success
                                
                                if not token_valid and remembered_username:
                                    # Auto-logout and prompt for re-login
                                    print("⚠️  Session expired on new leader")
                                    print("    Auto-logging out...")
                                    
                                    # Clear local session
                                    self.token = None
                                    self.username = None
                                    self.current_channel = None
                                    # Keep current_channel_name for restoration
                                    
                                    print(f"\n🔑 Please re-login: login {remembered_username}")
                            except:
                                pass
                        
                        # Try to restore current_channel after reconnect
                        if token_valid and self.current_channel_name and not self.current_channel:
                            try:
                                ch_req = raft_node_pb2.GetChannelsRequest(token=self.token)
                                ch_resp = test_stub.GetChannels(ch_req, timeout=3.0)
                                if ch_resp.success:
                                    for ch in ch_resp.channels:
                                        if ch.name.lower() == self.current_channel_name.lower():
                                            self.current_channel = ch.channel_id
                                            print(f"✓ Restored channel #{self.current_channel_name}")
                                            break
                            except:
                                pass  # Silent fail - user can rejoin manually
                        
                        return True
                    
                    test_channel.close()
                    
                except:
                    continue
            
            if attempt < 2:
                print(f"  Retry {attempt+1}/3... (waiting 2s)")
                time.sleep(2)
        
        print("❌ Could not reconnect to any leader")
        return False
    
    def _call_with_retry(self, rpc_func, *args, **kwargs):
        """Call RPC with automatic retry on leader failure"""
        max_retries = 2
        
        for attempt in range(max_retries):
            try:
                return rpc_func(*args, **kwargs)
            except grpc.RpcError as e:
                if e.code() == grpc.StatusCode.UNAVAILABLE and attempt < max_retries - 1:
                    # Leader might be down, try to reconnect
                    if self._reconnect_to_leader():
                        # Update stub reference and retry
                        continue
                    else:
                        raise
                elif e.code() == grpc.StatusCode.UNAVAILABLE:
                    raise Exception("Leader unavailable. Please check if Raft cluster is running.")
                else:
                    raise
            except Exception as e:
                if attempt < max_retries - 1 and "UNAVAILABLE" in str(e):
                    if self._reconnect_to_leader():
                        continue
                raise
        
        raise Exception("Failed after retries")
    
    def _ensure_connected_to_leader(self) -> bool:
        """Ensure we're connected to the current leader, reconnect if needed"""
        try:
            # Check if current connection is to leader (with short timeout)
            response = self.stub.GetLeaderInfo(raft_node_pb2.GetLeaderRequest(), timeout=2.0)
            
            if response.is_leader:
                return True  # Already connected to leader
            
            # We're connected to a follower, need to redirect to leader
            if response.leader_address and response.leader_id > 0:
                print(f"🔄 Redirecting to leader at {response.leader_address}...")
                
                # Create NEW connection (don't reuse old channel)
                leader_channel = grpc.insecure_channel(
                    response.leader_address,
                    options=[
                        ('grpc.max_connection_idle_ms', 30000),
                        ('grpc.max_connection_age_ms', 60000),
                        ('grpc.keepalive_time_ms', 10000),
                        ('grpc.keepalive_timeout_ms', 5000),
                    ]
                )
                leader_stub = raft_node_pb2_grpc.RaftNodeStub(leader_channel)
                
                # Verify it's actually the leader
                try:
                    verify = leader_stub.GetLeaderInfo(raft_node_pb2.GetLeaderRequest(), timeout=2.0)
                    
                    if verify.is_leader:
                        # Close old connection ONLY after new one works
                        old_channel = self.channel
                        self.channel = leader_channel
                        self.stub = leader_stub
                        self.server_address = response.leader_address
                        print(f"✓ Connected to leader node {response.leader_id}")
                        
                        # Close old channel in background (non-blocking)
                        if old_channel:
                            threading.Thread(target=lambda: old_channel.close(), daemon=True).start()
                        
                        return True
                    else:
                        leader_channel.close()
                        print("⚠️  Leader changed, retrying...")
                        return False
                except Exception as e:
                    leader_channel.close()
                    print(f"⚠️  Could not verify leader: {str(e)[:40]}")
                    return False
            else:
                print("⚠️  No leader available")
                return False
                
        except grpc.RpcError as e:
            # Current node is down or unreachable
            if e.code() == grpc.StatusCode.UNAVAILABLE:
                return self._reconnect_to_leader()
            elif e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                # Timeout doesn't mean connection is dead - just slow
                print("⚠️  Leader is slow, but still connected")
                return True
            elif e.code() == grpc.StatusCode.UNIMPLEMENTED:
                # Protocol mismatch - need to regenerate protos
                print("⚠️  Protocol mismatch - regenerate proto files!")
                return False
            else:
                print(f"⚠️  RPC error: {e.code()}")
                return False
        except Exception as e:
            # Any other error - try to reconnect
            if "closed channel" not in str(e).lower():
                print(f"⚠️  Connection error: {str(e)[:50]}")
            return self._reconnect_to_leader()
    
    def _call_leader_with_retry(self, rpc_func, *args, **kwargs):
        """Call RPC ensuring we're connected to leader, with retry"""
        max_retries = 3
        last_error = None

        # Fire-and-forget for send operations with BETTER deduplication
        is_send_operation = ('SendMessage' in str(rpc_func)) or ('SendDirectMessage' in str(rpc_func))
        
        if is_send_operation:
            request = args[0] if args else None
            if request:
                # Create hash based on content + user + 10-second window
                time_bucket = int(time.time() / 10)  # 10-second buckets instead of 2
                msg_hash = hashlib.md5(
                    f"{self.username}:{request.content}:{time_bucket}".encode()
                ).hexdigest()
                
                # Check if we sent this recently (within 30 seconds)
                with self.send_lock:
                    now = time.time()
                    last_sent = self.last_send_time.get(msg_hash, 0)
                    
                    if now - last_sent < 30:  # Block duplicates for 30 seconds
                        logger.info(f"Duplicate send blocked (sent {now - last_sent:.1f}s ago)")
                        return type('obj', (object,), {'success': True, 'message': 'Already sent'})()
                    
                    # Record this send
                    self.last_send_time[msg_hash] = now
                    self.pending_messages.append(msg_hash)
                    
                    # Clean old entries (older than 60 seconds)
                    old_hashes = [h for h, t in self.last_send_time.items() if now - t > 60]
                    for h in old_hashes:
                        del self.last_send_time[h]
            
            def async_send():
                try:
                    # Ensure leader connection
                    for _ in range(2):
                        try:
                            if self._ensure_connected_to_leader():
                                break
                        except:
                            pass
                        time.sleep(0.1)
                    
                    # Send with longer timeout for DMs (10s) vs messages (5s)
                    local_kwargs = dict(kwargs)
                    if 'SendDirectMessage' in str(rpc_func):
                        local_kwargs.setdefault('timeout', 10.0)  # Longer for DMs
                    else:
                        local_kwargs.setdefault('timeout', 5.0)
                    
                    rpc_func(*args, **local_kwargs)
                    logger.info("Message sent successfully in background")
                except grpc.RpcError as e:
                    if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                        logger.warning(f"Send timeout but message likely succeeded (server committed)")
                    else:
                        logger.warning(f"Send failed: {e.code()}")
                except Exception as e:
                    logger.warning(f"Send error: {str(e)[:60]}")

            threading.Thread(target=async_send, daemon=True).start()
            # Return immediate success with helpful message
            if 'SendDirectMessage' in str(rpc_func):
                return type('obj', (object,), {'success': True, 'message': 'DM sending...'})()
            else:
                return type('obj', (object,), {'success': True, 'message': 'Message queued'})()

        # Non-send operations use normal retry logic
        for attempt in range(max_retries):
            try:
                if attempt == 0:
                    if not self._ensure_connected_to_leader():
                        raise Exception("Not connected to leader")

                if 'timeout' not in kwargs:
                    kwargs['timeout'] = 5.0

                return rpc_func(*args, **kwargs)

            except grpc.RpcError as e:
                last_error = e
                if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                    if attempt < max_retries - 1:
                        print(f"⚠️  Timeout, retrying... ({attempt+1}/{max_retries})")
                        time.sleep(0.5)
                        continue
                    else:
                        raise Exception("❌ Operation timed out.")
                elif e.code() == grpc.StatusCode.UNAVAILABLE:
                    if attempt < max_retries - 1:
                        print("⚠️  Leader unavailable, reconnecting...")
                        if self._reconnect_to_leader():
                            time.sleep(0.3)
                            continue
                        time.sleep(0.5)
                        continue
                    else:
                        raise Exception("❌ No available leader. Check if 2+ nodes running.")
                elif e.code() == grpc.StatusCode.UNIMPLEMENTED:
                    raise Exception("❌ Protocol mismatch! Regenerate proto files.")
                elif e.code() == grpc.StatusCode.NOT_FOUND:
                    raise Exception("❌ Resource not found.")
                else:
                    if attempt < max_retries - 1:
                        print(f"⚠️  RPC error ({e.code()}), retrying...")
                        time.sleep(0.3)
                        continue
                    else:
                        raise
            except Exception as e:
                last_error = e
                msg = str(e)
                if "closed channel" in msg.lower():
                    if attempt < max_retries - 1:
                        print(f"⚠️  Reconnecting... ({attempt+1}/{max_retries})")
                        time.sleep(0.3)
                        self._reconnect_to_leader()
                        continue
                    else:
                        raise Exception("Connection closed. Type 'reconnect'.")
                if attempt < max_retries - 1 and ("UNAVAILABLE" in msg or "Connection" in msg):
                    print(f"⚠️  Connection error, retrying... ({attempt+1}/{max_retries})")
                    time.sleep(0.5)
                    continue
                else:
                    raise

        if last_error:
            raise last_error
        raise Exception("Failed after 3 retries")
    
    def do_signup(self, arg):
        """Create new account: signup"""
        if self.token:
            print("Already logged in. Logout first.")
            return
        
        print("\n📝 Create New Account")
        print("-" * 30)
        
        try:
            username = input("Username: ").strip()
            if not username:
                print("Username required")
                return
            
            email = input("Email: ").strip()
            display_name = input("Display name (optional): ").strip() or username
            password = getpass.getpass("Password: ")
            
            request = raft_node_pb2.SignupRequest(
                username=username,
                password=password,
                email=email,
                display_name=display_name
            )
           
            # Use leader-aware call for signup with longer timeout (user creation needs full replication)
            response = self._call_leader_with_retry(self.stub.Signup, request, timeout=15.0)
            
            if response.success:
                print(f"✓ {response.message}")
                print(f"  Username: {response.user_info.username}")
                print(f"  Display Name: {response.user_info.display_name}")
                print("\n✓ You can now login!")
            else:
                print(f"❌ Signup failed: {response.message}")
                
        except KeyboardInterrupt:
            print("\nSignup cancelled")
        except Exception as e:
            print(f"Error: {e}")
    
    def do_login(self, arg):
        """Login: login <username>"""
        if self.token:
            print("Already logged in")
            return
        
        if not arg:
            print("Usage: login <username>")
            print("Test users: alice, bob, admin (password: <username>123)")
            return
        
        username = arg.strip()
        password = getpass.getpass("Password: ")
        
        try:
            request = raft_node_pb2.LoginRequest(username=username, password=password)
            response = self.stub.Login(request)
            
            if response.success:
                self.token = response.token
                self.username = username
                print(f"✓ Logged in as {username}")
                print(f"  Display: {response.user_info.display_name}")
                print(f"  Connected to: {self.server_address}")
                
                # Try to restore previous channel if we had one before logout
                restored = False
                if self.current_channel_name and self.current_channel_name != "general":
                    try:
                        ch_req = raft_node_pb2.GetChannelsRequest(token=self.token)
                        ch_resp = self.stub.GetChannels(ch_req, timeout=3.0)
                        if ch_resp.success:
                            for ch in ch_resp.channels:
                                if ch.name.lower() == self.current_channel_name.lower():
                                    # Check if we're a member
                                    for member in ch.members:
                                        if member.username == username:
                                            self.current_channel = ch.channel_id
                                            print(f"✓ Restored channel #{self.current_channel_name}")
                                            restored = True
                                            break
                                    break
                    except:
                        pass
                
                if not restored:
                    self._join_default_channel()
            else:
                print(f"❌ Login failed: {response.message}")
        except Exception as e:
            print(f"Error: {e}")
    
    def do_logout(self, arg):
        """Logout"""
        if not self.token:
            print("Not logged in")
            return
        
        try:
            request = raft_node_pb2.LogoutRequest(token=self.token)
            response = self.stub.Logout(request)
            
            if response.success:
                print("✓ Logged out")
                self.token = None
                self.username = None
                self.current_channel = None
                self.current_channel_name = None
                self.dm_mode = False
            else:
                print("⚠️  Logout failed on server, but clearing local session")
                self.token = None
                self.username = None
                self.current_channel = None
                self.current_channel_name = None
                self.dm_mode = False
        except Exception as e:
            # Even if server logout fails, clear local session
            print(f"⚠️  Server error: {str(e)[:50]}")
            print("    Clearing local session anyway")
            self.token = None
            self.username = None
            self.current_channel = None
            self.current_channel_name = None
            self.dm_mode = False
    
    def do_channels(self, arg):
        """List all channels"""
        if not self.token:
            print("Please login first")
            return
        
        try:
            request = raft_node_pb2.GetChannelsRequest(token=self.token)
            response = self._call_with_retry(self.stub.GetChannels, request, timeout=5.0)
            
            if response.success:
                print("\n📋 Available Channels:")
                print("-" * 50)
                
                # Deduplicate channels by name (keep the one with most members)
                channels_by_name = {}
                for channel in response.channels:
                    name = channel.name
                    if name not in channels_by_name or channel.member_count > channels_by_name[name].member_count:
                        channels_by_name[name] = channel
                
                # Sort by name for consistent display
                unique_channels = sorted(channels_by_name.values(), key=lambda c: c.name)
                
                for channel in unique_channels:
                    status = "✓" if channel.channel_id == self.current_channel else " "
                    print(f"{status} #{channel.name:<20} ({channel.member_count} members)")
                    if channel.description:
                        print(f"    {channel.description}")
                print("-" * 50)
        except Exception as e:
            print(f"Error: {e}")
    
    def do_create_channel(self, arg):
        """Create a new channel: create_channel <name> [description]"""
        if not self.token:
            print("Please login first")
            return
        
        if not arg:
            print("Usage: create_channel <name> [description]")
            return
        
        parts = arg.split(maxsplit=1)
        channel_name = parts[0]
        description = parts[1] if len(parts) > 1 else f"Channel {channel_name}"
        
        try:
            request = raft_node_pb2.CreateChannelRequest(
                token=self.token,
                channel_name=channel_name,
                description=description,
                is_private=False
            )
            # Use leader-aware call
            response = self._call_leader_with_retry(self.stub.CreateChannel, request, timeout=5.0)
            
            if response.success:
                print(f"✓ {response.message}")
                # Auto-join the created channel
                if hasattr(response, 'channel_id') and response.channel_id:
                    self.current_channel = response.channel_id
                    self.current_channel_name = channel_name
                    self.dm_mode = False
                    logger.info(f"Auto-joined channel #{channel_name} (ID: {response.channel_id})")
            else:
                print(f"❌ Failed: {response.message}")
        except Exception as e:
            print(f"Error: {e}")
    
    def do_switch(self, arg):
        """Switch to a channel you're already a member of: switch <channel_name>"""
        if not self.token:
            print("Please login first")
            return
        
        if not arg:
            print("Usage: switch <channel_name>")
            print("Example: switch Test")
            return
        
        channel_name = arg.strip()
        
        try:
            # Get all channels
            request = raft_node_pb2.GetChannelsRequest(token=self.token)
            response = self._call_with_retry(self.stub.GetChannels, request, timeout=5.0)
            
            if response.success:
                # Find the channel by name (case-insensitive)
                target_channel = None
                for channel in response.channels:
                    if channel.name.lower() == channel_name.lower():
                        target_channel = channel
                        break
                
                if not target_channel:
                    print(f"❌ Channel #{channel_name} not found")
                    return
                
                # Check if user is a member
                if target_channel.member_count == 0:
                    print(f"❌ You are not a member of #{channel_name}")
                    print(f"   Ask an admin to add you: add_user {self.username}")
                    return
                
                # Switch to the channel
                self.current_channel = target_channel.channel_id
                self.current_channel_name = channel_name
                self.dm_mode = False
                
                print(f"✓ Switched to #{channel_name}")
                
                # Show recent messages
                self._show_recent_messages(10)
            else:
                print(f"❌ Failed to get channels: {response.message if hasattr(response, 'message') else 'Unknown error'}")
                print("   Possible causes:")
                print("   - Your session expired (try: logout then login)")
                print("   - Token invalid on this node (already fixed in latest code)")
                
        except grpc.RpcError as e:
            print(f"❌ Connection error: {e.code()}")
            print("   Try: reconnect")
        except Exception as e:
            print(f"❌ Error: {e}")
    
    def do_join(self, arg):
        """Join channel: join <channel_name> [DEPRECATED - Use 'switch' instead]"""
        if not self.token:
            print("Please login first")
            return
        
        if not arg:
            print("Usage: switch <channel_name> (to switch to a channel you're in)")
            print("Note: You cannot join channels directly.")
            print("      Ask a channel admin to add you using: add_user <your_username>")
            return
        
        channel_name = arg.strip()
        
        # Special case: Allow joining "general" channel
        try:
            request = raft_node_pb2.GetChannelsRequest(token=self.token)
            response = self._call_with_retry(self.stub.GetChannels, request, timeout=5.0)
            
            if response.success:
                for channel in response.channels:
                    # Allow joining default public channels: general, random, tech
                    if channel.name.lower() in ['general', 'random', 'tech'] and channel.name.lower() == channel_name.lower():
                        # Try to join the default public channel
                        join_request = raft_node_pb2.JoinChannelRequest(
                            token=self.token,
                            channel_id=channel.channel_id
                        )
                        join_response = self._call_leader_with_retry(self.stub.JoinChannel, join_request, timeout=5.0)
                        
                        if join_response.success:
                            self.current_channel = channel.channel_id
                            self.current_channel_name = channel.name
                            self.dm_mode = False
                            print(f"✓ {join_response.message}")
                            self._show_recent_messages(10)
                        else:
                            print(f"❌ {join_response.message}")
                        return
        except Exception as e:
            pass
        
        print(f"\n⚠️  NOTICE: Users cannot join channels directly.")
        print(f"   If you're already a member of #{channel_name}, use: switch {channel_name}")
        print(f"   Otherwise, ask an admin of #{channel_name} to add you with:")
        print(f"   > add_user {self.username}")
        print(f"\n   Or create your own channel with: create_channel <name>")
        return
        
        # OLD CODE - kept for reference but unreachable
        try:
            channels_req = raft_node_pb2.GetChannelsRequest(token=self.token)
            channels_resp = self.stub.GetChannels(channels_req)
            
            if channels_resp.success:
                for channel in channels_resp.channels:
                    if channel.name.lower() == channel_name.lower():
                        join_req = raft_node_pb2.JoinChannelRequest(
                            token=self.token,
                            channel_id=channel.channel_id
                        )
                        # Use leader-aware call for join
                        join_resp = self._call_leader_with_retry(self.stub.JoinChannel, join_req, timeout=5.0)
                        
                        if join_resp.success:
                            self.current_channel = channel.channel_id
                            self.current_channel_name = channel.name
                            self.dm_mode = False
                            print(f"✓ Joined #{channel_name}")
                            self._show_recent_messages()
                        else:
                            print(f"❌ Failed to join: {join_resp.message}")
                        return
                
                print(f"❌ Channel '{channel_name}' not found")
        except Exception as e:
            print(f"Error: {e}")
    
    def do_send(self, arg):
        """Send message: send <message>"""
        if not self.token:
            print("Please login first")
            return
        
        if not arg:
            print("Usage: send <message>")
            return
        
        try:
            if self.dm_mode:
                request = raft_node_pb2.DirectMessageRequest(
                    token=self.token,
                    recipient_username=self.dm_partner,
                    content=arg
                )
                # Use leader-aware call with longer timeout
                response = self._call_leader_with_retry(self.stub.SendDirectMessage, request)
                
                if response.success:
                    timestamp = datetime.now().strftime("%H:%M")
                    print(f"[{timestamp}] You: {arg}")
                else:
                    print(f"❌ Failed: {response.message}")
            else:
                if not self.current_channel:
                    print("❌ No channel selected. Use 'join <channel>' first.")
                    print("Available channels: general, random, tech")
                    return
                
                # Verify channel still exists before sending
                channels_req = raft_node_pb2.GetChannelsRequest(token=self.token)
                channels_resp = self.stub.GetChannels(channels_req, timeout=2.0)
                
                channel_exists = False
                if channels_resp.success:
                    for channel in channels_resp.channels:
                        if channel.channel_id == self.current_channel:
                            channel_exists = True
                            break
                
                if not channel_exists:
                    print(f"❌ Channel #{self.current_channel_name} no longer exists or you lost access.")
                    print("   Rejoining general channel...")
                    self._join_default_channel()
                    return
                
                request = raft_node_pb2.SendMessageRequest(
                    token=self.token,
                    channel_id=self.current_channel,
                    content=arg
                )
                # FIX: Use leader-aware call with longer timeout (15s)
                response = self._call_leader_with_retry(self.stub.SendMessage, request)
                
                if response.success:
                    timestamp = datetime.now().strftime("%H:%M")
                    print(f"[{timestamp}] You → #{self.current_channel_name}: {arg}")
                else:
                    print(f"❌ Failed: {response.message}")
                    if "not found" in response.message.lower():
                        print("   Try rejoining the channel: join general")
                        
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                print(f"❌ Channel not found. Rejoining general...")
                self._join_default_channel()
            else:
                print(f"Error: {e.details() if hasattr(e, 'details') else str(e)}")
                print("Tip: Try 'status' to check cluster health")
        except Exception as e:
            error_msg = str(e)
            print(f"Error: {error_msg}")
            # Don't print the "Tip" if it's a custom message from _call_leader_with_retry
            if "cluster" not in error_msg.lower() and "timeout" not in error_msg.lower():
                print("Tip: Try 'status' to check cluster health or 'join general' to rejoin")
    
    def do_dm(self, arg):
        """Start DM conversation: dm <username>"""
        if not self.token:
            print("Please login first")
            return
        
        if not arg:
            print("Usage: dm <username>")
            return
        
        recipient = arg.strip()
        
        if recipient == self.username:
            print("Cannot DM yourself")
            return
        
        self.dm_mode = True
        self.dm_partner = recipient
        self.current_channel = None
        
        print(f"💬 Direct message with @{recipient}")
        print(f"   Type 'send <message>' to chat")
        print(f"   Type 'back' to return to channels")
        
        try:
            # CRITICAL FIX: Force reconnect to ensure we're on a healthy node
            # Try up to 3 times with fresh connections
            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    # First ensure we're connected to leader
                    if not self._ensure_connected_to_leader():
                        if attempt < max_attempts - 1:
                            print(f"⚠️  Not connected to leader, retrying ({attempt+1}/{max_attempts})...")
                            time.sleep(1.0)
                            continue
                        print("\n⚠️  Could not connect to leader. Type 'reconnect' to try again.")
                        print("    Your DM history will be available once connected.")
                        return
                    
                    # Now fetch DMs with a fresh connection
                    request = raft_node_pb2.GetDirectMessagesRequest(
                        token=self.token,
                        other_username=recipient,
                        limit=20,
                        offset=0
                    )
                    
                    # Use longer timeout for potentially slow leader
                    response = self.stub.GetDirectMessages(request, timeout=5.0)
                    
                    if response.success:
                        if response.messages:
                            print("\n📜 Recent messages:")
                            print("-" * 50)
                            for dm in response.messages:
                                timestamp = datetime.fromtimestamp(dm.timestamp / 1000).strftime("%H:%M")
                                sender = "You" if dm.sender_name == self.username else dm.sender_name
                                print(f"[{timestamp}] {sender}: {dm.content}")
                            print("-" * 50)
                        else:
                            print("\n💡 No previous messages with this user")
                        return  # Success!
                    else:
                        # Response failed, retry
                        if attempt < max_attempts - 1:
                            print(f"⚠️  Failed to load DMs, retrying ({attempt+1}/{max_attempts})...")
                            time.sleep(0.5)
                            continue
                        print("\n💡 Could not load DM history. Your new messages will still be saved!")
                        return
                
                except grpc.RpcError as e:
                    if e.code() == grpc.StatusCode.UNAVAILABLE and attempt < max_attempts - 1:
                        print(f"⚠️  Connection error, reconnecting ({attempt+1}/{max_attempts})...")
                        self._reconnect_to_leader()
                        time.sleep(0.5)
                        continue
                    elif attempt == max_attempts - 1:
                        print(f"\n⚠️  Could not load DM history after {max_attempts} attempts")
                        print("    Your messages will still be sent and saved!")
                        return
                except Exception as e:
                    if attempt < max_attempts - 1:
                        print(f"⚠️  Error loading DMs, retrying ({attempt+1}/{max_attempts})...")
                        time.sleep(0.5)
                        continue
                    print(f"\n⚠️  Error: {str(e)[:60]}")
                    print("    Your messages will still be sent and saved!")
                    return
                    
        except Exception as e:
            print(f"\n⚠️  Unexpected error: {str(e)[:60]}")
            print("    Your messages will still be sent and saved!")
    
    def do_conversations(self, arg):
        """List all DM conversations"""
        if not self.token:
            print("Please login first")
            return
        
        try:
            # CRITICAL FIX: Ensure connected before fetching conversations
            if not self._ensure_connected_to_leader():
                print("⚠️  Not connected to any server. Type 'reconnect' to find the leader.")
                return
            
            request = raft_node_pb2.ListConversationsRequest(token=self.token)
            
            # Use leader-aware call with retry
            response = self._call_leader_with_retry(self.stub.ListConversations, request, timeout=5.0)
            
            if response.success:
                if response.conversations:
                    print("\n💬 Your Conversations:")
                    print("-" * 50)
                    for conv in response.conversations:
                        unread = f"({conv.unread_count} unread)" if conv.unread_count > 0 else ""
                        print(f"  @{conv.username} {unread}")
                        print(f"    {conv.display_name}")
                    print("-" * 50)
                    print("Use 'dm <username>' to open conversation")
                else:
                    print("No conversations yet")
        except Exception as e:
            print(f"Error: {str(e)[:60]}")
            print("Tip: Type 'reconnect' if you were connected to a failed node")
    
    def do_back(self, arg):
        """Return to channel mode from DM"""
        if self.dm_mode:
            self.dm_mode = False
            self.dm_partner = None
            print("Back to channel mode. Use 'join <channel>' to join a channel")
        else:
            print("Already in channel mode")
    
    def do_history(self, arg):
        """Show message history: history [limit]"""
        if not self.token:
            print("Please login first")
            return
        
        if self.dm_mode:
            print("History only works in channels. Type 'back' to return to channel mode.")
            return
        
        if not self.current_channel:
            print("❌ Not in any channel. Try: switch general")
            return
        
        limit = 20
        if arg:
            try:
                limit = int(arg)
            except:
                pass
        
        # Try to get messages - auto-logout if token invalid
        try:
            request = raft_node_pb2.GetMessagesRequest(
                token=self.token,
                channel_id=self.current_channel,
                limit=limit,
                offset=0
            )
            response = self.stub.GetMessages(request, timeout=5.0)
            
            if not response.success:
                # Token is invalid - auto-logout and prompt
                print("❌ Your session is invalid on this server")
                print("   Auto-logging out...")
                self.token = None
                self.username = None
                self.current_channel = None
                self.current_channel_name = None
                print("\n🔑 Please login again: login alice")
                return
            
            if response.messages:
                print(f"\n📜 Recent Messages (last {limit}):")
                print("-" * 50)
                for msg in response.messages:
                    timestamp = datetime.fromtimestamp(msg.timestamp / 1000).strftime("%H:%M")
                    print(f"[{timestamp}] {msg.sender_name}: {msg.content}")
                print("-" * 50)
            else:
                print("No messages yet. Be the first to say something!")
        except grpc.RpcError as e:
            print(f"❌ Connection error: {e.code()}")
            print("   Try: reconnect")
        except Exception as e:
            print(f"❌ Error: {e}")
    
    def do_users(self, arg):
        """Show all users"""
        if not self.token:
            print("Please login first")
            return
        
        try:
            request = raft_node_pb2.GetOnlineUsersRequest(token=self.token)
            response = self.stub.GetOnlineUsers(request, timeout=5.0)
            
            if response.success:
                online_users = [u for u in response.users if u.status == "online"]
                offline_users = [u for u in response.users if u.status == "offline"]
                
                print("\n👥 All Users:")
                print("-" * 50)
                
                if online_users:
                    print("🟢 ONLINE:")
                    for user in online_users:
                        admin_badge = "👑" if user.is_admin else "  "
                        print(f"  {admin_badge} {user.display_name} (@{user.username})")
                
                if offline_users:
                    print("\n⚫ OFFLINE:")
                    for user in offline_users:
                        admin_badge = "👑" if user.is_admin else "  "
                        print(f"  {admin_badge} {user.display_name} (@{user.username})")
                
                print("-" * 50)
                print(f"Total: {len(online_users)} online, {len(offline_users)} offline")
            else:
                error_msg = response.message if hasattr(response, 'message') and response.message else 'Token verification failed'
                print(f"❌ Failed to get users: {error_msg}")
                if not response.message or 'token' in error_msg.lower():
                    print("   💡 Your session is invalid. Get a fresh token:")
                    print("      logout")
                    print("      login alice")
        except grpc.RpcError as e:
            print(f"❌ Connection error: {e.code()}")
            print("   Try: reconnect")
        except Exception as e:
            print(f"❌ Error: {e}")
    
    def do_reconnect(self, arg):
        """Force reconnect to current leader"""
        print("🔄 Forcing reconnection...")
        
        # Close current connection
        if self.channel:
            try:
                self.channel.close()
            except:
                pass
            # Force Python to release the channel object
            self.channel = None
            self.stub = None
            time.sleep(0.2)  # Give OS time to close socket
        
        # Try to find and connect to leader
        if self._reconnect_to_leader():
            print(f"✓ Successfully reconnected to {self.server_address}")
            
            # Verify connection works with a quick test
            try:
                test_request = raft_node_pb2.GetLeaderRequest()
                test_response = self.stub.GetLeaderInfo(test_request, timeout=2.0)
                if test_response.is_leader:
                    print(f"✓ Verified connection to LEADER node {test_response.leader_id}")
                else:
                    print(f"⚠️  Connected to {test_response.state} node, not leader")
            except:
                pass
            
            # Show cluster status after reconnection
            self.do_status("")
        else:
            print("❌ Failed to reconnect. Please check if at least 2 nodes are running.")
    
    def do_status(self, arg):
        """Show Raft cluster status"""
        print("\n🖥️  Raft Cluster Status")
        print("=" * 60)
        print(f"Connected to: {self.server_address}")
        print(f"Username: {self.username or 'Not logged in'}")
        if self.current_channel_name:
            print(f"Current channel: #{self.current_channel_name}")
        
        # Show message count if logged in and in a channel
        if self.token and self.current_channel:
            try:
                req = raft_node_pb2.GetMessagesRequest(
                    token=self.token,
                    channel_id=self.current_channel,
                    limit=100,
                    offset=0
                )
                resp = self.stub.GetMessages(req, timeout=2.0)
                if resp.success:
                    print(f"Messages in #general: {len(resp.messages)}")
            except:
                pass
        
        # Check if current connection is alive
        current_connection_alive = False
        try:
            response = self.stub.GetLeaderInfo(raft_node_pb2.GetLeaderRequest(), timeout=2.0)
            current_connection_alive = True  # Connection worked
            if response.is_leader:
                print(f"Status: ✅ Connected to LEADER")
            else:
                print(f"Status: ⚠️  Connected to {response.state.upper()} (not leader)")
                if response.leader_address:
                    print(f"         Current leader is at: {response.leader_address}")
        except Exception as e:
            print(f"Status: ❌ UNREACHABLE - {str(e)[:60]}")
            print(f"        Tip: Use 'reconnect' to find the current leader")
        
        print(f"\nCluster nodes:")
        
        for node_addr in self.cluster_nodes:
            try:
                # Create fresh connection for each check with longer timeout
                channel = grpc.insecure_channel(
                    node_addr,
                    options=[
                        ('grpc.max_connection_idle_ms', 5000),
                        ('grpc.keepalive_time_ms', 10000),
                    ]
                )
                stub = raft_node_pb2_grpc.RaftNodeStub(channel)
                
                # Increase timeout to 3 seconds
                response = stub.GetLeaderInfo(raft_node_pb2.GetLeaderRequest(), timeout=3.0)
                
                status = "👑 LEADER" if response.is_leader else f"{response.state.upper()}"
                connected = "✓" if node_addr == self.server_address else " "
                print(f" {connected} {node_addr}: {status} (Term {response.term})")
                
                channel.close()
            except grpc.RpcError as e:
                unreachable_marker = "✗" if node_addr == self.server_address else " "
                # Show the actual error code for debugging
                print(f" {unreachable_marker} {node_addr}: UNREACHABLE ({e.code()})")
            except Exception as e:
                unreachable_marker = "✗" if node_addr == self.server_address else " "
                print(f" {unreachable_marker} {node_addr}: UNREACHABLE")
        
        print("=" * 60)
        
        # Only suggest reconnect if the FIRST check failed
        if not current_connection_alive:
            print("\n⚠️  Your connection is DEAD. Type 'reconnect' to find the current leader.")
    
    def do_clear(self, arg):
        """Clear the screen"""
        os.system('cls' if os.name == 'nt' else 'clear')
        print(self.intro)
    
    def do_upload(self, arg):
        """Upload file: upload <filepath> [description]"""
        if not self.token:
            print("Please login first")
            return
        
        if not arg:
            print("Usage: upload <filepath> [description]")
            return
        
        parts = arg.split(maxsplit=1)
        filepath = parts[0]
        description = parts[1] if len(parts) > 1 else ""
        
        if not os.path.exists(filepath):
            print(f"File not found: {filepath}")
            return
        
        try:
            with open(filepath, 'rb') as f:
                file_data = f.read()
            
            file_name = os.path.basename(filepath)
            file_size = len(file_data)
            
            if file_size > 10 * 1024 * 1024:  # 10MB limit
                print("File too large. Max 10MB")
                return
            
            print(f"Uploading {file_name} ({file_size} bytes)...")
            
            import mimetypes
            mime_type = mimetypes.guess_type(filepath)[0] or "application/octet-stream"
            
            request = raft_node_pb2.FileUploadRequest(
                token=self.token,
                file_name=file_name,
                file_data=file_data,
                channel_id=self.current_channel if not self.dm_mode else "",
                recipient_username=self.dm_partner if self.dm_mode else "",
                description=description,
                mime_type=mime_type
            )
            
            response = self.stub.UploadFile(request, timeout=30.0)
            
            if response.success:
                print(f"✓ File uploaded: {file_name}")
                print(f"  File ID: {response.file_id}")
            else:
                print(f"❌ Upload failed: {response.message}")
                
        except Exception as e:
            print(f"Error: {e}")
    
    def do_download(self, arg):
        """Download file: download <file_id> [save_as]"""
        if not self.token:
            print("Please login first")
            return
        
        if not arg:
            print("Usage: download <file_id> [save_as]")
            return
        
        parts = arg.split()
        file_id = parts[0]
        save_as = parts[1] if len(parts) > 1 else None
        
        try:
            print("Downloading...")
            
            request = raft_node_pb2.FileDownloadRequest(
                token=self.token,
                file_id=file_id
            )
            
            response = self.stub.DownloadFile(request, timeout=30.0)
            
            if response.success:
                # Create downloads folder with username
                download_dir = os.path.join("downloads", self.username)
                os.makedirs(download_dir, exist_ok=True)
                
                filename = save_as or response.file_name
                filepath = os.path.join(download_dir, filename)
                
                with open(filepath, 'wb') as f:
                    f.write(response.file_data)
                
                print(f"✓ Downloaded: {filepath}")
                print(f"  Size: {len(response.file_data)} bytes")
            else:
                print("❌ Download failed")
                
        except Exception as e:
            print(f"Error: {e}")
    
    def do_files(self, arg):
        """List files in current channel"""
        if not self.token or not self.current_channel or self.dm_mode:
            print("Only works in channels")
            return
        
        try:
            request = raft_node_pb2.ListFilesRequest(
                token=self.token,
                channel_id=self.current_channel
            )
            
            response = self.stub.ListFiles(request)
            
            if response.success:
                if response.files:
                    print(f"\n📁 Files in #{self.current_channel_name}:")
                    print("-" * 70)
                    for file in response.files:
                        size_kb = file.file_size / 1024
                        print(f"  {file.file_name}")
                        print(f"    By: {file.uploader_name} | Size: {size_kb:.1f}KB")
                        print(f"    ID: {file.file_id}")
                    print("-" * 70)
                    print("Use: download <file_id> to download")
                else:
                    print("No files in this channel")
        except Exception as e:
            print(f"Error: {e}")
    
    def do_smart_reply(self, arg):
        """Get smart reply suggestions or send numbered reply"""
        if not self.token or not self.current_channel or self.dm_mode:
            print("Only works in channels")
            return
        
        # Check if user typed a number to send a previous suggestion
        if arg.strip().isdigit():
            choice = int(arg.strip())
            if 1 <= choice <= len(self.last_smart_replies):
                selected_reply = self.last_smart_replies[choice - 1]
                print(f"📤 Sending: {selected_reply}")
                # Use the existing send command
                self.do_send(selected_reply)
                self.last_smart_replies = []  # Clear after sending
                return
            else:
                print(f"❌ Invalid choice. Choose 1-{len(self.last_smart_replies)}")
                return
        
        try:
            print("🤖 Getting smart replies...")
            
            request = raft_node_pb2.SmartReplyRequest(
                token=self.token,
                channel_id=self.current_channel,
                recent_message_count=5
            )
            
            # INCREASED timeout from 10s to 20s for Gemini API
            response = self.stub.GetSmartReply(request, timeout=20.0)
            
            if response.success and response.suggestions:
                self.last_smart_replies = response.suggestions  # Store for later
                print("\n💡 Smart Reply Suggestions:")
                for i, suggestion in enumerate(response.suggestions, 1):
                    print(f"   {i}. {suggestion}")
                print("\n💬 Type 'smart_reply <number>' to send that reply")
                print("   Example: smart_reply 1")
            else:
                print("No suggestions available")
                
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                print("⏱️  Smart reply timed out. The LLM server might be slow.")
                print("    Try again or check if the LLM server is running:")
                print("    python llm_server/llm_server.py")
            else:
                print(f"Error: {e.code()}")
        except Exception as e:
            print(f"Error: {str(e)[:80]}")

    def do_ask(self, arg):
        """Ask AI a question: ask <your question>"""
        if not self.token:
            print("Please login first")
            return
        
        if not arg.strip():
            print("Usage: ask <your question>")
            print("Example: ask What is the capital of France?")
            return
        
        question = arg.strip()
        
        try:
            print(f"🤖 Asking AI: {question[:60]}...")
            
            request = raft_node_pb2.LLMRequest(
                token=self.token,
                query=question,
                context=[]  # Empty context for now
            )
            
            # INCREASED timeout from 30s to 60s for Gemini API
            response = self.stub.GetLLMAnswer(request, timeout=60.0)
            
            if response.success:
                print("\n" + "="*60)
                print("🤖 AI ANSWER")
                print("="*60)
                print(f"\n{response.answer}\n")
                print("="*60)
            else:
                print(f"❌ {response.answer}")
                
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                print("⏱️  AI request timed out after 60 seconds.")
                print("    The Gemini API might be slow or overloaded.")
                print("    Try a simpler question or check your internet connection.")
                print("    Example: ask What is 2+2?")
            else:
                print(f"Error: {e.code()}")
        except Exception as e:
            error_msg = str(e)
            if "LLM service is not available" in error_msg:
                print("❌ LLM server is not running.")
                print("    Start it with: python llm_server/llm_server.py")
            else:
                print(f"Error: {error_msg[:80]}")

    def do_suggest(self, arg):
        """Get context-aware suggestions or send numbered suggestion"""
        if not self.token or not self.current_channel or self.dm_mode:
            print("Only works in channels")
            return
        
        # Check if user typed a number to send a previous suggestion
        if arg.strip().isdigit():
            choice = int(arg.strip())
            if 1 <= choice <= len(self.last_context_suggestions):
                selected_text = self.last_context_suggestions[choice - 1]
                print(f"📤 Sending: {selected_text}")
                # Use the existing send command
                self.do_send(selected_text)
                self.last_context_suggestions = []  # Clear after sending
                return
            else:
                print(f"❌ Invalid choice. Choose 1-{len(self.last_context_suggestions)}")
                return
        
        current_input = arg.strip() if arg else ""
        
        try:
            print("🤖 Getting context-aware suggestions...")
            
            request = raft_node_pb2.ContextSuggestionsRequest(
                token=self.token,
                channel_id=self.current_channel,
                current_input=current_input,
                context_message_count=5
            )
            
            # INCREASED timeout from 8s to 20s
            response = self.stub.GetContextSuggestions(request, timeout=20.0)
            
            if response.success:
                if response.suggestions:
                    self.last_context_suggestions = response.suggestions  # Store for later
                    print("\n💡 Suggested Completions:")
                    for i, suggestion in enumerate(response.suggestions, 1):
                        print(f"   {i}. {suggestion}")
                
                if response.topics:
                    print("\n🔖 Related Topics:")
                    for topic in response.topics:
                        print(f"   • {topic}")
                
                print("\n💬 Type 'suggest <number>' to send that completion")
                print("   Example: suggest 1")
            else:
                print("No suggestions available")
                
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                print("⏱️  Suggestions timed out. Try again or check the LLM server.")
            else:
                print(f"Error: {e.code()}")
        except Exception as e:
            print(f"Error: {str(e)[:80]}")
    
    def do_summarize(self, arg):
        """Summarize conversation: summarize [message_count]"""
        if not self.token or not self.current_channel or self.dm_mode:
            print("Only works in channels")
            return
        
        # Parse message count
        count = 20
        if arg.strip():
            try:
                count = int(arg.strip())
                if count < 5:
                    count = 5
                elif count > 100:
                    count = 100
            except ValueError:
                print("Invalid number. Using default (20 messages)")
        
        try:
            print(f"🤖 Summarizing last {count} messages...")
            
            request = raft_node_pb2.SummarizeRequest(
                token=self.token,
                channel_id=self.current_channel,
                message_count=count
            )
            
            # INCREASED timeout from 15s to 30s for summarization
            response = self.stub.SummarizeConversation(request, timeout=30.0)
            
            if response.success:
                print("\n" + "="*60)
                print("📝 CONVERSATION SUMMARY")
                print("="*60)
                print(f"\n{response.summary}\n")
                
                if response.key_points:
                    print("🔑 KEY POINTS:")
                    for i, point in enumerate(response.key_points, 1):
                        print(f"   {i}. {point}")
                print("="*60)
            else:
                print("❌ Could not generate summary")
                
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                print("⏱️  Summary generation timed out. Try with fewer messages:")
                print("   Example: summarize 10")
            else:
                print(f"Error: {e.code()}")
        except Exception as e:
            print(f"Error: {str(e)[:80]}")
            print("Tip: Make sure the LLM server is running")
    
    def do_add_user(self, arg):
        """Add user to current channel (admin only): add_user <username>"""
        if not self.token:
            print("Please login first")
            return
        
        if not self.current_channel:
            print("❌ Join a channel first")
            return
        
        if not arg:
            print("Usage: add_user <username>")
            return
        
        username = arg.strip()
        
        try:
            request = raft_node_pb2.ChannelAdminRequest(
                token=self.token,
                channel_id=self.current_channel,
                target_username=username
            )
            
            response = self._call_leader_with_retry(self.stub.AddUserToChannel, request, timeout=10.0)
            
            if response.success:
                print(f"✓ {response.message}")
            else:
                print(f"❌ Failed: {response.message}")
                
        except Exception as e:
            print(f"Error: {e}")
    
    def do_remove_user(self, arg):
        """Remove user from current channel (admin only): remove_user <username>"""
        if not self.token:
            print("Please login first")
            return
        
        if not self.current_channel:
            print("❌ Join a channel first")
            return
        
        if not arg:
            print("Usage: remove_user <username>")
            return
        
        username = arg.strip()
        
        try:
            request = raft_node_pb2.ChannelAdminRequest(
                token=self.token,
                channel_id=self.current_channel,
                target_username=username
            )
            
            response = self._call_leader_with_retry(self.stub.RemoveUserFromChannel, request, timeout=10.0)
            
            if response.success:
                print(f"✓ {response.message}")
            else:
                print(f"❌ Failed: {response.message}")
                
        except Exception as e:
            print(f"Error: {e}")
    
    def do_members(self, arg):
        """Show all members in current channel: members"""
        if not self.token:
            print("Please login first")
            return
        
        if not self.current_channel:
            print("❌ Join a channel first")
            return
        
        if self.dm_mode:
            print("❌ This command only works in channels")
            return
        
        try:
            # Use the new GetChannelMembers RPC
            request = raft_node_pb2.GetChannelMembersRequest(
                token=self.token,
                channel_id=self.current_channel
            )
            response = self.stub.GetChannelMembers(request, timeout=5.0)
            
            if not response.success:
                print("❌ Failed to get channel members")
                print("   💡 Your session may be invalid. Get a fresh token:")
                print("      logout")
                print("      login alice")
                return
            
            print(f"\n👥 Members of #{self.current_channel_name}")
            print("=" * 60)
            print(f"Total members: {response.total_count}")
            print("-" * 60)
            
            # Separate online and offline members
            online_members = [m for m in response.members if m.status == "online"]
            offline_members = [m for m in response.members if m.status == "offline"]
            
            if online_members:
                print("\n🟢 ONLINE:")
                for member in online_members:
                    current = "👈 You" if member.username == self.username else ""
                    admin_badge = "👑" if member.is_admin else "  "
                    print(f"  {admin_badge} {member.display_name} (@{member.username}) {current}")
            
            if offline_members:
                print("\n⚫ OFFLINE:")
                for member in offline_members:
                    current = "👈 You" if member.username == self.username else ""
                    admin_badge = "👑" if member.is_admin else "  "
                    print(f"  {admin_badge} {member.display_name} (@{member.username}) {current}")
            
            print("=" * 60)
            print(f"\nTotal: {len(online_members)} online, {len(offline_members)} offline")
            
            # Show admin hint only if user is admin
            current_user_is_admin = any(m.username == self.username and m.is_admin for m in response.members)
            if current_user_is_admin:
                print("\n💡 Admin commands: 'add_user <username>' | 'remove_user <username>'")
            else:
                print("\n💡 Tip: Only channel admins can add/remove members")
            
        except Exception as e:
            print(f"Error: {e}")
    
    def do_help_all(self, arg):
        """Show all available commands with categories"""
        print("\n" + "="*60)
        print("AUTHENTICATION COMMANDS")
        print("="*60)
        print("  signup                    - Create new account")
        print("  login <username>          - Login to account")
        print("  logout                    - Logout")
        
        print("\n" + "="*60)
        print("CHANNEL COMMANDS")
        print("="*60)
        print("  channels                  - List all channels")
        print("  create_channel <name> [d] - Create new channel (you become admin)")
        print("  switch <channel>          - Switch to a channel you're already in")
        print("  members                   - Show members of current channel")
        print("  send <message>            - Send message to current channel")
        print("  history [limit]           - Show message history")
        print("\n  Note: Use 'switch' to access channels you're a member of")
        print("        Ask admins to add you to other channels")
        
        print("\n" + "="*60)
        print("CHANNEL ADMIN COMMANDS (Admins Only)")
        print("="*60)
        print("  add_user <username>       - Add user to current channel")
        print("  remove_user <username>    - Remove user from current channel")
        print("  Note: You become admin when you create a channel")
        
        print("\n" + "="*60)
        print("DIRECT MESSAGE COMMANDS")
        print("="*60)
        print("  dm <username>             - Start DM conversation")
        print("  conversations             - List all your DM conversations")
        print("  send <message>            - Send DM (when in DM mode)")
        print("  back                      - Return to channel mode")
        
        print("\n" + "="*60)
        print("FILE TRANSFER COMMANDS")
        print("="*60)
        print("  upload <filepath> [desc]  - Upload file to channel/DM")
        print("  download <file_id> [name] - Download file by ID")
        print("  files                     - List files in current channel")
        
        print("\n" + "="*60)
        print("USER COMMANDS")
        print("="*60)
        print("  users                     - Show all users (online/offline)")
        
        print("\n" + "="*60)
        print("AI/LLM COMMANDS")
        print("="*60)
        print("  smart_reply               - Get AI reply suggestions")
        print("  summarize [limit]         - Summarize conversation")
        print("  ask <question>            - Ask AI a question")
        print("  suggest [text]         - Get context-aware completions")  # NEW!
        
    def do_help_all_DUPLICATE_REMOVE_ME(self, arg):
        """DUPLICATE FUNCTION - This should be removed"""
        print("⚠️  This is a duplicate function. Use 'help' or 'help_all' instead.")
        print("="*60)
        print("  status                    - Show Raft cluster status")
        print("  reconnect                 - Force reconnect to current leader")
        
        print("\n" + "="*60)
        print("OTHER COMMANDS")
        print("="*60)
        print("  clear                     - Clear screen")
        print("  help                      - Show basic help")
        print("  help_all                  - Show this comprehensive help")
        print("  exit                      - Exit application")
        print("="*60 + "\n")
    
    def do_help(self, arg):
        """Show help"""
        print("\n" + "="*60)
        print("AVAILABLE COMMANDS")
        print("="*60)
        print("  signup                 - Create new account")
        print("  login <username>       - Login")
        print("  logout                 - Logout")
        print()
        print("  channels               - List all channels")
        print("  create_channel <name>  - Create new channel (you become admin)")
        print("  switch <channel_name>  - Switch to a channel you're already in")
        print("  send <message>         - Send message")
        print("  history [limit]        - Show message history")
        print("  members                - Show channel members")
        print()
        print("  add_user <username>    - Add user to channel (admin only)")
        print("  remove_user <username> - Remove user from channel (admin only)")
        print("  ⚠️  Use 'switch' to access your channels. Admins add you to others.")
        print()
        print("  dm <username>          - Start DM conversation")
        print("  conversations          - List all DM conversations")
        print("  back                   - Exit DM mode")
        print()
        print("  upload <file>          - Upload file")
        print("  download <id>          - Download file")
        print("  files                  - List files in channel")
        print()
        print("  smart_reply            - Get AI reply suggestions")
        print("  summarize [count]      - Summarize conversation")
        print("  ask <question>         - Ask AI a question")
        print("  suggest [text]         - Get context-aware completions")
        print()
        print("  users                  - Show all users")
        print("  status                 - Show Raft cluster status")
        print("  Type 'help_all' for detailed help with all commands")
    def _join_default_channel(self):
        """Auto-join general channel"""
        # Add small delay to let connection stabilize after login
        time.sleep(0.2)
        
        try:
            # Use leader-aware call with retry
            request = raft_node_pb2.GetChannelsRequest(token=self.token)
            
            # Try multiple times with increasing delays
            for attempt in range(3):
                try:
                    response = self.stub.GetChannels(request, timeout=5.0)
                    
                    if response.success:
                        for channel in response.channels:
                            if channel.name == "general":
                                join_req = raft_node_pb2.JoinChannelRequest(
                                    token=self.token,
                                    channel_id=channel.channel_id
                                )
                                
                                try:
                                    # Use leader-aware call for join
                                    join_resp = self._call_leader_with_retry(self.stub.JoinChannel, join_req, timeout=10.0)
                                    
                                    if join_resp.success:
                                        self.current_channel = channel.channel_id
                                        self.current_channel_name = "general"
                                        print(f"✓ Joined #general")
                                        return True
                                    else:
                                        print(f"⚠️  Could not join general: {join_resp.message}")
                                        print(f"    You can manually join later: 'join general'")
                                        return False
                                except Exception as e:
                                    # Don't fail login if auto-join fails
                                    print(f"⚠️  Auto-join failed, but login successful!")
                                    print(f"    Manually join a channel: 'join general'")
                                    return False
                        
                        # General channel not found
                        print("⚠️  General channel not found")
                        available = ", ".join([c.name for c in response.channels[:3]])
                        print(f"    Available channels: {available}")
                        return False
                    else:
                        # Response unsuccessful, retry
                        if attempt < 2:
                            time.sleep(0.5 * (attempt + 1))
                            continue
                        print("⚠️  Could not get channels list")
                        print("    Use 'channels' to list available channels")
                        return False
                        
                except grpc.RpcError as e:
                    # gRPC error, retry
                    if attempt < 2:
                        if e.code() == grpc.StatusCode.UNAVAILABLE:
                            print(f"⚠️  Connection issue, retrying ({attempt+1}/3)...")
                        time.sleep(0.5 * (attempt + 1))
                        # Try to reconnect to leader
                        self._ensure_connected_to_leader()
                        continue
                    else:
                        # Final attempt failed
                        print("⚠️  Could not auto-join channel (connection issues)")
                        print("    Manually join later: 'join general'")
                        return False
                        
        except Exception as e:
            print(f"⚠️  Auto-join skipped: {str(e)[:40]}")
            print("    Use 'channels' to list and 'join <channel>' to join")
            return False
    
    def _show_recent_messages(self, limit: int = 10):
        """Show recent messages from channel"""
        try:
            request = raft_node_pb2.GetMessagesRequest(
                token=self.token,
                channel_id=self.current_channel,
                limit=limit,
                offset=0
            )
            response = self.stub.GetMessages(request, timeout=5.0)
            
            if not response.success:
                print("⚠️  Could not fetch messages (session may be invalid)")
                return
            
            if response.messages:
                print(f"\n📜 Recent Messages (last {limit}):")
                print("-" * 50)
                for msg in response.messages:
                    timestamp = datetime.fromtimestamp(msg.timestamp / 1000).strftime("%H:%M")
                    print(f"[{timestamp}] {msg.sender_name}: {msg.content}")
                print("-" * 50)
                print(f"Total: {len(response.messages)} messages")
            else:
                print("No messages yet. Be the first to say something!")
        except Exception as e:
            print(f"Error: {str(e)[:60]}")
    
    def emptyline(self):
        """Don't repeat last command on empty line"""
        pass
    
    def default(self, line):
        """Handle unknown commands"""
        print(f"Unknown command: {line}")
        print("Type 'help' for available commands")


def main():
    """Main function to run the chat client"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Raft Chat Client")
    parser.add_argument(
        "--server",
        default="localhost:50051",
        help="Initial server address (default: localhost:50051)"
    )
    args = parser.parse_args()
    
    try:
        client = ChatClient(args.server)
        print("\n✓ Ready! Type 'login <username>' or 'signup' to begin\n")
        sys.stdout.flush()  # Force flush output buffer
        client.cmdloop()
    except KeyboardInterrupt:
        print("\n\nGoodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()