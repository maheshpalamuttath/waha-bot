import random
from pprint import pprint
from time import sleep

import requests
from flask import Flask, request
import mysql.connector

# Initialize Flask app
app = Flask(__name__)

# MySQL connection configuration
mysql_host = 'localhost'
mysql_user = 'koha_library'
mysql_password = 'koha123'
mysql_database = 'koha_library'

# Dictionary to keep track of conversation states
conversation_states = {}

# Function to connect to MySQL and execute parameterized query
def query_mysql(query, params=None):
    connection = mysql.connector.connect(
        host=mysql_host,
        user=mysql_user,
        password=mysql_password,
        database=mysql_database
    )
    cursor = connection.cursor(dictionary=True)
    if params:
        cursor.execute(query, params)
    else:
        cursor.execute(query)
    result = cursor.fetchall()
    cursor.close()
    connection.close()
    return result

def update_mysql(query, params):
    connection = mysql.connector.connect(
        host=mysql_host,
        user=mysql_user,
        password=mysql_password,
        database=mysql_database
    )
    cursor = connection.cursor()
    cursor.execute(query, params)
    connection.commit()
    cursor.close()
    connection.close()

# WhatsApp API functions
def send_message(chat_id, text):
    response = requests.post(
        "http://localhost:3000/api/sendText",
        json={
            "chatId": chat_id,
            "text": text,
            "session": "default",
        },
    )
    response.raise_for_status()

def reply(chat_id, message_id, text):
    response = requests.post(
        "http://localhost:3000/api/reply",
        json={
            "chatId": chat_id,
            "text": text,
            "reply_to": message_id,
            "session": "default",
        },
    )
    response.raise_for_status()

def send_seen(chat_id, message_id, participant):
    response = requests.post(
        "http://localhost:3000/api/sendSeen",
        json={
            "session": "default",
            "chatId": chat_id,
            "messageId": message_id,
            "participant": participant,
        },
    )
    response.raise_for_status()

def typing(chat_id, seconds):
    response = requests.post(
        "http://localhost:3000/api/startTyping",
        json={
            "session": "default",
            "chatId": chat_id,
        },
    )
    response.raise_for_status()
    sleep(seconds)
    response = requests.post(
        "http://localhost:3000/api/stopTyping",
        json={
            "session": "default",
            "chatId": chat_id,
        },
    )
    response.raise_for_status()

@app.route("/")
def whatsapp_echo():
    return "WhatsApp Bot is ready!"

@app.route("/bot", methods=["POST"])
def whatsapp_webhook():
    data = request.get_json()
    pprint(data)

    if data["event"] != "message":
        return f"Unknown event {data['event']}"

    payload = data["payload"]
    text = payload.get("body")

    if not text:
        print("No text in message")
        print(payload)
        return "OK"

    chat_id = payload["from"]
    message_id = payload['id']
    participant = payload.get('participant')

    # Strip any suffixes to match phone number in database
    phone_number = chat_id.split('@')[0]

    print(f"Received chat_id: {chat_id}, extracted phone number: {phone_number}")  # Debug statement

    send_seen(chat_id=chat_id, message_id=message_id, participant=participant)

    # Check the state of the conversation
    state = conversation_states.get(chat_id, 'initial')

    if state == 'initial':
        # Check if message is "Hi"
        if text.strip().lower() == "hi":
            query = "SELECT CONCAT(title, ' ', surname) AS name FROM borrowers WHERE phone = %s"
            params = (phone_number,)

            try:
                result = query_mysql(query, params)
                print(f"Database query result: {result}")  # Debug statement
                if result:
                    name = result[0]['name']
                    print(f"Fetched name: {name}")  # Debug statement
                    reply_text = f"Hello, {name}, Welcome to Fr. Francis Sales Library."
                else:
                    print(f"No matching name found for phone number: {phone_number}")  # Debug statement
                    reply_text = "Welcome to Fr. Francis Sales Library. Please enter your card number"
                    # Update conversation state
                    conversation_states[chat_id] = 'waiting_for_card_number'
            except Exception as e:
                print(f"Error fetching name from database: {e}")
                reply_text = "Hello! How can I assist you today?"

            typing(chat_id=chat_id, seconds=random.random() * 3)
            reply(chat_id=chat_id, message_id=message_id, text=reply_text)

    elif state == 'waiting_for_card_number':
        card_number = text.strip()
        query = "SELECT borrowernumber, CONCAT(title, ' ', surname) AS name FROM borrowers WHERE cardnumber = %s"
        params = (card_number,)

        try:
            result = query_mysql(query, params)
            print(f"Card number query result: {result}")  # Debug statement
            if result:
                borrowernumber = result[0]['borrowernumber']
                name = result[0]['name']
                print(f"Fetched name: {name} for card number: {card_number}")  # Debug statement
                reply_text = f"Hello, {name}, would you like to update your WhatsApp number in the library for library alerts? Reply with 'yes' or 'no'."
                # Update conversation state and store borrowernumber
                conversation_states[chat_id] = {'state': 'waiting_for_confirmation', 'borrowernumber': borrowernumber}
            else:
                print(f"No matching borrower found for card number: {card_number}")  # Debug statement
                reply_text = "Invalid card number. Please enter a valid card number."
                conversation_states[chat_id] = 'waiting_for_card_number'
        except Exception as e:
            print(f"Error fetching borrower from database: {e}")
            reply_text = "There was an error processing your request. Please try again."

        typing(chat_id=chat_id, seconds=random.random() * 3)
        reply(chat_id=chat_id, message_id=message_id, text=reply_text)

    elif isinstance(state, dict) and state.get('state') == 'waiting_for_confirmation':
        if text.strip().lower() == "yes":
            borrowernumber = state['borrowernumber']
            query = "UPDATE borrowers SET phone = %s WHERE borrowernumber = %s"
            params = (phone_number, borrowernumber)

            try:
                update_mysql(query, params)
                reply_text = "Your WhatsApp number has been updated in the library."
                print(f"Updated WhatsApp number for borrowernumber: {borrowernumber}")  # Debug statement
            except Exception as e:
                print(f"Error updating WhatsApp number: {e}")
                reply_text = "There was an error updating your WhatsApp number. Please try again."
        elif text.strip().lower() == "no":
            reply_text = "You are opted not to subscribe."
        else:
            reply_text = "Invalid response. Please reply with 'yes' or 'no'."
            typing(chat_id=chat_id, seconds=random.random() * 3)
            reply(chat_id=chat_id, message_id=message_id, text=reply_text)
            return "OK"

        # Reset conversation state
        conversation_states.pop(chat_id, None)
        typing(chat_id=chat_id, seconds=random.random() * 3)
        reply(chat_id=chat_id, message_id=message_id, text=reply_text)

    return "OK"

if __name__ == "__main__":
    app.run(debug=True)
