import os
import logging
import sqlite3
from contextlib import contextmanager

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

# --- 1. Configuration Section ---
# Replace these values with your own.

# Get your bot token from @BotFather. It's a security best practice to use environment variables.
# On Linux/macOS: export BOT_TOKEN="YOUR_BOT_TOKEN_HERE"
# On Windows: set BOT_TOKEN="YOUR_BOT_TOKEN_HERE"
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError(
        "BOT_TOKEN environment variable not set. Please set it before running the bot."
    )

# Your Telegram user ID(s) who will be the admins of the bot.
# You can find your user ID using a bot like @userinfobot.
# Admins can add/remove other authorized users and list all links.
ADMIN_IDS = {123456789, 987654321}  # !!! REPLACE WITH YOUR ACTUAL ADMIN IDS !!!

DB_FILE = 'bot_data.db'

# --- 2. Logging Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- 3. Database Manager Class ---

class DatabaseManager:
    """A class to handle all interactions with the SQLite database."""

    def __init__(self, db_file: str):
        self.db_file = db_file
        self._setup_db()

    @contextmanager
    def _get_connection(self):
        """Provides a database connection with a context manager."""
        conn = sqlite3.connect(self.db_file)
        try:
            yield conn
        finally:
            conn.close()

    def _setup_db(self):
        """Initializes the necessary database tables."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS authorized_users (
                    user_id INTEGER PRIMARY KEY
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS invite_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    submitter_id INTEGER,
                    link TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
        logger.info("Database setup complete.")

    def add_authorized_user(self, user_id: int) -> bool:
        """Adds a user to the authorized list. Returns True if added, False if already exists."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT OR IGNORE INTO authorized_users (user_id) VALUES (?)', (user_id,))
            conn.commit()
            return cursor.rowcount > 0

    def remove_authorized_user(self, user_id: int) -> bool:
        """Removes a user from the authorized list. Returns True if removed, False otherwise."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM authorized_users WHERE user_id = ?', (user_id,))
            conn.commit()
            return cursor.rowcount > 0

    def is_authorized(self, user_id: int) -> bool:
        """Checks if a user is in the authorized list."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM authorized_users WHERE user_id = ?', (user_id,))
            return cursor.fetchone() is not None

    def get_authorized_users(self) -> list[int]:
        """Returns a list of all authorized user IDs."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM authorized_users')
            return [row[0] for row in cursor.fetchall()]

    def add_invite_link(self, submitter_id: int, link: str):
        """Adds a new invite link to the database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO invite_links (submitter_id, link) VALUES (?, ?)',
                (submitter_id, link)
            )
            conn.commit()
        logger.info(f"Link submitted by {submitter_id}: {link}")

    def get_all_links(self) -> list[tuple[int, str, str]]:
        """Returns all submitted links with submitter ID and timestamp."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT submitter_id, link, timestamp FROM invite_links ORDER BY timestamp DESC')
            return cursor.fetchall()

# --- 4. Global Objects & Helper Functions ---
db = DatabaseManager(DB_FILE)

def is_admin(user_id: int) -> bool:
    """Checks if a user is an admin."""
    return user_id in ADMIN_IDS

# --- 5. Bot Command Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command."""
    if update.message:
        await update.message.reply_text(
            "Hello! I am a bot for managing invite links. "
            "Admins can add/remove authorized users and view submitted links."
        )

async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin-only command to add a user to the authorized list."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        if update.message:
            await update.message.reply_text("You are not authorized to use this command.")
        return

    try:
        user_to_add = int(context.args[0])
        if db.add_authorized_user(user_to_add):
            await update.message.reply_text(
                f"User with ID `{user_to_add}` has been added to the authorized list.",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text(
                f"User with ID `{user_to_add}` is already in the authorized list.",
                parse_mode=ParseMode.MARKDOWN
            )
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: `/add_user <user_id>`", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Error in add_user: {e}", exc_info=True)
        await update.message.reply_text("An internal error occurred.")

async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin-only command to remove a user from the authorized list."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        if update.message:
            await update.message.reply_text("You are not authorized to use this command.")
        return

    try:
        user_to_remove = int(context.args[0])
        if db.remove_authorized_user(user_to_remove):
            await update.message.reply_text(
                f"User with ID `{user_to_remove}` has been removed from the authorized list.",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text(
                f"User with ID `{user_to_remove}` was not found in the authorized list.",
                parse_mode=ParseMode.MARKDOWN
            )
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: `/remove_user <user_id>`", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Error in remove_user: {e}", exc_info=True)
        await update.message.reply_text("An internal error occurred.")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin-only command to list all authorized users."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        if update.message:
            await update.message.reply_text("You are not authorized to use this command.")
        return

    try:
        users = db.get_authorized_users()
        if users:
            user_list = "\n".join([str(user) for user in users])
            await update.message.reply_text(
                f"Authorized users:\n```\n{user_list}\n```",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text("No authorized users found.")
    except Exception as e:
        logger.error(f"Error in list_users: {e}", exc_info=True)
        await update.message.reply_text("An internal error occurred.")

async def submit_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Allows authorized users to submit an invite link."""
    user_id = update.effective_user.id
    if not db.is_authorized(user_id):
        await update.message.reply_text(
            "You are not authorized to submit links. Please contact an admin."
        )
        return

    try:
        link = context.args[0]
        # Basic validation for a Telegram invite link
        if not link.startswith("https://t.me/joinchat/") and not link.startswith("https://t.me/+"):
            await update.message.reply_text("That doesn't look like a valid Telegram invite link.")
            return

        db.add_invite_link(user_id, link)
        await update.message.reply_text("Thank you! Your invite link has been submitted.")
    except IndexError:
        await update.message.reply_text("Usage: `/submit_link <invite_link>`", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Error in submit_link: {e}", exc_info=True)
        await update.message.reply_text("An internal error occurred.")

async def list_links(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin-only command to view all submitted links."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        if update.message:
            await update.message.reply_text("You are not authorized to use this command.")
        return

    try:
        links = db.get_all_links()
        if links:
            lines = []
            for submitter_id, link, timestamp in links:
                lines.append(f"- User ID: {submitter_id}\n  Link: {link}\n  Time: {timestamp}\n")
            # Avoid Markdown here to prevent formatting issues from link characters
            await update.message.reply_text(f"Submitted links:\n\n{''.join(lines)}")
        else:
            await update.message.reply_text("No links have been submitted yet.")
    except Exception as e:
        logger.error(f"Error in list_links: {e}", exc_info=True)
        await update.message.reply_text("An internal error occurred.")


# --- 6. Main function to run the bot ---

def main() -> None:
    """The main entry point of the bot application."""
    logger.info("Initializing bot...")

    # Initialize the database and add the first admin as an authorized user.
    # This simplifies the initial setup.
    for admin_id in ADMIN_IDS:
        if db.add_authorized_user(admin_id):
            logger.info(f"Admin user {admin_id} added to authorized list.")

    application = Application.builder().token(BOT_TOKEN).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add_user", add_user))
    application.add_handler(CommandHandler("remove_user", remove_user))
    application.add_handler(CommandHandler("list_users", list_users))
    application.add_handler(CommandHandler("submit_link", submit_link))
    application.add_handler(CommandHandler("list_links", list_links))

    logger.info("Bot is running. Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
