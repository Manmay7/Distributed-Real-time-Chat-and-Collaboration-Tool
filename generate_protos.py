import os
import subprocess

# Create generated directory if it doesn't exist
os.makedirs('generated', exist_ok=True)

# Generate raft_node proto
subprocess.run([
    'python', '-m', 'grpc_tools.protoc',
    '-I', 'protos',
    '--python_out=generated',
    '--grpc_python_out=generated',
    'protos/raft_node.proto'
])

# Generate llm_service proto
subprocess.run([
    'python', '-m', 'grpc_tools.protoc',
    '-I', 'protos',
    '--python_out=generated',
    '--grpc_python_out=generated',
    'protos/llm_service.proto'
])

print("✓ Generated raft_node protos")
print("✓ Generated llm_service protos")

print("\n✅ All proto files generated successfully!")
print("Run: python generate_protos.py")
