#!/usr/bin/env python3
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
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

CACHE_DB = 'books_cache.db'


def configure_logging(debug: bool):
    level = logging.DEBUG if debug else logging.WARNING
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
        raise ValueError(
            "Please set CALIBRE_URL, CALIBRE_USER, CALIBRE_PASS, CALIBRE_LIBRARY, and OPENAI_API_KEY in .env"
        )
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
            rec_date TEXT,
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
    logger.debug("Clearing books cache")
    cur.execute('DELETE FROM books')
    logger.debug(f"Caching {len(books)} books")
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
        resp = session.get(f"{base_url}/ajax/book/{bid}/{library}")
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
            logger.exception(f"Failed loading details for {bid}")
    return books


def recommend_tfidf(books, past_ids, logger):
    # Prepare TF-IDF matrix
    docs = [f"{b['title']} {b['author']} {b['topic']}" for b in books]
    vectorizer = TfidfVectorizer(stop_words='english')
    X = vectorizer.fit_transform(docs)

    if past_ids:
        # Compute user profile vector by averaging past book vectors
        indices = [i for i, b in enumerate(books) if b['id'] in past_ids]
        profile = X[indices].mean(axis=0)
        profile = np.asarray(profile)
        sims = cosine_similarity(X, profile)
        sims = sims.flatten()
        # Exclude already recommended
        for i, b in enumerate(books):
            if b['id'] in past_ids:
                sims[i] = -1
        idx = int(sims.argmax())
    else:
        # No past, pick highest TF-IDF norm
        norms = np.asarray(X.power(2).sum(axis=1)).flatten()
        idx = int(norms.argmax())

    rec = books[idx]
    logger.info(f"TF-IDF recommended book ID {rec['id']}")
    return rec['id']


def ask_openai_recommendation_full(books, past_ids, logger, debug=False):
    lines = [
        f"{b['id']}: Title='{b['title']}' | Author='{b['author']}' | Topics='{b['topic']}'"
        for b in books
    ]
    books_str = "\n".join(lines)
    past_str = "\n".join(f"- {pid}" for pid in past_ids) if past_ids else "(none)"
    prompt = (
        f"You are a thoughtful book recommender assistant.\n"
        f"I have {len(books)} books in my library, listed as ID, Title, Author, and Topics:\n"
        f"{books_str}\n\n"
        f"I have already recommended these IDs in the past:\n{past_str}\n\n"
        "Please pick one book ID from the above that you have never recommended before and reply with that ID only."
    )
    if debug:
        logger.debug(f"OpenAI prompt:\n{prompt}")
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "Recommend books without repeating past suggestions."},
            {"role": "user", "content": prompt},
        ]
    )
    return resp.choices[0].message.content.strip()


def display_books_table(books):
    console = Console()
    table = Table(title="Calibre Library Books")
    table.add_column("ID", style="dim")
    table.add_column("Title", style="bold cyan")
    table.add_column("Author", style="green")
    table.add_column("Topic", style="magenta")
    for b in books:
        table.add_row(b['id'], b['title'], b['author'], b['topic'])
    console.print(table)


def main():
    parser = argparse.ArgumentParser(description="Calibre book recommender.")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging and prompt logging")
    parser.add_argument("--method", choices=["openai","tfidf"], default="openai", help="Recommendation method")
    parser.add_argument("--list-only", action="store_true", help="Only list books")
    parser.add_argument("--recommend-only", action="store_true", help="Only recommend a book")
    args = parser.parse_args()

    logger = configure_logging(args.debug)
    base_url, user, password, library = load_credentials()
    session = requests.Session()
    session.auth = HTTPDigestAuth(user, password)
    session.headers.update({'Accept': 'application/json'})

    conn = init_db()
    ids = fetch_book_ids(session, base_url, library, logger)
    if set(ids) == get_cached_ids(conn):
        books = load_cached_books(conn)
    else:
        books = fetch_books(session, base_url, library, logger, ids)
        save_books(conn, books, logger)

    console = Console()
    if args.list_only:
        display_books_table(books)
        conn.close()
        return

    # Get past recommendations to avoid repeats
    cur = conn.cursor()
    cur.execute('SELECT book_id FROM recommendations')
    past_ids = [r[0] for r in cur.fetchall()]

    if args.method == 'tfidf':
        rec_id = recommend_tfidf(books, past_ids, logger)
    else:
        rec_id = ask_openai_recommendation_full(books, past_ids, logger, args.debug)

    # Store today's recommendation
    today = date.today().isoformat()
    cur.execute(        'INSERT OR REPLACE INTO recommendations (rec_date, book_id) VALUES (?, ?)',
        (today, rec_id)
    )
    conn.commit()

    rec = next(b for b in books if b['id'] == rec_id)
    if not args.recommend_only:
        console.print(f"Library contains {len(books)} books.")
    console.print(f"[bold yellow]Recommended today ({args.method}):[/] {rec['title']} by {rec['author']}")

    conn.close()

if __name__ == "__main__":
    main()

