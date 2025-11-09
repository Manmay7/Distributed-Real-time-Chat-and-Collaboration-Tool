import grpc
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'generated'))

import raft_node_pb2
import raft_node_pb2_grpc

def find_leader():
    """Find the Raft leader"""
    raft_ports = [50051, 50052, 50053]
    
    print("Discovering Raft leader...")
    
    for port in raft_ports:
        try:
            channel = grpc.insecure_channel(f'localhost:{port}')
            stub = raft_node_pb2_grpc.RaftNodeStub(channel)
            
            response = stub.GetLeader(raft_node_pb2.GetLeaderRequest(), timeout=1.0)
            
            if response.leader_id > 0:
                print(f"Found leader: Node {response.leader_id} at {response.leader_address}")
                channel.close()
                return response.leader_address
            
            channel.close()
        except Exception as e:
            continue
    
    print("No leader found. Retrying...")
    import time
    time.sleep(2)
    return find_leader()

def run():
    # Find leader
    leader_address = find_leader()
    
    channel = grpc.insecure_channel(leader_address)
    stub = raft_node_pb2_grpc.RaftNodeStub(channel)
    
    username = input("Enter your username: ")
    room = input("Enter room name (default: general): ") or "general"
    
    print(f"\nWelcome to the chat room '{room}'!")
    print("Type your messages and press Enter. Type 'quit' to exit.\n")
    
    # Get existing messages
    try:
        response = stub.GetMessages(raft_node_pb2.GetMessagesRequest(room=room))
        for msg in response.messages:
            print(f"[{msg.user}]: {msg.message}")
    except Exception as e:
        print(f"Error fetching messages: {e}")
    
    # Chat loop
    while True:
        try:
            message = input(f"{username}: ")
            
            if message.lower() == 'quit':
                break
            
            if message.strip():
                response = stub.SendMessage(raft_node_pb2.ChatMessageRequest(
                    user=username,
                    message=message,
                    room=room
                ))
                
                if not response.success:
                    print(f"Failed to send message: {response.message}")
                    # Try to find new leader
                    leader_address = find_leader()
                    channel = grpc.insecure_channel(leader_address)
                    stub = raft_node_pb2_grpc.RaftNodeStub(channel)
        
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")
            # Try to reconnect to leader
            try:
                leader_address = find_leader()
                channel = grpc.insecure_channel(leader_address)
                stub = raft_node_pb2_grpc.RaftNodeStub(channel)
            except:
                break
    
    channel.close()
    print("\nGoodbye!")

if __name__ == '__main__':
    run()
