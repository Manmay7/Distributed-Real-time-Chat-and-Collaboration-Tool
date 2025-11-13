#!/usr/bin/env python3
"""
Cleanup script to remove all persisted data and start fresh.
Run this script to delete all .pkl files and reset the system.
"""

import os
import shutil

def cleanup_data():
    """Remove all persisted data files"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    server_dir = os.path.join(base_dir, "server")
    
    # Directories to clean
    data_dirs = [
        os.path.join(server_dir, "raft_node_1_data"),
        os.path.join(server_dir, "raft_node_2_data"),
        os.path.join(server_dir, "raft_node_3_data"),
        os.path.join(server_dir, "server_data")
    ]
    
    files_deleted = 0
    dirs_deleted = 0
    
    print("🧹 Cleaning up persisted data...")
    print("=" * 60)
    
    # Remove data directories
    for data_dir in data_dirs:
        if os.path.exists(data_dir):
            try:
                shutil.rmtree(data_dir)
                dirs_deleted += 1
                print(f"✓ Deleted directory: {os.path.basename(data_dir)}")
            except Exception as e:
                print(f"✗ Failed to delete {os.path.basename(data_dir)}: {e}")
    
    # Also check for any standalone .pkl files in server directory
    if os.path.exists(server_dir):
        for filename in os.listdir(server_dir):
            if filename.endswith('.pkl'):
                filepath = os.path.join(server_dir, filename)
                try:
                    os.remove(filepath)
                    files_deleted += 1
                    print(f"✓ Deleted file: {filename}")
                except Exception as e:
                    print(f"✗ Failed to delete {filename}: {e}")
    
    print("=" * 60)
    print(f"✅ Cleanup complete!")
    print(f"   - Directories removed: {dirs_deleted}")
    print(f"   - Files removed: {files_deleted}")
    print("\nNow restart your Raft nodes:")
    print("  python server/raft_node.py --node-id 1 --port 50051")
    print("  python server/raft_node.py --node-id 2 --port 50052")
    print("  python server/raft_node.py --node-id 3 --port 50053")
    print("\nThen login and test:")
    print("  login alice")
    print("  channels           # Should show 3 default public channels")
    print("  create_channel C1  # Should work")
    print("  add_user bob       # Should work (you're auto-joined as admin)")
    print("\nTest users: alice, bob, charlie (all password: <username>123)")

if __name__ == "__main__":
    cleanup_data()
