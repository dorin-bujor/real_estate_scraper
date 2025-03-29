import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import config
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import re
import logging
import hashlib
import requests

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[
        logging.FileHandler('scraper.log'),
        logging.StreamHandler()
    ]
)

# Filter out WebDriver manager logs
logging.getLogger('WDM').setLevel(logging.WARNING)

class RealEstateScraper:
    def __init__(self):
        """Initialize the scraper with configuration"""
        # Initialize configuration
        self.config = {
            'url': config.WEBSITES[0]['url'],  # Using the first website for now
            'selector': config.WEBSITES[0]['selector'],
            'email': {
                'host': config.EMAIL_HOST,
                'port': config.EMAIL_PORT,
                'user': config.EMAIL_USER,
                'password': config.EMAIL_PASSWORD,
                'recipient': config.RECIPIENT_EMAIL
            }
        }
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.sender_email = self.config['email']['user']
        self.sender_password = self.config['email']['password']
        self.recipient_email = self.config['email']['recipient']
        
        # Initialize database connection
        self.conn = sqlite3.connect('listings.db')
        self.cursor = self.conn.cursor()
        self.setup_database()
        
        # Get or create site record
        self.cursor.execute('SELECT id FROM sites WHERE base_url = ?', (self.config['url'],))
        result = self.cursor.fetchone()
        if result:
            self.site_id = result[0]
        else:
            self.cursor.execute('INSERT INTO sites (name, base_url) VALUES (?, ?)', 
                              ('Storia.ro', self.config['url']))
            self.site_id = self.cursor.lastrowid
            self.conn.commit()
            
        # Initialize WebDriver
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument(f'user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.binary_location = '/usr/bin/google-chrome'
        
        self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36'
        })
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        self.wait = WebDriverWait(self.driver, 10)

    def setup_database(self):
        """Initialize SQLite database"""
        try:
            cursor = self.conn.cursor()
            
            # Create sites table if it doesn't exist
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    base_url TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(base_url)
                )
            ''')
            
            # Insert initial site (Storia) if it doesn't exist
            cursor.execute('''
                INSERT OR IGNORE INTO sites (name, base_url) 
                VALUES (?, ?)
            ''', ('Storia', 'https://www.storia.ro'))

            # Create listings table if it doesn't exist
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS seen_listings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_id INTEGER NOT NULL,
                    listing_hash TEXT NOT NULL,
                    listing_url TEXT NOT NULL,
                    title TEXT,
                    price REAL,
                    currency TEXT,
                    image_url TEXT,
                    location TEXT,
                    seen_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (site_id) REFERENCES sites(id),
                    UNIQUE(listing_hash)
                )
            ''')

            # Create indexes if they don't exist
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_listing_hash ON seen_listings(listing_hash)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_site_id ON seen_listings(site_id)')
            
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error setting up database: {str(e)}")
            raise

    def __del__(self):
        """Cleanup when the scraper is destroyed"""
        if hasattr(self, 'driver'):
            self.driver.quit()
        if hasattr(self, 'conn'):
            self.conn.close()

    def get_listing_info(self, listing_hash: str) -> dict:
        """Get listing information from database"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT l.*, s.name as site_name, s.base_url 
                FROM seen_listings l
                JOIN sites s ON l.site_id = s.id
                WHERE l.listing_hash = ?
            ''', (listing_hash,))
            row = cursor.fetchone()
            if row:
                return {
                    'id': row[0],
                    'site_id': row[1],
                    'listing_hash': row[2],
                    'listing_url': row[3],
                    'title': row[4],
                    'price': row[5],
                    'currency': row[6],
                    'image_url': row[7],
                    'location': row[8],
                    'seen_date': row[9],
                    'last_updated': row[10],
                    'site_name': row[11],
                    'base_url': row[12]
                }
            return None
        except Exception as e:
            logging.error(f"Error getting listing info: {str(e)}")
            return None

    def update_listing(self, listing_hash: str, listing_url: str, title: str, price: float, currency: str, image_url: str, location: str = None) -> dict:
        """Update or insert listing information"""
        try:
            cursor = self.conn.cursor()
            
            # Get site_id for Storia (we'll make this more dynamic when adding more sites)
            cursor.execute('SELECT id FROM sites WHERE name = ?', ('Storia',))
            site_id = cursor.fetchone()[0]
            
            existing = self.get_listing_info(listing_hash)
            result = {
                'is_new': not existing,
                'price_changed': False,
                'old_price': None,
                'listing_hash': listing_hash,
                'listing_url': listing_url,
                'title': title,
                'price': price,
                'currency': currency,
                'image_url': image_url,
                'location': location
            }
            
            if existing:
                if existing['price'] != price:
                    result['price_changed'] = True
                    result['old_price'] = existing['price']
                    # Update existing listing
                    cursor.execute('''
                        UPDATE seen_listings 
                        SET title = ?, price = ?, currency = ?, image_url = ?, location = ?, last_updated = CURRENT_TIMESTAMP
                        WHERE listing_hash = ?
                    ''', (title, price, currency, image_url, location, listing_hash))
                    logging.info(f"Updated listing {listing_hash} (price changed from {existing['price']} to {price})")
            else:
                # Insert new listing
                cursor.execute('''
                    INSERT INTO seen_listings (site_id, listing_hash, listing_url, title, price, currency, image_url, location)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (site_id, listing_hash, listing_url, title, price, currency, image_url, location))
                logging.info(f"Added new listing {listing_hash}")
            
            self.conn.commit()
            return result
            
        except Exception as e:
            logging.error(f"Error updating listing: {str(e)}")
            return None

    def extract_price(self, price_text: str) -> float:
        """Extract numeric price from text"""
        try:
            price_text = price_text.replace('€', '').replace(' ', '').replace('.', '')
            price_text = ''.join(c for c in price_text if c.isdigit())
            return float(price_text)
        except Exception as e:
            logging.error(f"Error extracting price from {price_text}: {str(e)}")
            return 0.0

    def extract_area(self, area_text: str) -> float:
        """Extract numeric area from text"""
        try:
            numbers = re.findall(r'\d+', area_text)
            if numbers:
                return float(numbers[0])
            return 0.0
        except:
            return 0.0

    def extract_price_and_currency(self, price_text: str) -> tuple[float, str]:
        """Extract price and currency from price text."""
        try:
            # Remove any whitespace and convert to lowercase
            price_text = price_text.strip().lower()
            
            # Define currency mappings
            currency_patterns = {
                'eur': ['€', 'eur', 'euro'],
                'ron': ['lei', 'ron', 'leu'],
                'usd': ['$', 'usd', 'dollar']
            }
            
            # Detect currency
            detected_currency = 'ron'  # default to RON
            for currency, patterns in currency_patterns.items():
                if any(pattern in price_text for pattern in patterns):
                    detected_currency = currency
                    break
            
            # Extract numeric value
            # Remove currency symbols and text
            clean_text = price_text
            for patterns in currency_patterns.values():
                for pattern in patterns:
                    clean_text = clean_text.replace(pattern, '')
            
            # Remove any remaining non-numeric characters except decimal point
            clean_text = ''.join(c for c in clean_text if c.isdigit() or c == '.')
            
            # Convert to float
            price = float(clean_text)
            
            return price, detected_currency.upper()
            
        except Exception as e:
            logging.error(f"Error extracting price and currency from '{price_text}': {str(e)}")
            return 0.0, 'RON'  # Return defaults on error

    def generate_listing_hash(self, title: str, price: float, currency: str, url: str) -> str:
        """Generate a consistent hash for a listing."""
        hash_input = f"{title}{price}{currency}{url}"
        return hashlib.sha256(hash_input.encode()).hexdigest()

    def scrape_storia(self):
        """Scrape Storia website for listings"""
        try:
            url = self.config['url']
            logging.info(f"\n=== Starting Storia Scraper ===")
            logging.info(f"URL: {url}")
            
            # Get the page content
            self.driver.get(url)
            self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, self.config['selector']['listing'])))
            
            # Parse the page
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            listings = soup.select(self.config['selector']['listing'])
            
            if not listings:
                logging.warning("No listings found on the page")
                return []
            
            # Process each listing
            results = []
            for listing in listings:
                try:
                    # Extract listing details
                    title = listing.select_one(self.config['selector']['title']).text.strip()
                    price_text = listing.select_one(self.config['selector']['price']).text.strip()
                    link = listing.select_one(self.config['selector']['link'])['href']
                    
                    # Extract price and currency
                    price, currency = self.extract_price_and_currency(price_text)
                    
                    # Get image URL if available
                    image_url = None
                    img_tag = listing.select_one('img')
                    if img_tag and 'src' in img_tag.attrs:
                        image_url = img_tag['src']
                    
                    # Get location if available
                    location = None
                    location_tag = listing.select_one('p[data-cy="listing-item-location"]')
                    if location_tag:
                        location = location_tag.text.strip()
                    
                    # Generate a unique hash for this listing
                    listing_hash = self.generate_listing_hash(title, price, currency, link)
                    
                    # Add to results
                    results.append({
                        'listing_hash': listing_hash,
                        'listing_url': link,
                        'title': title,
                        'price': price,
                        'currency': currency,
                        'image_url': image_url,
                        'location': location
                    })
                    
                except Exception as e:
                    logging.error(f"Error processing listing: {str(e)}")
                    continue
            
            return results
            
        except Exception as e:
            logging.error(f"Error during scraping: {str(e)}")
            return []

    def send_email(self, listings):
        """Send email with new listings"""
        if not listings:
            logging.info("No listings to send")
            return
            
        try:
            # Get site name
            self.cursor.execute('SELECT name FROM sites WHERE id = ?', (self.site_id,))
            site_name = self.cursor.fetchone()[0]
            
            # Prepare email content
            subject = f"New Real Estate Listings from {site_name} - {len(listings)} Found"
            
            # Create email body
            body = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; }}
                    .listing {{ 
                        margin-bottom: 20px; 
                        padding: 10px; 
                        border: 1px solid #ddd; 
                        border-radius: 5px;
                    }}
                    .listing img {{ 
                        max-width: 100%; 
                        height: auto; 
                        border-radius: 5px;
                    }}
                    .price {{ 
                        font-size: 1.2em; 
                        font-weight: bold; 
                        color: #2c5282;
                    }}
                    .location {{
                        color: #4a5568;
                        margin: 5px 0;
                    }}
                </style>
            </head>
            <body>
                <h2>New Listings from {site_name}</h2>
                <p>Found {len(listings)} new listings.</p>
            """
            
            # Add all listings
            for idx, listing in enumerate(listings, 1):
                body += f"""
                <a href="{listing['listing_url']}" style="text-decoration: none; color: inherit; display: block;">
                    <div class="listing">
                        <h3>Listing #{idx}</h3>
                        <p><strong>{listing['title']}</strong></p>
                        <p class="price">{listing['price']} {listing['currency']}</p>
                        <p class="location">Location: {listing['location'] if listing['location'] else 'Not specified'}</p>
                        <img src="{listing['image_url']}" alt="Listing image">
                    </div>
                </a>
                """
            
            body += """
            </body>
            </html>
            """
            
            # Send email
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.sender_email
            msg['To'] = self.recipient_email
            
            msg.attach(MIMEText(body, 'html'))
            
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(self.sender_email, self.sender_password)
                server.send_message(msg)
            
            logging.info(f"✓ Email sent successfully with {len(listings)} listings")
            
        except Exception as e:
            logging.error(f"Error sending email: {str(e)}")

    def check_new_listings(self):
        """Check for new listings and send email if found."""
        try:
            # Get listings from Storia
            storia_listings = self.scrape_storia()
            
            if not storia_listings:
                logging.info("\nNo new or updated listings found")
                return
            
            # Filter only new listings (not already in database)
            new_listings = []
            for listing in storia_listings:
                # Check if listing exists
                self.cursor.execute('SELECT id FROM seen_listings WHERE listing_hash = ?', (listing['listing_hash'],))
                if not self.cursor.fetchone():
                    # Update the database with the new listing
                    result = self.update_listing(
                        listing['listing_hash'],
                        listing['listing_url'],
                        listing['title'],
                        listing['price'],
                        listing['currency'],
                        listing['image_url'],
                        listing['location']
                    )
                    if result:
                        new_listings.append(listing)
                        logging.info(f"✓ Listing #{len(new_listings)}: {listing['title']}")
            
            logging.info(f"\nSummary:")
            logging.info(f"Total listings found: {len(storia_listings)}")
            logging.info(f"New or updated: {len(new_listings)}")
            
            if new_listings:
                # Send email with all new listings
                self.send_email(new_listings)
                logging.info(f"\nSent email with {len(new_listings)} new listings")
            else:
                logging.info("\nNo new listings found")
            
        except Exception as e:
            logging.error(f"Error checking new listings: {str(e)}")
            raise e

    def scrape_listing(self, url):
        """Scrape a single listing page"""
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract listing details
            title = soup.find('h1', class_='title').text.strip()
            price_text = soup.find('div', class_='price').text.strip()
            price, currency = self.extract_price_and_currency(price_text)
            
            # Extract location from the listing details
            location = None
            location_element = soup.find('div', class_='location')
            if location_element:
                location = location_element.text.strip()
            else:
                # Try to extract location from title if not found in location element
                title_parts = title.split(',')
                for part in title_parts:
                    part = part.strip()
                    if any(loc in part.lower() for loc in ['goruni', 'tomesti', 'iasi', 'chicerea']):
                        location = part
                        break
            
            # Extract image URL
            image = soup.find('img', class_='main-image')
            image_url = image['src'] if image else None
            
            # Create listing hash
            listing_hash = self.generate_listing_hash(title, price, currency, url)
            
            # Store in database
            self.cursor.execute('''
                INSERT OR REPLACE INTO seen_listings 
                (listing_hash, title, price, listing_url, image_url, location, site_id, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ''', (listing_hash, title, price, url, image_url, location, self.site_id))
            self.conn.commit()
            
            return listing_hash
            
        except Exception as e:
            logging.error(f"Error scraping listing: {str(e)}")
            return None

def main():
    try:
        scraper = RealEstateScraper()
        scraper.check_new_listings()
    except Exception as e:
        logging.error(f"Fatal error: {str(e)}")
        raise

if __name__ == "__main__":
    main() 