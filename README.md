# PMC Services Chatbot

An AI-powered chatbot assistant for Pune Municipal Corporation services. Get instant help with licenses, permits, certificates, and all civic amenities.

## Features

- 🤖 AI-powered responses using Google's Gemini AI
- 📚 Comprehensive PMC services database
- 💬 Interactive chat interface
- 🌐 RESTful API endpoints
- 📱 Mobile-responsive design
- 🔄 Real-time conversation support

## Quick Start

### Method 1: Using the Startup Script (Recommended)

```bash
# Make sure you're in the project directory
cd /home/stark/Desktop/RTS/Data

# Run the startup script
./start_chatbot.sh
```

### Method 2: Manual Setup

```bash
# 1. Activate virtual environment (IMPORTANT!)
source venv/bin/activate

# 2. Install dependencies (if needed)
pip install -r requirements.txt

# 3. Start the server
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**⚠️ Important**: Always activate the virtual environment first using `source venv/bin/activate` before running any commands. The virtual environment uses Python 3.11 which is compatible with all dependencies.

## Access Points

Once the server is running, you can access:

- **Main Page**: http://localhost:8000 (serves the chat interface directly)
- **API Endpoint**: http://localhost:8000/chat
- **Health Check**: http://localhost:8000/health
- **API Documentation**: http://localhost:8000/docs

## API Usage

### Chat Endpoint

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "How do I apply for a birth certificate?"}'
```

Response:
```json
{
  "response": "Detailed response with service information...",
  "timestamp": "2025-09-23T18:01:55.096790",
  "service_references": ["service-41"]
}
```

### Health Check

```bash
curl http://localhost:8000/health
```

## Sample Questions

- "How to apply for birth certificate?"
- "How to get trade license?"
- "Property tax payment process"
- "How to apply for building permit?"
- "Water connection application"
- "How to get fire NOC?"
- "Dog license application"

## Configuration

### Environment Variables

Create a `.env` file with your Gemini API key:

```env
GEMINI_API_KEY=your_actual_api_key_here
```

Get your API key from: https://aistudio.google.com/app/apikey

### Data Source

The chatbot uses municipal services data from `json data/final.json`. This file contains comprehensive information about all PMC services including:

- Service descriptions
- Required documents
- Approval processes
- Application links
- Physical verification requirements

## Project Structure

```
RTS/Data/
├── main.py                 # FastAPI server
├── start_bot.py           # Alternative startup script
├── start_chatbot.sh       # Main startup script
├── requirements.txt       # Python dependencies
├── new.html               # Main chat interface
├── json data/
│   └── final.json         # PMC services database
└── venv/                  # Virtual environment
```

## Troubleshooting

### Server won't start
1. Make sure you're using Python 3.8+
2. Activate the virtual environment: `source venv/bin/activate`
3. Install dependencies: `pip install -r requirements.txt`
4. Check that `.env` file exists with valid API key

### Chat interface not loading
- Ensure the server is running with `--reload` flag
- Check that `new.html` exists in the root directory
- Try hard refresh (Ctrl+F5) in browser

### API errors
- Verify your Gemini API key is correct
- Check the health endpoint: http://localhost:8000/health
- Ensure municipal data loaded properly

### Virtual Environment Issues
- Always activate venv first: `source venv/bin/activate`
- The virtual environment uses Python 3.11 (compatible with all dependencies)
- If you get import errors, make sure you're in the activated environment

## Development

### Adding New Services
1. Update `json data/final.json` with new service information
2. Restart the server to reload data
3. Test with sample questions

### Customizing the Chat Interface
1. Edit `new.html`
2. Modify CSS styles in the `<style>` section
3. Update sample questions in the JavaScript section

## Support

For issues or questions:
1. Check the health endpoint for system status
2. Review server logs for error details
3. Ensure all dependencies are installed correctly

---

**Note**: This chatbot provides information based on PMC's official services database. For official applications, please visit the respective PMC portals mentioned in the responses.
