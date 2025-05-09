# phone_voice_chat_bot

## Steps for installation
0. Clone this repository
1. Get twillio phone number
2. Install ngrok 
3. ngrok config add-authtoken <YourAuthToken>
4. ngrok http 8000
4. go to your twillio phone dashboard set inbound webhook to: https://<ngrok_address>/inbound-call
5. go to your twillio phone dashboard set call status changes webhook to: https://<ngrok_address>/call-status
6. Edit env variables setup values
7. run "python inbound_call.py"
8. Edit test_call.py set your ngrok test params such as mobile numbers and ngrok inbound url
9. run "python test_call.py"
10. happy voice chatting!!
