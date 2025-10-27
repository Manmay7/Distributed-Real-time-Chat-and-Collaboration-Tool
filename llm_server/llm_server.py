# llm_server/llm_server.py
import grpc
from concurrent import futures
import logging
import sys
import os
import uuid
from typing import List, Dict
import time

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import generated proto files
import generated.llm_service_pb2_grpc as llm_service_pb2_grpc
import generated.llm_service_pb2 as llm_service_pb2

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LLMServicer(llm_service_pb2_grpc.LLMServiceServicer):
    def __init__(self, use_gemini: bool = True, gemini_api_key: str = None):
        """Initialize LLM Service with choice of backend"""
        self.use_gemini = use_gemini
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        
        if self.use_gemini and self.gemini_api_key:
            self._init_gemini()
        else:
            self._init_local_model()
    
    def _init_gemini(self):
        """Initialize Gemini Flash API"""
        try:
            import google.generativeai as genai
            
            genai.configure(api_key=self.gemini_api_key)
            self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
            self.backend = "gemini"
            
            logger.info("✓ Using Gemini 2.0 Flash (Experimental) - Latest & Smartest!")
            logger.info("  Model: gemini-2.0-flash-exp")
            logger.info("  Free tier: 15 requests/minute")
            
        except ImportError:
            logger.error("google-generativeai not installed!")
            logger.error("Install with: pip install google-generativeai")
            self._init_local_model()
        except Exception as e:
            logger.error(f"Failed to initialize Gemini: {e}")
            logger.error("Falling back to local model")
            self._init_local_model()
    
    def _init_local_model(self):
        """Initialize local DialoGPT model"""
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
            
            self.model_name = "microsoft/DialoGPT-small"
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            
            logger.info(f"Initializing local LLM model: {self.model_name}")
            logger.info(f"Using device: {self.device}")
            
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.local_model = AutoModelForCausalLM.from_pretrained(self.model_name)
            self.local_model.to(self.device)
            
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token
            
            self.generator = pipeline(
                "text-generation",
                model=self.local_model,
                tokenizer=self.tokenizer,
                device=0 if self.device == "cuda" else -1,
                max_new_tokens=100,
                temperature=0.7,
                do_sample=True,
                top_p=0.9
            )
            
            self.backend = "local"
            logger.info("⚠ Using local DialoGPT (basic responses)")
            logger.info("  For better results, use Gemini Flash API")
            
        except Exception as e:
            logger.error(f"Failed to load local model: {e}")
            self.generator = None
            self.backend = "fallback"
    
    def GetLLMAnswer(self, request, context):
        """Generate answer based on query and context"""
        request_id = request.request_id
        query = request.query
        context_list = list(request.context) if request.context else []
        
        logger.info(f"Processing LLM request {request_id}: {query[:50]}...")
        
        try:
            if self.backend == "gemini":
                response_text = self._generate_gemini_response(query, context_list)
                confidence = 0.95
            elif self.backend == "local":
                input_text = self._prepare_input(query, context_list)
                response_text = self._generate_local_response(input_text)
                confidence = 0.75
            else:
                response_text = self._get_fallback_response(query)
                confidence = 0.5
            
            return llm_service_pb2.LLMResponse(
                request_id=request_id,
                answer=response_text,
                confidence=confidence
            )
            
        except Exception as e:
            logger.error(f"Error processing LLM request: {e}")
            return llm_service_pb2.LLMResponse(
                request_id=request_id,
                answer="I apologize, but I'm having trouble processing your request.",
                confidence=0.0
            )
    
    def GetSmartReply(self, request, context):
        """Generate smart reply suggestions"""
        request_id = request.request_id
        recent_messages = list(request.recent_messages)
        
        logger.info(f"Generating smart replies for request {request_id}")
        
        try:
            if self.backend == "gemini":
                suggestions = self._generate_gemini_smart_replies(recent_messages)
            else:
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
        
        logger.info(f"Summarizing conversation for request {request_id}")
        
        try:
            if self.backend == "gemini":
                summary, key_points = self._summarize_gemini(messages, max_length)
            else:
                summary, key_points = self._summarize_messages(messages, max_length)
            
            return llm_service_pb2.SummarizeResponse(
                request_id=request_id,
                summary=summary,
                key_points=key_points
            )
            
        except Exception as e:
            logger.error(f"Error summarizing conversation: {e}")
            return llm_service_pb2.SummarizeResponse(
                request_id=request_id,
                summary="Unable to generate summary",
                key_points=[]
            )
    
    def GetContextSuggestions(self, request, context):
        """Get context-aware suggestions"""
        request_id = request.request_id
        context_messages = list(request.context)
        current_input = request.current_input
        
        logger.info(f"Getting context suggestions for request {request_id}")
        
        try:
            if self.backend == "gemini":
                suggestions, topics = self._get_gemini_context_suggestions(
                    context_messages, current_input
                )
            else:
                suggestions, topics = self._get_context_suggestions(
                    context_messages, current_input
                )
            
            return llm_service_pb2.SuggestionsResponse(
                request_id=request_id,
                suggestions=suggestions,
                topics=topics
            )
            
        except Exception as e:
            logger.error(f"Error getting suggestions: {e}")
            return llm_service_pb2.SuggestionsResponse(
                request_id=request_id,
                suggestions=[],
                topics=[]
            )
    
    # ========== GEMINI METHODS ==========
    
    def _generate_gemini_response(self, query: str, context_list: List[str]) -> str:
        """Generate response using Gemini Flash API"""
        try:
            prompt = query
            if context_list:
                context_str = "\n".join(context_list[-3:])
                prompt = f"Context:\n{context_str}\n\nQuestion: {query}\n\nAnswer:"
            
            response = self.model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return "I'm having trouble connecting to the AI service."
    
    def _generate_gemini_smart_replies(self, messages: List) -> List[str]:
        """Generate smart replies using Gemini"""
        if not messages:
            return ["Hello!", "How can I help?", "What's on your mind?"]
        
        try:
            conversation = "\n".join([f"{m.sender}: {m.content}" for m in messages[-5:]])
            prompt = f"""Based on this conversation:
{conversation}

Generate 3 short, natural reply suggestions (each under 10 words):"""
            
            response = self.model.generate_content(prompt)
            suggestions = [s.strip() for s in response.text.split('\n') if s.strip()]
            return suggestions[:3] if suggestions else ["I agree", "Interesting point", "Tell me more"]
        except:
            return ["I agree", "That's interesting", "Tell me more"]
    
    def _summarize_gemini(self, messages: List, max_length: int) -> tuple:
        """Summarize using Gemini"""
        if not messages:
            return "No messages to summarize", []
        
        try:
            conversation = "\n".join([f"{m.sender}: {m.content}" for m in messages])
            prompt = f"""Summarize this conversation in {max_length} characters:
{conversation}

Also provide 3 key points as bullet points."""
            
            response = self.model.generate_content(prompt)
            text = response.text.strip()
            
            # Split summary and key points
            parts = text.split('\n\n')
            summary = parts[0][:max_length]
            key_points = [p.strip('- •*') for p in parts[1:] if p.strip()][:3]
            
            if not key_points:
                key_points = [f"Messages: {len(messages)}", 
                             f"Participants: {len(set(m.sender for m in messages))}"]
            
            return summary, key_points
        except:
            return self._summarize_messages(messages, max_length)
    
    def _get_gemini_context_suggestions(self, messages: List, current_input: str) -> tuple:
        """Get context suggestions using Gemini"""
        try:
            context = "\n".join([f"{m.sender}: {m.content}" for m in messages[-5:]])
            prompt = f"""Based on this conversation:
{context}

Current input: "{current_input}"

Provide:
1. 3 completion suggestions
2. 2 related topics

Format as:
SUGGESTIONS:
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
                if 'SUGGESTIONS' in line.upper():
                    current_section = 'suggestions'
                elif 'TOPICS' in line.upper():
                    current_section = 'topics'
                elif line.startswith('-') or line.startswith('•'):
                    item = line.strip('- •*').strip()
                    if current_section == 'suggestions':
                        suggestions.append(item)
                    elif current_section == 'topics':
                        topics.append(item)
            
            return suggestions[:5], topics[:3]
        except:
            return self._get_context_suggestions(messages, current_input)
    
    # ========== LOCAL MODEL METHODS ==========
    
    def _prepare_input(self, query: str, context_list: List[str]) -> str:
        """Prepare input text with context"""
        if context_list:
            context_str = " ".join(context_list[-3:])
            return f"Context: {context_str}\nUser: {query}\nAssistant:"
        return f"User: {query}\nAssistant:"
    
    def _generate_local_response(self, input_text: str) -> str:
        """Generate response using local model"""
        try:
            outputs = self.generator(
                input_text,
                max_new_tokens=100,
                num_return_sequences=1,
                temperature=0.7,
                do_sample=True,
                top_p=0.9,
                pad_token_id=self.tokenizer.eos_token_id
            )
            
            generated_text = outputs[0]['generated_text']
            response = generated_text.replace(input_text, "").strip()
            
            if "User:" in response:
                response = response.split("User:")[0].strip()
            
            return response if response else "I understand. How can I help you further?"
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return "I'm having trouble generating a response right now."
    
    def _get_fallback_response(self, query: str) -> str:
        """Get rule-based fallback response"""
        query_lower = query.lower()
        
        if "hello" in query_lower or "hi" in query_lower:
            return "Hello! How can I assist you today?"
        elif "how are you" in query_lower:
            return "I'm functioning well, thank you! How can I help you?"
        elif "help" in query_lower:
            return "I'm here to help! You can ask me questions or have a conversation."
        elif "thank" in query_lower:
            return "You're welcome! Let me know if you need anything else."
        else:
            return "That's an interesting point. Could you tell me more?"
    
    def _generate_smart_replies(self, messages: List) -> List[str]:
        """Generate smart reply suggestions (local)"""
        if not messages:
            return ["Hello!", "How can I help?", "What's on your mind?"]
        
        last_message = messages[-1].content if messages else ""
        last_message_lower = last_message.lower()
        
        suggestions = []
        
        if "?" in last_message:
            suggestions.extend([
                "That's a great question!",
                "Let me think about that...",
                "I'll look into it"
            ])
        elif "thanks" in last_message_lower or "thank you" in last_message_lower:
            suggestions.extend([
                "You're welcome!",
                "Happy to help!",
                "Anytime!"
            ])
        else:
            suggestions.extend([
                "I see what you mean",
                "That makes sense",
                "Tell me more"
            ])
        
        return suggestions[:3]
    
    def _summarize_messages(self, messages: List, max_length: int) -> tuple:
        """Summarize messages (local)"""
        if not messages:
            return "No messages to summarize", []
        
        message_texts = [f"{m.sender}: {m.content}" for m in messages]
        
        key_points = []
        questions = [m.content for m in messages if "?" in m.content]
        if questions:
            key_points.append(f"Questions discussed: {len(questions)}")
        
        participants = list(set([m.sender for m in messages]))
        key_points.append(f"Participants: {', '.join(participants)}")
        key_points.append(f"Total messages: {len(messages)}")
        
        summary = f"Conversation between {', '.join(participants)}. {len(messages)} messages exchanged."
        
        if len(summary) > max_length:
            summary = summary[:max_length-3] + "..."
        
        return summary, key_points
    
    def _get_context_suggestions(self, messages: List, current_input: str) -> tuple:
        """Get context suggestions (local)"""
        suggestions = []
        topics = []
        
        if messages:
            all_text = " ".join([m.content for m in messages])
            words = all_text.lower().split()
            
            word_freq = {}
            for word in words:
                if len(word) > 5 and word.isalpha():
                    word_freq[word] = word_freq.get(word, 0) + 1
            
            top_topics = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:3]
            topics = [word for word, _ in top_topics]
        
        if current_input:
            input_lower = current_input.lower()
            
            if input_lower.startswith("can you"):
                suggestions.extend([
                    "help me with that?",
                    "explain this further?",
                    "provide more details?"
                ])
            elif input_lower.startswith("what"):
                suggestions.extend([
                    "do you think about this?",
                    "is your opinion?",
                    "should we do next?"
                ])
            else:
                suggestions.extend([
                    "sounds good to me",
                    "makes sense",
                    "I agree with that"
                ])
        
        return suggestions[:5], topics[:3]


def serve(use_gemini: bool = True):
    """Start the LLM gRPC server"""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    
    # Get Gemini API key from environment or prompt
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    
    if use_gemini and not gemini_api_key:
        print("\n" + "="*60)
        print("GEMINI API KEY REQUIRED")
        print("="*60)
        print("Get your free API key from:")
        print("https://makersuite.google.com/app/apikey")
        print("\nThen either:")
        print("1. Set environment variable: export GEMINI_API_KEY='your-key'")
        print("2. Or run with: python llm_server.py --local")
        print("="*60 + "\n")
        gemini_api_key = input("Enter Gemini API key (or press Enter for local model): ").strip()
        
        if not gemini_api_key:
            use_gemini = False
            print("\n⚠ Using local model instead\n")
    
    # Add servicer
    servicer = LLMServicer(use_gemini=use_gemini, gemini_api_key=gemini_api_key)
    llm_service_pb2_grpc.add_LLMServiceServicer_to_server(servicer, server)
    
    # Start server on port 50055
    port = 50055
    server.add_insecure_port(f'[::]:{port}')
    server.start()
    
    logger.info(f"LLM Server started on port {port}")
    logger.info(f"Backend: {servicer.backend}")
    logger.info("Ready to process AI requests...")
    
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down LLM server...")
        server.stop(0)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="LLM Server")
    parser.add_argument(
        "--local",
        action="store_true",
        help="Use local DialoGPT model instead of Gemini"
    )
    args = parser.parse_args()
    
    serve(use_gemini=not args.local)
