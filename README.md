# 📚 Calibre Book Recommender

Welcome to **Calibre Book Recommender**, a command-line tool that fetches your Calibre library catalog and suggests what to read next using various methods like TF-IDF, fuzzy matching, or query-based similarity, and can return multiple recommendations at once.

---

## 🎯 Purpose

- Automatically recommend daily reading from your Calibre library 📖
- Avoid recommending the same book twice until every book has been suggested 🔄
- Support thematic searches (e.g., `-r fantasy`) and fuzzy title matching 🧙‍♂️
- Return top **X** recommendations in one go 📋
- Lightweight: pure Python, SQLite for caching, no heavy dependencies by default 🐍

---

## 🚀 Features

- **TF-IDF**-based content similarity (default) 📝
- **Fuzzy title matching** using FuzzyWuzzy 🔍
- **Query-based TF-IDF** similarity for custom search strings ✏️
- Return **top X** recommendations with `-x` 📊
- Local **SQLite** cache of book metadata and history 🗄️
- Rich console output with **Rich** tables 🌈
- CLI flags for listing, recommending, clearing history, and debugging ⚙️

---

## 🛠️ Installation

1. Clone this repo:
   ```bash
   git clone git@github.com:stratosphereips/book_whisperer.git
   cd book_whisperer
   ```
2. Create and activate a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Create a `.env` in the project root with your Calibre server info and (optionally) OpenAI key:
   ```dotenv
   CALIBRE_URL=http://xx.xx.xx.xx:8081
   CALIBRE_USER=your_user
   CALIBRE_PASS=your_pass

   # OPENAI_API_KEY=sk-... (if using OpenAI method)
   ```

---

## 🎛️ Usage

```bash
# List all books
./book_wisperer.py -l

# Recommend 1 book (TF-IDF default)
./book_wisperer.py

# Recommend 3 books using TF-IDF
./book_wisperer.py -x 3

# Recommend a book with a search term
./book_wisperer.py -r mystery

# Recommend top 2 for 'fantasy'
./book_wisperer.py -r fantasy -x 2

# Use fuzzy title-matching
./book_wisperer.py -m fuzzy -r 'python'

# Use query-based TF-IDF explicitly
./book_wisperer.py -m query -r 'deep learning'

# Debug mode: show internal logs
./book_wisperer.py -d

# Clear recommendation history
./book_wisperer.py -c
```

---

## 📖 Parameters

| Flag                | Alias        | Description                                                                                   |
|---------------------|--------------|-----------------------------------------------------------------------------------------------|
| `-l`, `--list`      | N/A          | List all books in a formatted table                                                          |
| `-r`, `--recommend` | N/A          | Recommend books; optionally provide a query string                                            |
| `-m`, `--method`    | N/A          | Choose method: `tfidf` (default), `fuzzy`, or `query`                                         |
| `-x`, `--top`       | N/A          | Number of top recommendations to return (default: 1)                                          |
| `-c`, `--clear`     | N/A          | Clear all past recommendation history                                                        |
| `-d`, `--debug`     | N/A          | Enable debug logging                                                                         |

---

## 💡 Examples

1. **Daily reading recommendation** (TF-IDF default):
   ```bash
   ./book_wisperer.py
   # Library contains 659 books.
   # Top 1 recommendation today:
   #  - The Hobbit by J.R.R. Tolkien 🧝‍♂️
   ```

2. **Top 5 thematic picks**:
   ```bash
   ./book_wisperer.py -r sci-fi -x 5
   # Top 5 for 'sci-fi':
   #  - Dune by Frank Herbert 🚀
   #  - Neuromancer by William Gibson 🧠
   #  - Foundation by Isaac Asimov 📚
   #  - Ender's Game by Orson Scott Card 🛰️
   #  - Snow Crash by Neal Stephenson 🏙️
   ```

3. **Fuzzy title match**:
   ```bash
   ./book_wisperer.py -m fuzzy -r 'python'
   # Recommended for 'python':
   #  - Advanced Guide to Python 3 Programming by John Hunt 🐍
   ```

4. **Clear recommendation history**:
   ```bash
   ./book_wisperer.py -c
   🔄 Recommendation history cleared.
   ```

---

## 🔄 Caching Behavior

- **Books metadata**: cached locally in `books_cache.db`, refreshed only when the library list changes.
- **Recommendations history**: stored to avoid repeats until every book has been suggested.

---

## 🎉 Contribute

Feel free to open issues or PRs! Your feedback and enhancements are welcome. ✨

---

© 2025 eldraco. Built with ❤️ and Python.


