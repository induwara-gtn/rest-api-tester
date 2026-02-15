# AI-Powered REST API Tester

An advanced, Swagger-driven API testing suite with a modern web UI. Features automated discovery, combinatorial testing, AI-powered logic verification (Gemini), and Jira integration.

## 🚀 Features

- **Auto-Discovery**: Fetches endpoints directly from OpenAPI/Swagger specs.
- **Combinatorial Testing**: Generates exhaustive test cases for parameter combinations.
- **AI Logic Verification**: Uses Google Gemini to verify complex business logic (sorting, filtering).
- **Jira Integration**: Scope tests based on Jira task IDs/URLs.
- **Visual Reporting**: Real-time results with request/response previews.

## ❌ GitHub Pages Compatibility

This application **cannot** be hosted on GitHub Pages bcause it requires a Python backend (`Flask`) to execute the testing logic and proxy API requests. GitHub Pages only supports static sites (HTML/CSS/JS).

You must run this application locally or deploy it to a platform that supports Python (e.g., Heroku, Render, AWS, Google Cloud Run).

## 🛠️ Local Setup Guide

Follow these steps to run the application on your personal machine.

### Prerequisites
- [Python 3.8+](https://www.python.org/downloads/)
- [Git](https://git-scm.com/downloads)

### 1. Clone the Repository
```bash
git clone https://github.com/induwara-gtn/rest-api-tester.git
cd rest-api-tester
```

### 2. Create a Virtual Environment (Recommended)
```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# Mac/Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configuration
1.  Copy the example config file:
    ```bash
    cp config.example.json config.json
    # On Windows: copy config.example.json config.json
    ```
2.  Open `config.json` and fill in your details:
    *   `gemini_api_key`: Your Google Gemini API Key.
    *   `services`: List of API services to test (Name, URL, Auth Token).
    *   `jira_...`: Jira credentials for scoping (optional).

### 5. Run the Application
```bash
python app.py
```
The server will start at `http://127.0.0.1:5000`.

## 📖 Usage

1.  Open your browser to `http://127.0.0.1:5000`.
2.  **Select an Endpoint**: Choose from the sidebar list (grouped by service).
3.  **Configure Parameters**: Use the UI to set values, enable "Multi" mode for combinations, or "Fuzz" for random testing.
4.  **Run Tests**: Click "Run Test" or use "Jira Scoping" to auto-select relevant tests.
5.  **Analyze Results**: View the breakdown of Baseline, Auth, Combinatorial, and Fuzz tests below.

## 🤝 Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## License

[MIT](https://choosealicense.com/licenses/mit/)
