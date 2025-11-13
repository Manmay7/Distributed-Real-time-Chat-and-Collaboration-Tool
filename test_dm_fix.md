# DM Fix Verification Guide

## Problem Identified

When a new leader is elected, DMs were not showing in the `dm` command even though they were properly replicated and saved to disk.

**Root Cause**: User IDs change when nodes restart and rebuild from the Raft log. The old `GetDirectMessages` matched DMs by `user_id`, but after a leader election:
- Old DMs had user_ids like: `ca76d201-2211-44c5-8086-e6f90420b4c6`
- New users (after log rebuild) had different user_ids like: `8fb4fa85-67ee-44e8-8715-0de88f18c822`

## Fix Applied

Changed `GetDirectMessages` to match DMs by **username** instead of `user_id`:

```python
# OLD (broken after restart):
if (dm["sender_id"] == user_id and dm["recipient_id"] == other_user_id) or ...

# NEW (works across restarts):
if (dm["sender_name"] == current_username and dm["recipient_name"] == other_username) or ...
```

## Changes Made

1. **server/raft_node.py - GetDirectMessages (line ~1469)**:
   - Match DMs by username instead of user_id
   - Added debug logging to track DM queries

2. **server/raft_node.py - _become_leader (line ~670)**:
   - Added logging to show DMs before clearing
   - Added logging to show DMs after rebuilding from log
   - This helps debug leader election issues

## How to Test

### Test 1: Verify DMs survive leader failover

```powershell
# Terminal 1: Start node 1
python server/raft_node.py --node-id 1 --port 50051

# Terminal 2: Start node 2
python server/raft_node.py --node-id 2 --port 50052

# Terminal 3: Start node 3
python server/raft_node.py --node-id 3 --port 50053

# Terminal 4: Client
python client/chat_client.py

# In client:
login alice
dm bob
send Test message 1
send Test message 2
back

# Now kill the current leader (check which node shows "BECAME LEADER" in logs)
# Kill that node with Ctrl+C

# Wait 3-15 seconds for new leader election

# In client (should auto-reconnect):
dm bob
# You should now see "Test message 1" and "Test message 2" ✅
```

### Test 2: Verify DMs are in Raft log

```powershell
# Check node logs after leader election
# Look for these log lines:

# Before clearing:
📋 Current DMs before rebuild: 6

# After rebuilding:
✅ FULL REBUILD COMPLETE:
   DMs: 6/6 expected
   Last 3 DMs after rebuild:
     alice → bob: Test message 1
     alice → bob: Test message 2
```

### Test 3: Verify all nodes have identical DM data

```powershell
# Check all three nodes (while running):
python -c "import pickle; dms = pickle.load(open('server/raft_node_1_data/direct_messages.pkl', 'rb')); print(f'Node 1: {len(dms)} DMs')"

python -c "import pickle; dms = pickle.load(open('server/raft_node_2_data/direct_messages.pkl', 'rb')); print(f'Node 2: {len(dms)} DMs')"

python -c "import pickle; dms = pickle.load(open('server/raft_node_3_data/direct_messages.pkl', 'rb')); print(f'Node 3: {len(dms)} DMs')"

# All three should show the same count ✅
```

## Expected Behavior After Fix

✅ DMs show correctly after leader election
✅ DMs persist across node restarts
✅ All nodes have identical DM data
✅ Client can read DM history from any leader
✅ Detailed logs show DM rebuild process during leader election

## Debugging Tips

If DMs still don't show:

1. **Check server logs** for `GetDirectMessages` debug output:
   ```
   GetDirectMessages: alice ↔ bob, found 2 messages from 6 total DMs
   ```

2. **Check if DMs are in the log**:
   ```powershell
   # Count SEND_DM commands in Raft log
   python -c "import pickle; log = pickle.load(open('server/raft_node_1_data/raft_log_port_50051.pkl', 'rb')); print(f'SEND_DM commands: {sum(1 for e in log if e[\"command\"] == \"SEND_DM\")}')"
   ```

3. **Verify usernames match exactly** (case-sensitive):
   ```powershell
   # Check actual DM data
   python -c "import pickle; dms = pickle.load(open('server/raft_node_1_data/direct_messages.pkl', 'rb')); print([f'{dm[\"sender_name\"]}→{dm[\"recipient_name\"]}' for dm in dms])"
   ```

## Technical Notes

- **Raft log is source of truth**: When a node becomes leader, it rebuilds state from the Raft log, not from disk
- **Disk files are cache**: They speed up startup but leader rebuilds from log anyway
- **User IDs are not stable**: They're regenerated on each CREATE_USER log replay
- **Usernames ARE stable**: They're part of the CREATE_USER command data
- **This is why matching by username works across restarts**

## Summary

The fix ensures DMs are matched by stable usernames rather than transient user IDs, allowing DM history to survive leader elections and node restarts. All replication and persistence was already working correctly - only the query logic needed adjustment.
