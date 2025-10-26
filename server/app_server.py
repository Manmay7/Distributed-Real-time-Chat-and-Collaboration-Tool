# server/app_server.py
import grpc
from concurrent import futures
import logging
import argparse
import sys
import os
import uuid
import time
import jwt
import bcrypt
import re
import json
import pickle
from datetime import datetime, timedelta
import threading
from typing import Dict, List, Optional, Set
from queue import Queue
import mimetypes

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generated.chat_service_pb2 as chat_service_pb2
import generated.chat_service_pb2_grpc as chat_service_pb2_grpc
import generated.llm_service_pb2 as llm_service_pb2
import generated.llm_service_pb2_grpc as llm_service_pb2_grpc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MessageBroker:
    """Handles real-time message distribution to connected clients"""
    def __init__(self):
        self.subscribers: Dict[str, Queue] = {}
        self.lock = threading.Lock()
    
    def subscribe(self, user_id: str) -> Queue:
        with self.lock:
            queue = Queue(maxsize=100)
            self.subscribers[user_id] = queue
            logger.info(f"User {user_id} subscribed to real-time messages")
            return queue
    
    def unsubscribe(self, user_id: str):
        with self.lock:
            if user_id in self.subscribers:
                del self.subscribers[user_id]
                logger.info(f"User {user_id} unsubscribed from real-time messages")
    
    def broadcast_to_channel(self, channel_id: str, event: chat_service_pb2.MessageEvent, 
                            channel_members: Set[str], exclude_user: str = None):
        with self.lock:
            for user_id in channel_members:
                if user_id == exclude_user:
                    continue
                if user_id in self.subscribers:
                    try:
                        self.subscribers[user_id].put(event, block=False)
                    except:
                        pass
    
    def send_to_user(self, user_id: str, event: chat_service_pb2.MessageEvent):
        with self.lock:
            if user_id in self.subscribers:
                try:
                    self.subscribers[user_id].put(event, block=False)
                except:
                    pass

class ChatServicer(chat_service_pb2_grpc.ChatServiceServicer):
    def __init__(self, node_id: int, llm_server_address: str):
        self.node_id = node_id
        self.llm_server_address = llm_server_address
        self.is_leader = node_id == 1
        
        # Storage file paths
        self.data_dir = "server_data"
        os.makedirs(self.data_dir, exist_ok=True)
        self.users_file = os.path.join(self.data_dir, "users.pkl")
        self.channels_file = os.path.join(self.data_dir, "channels.pkl")
        
        # Storage
        self.users: Dict[str, dict] = {}
        self.users_by_email: Dict[str, str] = {}
        self.users_by_id: Dict[str, str] = {}
        self.sessions: Dict[str, dict] = {}
        self.channels: Dict[str, dict] = {}
        self.messages: Dict[str, List[dict]] = {}
        self.direct_messages: List[dict] = []
        self.files: Dict[str, dict] = {}
        self.online_users: set = set()
        
        # Real-time messaging
        self.message_broker = MessageBroker()
        
        # JWT secret
        self.jwt_secret = "your-secret-key-here"
        
        # Load persisted data
        self._load_data()
        
        # Initialize defaults if needed
        if not self.channels:
            self._init_default_channels()
        if not self.users:
            self._init_test_users()
        
        self._connect_to_llm()
    
    def _load_data(self):
        """Load persisted users and channels"""
        try:
            if os.path.exists(self.users_file):
                with open(self.users_file, 'rb') as f:
                    data = pickle.load(f)
                    self.users = data.get('users', {})
                    self.users_by_email = data.get('users_by_email', {})
                    self.users_by_id = data.get('users_by_id', {})
                logger.info(f"Loaded {len(self.users)} users from disk")
            
            if os.path.exists(self.channels_file):
                with open(self.channels_file, 'rb') as f:
                    self.channels = pickle.load(f)
                    # Initialize members as set if loaded as list
                    for channel in self.channels.values():
                        if isinstance(channel['members'], list):
                            channel['members'] = set(channel['members'])
                logger.info(f"Loaded {len(self.channels)} channels from disk")
        except Exception as e:
            logger.error(f"Error loading data: {e}")
    
    def _save_users(self):
        """Persist users to disk"""
        try:
            data = {
                'users': self.users,
                'users_by_email': self.users_by_email,
                'users_by_id': self.users_by_id
            }
            with open(self.users_file, 'wb') as f:
                pickle.dump(data, f)
            logger.info("Users saved to disk")
        except Exception as e:
            logger.error(f"Error saving users: {e}")
    
    def _save_channels(self):
        """Persist channels to disk"""
        try:
            # Convert sets to lists for serialization
            channels_copy = {}
            for cid, channel in self.channels.items():
                channel_copy = channel.copy()
                channel_copy['members'] = list(channel['members'])
                channels_copy[cid] = channel_copy
            
            with open(self.channels_file, 'wb') as f:
                pickle.dump(channels_copy, f)
            logger.info("Channels saved to disk")
        except Exception as e:
            logger.error(f"Error saving channels: {e}")
    
    def _init_default_channels(self):
        """Initialize default channels"""
        default_channels = ["general", "random", "development"]
        for channel_name in default_channels:
            channel_id = str(uuid.uuid4())
            self.channels[channel_id] = {
                "id": channel_id,
                "name": channel_name,
                "description": f"Default {channel_name} channel",
                "is_private": False,
                "members": set(),
                "admins": set(["system"]),  # Channel admins
                "created_at": datetime.utcnow(),
                "created_by": "system"
            }
            self.messages[channel_id] = []
            logger.info(f"Created default channel: {channel_name}")
        self._save_channels()
    
    def _init_test_users(self):
        """Initialize test users"""
        test_users = [
            {"username": "admin", "password": "admin123", "email": "admin@chat.com", "is_admin": True, "display_name": "Administrator"},
            {"username": "user1", "password": "user123", "email": "user1@chat.com", "is_admin": False, "display_name": "User One"},
            {"username": "user2", "password": "user123", "email": "user2@chat.com", "is_admin": False, "display_name": "User Two"},
        ]
        
        for user_data in test_users:
            user_id = str(uuid.uuid4())
            hashed_password = bcrypt.hashpw(user_data["password"].encode('utf-8'), bcrypt.gensalt())
            self.users[user_data["username"]] = {
                "id": user_id,
                "username": user_data["username"],
                "password": hashed_password,
                "email": user_data["email"],
                "display_name": user_data["display_name"],
                "is_admin": user_data["is_admin"],
                "created_at": datetime.utcnow(),
                "status": "offline",
                "last_seen": datetime.utcnow()
            }
            self.users_by_email[user_data["email"]] = user_data["username"]
            self.users_by_id[user_id] = user_data["username"]
            logger.info(f"Created test user: {user_data['username']}")
        self._save_users()
    
    def _connect_to_llm(self):
        """Connect to LLM server"""
        try:
            self.llm_channel = grpc.insecure_channel(self.llm_server_address)
            self.llm_stub = llm_service_pb2_grpc.LLMServiceStub(self.llm_channel)
            logger.info(f"Connected to LLM server at {self.llm_server_address}")
        except Exception as e:
            logger.error(f"Failed to connect to LLM server: {e}")
    
    def _generate_token(self, user_id: str, username: str) -> str:
        """Generate JWT token"""
        payload = {
            "user_id": user_id,
            "username": username,
            "exp": datetime.utcnow() + timedelta(hours=24),
            "iat": datetime.utcnow()
        }
        return jwt.encode(payload, self.jwt_secret, algorithm="HS256")
    
    def _verify_token(self, token: str) -> Optional[dict]:
        """Verify JWT token"""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=["HS256"])
            return payload
        except:
            return None
    
    def _validate_email(self, email: str) -> bool:
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    def _validate_username(self, username: str) -> bool:
        if not username or len(username) < 3 or len(username) > 20:
            return False
        return re.match(r'^[a-zA-Z0-9_]+$', username) is not None
    
    def _validate_password(self, password: str) -> tuple:
        if len(password) < 6:
            return False, "Password must be at least 6 characters long"
        if len(password) > 50:
            return False, "Password must be less than 50 characters"
        if not re.search(r'[0-9!@#$%^&*(),.?":{}|<>]', password):
            return False, "Password must contain at least one number or special character"
        return True, "Password is valid"
    
    def Signup(self, request, context):
        """Handle user signup"""
        username = request.username.strip()
        password = request.password
        email = request.email.strip().lower()
        display_name = request.display_name.strip() if request.display_name else username
        
        logger.info(f"Signup attempt for user: {username}")
        
        if not username or not password or not email:
            return chat_service_pb2.SignupResponse(
                success=False, message="Username, password, and email are required", code=400
            )
        
        if not self._validate_username(username):
            return chat_service_pb2.SignupResponse(
                success=False, message="Username must be 3-20 characters, alphanumeric and underscore only", code=400
            )
        
        if not self._validate_email(email):
            return chat_service_pb2.SignupResponse(
                success=False, message="Invalid email format", code=400
            )
        
        password_valid, password_msg = self._validate_password(password)
        if not password_valid:
            return chat_service_pb2.SignupResponse(success=False, message=password_msg, code=400)
        
        if username in self.users:
            return chat_service_pb2.SignupResponse(success=False, message="Username already exists", code=409)
        
        if email in self.users_by_email:
            return chat_service_pb2.SignupResponse(success=False, message="Email already registered", code=409)
        
        try:
            user_id = str(uuid.uuid4())
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
            
            user_data = {
                "id": user_id,
                "username": username,
                "password": hashed_password,
                "email": email,
                "display_name": display_name,
                "is_admin": False,
                "created_at": datetime.utcnow(),
                "status": "offline",
                "last_seen": datetime.utcnow()
            }
            
            self.users[username] = user_data
            self.users_by_email[email] = username
            self.users_by_id[user_id] = username
            self._save_users()  # Persist to disk
            
            user_info = chat_service_pb2.UserInfo(
                user_id=user_id, username=username, is_admin=False,
                status="offline", display_name=display_name, email=email
            )
            
            logger.info(f"User {username} registered successfully and saved to disk")
            
            return chat_service_pb2.SignupResponse(
                success=True, message="Account created successfully!", code=201, user_info=user_info
            )
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            return chat_service_pb2.SignupResponse(
                success=False, message="Failed to create account", code=500
            )
    
    def Login(self, request, context):
        """Handle user login"""
        username = request.username
        password = request.password
        
        if username not in self.users:
            return chat_service_pb2.LoginResponse(success=False, message="Invalid username or password")
        
        user = self.users[username]
        
        if not bcrypt.checkpw(password.encode('utf-8'), user["password"]):
            return chat_service_pb2.LoginResponse(success=False, message="Invalid username or password")
        
        token = self._generate_token(user["id"], username)
        
        self.sessions[token] = {
            "user_id": user["id"],
            "username": username,
            "login_time": datetime.utcnow(),
            "last_activity": datetime.utcnow()
        }
        
        user["status"] = "online"
        user["last_seen"] = datetime.utcnow()
        self.online_users.add(username)
        self._save_users()  # Save status change
        
        self._auto_join_general_channel(username, user["id"])
        
        user_info = chat_service_pb2.UserInfo(
            user_id=user["id"], username=username, is_admin=user["is_admin"],
            status="online", display_name=user.get("display_name", username),
            email=user.get("email", "")
        )
        
        logger.info(f"User {username} logged in")
        
        return chat_service_pb2.LoginResponse(
            success=True, token=token, message="Login successful", user_info=user_info
        )
    
    def _auto_join_general_channel(self, username: str, user_id: str):
        """Auto-join to general channel"""
        for channel_id, channel in self.channels.items():
            if channel["name"] == "general":
                channel["members"].add(user_id)
                self._save_channels()
                logger.info(f"Auto-joined {username} to general")
                break
    
    def CreateChannel(self, request, context):
        """Create a new channel"""
        payload = self._verify_token(request.token)
        if not payload:
            return chat_service_pb2.StatusResponse(success=False, message="Invalid token", code=401)
        
        user_id = payload["user_id"]
        username = payload["username"]
        channel_name = request.channel_name.strip()
        
        if not channel_name or len(channel_name) < 3:
            return chat_service_pb2.StatusResponse(
                success=False, message="Channel name must be at least 3 characters", code=400
            )
        
        # Check if channel already exists
        for channel in self.channels.values():
            if channel["name"].lower() == channel_name.lower():
                return chat_service_pb2.StatusResponse(
                    success=False, message="Channel already exists", code=409
                )
        
        channel_id = str(uuid.uuid4())
        self.channels[channel_id] = {
            "id": channel_id,
            "name": channel_name,
            "description": request.description or f"Channel {channel_name}",
            "is_private": request.is_private,
            "members": {user_id},  # Creator is first member
            "admins": {user_id},  # Creator is admin
            "created_at": datetime.utcnow(),
            "created_by": username
        }
        self.messages[channel_id] = []
        self._save_channels()
        
        logger.info(f"Channel {channel_name} created by {username}")
        
        return chat_service_pb2.StatusResponse(
            success=True, message=f"Channel #{channel_name} created! You are the admin.", code=200
        )
    
    def JoinChannel(self, request, context):
        """Join a channel"""
        payload = self._verify_token(request.token)
        if not payload:
            return chat_service_pb2.StatusResponse(success=False, message="Invalid token", code=401)
        
        user_id = payload["user_id"]
        username = payload["username"]
        channel_id = request.channel_id
        
        if channel_id not in self.channels:
            return chat_service_pb2.StatusResponse(success=False, message="Channel not found", code=404)
        
        channel = self.channels[channel_id]
        channel["members"].add(user_id)
        self._save_channels()
        
        logger.info(f"{username} joined channel {channel['name']}")
        
        return chat_service_pb2.StatusResponse(
            success=True, message=f"Joined #{channel['name']}", code=200
        )
    
    def ManageChannel(self, request, context):
        """Manage channel (add/remove users) - Admin only"""
        payload = self._verify_token(request.token)
        if not payload:
            return chat_service_pb2.StatusResponse(success=False, message="Invalid token", code=401)
        
        user_id = payload["user_id"]
        username = payload["username"]
        channel_id = request.channel_id
        action = request.action
        
        if channel_id not in self.channels:
            return chat_service_pb2.StatusResponse(success=False, message="Channel not found", code=404)
        
        channel = self.channels[channel_id]
        
        # Check if user is admin of this channel
        if user_id not in channel["admins"]:
            return chat_service_pb2.StatusResponse(
                success=False, message="Only channel admins can manage members", code=403
            )
        
        if action == "add_user":
            target_username = request.parameters.get("username")
            if target_username and target_username in self.users:
                target_user_id = self.users[target_username]["id"]
                channel["members"].add(target_user_id)
                self._save_channels()
                return chat_service_pb2.StatusResponse(
                    success=True, message=f"Added {target_username} to channel", code=200
                )
            return chat_service_pb2.StatusResponse(
                success=False, message="User not found", code=404
            )
        
        elif action == "remove_user":
            target_username = request.parameters.get("username")
            if target_username and target_username in self.users:
                target_user_id = self.users[target_username]["id"]
                if target_user_id in channel["admins"]:
                    return chat_service_pb2.StatusResponse(
                        success=False, message="Cannot remove channel admin", code=403
                    )
                channel["members"].discard(target_user_id)
                self._save_channels()
                return chat_service_pb2.StatusResponse(
                    success=True, message=f"Removed {target_username} from channel", code=200
                )
            return chat_service_pb2.StatusResponse(
                success=False, message="User not found", code=404
            )
        
        return chat_service_pb2.StatusResponse(
            success=False, message="Invalid action", code=400
        )
    
    def StreamMessages(self, request, context):
        """Stream real-time messages to client"""
        payload = self._verify_token(request.token)
        if not payload:
            return
        
        user_id = payload["user_id"]
        username = payload["username"]
        
        queue = self.message_broker.subscribe(user_id)
        logger.info(f"User {username} started streaming messages")
        
        try:
            while context.is_active():
                try:
                    event = queue.get(timeout=30)
                    yield event
                except:
                    pass
        finally:
            self.message_broker.unsubscribe(user_id)
            logger.info(f"User {username} stopped streaming")
    
    def PostMessage(self, request, context):
        """Post message to channel"""
        payload = self._verify_token(request.token)
        if not payload:
            return chat_service_pb2.StatusResponse(success=False, message="Invalid token", code=401)
        
        username = payload["username"]
        user_id = payload["user_id"]
        channel_id = request.channel_id
        
        if channel_id not in self.channels:
            return chat_service_pb2.StatusResponse(success=False, message="Channel not found", code=404)
        
        if user_id not in self.channels[channel_id]["members"]:
            return chat_service_pb2.StatusResponse(success=False, message="Not a member of this channel", code=403)
        
        message = {
            "id": str(uuid.uuid4()),
            "sender_id": user_id,
            "sender_name": username,
            "channel_id": channel_id,
            "content": request.content,
            "type": request.type,
            "timestamp": datetime.utcnow()
        }
        
        if channel_id not in self.messages:
            self.messages[channel_id] = []
        self.messages[channel_id].append(message)
        
        # Broadcast to all channel members in real-time
        proto_msg = chat_service_pb2.Message(
            message_id=message["id"],
            sender_id=user_id,
            sender_name=username,
            channel_id=channel_id,
            content=request.content,
            type=request.type
        )
        
        event = chat_service_pb2.MessageEvent(
            event_type="message",
            message=proto_msg,
            channel_id=channel_id
        )
        
        self.message_broker.broadcast_to_channel(
            channel_id, event, self.channels[channel_id]["members"], exclude_user=user_id
        )
        
        logger.info(f"Message from {username} broadcasted to channel {channel_id}")
        
        return chat_service_pb2.StatusResponse(success=True, message="Message sent", code=200)
    
    def SendDirectMessage(self, request, context):
        """Send direct message to user"""
        payload = self._verify_token(request.token)
        if not payload:
            return chat_service_pb2.StatusResponse(success=False, message="Invalid token", code=401)
        
        sender_id = payload["user_id"]
        sender_name = payload["username"]
        recipient_username = request.recipient_username
        
        if recipient_username not in self.users:
            return chat_service_pb2.StatusResponse(success=False, message="User not found", code=404)
        
        recipient = self.users[recipient_username]
        recipient_id = recipient["id"]
        
        dm = {
            "id": str(uuid.uuid4()),
            "sender_id": sender_id,
            "sender_name": sender_name,
            "recipient_id": recipient_id,
            "recipient_name": recipient_username,
            "content": request.content,
            "timestamp": datetime.utcnow(),
            "is_read": False
        }
        
        self.direct_messages.append(dm)
        
        # Send to recipient in real-time if online
        proto_dm = chat_service_pb2.DirectMessage(
            message_id=dm["id"],
            sender_id=sender_id,
            sender_name=sender_name,
            recipient_id=recipient_id,
            recipient_name=recipient_username,
            content=request.content,
            is_read=False
        )
        
        event = chat_service_pb2.MessageEvent(
            event_type="dm",
            direct_message=proto_dm
        )
        
        self.message_broker.send_to_user(recipient_id, event)
        
        logger.info(f"DM from {sender_name} to {recipient_username}")
        
        return chat_service_pb2.StatusResponse(success=True, message="DM sent", code=200)
    
    def GetDirectMessages(self, request, context):
        """Get DM conversation with user"""
        payload = self._verify_token(request.token)
        if not payload:
            return chat_service_pb2.DirectMessageResponse(success=False, messages=[])
        
        user_id = payload["user_id"]
        other_username = request.other_username
        
        if other_username not in self.users:
            return chat_service_pb2.DirectMessageResponse(success=False, messages=[])
        
        other_user_id = self.users[other_username]["id"]
        
        conversation = []
        for dm in self.direct_messages:
            if (dm["sender_id"] == user_id and dm["recipient_id"] == other_user_id) or \
               (dm["sender_id"] == other_user_id and dm["recipient_id"] == user_id):
                conversation.append(dm)
        
        conversation.sort(key=lambda x: x["timestamp"])
        
        proto_messages = []
        for dm in conversation[-request.limit if request.limit > 0 else len(conversation):]:
            proto_dm = chat_service_pb2.DirectMessage(
                message_id=dm["id"],
                sender_id=dm["sender_id"],
                sender_name=dm["sender_name"],
                recipient_id=dm["recipient_id"],
                recipient_name=dm["recipient_name"],
                content=dm["content"],
                is_read=dm["is_read"]
            )
            proto_messages.append(proto_dm)
        
        return chat_service_pb2.DirectMessageResponse(success=True, messages=proto_messages)
    
    def ListConversations(self, request, context):
        """List all DM conversations for user"""
        payload = self._verify_token(request.token)
        if not payload:
            return chat_service_pb2.ConversationsResponse(success=False, conversations=[])
        
        user_id = payload["user_id"]
        
        partners = set()
        for dm in self.direct_messages:
            if dm["sender_id"] == user_id:
                partners.add(dm["recipient_id"])
            elif dm["recipient_id"] == user_id:
                partners.add(dm["sender_id"])
        
        conversations = []
        for partner_id in partners:
            partner_username = self.users_by_id.get(partner_id)
            if partner_username:
                partner = self.users[partner_username]
                
                unread = sum(1 for dm in self.direct_messages 
                            if dm["recipient_id"] == user_id and dm["sender_id"] == partner_id and not dm["is_read"])
                
                conv = chat_service_pb2.Conversation(
                    username=partner_username,
                    display_name=partner.get("display_name", partner_username),
                    unread_count=unread
                )
                conversations.append(conv)
        
        return chat_service_pb2.ConversationsResponse(success=True, conversations=conversations)
    
    def UploadFile(self, request, context):
        """Upload file"""
        payload = self._verify_token(request.token)
        if not payload:
            return chat_service_pb2.FileUploadResponse(success=False, message="Invalid token")
        
        user_id = payload["user_id"]
        username = payload["username"]
        
        file_id = str(uuid.uuid4())
        file_name = request.file_name
        file_data = request.file_data
        mime_type = request.mime_type or mimetypes.guess_type(file_name)[0] or "application/octet-stream"
        
        self.files[file_id] = {
            "id": file_id,
            "name": file_name,
            "data": file_data,
            "size": len(file_data),
            "mime_type": mime_type,
            "uploader_id": user_id,
            "uploader_name": username,
            "channel_id": request.channel_id if request.channel_id else None,
            "recipient": request.recipient_username if request.recipient_username else None,
            "description": request.description,
            "uploaded_at": datetime.utcnow()
        }
        
        file_url = f"file://{file_id}"
        
        if request.channel_id:
            file_metadata = chat_service_pb2.FileMetadata(
                file_id=file_id,
                file_name=file_name,
                uploader_name=username,
                file_size=len(file_data),
                mime_type=mime_type,
                channel_id=request.channel_id
            )
            
            event = chat_service_pb2.MessageEvent(
                event_type="file_uploaded",
                file=file_metadata,
                channel_id=request.channel_id
            )
            
            self.message_broker.broadcast_to_channel(
                request.channel_id, event, 
                self.channels[request.channel_id]["members"], 
                exclude_user=user_id
            )
        
        logger.info(f"File {file_name} uploaded by {username}")
        
        return chat_service_pb2.FileUploadResponse(
            success=True,
            message="File uploaded successfully",
            file_id=file_id,
            file_url=file_url
        )
    
    def DownloadFile(self, request, context):
        """Download file"""
        payload = self._verify_token(request.token)
        if not payload:
            return chat_service_pb2.FileResponse(success=False)
        
        file_id = request.file_id
        
        if file_id not in self.files:
            return chat_service_pb2.FileResponse(success=False)
        
        file_data = self.files[file_id]
        
        return chat_service_pb2.FileResponse(
            success=True,
            file_name=file_data["name"],
            file_data=file_data["data"],
            mime_type=file_data["mime_type"]
        )
    
    def ListFiles(self, request, context):
        """List files in channel"""
        payload = self._verify_token(request.token)
        if not payload:
            return chat_service_pb2.FileListResponse(success=False, files=[])
        
        channel_id = request.channel_id
        
        file_list = []
        for file_id, file_data in self.files.items():
            if file_data.get("channel_id") == channel_id:
                metadata = chat_service_pb2.FileMetadata(
                    file_id=file_id,
                    file_name=file_data["name"],
                    uploader_name=file_data["uploader_name"],
                    file_size=file_data["size"],
                    mime_type=file_data["mime_type"],
                    channel_id=channel_id
                )
                file_list.append(metadata)
        
        return chat_service_pb2.FileListResponse(success=True, files=file_list)
    
    def Logout(self, request, context):
        """Handle user logout"""
        payload = self._verify_token(request.token)
        if not payload:
            return chat_service_pb2.StatusResponse(success=False, message="Invalid token", code=401)
        
        username = payload["username"]
        user_id = payload["user_id"]
        
        # Don't remove from channels permanently, just update status
        
        if request.token in self.sessions:
            del self.sessions[request.token]
        
        if username in self.users:
            self.users[username]["status"] = "offline"
            self.users[username]["last_seen"] = datetime.utcnow()
            self.online_users.discard(username)
            self._save_users()  # Save offline status
        
        self.message_broker.unsubscribe(user_id)
        
        logger.info(f"User {username} logged out")
        
        return chat_service_pb2.StatusResponse(success=True, message="Logout successful", code=200)
    
    def GetMessages(self, request, context):
        """Retrieve messages from channel"""
        payload = self._verify_token(request.token)
        if not payload:
            return chat_service_pb2.GetResponse(success=False, messages=[])
        
        channel_id = request.channel_id
        limit = request.limit if request.limit > 0 else 50
        offset = request.offset if request.offset >= 0 else 0
        
        if channel_id not in self.messages:
            return chat_service_pb2.GetResponse(success=True, messages=[])
        
        all_messages = self.messages[channel_id]
        messages_slice = all_messages[offset:offset + limit]
        
        proto_messages = []
        for msg in messages_slice:
            proto_msg = chat_service_pb2.Message(
                message_id=msg["id"],
                sender_id=msg["sender_id"],
                sender_name=msg["sender_name"],
                channel_id=msg["channel_id"],
                content=msg["content"],
                type=msg["type"]
            )
            proto_messages.append(proto_msg)
        
        return chat_service_pb2.GetResponse(success=True, messages=proto_messages)
    
    def GetChannels(self, request, context):
        """Get list of channels"""
        payload = self._verify_token(request.token)
        if not payload:
            return chat_service_pb2.ChannelListResponse(success=False, channels=[])
        
        proto_channels = []
        for channel_id, channel in self.channels.items():
            proto_channel = chat_service_pb2.Channel(
                channel_id=channel_id,
                name=channel["name"],
                description=channel["description"],
                is_private=channel["is_private"],
                member_count=len(channel["members"])
            )
            proto_channels.append(proto_channel)
        
        return chat_service_pb2.ChannelListResponse(success=True, channels=proto_channels)
    
    def GetOnlineUsers(self, request, context):
        """Get online AND offline users"""
        payload = self._verify_token(request.token)
        if not payload:
            return chat_service_pb2.UserListResponse(success=False, users=[])
        
        user_list = []
        for username, user in self.users.items():
            user_info = chat_service_pb2.UserInfo(
                user_id=user["id"],
                username=username,
                is_admin=user["is_admin"],
                status=user["status"],
                display_name=user.get("display_name", username),
                email=user.get("email", "")
            )
            user_list.append(user_info)
        
        return chat_service_pb2.UserListResponse(success=True, users=user_list)

def serve(port: int, node_id: int):
    """Start the gRPC server"""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    
    llm_server_address = "localhost:50055"
    
    servicer = ChatServicer(node_id, llm_server_address)
    chat_service_pb2_grpc.add_ChatServiceServicer_to_server(servicer, server)
    
    server.add_insecure_port(f'[::]:{port}')
    server.start()
    
    logger.info(f"Application server (Node {node_id}) started on port {port}")
    logger.info(f"✓ User persistence enabled - users saved to disk")
    logger.info(f"✓ Real-time messaging enabled")
    logger.info(f"✓ Direct messages enabled")
    logger.info(f"✓ File transfer enabled")
    logger.info(f"✓ Create channel feature enabled")
    logger.info(f"✓ Channel admin management enabled")
    
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
        server.stop(0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chat Application Server")
    parser.add_argument("--port", type=int, default=50051, help="Server port")
    parser.add_argument("--node_id", type=int, default=1, help="Node ID")
    args = parser.parse_args()
    
    serve(args.port, args.node_id)
