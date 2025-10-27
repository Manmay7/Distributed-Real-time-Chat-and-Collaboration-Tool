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
import uuid

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generated import chat_service_pb2, chat_service_pb2_grpc
from generated import llm_service_pb2, llm_service_pb2_grpc

class ChatClient(cmd.Cmd):
    intro = """
    ╔══════════════════════════════════════════════╗
    ║     Distributed Chat & Collaboration Tool    ║
    ║    Real-time Messages | DMs | File Transfer  ║
    ╚══════════════════════════════════════════════╝
    
    New users: 'signup' | Existing: 'login <username>'
    Type 'help' or 'help_all' for commands
    """
    prompt = '(chat) > '
    
    def __init__(self, server_address: str = "localhost:50051", llm_address: str = "localhost:50055"):
        super().__init__()
        self.server_address = server_address
        self.llm_address = llm_address
        self.channel = None
        self.stub = None
        self.token = None
        self.username = None
        self.current_channel = None
        self.current_channel_name = None
        self.running = True
        self.stream_thread = None
        self.dm_mode = False
        self.dm_partner = None
        self.unread_dms = {}
        
        # Downloads folder will be set after login
        self.downloads_dir = None
        
        # LLM connection
        self.llm_channel = None
        self.llm_stub = None
        
        self._connect()
        self._connect_llm()
    
    def _connect(self):
        """Connect to the gRPC server"""
        try:
            self.channel = grpc.insecure_channel(self.server_address)
            self.stub = chat_service_pb2_grpc.ChatServiceStub(self.channel)
            print(f"Connected to chat server at {self.server_address}")
            print(f"Downloads folder: {self.downloads_dir}/")
        except Exception as e:
            print(f"Failed to connect to chat server: {e}")
            sys.exit(1)
    
    def _connect_llm(self):
        """Connect to the LLM server"""
        try:
            self.llm_channel = grpc.insecure_channel(self.llm_address)
            self.llm_stub = llm_service_pb2_grpc.LLMServiceStub(self.llm_channel)
            print(f"Connected to LLM server at {self.llm_address}")
        except Exception as e:
            print(f"Warning: LLM server unavailable")
    
    def _start_message_stream(self):
        """Start streaming messages in background"""
        if self.stream_thread and self.stream_thread.is_alive():
            return
        
        self.stream_thread = threading.Thread(target=self._stream_messages, daemon=True)
        self.stream_thread.start()
    
    def _stream_messages(self):
        """Stream real-time messages from server"""
        try:
            request = chat_service_pb2.StreamRequest(
                token=self.token,
                channel_ids=[],
                include_direct_messages=True
            )
            
            for event in self.stub.StreamMessages(request):
                if event.event_type == "message":
                    self._handle_channel_message(event)
                elif event.event_type == "dm":
                    self._handle_direct_message(event)
                elif event.event_type == "file_uploaded":
                    self._handle_file_upload(event)
                
        except Exception as e:
            if self.running:
                print(f"\nStream disconnected: {e}")
    
    def _handle_channel_message(self, event):
        """Handle incoming channel message"""
        msg = event.message
        if msg.channel_id == self.current_channel and not self.dm_mode:
            timestamp = datetime.now().strftime("%H:%M")
            print(f"\n[{timestamp}] {msg.sender_name}: {msg.content}")
            print(self.prompt, end='', flush=True)
    
    def _handle_direct_message(self, event):
        """Handle incoming DM"""
        dm = event.direct_message
        sender = dm.sender_name
        
        if self.dm_mode and self.dm_partner == sender:
            timestamp = datetime.now().strftime("%H:%M")
            print(f"\n[{timestamp}] {sender}: {dm.content}")
            print(self.prompt, end='', flush=True)
        else:
            self.unread_dms[sender] = self.unread_dms.get(sender, 0) + 1
            print(f"\nNew DM from {sender}: {dm.content[:50]}...")
            print(f"   Type 'dm {sender}' to reply")
            print(self.prompt, end='', flush=True)
    
    def _handle_file_upload(self, event):
        """Handle file upload notification"""
        file_meta = event.file
        if event.channel_id == self.current_channel and not self.dm_mode:
            print(f"\n📎 {file_meta.uploader_name} uploaded: {file_meta.file_name} ({file_meta.file_size} bytes)")
            print(f"   Download with: download_file {file_meta.file_id}")
            print(self.prompt, end='', flush=True)
    
    def do_signup(self, arg):
        """Create new account: signup"""
        if self.token:
            print("Already logged in. Logout first.")
            return
        
        print("\nCreate New Account")
        print("-" * 30)
        
        try:
            username = input("Username (3-20 chars): ").strip()
            if not username:
                print("Username required")
                return
            
            email = input("Email: ").strip()
            if not email:
                print("Email required")
                return
            
            display_name = input("Display name (optional): ").strip() or username
            password = getpass.getpass("Password (6+ chars): ")
            confirm_password = getpass.getpass("Confirm password: ")
            
            if password != confirm_password:
                print("Passwords don't match")
                return
            
            print("\nCreating account...")
            request = chat_service_pb2.SignupRequest(
                username=username, password=password,
                email=email, display_name=display_name
            )
            
            response = self.stub.Signup(request)
            
            if response.success:
                print(f"  {response.message}")
                print(f"  Username: {response.user_info.username}")
                print(f"  Display Name: {response.user_info.display_name}")
                print("\nYou can now login!")
            else:
                print(f"Signup failed: {response.message}")
                
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
            return
        
        username = arg.strip()
        password = getpass.getpass("Password: ")
        
        try:
            request = chat_service_pb2.LoginRequest(username=username, password=password)
            response = self.stub.Login(request)
            
            if response.success:
                self.token = response.token
                self.username = username
                print(f"Logged in as {username}")
                print(f"  Display: {response.user_info.display_name}")
                
                self._join_default_channel()
                self._start_message_stream()
                self._check_conversations()
            else:
                print(f"Login failed: {response.message}")
        except Exception as e:
            print(f"Error: {e}")
    
    def do_logout(self, arg):
        """Logout"""
        if not self.token:
            print("Not logged in")
            return
        
        try:
            self.running = False
            request = chat_service_pb2.LogoutRequest(token=self.token)
            response = self.stub.Logout(request)
            
            if response.success:
                print("Logged out")
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
            request = chat_service_pb2.GetChannelsRequest(token=self.token)
            response = self.stub.GetChannels(request)
            
            if response.success:
                print("\nAvailable Channels:")
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
            request = chat_service_pb2.CreateChannelRequest(
                token=self.token,
                channel_name=channel_name,
                description=description,
                is_private=False
            )
            response = self.stub.CreateChannel(request)
            
            if response.success:
                print(f"{response.message}")
                print(f"  You are the admin of #{channel_name}")
            else:
                print(f"Failed: {response.message}")
        except Exception as e:
            print(f"Error: {e}")
    
    def do_add_user(self, arg):
        """Add user to current channel (admin only): add_user <username>"""
        if not self.token or not self.current_channel:
            print("Please login and join a channel first")
            return
        
        if not arg:
            print("Usage: add_user <username>")
            return
        
        username = arg.strip()
        
        try:
            request = chat_service_pb2.ManageChannelRequest(
                token=self.token,
                channel_id=self.current_channel,
                action="add_user",
                parameters={"username": username}
            )
            response = self.stub.ManageChannel(request)
            
            if response.success:
                print(f"{response.message}")
            else:
                print(f"Failed: {response.message}")
        except Exception as e:
            print(f"Error: {e}")
    
    def do_remove_user(self, arg):
        """Remove user from current channel (admin only): remove_user <username>"""
        if not self.token or not self.current_channel:
            print("Please login and join a channel first")
            return
        
        if not arg:
            print("Usage: remove_user <username>")
            return
        
        username = arg.strip()
        
        try:
            request = chat_service_pb2.ManageChannelRequest(
                token=self.token,
                channel_id=self.current_channel,
                action="remove_user",
                parameters={"username": username}
            )
            response = self.stub.ManageChannel(request)
            
            if response.success:
                print(f"{response.message}")
            else:
                print(f"Failed: {response.message}")
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
            # Get list of channels
            channels_req = chat_service_pb2.GetChannelsRequest(token=self.token)
            channels_resp = self.stub.GetChannels(channels_req)
            
            if channels_resp.success:
                for channel in channels_resp.channels:
                    if channel.name.lower() == channel_name.lower():
                        # Join the channel
                        join_req = chat_service_pb2.JoinChannelRequest(
                            token=self.token,
                            channel_id=channel.channel_id
                        )
                        join_resp = self.stub.JoinChannel(join_req)
                        
                        if join_resp.success:
                            self.current_channel = channel.channel_id
                            self.current_channel_name = channel.name
                            self.dm_mode = False
                            print(f"Joined #{channel_name}")
                            self._show_recent_messages()
                        else:
                            print(f"Failed to join: {join_resp.message}")
                        return
                
                print(f"Channel '{channel_name}' not found")
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
                request = chat_service_pb2.DirectMessageRequest(
                    token=self.token,
                    recipient_username=self.dm_partner,
                    content=arg
                )
                response = self.stub.SendDirectMessage(request)
                
                if response.success:
                    timestamp = datetime.now().strftime("%H:%M")
                    print(f"[{timestamp}] You: {arg}")
                else:
                    print(f"Failed: {response.message}")
            else:
                if not self.current_channel:
                    print("Join a channel first or use 'dm <username>'")
                    return
                
                request = chat_service_pb2.PostRequest(
                    token=self.token,
                    type="message",
                    channel_id=self.current_channel,
                    content=arg
                )
                response = self.stub.PostMessage(request)
                
                if response.success:
                    timestamp = datetime.now().strftime("%H:%M")
                    print(f"[{timestamp}] You: {arg}")
                else:
                    print(f"Failed: {response.message}")
        except Exception as e:
            print(f"Error: {e}")
    
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
        
        if recipient in self.unread_dms:
            del self.unread_dms[recipient]
        
        print(f" Direct message with @{recipient}")
        print(f"   Type 'send <message>' to chat")
        print(f"   Type 'back' to return to channels")
        
        try:
            request = chat_service_pb2.GetDirectMessagesRequest(
                token=self.token,
                other_username=recipient,
                limit=20,
                offset=0
            )
            response = self.stub.GetDirectMessages(request)
            
            if response.success and response.messages:
                print("\n Recent messages:")
                print("-" * 50)
                for dm in response.messages:
                    timestamp = datetime.now().strftime("%H:%M")
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
            request = chat_service_pb2.ListConversationsRequest(token=self.token)
            response = self.stub.ListConversations(request)
            
            if response.success:
                if response.conversations:
                    print("\nYour Conversations:")
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
            if self.current_channel_name:
                self.current_channel = None  # Will need to rejoin
                print(f"Exited DM mode. Use 'join {self.current_channel_name}' to return to channel")
            else:
                print("Back to channel mode")
        else:
            print("Already in channel mode")
    
    def do_upload(self, arg):
        """Upload file: upload <filepath>"""
        if not self.token:
            print("Please login first")
            return
        
        if not arg:
            print("Usage: upload <filepath>")
            return
        
        filepath = arg.strip()
        
        if not os.path.exists(filepath):
            print(f"File not found: {filepath}")
            return
        
        try:
            with open(filepath, 'rb') as f:
                file_data = f.read()
            
            file_name = os.path.basename(filepath)
            file_size = len(file_data)
            
            if file_size > 10 * 1024 * 1024:
                print(f"File too large. Max 10MB")
                return
            
            print(f"Uploading {file_name} ({file_size} bytes)...")
            
            if self.dm_mode:
                request = chat_service_pb2.FileUploadRequest(
                    token=self.token,
                    recipient_username=self.dm_partner,
                    file_name=file_name,
                    file_data=file_data
                )
            else:
                if not self.current_channel:
                    print("Join a channel or start a DM first")
                    return
                
                request = chat_service_pb2.FileUploadRequest(
                    token=self.token,
                    channel_id=self.current_channel,
                    file_name=file_name,
                    file_data=file_data
                )
            
            response = self.stub.UploadFile(request)
            
            if response.success:
                print(f"File uploaded: {file_name}")
                print(f"File ID: {response.file_id}")
            else:
                print(f"Upload failed: {response.message}")
                
        except Exception as e:
            print(f"Error: {e}")
    
    def do_download_file(self, arg):
        """Download file: download_file <file_id> [save_as]"""
        if not self.token:
            print("Please login first")
            return
        
        parts = arg.split()
        if not parts:
            print("Usage: download_file <file_id> [save_as]")
            return
        
        file_id = parts[0]
        save_as = parts[1] if len(parts) > 1 else None
        
        try:
            print(f"Downloading file...")
            
            request = chat_service_pb2.FileDownloadRequest(
                token=self.token,
                file_id=file_id
            )
            response = self.stub.DownloadFile(request)
            
            if response.success:
                filename = save_as or response.file_name
                filepath = os.path.join(self.downloads_dir, filename)
                
                with open(filepath, 'wb') as f:
                    f.write(response.file_data)
                
                print(f"✓ Downloaded: {filepath}")
                print(f"  Size: {len(response.file_data)} bytes")
            else:
                print(f"✗ Download failed")
                
        except Exception as e:
            print(f"✗ Error: {e}")
    
    def do_files(self, arg):
        """List files in current channel"""
        if not self.token:
            print("Please login first")
            return
        
        if not self.current_channel or self.dm_mode:
            print("Only works in channels")
            return
        
        try:
            request = chat_service_pb2.ListFilesRequest(
                token=self.token,
                channel_id=self.current_channel
            )
            response = self.stub.ListFiles(request)
            
            if response.success:
                if response.files:
                    print(f"\nFiles in #{self.current_channel_name}:")
                    print("-" * 70)
                    for file in response.files:
                        size_kb = file.file_size / 1024
                        print(f"  {file.file_name}")
                        print(f"    Uploaded by: {file.uploader_name} | Size: {size_kb:.1f}KB")
                        print(f"    ID: {file.file_id}")
                    print("-" * 70)
                else:
                    print("No files in this channel")
        except Exception as e:
            print(f"✗ Error: {e}")
    
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
        """Show all users (online and offline)"""
        if not self.token:
            print("Please login first")
            return
        
        try:
            request = chat_service_pb2.GetOnlineUsersRequest(token=self.token)
            response = self.stub.GetOnlineUsers(request)
            
            if response.success:
                online_users = [u for u in response.users if u.status == "online"]
                offline_users = [u for u in response.users if u.status == "offline"]
                
                print("\n All Users:")
                print("-" * 50)
                
                if online_users:
                    print("ONLINE:")
                    for user in online_users:
                        admin_badge = "👑" if user.is_admin else "  "
                        display = user.display_name if user.display_name != user.username else user.username
                        print(f"  {admin_badge} {display} (@{user.username})")
                
                if offline_users:
                    print("\n OFFLINE:")
                    for user in offline_users:
                        admin_badge = "👑" if user.is_admin else "  "
                        display = user.display_name if user.display_name != user.username else user.username
                        print(f"  {admin_badge} {display} (@{user.username})")
                
                print("-" * 50)
                print(f"Total: {len(online_users)} online, {len(offline_users)} offline")
        except Exception as e:
            print(f"✗ Error: {e}")
    
    def do_clear(self, arg):
        """Clear the screen"""
        os.system('cls' if os.name == 'nt' else 'clear')
        print(self.intro)
    
    def do_help_all(self, arg):
        """Show all available commands"""
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
        print("  join <channel>            - Join a channel")
        print("  send <message>            - Send message to current channel")
        print("  history [limit]           - Show message history")
        
        print("\n" + "="*60)
        print("CHANNEL ADMIN COMMANDS")
        print("="*60)
        print("  add_user <username>       - Add user to current channel")
        print("  remove_user <username>    - Remove user from current channel")
        
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
        print("  upload <filepath>         - Upload file to channel/DM")
        print("  download_file <id> [name] - Download file by ID")
        print("  files                     - List files in current channel")
        
        print("\n" + "="*60)
        print("USER COMMANDS")
        print("="*60)
        print("  users                     - Show all users (online/offline)")
        
        print("\n" + "="*60)
        print("AI/LLM COMMANDS")
        print("="*60)
        print("  ask_llm <question>        - Ask AI a question")
        print("  smart_reply               - Get AI reply suggestions")
        print("  send_reply <number>       - Send AI suggestion")
        print("  summarize [limit]         - Summarize conversation")
        print("  context_help [text]       - Get context suggestions")
        
        print("\n" + "="*60)
        print("OTHER COMMANDS")
        print("="*60)
        print("  clear                     - Clear screen")
        print("  help                      - Show help")
        print("  exit                      - Exit application")
        print("="*60 + "\n")
    
    def do_ask_llm(self, arg):
        """Ask LLM: ask_llm <question>"""
        if not self.llm_stub:
            print("✗ LLM server not available")
            return
        
        if not arg:
            print("Usage: ask_llm <question>")
            return
        
        try:
            print("🤖 Asking LLM...")
            request = llm_service_pb2.LLMRequest(
                request_id=str(uuid.uuid4()),
                query=arg,
                context=[]
            )
            
            response = self.llm_stub.GetLLMAnswer(request)
            print(f"\n🤖 LLM Response:")
            print(f"   {response.answer}")
            print(f"   Confidence: {response.confidence:.2f}\n")
            
        except Exception as e:
            print(f"✗ LLM Error: {e}")
    
    def do_smart_reply(self, arg):
        """Get smart reply suggestions"""
        if not self.llm_stub:
            print("✗ LLM server not available")
            return
        
        if not self.token or not self.current_channel or self.dm_mode:
            print("Only works in channels with message history")
            return
        
        try:
            print("💡 Getting smart replies...")
            
            msg_request = chat_service_pb2.GetRequest(
                token=self.token,
                type="messages",
                channel_id=self.current_channel,
                limit=5,
                offset=0
            )
            msg_response = self.stub.GetMessages(msg_request)
            
            if msg_response.success and msg_response.messages:
                llm_messages = []
                for msg in msg_response.messages:
                    llm_msg = llm_service_pb2.ChatMessage(
                        sender=msg.sender_name,
                        content=msg.content,
                        timestamp=int(time.time())
                    )
                    llm_messages.append(llm_msg)
                
                request = llm_service_pb2.SmartReplyRequest(
                    request_id=str(uuid.uuid4()),
                    recent_messages=llm_messages,
                    user_id=self.username
                )
                
                response = self.llm_stub.GetSmartReply(request)
                
                print(f"\n💡 Smart Reply Suggestions:")
                for i, suggestion in enumerate(response.suggestions, 1):
                    print(f"   {i}. {suggestion}")
                print("\nUse: send_reply <number>")
                
                self._smart_suggestions = response.suggestions
            else:
                print("No recent messages for suggestions")
                
        except Exception as e:
            print(f"✗ Error: {e}")
    
    def do_send_reply(self, arg):
        """Send smart reply: send_reply <number>"""
        if not hasattr(self, '_smart_suggestions'):
            print("Use 'smart_reply' first")
            return
        
        try:
            index = int(arg) - 1
            if 0 <= index < len(self._smart_suggestions):
                suggestion = self._smart_suggestions[index]
                self.do_send(suggestion)
            else:
                print(f"Invalid number. Choose 1-{len(self._smart_suggestions)}")
        except ValueError:
            print("Provide a valid number")
    
    def do_summarize(self, arg):
        """Summarize conversation: summarize [limit]"""
        if not self.llm_stub:
            print("✗ LLM server not available")
            return
        
        if not self.token or not self.current_channel or self.dm_mode:
            print("Only works in channels")
            return
        
        limit = 20
        if arg:
            try:
                limit = int(arg)
            except:
                pass
        
        try:
            print("📋 Summarizing...")
            
            msg_request = chat_service_pb2.GetRequest(
                token=self.token,
                type="messages",
                channel_id=self.current_channel,
                limit=limit,
                offset=0
            )
            msg_response = self.stub.GetMessages(msg_request)
            
            if msg_response.success and msg_response.messages:
                llm_messages = []
                for msg in msg_response.messages:
                    llm_msg = llm_service_pb2.ChatMessage(
                        sender=msg.sender_name,
                        content=msg.content,
                        timestamp=int(time.time())
                    )
                    llm_messages.append(llm_msg)
                
                request = llm_service_pb2.SummarizeRequest(
                    request_id=str(uuid.uuid4()),
                    messages=llm_messages,
                    max_length=200
                )
                
                response = self.llm_stub.SummarizeConversation(request)
                
                print(f"\n📋 Summary:")
                print(f"   {response.summary}")
                if response.key_points:
                    print(f"\n🔑 Key Points:")
                    for point in response.key_points:
                        print(f"   • {point}")
                print()
            else:
                print("No messages to summarize")
                
        except Exception as e:
            print(f"✗ Error: {e}")
    
    def do_context_help(self, arg):
        """Get context suggestions: context_help [text]"""
        if not self.llm_stub:
            print("✗ LLM server not available")
            return
        
        if not self.token or not self.current_channel or self.dm_mode:
            print("Only works in channels")
            return
        
        try:
            print("🔍 Getting suggestions...")
            
            msg_request = chat_service_pb2.GetRequest(
                token=self.token,
                type="messages",
                channel_id=self.current_channel,
                limit=5,
                offset=0
            )
            msg_response = self.stub.GetMessages(msg_request)
            
            llm_messages = []
            if msg_response.success and msg_response.messages:
                for msg in msg_response.messages:
                    llm_msg = llm_service_pb2.ChatMessage(
                        sender=msg.sender_name,
                        content=msg.content,
                        timestamp=int(time.time())
                    )
                    llm_messages.append(llm_msg)
            
            request = llm_service_pb2.ContextRequest(
                request_id=str(uuid.uuid4()),
                context=llm_messages,
                current_input=arg if arg else ""
            )
            
            response = self.llm_stub.GetContextSuggestions(request)
            
            print(f"\n🔍 Context Suggestions:")
            for suggestion in response.suggestions:
                print(f"   • {suggestion}")
            
            if response.topics:
                print(f"\n📝 Topics:")
                for topic in response.topics:
                    print(f"   • {topic}")
            print()
                    
        except Exception as e:
            print(f"✗ Error: {e}")
    
    def do_exit(self, arg):
        """Exit the application"""
        if self.token:
            self.do_logout("")
        print("Goodbye! 👋")
        return True
    
    # def do_quit(self, arg):
    #     """Exit the application"""
    #     return self.do_exit(arg)
    
    def _join_default_channel(self):
        """Auto-join general channel"""
        try:
            request = chat_service_pb2.GetChannelsRequest(token=self.token)
            response = self.stub.GetChannels(request)
            
            if response.success:
                for channel in response.channels:
                    if channel.name == "general":
                        # Actually join the channel
                        join_req = chat_service_pb2.JoinChannelRequest(
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
            print(f"⚠ Could not auto-join general: {e}")
    
    def _check_conversations(self):
        """Check for unread DMs on login"""
        try:
            request = chat_service_pb2.ListConversationsRequest(token=self.token)
            response = self.stub.ListConversations(request)
            
            if response.success:
                unread_count = sum(conv.unread_count for conv in response.conversations)
                if unread_count > 0:
                    print(f"\n💬 You have {unread_count} unread DM(s)")
                    print("   Type 'conversations' to view")
        except Exception as e:
            pass
    
    def _show_recent_messages(self, limit: int = 10):
        """Show recent messages from channel"""
        try:
            request = chat_service_pb2.GetRequest(
                token=self.token,
                type="messages",
                channel_id=self.current_channel,
                limit=limit,
                offset=0
            )
            response = self.stub.GetMessages(request)
            
            if response.success:
                if response.messages:
                    print(f"\n📝 Recent Messages (last {limit}):")
                    print("-" * 50)
                    for msg in response.messages:
                        timestamp = datetime.now().strftime("%H:%M")
                        print(f"[{timestamp}] {msg.sender_name}: {msg.content}")
                    print("-" * 50)
                else:
                    print("No messages yet")
        except Exception as e:
            print(f"✗ Error: {e}")
    
    def emptyline(self):
        """Don't repeat last command on empty line"""
        pass
    
    def default(self, line):
        """Handle unknown commands"""
        print(f"Unknown command: {line}")
        print("Type 'help' or 'help_all' for available commands")
    
    def precmd(self, line):
        """Called before executing command"""
        return line
    
    def postcmd(self, stop, line):
        """Called after executing command"""
        return stop


def main():
    """Main function to run the chat client"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Chat Client - Real-time, DMs, Files, AI")
    parser.add_argument(
        "--server",
        default="localhost:50051",
        help="Chat server address (default: localhost:50051)"
    )
    parser.add_argument(
        "--llm-server",
        default="localhost:50055",
        help="LLM server address (default: localhost:50055)"
    )
    args = parser.parse_args()
    
    try:
        client = ChatClient(args.server, args.llm_server)
        client.cmdloop()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Goodbye! 👋")
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
