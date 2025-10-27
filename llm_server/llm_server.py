# llm_server/llm_server.py
import grpc
from concurrent import futures
import logging
import sys
import os
import uuid
from typing import List, Dict
import google.generativeai as genai

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import generated proto files
import generated.llm_service_pb2_grpc as llm_service_pb2_grpc
import generated.llm_service_pb2 as llm_service_pb2

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LLMServicer(llm_service_pb2_grpc.LLMServiceServicer):
    def __init__(self, gemini_api_key: str):
        """Initialize LLM Service with Gemini 2.5 Flash"""
        self.gemini_api_key = gemini_api_key
        self._init_gemini()
    
    def _init_gemini(self):
        """Initialize Gemini 2.5 Flash API"""
        try:
            genai.configure(api_key=self.gemini_api_key)
            self.model = genai.GenerativeModel('gemini-2.5-flash')
            self.backend = "gemini"
            
            logger.info("  Using Gemini Flash API (much smarter responses!)")
            logger.info("  Model: gemini-2.5-flash")
            logger.info("  Free tier: 15 requests/minute")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"Failed to initialize Gemini: {e}")
            raise
    
    
    
    def GetSmartReply(self, request, context):
        """Generate smart reply suggestions"""
        request_id = request.request_id
        recent_messages = list(request.recent_messages)
        
        logger.info(f"Generating smart replies...")
        
        try:
            suggestions = self._generate_smart_replies(recent_messages)
            
            return llm_service_pb2.SmartReplyResponse(
                request_id=request_id,
                suggestions=suggestions
            )
            
        except Exception as e:
            logger.error(f"Error generating smart replies: {e}")
            return llm_service_pb2.SmartReplyResponse(
                request_id=request_id,
                suggestions=["I agree", "That's interesting", "Tell me more"]
            )
    
    def SummarizeConversation(self, request, context):
        """Summarize conversation messages"""
        request_id = request.request_id
        messages = list(request.messages)
        max_length = request.max_length if request.max_length > 0 else 200
        
        logger.info(f"Summarizing conversation...")
        
        try:
            summary, key_points = self._summarize_conversation(messages, max_length)
            
            return llm_service_pb2.SummarizeResponse(
                request_id=request_id,
                summary=summary,
                key_points=key_points
            )
            
        except Exception as e:
            logger.error(f"Error summarizing conversation: {e}")
            return llm_service_pb2.SummarizeResponse(
                request_id=request_id,
                summary="Unable to generate summary at this time.",
                key_points=[]
            )
    
    
    
   
    
    def _generate_smart_replies(self, messages: List) -> List[str]:
        """Generate smart reply suggestions using Gemini"""
        if not messages:
            return ["Hello!", "How can I help?", "What's on your mind?"]
        
        try:
            conversation = "\n".join([f"{m.sender}: {m.content}" for m in messages[-5:]])
            prompt = f"""Based on this conversation:
{conversation}

Generate exactly 3 short, natural reply suggestions. Each suggestion should be:
- Under 10 words
- Contextually relevant
- Natural and conversational

Format: Just list the 3 suggestions, one per line, no numbering or bullets."""
            
            response = self.model.generate_content(prompt)
            suggestions = [s.strip() for s in response.text.strip().split('\n') if s.strip()]
            
            # Clean up any numbering or bullets
            cleaned = []
            for s in suggestions:
                s = s.lstrip('0123456789.-•*) ')
                if s:
                    cleaned.append(s)
            
            return cleaned[:3] if len(cleaned) >= 3 else cleaned + ["I agree", "Interesting point"][:3-len(cleaned)]
            
        except Exception as e:
            logger.error(f"Smart reply error: {e}")
            return ["I agree", "That's interesting", "Tell me more"]
    
    def _summarize_conversation(self, messages: List, max_length: int) -> tuple:
        """Summarize conversation using Gemini"""
        if not messages:
            return "No messages to summarize", []
        
        try:
            conversation = "\n".join([f"{m.sender}: {m.content}" for m in messages])
            prompt = f"""Summarize this conversation concisely in under {max_length} characters:

{conversation}

Then provide 3 key bullet points about the discussion.

Format:
Summary: [your summary here]

Key Points:
- point 1
- point 2
- point 3"""
            
            response = self.model.generate_content(prompt)
            text = response.text.strip()
            
            # Parse summary and key points
            summary = ""
            key_points = []
            
            lines = text.split('\n')
            in_key_points = False
            
            for line in lines:
                line = line.strip()
                if line.startswith('Summary:'):
                    summary = line.replace('Summary:', '').strip()
                elif 'Key Points:' in line or 'Key points:' in line:
                    in_key_points = True
                elif in_key_points and (line.startswith('-') or line.startswith('•')):
                    point = line.lstrip('-•* ').strip()
                    if point:
                        key_points.append(point)
                elif not in_key_points and summary and line:
                    summary += " " + line
            
            # Ensure summary fits max_length
            if len(summary) > max_length:
                summary = summary[:max_length-3] + "..."
            
            # Fallback if parsing failed
            if not summary:
                summary = text[:max_length-3] + "..." if len(text) > max_length else text
            
            if not key_points:
                participants = list(set([m.sender for m in messages]))
                key_points = [
                    f"{len(messages)} messages exchanged",
                    f"Participants: {', '.join(participants[:3])}",
                    f"Active discussion"
                ]
            
            return summary, key_points[:3]
            
        except Exception as e:
            logger.error(f"Summarize error: {e}")
            participants = list(set([m.sender for m in messages]))
            return (
                f"Conversation between {', '.join(participants)}",
                [f"{len(messages)} messages", f"Participants: {len(participants)}"]
            )
    
    


def serve():
    """Start the LLM gRPC server"""
    # Get Gemini API key from environment
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    
    if not gemini_api_key:
        print("\n" + "=" * 60)
        print("GEMINI API KEY REQUIRED")
        print("=" * 60)
        print("\nTo use this LLM server, you need a Gemini API key.")
        print("\nGet your FREE API key:")
        print("   https://makersuite.google.com/app/apikey")
        print("\nThen set it as an environment variable:")
        print("   Linux/Mac:  export GEMINI_API_KEY='your-key-here'")
        print("   Windows:    set GEMINI_API_KEY=your-key-here")
        print("\n" + "=" * 60 + "\n")
        
        gemini_api_key = input("Or enter your Gemini API key now: ").strip()
        
        if not gemini_api_key:
            print("\nNo API key provided. Exiting...")
            return
    
    try:
        # Create gRPC server
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
        
        # Initialize and add servicer
        servicer = LLMServicer(gemini_api_key=gemini_api_key)
        llm_service_pb2_grpc.add_LLMServiceServicer_to_server(servicer, server)
        
        # Start server on port 50055
        port = 50055
        server.add_insecure_port(f'[::]:{port}')
        server.start()
        
        logger.info(f"\n LLM Server running on port {port}")
        logger.info(" Ready to process AI requests...\n")
        
        server.wait_for_termination()
        
    except KeyboardInterrupt:
        logger.info("\n Shutting down LLM server...")
        server.stop(0)
    except Exception as e:
        logger.error(f"\n Fatal error: {e}")
        logger.error("Please check your API key and internet connection.")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print(" Gemini 2.5 Flash LLM Server")
    print("=" * 60)
    serve()
