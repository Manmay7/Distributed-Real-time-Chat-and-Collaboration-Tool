# 🚀 Real-Time Chat & Collaboration Tool

A distributed, fault-tolerant chat application built with **Raft Consensus Algorithm** for high availability and consistency. Features real-time messaging, AI-powered suggestions, file sharing, and channel-based collaboration.

---

## 📋 Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Quick Start](#quick-start)

---

## ✨ Features

### 🔐 **User Authentication**
- Secure signup and login with bcrypt password hashing
- JWT token-based session management
- Persistent user data across node failures

### 💬 **Real-Time Messaging**
- **Channel-based chat**: Public and private channels
- **Direct messaging**: Private 1-on-1 conversations
- Message history and persistence
- Real-time message delivery

### 🤖 **AI-Powered Features** (Optional)
- **Smart Replies**: AI-generated response suggestions
- **Conversation Summarization**: Get key points from long discussions
- **Context-Aware Suggestions**: AI helps you complete your messages
- **Ask AI**: Get answers to questions using LLM

### 📁 **File Sharing**
- Upload and download files in channels or DMs
- Support for multiple file types
- File metadata tracking

### 👥 **Channel Management**
- Create public/private channels
- Admin-controlled membership (add/remove users)
- Channel-specific permissions
- View channel members and online status

### 🔄 **Distributed Architecture**
- **Raft Consensus**: Ensures data consistency across nodes
- **Fault Tolerance**: Continues working even if nodes fail
- **Automatic Leader Election**: No single point of failure
- **Data Persistence**: State survives node restarts

### 🛡️ **Security & Access Control**
- Role-based permissions (Channel admins)
- Membership validation for channel access
- Token expiration and renewal
- Secure file transfer

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Client Applications                    │
│              (Multiple concurrent users)                 │
└─────────────────┬───────────────────────────────────────┘
                  │
        ┌─────────┼─────────┐
        │         │         │
┌───────▼─────┐ ┌▼─────────▼──┐ ┌───────────────┐
│  Raft Node  │ │ Raft Node   │ │  Raft Node    │
│  (Leader)   │ │ (Follower)  │ │  (Follower)   │
│  Port 50051 │ │ Port 50052  │ │  Port 50053   │
└──────┬──────┘ └──────┬──────┘ └───────┬───────┘
       │               │                 │
       └───────────────┼─────────────────┘
                       │ Raft Consensus
                       │ (Leader Election,
                       │  Log Replication)
                       │
              ┌────────▼─────────┐
              │   LLM Server     │
              │   (Optional)     │
              │   Port 50055     │
              │  (Gemini API)    │
              └──────────────────┘
```

### Key Components:

1. **Raft Nodes**: Distributed servers implementing Raft consensus
   - One leader handles all writes
   - Followers replicate data
   - Automatic failover on leader failure

2. **Client**: Command-line interface for users
   - Auto-discovers current leader
   - Reconnects on node failure

3. **LLM Server**: AI features powered by Google Gemini
   - Smart replies
   - Summarization
   - Q&A

---

## 📦 Prerequisites

### Required:
- **Python 3.8+**
- **pip** (Python package manager)

### Python Packages:
```bash
grpcio==1.59.0
grpcio-tools==1.59.0
protobuf==4.24.3
pyyaml==6.0.1
python-dotenv==1.0.0
transformers==4.35.0
torch==2.2.0
bcrypt==4.0.1
redis==5.0.0
colorlog==6.7.0
PyJWT==2.10.1
google-generativeai==0.8.3
```

### For AI features:
- **Google Gemini API Key**
- `google-generativeai` package

---

## 🔧 Installation

### 1. Clone the Repository
```bash
git clone https://github.com/Manmay7/Distributed-Real-time-Chat-and-Collaboration-Tool.git
cd Distributed-Real-time-Chat-and-Collaboration-Tool
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Generate gRPC Code (if not included)
```bash
python -m grpc_tools.protoc -I./protos --python_out=./generated --pyi_out=./generated --grpc_python_out=./generated ./protos/chat_service.proto
python -m grpc_tools.protoc -I./protos --python_out=./generated --pyi_out=./generated --grpc_python_out=./generated ./protos/raft_node.proto
```

---

## 🚀 Quick Start

### Step 1: Start the LLM Server (Optional - for AI features)

```bash
cd llm_server
python llm_server.py
```

**Expected Output:**
```
✅ LLM Server started on port 50055
🤖 Using Google Gemini model: gemini-1.5-flash
📡 Ready to handle AI requests...
```

> **Note**: The chat system works without LLM server, but AI features will be disabled.

---

### Step 2: Start Raft Nodes (3 terminals)

**Terminal 1 - Node 1:**
```bash
python server/raft_node.py --node-id 1 --port 50051
```

**Terminal 2 - Node 2:**
```bash
python server/raft_node.py --node-id 2 --port 50052
```

**Terminal 3 - Node 3:**
```bash
python server/raft_node.py --node-id 3 --port 50053
```

**Expected Output (after 3-6 seconds):**
```
============================================================
  Raft Chat Node 1
  Port: 50051
  Features: Consensus + Full Chat Application
============================================================

✅ Complete Raft Chat Node 1 on port 50051
============================================================
INFO:__main__:Initialized 3 channels and 3 test users
INFO:__main__:  - All default channels (general, random, tech): 3 members (all are admins)
INFO:__main__:Connected to peer 2 at localhost:50052
INFO:__main__:Connected to peer 3 at localhost:50053
INFO:__main__:Node 1 initialized with ALL FEATURES
INFO:__main__:  ✓ Raft Consensus (Log: 0 entries, Term: 0)
INFO:__main__:  ✓ User Auth (Signup/Login)
INFO:__main__:  ✓ Channels & Messages
INFO:__main__:  ✓ Direct Messages
INFO:__main__:  ✓ File Upload/Download
INFO:__main__:  ✓ Real-time Streaming
INFO:__main__:  ✓ Data Persistence + Raft Log Recovery
INFO:__main__:Peers: [2, 3]
INFO:__main__:✅ Complete Raft Chat Node 1 on port 50051
INFO:__main__:============================================================
```

> **Important**: Wait 3-6 seconds for leader election to complete before starting clients.

---

### Step 3: Start Client(s)

```bash
# Terminal 4 - Client 1
python client/chat_client.py
```

**Expected Output:**
```
🔍 Discovering Raft leader...
✓ Found leader at localhost:50051 (Node 1, Term 2)

✓ Ready! Type 'login <username>' or 'signup' to begin

    ╔══════════════════════════════════════════════╗
    ║     Distributed Chat & Collaboration Tool    ║
    ║         Raft Consensus + Real-time Chat      ║
    ╚══════════════════════════════════════════════╝

    Commands: 'signup' | 'login <username>' | 'help'
    Test users: alice/alice123, bob/bob123, charlie/charlie123

(chat) > 
```

---
