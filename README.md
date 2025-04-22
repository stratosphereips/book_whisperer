# 📚 Calibre Book Recommender

Welcome to **Calibre Book Recommender**, a command-line tool that fetches your Calibre library catalog and suggests what to read next, using either TF-IDF similarity or (future) AI methods.

---

## 🎯 Purpose

- Automatically recommend daily reading from your Calibre library 📖
- Avoid recommending the same book twice until every book has been suggested 🔄
- Support fuzzy thematic searches (e.g., `-r fantasy`) 🧙‍♂️
- Lightweight: pure Python, SQLite for caching, no heavy dependencies by default 🐍

---

## 🚀 Features

- **TF-IDF**-based content similarity (default method) 📝
- Optional **OpenAI**-powered recommendations (if configured) 🤖
- Local **SQLite** cache of book metadata and history 🗄️
- Rich console output with **Rich** tables 🌈
- CLI flags for listing, recommending, and debugging ⚙️

---

## 🛠️ Installation

1. Clone this repo:
   ```bash
   git clone git@github.com:stratosphereips/book_whisperer.git
   cd book_whisperer
   ```
2. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. Create a `.env` in the root with your Calibre server info and (optionally) OpenAI key:
   ```dotenv
   # Calibre Web
   CALIBRE_URL=http://xx.xx.xx.xx:8081
   CALIBRE_USER=your_user
   CALIBRE_PASS=your_pass

   # OpenAI (optional)
   OPENAI_API_KEY=sk-...yourkey...
   ```

---

## 🎛️ Usage

```bash
# List all books
./book_wisperer.py -l

# Recommend a book based on TF-IDF (default)
./book_wisperer.py

# Recommend only (no count/list)
./book_wisperer.py -r

# Recommend based on a query (e.g. 'fantasy')
./book_wisperer.py -r fantasy

# Debug mode: show internal logs
./book_wisperer.py -d

# Switch to OpenAI method (if configured)
./book_wisperer.py -m openai -r
```

---

## 📖 Parameters

| Flag            | Alias | Description                                           |
|-----------------|-------|-------------------------------------------------------|
| `-l`, `--list`  | N/A   | List all books in a table                             |
| `-r`, `--recommend` | N/A | Recommend a book. Optionally accept a query string (e.g., `-r mystery`) |
| `-m`, `--method`| N/A   | Choose `tfidf` (default) or `openai` methods          |
| `-d`, `--debug` | N/A   | Enable debug logging and prompt output                |

---

## 💡 Examples

1. **Daily reading recommendation** (TF-IDF default):
   ```bash
   ./book_wisperer.py
   # Library contains 659 books.
   Recommended today (tfidf): The Hobbit by J.R.R. Tolkien 🧝‍♂️
   ```

2. **Themed suggestion**:
   ```bash
   ./book_wisperer.py -r sci-fi
   # Recommended for 'sci-fi': Dune by Frank Herbert 🚀
   ```

3. **Listing all books**:
   ```bash
   ./book_wisperer.py -l
   # Prints a colorful table of IDs, Titles, Authors, Topics.
   ```

---

## 🔄 Caching Behavior

- **Books metadata** is cached locally in `books_cache.db` and refreshed only when the library list changes.
- **Recommendations history** is stored to avoid repeating until all books have been suggested.

---

## 🎉 Contribute

Feel free to open issues or PRs! Your feedback and enhancements are welcome. ✨

---

© 2025 eldraco. Built with ❤️  and Python.


