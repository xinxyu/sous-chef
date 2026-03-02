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
   The app uses cookie-based sessions (`withCredentials: true`). If the frontend and API are on different domains, set **`SESSION_COOKIE_SECURE=1`** in the backend environment so cookies use `SameSite=None; Secure` (HTTPS only). For local or mobile testing over **HTTP**, leave `SESSION_COOKIE_SECURE` unset so the session cookie can be stored; otherwise you’ll see “Authentication required” after login on mobile.

4. **Recipe scraping proxy (402/403 on deployed servers)**  
   Recipe sites often block cloud IPs. Set **`SCRAPING_PROXY`** to an HTTP proxy URL so scraping works when deployed. Example with [Bright Data](https://brightdata.com/): create a residential or datacenter proxy zone, then set:
   ```
   SCRAPING_PROXY=http://brd-customer-<customer_id>-zone-<zone_name>:<zone_password>@brd.superproxy.io:33335
   ```
   Use the host and port from your Bright Data zone. Bright Data’s **new** proxy port is **33335** (see [SSL certificate](https://docs.brightdata.com/general/account/ssl-certificate)).  
   **SSL (Bright Data) – no cert in code:** Either (1) **Install** Bright Data’s [CA certificate](https://docs.brightdata.com/general/account/ssl-certificate) on the server that runs the app (e.g. Linux: copy `ca.crt` to `/usr/local/share/ca-certificates/` and run `sudo update-ca-certificates`). Then the app uses the system trust store and no env var is needed. Or (2) set **`SCRAPING_CA_BUNDLE`** to a **path** to `ca.crt` or to the **PEM content** (paste the cert into your deployment’s env/secrets). Other providers (ScraperAPI, ZenRows) need only `SCRAPING_PROXY`. Leave both unset for local development.

   **DigitalOcean App Platform:** You can’t install system certs, so use env vars. In your App’s **Settings → App-Level Environment Variables** (or component env vars), add **`SCRAPING_PROXY`** as above and **`SCRAPING_CA_BUNDLE`** with the Bright Data CA. Either paste the full PEM (multi-line) into the value, or use a single-line base64 version: run `base64 -i ca.crt | tr -d '\n'` locally and set `SCRAPING_CA_BUNDLE` to that string.

### Mobile / same-network testing

To use the app on your phone while the dev servers run on your computer:

1. **Backend:** In `.env`, add your machine’s URL to CORS (e.g. `CORS_ORIGINS=http://192.168.1.5:4200`). Do **not** set `SESSION_COOKIE_SECURE` so the session cookie works over HTTP.
2. **Frontend:** Run the Angular dev server with `ng serve --host 0.0.0.0`, then on the phone open `http://YOUR_COMPUTER_IP:4200`. In development the app uses the current host for the API (e.g. `http://YOUR_COMPUTER_IP:4100` when opened from the phone), so no extra config is needed.
3. Log in on the phone; saved recipes and save should work once the session cookie is stored (see step 1).

### Email verification and password reset

- **Register** requires an email; new users get a verification link by email and cannot log in until they verify.
- **Verify email:** `GET /auth/verify-email?token=...` or `POST /auth/verify-email` with `{"token": "..."}`.
- **Forgot password:** `POST /auth/forgot-password` with `{"email": "..."}` sends a reset link.
- **Reset password:** `POST /auth/reset-password` with `{"token": "...", "new_password": "..."}` (or `password`).

Set **APP_BASE_URL** (or **FRONTEND_ORIGIN**) so verification and reset links point to your frontend (e.g. `https://your-app.vercel.app`). Set **RESEND_API_KEY** and **FROM_EMAIL** (e.g. `Sous Chef <onboarding@resend.dev>` for testing, or your verified domain) to send emails via [Resend](https://resend.com). Without Resend, registration and forgot-password still succeed but no email is sent (link is only logged).

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

## Testing

Tests use [pytest](https://docs.pytest.org/). Install dependencies (including pytest) from the project root, then run:

```bash
source ./venv/bin/activate
pip install -r requirements.txt
pytest test_fallback.py -v
```

- **Unit tests** (default): Mock HTTP so no network is used. They check that the fallback ingredient parser correctly extracts count and contents from HTML (e.g. JSON-LD recipe data).
- **Integration test**: One test hits the real AllRecipes URL; it is not run by default. To run it and see the summary (e.g. 1 passed):
  ```bash
  pytest test_fallback.py -m integration -v -s
  ```
  Omit `-m integration` to run only the fast, mocked unit tests.
