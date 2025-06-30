#!/usr/bin/env python3
"""
Sensor check-in monitoring script.

Connects to a remote SQLite database via SSH and checks for missing sensor check-ins
in the last 45 minutes. Reports any MAC addresses with fewer than 2 entries.

Schema:
CREATE TABLE temp_humidity (
	location VARCHAR(64) NOT NULL,
	mac VARCHAR(64) NOT NULL,
	temperature NUMERIC NOT NULL,
	humidity NUMERIC NOT NULL,
	timestamp DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
	PRIMARY KEY (location, timestamp)
);

JSON output: 
[{"mac":"24:58:7c:ac:61:8c","location":"wine","timestamp":"2025-06-29 23:46:18.000000"},
{"mac":"24:58:7c:ac:61:8c","location":"wine","timestamp":"2025-06-30 00:01:55.000000"},
{"mac":"24:58:7c:ac:61:8c","location":"wine","timestamp":"2025-06-30 00:17:32.000000"},
{"mac":"24:58:7c:ac:61:8c","location":"wine","timestamp":"2025-06-30 00:33:09.000000"},
{"mac":"24:58:7c:ac:61:8c","location":"wine","timestamp":"2025-06-30 00:48:46.000000"},
{"mac":"24:58:7c:ac:61:8c","location":"wine","timestamp":"2025-06-30 01:04:23.000000"},
{"mac":"24:58:7c:ac:61:8c","location":"wine","timestamp":"2025-06-30 01:20:00.000000"},
{"mac":"24:58:7c:ac:61:8c","location":"wine","timestamp":"2025-06-30 01:35:37.000000"}]


"""

import asyncio
import json
import sys
import logging
import os
import httpx
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import List, Tuple, Dict
import asyncssh
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configuration constants
MINUTES_AGO = int(os.getenv("MINUTES_AGO", "45"))
MIN_CHECKINS = int(os.getenv("MIN_CHECKINS", "2"))

# loaded from .env
NTFY_HOST = os.getenv("NTFY_HOST")
NTFY_SENSOR_TOPIC = os.getenv("NTFY_SENSOR_TOPIC")
NTFY_USERNAME = os.getenv("NTFY_USERNAME")
NTFY_PASSWORD = os.getenv("NTFY_PASSWORD")
SSH_HOST = os.getenv("SSH_HOST")
SSH_USERNAME = os.getenv("SSH_USERNAME")
DATABASE_PATH = os.getenv("DATABASE_PATH")

def send_notification(title: str, message: str, emojis: list[str] = [], priority: str = "3") -> None:
    """
    Send a notification using ntfy.sh.
    
    Args:
        title (str): The notification title
        message (str): The notification message
        emojis (list[str]): List of emoji tags to include
        priority (str): The notification priority (0-4)
    """
    if not NTFY_HOST or not NTFY_SENSOR_TOPIC:
        logger.error("NTFY_HOST and NTFY_SENSOR_TOPIC environment variables must be set.")
        return

    try:
        auth = httpx.BasicAuth(username=NTFY_USERNAME, password=NTFY_PASSWORD) if NTFY_USERNAME and NTFY_PASSWORD else None
        
        headers = {
            "Title": title,
            "Priority": str(priority),
        }
        if emojis:
            headers["Tags"] = ",".join(emojis)

        with httpx.Client(auth=auth, timeout=10) as client:
            logger.info(f"Sending notification to {NTFY_HOST}/{NTFY_SENSOR_TOPIC}")
            response = client.post(
                f"{NTFY_HOST}/{NTFY_SENSOR_TOPIC}",
                data=message,
                headers=headers,
            )
            response.raise_for_status()
            logger.info(f"Notification sent successfully: {response.text}")
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error sending notification: {e.response.status_code} - {e.response.text}")
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")


async def execute_sql_query(host: str, username: str, sql: str) -> str:
    """
    Execute a SQL query on a remote SQLite database via SSH.
    
    Args:
        host: The SSH host address
        username: The SSH username
        sql: The SQL query to execute
        
    Returns:
        The JSON output from the SQLite query
        
    Raises:
        asyncssh.Error: If SSH connection or command execution fails
    """
    logger.debug(f"Executing query: {sql}")
    try:
        async with asyncssh.connect(host, username=username) as conn:
            command = f'sqlite3 -json {DATABASE_PATH} "{sql}"'
            result = await conn.run(command)
            return result.stdout
    except asyncssh.Error as e:
        logger.error(f"SSH connection error: {e}")
        raise


def build_query() -> str:
    """
    Build the SQL query to get sensor data from the last MINUTES_AGO minutes.
    
    Returns:
        SQL query string
    """
    # Calculate timestamp for MINUTES_AGO minutes ago in UTC
    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=MINUTES_AGO)
    cutoff_str = cutoff_time.strftime('%Y-%m-%d %H:%M:%S')
    
    return f"""
    SELECT mac, location, timestamp 
    FROM temp_humidity 
    WHERE timestamp >= '{cutoff_str}'
    ORDER BY mac, timestamp
    """


def analyze_sensor_data(json_output: str) -> List[Tuple[str, str]]:
    """
    Analyze sensor data to find sensors with fewer than MIN_CHECKINS.

    Args:
        json_output: JSON string from SQLite query.

    Returns:
        List of tuples (mac, location) for sensors with missing check-ins.
    """
    if not json_output.strip():
        return []

    try:
        records = json.loads(json_output)
    except json.JSONDecodeError:
        logger.exception("Error parsing JSON output from database.")
        return []

    mac_counts = defaultdict(int)
    mac_locations: Dict[str, str] = {}

    for record in records:
        mac = record.get('mac')
        if not mac:
            continue
        mac_counts[mac] += 1
        if mac not in mac_locations:
            mac_locations[mac] = record.get('location', 'unknown location')

    missing_checkins = []
    for mac, count in mac_counts.items():
        logger.info(f"MAC: {mac}, Location: {mac_locations.get(mac)}, Entries: {count}")
        if count < MIN_CHECKINS:
            missing_checkins.append((mac, mac_locations[mac]))
    
    return missing_checkins


async def main():
    """
    Main function to execute the sensor check-in monitoring.
    """
    # Check for required environment variables
    required_vars = {
        "NTFY_HOST": NTFY_HOST,
        "NTFY_SENSOR_TOPIC": NTFY_SENSOR_TOPIC,
        "SSH_HOST": SSH_HOST,
        "SSH_USERNAME": SSH_USERNAME,
        "DATABASE_PATH": DATABASE_PATH,
    }
    missing_vars = [name for name, value in required_vars.items() if not value]

    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}. Exiting.")
        sys.exit(1)

    try:
        # Build and execute query
        sql_query = build_query()
        logger.info(f"Querying for data since: {datetime.now(timezone.utc) - timedelta(minutes=MINUTES_AGO)}")
        
        json_output = await execute_sql_query(SSH_HOST, SSH_USERNAME, sql_query)
        logger.debug(f"JSON output: {json_output}")

        if not json_output.strip():
            logger.warning("No sensor data found in time period. All sensors may be offline.")
            send_notification(
                title="Sensor Check-in Alert",
                message=f"No sensor data received in the last {MINUTES_AGO} minutes. All sensors may be offline.",
                priority="4",
                emojis=['warning', 'thermometer']
            )
            return

        missing_checkins = analyze_sensor_data(json_output)
        
        if missing_checkins:
            logger.warning(f"Missing check-ins detected for {len(missing_checkins)} sensor(s).")
            
            missing_sensors_str = "\n".join(
                [f"{mac} ({location})" for mac, location in missing_checkins]
            )
            message = f"Missing check-ins detected for {len(missing_checkins)} sensor(s):\n{missing_sensors_str}"
            
            send_notification(
                title="Sensor Check-in Alert",
                message=message,
                priority="2",
                emojis=['warning', 'thermometer']
            )
        else:
            logger.info(f"All sensors have sufficient check-ins in the last {MINUTES_AGO} minutes.")
            
    except Exception:
        logger.exception("An unhandled error occurred during script execution.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
