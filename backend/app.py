from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os
import logging
import re
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend communication
load_dotenv()

# Configuration
API_KEY = os.getenv('VEXT_API_KEY')
CHANNEL_TOKEN = os.getenv('CHANNEL_TOKEN')
ENVIRONMENT = os.getenv('ENVIRONMENT', 'production')  # Default to production for Render
PORT = int(os.getenv('PORT', 5000))  # Render provides PORT environment variable

# External API endpoint
EXTERNAL_API_URL = f'https://payload.vextapp.com/hook/AKEIS1C8PZ/catch/{CHANNEL_TOKEN}'

def format_text_response(text):
    """
    Format the text response for better readability
    """
    # Remove markdown bold formatting (**text**) and replace with plain text
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    
    # Add line breaks before numbered lists with proper spacing
    text = re.sub(r'(\d+\.\s\*\*)', r'\n\n\1', text)
    text = re.sub(r'(\d+\.\s)', r'\n\n\1', text)
    
    # Add line breaks before sub-bullet points with dashes
    text = re.sub(r'(\s+-\s)', r'\n   - ', text)
    
    # Add line breaks before main bullet points
    text = re.sub(r'(\s-\s)', r'\n- ', text)
    
    # Add spacing before "For" statements (stakeholder sections)
    text = re.sub(r'(- For\s)', r'\n- For ', text)
    
    # Add spacing before "In India" and "In the UK" (regulatory sections)
    text = re.sub(r'(- In\s)', r'\n- In ', text)
    
    # Add extra spacing before major sections
    text = re.sub(r'(Overview of|Feasibility and|Benefits for|Challenges and|Regulatory|Market Insights)', r'\n\1', text)
    
    # Ensure proper spacing after colons in main sections
    text = re.sub(r'(:)(\s*-)', r':\n\2', text)
    
    # Clean up multiple consecutive line breaks (max 2)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Remove leading/trailing whitespace
    text = text.strip()
    
    # Ensure numbered sections have proper spacing
    text = re.sub(r'(\d+\.\s)([A-Z])', r'\1\n\2', text)
    
    return text

@app.route('/', methods=['GET'])
def home():
    """Root endpoint for health check"""
    return jsonify({
        "status": "online",
        "service": "chatbot-bridge",
        "environment": ENVIRONMENT
    }), 200

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy", 
        "service": "chatbot-bridge",
        "environment": ENVIRONMENT
    }), 200

@app.route('/chat', methods=['POST'])
def chat():
    """
    Handle chat messages from frontend and forward to external API
    """
    try:
        # Get message from frontend
        data = request.get_json()
        
        if not data or 'message' not in data:
            logger.error("No message provided in request")
            return jsonify({"error": "No message provided"}), 400
        
        user_message = data['message']
        logger.info(f"Received message: {user_message}")
        
        # Prepare payload for external API
        payload = {
            "payload": user_message,
            "env": ENVIRONMENT
        }
        
        headers = {
            'Content-Type': 'application/json',
            'Apikey': f'Api-Key {API_KEY}'
        }
        
        # Send request to external API
        logger.info(f"Sending request to external API: {EXTERNAL_API_URL}")
        response = requests.post(
            EXTERNAL_API_URL,
            json=payload,
            headers=headers,
            timeout=30  # 30 second timeout
        )
        
        # Check if request was successful
        if response.status_code == 200:
            # Parse the JSON response
            try:
                response_data = response.json()
                # Extract the text content from the response
                if 'text' in response_data:
                    raw_text = response_data['text']
                    # Format the text for better readability
                    formatted_response = format_text_response(raw_text)
                    logger.info(f"Received successful response: {formatted_response[:100]}...")
                    return formatted_response, 200
                else:
                    # If no 'text' field, return the full response
                    logger.info(f"Received response without 'text' field: {response_data}")
                    return str(response_data), 200
            except ValueError:
                # If response is not JSON, return as text
                response_text = response.text
                logger.info(f"Received non-JSON response: {response_text}")
                return response_text, 200
        else:
            logger.error(f"External API error: {response.status_code} - {response.text}")
            return jsonify({"error": f"External API error: {response.status_code}"}), response.status_code
            
    except requests.exceptions.Timeout:
        logger.error("Request to external API timed out")
        return jsonify({"error": "Request timed out. Please try again."}), 408
    
    except requests.exceptions.ConnectionError:
        logger.error("Connection error to external API")
        return jsonify({"error": "Connection error. Please check your internet connection."}), 503
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error: {str(e)}")
        return jsonify({"error": f"Request error: {str(e)}"}), 500
    
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500

@app.route('/config', methods=['GET'])
def get_config():
    """
    Get current configuration (for debugging - don't expose sensitive data in production)
    """
    if ENVIRONMENT == 'production':
        return jsonify({
            "environment": ENVIRONMENT,
            "status": "API keys configured" if API_KEY and CHANNEL_TOKEN else "API keys missing"
        })
    else:
        return jsonify({
            "environment": ENVIRONMENT,
            "api_key_configured": bool(API_KEY),
            "channel_token_configured": bool(CHANNEL_TOKEN),
            "external_url": EXTERNAL_API_URL
        })

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    # Check configuration on startup
    if not API_KEY:
        logger.error("VEXT_API_KEY environment variable not set!")
    if not CHANNEL_TOKEN:
        logger.error("CHANNEL_TOKEN environment variable not set!")
    
    if API_KEY and CHANNEL_TOKEN:
        logger.info("Configuration loaded successfully")
    
    logger.info(f"Starting Flask app on port {PORT}")
    logger.info(f"Environment: {ENVIRONMENT}")
    logger.info(f"External API URL: {EXTERNAL_API_URL}")
    
    # Run the Flask app (Render handles the host and port)
    app.run(host='0.0.0.0', port=PORT, debug=(ENVIRONMENT != 'production'))