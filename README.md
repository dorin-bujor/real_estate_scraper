# Real Estate Scraper

A Python application that scrapes real estate websites and sends email notifications when new listings are found.

## Features

- Scrapes multiple real estate websites
- Sends email notifications for new listings
- Keeps track of seen listings to avoid duplicates
- Configurable scraping intervals
- Easy to add new websites to scrape

## Setup

1. Install the required dependencies:
```bash
pip install -r requirements.txt
```

2. Create a `.env` file in the project root with your email settings:
```
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USER=your-email@gmail.com
EMAIL_PASSWORD=your-app-specific-password
RECIPIENT_EMAIL=recipient@example.com
SCRAPING_INTERVAL=3600  # in seconds (default: 1 hour)
```

Note: If using Gmail, you'll need to use an App Password instead of your regular password. You can generate one in your Google Account settings.

3. Configure the websites to scrape in `config.py`:
- Add the website URL
- Configure the CSS selectors for listing elements
- Adjust the scraping interval if needed

## Usage

Run the scraper:
```bash
python scraper.py
```

To run it continuously, you can use a task scheduler like cron or set up a systemd service.

## Adding New Websites

To add a new website to scrape:

1. Add a new entry to the `WEBSITES` list in `config.py`
2. Configure the appropriate CSS selectors for:
   - Listing container
   - Title
   - Price
   - Link

Example:
```python
{
    'name': 'New Website',
    'url': 'https://example.com/listings',
    'selectors': {
        'listing': '.property-card',
        'title': '.property-title',
        'price': '.property-price',
        'link': '.property-link'
    }
}
```

## Notes

- The scraper maintains a list of seen listings in `seen_listings.json`
- Make sure to respect the websites' robots.txt and terms of service
- Consider adding delays between requests to avoid overwhelming the servers 