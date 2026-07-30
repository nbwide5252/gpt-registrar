"""ChatGPT channel manifest."""

MANIFEST = {
    "name": "chatgpt",
    "label": "ChatGPT Protocol Register",
    "flow": "channels.chatgpt.flow:register",
    "defaults": {
        "mode": "protocol",
        "phone_country": 31,  # South Africa
    }
}
