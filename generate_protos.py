import os
import subprocess
import sys

print("="*60)
print("  REGENERATING ALL PROTOCOL BUFFERS")
print("="*60)

# Create generated directory if it doesn't exist
os.makedirs('generated', exist_ok=True)

# Create __init__.py to make it a package
init_file = os.path.join('generated', '__init__.py')
if not os.path.exists(init_file):
    with open(init_file, 'w') as f:
        f.write("# Generated proto package\n")
    print("✓ Created generated/__init__.py")

# Generate raft_node proto
print("\n📦 Generating raft_node proto...")
result = subprocess.run([
    sys.executable, '-m', 'grpc_tools.protoc',
    '-I', 'protos',
    '--python_out=generated',
    '--grpc_python_out=generated',
    'protos/raft_node.proto'
], capture_output=True, text=True)

if result.returncode != 0:
    print(f"❌ Error generating raft_node proto:")
    print(result.stderr)
    sys.exit(1)
else:
    print("✓ raft_node_pb2.py")
    print("✓ raft_node_pb2_grpc.py")

# Generate llm_service proto
print("\n📦 Generating llm_service proto...")
result = subprocess.run([
    sys.executable, '-m', 'grpc_tools.protoc',
    '-I', 'protos',
    '--python_out=generated',
    '--grpc_python_out=generated',
    'protos/llm_service.proto'
], capture_output=True, text=True)

if result.returncode != 0:
    print(f"❌ Error generating llm_service proto:")
    print(result.stderr)
    sys.exit(1)
else:
    print("✓ llm_service_pb2.py")
    print("✓ llm_service_pb2_grpc.py")

print("\n" + "="*60)
print("  ✅ ALL PROTOS GENERATED SUCCESSFULLY")
print("="*60)
print("\n📋 Generated files:")
print("   - generated/raft_node_pb2.py")
print("   - generated/raft_node_pb2_grpc.py")
print("   - generated/llm_service_pb2.py")
print("   - generated/llm_service_pb2_grpc.py")
print("\n🚀 Now restart ALL servers:")
print("   1. Kill all running nodes (Ctrl+C in each terminal)")
print("   2. python server/raft_node.py --node-id 1 --port 50051")
print("   3. python server/raft_node.py --node-id 2 --port 50052")
print("   4. python server/raft_node.py --node-id 3 --port 50053")
print("   5. python llm_server/llm_server.py")
print("   6. python client/chat_client.py")
print("="*60)
