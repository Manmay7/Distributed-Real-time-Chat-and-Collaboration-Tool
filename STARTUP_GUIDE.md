# Distributed Chat System - Startup Guide

## Quick Start (Any Order Works Now! ✅)

You can start services in **ANY order** - the Raft nodes will automatically connect to the LLM server when you use AI features.

### Option 1: Start LLM Server First (Recommended)
```powershell
# Terminal 1: LLM Server
python llm_server/llm_server.py

# Terminal 2-4: Raft Nodes
python server/raft_node.py --node-id 1 --port 50051
python server/raft_node.py --node-id 2 --port 50052
python server/raft_node.py --node-id 3 --port 50053

# Terminal 5: Client
python client/chat_client.py
```

### Option 2: Start LLM Server After Raft Nodes (Also Works! ✨)
```powershell
# Terminals 1-3: Start Raft nodes first
python server/raft_node.py --node-id 1 --port 50051
python server/raft_node.py --node-id 2 --port 50052
python server/raft_node.py --node-id 3 --port 50053

# Terminal 4: Start LLM server later
python llm_server/llm_server.py

# Terminal 5: Client
python client/chat_client.py

# Now AI features will work automatically!
```

### Option 3: Start LLM Server Anytime During Operation
```powershell
# If you forgot to start the LLM server:
# 1. Raft nodes are already running
# 2. You tried AI commands and got fallback responses
# 3. Just start the LLM server:

python llm_server/llm_server.py

# Next time you use AI commands, they'll connect automatically!
```

## How It Works

### Lazy Connection Pattern
- **On Startup**: Raft nodes try to connect to LLM server
  - If available → Connected ✅
  - If not available → Continues without LLM ⚠️

- **On AI Command**: When you use `summarize`, `smart_reply`, `ask`, or `suggest`
  - Checks if LLM is connected
  - If not, attempts to reconnect automatically
  - If connection succeeds → AI features work ✅
  - If connection fails → Falls back to basic responses 💡

### What You'll See

**LLM Server Not Running:**
```
(chat) > summarize
🤖 Summarizing last 20 messages...

============================================================
📝 CONVERSATION SUMMARY
============================================================

Conversation with 3 messages between alice

🔑 KEY POINTS:
   1. 3 messages exchanged
   2. 1 participants
   3. 💡 Tip: Start LLM server for AI-powered summaries: python llm_server/llm_server.py
============================================================
```

**After Starting LLM Server:**
```
(chat) > summarize
🤖 Summarizing last 20 messages...

============================================================
📝 CONVERSATION SUMMARY
============================================================

Alice and Bob discussed the new project requirements and agreed
on using Python for the backend. They decided to meet tomorrow
to finalize the architecture design.

🔑 KEY POINTS:
   1. Project requirements review completed
   2. Technology stack decision: Python backend
   3. Follow-up meeting scheduled for tomorrow
============================================================
```

## AI Features Available

Once LLM server is connected, you get:

1. **Conversation Summarization**
   ```
   summarize [message_count]
   ```
   - Intelligent summary of conversation
   - Key points extraction
   - Context understanding

2. **Smart Replies**
   ```
   smart_reply
   ```
   - Context-aware reply suggestions
   - Natural language responses
   - Quick response options

3. **AI Q&A**
   ```
   ask <question>
   ```
   - Ask AI questions
   - Get contextual answers
   - Knowledge queries

4. **Context Suggestions**
   ```
   suggest [partial_text]
   ```
   - Auto-complete suggestions
   - Topic recommendations
   - Conversation starters

## Troubleshooting

### LLM Features Not Working

**Check 1: Is LLM Server Running?**
```powershell
# Look for this in a terminal:
✅ LLM Server running on port 50055
```

**Check 2: Raft Node Logs**
When you use an AI command, you should see:
```
🔄 Attempting to connect to LLM server...
✅ Successfully connected to LLM server
```

**Check 3: Gemini API Key**
LLM server needs a Gemini API key:
```powershell
# Windows
set GEMINI_API_KEY=your-key-here

# Or enter when prompted during startup
```

Get free API key: https://makersuite.google.com/app/apikey

### Connection Issues

If you see:
```
⚠️ LLM server at localhost:50055 is not available
```

1. Check if LLM server is running on port 50055
2. Verify no firewall blocking localhost:50055
3. Start/restart the LLM server
4. Try the AI command again (it will auto-reconnect)

## Summary

✅ **Flexible Startup**: Start services in any order
✅ **Auto-Reconnect**: Raft nodes connect to LLM on-demand
✅ **Graceful Fallback**: Basic features work without LLM
✅ **No Restart Needed**: Start LLM server anytime
✅ **User-Friendly**: Clear messages when LLM unavailable

The system is designed to work smoothly whether you start the LLM server first, last, or somewhere in between!
