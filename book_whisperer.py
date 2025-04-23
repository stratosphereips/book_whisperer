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
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from fuzzywuzzy import fuzz, process

CACHE_DB = 'books_cache.db'

def configure_logging(debug: bool):
    level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    return logging.getLogger(__name__)

def load_calibre_credentials():
    load_dotenv()
    base_url = os.getenv("CALIBRE_URL")
    user = os.getenv("CALIBRE_USER")
    password = os.getenv("CALIBRE_PASS")
    library = os.getenv("CALIBRE_LIBRARY", "Calibre_Library")
    if not (base_url and user and password):
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
    cur.execute('''
        CREATE TABLE IF NOT EXISTS recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    return [str(bid) for bid in resp.json().get('book_ids') or []]

def fetch_books(session, base_url, library, logger, ids):
    books = []
    for bid in ids:
        resp = session.get(f"{base_url}/ajax/book/{bid}/{library}")
        resp.raise_for_status()
        info = resp.json()
        title = info.get('title', f"Book {bid}")
        authors = info.get('authors') or []
        author = ', '.join(authors)
        tags = info.get('tags') or []
        topic = ', '.join(tags)
        books.append({'id': bid, 'title': title, 'author': author, 'topic': topic})
    return books

def recommend_tfidf_top(books, past_ids, top_n, logger):
    docs = [f"{b['title']} {b['author']} {b['topic']}" for b in books]
    vectorizer = TfidfVectorizer(stop_words='english')
    X = vectorizer.fit_transform(docs)
    if past_ids:
        indices = [i for i, b in enumerate(books) if b['id'] in past_ids]
        profile = X[indices].mean(axis=0); profile = np.asarray(profile)
        sims = cosine_similarity(X, profile).flatten()
    else:
        sims = X.sum(axis=1).A1
    for i, b in enumerate(books):
        if b['id'] in past_ids:
            sims[i] = -1
    idxs = np.argsort(sims)[::-1][:top_n]
    rec_ids = [books[i]['id'] for i in idxs]
    logger.info(f"TF-IDF top{top_n} recommended IDs {rec_ids}")
    return rec_ids

def recommend_query_top(books, query, past_ids, top_n, logger):
    docs = [f"{b['title']} {b['author']} {b['topic']}" for b in books]
    vectorizer = TfidfVectorizer(stop_words='english')
    X = vectorizer.fit_transform(docs)
    q_vec = vectorizer.transform([query])
    sims = cosine_similarity(X, q_vec).flatten()
    for i, b in enumerate(books):
        if b['id'] in past_ids:
            sims[i] = -1
    idxs = np.argsort(sims)[::-1][:top_n]
    rec_ids = [books[i]['id'] for i in idxs]
    logger.info(f"Query-TFIDF top{top_n} '{query}' recommended IDs {rec_ids}")
    return rec_ids

def fuzzy_query_top(books, query, past_ids, top_n, logger):
    titles = [b['title'] for b in books]
    matches = process.extract(query, titles, scorer=fuzz.token_set_ratio, limit=top_n*3)
    rec_ids = []
    for title, score in matches:
        if score < 80:
            break
        idx = titles.index(title)
        b_id = books[idx]['id']
        if b_id not in past_ids:
            rec_ids.append(b_id)
        if len(rec_ids) >= top_n:
            break
    if not rec_ids:
        logger.warning(f"No fuzzy matches for '{query}', falling back to query TF-IDF")
        return recommend_query_top(books, query, past_ids, top_n, logger)
    logger.info(f"Fuzzy top{top_n} '{query}' recommended IDs {rec_ids}")
    return rec_ids

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
    parser.add_argument("-d","--debug",action="store_true",help="Enable debug logging")
    parser.add_argument("-m","--method",choices=["tfidf","fuzzy","query"],default="tfidf",help="Recommendation method")
    parser.add_argument("-l","--list",action="store_true",dest="list_only",help="Only list books")
    parser.add_argument("-r","--recommend",nargs="?",const="",dest="recommend_query",help="Recommend; optional query")
    parser.add_argument("-x","--top",type=int,default=1,help="Number of top recs")
    args = parser.parse_args()

    logger = configure_logging(args.debug)
    base_url, user, password, library = load_calibre_credentials()
    session = requests.Session(); session.auth = HTTPDigestAuth(user, password)
    session.headers.update({'Accept':'application/json'})

    conn = init_db()
    ids = fetch_book_ids(session, base_url, library, logger)
    if set(ids) == get_cached_ids(conn):
        books = load_cached_books(conn)
    else:
        books = fetch_books(session, base_url, library, logger, ids)
        save_books(conn, books, logger)

    if args.list_only:
        display_books_table(books)
        conn.close()
        return

    cur = conn.cursor(); cur.execute('SELECT book_id FROM recommendations')
    past_ids = [r[0] for r in cur.fetchall()]

    if args.method == "fuzzy":
        rec_ids = fuzzy_query_top(books, args.recommend_query or "", past_ids, args.top, logger)
    elif args.method == "query" and args.recommend_query:
        rec_ids = recommend_query_top(books, args.recommend_query, past_ids, args.top, logger)
    else:
        rec_ids = recommend_tfidf_top(books, past_ids, args.top, logger)

    today = date.today().isoformat()
    for rid in rec_ids:
        conn.execute('INSERT INTO recommendations (rec_date, book_id) VALUES (?,?)', (today, rid))
    conn.commit()

    console = Console()
    if args.recommend_query:
        console.print(f"[bold yellow]Top {args.top} for '{args.recommend_query}':[/]")
    else:
        console.print(f"[bold yellow]Top {args.top} recommendations today:[/]")
    for rid in rec_ids:
        rec = next(b for b in books if b['id']==rid)
        console.print(f" - {rec['title']} by {rec['author']}")

    conn.close()

if __name__=="__main__":
    main()
