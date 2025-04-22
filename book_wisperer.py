import os
import logging
import argparse
import sqlite3
from dotenv import load_dotenv
import requests
from requests.auth import HTTPDigestAuth
from rich.console import Console
from rich.table import Table

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
    if not base_url or not user or not password:
        raise ValueError("Please set CALIBRE_URL, CALIBRE_USER, and CALIBRE_PASS in .env")
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
    # Convert all IDs to strings for consistent comparison
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


def display_books_table(books):
    console = Console()
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
    parser = argparse.ArgumentParser(description="Fetch and list Calibre books in the console.")
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG logging output")
    args = parser.parse_args()

    logger = configure_logging(args.debug)
    base_url, user, password, library = load_credentials()
    session = requests.Session()
    session.auth = HTTPDigestAuth(user, password)
    session.headers.update({'Accept': 'application/json'})

    conn = init_db()
    try:
        remote_ids = fetch_book_ids(session, base_url, library, logger)
        cached_ids = get_cached_ids(conn)
        if set(remote_ids) == cached_ids:
            logger.info("No change in book list; loading from cache")
            books = load_cached_books(conn)
        else:
            logger.info("Book list changed; fetching details and updating cache")
            books = fetch_books(session, base_url, library, logger, remote_ids)
            save_books(conn, books, logger)
        display_books_table(books)
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    main()

