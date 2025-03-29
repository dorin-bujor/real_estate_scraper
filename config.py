import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Email configuration
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_USER = os.getenv('EMAIL_USER')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
RECIPIENT_EMAIL = os.getenv('RECIPIENT_EMAIL')

# Gemini configuration
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Scraping configuration
SCRAPING_INTERVAL = int(os.getenv('SCRAPING_INTERVAL', '3600'))  # Default 1 hour
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Connection': 'keep-alive',
}

# Real estate websites to scrape
WEBSITES = [
    {
        'name': 'Storia',
        'url': 'https://www.storia.ro/ro/rezultate/vanzare/teren/iasi/tomesti/chicerea?ownerTypeSingleSelect=ALL&distanceRadius=5&priceMax=33000&viewType=listing&by=LATEST&direction=DESC',
        'selector': {
            'listing': 'article[data-cy="listing-item"]',
            'title': 'p[data-cy="listing-item-title"]',
            'price': 'span.css-2bt9f1',
            'link': 'a[data-cy="listing-item-link"]'
        }
    }
    # Add more websites here as needed
] 