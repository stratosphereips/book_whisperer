import os
import logging
import argparse
import sqlite3
from datetime import date
from dotenv import load_dotenv
import requests
from requests.auth import HTTPDigestAuth
from rich.console import Console
from rich.table import Table
import openai

CACHE_DB = 'books_cache.db'


def configure_logging(debug: bool):
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    return logging.getLogger(__name__)


def load_credentials():
    load_dotenv()
    base_url = os.getenv("CALIBRE_URL")
    user = os.getenv("CALIBRE_USER")
    password = os.getenv("CALIBRE_PASS")
    library = os.getenv("CALIBRE_LIBRARY", "Calibre_Library")
    openai.api_key = os.getenv("OPENAI_API_KEY")
    if not (base_url and user and password and openai.api_key):
        raise ValueError("Please set CALIBRE_URL, CALIBRE_USER, CALIBRE_PASS, and OPENAI_API_KEY in .env")
    return base_url.rstrip('/'), user, password, library


def init_db():
    conn = sqlite3.connect(CACHE_DB)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS books (
            id TEXT PRIMARY KEY,
            title TEXT,
            author TEXT,
            topic TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS recommendations (
            rec_date TEXT PRIMARY KEY,
            book_id TEXT
        )
    ''')
    conn.commit()
    return conn


def get_cached_ids(conn):
    cur = conn.cursor()
    cur.execute('SELECT id FROM books')
    return {row[0] for row in cur.fetchall()}


def load_cached_books(conn):
    cur = conn.cursor()
    cur.execute('SELECT id, title, author, topic FROM books')
    return [
        {'id': row[0], 'title': row[1], 'author': row[2], 'topic': row[3]}
        for row in cur.fetchall()
    ]


def save_books(conn, books, logger):
    cur = conn.cursor()
    logger.debug("Clearing cached books table")
    cur.execute('DELETE FROM books')
    logger.debug(f"Inserting {len(books)} books into cache")
    for b in books:
        cur.execute(
            'INSERT INTO books (id, title, author, topic) VALUES (?, ?, ?, ?)',
            (b['id'], b['title'], b['author'], b['topic'])
        )
    conn.commit()


def fetch_book_ids(session, base_url, library, logger):
    url = f"{base_url}/ajax/search"
    params = {'library_id': library, 'pattern': '', 'start': 0, 'num': 10000}
    logger.debug(f"GET {url} params={params}")
    resp = session.get(url, params=params)
    resp.raise_for_status()
    data = resp.json()
    return [str(bid) for bid in (data.get('book_ids') or [])]


def fetch_books(session, base_url, library, logger, ids):
    books = []
    for bid in ids:
        detail_url = f"{base_url}/ajax/book/{bid}/{library}"
        resp = session.get(detail_url)
        try:
            resp.raise_for_status()
            info = resp.json()
            title = info.get('title', f"Book {bid}")
            authors = info.get('authors') or []
            author = ', '.join(authors) if isinstance(authors, list) else str(authors)
            tags = info.get('tags') or []
            topic = ', '.join(tags) if isinstance(tags, list) else str(tags)
            books.append({'id': bid, 'title': title, 'author': author, 'topic': topic})
        except Exception:
            logger.exception(f"Error loading details for {bid}")
    return books


def get_or_create_recommendation(conn, books, logger):
    today = date.today().isoformat()
    cur = conn.cursor()
    cur.execute('SELECT book_id FROM recommendations WHERE rec_date = ?', (today,))
    row = cur.fetchone()
    if row:
        rec_id = row[0]
        logger.info(f"Loaded existing recommendation for {today}: {rec_id}")
    else:
        prompt_books = "\n".join(
            [f"{b['id']}: {b['title']} by {b['author']} [{b['topic']}]" for b in books]
        )
        prompt = (
            f"You are a helpful book recommender. Given today's date {today} and the following list of books:\n"
            f"{prompt_books}\n"
            "Choose one book ID to recommend to the user today. Reply with the ID only."
        )
        try:
            # Updated for openai>=1.0.0
            response = openai.chat.completions.create(
                model='gpt-3.5-turbo',
                messages=[
                    {'role': 'system', 'content': 'You recommend books.'},
                    {'role': 'user', 'content': prompt}
                ]
            )
            rec_id = response.choices[0].message.content.strip()
            logger.info(f"AI recommended book ID {rec_id}")
        except Exception as e:
            logger.error(f"OpenAI recommendation error: {e}")
            rec_id = books[0]['id'] if books else None
        if rec_id:
            cur.execute(
                'INSERT OR REPLACE INTO recommendations (rec_date, book_id) VALUES (?, ?)',
                (today, rec_id)
            )
            conn.commit()
    return next((b for b in books if b['id'] == rec_id), None)


def display_books_table(books, recommendation=None):
    console = Console()
    if recommendation:
        console.print(
            f"[bold yellow]Today's recommendation:[/] {recommendation['title']} by {recommendation['author']}"
        )
    table = Table(title="Calibre Library Books")
    table.add_column("ID", justify="right", style="dim")
    table.add_column("Title", style="bold cyan")
    table.add_column("Author", style="green")
    table.add_column("Topic", style="magenta")
    if not books:
        console.print("[bold red]No books to display.[/bold red]")
        return
    for b in books:
        table.add_row(b['id'], b['title'], b['author'], b['topic'])
    console.print(table)


def main():
    parser = argparse.ArgumentParser(
        description="Fetch and list Calibre books in the console."
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable DEBUG logging output"
    )
    args = parser.parse_args()

    logger = configure_logging(args.debug)
    base_url, user, password, library = load_credentials()
    session = requests.Session()
    session.auth = HTTPDigestAuth(user, password)
    session.headers.update({'Accept': 'application/json'})

    conn = init_db()
    try:
        remote_ids = fetch_book_ids(
            session, base_url, library, logger
        )
        cached_ids = get_cached_ids(conn)
        if set(remote_ids) == cached_ids:
            logger.info("No change in book list; loading from cache")
            books = load_cached_books(conn)
        else:
            logger.info("Book list changed; fetching details and updating cache")
            books = fetch_books(
                session, base_url, library, logger, remote_ids
            )
            save_books(conn, books, logger)
        rec = get_or_create_recommendation(conn, books, logger)
        display_books_table(books, recommendation=rec)
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    main()
