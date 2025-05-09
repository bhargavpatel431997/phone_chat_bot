import os
import asyncio
import json
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse
import openai

# Load environment variables from .env file
load_dotenv(override=True)

# Initialize OpenAI client
openai.api_key = os.getenv("OPENAI_API_KEY")

app = FastAPI()

# Global storage for call tracking
call_stats = {}
active_calls = {}
silence_counters = {}

@app.post("/inbound-call")
async def handle_inbound_call(request: Request):
    """Handle incoming Twilio calls"""
    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    
    print(f"Received inbound call with SID: {call_sid}")
    
    # Initialize call stats
    initialize_call_stats(call_sid)
    
    # Initialize silence counter
    silence_counters[call_sid] = 0
    
    # Store in active calls
    active_calls[call_sid] = {
        "status": "active",
        "last_activity": datetime.now()
    }
    
    # Start silence detection in background
    asyncio.create_task(monitor_silence(call_sid))
    
    # Return TwiML to answer and gather speech
    response = VoiceResponse()
    response.say("Welcome to our phone chatbot. How can I help you today?")
    
    # Start gathering speech
    gather = response.gather(
        input='speech',
        action=f'/speech?call_sid={call_sid}',
        method='POST',
        speechTimeout='auto',
        speechModel='phone_call'
    )
    
    # Add a redirect in case the gather times out
    response.redirect(f'/silence?call_sid={call_sid}')
    
    return Response(content=str(response), media_type="application/xml")

@app.post("/speech")
async def handle_speech(request: Request):
    """Handle speech input from Twilio"""
    try:
        form_data = await request.form()
        call_sid = request.query_params.get("call_sid")
        speech_result = form_data.get("SpeechResult")
        
        print(f"Received speech from call {call_sid}: {speech_result}")
        
        # If call is no longer active, just return a hangup
        if call_sid not in active_calls or active_calls[call_sid]["status"] != "active":
            response = VoiceResponse()
            response.hangup()
            return Response(content=str(response), media_type="application/xml")
        
        # Reset silence counter when user speaks
        if call_sid in silence_counters:
            silence_counters[call_sid] = 0
            
        # Update activity timestamp
        if call_sid in active_calls:
            active_calls[call_sid]["last_activity"] = datetime.now()
        
        # Update stats
        if call_sid in call_stats:
            update_call_stats(call_sid, "messages_received")
        
        # Process the speech with OpenAI directly
        response_text = process_speech_with_openai(call_sid, speech_result)
        
        # Create TwiML response with bot's response and new gather
        response = VoiceResponse()
        response.say(response_text)
        
        # Check if user said goodbye
        if any(phrase in speech_result.lower() for phrase in ["goodbye", "bye", "end call", "hang up"]):
            # Update call status
            if call_sid in active_calls:
                active_calls[call_sid]["status"] = "ending"
            
            # End the call
            response.hangup()
        else:
            # Continue gathering speech
            gather = response.gather(
                input='speech',
                action=f'/speech?call_sid={call_sid}',
                method='POST',
                speechTimeout='auto',
                speechModel='phone_call'
            )
            
            # Add a redirect in case the gather times out
            response.redirect(f'/silence?call_sid={call_sid}')
        
        # Update stats
        update_call_stats(call_sid, "messages_sent")
        
        return Response(content=str(response), media_type="application/xml")
    except Exception as e:
        print(f"Error in speech handler: {e}")
        # Return a generic response on error
        response = VoiceResponse()
        response.say("I'm sorry, I had trouble processing that. Could you try again?")
        response.gather(
            input='speech',
            action=f'/speech?call_sid={call_sid}',
            method='POST',
            speechTimeout='auto',
            speechModel='phone_call'
        )
        return Response(content=str(response), media_type="application/xml")

@app.post("/silence")
async def handle_silence(request: Request):
    """Handle silence events from Twilio"""
    call_sid = request.query_params.get("call_sid")
    
    print(f"Silence detected for call {call_sid}")
    
    # If call is no longer active, just return a hangup
    if call_sid not in active_calls or active_calls[call_sid]["status"] != "active":
        response = VoiceResponse()
        response.hangup()
        return Response(content=str(response), media_type="application/xml")
    
    # Increment silence counter
    if call_sid in call_stats:
        update_call_stats(call_sid, "silence_events")
        silence_event_count = call_stats[call_sid]["silence_events"]
        
        # Handle based on silence count
        if silence_event_count <= 3:
            # Get appropriate prompt
            prompts = [
                "I noticed you've been quiet. Are you still there?",
                "I'm still here if you'd like to continue our conversation.",
                "If I don't hear from you soon, I'll have to end our call."
            ]
            prompt_index = min(silence_event_count - 1, len(prompts) - 1)
            prompt = prompts[prompt_index]
            
            # Create TwiML with prompt
            response = VoiceResponse()
            response.say(prompt)
            gather = response.gather(
                input='speech',
                action=f'/speech?call_sid={call_sid}',
                method='POST',
                speechTimeout='auto',
                speechModel='phone_call'
            )
            response.redirect(f'/silence?call_sid={call_sid}')
            
            # Update stats
            update_call_stats(call_sid, "messages_sent")
            
            return Response(content=str(response), media_type="application/xml")
        else:
            # End call after too many silence events
            final_message = "Since I haven't heard from you, I'll be ending our call now. Goodbye!"
            
            # Mark call as ending
            if call_sid in active_calls:
                active_calls[call_sid]["status"] = "ending"
            
            # Create TwiML
            response = VoiceResponse()
            response.say(final_message)
            response.hangup()
            
            # Generate summary
            update_call_stats(call_sid, "end_call")
            generate_call_summary(call_sid)
            
            return Response(content=str(response), media_type="application/xml")
    
    # Default response for unexpected cases
    response = VoiceResponse()
    response.say("Are you still there?")
    response.gather(
        input='speech',
        action=f'/speech?call_sid={call_sid}',
        method='POST',
        speechTimeout='auto',
        speechModel='phone_call'
    )
    return Response(content=str(response), media_type="application/xml")

def process_speech_with_openai(call_sid, speech_text):
    """Process user speech with OpenAI and return response"""
    try:
        # Check for end phrases
        if any(phrase in speech_text.lower() for phrase in ["goodbye", "bye", "end call", "hang up"]):
            # Mark call as ending
            if call_sid in active_calls:
                active_calls[call_sid]["status"] = "ending"
            return "Thank you for calling. Have a great day!"
        
        # Use OpenAI directly (synchronous)
        completion = openai.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4"),
            messages=[
                {"role": "system", "content": "You are a helpful phone assistant. Keep responses brief and natural."},
                {"role": "user", "content": speech_text}
            ]
        )
        
        # Extract the response text
        response_text = completion.choices[0].message.content
        
        return response_text
    except Exception as e:
        print(f"Error processing speech: {e}")
        return "I'm sorry, I encountered an issue. Could you please try again?"

@app.post("/call-status")
async def handle_call_status(request: Request):
    """Handle Twilio call status callbacks"""
    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    status = form_data.get("CallStatus")
    
    print(f"Call {call_sid} status changed to: {status}")
    
    # If call has ended
    if status in ["completed", "busy", "no-answer", "failed"]:
        # Update the active calls tracking
        if call_sid in active_calls:
            active_calls[call_sid]["status"] = "completed"
        
        # Generate summary
        if call_sid in call_stats:
            update_call_stats(call_sid, "end_call")
            summary = generate_call_summary(call_sid)
        
        # Clean up resources
        if call_sid in silence_counters:
            del silence_counters[call_sid]
    
    return {"message": "Status processed"}

async def monitor_silence(call_sid):
    """Monitor for silence (as a backup to the TwiML approach)"""
    # This is now a lightweight backup to the TwiML-based silence detection
    timeout = 120  # seconds
    check_interval = 10  # seconds
    
    while call_sid in active_calls and active_calls[call_sid]["status"] == "active":
        await asyncio.sleep(check_interval)
        
        # Check if call has been inactive for too long
        if call_sid in active_calls:
            last_activity = active_calls[call_sid]["last_activity"]
            inactive_time = (datetime.now() - last_activity).total_seconds()
            
            if inactive_time > timeout:
                print(f"Call {call_sid} has been inactive for {inactive_time} seconds, marking as completed")
                
                # Mark as completed and generate summary
                active_calls[call_sid]["status"] = "completed"
                
                if call_sid in call_stats:
                    update_call_stats(call_sid, "end_call")
                    generate_call_summary(call_sid)
                
                # Clean up
                if call_sid in silence_counters:
                    del silence_counters[call_sid]
                    
                return

def initialize_call_stats(call_sid):
    """Initialize statistics tracking for a call"""
    call_stats[call_sid] = {
        "start_time": datetime.now(),
        "end_time": None,
        "duration": None,
        "silence_events": 0,
        "messages_sent": 0,
        "messages_received": 0
    }

def update_call_stats(call_sid, stat_type, value=1):
    """Update statistics for a call"""
    if call_sid not in call_stats:
        return
        
    if stat_type == "end_call":
        call_stats[call_sid]["end_time"] = datetime.now()
        call_stats[call_sid]["duration"] = (
            call_stats[call_sid]["end_time"] - call_stats[call_sid]["start_time"]
        ).total_seconds()
    else:
        call_stats[call_sid][stat_type] += value

def generate_call_summary(call_sid):
    """Generate a summary of call statistics"""
    if call_sid not in call_stats:
        return "No stats available for this call"
        
    stats = call_stats[call_sid]
    
    # Calculate duration if end_time is set
    if stats["end_time"] is None:
        stats["end_time"] = datetime.now()
        stats["duration"] = (stats["end_time"] - stats["start_time"]).total_seconds()
    
    summary = f"""
    Call Summary for {call_sid}:
    - Duration: {stats['duration']:.2f} seconds
    - Silence events: {stats['silence_events']}
    - Messages sent by bot: {stats['messages_sent']}
    - Messages received from caller: {stats['messages_received']}
    - Start time: {stats['start_time'].strftime('%Y-%m-%d %H:%M:%S')}
    - End time: {stats['end_time'].strftime('%Y-%m-%d %H:%M:%S')}
    """
    
    # Log the summary
    print(summary)
    
    # Save to a file
    with open(f"call_summary_{call_sid}.txt", "w") as f:
        f.write(summary)
    
    # Remove from memory
    if call_sid in call_stats:
        del call_stats[call_sid]
    
    return summary

if __name__ == "__main__":
    import uvicorn
    
    # Get port from environment or use default
    port = int(os.getenv("PORT", "8000"))
    
    print(f"Starting phone chatbot server on port {port}...")
    print("Make sure Twilio webhooks are configured:")
    print(f"  - Voice webhook: YOUR_NGROK_URL/inbound-call")
    print(f"  - Status callback: YOUR_NGROK_URL/call-status")
    
    uvicorn.run(app, host="0.0.0.0", port=port)