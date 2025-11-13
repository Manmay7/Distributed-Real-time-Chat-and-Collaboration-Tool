# Channel Administration Guide

## Admin Privileges System

The chat system now implements **restricted channel access** where only channel admins can add or remove users.

### 🔑 Key Changes

1. **No Self-Join**: Users cannot join channels on their own
2. **Admin-Controlled Access**: Only channel admins can add users
3. **Creator = Admin**: When you create a channel, you become its admin
4. **Global Admin**: The user 'admin' can manage all channels

---

## User Types

### Regular Users
- Can create channels (becoming admin of their channel)
- Can send messages in channels they're a member of
- Can send direct messages to anyone
- **Cannot** join channels without admin approval
- **Cannot** add/remove users from channels

### Channel Admins
- Automatically assigned when creating a channel
- Can add users to their channel
- Can remove users from their channel
- Cannot remove themselves if they're the only admin
- Have full control over their channel membership

### Global Admins
- Username: `admin` (password: `admin123`)
- Can add/remove users from **any** channel
- Can manage all channels regardless of creator
- Useful for system-wide moderation

---

## How To Use

### Creating a Channel (Becomes Admin)
```
create_channel myteam My Team Channel
```
✅ You are now admin of `#myteam`

### Adding Users to Your Channel
```
# First, join the channel or be in it
# Then add users:
add_user alice
add_user bob
```

### Viewing Channel Members
```
members
```

### Removing Users from Your Channel
```
remove_user bob
```

### Attempting to Join a Channel (Will Fail)
```
join myteam
```
❌ Error: Cannot join channels directly. Ask admin to add you.

---

## Example Workflows

### Workflow 1: Creating a Team Channel

**Alice wants to create a private team channel:**

```
(chat) > login alice
Password: alice123
✓ Logged in as alice

(chat) > create_channel projectx Project X Team
✓ Channel #projectx created!

(chat) > add_user bob
✅ Added bob to #projectx

(chat) > add_user charlie
✅ Added charlie to #projectx

(chat) > members
📋 Members in #projectx (3 total):
   alice (admin) 👑
   bob
   charlie
```

### Workflow 2: User Trying to Join

**Bob tries to join a channel:**

```
(chat) > login bob
Password: bob123

(chat) > join projectx
⚠️  NOTICE: Users cannot join channels directly.
   Ask an admin of #projectx to add you with:
   > add_user bob

   Or create your own channel with: create_channel <name>
```

**Bob must wait for Alice to add him.**

### Workflow 3: Admin Managing Users

**Alice removes a user:**

```
(chat) > remove_user charlie
✅ Removed charlie from #projectx

(chat) > members
📋 Members in #projectx (2 total):
   alice (admin) 👑
   bob
```

### Workflow 4: Global Admin Access

**System admin manages any channel:**

```
(chat) > login admin
Password: admin123
✓ Logged in as admin (Global Admin)

(chat) > channels
Available channels:
1. #general
2. #projectx (alice's channel)

# Can add users to ANY channel
(chat) > add_user newuser
✅ Added newuser to #projectx

# Can remove users from ANY channel
(chat) > remove_user troublemaker
✅ Removed troublemaker from #projectx
```

---

## Command Reference

### Channel Admin Commands

| Command | Who Can Use | Description |
|---------|------------|-------------|
| `create_channel <name>` | Everyone | Create channel (you become admin) |
| `add_user <username>` | Channel admins, Global admin | Add user to current channel |
| `remove_user <username>` | Channel admins, Global admin | Remove user from current channel |
| `members` | Everyone | View channel members and admins |
| `channels` | Everyone | List all available channels |

### Restrictions

| Action | Restriction | Reason |
|--------|------------|---------|
| Join channel | ❌ Blocked | Admins must add users |
| Add user | ✅ Admin only | Prevents spam/unwanted access |
| Remove user | ✅ Admin only | Protects channel integrity |
| Remove self (last admin) | ❌ Blocked | Prevents orphaned channels |

---

## Benefits

✅ **Security**: Prevents unauthorized access to channels
✅ **Control**: Channel creators maintain full control
✅ **Organization**: Clear hierarchy and permissions
✅ **Spam Prevention**: No random users joining channels
✅ **Privacy**: Private discussions stay private

---

## Testing the Admin System

### Test 1: Create and Manage Channel
```powershell
# Start system
python server/raft_node.py --node-id 1 --port 50051
python server/raft_node.py --node-id 2 --port 50052
python server/raft_node.py --node-id 3 --port 50053
python client/chat_client.py

# Login and test
login alice
create_channel testchannel Test Channel
add_user bob
members
send Hello team!
remove_user bob
```

### Test 2: Verify Join Restriction
```
login bob
join testchannel  # Should fail with clear message
```

### Test 3: Global Admin Powers
```
login admin
channels
# Pick any channel
add_user alice
remove_user someuser
```

---

## Summary

- **Channel creation** makes you the admin
- **Only admins** can add/remove users
- **No self-join** allowed - must be added by admin
- **Global admin** (username: `admin`) can manage all channels
- **Clear error messages** guide users on what to do

This system ensures organized, secure, and admin-controlled channel access! 🔒
