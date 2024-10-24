import os
import requests
from bs4 import BeautifulSoup
import mysql.connector
import time
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
from dotenv import load_dotenv
import google.generativeai as genai
import threading

load_dotenv()

MYSQL_HOST = os.getenv('MYSQL_HOST')
MYSQL_USER = os.getenv('MYSQL_USER')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
MYSQL_DB = os.getenv('MYSQL_DB')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.getenv('API_KEY')

db = mysql.connector.connect(
    host=MYSQL_HOST,
    user=MYSQL_USER,
    password=MYSQL_PASSWORD,
    database=MYSQL_DB
)
cursor = db.cursor()

genai.configure(api_key=GEMINI_API_KEY)

bot = telebot.TeleBot(TELEGRAM_TOKEN)

categories = []
links = []
descriptions = []
topics_list = []
topics_links = []
topics_content = []
associated_categories = []

# MySQL table creation if they don't exist
def create_tables():
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INT AUTO_INCREMENT PRIMARY KEY,
            category_name VARCHAR(255) UNIQUE,
            link TEXT,
            description TEXT
        );
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS topics (
            id INT AUTO_INCREMENT PRIMARY KEY,
            topic_name TEXT,
            topic_link TEXT,
            topic_content TEXT,
            associated_category TEXT,
            summary TEXT
        );
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS last_fetched (
            id INT AUTO_INCREMENT PRIMARY KEY,
            category_name VARCHAR(255) UNIQUE,
            last_topic VARCHAR(255),
            last_fetched_time DATETIME
        );
    ''')
    db.commit()

def extract_categories(soup):
    rows = soup.select('tbody > tr')
    for row in rows:
        category_div = row.find('td', class_='category').find('div', itemprop='itemListElement')
        if category_div:
            heading_tag = category_div.find('h3').find('span', itemprop='name')
            if heading_tag:
                category_text = heading_tag.text.strip()
                categories.append(category_text)

                link_tag = category_div.find('meta', itemprop='url')
                if link_tag:
                    category_link = link_tag['content']
                    links.append(url + category_link)
                else:
                    links.append('No link')

                description_tag = category_div.find('div', itemprop='description')
                description_text = description_tag.text.strip() if description_tag else 'No description'
                descriptions.append(description_text)

def store_categories_in_db():
    for category, link, description in zip(categories, links, descriptions):
        cursor.execute("""
            INSERT INTO categories (category_name, link, description) 
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE link = %s, description = %s
        """, (category, link, description, link, description))
    db.commit()

def extract_topics():
    topics_list.clear()
    topics_links.clear()
    topics_content.clear()
    associated_categories.clear()

    for category_text, full_category_link in zip(categories, links):
        sub_response = requests.get(full_category_link)
        sub_soup = BeautifulSoup(sub_response.content, 'html.parser')
        topics = sub_soup.select('td.main-link a.title')[:2]  # Limit to 2 topics for testing

        if topics:
            for topic in topics:
                topic_name = topic.text.strip()
                topic_link = topic['href']
                extract_content(topic_link)
                topics_list.append(topic_name)
                topics_links.append(topic_link)
                associated_categories.append(category_text)

            first_topic_for_category = topics[0].text.strip()
            store_last_fetched_topic(category_text, first_topic_for_category)

    store_topics_in_db()

def extract_content(topic_link):
    response = requests.get(topic_link)
    soup = BeautifulSoup(response.content, 'html.parser')
    desc = soup.find('div', class_='topic-body')
    if desc:
        cleaned_content = " ".join(desc.get_text(separator=' ', strip=True).split())
        topics_content.append(cleaned_content)
        summary = summarize_content(cleaned_content)
    else:
        cleaned_content = 'No topic body available'
        summary = 'No summary available'
        topics_content.append(cleaned_content)

    return summary

def summarize_content(text):
    try:
        model = genai.GenerativeModel(model_name="gemini-1.5-flash")
        prompt = "Summarize the following text in 50 words:"
        response = model.generate_content([prompt, text])
        time.sleep(5)
        return response.text.strip()
    except Exception as e:
        print(f"Error in Gemini API call: {e}")
        return "Summary not available."

def store_topics_in_db():
    for topic_name, topic_link, topic_content, category in zip(topics_list, topics_links, topics_content, associated_categories):
        summary = summarize_content(topic_content)
        cursor.execute("""
            INSERT INTO topics (topic_name, topic_link, topic_content, associated_category, summary) 
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE topic_content = VALUES(topic_content), summary = VALUES(summary)
        """, (topic_name, topic_link, topic_content, category, summary))
    db.commit()

def store_last_fetched_topic(category, first_topic):
    cursor.execute("SELECT * FROM last_fetched WHERE category_name = %s", (category,))
    result = cursor.fetchone()

    if result:
        cursor.execute("""
            UPDATE last_fetched 
            SET last_topic = %s, last_fetched_time = %s 
            WHERE category_name = %s
        """, (first_topic, datetime.now(), category))
    else:
        cursor.execute("""
            INSERT INTO last_fetched (category_name, last_topic, last_fetched_time) 
            VALUES (%s, %s, %s)
        """, (category, first_topic, datetime.now()))

    db.commit()

def get_topics_by_category(category):
    cursor.execute("SELECT topic_name, topic_link, summary FROM topics WHERE associated_category = %s LIMIT 2", (category,))
    result = cursor.fetchall()
    if result:
        return result
    else:
        return None

def backfill_and_poll():
    while True:
        for category in categories:
            cursor.execute("SELECT last_topic, last_fetched_time FROM last_fetched WHERE category_name = %s", (category,))
            result = cursor.fetchone()
            if result:
                last_topic, last_fetched_time = result
                sub_response = requests.get(links[categories.index(category)])
                sub_soup = BeautifulSoup(sub_response.content, 'html.parser')
                latest_topic = sub_soup.select('td.main-link a.title')[0].text.strip()
                if latest_topic != last_topic:
                    extract_topics()
                    print(f"New topics fetched for category {category}.")
                else:
                    print(f"No new data for category {category}.")
            else:
                extract_topics()
        print("Sleeping for 2 minutes...")
        time.sleep(120)


@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Welcome to the category bot. Use /categories to get started.")


@bot.message_handler(commands=['categories'])
def show_categories(message):
    cursor.execute("SELECT category_name FROM categories")
    result = cursor.fetchall()

    if result:
        markup = InlineKeyboardMarkup()
        for r in result:
            category = r[0]
            markup.add(InlineKeyboardButton(category, callback_data=category))

        bot.reply_to(message, "Choose a category:", reply_markup=markup)
    else:
        bot.reply_to(message, "No categories found.")

# Handle category selection
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    category = call.data
    topics = get_topics_by_category(category)

    if topics:
        reply = ""
        for topic in topics:
            topic_name = topic[0]
            topic_link = topic[1]
            summary = topic[2] if topic[2] else 'No summary available.'  # Default to 'No summary available'
            reply += f"📌 *{topic_name}*\nSummary: {summary}\n🔗 [Link]({topic_link})\n\n"
        bot.send_message(call.message.chat.id, f"Top 2 topics in {category}:\n{reply}", parse_mode="Markdown", disable_web_page_preview=True)
    else:
        bot.send_message(call.message.chat.id, f"No topics found for category: {category}")

if __name__ == "__main__":
    url = 'https://gov.optimism.io/'
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')
    print("Started running")

    # Uncomment the following to initialize and backfill categories and topics
    # create_tables()
    # extract_categories(soup)
    # store_categories_in_db()
    # extract_topics()

    thread = threading.Thread(target=backfill_and_poll)
    thread.start()

    print("Starting Telegram bot...")
    bot.polling()