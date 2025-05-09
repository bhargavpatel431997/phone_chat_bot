# phone_voice_chat_bot

## Steps for installation
0. Clone this repository
1. Get twillio phone number
![Screenshot 2025-05-09 183538](https://github.com/user-attachments/assets/7f5c5942-3bc6-4099-bce4-c4a3b616262f)
3. Open Terminal
4. command: `ngrok config add-authtoken |YourAuthToken|`
5. command:  `ngrok http 8000`
6. go to your twillio phone dashboard (click on the phone number to edit inbound webhook) set inbound webhook to: https://<ngrok_address>/inbound-call
7. go to your twillio phone dashboard set call status changes webhook to: https://<ngrok_address>/call-status
8. Edit env variables setup values
9. Open new Terminal
10. command: `python inbound_call.py`
11. Edit `test_call.py` set your ngrok test params such as mobile numbers and ngrok inbound url
12. command: `python test_call.py`
13. happy voice chatting!!
