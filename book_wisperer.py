import os
import logging
import argparse
from dotenv import load_dotenv
import requests
from requests.auth import HTTPDigestAuth
from rich.console import Console
from rich.table import Table


def configure_logging(debug: bool):
    """
    Configure logging level and format.
    """
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    return logging.getLogger(__name__)


def load_credentials():
    """
    Load Calibre Content Server credentials and settings from a .env file.

    Expected variables:
      - CALIBRE_URL: the base URL, e.g. http://host:port
      - CALIBRE_USER: HTTP Auth username
      - CALIBRE_PASS: HTTP Auth password
      - CALIBRE_LIBRARY: library identifier, e.g. Calibre_Library
    """
    load_dotenv()
    base_url = os.getenv("CALIBRE_URL")
    user = os.getenv("CALIBRE_USER")
    password = os.getenv("CALIBRE_PASS")
    library = os.getenv("CALIBRE_LIBRARY", "Calibre_Library")
    if not base_url or not user or not password:
        raise ValueError("Please set CALIBRE_URL, CALIBRE_USER, and CALIBRE_PASS in .env")
    return base_url.rstrip('/'), user, password, library


def fetch_books(session, base_url, library, logger):
    """
    Fetch all book IDs via AJAX search, then fetch each book's details.
    Uses HTTP Digest authentication.
    Returns list of dicts: {'id', 'title', 'author', 'topic'}
    """
    # Step 1: get all book IDs
    search_url = f"{base_url}/ajax/search"
    params = {'library_id': library, 'pattern': '', 'start': 0, 'num': 10000}
    logger.debug(f"GET {search_url} params={params}")
    resp = session.get(search_url, params=params)
    logger.debug(f"Search status {resp.status_code}")
    resp.raise_for_status()
    data = resp.json()
    # 'book_ids' contains list of integer IDs
    book_ids = data.get('book_ids') or []
    logger.info(f"Found {len(book_ids)} book IDs")

    books = []
    # Step 2: fetch details for each ID
    for bid in book_ids:
        detail_url = f"{base_url}/ajax/book/{bid}/{library}"
        logger.debug(f"GET {detail_url}")
        resp2 = session.get(detail_url)
        logger.debug(f"Detail [{bid}] status {resp2.status_code}")
        try:
            resp2.raise_for_status()
            info = resp2.json()
            title = info.get('title', f"Book {bid}")
            # Authors list
            authors = info.get('authors') or []
            author = ', '.join(authors) if isinstance(authors, list) else str(authors)
            tags = info.get('tags') or []
            topic = ', '.join(tags) if isinstance(tags, list) else str(tags)
            books.append({'id': str(bid), 'title': title, 'author': author, 'topic': topic})
            logger.debug(f"Loaded book {bid}: {title} by {author} [{topic}]")
        except Exception as e:
            logger.exception(f"Error loading details for {bid}: {e}")
    return books


def display_books_table(books):
    """
    Display a list of books in a console table using Rich.
    """
    console = Console()
    table = Table(title="Calibre Library Books")
    table.add_column("ID", justify="right", style="dim")
    table.add_column("Title", style="bold cyan")
    table.add_column("Author", style="green")
    table.add_column("Topic", style="magenta")

    if not books:
        console.print("[bold red]No books found or failed to fetch.[/bold red]")
        return

    for b in books:
        table.add_row(b['id'], b['title'], b['author'], b['topic'])

    console.print(table)


def main():
    parser = argparse.ArgumentParser(description="Fetch and list Calibre books in the console.")
    parser.add_argument(
        "--debug", action="store_true", help="Enable DEBUG logging output"
    )
    args = parser.parse_args()

    logger = configure_logging(args.debug)

    try:
        base_url, user, password, library = load_credentials()
        session = requests.Session()
        session.auth = HTTPDigestAuth(user, password)
        session.headers.update({'Accept': 'application/json'})

        books = fetch_books(session, base_url, library, logger)
        display_books_table(books)
    except Exception as e:
        logger.critical(f"Fatal error: {e}")


if __name__ == '__main__':
    main()
