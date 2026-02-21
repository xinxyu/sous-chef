# sous-chef
A meal planning and recipe app

# Features
1. Recipe scraper - scrape a recipe from a website to remove the ads and get a list of instructions and ingredients
2. Grocery list maker - creates a grocery list from recipes

## Recipe Scraper Setup
### Virtual Environment Set Up

1. Create the environment
```bash
python -m venv venv
```

2. Activate the environment
```bash
source ./venv/bin/activate
```

### Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

### Data storage (PostgreSQL)

Recipes and users are stored in PostgreSQL:

- **saved_recipes**: Option A schema (`user_id`, `recipe_id`, `saved_at`, `title`, `data` JSONB).
- **users**: `id`, `username` (unique), `email`, `password_hash`, `created_at`.

1. Create a database, then put your connection URL in a **`.env`** file in the project root (the app loads it with `python-dotenv`):
   ```bash
   cp .env.example .env
   ```
   In `.env`, set:
   ```
   DATABASE_URL=postgresql://user:password@localhost:5432/sous_chef
   ```
   Replace `user`, `password`, and `sous_chef` with your PostgreSQL username, password, and database name. Optionally set `SECRET_KEY` for production.

2. (Optional) Migrate existing data from JSON files:
   ```bash
   python scripts/migrate_users_to_postgres.py    # users.json → users table
   python scripts/migrate_recipes_to_postgres.py  # saved_recipes.json → saved_recipes table
   ```

3. Start the app; the `users` and `saved_recipes` tables are created automatically if they don’t exist.

### Connecting frontend and backend (separate deployments)

When the Angular app is deployed on one host (e.g. Vercel) and the Python API on another (e.g. Railway, Render):

1. **Frontend (Angular)**  
   Keep the API URL out of the repo by using the **`API_URL`** env var at build time:
   - **Vercel:** In the project → Settings → Environment Variables, add `API_URL` = `https://your-python-api.railway.app` (your real backend URL). Set the build command to:
     ```bash
     node scripts/inject-api-url.js && ng build --configuration production
     ```
     (Or use the npm script: `npm run build:prod` and set Vercel’s build command to `npm run build:prod`.)
   - The repo only contains a placeholder (`__API_URL__`); the real URL is injected during the build from `API_URL`, so it is never committed.

2. **Backend (Python)**  
   Allow the frontend origin for CORS. Set in the backend’s environment (e.g. in Railway/Render dashboard):
   ```
   FRONTEND_ORIGIN=https://your-angular-app.vercel.app
   ```
   Or multiple origins, comma-separated:
   ```
   CORS_ORIGINS=https://app.vercel.app,https://www.yourapp.com
   ```

3. **Sessions / cookies**  
   The app uses cookie-based sessions (`withCredentials: true`). If the frontend and API are on different domains, ensure the backend sets cookies with `SameSite=None; Secure` and that the frontend is served over HTTPS so cookies are sent. Flask’s default session cookie may need tuning for cross-origin (e.g. `SESSION_COOKIE_SAMESITE`, `SESSION_COOKIE_SECURE`) in production.

### Running the App

1. Start the Flask server:
```bash
python app.py
```

2. Open your browser and navigate to:
```
http://localhost:4100
```
(The API runs on port 4100 so the Angular dev server can use 4200.)

3. Enter a recipe URL in the input field and click "Scrape Recipe"

### API Endpoint

You can also use the scraper programmatically via the API:

**POST** `/scrape`
- **Body (JSON):** `{"url": "https://example.com/recipe"}`
- **Response:** JSON object containing:
  - `title`: Recipe title
  - `total_time`: Total cooking time
  - `yields`: Number of servings
  - `ingredients`: List of ingredients
  - `instructions`: List of instruction steps
  - `image`: Recipe image URL
  - `host`: Source website
  - `nutrients`: Nutritional information (if available)

### Example Usage

```bash
curl -X POST http://localhost:5000/scrape \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.allrecipes.com/recipe/..."}'
```

### Supported Websites

The `recipe-scrapers` library supports many popular recipe websites including:
- AllRecipes
- Food Network
- BBC Good Food
- Serious Eats
- And many more...

See the [recipe-scrapers documentation](https://github.com/hhursev/recipe-scrapers) for a full list of supported sites.
