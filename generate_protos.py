import os
import subprocess

# Create generated directory if it doesn't exist
os.makedirs('generated', exist_ok=True)

print("Generating proto files...")

# Generate raft_node proto (with all chat features)
print("- Generating raft_node protos...")
subprocess.run([
    'python', '-m', 'grpc_tools.protoc',
    '-I', 'protos',
    '--python_out=generated',
    '--grpc_python_out=generated',
    'protos/raft_node.proto'
], check=True)

# Generate llm_service proto (if exists)
if os.path.exists('protos/llm_service.proto'):
    print("- Generating llm_service protos...")
    subprocess.run([
        'python', '-m', 'grpc_tools.protoc',
        '-I', 'protos',
        '--python_out=generated',
        '--grpc_python_out=generated',
        'protos/llm_service.proto'
    ], check=True)

print("✓ Proto files generated successfully!")
print("\nNow you can:")
print("1. Start 3 Raft nodes (they handle ALL chat features)")
print("2. Connect with chat_client.py directly to Raft nodes")
