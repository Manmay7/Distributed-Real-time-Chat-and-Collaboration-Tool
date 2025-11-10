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

print("✓ Generated raft_node protos")

# Generate chat_client proto if it exists
if os.path.exists('protos/chat_client.proto'):
    subprocess.run([
        'python', '-m', 'grpc_tools.protoc',
        '-I', 'protos',
        '--python_out=generated',
        '--grpc_python_out=generated',
        'protos/chat_client.proto'
    ])
    print("✓ Generated chat_client protos")

# Generate LLM service proto if it exists
if os.path.exists('protos/llm_service.proto'):
    subprocess.run([
        'python', '-m', 'grpc_tools.protoc',
        '-I', 'protos',
        '--python_out=generated',
        '--grpc_python_out=generated',
        'protos/llm_service.proto'
    ])
    print("✓ Generated llm_service protos")

print("\n✅ All proto files generated successfully!")
print("Run: python generate_protos.py")
