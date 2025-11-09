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

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generated.raft_node_pb2 as raft_node_pb2
import generated.raft_node_pb2_grpc as raft_node_pb2_grpc

class ChatClient(cmd.Cmd):
    intro = """
    ╔══════════════════════════════════════════════╗
    ║     Distributed Chat & Collaboration Tool    ║
    ║         Raft Consensus + Real-time Chat      ║
    ╚══════════════════════════════════════════════╝
    
    Commands: 'signup' | 'login <username>' | 'help'
    Test users: alice/alice123, bob/bob123, admin/admin123
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
        
        self._connect_to_raft_leader()
    
    def _connect_to_raft_leader(self):
        """Find and connect to Raft leader"""
        print("🔍 Discovering Raft leader...")
        
        for attempt in range(5):
            for node_addr in self.cluster_nodes:
                try:
                    channel = grpc.insecure_channel(node_addr)
                    stub = raft_node_pb2_grpc.RaftNodeStub(channel)
                    
                    response = stub.GetLeaderInfo(raft_node_pb2.GetLeaderRequest(), timeout=2.0)
                    
                    if response.is_leader:
                        print(f"✓ Found leader at {node_addr} (Node {response.leader_id}, Term {response.term})")
                        self.channel = channel
                        self.stub = stub
                        self.server_address = node_addr
                        return True
                    elif response.leader_address and response.leader_id > 0:
                        print(f"→ Redirecting to leader at {response.leader_address}")
                        try:
                            leader_channel = grpc.insecure_channel(response.leader_address)
                            leader_stub = raft_node_pb2_grpc.RaftNodeStub(leader_channel)
                            
                            verify = leader_stub.GetLeaderInfo(raft_node_pb2.GetLeaderRequest(), timeout=2.0)
                            if verify.is_leader:
                                print(f"✓ Connected to leader at {response.leader_address}")
                                self.channel = leader_channel
                                self.stub = leader_stub
                                self.server_address = response.leader_address
                                channel.close()
                                return True
                        except Exception as e:
                            print(f"  Failed to connect to reported leader: {e}")
                    
                    channel.close()
                except Exception as e:
                    continue
            
            if attempt < 4:
                print(f"⚠️  No leader found, waiting 2s before retry {attempt+1}/5...")
                time.sleep(2)
        
        print("\n❌ Could not find Raft leader")
        print("   Make sure all 3 Raft nodes are running:")
        print("   python server/raft_node.py --node-id 1 --port 50051")
        print("   python server/raft_node.py --node-id 2 --port 50052")
        print("   python server/raft_node.py --node-id 3 --port 50053")
        sys.exit(1)
    
    def _reconnect_to_leader(self) -> bool:
        """Reconnect to current Raft leader"""
        logger_backup = self.username  # Remember who we are
        
        print("\n⚠️  Connection lost. Finding new leader...")
        
        for attempt in range(3):
            for node_addr in self.cluster_nodes:
                try:
                    test_channel = grpc.insecure_channel(node_addr)
                    test_stub = raft_node_pb2_grpc.RaftNodeStub(test_channel)
                    
                    response = test_stub.GetLeaderInfo(raft_node_pb2.GetLeaderRequest(), timeout=2.0)
                    
                    if response.is_leader:
                        print(f"✓ Reconnected to new leader at {node_addr}")
                        
                        # Close old connection
                        if self.channel:
                            self.channel.close()
                        
                        self.channel = test_channel
                        self.stub = test_stub
                        self.server_address = node_addr
                        return True
                    
                    test_channel.close()
                    
                except:
                    continue
            
            if attempt < 2:
                print(f"  Retry {attempt+1}/3...")
                time.sleep(1)
        
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
           
            response = self._call_with_retry(self.stub.Signup, request, timeout=5.0)
            
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
                self.dm_mode = False
        except Exception as e:
            print(f"Error: {e}")
    
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
                for channel in response.channels:
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
            response = self._call_with_retry(self.stub.CreateChannel, request, timeout=5.0)
            
            if response.success:
                print(f"✓ {response.message}")
            else:
                print(f"❌ Failed: {response.message}")
        except Exception as e:
            print(f"Error: {e}")
    
    def do_join(self, arg):
        """Join channel: join <channel_name>"""
        if not self.token:
            print("Please login first")
            return
        
        if not arg:
            print("Usage: join <channel_name>")
            return
        
        channel_name = arg.strip()
        
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
                        join_resp = self.stub.JoinChannel(join_req)
                        
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
                response = self._call_with_retry(self.stub.SendDirectMessage, request, timeout=5.0)
                
                if response.success:
                    timestamp = datetime.now().strftime("%H:%M")
                    print(f"[{timestamp}] You: {arg}")
                else:
                    print(f"❌ Failed: {response.message}")
            else:
                if not self.current_channel:
                    print("Join a channel first or use 'dm <username>'")
                    return
                
                request = raft_node_pb2.SendMessageRequest(
                    token=self.token,
                    channel_id=self.current_channel,
                    content=arg
                )
                response = self._call_with_retry(self.stub.SendMessage, request, timeout=5.0)
                
                if response.success:
                    timestamp = datetime.now().strftime("%H:%M")
                    print(f"[{timestamp}] You: {arg}")
                else:
                    print(f"❌ Failed: {response.message}")
        except Exception as e:
            print(f"Error: {e}")
            print("Tip: Try 'status' to check cluster health")
    
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
            request = raft_node_pb2.GetDirectMessagesRequest(
                token=self.token,
                other_username=recipient,
                limit=20,
                offset=0
            )
            response = self.stub.GetDirectMessages(request)
            
            if response.success and response.messages:
                print("\n📜 Recent messages:")
                print("-" * 50)
                for dm in response.messages:
                    timestamp = datetime.fromtimestamp(dm.timestamp / 1000).strftime("%H:%M")
                    sender = "You" if dm.sender_name == self.username else dm.sender_name
                    print(f"[{timestamp}] {sender}: {dm.content}")
                print("-" * 50)
        except Exception as e:
            print(f"Could not load history: {e}")
    
    def do_conversations(self, arg):
        """List all DM conversations"""
        if not self.token:
            print("Please login first")
            return
        
        try:
            request = raft_node_pb2.ListConversationsRequest(token=self.token)
            response = self.stub.ListConversations(request)
            
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
            print(f"Error: {e}")
    
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
        if not self.token or not self.current_channel or self.dm_mode:
            print("Join a channel first")
            return
        
        limit = 20
        if arg:
            try:
                limit = int(arg)
            except:
                pass
        
        self._show_recent_messages(limit)
    
    def do_users(self, arg):
        """Show all users"""
        if not self.token:
            print("Please login first")
            return
        
        try:
            request = raft_node_pb2.GetOnlineUsersRequest(token=self.token)
            response = self.stub.GetOnlineUsers(request)
            
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
        except Exception as e:
            print(f"Error: {e}")
    
    def do_status(self, arg):
        """Show Raft cluster status"""
        print("\n🖥️  Raft Cluster Status")
        print("=" * 60)
        print(f"Connected to: {self.server_address}")
        print(f"Username: {self.username or 'Not logged in'}")
        if self.current_channel_name:
            print(f"Current channel: #{self.current_channel_name}")
        print(f"\nCluster nodes:")
        
        for node_addr in self.cluster_nodes:
            try:
                channel = grpc.insecure_channel(node_addr)
                stub = raft_node_pb2_grpc.RaftNodeStub(channel)
                response = stub.GetLeaderInfo(raft_node_pb2.GetLeaderRequest(), timeout=1.0)
                
                status = "👑 LEADER" if response.is_leader else f"{response.state.upper()}"
                connected = "✓" if node_addr == self.server_address else " "
                print(f" {connected} {node_addr}: {status} (Term {response.term})")
                
                channel.close()
            except:
                print(f"   {node_addr}: UNREACHABLE")
        
        print("=" * 60)
    
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
                filename = save_as or response.file_name
                filepath = os.path.join(".", filename)
                
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
        """Get smart reply suggestions"""
        if not self.token or not self.current_channel or self.dm_mode:
            print("Only works in channels")
            return
        
        try:
            print("🤖 Getting smart replies...")
            
            request = raft_node_pb2.SmartReplyRequest(
                token=self.token,
                channel_id=self.current_channel,
                recent_message_count=5
            )
            
            response = self.stub.GetSmartReply(request, timeout=10.0)
            
            if response.success and response.suggestions:
                print("\n💡 Smart Reply Suggestions:")
                for i, suggestion in enumerate(response.suggestions, 1):
                    print(f"   {i}. {suggestion}")
                print("\nType the number to send, or type your own message")
            else:
                print("No suggestions available")
                
        except Exception as e:
            print(f"Error: {e}")
    
    def do_summarize(self, arg):
        """Summarize conversation: summarize [count]"""
        if not self.token or not self.current_channel or self.dm_mode:
            print("Only works in channels")
            return
        
        count = 20
        if arg:
            try:
                count = int(arg)
            except:
                pass
        
        try:
            print("🤖 Summarizing conversation...")
            
            request = raft_node_pb2.SummarizeRequest(
                token=self.token,
                channel_id=self.current_channel,
                message_count=count
            )
            
            response = self.stub.SummarizeConversation(request, timeout=15.0)
            
            if response.success:
                print(f"\n📝 Summary:")
                print(f"   {response.summary}")
                if response.key_points:
                    print(f"\n📌 Key Points:")
                    for point in response.key_points:
                        print(f"   • {point}")
                print()
            else:
                print("Failed to summarize")
                
        except Exception as e:
            print(f"Error: {e}")
    
    def do_ask(self, arg):
        """Ask LLM a question: ask <question>"""
        if not self.token:
            print("Please login first")
            return
        
        if not arg:
            print("Usage: ask <question>")
            return
        
        try:
            print("🤖 Thinking...")
            
            request = raft_node_pb2.LLMRequest(
                token=self.token,
                query=arg,
                context=[]
            )
            
            response = self.stub.GetLLMAnswer(request, timeout=15.0)
            
            if response.success:
                print(f"\n💬 Answer:")
                print(f"   {response.answer}\n")
            else:
                print(f"❌ {response.answer}")
                
        except Exception as e:
            print(f"Error: {e}")
    
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
        print("  create_channel <name>  - Create new channel")
        print("  join <channel>         - Join a channel")
        print("  send <message>         - Send message")
        print("  history [limit]        - Show message history")
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
        print()
        print("  users                  - Show all users")
        print("  status                 - Show Raft cluster status")
        print("  clear                  - Clear screen")
        print("  exit                   - Exit application")
        print("="*60 + "\n")
    
    def do_exit(self, arg):
        """Exit the application"""
        if self.token:
            self.do_logout("")
        print("Goodbye!")
        if self.channel:
            self.channel.close()
        return True
    
    def _join_default_channel(self):
        """Auto-join general channel"""
        try:
            request = raft_node_pb2.GetChannelsRequest(token=self.token)
            response = self.stub.GetChannels(request)
            
            if response.success:
                for channel in response.channels:
                    if channel.name == "general":
                        join_req = raft_node_pb2.JoinChannelRequest(
                            token=self.token,
                            channel_id=channel.channel_id
                        )
                        join_resp = self.stub.JoinChannel(join_req)
                        
                        if join_resp.success:
                            self.current_channel = channel.channel_id
                            self.current_channel_name = "general"
                            print(f"✓ Auto-joined #general")
                        break
        except Exception as e:
            print(f"Could not auto-join general: {e}")
    
    def _show_recent_messages(self, limit: int = 10):
        """Show recent messages from channel"""
        try:
            request = raft_node_pb2.GetMessagesRequest(
                token=self.token,
                channel_id=self.current_channel,
                limit=limit,
                offset=0
            )
            response = self.stub.GetMessages(request)
            
            if response.success:
                if response.messages:
                    print(f"\n📜 Recent Messages (last {limit}):")
                    print("-" * 50)
                    for msg in response.messages:
                        timestamp = datetime.fromtimestamp(msg.timestamp / 1000).strftime("%H:%M")
                        print(f"[{timestamp}] {msg.sender_name}: {msg.content}")
                    print("-" * 50)
                else:
                    print("No messages yet. Be the first to say something!")
        except Exception as e:
            print(f"Error: {e}")
    
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
