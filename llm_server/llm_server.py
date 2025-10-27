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
        """Initialize LLM Service with Gemini 2.0 Flash"""
        self.gemini_api_key = gemini_api_key
        self._init_gemini()
    
    def _init_gemini(self):
        """Initialize Gemini 2.0 Flash API"""
        try:
            genai.configure(api_key=self.gemini_api_key)
            self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
            
            logger.info("=" * 60)
            logger.info("✓ Gemini 2.0 Flash (Experimental) Initialized!")
            logger.info("  Model: gemini-2.0-flash-exp")
            logger.info("  Latest & Smartest Google AI Model")
            logger.info("  Free tier: 15 requests/minute")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"Failed to initialize Gemini: {e}")
            raise
    
    def GetLLMAnswer(self, request, context):
        """Generate answer based on query and context"""
        request_id = request.request_id
        query = request.query
        context_list = list(request.context) if request.context else []
        
        logger.info(f"Processing LLM request: {query[:60]}...")
        
        try:
            response_text = self._generate_response(query, context_list)
            
            return llm_service_pb2.LLMResponse(
                request_id=request_id,
                answer=response_text,
                confidence=0.95
            )
            
        except Exception as e:
            logger.error(f"Error processing LLM request: {e}")
            return llm_service_pb2.LLMResponse(
                request_id=request_id,
                answer="I apologize, but I'm having trouble processing your request. Please try again.",
                confidence=0.0
            )
    
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
    
    def GetContextSuggestions(self, request, context):
        """Get context-aware suggestions"""
        request_id = request.request_id
        context_messages = list(request.context)
        current_input = request.current_input
        
        logger.info(f"Getting context suggestions...")
        
        try:
            suggestions, topics = self._get_context_suggestions(context_messages, current_input)
            
            return llm_service_pb2.SuggestionsResponse(
                request_id=request_id,
                suggestions=suggestions,
                topics=topics
            )
            
        except Exception as e:
            logger.error(f"Error getting suggestions: {e}")
            return llm_service_pb2.SuggestionsResponse(
                request_id=request_id,
                suggestions=["sounds interesting", "tell me more", "I see"],
                topics=[]
            )
    
    def _generate_response(self, query: str, context_list: List[str]) -> str:
        """Generate response using Gemini 2.0 Flash"""
        try:
            if context_list:
                # Include recent context for better responses
                context_str = "\n".join(context_list[-5:])
                prompt = f"""Based on this recent conversation context:

{context_str}

User's question: {query}

Provide a helpful, informative response that considers the conversation context:"""
            else:
                prompt = query
            
            response = self.model.generate_content(prompt)
            return response.text.strip()
            
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return "I'm having trouble connecting to the AI service. Please check your API key and internet connection."
    
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
    
    def _get_context_suggestions(self, messages: List, current_input: str) -> tuple:
        """Get context-aware suggestions using Gemini"""
        try:
            context = "\n".join([f"{m.sender}: {m.content}" for m in messages[-5:]]) if messages else "No previous context"
            
            prompt = f"""Based on this conversation context:
{context}

Current partial input: "{current_input}"

Provide:
1. Three completion suggestions for what the user might want to say
2. Two related topics they might want to discuss

Format:
COMPLETIONS:
- suggestion 1
- suggestion 2
- suggestion 3

TOPICS:
- topic 1
- topic 2"""
            
            response = self.model.generate_content(prompt)
            text = response.text.strip()
            
            suggestions = []
            topics = []
            
            current_section = None
            for line in text.split('\n'):
                line = line.strip()
                upper_line = line.upper()
                
                if 'COMPLETION' in upper_line or 'SUGGESTION' in upper_line:
                    current_section = 'suggestions'
                elif 'TOPIC' in upper_line:
                    current_section = 'topics'
                elif line.startswith('-') or line.startswith('•'):
                    item = line.lstrip('-•* ').strip()
                    if item:
                        if current_section == 'suggestions':
                            suggestions.append(item)
                        elif current_section == 'topics':
                            topics.append(item)
            
            # Ensure we have at least some suggestions
            if not suggestions:
                suggestions = ["continue the thought", "ask a question", "share more details"]
            if not topics:
                topics = ["current discussion", "related ideas"]
            
            return suggestions[:5], topics[:3]
            
        except Exception as e:
            logger.error(f"Context suggestions error: {e}")
            return (
                ["continue the conversation", "ask for clarification", "share thoughts"],
                ["discussion topic", "related subjects"]
            )


def serve():
    """Start the LLM gRPC server"""
    # Get Gemini API key from environment
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    
    if not gemini_api_key:
        print("\n" + "=" * 60)
        print("⚠️  GEMINI API KEY REQUIRED")
        print("=" * 60)
        print("\n📝 To use this LLM server, you need a Gemini API key.")
        print("\n🔑 Get your FREE API key:")
        print("   https://makersuite.google.com/app/apikey")
        print("\n💡 Then set it as an environment variable:")
        print("   Linux/Mac:  export GEMINI_API_KEY='your-key-here'")
        print("   Windows:    set GEMINI_API_KEY=your-key-here")
        print("\n" + "=" * 60 + "\n")
        
        gemini_api_key = input("Or enter your Gemini API key now: ").strip()
        
        if not gemini_api_key:
            print("\n❌ No API key provided. Exiting...")
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
        
        logger.info(f"\n🚀 LLM Server running on port {port}")
        logger.info("📡 Ready to process AI requests...\n")
        
        server.wait_for_termination()
        
    except KeyboardInterrupt:
        logger.info("\n👋 Shutting down LLM server...")
        server.stop(0)
    except Exception as e:
        logger.error(f"\n❌ Fatal error: {e}")
        logger.error("Please check your API key and internet connection.")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🤖 Gemini 2.0 Flash LLM Server")
    print("=" * 60)
    serve()
