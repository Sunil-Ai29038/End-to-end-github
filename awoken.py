#---Enhanced Facebook Automation Script---#
#---Based on Awoken.py---#
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import time
import os
import traceback
import json
import random
import datetime
import signal
import emoji
import sys
from collections import deque

# Configuration files
MESSAGES_FILE = "message.txt"
TARGETS_FILE = "targets.txt"
DELAYS_FILE = "time.txt"
ACCOUNTS_FILE = "account.txt"
COOKIES_FILE = "fb_cookies.json"
DEBUG_DIR = "debug_screenshots"
LOGS_DIR = "logs"

# Global variables
SAVED_COOKIES = None
RUNNING = True
MAX_TABS = 20  # Maximum number of tabs to use

# Status constants
STATUS_OK = "SUCCESS"
STATUS_ERROR = "ERROR"
STATUS_RETRY = "RETRY"

def get_timestamp():
    return datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")

def log(message, status=None):
    status_tag = f"[{status}] " if status else ""
    formatted_message = f"{get_timestamp()} {status_tag}{message}"
    print(formatted_message)
    
    # Also write to log file
    os.makedirs(LOGS_DIR, exist_ok=True)
    log_file = os.path.join(LOGS_DIR, f"log_{datetime.datetime.now().strftime('%Y%m%d')}.txt")
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(formatted_message + "\n")

def load_file_lines(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        log(f"Error: {filename} not found. Creating empty file.", STATUS_ERROR)
        with open(filename, 'w'): pass
        return []
    except Exception as e:
        log(f"Error loading {filename}: {e}", STATUS_ERROR)
        return []

def load_account_credentials():
    try:
        for line in load_file_lines(ACCOUNTS_FILE):
            if ':' in line:
                return tuple(x.strip() for x in line.split(':', 1))
        log(f"Error: Invalid format in {ACCOUNTS_FILE}", STATUS_ERROR)
    except Exception as e:
        log(f"Error loading credentials: {e}", STATUS_ERROR)
    return None, None

def get_random_delay(delays):
    try:
        valid_delays = [int(d) for d in delays if d.isdigit()]
        return random.choice(valid_delays) if valid_delays else random.randint(30, 60)
    except Exception as e:
        log(f"Error parsing delays: {e}", STATUS_ERROR)
        return random.randint(30, 60)

def load_cookies(context):
    try:
        if os.path.exists(COOKIES_FILE):
            with open(COOKIES_FILE, "r") as f:
                context.add_cookies(json.load(f))
                log("Cookies loaded successfully", STATUS_OK)
                return True
        log("No cookies file found", STATUS_RETRY)
    except Exception as e:
        log(f"Error loading cookies: {e}", STATUS_ERROR)
    return False

def initialize_browser():
    try:
        playwright = sync_playwright().start()
        browser = playwright.firefox.launch(
            headless=True,
            timeout=60000,
            firefox_user_prefs={
                "browser.cache.memory.enable": True,
                "dom.webnotifications.enabled": False,
                "media.volume_scale": "0.0",
                "privacy.trackingprotection.enabled": False,
                "javascript.options.jit.content": True,
                "gfx.font_rendering.colr.enabled": True,
                "intl.accept_languages": "en-US, en"
            }
        )
        log("Browser initialized successfully", STATUS_OK)
        return browser, playwright
    except Exception as e:
        log(f"Failed to initialize browser: {e}", STATUS_ERROR)
        return None, None

def login_to_facebook(page, email, password):
    try:
        if load_cookies(page.context):
            try:
                log("Testing cookie validity by navigating to Facebook", STATUS_RETRY)
                page.goto("https://www.facebook.com/", timeout=60000, wait_until="load")
                if "login" not in page.url.lower():
                    log("Logged in via cookies successfully", STATUS_OK)
                    return True
                log("Cookies expired or invalid", STATUS_RETRY)
            except Exception as e:
                log(f"Error verifying cookies: {e}", STATUS_ERROR)
        
        log("Starting automated login process", STATUS_RETRY)
        page.goto("https://www.facebook.com/", timeout=60000, wait_until="domcontentloaded")
        
        try:
            page.locator("text=Accept All").first.click(timeout=5000)
            log("Accepted cookies popup", STATUS_OK)
        except Exception:
            log("No cookies popup found or already accepted", STATUS_OK)
            
        try:
            log("Filling login credentials", STATUS_RETRY)
            page.locator("#email").fill(email)
            page.locator("#pass").fill(password)
            page.locator("button[name='login']").click()
            log("Login credentials submitted", STATUS_OK)
            
            try:
                page.locator("div[aria-label='Facebook']").wait_for(timeout=15000)
                cookies = page.context.cookies()
                with open(COOKIES_FILE, "w") as f:
                    json.dump(cookies, f)
                log("Login successful - cookies saved", STATUS_OK)
                return True
            except Exception:
                if "login" not in page.url.lower():
                    log("Login appears successful based on URL redirect", STATUS_OK)
                    return True
                log("Login failed - still on login page", STATUS_ERROR)
                return False
                
        except Exception as e:
            log(f"Error during automated login: {e}", STATUS_ERROR)
            return False
            
    except Exception as e:
        log(f"Fatal error in login process: {e}", STATUS_ERROR)
        return False

def ensure_url_loads(page, url, max_attempts=3):
    for attempt in range(1, max_attempts+1):
        try:
            log(f"Loading URL (attempt {attempt}/{max_attempts}): {url}", STATUS_RETRY)
            page.goto(url, timeout=60000, wait_until="domcontentloaded")
            
            # Check if page loaded successfully
            page.wait_for_selector("body", timeout=30000)
            
            if "facebook.com" in page.url and "login" not in page.url.lower():
                log("Page loaded successfully", STATUS_OK)
                time.sleep(2)
                return True
                
            log(f"Redirect detected: {page.url}", STATUS_RETRY)
            if attempt < max_attempts:
                time.sleep(2)
                
        except Exception as e:
            log(f"Error loading URL: {e}", STATUS_ERROR)
            page.screenshot(path=f"{DEBUG_DIR}/url_load_error_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
            if attempt < max_attempts:
                time.sleep(2)
    
    log(f"Failed to load URL after {max_attempts} attempts", STATUS_ERROR)
    return False

def find_inbox(page, max_attempts=3, wait_time=10):
    import time

    selectors = [
        "div[role='textbox'][contenteditable='true']",
        "div.notranslate._5rpu[role='textbox']",
        "div[aria-label='Message'][contenteditable='true']",
        "div[data-lexical-editor='true']",
        "div[role='textbox'][data-testid='messenger_composer']"
    ]

    for attempt in range(1, max_attempts + 1):
        log(f"Attempt {attempt}/{max_attempts}: Checking all selectors...", STATUS_RETRY)
        
        found = False
        working_selector = None

        # एक ही बार में सभी selectors चेक करें
        for selector in selectors:
            try:
                inbox = page.locator(selector)
                if inbox.count() > 0:
                    log(f"Inbox found using selector: {selector}", STATUS_OK)
                    return True, selector
            except Exception as e:
                log(f"Error with selector {selector}: {e}", STATUS_RETRY)
                continue

        # अगर कोई selector नहीं मिला, तो इंतज़ार करें
        if attempt < max_attempts:
            log(f"No selector found. Waiting {wait_time} seconds...", STATUS_RETRY)
            time.sleep(wait_time)  # बिना रीलोड के इंतज़ार

    log("Failed to locate inbox after all attempts.", STATUS_ERROR)
    return False, None

def handle_encryption_error(page):
    try:
        if page.locator("text=These messages were sent before").count():
            page.locator("text=Continue").first.click(timeout=5000)
            log("Handled encryption warning", STATUS_OK)
            return True
    except Exception:
        pass
    return False

def send_message_safely(page, message_text, target_idx, msg_idx):
    """Send message to inbox or group with retries and reload - Playwright version"""
    max_attempts = 3
    
    for attempt in range(max_attempts):
        try:
            # First check for and handle encryption error
            if handle_encryption_error(page):
                log("Successfully handled encryption error - proceeding with message", STATUS_OK)
            
            # Check if we're in messenger or group page
            in_messenger = any(x in page.url for x in ["messenger.com", "/messages/", "/t/"])
            in_group = "/groups/" in page.url
            
            log(f"Detected page type: {'Messenger' if in_messenger else 'Group' if in_group else 'Unknown'}", STATUS_OK)
            
            # Different selectors based on page type
            if in_messenger:
                message_selectors = [
                    "div[aria-label='Message'][contenteditable='true']",
                    "div[data-lexical-editor='true']",
                    "div[role='textbox'][data-testid='messenger_composer']",
                    "div.notranslate[contenteditable='true']",
                    "div[contenteditable='true'][spellcheck='true']"
                ]
            else: # Group or other page
                message_selectors = [
                    "div[aria-label='Write a comment']",
                    "div[data-lexical-editor='true']",
                    "div[contenteditable='true'][role='textbox']",
                    "div.notranslate[contenteditable='true']"
                ]
            
            # Find message input area
            message_area = None
            for selector in message_selectors:
                elements = page.locator(selector)
                if elements.count() > 0:
                    message_area = elements.first
                    break
            
            if not message_area:
                if attempt < max_attempts - 1:
                    log("Message input area not found, reloading page and retrying...", STATUS_RETRY)
                    page.reload()
                    page.wait_for_load_state("load")
                    time.sleep(2)
                    continue
                else:
                    log("ERROR: Message input area not found after retries", STATUS_ERROR)
                    page.screenshot(path=f"{DEBUG_DIR}/error_message_area_not_found_target{target_idx}_message{msg_idx}.png")
                    return False
            
            # Click to focus
            message_area.click()
            log("Message input area clicked", STATUS_OK)
            time.sleep(0.2)
            
            # Process message text (handle emojis and multilingual text)
            processed_message = emoji.emojize(message_text, language='alias')
            
            # Type the message character by character with small delays
            for char in processed_message:
                message_area.press(char)
                time.sleep(0.03)  # Small delay between characters
            
            time.sleep(0.5)  # Additional delay after typing
            
            page.screenshot(path=f"{DEBUG_DIR}/message_entered_target{target_idx}_message{msg_idx}.png")
            
            # Send message - different methods for messenger vs groups
            if in_messenger:
                # Press Enter to send in messenger
                message_area.press("Enter")
            else:
                # Look for send button in groups
                send_buttons = page.locator("button[type='submit'], button[aria-label*='Send'], button[aria-label*='Post']")
                if send_buttons.count() > 0:
                    send_buttons.first.click()
                else:
                    # Fall back to Enter key
                    message_area.press("Enter")
            
            log("Message send triggered", STATUS_OK)
            time.sleep(1)
            page.screenshot(path=f"{DEBUG_DIR}/message_sent_target{target_idx}_message{msg_idx}.png")
            
            # Verify message was sent
            if in_messenger:
                try:
                    # Look for the message in the conversation
                    message_snippet = processed_message[:20].replace("'", "\\'")
                    sent_messages = page.locator(f"div:has-text('{message_snippet}')")
                    if sent_messages.count() > 0:
                        log("Message appears to have been sent successfully!", STATUS_OK)
                        return True
                    else:
                        # Check for any error messages
                        error_indicators = page.locator("text=Message failed to send")
                        if error_indicators.count() > 0:
                            log("Error detected: Message failed to send", STATUS_ERROR)
                            return False
                        else:
                            log("No confirmation, but no error either - assuming message sent", STATUS_OK)
                            return True
                except Exception as e:
                    log(f"Error verifying message sent: {e}", STATUS_ERROR)
                    return True  # Assume success if no obvious error
            else:
                # For groups, just check if the input area was cleared
                try:
                    message_area_value = message_area.text_content()
                    if not message_area_value.strip():
                        log("Message input area cleared - message likely sent", STATUS_OK)
                        return True
                    else:
                        log("Warning: Message input area not cleared after sending", STATUS_ERROR)
                        return False
                except Exception as e:
                    log(f"Error checking message input after send: {e}", STATUS_ERROR)
                    return True  # Assume success if no obvious error
                
        except Exception as e:
            log(f"Error while trying to send message (attempt {attempt+1}): {e}", STATUS_ERROR)
            if attempt < max_attempts - 1:
                log("Reloading page and retrying...", STATUS_RETRY)
                page.reload()
                page.wait_for_load_state("load")
                time.sleep(2)
            else:
                log(traceback.format_exc(), STATUS_ERROR)
                page.screenshot(path=f"{DEBUG_DIR}/error_sending_message_target{target_idx}_message{msg_idx}.png")
                return False

def process_target(page, target_url, message, target_idx, msg_idx):
    log(f"\nProcessing target {target_idx+1} (message {msg_idx+1})")
    log(f"URL: {target_url[:60]}...", STATUS_RETRY)
    
    try:
        # Load the URL
        if not ensure_url_loads(page, target_url):
            log(f"Failed to load target URL: {target_url}", STATUS_ERROR)
            return False
            
        # Find inbox
        found, inbox_selector = find_inbox(page)
        if not found:
            log(f"Could not find inbox for target {target_idx+1}", STATUS_ERROR)
            return False
            
        # Send message
        page.screenshot(path=f"{DEBUG_DIR}/before_send_target_{target_idx+1}_msg_{msg_idx+1}.png")
        result = send_message_safely(page, message, inbox_selector, msg_idx)
        page.screenshot(path=f"{DEBUG_DIR}/after_send_target_{target_idx+1}_msg_{msg_idx+1}.png")
        
        return result
        
    except Exception as e:
        log(f"Error processing target: {e}", STATUS_ERROR)
        page.screenshot(path=f"{DEBUG_DIR}/error_target_{target_idx+1}_msg_{msg_idx+1}.png")
        return False

def signal_handler(signum, frame):
    global RUNNING
    log("\nReceived stop signal. Shutting down...", STATUS_OK)
    RUNNING = False

def main():
    global RUNNING
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    os.makedirs(DEBUG_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)
    
    email, password = load_account_credentials()
    if not email or not password:
        log("Invalid credentials", STATUS_ERROR)
        return
        
    targets = load_file_lines(TARGETS_FILE)
    messages = load_file_lines(MESSAGES_FILE)
    delays = load_file_lines(DELAYS_FILE)
    
    if not targets or not messages:
        log("Missing targets or messages", STATUS_ERROR)
        return
        
    log(f"Starting with {len(targets)} targets and {len(messages)} messages", STATUS_OK)
    
    browser, playwright = initialize_browser()
    if not browser:
        return
        
    try:
        context = browser.new_context()
        page = context.new_page()
        
        if not login_to_facebook(page, email, password):
            log("Login failed", STATUS_ERROR)
            return
        
        # Create a list of tabs (pages) for processing targets efficiently
        tab_count = min(MAX_TABS, len(targets))
        tabs = [page]  # First tab is already created
        
        # Create the remaining tabs
        for _ in range(tab_count - 1):
            tabs.append(context.new_page())
        
        log(f"Initialized {len(tabs)} tabs for processing", STATUS_OK)
        
        # Create a queue to track tabs and their status
        tab_queue = deque([(i, tab) for i, tab in enumerate(tabs)])
        
        cycle = 1
        while RUNNING:
            log(f"\n--- Starting cycle {cycle} ---", STATUS_OK)
            
            for msg_idx, message in enumerate(messages):
                if not RUNNING: break
                
                log(f"\nUsing message {msg_idx+1}/{len(messages)}", STATUS_OK)
                
                # Create a list to keep track of processed targets
                processed_targets = set()
                
                # Process targets with available tabs
                while len(processed_targets) < len(targets) and RUNNING:
                    tab_idx, tab = tab_queue.popleft()
                    
                    # Find next unprocessed target
                    target_idx = 0
                    while target_idx < len(targets) and target_idx in processed_targets:
                        target_idx += 1
                    
                    if target_idx >= len(targets):
                        # All targets processed, put the tab back in queue
                        tab_queue.append((tab_idx, tab))
                        break
                    
                    log(f"Using tab {tab_idx+1} for target {target_idx+1}", STATUS_RETRY)
                    
                    # Process the target
                    success = process_target(tab, targets[target_idx], message, target_idx, msg_idx)
                    processed_targets.add(target_idx)
                    
                    # Put the tab back in the queue
                    tab_queue.append((tab_idx, tab))
                    
                    if success:
                        delay = get_random_delay(delays)
                        log(f"Waiting {delay} seconds before next target...", STATUS_OK)
                        time.sleep(delay)
            
            cycle += 1
            if cycle > 1 and RUNNING:
                log("\nCycle completed. Starting next...", STATUS_OK)
                time.sleep(get_random_delay(delays))
                
    except Exception as e:
        log(f"Fatal error: {e}", STATUS_ERROR)
        traceback.print_exc()
    finally:
        if browser:
            browser.close()
        if playwright:
            playwright.stop()
        log("Script ended", STATUS_OK)

if __name__ == "__main__":
    main()