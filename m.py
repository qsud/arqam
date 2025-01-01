import os
import telebot
import json
import requests
import logging
import time
from pymongo import MongoClient
from datetime import datetime, timedelta
import certifi
import random
from subprocess import Popen
from threading import Thread
import asyncio
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import pytz

loop = asyncio.get_event_loop()

TOKEN = '7938475169:AAEd9HR1rn3MIIrgpiw4apxk_YbHRJTq_a4'
USER_DATA_FILE = "user_data.json"
FORWARD_CHANNEL_ID = -1002166347748
CHANNEL_ID = -1002166347748
error_channel_id = -1002166347748

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

bot = telebot.TeleBot(TOKEN)
REQUEST_INTERVAL = 1

LOG_FILE = "log.txt"  # File to store command logs
ADMIN_ID = "7154971116"  # Example admin user ID

# List of blocked ports
blocked_ports = [8700, 20000, 443, 17500, 9031, 20002, 20001]

# Track ongoing attacks
ongoing_attacks = {}
# Time zone setup
tz = pytz.timezone('Asia/Kolkata')

if not os.path.exists(USER_DATA_FILE):
    with open(USER_DATA_FILE, "w") as file:
        json.dump([], file)

def load_users():
    """Load users from the JSON file."""
    with open(USER_DATA_FILE, "r") as file:
        return json.load(file)

def save_users(users):
    """Save users to the JSON file."""
    with open(USER_DATA_FILE, "w") as file:
        json.dump(users, file, indent=4)

def get_user(user_id):
    """Retrieve a user by ID."""
    users = load_users()
    return next((user for user in users if user["user_id"] == user_id), None)
    
    
def extend_and_clean_expired_users():
    """Clean up users whose access has expired."""
    now = datetime.now(tz)
    logging.info(f"Current Date and Time: {now}")

    users = load_users()
    updated_users = []

    for user in users:
        user_id = user.get("user_id")
        username = user.get("username", "Unknown User")
        valid_until_str = user.get("valid_until", "")
        time_add_str = user.get("time_add")

        if valid_until_str:
            try:
                valid_until_date = datetime.strptime(valid_until_str, "%Y-%m-%d").date()
                time_add = datetime.strptime(time_add_str, "%I:%M:%S %p %Y-%m-%d").time() if time_add_str else datetime.min.time()
                valid_until_datetime = datetime.combine(valid_until_date, time_add)
                valid_until_datetime = tz.localize(valid_until_datetime)

                if now > valid_until_datetime:
                    try:
                        bot.send_message(
                            user_id,
                            f"*⚠️ Access Expired! ⚠️*\n"
                            f"Your access expired on {valid_until_datetime.strftime('%Y-%m-%d %I:%M:%S %p')}.\n"
                            f"🕒 Approval Time: {time_add_str if time_add_str else 'N/A'}\n"
                            f"📅 Valid Until: {valid_until_datetime.strftime('%Y-%m-%d %I:%M:%S %p')}\n"
                            f"If you believe this is a mistake or wish to renew your access, please contact support. 💬",
                            reply_markup=create_inline_keyboard(), parse_mode='Markdown'
                        )
                    except Exception as e:
                        logging.error(f"Failed to send message for user {user_id}: {e}")
                else:
                    updated_users.append(user)
            except ValueError as e:
                logging.error(f"Failed to parse date for user {user_id}: {e}")

    save_users(updated_users)
    logging.info("Approval times extension and cleanup completed. ✅")

def log_command(user_id, target, port, time):
    user_info = bot.get_chat(user_id)
    username = "@" + user_info.username if user_info.username else f"UserID: {user_id}"
    
    with open(LOG_FILE, "a") as file:
        file.write(f"UserID: {user_id}\n")  # Ensure user ID is stored in this format
        file.write(f"Username: {username}\n")
        file.write(f"Target: {target}\n")
        file.write(f"Port: {port}\n")
        file.write(f"Time: {time} seconds\n\n")

# Clear attack logs
def clear_logs():
    try:
        with open(LOG_FILE, "r+") as file:
            if file.read() == "":
                response = "Logs are already cleared. No data found."
            else:
                file.truncate(0)
                response = "Logs cleared successfully."
    except FileNotFoundError:
        response = "No logs found to clear."
    return response

# Show logs to the admin
@bot.message_handler(commands=['logs'])
def show_recent_logs(message):
    user_id = str(message.chat.id)
    if user_id == ADMIN_ID:
        if os.path.exists(LOG_FILE) and os.stat(LOG_FILE).st_size > 0:
            try:
                with open(LOG_FILE, "rb") as file:
                    bot.send_document(message.chat.id, file)
            except FileNotFoundError:
                bot.reply_to(message, "No logs found.")
        else:
            bot.reply_to(message, "No logs found.")
    else:
        bot.reply_to(message, "🚫 *Access Denied!*\n"
            "❌ *You don't have the required permissions to use this command.*\n"
            "💬 *Please contact the bot owner if you believe this is a mistake.*")

# Allow the admin to clear logs
@bot.message_handler(commands=['clearlogs'])
def clear_logs_command(message):
    user_id = str(message.chat.id)
    if user_id == ADMIN_ID:
        response = clear_logs()
    else:
        response = (
            "🚫 *Access Denied!*\n"
            "❌ *You don't have the required permissions to use this command.*\n"
            "💬 *Please contact the bot owner if you believe this is a mistake.*"
        )
    bot.reply_to(message, response)


# Allow users to see their own logs
@bot.message_handler(commands=['mylogs'])
def show_command_logs(message):
    user_id = str(message.from_user.id)  # Convert user ID to string for consistency
    try:
        with open(LOG_FILE, "r") as file:
            logs = file.readlines()  # Read all lines from the log file
            
            # Search for logs specific to this user
            user_logs = []
            for i in range(len(logs)):
                if f"UserID: {user_id}" in logs[i]:  # Ensure the format matches
                    # Capture subsequent log lines that belong to this user's log
                    user_logs.append(logs[i])
                    # Continue appending lines that belong to this entry (target, port, time)
                    if i + 1 < len(logs):
                        user_logs.append(logs[i + 1])  # Target
                    if i + 2 < len(logs):
                        user_logs.append(logs[i + 2])  # Port
                    if i + 3 < len(logs):
                        user_logs.append(logs[i + 3])  # Time
                    user_logs.append("\n")  # Add separation between logs
            
            # If user logs are found, return them; otherwise, show no logs found
            if user_logs:
                response = "Your Command Logs:\n" + "".join(user_logs)
            else:
                response = "No Command Logs Found For You."
    except FileNotFoundError:
        response = "No command logs found."
    
    bot.reply_to(message, response)
        
async def start_asyncio_thread():
    asyncio.set_event_loop(loop)
    await start_asyncio_loop()

async def start_asyncio_loop():
    while True:
        now = datetime.now()
        for message_id, (chat_id, target_ip, target_port, duration, end_time, user_id) in list(ongoing_attacks.items()):
            remaining_time = int((end_time - now).total_seconds())
            if remaining_time > 0:
                try:
                    bot.edit_message_reply_markup(
                        chat_id=chat_id,
                        message_id=message_id,
                        reply_markup=create_time_left_button(remaining_time)
                    )
                except Exception as e:
                    logging.error(f"Error updating message: {e}")
            else:
                try:
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=f"*✅ Attack Finished! ✅\n\n📡 Host: {target_ip}\n👉 Port: {target_port}*",
                        parse_mode='Markdown',
                        reply_markup=create_inline_keyboard()
                    )
                    forward_attack_finished_message(chat_id, user_id, target_ip, target_port)
                except Exception as e:
                    logging.error(f"Error updating message: {e}")
                ongoing_attacks.pop(message_id, None)
        await asyncio.sleep(1)

async def run_attack_command_async(message_id, chat_id, target_ip, target_port, duration):
    process = await asyncio.create_subprocess_shell(f"./bgmi {target_ip} {target_port} {duration} 100")
    await process.communicate()

    # After the attack finishes, update the message
    bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=f"*✅ Attack Finished! ✅*\n"
             f"*The attack on {target_ip}:{target_port} has finished successfully.*\n"
             f"*Thank you for using our service!*",
        parse_mode='Markdown',
        reply_markup=create_inline_keyboard()
    )
    
    ongoing_attacks.pop(message_id, None)

def is_user_admin(user_id, chat_id):
    try:
        return bot.get_chat_member(chat_id, user_id).status in ['administrator', 'creator']
    except:
        return False

def create_inline_keyboard():
    keyboard = InlineKeyboardMarkup()
    button = InlineKeyboardButton(text="OWNER", url="https://t.me/arqamnabi")
    keyboard.add(button)
    return keyboard

def create_time_left_button(remaining_time):
    keyboard = InlineKeyboardMarkup()
    button = InlineKeyboardButton(text="Time remaining", callback_data=f"time_remaining_{remaining_time}")
    keyboard.add(button)
    return keyboard

@bot.message_handler(commands=['users'])
def list_approved_users(message):
    if message.from_user.id != int(ADMIN_ID):
        bot.reply_to(message, 
            "🚫 *Access Denied!*\n"
            "❌ *You don't have the required permissions to use this command.*\n"
            "💬 *Please contact the bot owner if you believe this is a mistake.*")
        return

    users = load_users()
    approved_users = [u for u in users if u["plan"] > 0]

    if not approved_users:
        bot.send_message(message.chat.id, "No approved users found.")
        return

    user_list = "Approved Users:\n"
    for user in approved_users:
        user_list += f"User ID: {user['user_id']}, Plan: {user['plan']}, Valid Until: {user.get('valid_until', 'N/A')}\n"

    bot.send_message(message.chat.id, user_list)

@bot.message_handler(commands=['add', 'remove'])
def add_or_remove_user(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    is_admin = user_id == int(ADMIN_ID)
    cmd_parts = message.text.split()

    if not is_admin:
        bot.send_message(
            chat_id,
            "🚫 *Access Denied!*\n"
            "❌ *You don't have the required permissions to use this command.*\n"
            "💬 *Please contact the bot owner if you believe this is a mistake.*",
            reply_markup=create_inline_keyboard(), parse_mode='Markdown')
        return

    if len(cmd_parts) < 2:
        bot.send_message(
            chat_id,
            "⚠️ *Invalid Command Format!*\n"
            "ℹ️ *To add a user:*\n"
            "`/add <user_id> <plan> <days>`\n"
            "ℹ️ *To remove a user:*\n"
            "`/remove <user_id>`\n"
            "🔄 *Example:* `/add 12345678 1 30`\n"
            "✅ *This command adds the user with ID 12345678 for Plan 1, valid for 30 days.*",
            reply_markup=create_inline_keyboard(), parse_mode='Markdown')
        return

    action = cmd_parts[0]

    try:
        target_user_id = int(cmd_parts[1])
    except ValueError:
        bot.send_message(chat_id,
                         "⚠️ *Error: [user_id] must be an integer!*\n"
                         "🔢 *Please enter a valid user ID and try again.*",
                         reply_markup=create_inline_keyboard(), parse_mode='Markdown')
        return

    target_username = message.reply_to_message.from_user.username if message.reply_to_message else None

    if action == '/add':
        try:
            plan = int(cmd_parts[2]) if len(cmd_parts) >= 3 else 0
            days = int(cmd_parts[3]) if len(cmd_parts) >= 4 else 0
        except ValueError:
            bot.send_message(chat_id,
                             "⚠️ *Error: <plan> and <days> must be integers!*\n"
                             "🔢 *Ensure that the plan and days are numerical values and try again.*",
                             reply_markup=create_inline_keyboard(), parse_mode='Markdown')
            return

        # Adding user to JSON file
        users = load_users()
        now = datetime.now(tz).date()
        valid_until = (now + timedelta(days=days)).isoformat() if days > 0 else now.isoformat()
        time_add = datetime.now(tz).strftime("%I:%M:%S %p %Y-%m-%d")

        # Check if user already exists
        user = next((u for u in users if u["user_id"] == target_user_id), None)
        if user:
            user.update({
                "username": target_username,
                "plan": plan,
                "days": days,
                "valid_until": valid_until,
                "add_by": user_id,
                "time_add": time_add,
                "access_count": 0
            })
        else:
            users.append({
                "user_id": target_user_id,
                "username": target_username,
                "plan": plan,
                "days": days,
                "valid_until": valid_until,
                "add_by": user_id,
                "time_add": time_add,
                "access_count": 0
            })

        save_users(users)

        bot.send_message(
            chat_id,
            f"✅ *Approval Successful!*\n"
            f"👤 *User ID:* `{target_user_id}`\n"
            f"📋 *Plan:* `{plan}`\n"
            f"⏳ *Duration:* `{days} days`\n"
            f"🎉 *The user has been added and their account is now active.*\n"
            f"🚀 *They will be able to use the bot's commands according to their plan.*",
            reply_markup=create_inline_keyboard(), parse_mode='Markdown')

    elif action == '/remove':
        # Removing user from JSON file
        users = load_users()
        users = [u for u in users if u["user_id"] != target_user_id]
        save_users(users)

        bot.send_message(
            chat_id,
            f"❌ *Disapproval Successful!*\n"
            f"👤 *User ID:* `{target_user_id}`\n"
            f"🗑️ *The user's account has been removed and all related data has been deleted.*\n"
            f"🚫 *They will no longer be able to access the bot.*",
            reply_markup=create_inline_keyboard(), parse_mode='Markdown')

        bot.send_message(
            target_user_id,
            "🚫 *Your account has been removed and deleted.*\n"
            "💬 *If you believe this is a mistake, please contact the admin.*",
            reply_markup=create_inline_keyboard(), parse_mode='Markdown')

@bot.message_handler(commands=['broadcast'])
def broadcast_message(message):
    if message.from_user.id != int(ADMIN_ID):
        bot.reply_to(message, 
            "🚫 *Access Denied!*\n"
            "❌ *You don't have the required permissions to use this command.*\n"
            "💬 *Please contact the bot owner if you believe this is a mistake.*")
        return

    msg = bot.reply_to(message, "Please send the message you want to broadcast to all users:")
    bot.register_next_step_handler(msg, send_broadcast)

def send_broadcast(message):
    broadcast_text = message.text
    if not broadcast_text:
        bot.reply_to(message, "Broadcast message cannot be empty.")
        return

    users = load_users()
    for user in users:
        try:
            bot.send_message(user["user_id"], broadcast_text)
        except Exception as e:
            logging.error(f"Failed to send message to {user['user_id']}: {e}")

    bot.reply_to(message, "Message has been broadcasted to all users successfully.")


@bot.message_handler(commands=['attack'])
def handle_attack_command(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    try:
        users = load_users()
        user_data = next((u for u in users if u["user_id"] == user_id), None)

        if not user_data or user_data['plan'] == 0:
            bot.send_message(chat_id, 
                "🚫 *Access Denied!*\n"
                "❌ *You don't have the required permissions to use this command.*\n"
                "💬 *Please contact the bot owner if you believe this is a mistake.*", 
                parse_mode='Markdown', reply_markup=create_inline_keyboard())
            return

        bot.send_message(chat_id, 
            "*Enter the target IP, port, and duration (in seconds) separated by spaces. \nE.g. - 167.67.25 6296 60*", 
            parse_mode='Markdown', reply_markup=create_inline_keyboard())
        bot.register_next_step_handler(message, process_attack_command)
    except Exception as e:
        logging.error(f"Error in attack command: {e}")

def process_attack_command(message):
    try:
        args = message.text.split()
        if len(args) != 3:
            bot.send_message(message.chat.id, 
                "*Error in command\nPlease try again with the correct format.*", 
                parse_mode='Markdown', reply_markup=create_inline_keyboard())
            return

        target_ip, target_port, duration = args[0], int(args[1]), int(args[2])

        if target_port in blocked_ports:
            bot.send_message(message.chat.id, 
                f"*Port {target_port} is blocked. \nPlease use a different port.*", 
                parse_mode='Markdown', reply_markup=create_inline_keyboard())
            return

        # Simulate attack for now (Replace with actual attack logic)
        bot.send_message(
            message.chat.id,
            f"*❌ Attack started ❌\n\n📡 Host : {target_ip}\n👉 Port : {target_port}\n⏰ Duration : {duration} seconds*",
            parse_mode='Markdown',
            reply_markup=create_inline_keyboard()
        )
    except Exception as e:
        logging.error(f"Error in processing attack command: {e}")


def start_asyncio_thread():
    asyncio.set_event_loop(loop)
    loop.run_until_complete(start_asyncio_loop())

@bot.message_handler(commands=['info'])
def info_command(message):
    user_id = message.from_user.id
    users = load_users()
    user_data = next((u for u in users if u["user_id"] == user_id), None)

    if user_data:
        plan = user_data.get('plan', 'N/A')
        valid_until = user_data.get('valid_until', 'N/A')
        response = (f"👤 *Your Account Information:*\n"
                    f"📋 *Plan:* `{plan}`\n"
                    f"📅 *Valid Until:* `{valid_until}`\n"
                    f"✅ *You are authorized to use this bot.*")
    else:
        response = "❌ *No account information found. Please contact the admin.*"

    bot.send_message(message.chat.id, response, parse_mode='Markdown')


@bot.message_handler(commands=['admin'])
def welcome_plan(message):
    user_name = message.from_user.first_name
    response = f'''{user_name}, Admin Commands Are Here!!:

/add <userId> : Add a User.
/remove <userid> : Remove a User.
/users : Authorized Users List.
/logs : All Users Logs.
/broadcast : Broadcast a Message.
/clearlogs : Clear The Logs File.
    '''
    
    # Inline Button for Owner (already existing in the script)
    keyboard = InlineKeyboardMarkup()
    button = InlineKeyboardButton(text="Owner", url="https://t.me/arqamnabi")  # Owner button URL
    keyboard.add(button)
    
    bot.reply_to(message, response, reply_markup=keyboard)

@bot.message_handler(commands=['help'])
def help_command(message):
    bot.send_message(message.chat.id, "*🌟 Welcome to the Ultimate Command Center!*\n\n"
                 "*Here’s what you can do:* \n"
                 "1. *`/attack` - ⚔️ Launch a powerful attack and show your skills!*\n"
                 "2. *`/info` - 👤 Check your account info and stay updated.*\n"
                 "3. *`/owner` - 📞 Get in touch with the mastermind behind this bot!*\n"
                 "4. *`/canary` - 🦅 Grab the latest Canary version for cutting-edge features.*\n"
                 "5. *`/mylogs` - 📜 shows logs user attacks with timestamps and types, enabling viewing, deletion, and summary reporting.*\n\n"              
                   "6. *`/id` - 📜 Get your telegram id. Easy for getting approval.*\n\n"
                 "*💡 Got questions? Don't hesitate to ask! Your satisfaction is our priority!*", parse_mode='Markdown', reply_markup=create_inline_keyboard())

@bot.message_handler(commands=['owner'])
def owner_command(message):
    bot.send_message(message.chat.id, "*Owner - @arqamnabi*", parse_mode='Markdown', reply_markup=create_inline_keyboard())

@bot.message_handler(commands=['canary'])
def canary_command(message):
    response = ("*📥 Download the HttpCanary APK Now! 📥*\n\n"
                "*🔍 Track IP addresses with ease and stay ahead of the game! 🔍*\n"
                "*💡 Utilize this powerful tool wisely to gain insights and manage your network effectively. 💡*\n\n"
                "*Choose your platform:*")

    markup = InlineKeyboardMarkup()  # Ensure you use 'InlineKeyboardMarkup' directly from 'telebot.types'
    button1 = InlineKeyboardButton(
        text="📱 𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱 𝗙𝗼𝗿 𝗔𝗻𝗱𝗿𝗼𝗶𝗱 📱",
        url="https://t.me/DANGERXVIP_FEEDBACKS/1244")
    button2 = InlineKeyboardButton(
        text="🍎 𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱 𝗳𝗼𝗿 𝗶𝗢𝗦 🍎",
        url="https://apps.apple.com/in/app/surge-5/id1442620678")

    markup.add(button1)
    markup.add(button2)

    try:
        bot.send_message(message.chat.id,
                         response,
                         parse_mode='Markdown',
                         reply_markup=markup)
    except Exception as e:
        logging.error(f"Error while processing /canary command: {e}")

@bot.message_handler(commands=['id'])
def id_command(message):
    user_id = message.from_user.id
    bot.send_message(message.chat.id, f"Your Telegram ID: `{user_id}`", parse_mode='Markdown')

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(message.chat.id, "*WELCOME! \n\nTo launch an attack, use the /attack command followed by the target host and port.\n\nFor example: After /attack enter IP port duration.\n\nMake sure you have the target in sight before unleashing the chaos!\n\nIf you're new here, check out the /help command to see what else I can do for you.\n\nRemember, with great power comes great responsibility. Use it wisely... or not! 😈*", parse_mode='Markdown', reply_markup=create_inline_keyboard())

@bot.callback_query_handler(func=lambda call: call.data.startswith('time_remaining_'))
def handle_time_remaining_callback(call):
    remaining_time = int(call.data.split('_')[-1])
    bot.answer_callback_query(call.id, f"Time remaining: {remaining_time} seconds")
if __name__ == "__main__":
    asyncio_thread = Thread(target=start_asyncio_thread, daemon=True)
    asyncio_thread.start()
    logging.info("Starting Codespace activity keeper and Telegram bot...")
    while True:
        try:
            bot.polling(none_stop=True)
        except Exception as e:
            logging.error(f"An error occurred while polling: {e}")
        logging.info(f"Waiting for {REQUEST_INTERVAL} seconds before the next request...")
        time.sleep(REQUEST_INTERVAL)
