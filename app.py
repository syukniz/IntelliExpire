from flask import Flask, render_template, request, session, redirect, url_for
from flask_bcrypt import Bcrypt
from dateutil import parser
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import mysql.connector
import os
import base64
import telegram
import asyncio
import requests
import json
import time

app = Flask(__name__)
app.secret_key = 'SyukNiz27_'
bcrypt = Bcrypt(app)

# Database setup (replace with your database configuration)
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="database"
)
cursor = db.cursor()
# Replace with your bot token
bot_token = '5629926169:AAGXcbJ9ZH64qQsIVjXgNmwX4SbGgZ8zkmI'
# Replace with your URL for /register
register_url = 'https://t.me/IntelliExpire_bot?start=register'
# Create the bot instance
bot = telegram.Bot(token=bot_token)

URL = 'https://inf-193eadde-76ba-4440-ace8-1d7380c00296-no4xvrhsfq-uc.a.run.app/detect'
FALLBACK_URL = ''
IMAGE_PATH = 'IntelliExpire\\image.png'

# Get chat ID from the Telegram bot
async def get_chat_id():
    # Use the Telegram bot object to get the chat ID
    updates = await bot.get_updates()
    if updates:  # Check if there are updates
        chat_id = updates[0].message.chat_id  # Update chat_id
        return chat_id
    else:
        return None

# Send a message via Telegram
async def send_telegram_message(chat_id, message_text):
    if chat_id:  # Check if chat_id is available
        await bot.send_message(chat_id=chat_id, text=message_text)
    else:
        print("Chat ID not available yet.")

# REST API that linked the image to THEOS AI
def detect(image_path=IMAGE_PATH, url=URL, conf_thres=0.57, iou_thres=0.45, ocr_model=any, ocr_classes=any, ocr_language=any, retries=10, delay=0):
    response = requests.post(url, data={'conf_thres':conf_thres, 'iou_thres':iou_thres, **({'ocr_model':'large', 'ocr_classes':'expiry_date', 'ocr_language':'eng'} if ocr_model is not None else {})}, files={'image':open(image_path, 'rb')})
    if response.status_code in [200, 500]:
        data = response.json()
        if 'error' in data:
            print('[!]', data['message'])
        else:
            return data
    elif response.status_code == 403:
        print('[!] you reached your monthly requests limit. Upgrade your plan to unlock unlimited requests.')
    elif retries > 0:
        if delay > 0:
            time.sleep(delay)
        return detect(image_path, url=FALLBACK_URL if FALLBACK_URL else URL, retries=retries-1, delay=2)
    return []

# Remove unwanted character from expiry date
def remove_unwanted_characters(expiry_date):
    # Remove unwanted characters (-, /, ., space) from the string
    cleaned_date = ''.join(char for char in expiry_date if char.isdigit())
    return cleaned_date

# Algorithm to standardize date
def standardize_expiry_date(expiry_date):
    cleaned_date = remove_unwanted_characters(expiry_date)

    try:
        # Create a datetime object with the extracted components
        parsed_date = datetime.strptime(cleaned_date, "%d%m%y")
    except ValueError:
        try:
            # Create a datetime object with the extracted components
            parsed_date = datetime.strptime(cleaned_date, "%d/%m/%Y")
        except ValueError:
            try:
                # If parsing still fails, try using dateutil.parser
                parsed_date = parser.parse(expiry_date)
            except ValueError:
                return "Error: Date could not be standardized"

    # If the time component is not set, set it to the end of the day
    if parsed_date.time() == datetime.min.time():
        parsed_date = parsed_date.replace(hour=23, minute=59, second=59)

    # Return the parsed date as datetime object
    return parsed_date

# Redirect to IntelliExpire Homepage
@app.route('/', methods=['GET', 'POST'])
def index():
    return render_template('index.html')

# Signup Route
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        fullname = request.form['fullname']
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        # Hash the password before storing it using bcrypt
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        # Check if the username or email already exists
        check_query = "SELECT * FROM users WHERE username = %s OR email = %s"
        cursor.execute(check_query, (username, email))
        existing_user = cursor.fetchone()

        if existing_user:
            return """
                <script>
                    alert('Error: Username or email already taken.');
                    window.location.href = '/signup';
                </script>
            """
        else:
            # Insert the new user
            insert_query = "INSERT INTO users (fullname, username, email, password) VALUES (%s, %s, %s, %s)"
            cursor.execute(insert_query, (fullname, username, email, hashed_password))
            db.commit()

            # Get chat ID from the Telegram bot
            chat_id = asyncio.run(get_chat_id())

            # Update chat_id into the database
            update_query = "UPDATE users SET chat_id = %s WHERE username = %s"
            cursor.execute(update_query, (chat_id, username))
            db.commit()

            # Send a welcome message to the user
            welcome_message = f"🌟 Welcome to IntelliExpire! 🌟\n\nDear {fullname},\n\nThank you for choosing IntelliExpire. You've successfully completed the registration process, and now you're part of our growing community.\n\nTo continue your journey, please go to the link below:\nhttp://127.0.0.1:5000"
            asyncio.run(send_telegram_message(chat_id, welcome_message))

            # Redirect to the Telegram bot for registration
            return redirect(register_url + f'&chat_id={chat_id}')

    return render_template('signup.html')

# Login Route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Retrieve user information including user_id
        query = "SELECT user_id, password FROM users WHERE username = %s"
        cursor.execute(query, (username,))
        result = cursor.fetchone()

        if result and bcrypt.check_password_hash(result[1], password):
            # Store user_id in the session
            session['user_id'] = result[0]
            return redirect(url_for('product_info'))
        else:
            return """
                <script>
                    alert('Invalid username or password.');
                    window.location.href = '/login';
                </script>
            """
        
    return render_template('login.html')

# Product Information Route
@app.route('/product_info', methods=['GET', 'POST'])
def product_info():
    # Check if user is logged in
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        user_id = session['user_id']  # Retrieve user_id from the session
        product_type = request.form['product_type']
        product_name = request.form['product_name']
        batch_number = request.form['batch_number']

        if not all([product_type, product_name, batch_number]):
            return """
                <script>
                    alert('Please fill out all the form fields before submitting.');
                    window.location.href = '/product_info';
                </script>
            """
        # Handling capture functionality
        if 'image_data' in request.form:
            image_data = request.form['image_data'].split(',')[1]
            image_binary = base64.b64decode(image_data)

            # Create folder if not exist
            folder_name = 'IntelliExpire'
            if not os.path.exists(folder_name):
                os.makedirs(folder_name)

            image_path = os.path.join(folder_name, 'image.png')
            with open(image_path, 'wb') as f:
                f.write(image_binary)
        
            # Start the expiry date label using REST API from THEOS AI
            detections = detect(image_path)

            # Extract the 'text' for expiry_date part from each detection
            for detection in detections:
                expiry_date = detection.get('text')

                # Check if the expiry date exist
                if expiry_date:
                    print(expiry_date)
                    standard_date = standardize_expiry_date(expiry_date)
                    print(standard_date)
                    
                    # Check if the standard date exist
                    if standard_date:

                        # Check if a record with the same product_type, product_name, batch_number, and user_id already exists
                        check_query = "SELECT * FROM products WHERE product_type = %s AND product_name = %s AND batch_number = %s AND user_id = %s"
                        cursor.execute(check_query, (product_type, product_name, batch_number, user_id))
                        existing_record = cursor.fetchone()

                        # Check for duplicate product information
                        if existing_record:
                            return """
                                <script>
                                    alert('Duplicate entry. Product information already exists.');
                                    window.location.href = '/product_info';
                                </script>
                            """
                        else:
                            # Insert product information into the database with user_id
                            insert_query = "INSERT INTO products (user_id, product_type, product_name, batch_number, expired_date) VALUES (%s, %s, %s, %s,%s)"
                            cursor.execute(insert_query, (user_id, product_type, product_name, batch_number, standard_date))
                            db.commit()
                            
                            return """
                                <script>
                                    alert('Product information has been saved successfully!');
                                    window.location.href = '/product_info';
                                </script>
                            """
                    else:
                        return """
                            <script>
                                alert('Failed to save the product information!');
                                window.location.href = '/product_info';
                            </script>
                        """
                else:
                    print('No expiry date found in the detection.')
                    return """
                        <script>
                            alert('Failed to detect the expiry date! Please try again');
                            window.location.href = '/product_info';
                        </script>
                    """

    return render_template('product_info.html')

# Product Overview Route
@app.route('/product_overview', methods=['GET', 'POST'])
def product_overview():
    # Check if user is logged in
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    
    # Fetch product information from the database for the logged-in user
    select_query = "SELECT product_id, product_type, product_name, batch_number, entered_date, expired_date FROM products WHERE user_id = %s"
    cursor.execute(select_query, (user_id,))
    product_records = cursor.fetchall()

    # Calculate duration left for each product
    now = datetime.now()
    products_with_duration = []

    for product in product_records:
        expired_date = product[5]  # Assuming 'expired_date' is stored as datetime in the database
        duration_left = (expired_date - now).days

        # Convert the tuple to a list and add 'duration_left'
        product_list = list(product)
        product_list.append(duration_left)
        products_with_duration.append(product_list)
    
    # Handle product deletion
    if request.method == 'POST':
        product_id_to_delete = request.form.get('delete_product')
        if product_id_to_delete:
            # Perform the deletion operation (e.g., execute a DELETE query)
            delete_query = "DELETE FROM products WHERE product_id = %s AND user_id = %s"
            cursor.execute(delete_query, (product_id_to_delete, user_id))
            # Commit the changes to the database
            db.commit()

            # Redirect to the product overview page to refresh the table
            return redirect(url_for('product_overview'))

    # Render the product information in an HTML table
    return render_template('product_overview.html', products=products_with_duration)

if __name__ == '__main__':
    app.run(debug=True)