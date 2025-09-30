from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os
import google.generativeai as genai
import json
import httpx
from datetime import datetime
import logging
from dotenv import load_dotenv
import re
import unicodedata

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

class ApplicationTrackRequest(BaseModel):
    application_id: str

class ApplicationTrackResponse(BaseModel):
    remark: str
    app_status: str
    token: str
    timestamp: str

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
    
    def is_tracking_request(self, user_message):
        """Check if the user message is asking for application tracking"""
        tracking_keywords = [
            'track', 'status', 'check application', 'application status', 'track application',
            'my application', 'application id', 'token', 'check status', 'where is my',
            'application tracking', 'track my', 'status of', 'check my application',
            'application number', 'reference number', 'tracking number', 'follow up',
            'progress', 'update', 'tracker', 'trace', 'follow'
        ]
        
        # Convert to lowercase for case-insensitive matching
        message_lower = user_message.lower()
        
        # Check for tracking keywords
        return any(keyword in message_lower for keyword in tracking_keywords)
    
    def detect_language(self, text):
        """Detect if the text contains Marathi Devanagari script"""
        if not text:
            return 'en'
        
        # Count Devanagari characters
        devanagari_count = 0
        total_chars = 0
        
        for char in text:
            if char.strip():  # Skip whitespace
                total_chars += 1
                # Check if character is in Devanagari Unicode block (U+0900-U+097F)
                if '\u0900' <= char <= '\u097F':
                    devanagari_count += 1
        
        # If more than 30% of characters are Devanagari, consider it Marathi
        if total_chars > 0 and (devanagari_count / total_chars) > 0.3:
            return 'mr'  # Marathi
        return 'en'  # English (default)
    
    def extract_application_id(self, user_message):
        """Extract application ID from user message if present"""
        # Look for patterns like: numbers, alphanumeric codes
        patterns = [
            r'\b([A-Z]{2}\d{14,})\b',     # Pattern like PL10000004252600772
            r'\b([A-Z]{2,}\d{6,})\b',     # Pattern like ABC123456
            r'\b(\d{8,})\b',              # Pattern like 12345678
            r'\b([A-Z]\d{7,})\b',         # Pattern like A1234567
            r'\b(\d{4,6}[-/]\d{4,6})\b',  # Pattern like 1234-5678 or 1234/5678
            r'\b([A-Z]{1,3}\d{10,})\b',   # Pattern for longer alphanumeric IDs
        ]
        
        for pattern in patterns:
            match = re.search(pattern, user_message)
            if match:
                return match.group(1)
        
        return None

    async def track_application(self, application_id):
        """Call PMC API to track application status"""
        try:
            api_url = f"https://services.pmc.gov.in/getStatusByToken/{application_id}"
            
            # Create client with SSL verification disabled for government websites
            async with httpx.AsyncClient(
                timeout=15.0,
                verify=False,  # Disable SSL verification for government sites
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Accept': 'application/json, text/plain, */*',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                }
            ) as client:
                response = await client.get(api_url)
                
                logger.info(f"API Response Status: {response.status_code}")
                logger.info(f"API Response Content: {response.text[:200]}...")
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        return {
                            "success": True,
                            "data": data
                        }
                    except ValueError as e:
                        # If JSON parsing fails, check if it's HTML (error page)
                        if 'html' in response.text.lower():
                            return {
                                "success": False,
                                "error": "The application ID was not found in the PMC database"
                            }
                        else:
                            return {
                                "success": False,
                                "error": f"Invalid response format from PMC API"
                            }
                elif response.status_code == 404:
                    return {
                        "success": False,
                        "error": "Application ID not found in the PMC database"
                    }
                else:
                    return {
                        "success": False,
                        "error": f"PMC API returned status code {response.status_code}"
                    }
                    
        except httpx.TimeoutException:
            return {
                "success": False,
                "error": "Request timed out. The PMC server might be busy. Please try again later."
            }
        except httpx.ConnectError:
            return {
                "success": False,
                "error": "Unable to connect to PMC servers. Please check your internet connection and try again."
            }
        except Exception as e:
            logger.error(f"Error tracking application {application_id}: {e}")
            return {
                "success": False,
                "error": f"Unable to fetch application status. Please try again later or contact PMC customer service."
            }

    def create_prompt(self, user_message, conversation_history=None):
        """Create the prompt for Gemini API"""
        
        # Detect language of the user message
        detected_language = self.detect_language(user_message)
        
        # Build conversation context if provided
        conversation_context = ""
        if conversation_history:
            conversation_context = "\nCONVERSATION HISTORY:\n"
            for msg in conversation_history[-5:]:  # Keep last 5 messages for context
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                conversation_context += f"{role.upper()}: {content}\n"
            conversation_context += "\n"

        # Language-specific instructions
        language_instruction = ""
        if detected_language == 'mr':
            language_instruction = """
**LANGUAGE DETECTION**: The user's message contains Marathi Devanagari script. You MUST respond in Marathi (मराठी) using Devanagari script. Be natural and conversational in Marathi, using appropriate Marathi terms for government services and processes.
"""
        else:
            language_instruction = """
**LANGUAGE DETECTION**: The user's message is in English. Respond in English as usual.
"""

        prompt = f"""You are a friendly, helpful assistant for Pune Municipal Corporation (PMC) services. You're like a knowledgeable government office helper who gives clear, concise answers without overwhelming users with unnecessary details.

{language_instruction}

KEY INSTRUCTIONS:
1. **ANALYZE QUESTION TYPE FIRST**: Before responding, determine if it's a general inquiry, specific service request, document question, simple factual query, APPLICATION TRACKING REQUEST, or needs clarification
2. **APPLICATION TRACKING DETECTION**: If the user asks about tracking, checking status, or mentions application ID/token/reference number, respond with: "TRACK_APPLICATION_REQUEST" followed by your normal helpful response
3. **COMPLETE INFORMATION REQUIREMENT**: When asked about documents, requirements, or processes, you MUST provide ALL information available in the knowledge base. Do not summarize or truncate document lists - include every single document mentioned in the data.
4. **DOCUMENT COMPLETENESS**: If the knowledge base shows 16 documents, you must list all 16. If it shows 5 documents, list all 5. Never provide partial lists.
5. Respond like a human - be friendly, conversational, and direct
6. Answer exactly what the user is asking for - don't provide extra information unless requested
7. If they ask "how to get marriage certificate", give them the direct steps and link, not all possible related services
8. Be concise but complete - provide essential information without jargon or technical details
9. Only mention service ID if it's directly relevant to their question
10. If something is unclear, ask for clarification rather than guessing
11. **IMPORTANT**: When providing links, use this format: LINK:URL (e.g., "LINK:http://example.com"). This will create a clickable "LINK" text instead of showing the full URL.

RESPONSE STYLE:
- **VARY YOUR RESPONSE OPENERS**: Choose the most appropriate opener based on context and question type:
  - General help requests: "Sure, I can help you with..." or "I'd be happy to assist with..."
  - Specific service requests: "For [service name], you'll need..." or "To apply for [service name], follow these steps:"
  - Document/status questions: "Here's what you need to know about..." or "For [service name], the requirements are:"
  - Application tracking: "I can help you track your application..." or "To check your application status..."
  - Clarification needed: "To better assist you, could you please clarify..." or "I need more information about..."
  - Simple factual questions: Start directly with the answer
  - Complex processes: "Let me break this down for you..." or "Here are the steps to..."
  - Follow-up questions: "Regarding your question about..." or "About [topic]..."
- **MATCH THE USER'S TONE**: If they're casual, be casual. If they're formal, be more professional
- Give direct, actionable steps without unnecessary pleasantries
- When mentioning links, use "LINK:URL" format instead of embedding the full URL in text
- End with an offer for more help: "Let me know if you need anything else!" (only when it makes sense)
- **DOCUMENT LISTS MUST BE COMPLETE**: When listing documents, include EVERY document from the knowledge base. Count them if needed to ensure completeness.
- **FORMAT LISTS PROPERLY**: When listing multiple items (documents, steps, requirements), use this exact format:
  - Item 1
  - Item 2
  - Item 3
  Each item should be on its own line with a dash (-) at the beginning, followed by a space, then the item text
- Use proper line breaks to make lists readable and well-structured
- Put each list item on a separate line for better readability
- **CRITICAL**: Never truncate or summarize document lists. If the data shows 16 documents, list all 16. If it shows 3 documents, list all 3.

RESPONSE EXAMPLES:
- General question: "What services do you offer?" → "Sure, I can help you with information about PMC services. We offer various municipal services including..."
- Specific service: "How do I get a marriage certificate?" → "To get a marriage certificate, you'll need to apply online through LINK:http://example.com and submit these documents: - Marriage application form - Proof of age..."
- Document requirements: "What documents do I need for birth certificate?" → "For a birth certificate, you'll need: - Hospital birth report - Parents' ID proof - Address proof..."
- Simple question: "What is the contact number?" → "The PMC customer service number is 020-25501000."
- Clarification: "I need help with property tax" → "To better assist you with property tax, could you please specify if you need help with payment, assessment, or something else?"
- Application tracking: "I want to track my application" → "TRACK_APPLICATION_REQUEST I can help you track your application status. Please provide your application ID or reference number so I can check the current status for you."

MARATHI RESPONSE EXAMPLES:
- General question: "तुम्ही कोणत्या सेवा देत?" → "नक्कीच, मी तुम्हाला PMC सेवांबद्दल माहिती देऊ शकतो. आम्ही विविध नगरपालिका सेवा देतो ज्यात..."
- Specific service: "लग्नाचे प्रमाणपत्र कसे मिळेल?" → "लग्नाचे प्रमाणपत्र मिळवण्यासाठी, तुम्हाला ऑनलाइन अर्ज करावा लागेल LINK:http://example.com आणि हे कागदपत्रे सादर करावी लागतील: - लग्न अर्ज फॉर्म - वयाचा पुरावा..."
- Document requirements: "जन्म प्रमाणपत्रासाठी कोणते कागदपत्रे लागतात?" → "जन्म प्रमाणपत्रासाठी तुम्हाला हे लागेल: - रुग्णालयातील जन्म अहवाल - पालकांचा ओळखपत्र - पत्ता पुरावा..."
- Simple question: "संपर्क क्रमांक काय आहे?" → "PMC ग्राहक सेवा क्रमांक 020-25501000 आहे."
- Application tracking: "माझा अर्ज ट्रॅक करायचा आहे" → "TRACK_APPLICATION_REQUEST मी तुमच्या अर्जाची स्थिती तपासण्यात मदत करू शकतो. कृपया तुमचा अर्ज क्रमांक किंवा संदर्भ क्रमांक द्या जेणेकरून मी तुमच्यासाठी सद्यस्थिती तपासू शकेन."

CRITICAL DOCUMENT COMPLETENESS EXAMPLES:
- If asked "documents for Marriage Hall License" and the knowledge base has 16 documents, you MUST list all 16 documents, not 8 or 9.
- If asked "मंगलकार्यालय परवाना साठी कागदपत्रे" and the knowledge base has 16 documents, you MUST list all 16 documents in Marathi.
- Always count and verify: "Here are all 16 documents required for Marriage Hall License: [list all 16]"
- Never say "some documents include" or "key documents are" - always say "ALL documents required are" and list every single one.

MUNICIPAL SERVICES DATA:
{self.municipal_data}

{conversation_context}

USER QUESTION: {user_message}

**FINAL REMINDER**: When listing documents, requirements, or processes, you MUST include ALL items from the knowledge base. Do not summarize, truncate, or provide partial lists. If the data contains 16 documents, list all 16. If it contains 3 documents, list all 3. Count the items if needed to ensure completeness.

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
    
    def validate_document_completeness(self, user_message, response_text):
        """Validate that document responses are complete"""
        # Check if the query is about documents
        document_keywords = ['document', 'कागदपत्र', 'कागद', 'पत्र', 'required', 'लागणारी', 'लागतात']
        if not any(keyword.lower() in user_message.lower() for keyword in document_keywords):
            return response_text
        
        # Count documents in response
        document_count = response_text.count('- ')
        
        # If response has documents but seems incomplete (less than 5), add a note
        if document_count > 0 and document_count < 5:
            response_text += f"\n\nNote: Please ensure you have all required documents. If you need the complete list, please ask again."
        
        return response_text
    
    async def get_response(self, user_message, conversation_history=None):
        """Get response from Gemini API"""
        try:
            # First, always check if the message contains an application ID (regardless of other content)
            app_id = self.extract_application_id(user_message)
            
            if app_id:
                # We found an application ID, track it immediately
                logger.info(f"Found application ID: {app_id}, tracking immediately...")
                tracking_result = await self.track_application(app_id)
                
                if tracking_result["success"]:
                    data = tracking_result["data"]
                    status_message = f"Application Status Update:\n\n"
                    status_message += f"Application ID: {data.get('token', app_id)}\n"
                    status_message += f"Status: {data.get('appStatus', 'Unknown')}\n"
                    status_message += f"Remark: {data.get('remark', 'No additional information')}\n\n"
                    
                    # Add status interpretation
                    status = data.get('appStatus', '').upper()
                    if status == 'APPROVED':
                        status_message += "Great news! Your application has been approved. You can proceed to collect your documents or certificate as applicable."
                    elif status == 'PENDING':
                        status_message += "Your application is currently being processed. Please wait for further updates."
                    elif status == 'REJECTED':
                        status_message += "Your application has been rejected. Please contact the relevant department for more information on next steps."
                    elif status == 'IN_PROGRESS':
                        status_message += "Your application is currently in progress. We'll notify you once there's an update."
                    else:
                        status_message += "Please contact PMC customer service at 020-25501000 for more details about this status."
                    
                    return {
                        "response": status_message,
                        "service_references": [],
                        "is_tracking": True
                    }
                else:
                    error_message = f"Sorry, I couldn't retrieve the status for application ID {app_id}. "
                    error_message += f"Error: {tracking_result['error']}\n\n"
                    error_message += "Please double-check your application ID and try again, or contact PMC customer service at 020-25501000 for assistance."
                    
                    return {
                        "response": error_message,
                        "service_references": [],
                        "is_tracking": True
                    }
            
            # Check if this is a tracking request without an ID
            elif self.is_tracking_request(user_message):
                # No application ID found, ask for it
                ask_for_id = "I can help you track your application status! To check your application, I'll need your application ID or reference number.\n\n"
                ask_for_id += "Please provide your application ID (it usually looks like ABC123456 or a series of numbers) and I'll get the current status for you."
                
                return {
                    "response": ask_for_id,
                    "service_references": [],
                    "is_tracking": True,
                    "needs_app_id": True
                }

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
                # Check if the response indicates a tracking request
                is_tracking = "TRACK_APPLICATION_REQUEST" in response.text
                clean_response = response.text.replace("TRACK_APPLICATION_REQUEST", "").strip()
                
                # Validate document completeness
                validated_response = self.validate_document_completeness(user_message, clean_response)
                
                service_refs = self.extract_service_references(validated_response)
                result = {
                    "response": validated_response,
                    "service_references": service_refs
                }
                
                if is_tracking:
                    result["is_tracking"] = True
                    result["needs_app_id"] = True
                    
                return result
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

@app.post("/track-application")
async def track_application_endpoint(request: ApplicationTrackRequest):
    """Dedicated endpoint for application tracking"""
    try:
        logger.info(f"Tracking application: {request.application_id}")
        
        # Call the tracking function
        result = await chatbot.track_application(request.application_id)
        
        if result["success"]:
            data = result["data"]
            return ApplicationTrackResponse(
                remark=data.get("remark", "OK"),
                app_status=data.get("appStatus", "Unknown"),
                token=data.get("token", request.application_id),
                timestamp=datetime.now().isoformat()
            )
        else:
            raise HTTPException(status_code=404, detail=result["error"])
            
    except Exception as e:
        logger.error(f"Error tracking application: {e}")
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