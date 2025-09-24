from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os
import google.generativeai as genai
import json
from datetime import datetime
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="PMC Services Chatbot API",
    description="Chatbot API for Pune Municipal Corporation Services",
    version="1.0.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files directory to serve images and other assets
app.mount("/static", StaticFiles(directory="."), name="static")

# Configure Gemini API
api_key = os.getenv('GEMINI_API_KEY')
if not api_key:
    logger.warning("GEMINI_API_KEY not found in environment variables. Please set it in .env file.")
    # Create a mock model for testing without API key
    model = None
else:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.0-flash-exp')

# Pydantic models for request/response
class ChatRequest(BaseModel):
    message: str
    conversation_history: list = []

class ChatResponse(BaseModel):
    response: str
    timestamp: str
    service_references: list = []

class MunicipalChatbot:
    def __init__(self, json_file_path):
        self.municipal_data = self.load_municipal_data(json_file_path)
        
    def load_municipal_data(self, json_file_path):
        """Load and format municipal services data"""
        try:
            with open(json_file_path, 'r', encoding='utf-8') as file:
                data = json.load(file)
            
            # Convert JSON to readable text format for the model
            formatted_data = self.format_data_for_context(data)
            logger.info(f"Loaded municipal data with {len(data)} departments")
            return formatted_data
            
        except Exception as e:
            logger.error(f"Error loading municipal data: {e}")
            return ""
    
    def format_data_for_context(self, data):
        """Format JSON data into readable text for the AI model"""
        context = "PUNE MUNICIPAL CORPORATION SERVICES DATABASE:\n\n"
        
        for department in data:
            context += f"DEPARTMENT: {department['Department']}\n"
            context += "=" * 50 + "\n"
            
            for service in department['Service']:
                context += f"\nSERVICE: {service['Service']}\n"
                context += f"Service ID: {service['service_id']}\n"
                context += f"Description: {service['description']}\n"
                
                # Handle documents (can be list or string)
                docs = service.get('Documents Required', 'No documents specified')
                if isinstance(docs, list):
                    if docs and docs != ["No Documents are required"]:
                        context += f"Required Documents:\n"
                        for doc in docs:
                            context += f"   - {doc}\n"
                    else:
                        context += f"Required Documents: No documents required\n"
                else:
                    context += f"Required Documents: {docs}\n"
                
                # Approval process
                approval_process = service.get('Levels of Approval / process', {})
                if isinstance(approval_process, dict):
                    context += f"Approval Process:\n"
                    for level, approver in approval_process.items():
                        if approver and approver != "-":
                            context += f"   {level}: {approver}\n"
                else:
                    context += f"Approval Process: {approval_process}\n"
                
                # Physical verification
                verification = service.get('Physical Verification', 'Not specified')
                context += f"Physical Verification: {verification}\n"
                
                # Output format
                output_format = service.get('Output Certificate Format', 'Not specified')
                context += f"Output Certificate Format: {output_format}\n"
                
                # Application link
                app_link = service.get('application link / url', 'Not available')
                context += f"Application Link: {app_link}\n"
                
                context += "-" * 40 + "\n"
            
            context += "\n"
        
        return context
    
    def create_prompt(self, user_message, conversation_history=None):
        """Create the prompt for Gemini API"""

        # Build conversation context if provided
        conversation_context = ""
        if conversation_history:
            conversation_context = "\nCONVERSATION HISTORY:\n"
            for msg in conversation_history[-5:]:  # Keep last 5 messages for context
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                conversation_context += f"{role.upper()}: {content}\n"
            conversation_context += "\n"

        prompt = f"""You are a friendly, helpful assistant for Pune Municipal Corporation (PMC) services. You're like a knowledgeable government office helper who gives clear, concise answers without overwhelming users with unnecessary details.

KEY INSTRUCTIONS:
1. **ANALYZE QUESTION TYPE FIRST**: Before responding, determine if it's a general inquiry, specific service request, document question, simple factual query, or needs clarification
2. Respond like a human - be friendly, conversational, and direct
3. Answer exactly what the user is asking for - don't provide extra information unless requested
4. If they ask "how to get marriage certificate", give them the direct steps and link, not all possible related services
5. Be concise but complete - provide essential information without jargon or technical details
6. Only mention service ID if it's directly relevant to their question
7. If something is unclear, ask for clarification rather than guessing
8. **IMPORTANT**: When providing links, use this format: LINK:URL (e.g., "LINK:http://example.com"). This will create a clickable "LINK" text instead of showing the full URL.

RESPONSE STYLE:
- **VARY YOUR RESPONSE OPENERS**: Choose the most appropriate opener based on context and question type:
  - General help requests: "Sure, I can help you with..." or "I'd be happy to assist with..."
  - Specific service requests: "For [service name], you'll need..." or "To apply for [service name], follow these steps:"
  - Document/status questions: "Here's what you need to know about..." or "For [service name], the requirements are:"
  - Clarification needed: "To better assist you, could you please clarify..." or "I need more information about..."
  - Simple factual questions: Start directly with the answer
  - Complex processes: "Let me break this down for you..." or "Here are the steps to..."
  - Follow-up questions: "Regarding your question about..." or "About [topic]..."
- **MATCH THE USER'S TONE**: If they're casual, be casual. If they're formal, be more professional
- Give direct, actionable steps without unnecessary pleasantries
- When mentioning links, use "LINK:URL" format instead of embedding the full URL in text
- End with an offer for more help: "Let me know if you need anything else!" (only when it makes sense)
- Keep responses under 200 words unless they ask for detailed information
- **FORMAT LISTS PROPERLY**: When listing multiple items (documents, steps, requirements), use this exact format:
  - Item 1
  - Item 2
  - Item 3
  Each item should be on its own line with a dash (-) at the beginning, followed by a space, then the item text
- Use proper line breaks to make lists readable and well-structured
- Put each list item on a separate line for better readability

RESPONSE EXAMPLES:
- General question: "What services do you offer?" → "Sure, I can help you with information about PMC services. We offer various municipal services including..."
- Specific service: "How do I get a marriage certificate?" → "To get a marriage certificate, you'll need to apply online through LINK:http://example.com and submit these documents: - Marriage application form - Proof of age..."
- Document requirements: "What documents do I need for birth certificate?" → "For a birth certificate, you'll need: - Hospital birth report - Parents' ID proof - Address proof..."
- Simple question: "What is the contact number?" → "The PMC customer service number is 020-25501000."
- Clarification: "I need help with property tax" → "To better assist you with property tax, could you please specify if you need help with payment, assessment, or something else?"

MUNICIPAL SERVICES DATA:
{self.municipal_data}

{conversation_context}

USER QUESTION: {user_message}

Please provide a friendly, concise response that directly answers their question."""

        return prompt
    
    def extract_service_references(self, response_text):
        """Extract service IDs and names from the response"""
        import re
        
        # Pattern to match service IDs
        service_id_pattern = r'service-\d+'
        service_ids = re.findall(service_id_pattern, response_text)
        
        # For simplicity, return the service IDs found
        return list(set(service_ids))
    
    async def get_response(self, user_message, conversation_history=None):
        """Get response from Gemini API"""
        try:
            # If model is not available, return a mock response
            if model is None:
                logger.warning("Gemini model not available, returning mock response")
                mock_response = f"I understand you asked: '{user_message}'. This is a mock response since the Gemini API key is not configured. Please add your GEMINI_API_KEY to the .env file to get real AI responses."
                return {
                    "response": mock_response,
                    "service_references": []
                }

            prompt = self.create_prompt(user_message, conversation_history)

            response = model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.3,  # Slightly higher for more natural responses
                    "max_output_tokens": 512,  # Limit to encourage concise responses
                    "top_p": 0.9,
                    "top_k": 40
                }
            )

            if response.text:
                service_refs = self.extract_service_references(response.text)
                return {
                    "response": response.text,
                    "service_references": service_refs
                }
            else:
                raise Exception("Empty response from Gemini API")

        except Exception as e:
            logger.error(f"Error getting response from Gemini: {e}")
            raise Exception(f"Failed to generate response: {str(e)}")

# Initialize chatbot (adjust path to your JSON file)
chatbot = MunicipalChatbot('json data/final.json')

@app.on_event("startup")
async def startup_event():
    """Initialize the application"""
    logger.info("PMC Services Chatbot API starting up...")
    if not chatbot.municipal_data:
        logger.warning("Municipal data not loaded properly")

@app.get("/", response_class=HTMLResponse)
async def root():
    """Root endpoint - serves chatbot.html directly"""
    try:
        with open("chatbot.html", "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content)
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Chatbot file not found</h1>", status_code=404)

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """Main chat endpoint"""
    try:
        if not request.message.strip():
            raise HTTPException(status_code=400, detail="Message cannot be empty")
        
        logger.info(f"Received chat request: {request.message[:50]}...")
        
        # Get response from chatbot
        result = await chatbot.get_response(
            request.message, 
            request.conversation_history
        )
        
        response = ChatResponse(
            response=result["response"],
            timestamp=datetime.now().isoformat(),
            service_references=result["service_references"]
        )
        
        logger.info(f"Generated response with {len(result['service_references'])} service references")
        return response
        
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Detailed health check"""
    try:
        # Test API key
        api_key_status = "configured" if os.getenv('GEMINI_API_KEY') else "missing"
        
        # Check data loading
        data_status = "loaded" if chatbot.municipal_data else "failed"
        
        return {
            "status": "healthy",
            "api_key": api_key_status,
            "municipal_data": data_status,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")

@app.get("/services/search")
async def search_services(query: str):
    """Search for specific services (optional endpoint)"""
    try:
        # Simple search in the loaded data
        # This could be enhanced with fuzzy matching
        results = []
        
        # In a real implementation, you'd search through the original JSON
        # For now, return a simple response
        return {
            "query": query,
            "results": results,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in search endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/clear-memory")
async def clear_memory():
    """Clear chat history and memory"""
    try:
        # This endpoint can be used to clear any stored conversation history
        # For now, it just returns success as the frontend handles clearing local history
        return {
            "status": "success",
            "message": "Chat memory cleared successfully",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error clearing memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn

    # Run the server
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,  # Disabled for testing
        log_level="info"
    )