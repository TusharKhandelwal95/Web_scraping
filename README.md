## Project Overview

This project scrapes data from forum websites, stores it in a MySQL database, and includes functionality to backfill and poll for new topics on a daily interval. It also integrates with the Gemini API to generate summaries for all topics within each category and uses a Telegram bot to display categories and the top 2 topic summaries for each category.

### Features
- **Data Scraping**: Fetches category names, descriptions, and topics from forum websites.
- **Summary Generation**: Utilizes the Gemini API to summarize all topics for each category.
- **Polling Mechanism**: Automatically checks for new topics every 24 hours.
- **Telegram Bot Integration**: Access categories and their top 2 topic summaries via a Telegram bot.

### Refer to project.py code for complete code



