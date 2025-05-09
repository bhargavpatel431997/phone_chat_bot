from twilio.rest import Client
import os
from dotenv import load_dotenv

load_dotenv()

# Your Account SID and Auth Token from twilio.com/console
account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
print(account_sid)
print(auth_token)
client = Client(username=account_sid, password=auth_token)

# Make a call
call = client.calls.create(
    to='+1<your_phone_number>',  # Your phone number to receive the test call
    from_='+1<twilio_phone_number>',  # Your Twilio phone number
    url='https://<ngrok_url>/inbound-call'# ngrok url
)

print(f"Call initiated with SID: {call.sid}")