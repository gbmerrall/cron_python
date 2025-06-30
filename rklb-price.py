#!/usr/bin/env python3

import httpx
import logging
import os
import yfinance as yf

from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# load environment variables
load_dotenv()


def send_notification(title: str, message: str, emojis: list[str] = [], priority: str = "3") -> None:
    """
    Send a notification using ntfy.sh.
    
    Args:
        title (str): The notification title
        message (str): The notification message
        emojis (list[str]): List of emoji tags to include
        priority (int): The notification priority (0-4)
    """
    try:
        logger.info(f"Seeing NTFY auth {os.getenv('NTFY_USERNAME')}/{os.getenv('NTFY_PASSWORD')}")
        auth = httpx.BasicAuth(username=os.getenv("NTFY_USERNAME"), 
                               password=os.getenv("NTFY_PASSWORD"))
        
        client = httpx.Client(auth=auth, timeout=10)
        logger.info(f"Sending notification to {os.getenv('NTFY_HOST')}/{os.getenv('NTFY_EOD_TOPIC')}")
        response = client.post(
            f"{os.getenv('NTFY_HOST')}/{os.getenv('NTFY_EOD_TOPIC')}",
            data=message,
            headers={
                "Title": title,
                "Priority": str(priority),
                "Tags": ",".join(emojis) if emojis else "",
                "Click": "https://finance.yahoo.com/quote/RKLB/"
            }
        )
        response.raise_for_status()
        logger.info(f"Notification sent successfully: {response.text}")
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")

def main() -> None:
    """
    Main function to fetch RKLB stock data and send notifications.
    """
    try:
        # Fetch RKLB stock data
        stock = yf.Ticker("RKLB")
        current_price = stock.info.get('regularMarketPrice')
        price_change = stock.info.get('regularMarketChangePercent')
        
        if current_price is None:
            logger.error("Unable to fetch RKLB quote")
            send_notification(
                title="RKLB quote error",
                message="Yahoo data error?",
                priority="4",
                emojis=['skull']
            )
            return

        # Format the price with 2 decimal places
        formatted_price = f"${current_price:.2f}"
        formatted_change = f"{price_change:.2f}%"

        if price_change > 0:
            emoji = "arrow_up"
        elif price_change < 0:
            emoji = "arrow_down"
        else:
            emoji = "arrow_up_down"

        logger.info(f"RKLB current price: {formatted_price} / {formatted_change}")
        
        # Send notification with the current price
        send_notification(
            title="RKLB quote",
            message=f"{formatted_price} / {formatted_change}",
            emojis=[emoji]
        )

    except Exception as e:
        logger.error(f"Error in main function: {e}")
        send_notification(
            title="RKLB quote error",
            message="Yahoo down?",
            priority=4,
            emojis=['skull']
        )

if __name__ == "__main__":
    main() 