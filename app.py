from flask import Flask, request, jsonify, session
from recipe_scrapers import scrape_me
from flask_cors import CORS
import logging
import requests
from bs4 import BeautifulSoup
import re
import json
import os
import argparse
from datetime import datetime, timedelta
import uuid
import hashlib
import secrets
from functools import wraps
import jwt
import resend
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from dotenv import load_dotenv

# Load .env so DATABASE_URL, SECRET_KEY, etc. are available
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# CORS and session cookie: production (HTTPS) vs dev/mobile (HTTP)
_cors_origins = os.environ.get('CORS_ORIGINS', os.environ.get('FRONTEND_ORIGIN', ''))
_origins_list = [o.strip() for o in _cors_origins.split(',') if o.strip()]
_secure = os.environ.get('SESSION_COOKIE_SECURE', '').strip().lower() in ('1', 'true', 'yes')

if _secure:
    # Production HTTPS: restrict CORS to allowed frontend origin(s)
    if _origins_list:
        for origin in ('http://localhost:4200', 'http://127.0.0.1:4200'):
            if origin not in _origins_list:
                _origins_list.append(origin)
        CORS(app, supports_credentials=True, origins=_origins_list)
    else:
        CORS(app, supports_credentials=True)
    app.config['SESSION_COOKIE_SAMESITE'] = 'None'
    app.config['SESSION_COOKIE_SECURE'] = True
else:
    # Dev / mobile over HTTP: allow any origin so phone (e.g. http://192.168.x.x:4200) works
    # without adding it to CORS_ORIGINS. Session cookie is not Secure so browser stores it.
    CORS(app, supports_credentials=True)
    app.config['SESSION_COOKIE_SECURE'] = False
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Storage: PostgreSQL for recipes and users
DATABASE_URL = os.environ.get('DATABASE_URL')


def get_db_connection():
    """Return a DB connection. Requires DATABASE_URL to be set."""
    if not DATABASE_URL:
        raise RuntimeError('DATABASE_URL environment variable is required for recipe storage')
    return psycopg.connect(DATABASE_URL)


def init_db():
    """Create saved_recipes and users tables if they do not exist."""
    conn = get_db_connection()
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS saved_recipes (
                    user_id UUID NOT NULL,
                    recipe_id UUID NOT NULL,
                    saved_at TIMESTAMPTZ NOT NULL,
                    title TEXT,
                    data JSONB NOT NULL,
                    PRIMARY KEY (user_id, recipe_id)
                );
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_saved_recipes_user_saved_at
                ON saved_recipes (user_id, saved_at DESC);
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id UUID PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    email_verified BOOLEAN NOT NULL DEFAULT FALSE
                );
            """)
            # Add email_verified for existing DBs that had users table without it
            cur.execute("""
                DO $$
                BEGIN
                  IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = current_schema() AND table_name = 'users' AND column_name = 'email_verified'
                  ) THEN
                    ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT TRUE;
                  END IF;
                END $$;
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS email_verification_tokens (
                    token TEXT PRIMARY KEY,
                    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at TIMESTAMPTZ NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    token TEXT PRIMARY KEY,
                    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at TIMESTAMPTZ NOT NULL
                );
            """)
        conn.commit()
    finally:
        conn.close()


def fallback_parse_ingredients(url):
    """Fallback method to parse ingredients directly from HTML when recipe-scrapers fails."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        ingredients = []
        
        # Pattern 1: Look for JSON-LD structured data (most reliable - try first)
        json_scripts = soup.find_all('script', type='application/ld+json')
        for script in json_scripts:
            try:
                script_content = script.string
                if not script_content:
                    continue
                data = json.loads(script_content)
                recipe_data = None
                if isinstance(data, dict):
                    recipe_data = data
                elif isinstance(data, list):
                    # Find the Recipe object in the list (skip None items)
                    recipe_data = next(
                        (item for item in data if item is not None and isinstance(item, dict) and item.get('@type') == 'Recipe'),
                        None,
                    )
                if recipe_data is None or not isinstance(recipe_data, dict):
                    continue
                if recipe_data.get('@type') != 'Recipe' or 'recipeIngredient' not in recipe_data:
                    continue
                ingredients_raw = recipe_data['recipeIngredient']
                if not isinstance(ingredients_raw, list):
                    continue
                # Handle both string and object formats
                processed_ingredients = []
                for ing in ingredients_raw:
                    if ing is None:
                        continue
                    if isinstance(ing, str):
                        processed_ingredients.append(ing.strip())
                    elif isinstance(ing, dict):
                        # Some sites structure ingredients as objects
                        parts = []
                        if 'amount' in ing:
                            parts.append(str(ing['amount']))
                        if 'unit' in ing:
                            parts.append(str(ing['unit']))
                        if 'name' in ing:
                            parts.append(str(ing['name']))
                        elif 'ingredient' in ing:
                            parts.append(str(ing['ingredient']))
                        if parts:
                            processed_ingredients.append(' '.join(parts).strip())
                    else:
                        processed_ingredients.append(str(ing).strip())
                ingredients = [ing for ing in processed_ingredients if ing]
                if ingredients:
                    logger.info(f"Found {len(ingredients)} ingredients from JSON-LD")
                    break
            except (json.JSONDecodeError, KeyError, AttributeError, TypeError) as e:
                logger.debug(f"Error parsing JSON-LD: {e}")
                continue
        
        # Pattern 2: AllRecipes specific - data-ingredient-name attribute
        # Need to get the full text including quantity, not just the name
        if not ingredients:
            ingredient_elements = soup.find_all(['span', 'li'], {'data-ingredient-name': True})
            if ingredient_elements:
                for elem in ingredient_elements:
                    # Get the parent container to include quantity and ingredient name
                    parent = elem.find_parent('li')
                    if parent:
                        # Get full text from parent to include quantity, using space separator
                        ingredient_text = parent.get_text(separator=' ', strip=True)
                        # Clean up multiple spaces
                        ingredient_text = re.sub(r'\s+', ' ', ingredient_text).strip()
                    else:
                        # Fallback to element's own text
                        ingredient_text = elem.get_text(separator=' ', strip=True)
                        ingredient_text = re.sub(r'\s+', ' ', ingredient_text).strip()
                    if ingredient_text and len(ingredient_text) > 2:
                        ingredients.append(ingredient_text)
                if ingredients:
                    logger.info(f"Found {len(ingredients)} ingredients from data-ingredient-name")
        
        # Pattern 3: AllRecipes specific - ingredient list items with specific classes
        # Make sure we get the full list item text including quantities
        if not ingredients:
            # AllRecipes uses various class patterns - prioritize list items to get full text
            allrecipes_selectors = [
                'li.mntl-structured-ingredients__list-item',
                'li.ingredients-section__list-item',
                'li[data-testid="ingredient-item"]',
                '.mntl-structured-ingredients__list-item',
                '.ingredients-section__list-item',
                '[data-testid="ingredient-item"]',
                'li[data-ingredient-name]',
                'span[data-ingredient-name]',
            ]
            
            for selector in allrecipes_selectors:
                elements = soup.select(selector)
                if elements:
                    for elem in elements:
                        # If it's a span, try to get parent li for full text
                        if elem.name == 'span':
                            parent_li = elem.find_parent('li')
                            if parent_li:
                                text = parent_li.get_text(separator=' ', strip=True)
                            else:
                                text = elem.get_text(separator=' ', strip=True)
                        else:
                            text = elem.get_text(separator=' ', strip=True)
                        
                        # Clean up multiple spaces
                        text = re.sub(r'\s+', ' ', text).strip()
                        
                        # Filter out empty or very short text
                        if text and len(text) > 2:
                            ingredients.append(text)
                    if ingredients:
                        logger.info(f"Found {len(ingredients)} ingredients using selector: {selector}")
                        break
        
        # Pattern 4: Common ingredient list selectors (for other sites)
        # Ensure we get full text including quantities
        if not ingredients:
            selectors = [
                'li.ingredients-item',
                'li.ingredient',
                'li[itemprop="recipeIngredient"]',
                '.recipe-ingredients li',
                '.ingredients-list li',
                'ul.ingredients li',
                'div.ingredients li',
                'li.ingredient',
                '.ingredients-item',
                '.ingredient',
                '[itemprop="recipeIngredient"]',
            ]
            
            for selector in selectors:
                elements = soup.select(selector)
                if elements:
                    for elem in elements:
                        # Get full text with separator to combine nested elements
                        if elem.name == 'li':
                            text = elem.get_text(separator=' ', strip=True)
                        else:
                            # For non-li elements, try to get parent li or use element text
                            parent_li = elem.find_parent('li')
                            if parent_li:
                                text = parent_li.get_text(separator=' ', strip=True)
                            else:
                                text = elem.get_text(separator=' ', strip=True)
                        
                        # Filter out empty or very short text
                        if text and len(text) > 2:
                            ingredients.append(text)
                    if ingredients:
                        logger.info(f"Found {len(ingredients)} ingredients using selector: {selector}")
                        break
        
        # Pattern 5: Look for ingredients section by heading (AllRecipes specific)
        # This should capture full ingredient text including measurements
        if not ingredients:
            # Find the "Ingredients" heading and get the list after it
            headings = soup.find_all(['h2', 'h3'], string=re.compile(r'ingredients', re.I))
            for heading in headings:
                # Look for the next list after the heading
                next_elem = heading.find_next_sibling()
                while next_elem and len(ingredients) == 0:
                    if next_elem.name == 'ul' or (next_elem.name == 'div' and next_elem.find('ul')):
                        list_container = next_elem if next_elem.name == 'ul' else next_elem.find('ul')
                        # Get direct children li elements first (most reliable)
                        list_items = list_container.find_all('li', recursive=False)
                        if not list_items:
                            # Fallback to all li elements
                            list_items = list_container.find_all('li', recursive=True)
                        
                        for li in list_items:
                            # Get full text including any nested spans/divs with space separator
                            text = li.get_text(separator=' ', strip=True)
                            # Clean up multiple spaces
                            text = re.sub(r'\s+', ' ', text).strip()
                            if text and len(text) > 2:
                                # Skip if this looks like just a number or very short
                                if not re.match(r'^[\d\s/]+$', text) and len(text) > 5:
                                    ingredients.append(text)
                        if ingredients:
                            logger.info(f"Found {len(ingredients)} ingredients from heading-based search")
                            break
                    next_elem = next_elem.find_next_sibling()
                if ingredients:
                    break
        
        # Pattern 6: Look for ingredients in common HTML structures (last resort)
        if not ingredients:
            # Find sections that might contain ingredients
            ingredient_sections = soup.find_all(['section', 'div'], class_=re.compile(r'ingredient', re.I))
            for section in ingredient_sections:
                list_items = section.find_all('li')
                for li in list_items:
                    text = li.get_text(strip=True)
                    if text and len(text) > 2:
                        # Basic validation: ingredient should have some substance
                        if not re.match(r'^[^\w]*$', text):  # Not just punctuation
                            ingredients.append(text)
        
        logger.info(f"Fallback parser found {len(ingredients)} ingredients")
        return ingredients
        
    except Exception as e:
        logger.error(f"Error in fallback ingredient parsing: {str(e)}")
        return []


@app.route('/scrape', methods=['POST'])
def scrape_recipe():
    """Scrape a recipe from the given URL."""
    data = request.get_json()
    url = data.get('url') if data else request.form.get('url')
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    logger.info(f"Scraping recipe from: {url}")

    try:
        scraper = scrape_me(url, wild_mode=True)
        ingredients = scraper.ingredients()
        if ingredients is None or not isinstance(ingredients, list):
            ingredients = []
        logger.info(f"recipe-scrapers found {len(ingredients)} ingredients")

        if not ingredients:
            logger.warning("No ingredients from recipe-scrapers, trying fallback parser")
            ingredients = fallback_parse_ingredients(url)
            if ingredients:
                logger.info(f"Fallback parser extracted {len(ingredients)} ingredients")

        instructions = scraper.instructions_list()
        if instructions is None or not isinstance(instructions, list):
            instructions = []
        recipe_data = {
            'title': scraper.title() or '',
            'total_time': scraper.total_time(),
            'yields': scraper.yields() or '',
            'ingredients': ingredients,
            'instructions': instructions,
            'image': scraper.image() or '',
            'host': scraper.host() or '',
            'nutrients': scraper.nutrients() if hasattr(scraper, 'nutrients') and scraper.nutrients() else None,
            'source_url': url,
        }
        return jsonify(recipe_data), 200

    except Exception as e:
        logger.warning(f"recipe-scrapers failed ({e}), trying fallback parser only")
        try:
            ingredients = fallback_parse_ingredients(url)
            recipe_data = {
                'title': '',
                'total_time': None,
                'yields': '',
                'ingredients': ingredients or [],
                'instructions': [],
                'image': '',
                'host': '',
                'nutrients': None,
                'source_url': url,
            }
            return jsonify(recipe_data), 200
        except Exception as fallback_e:
            logger.error(f"Error scraping recipe: {fallback_e}")
            return jsonify({'error': f'Failed to scrape recipe: {str(fallback_e)}'}), 500


# User management (PostgreSQL)
def db_get_user_by_username(username):
    """Return user dict (id, username, email, password_hash, created_at) or None."""
    conn = get_db_connection()
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, username, email, password_hash, created_at, email_verified FROM users WHERE username = %s",
                (username,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def db_get_user_by_id(user_id):
    """Return user dict or None."""
    conn = get_db_connection()
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, username, email, password_hash, created_at, email_verified FROM users WHERE id = %s",
                (user_id,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def db_get_user_by_email(email):
    """Return user dict or None. Email match is case-insensitive."""
    if not email or not email.strip():
        return None
    conn = get_db_connection()
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, username, email, password_hash, created_at, email_verified FROM users WHERE LOWER(TRIM(email)) = LOWER(TRIM(%s))",
                (email,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def db_create_user(user_id, username, email, password_hash, created_at, email_verified=False):
    """Insert a new user. Raises on duplicate username."""
    conn = get_db_connection()
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO users (id, username, email, password_hash, created_at, email_verified)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (user_id, username, email or None, password_hash, created_at, email_verified),
            )
        conn.commit()
        return True
    finally:
        conn.close()


def db_set_user_email_verified(user_id, verified=True):
    """Set email_verified for a user."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET email_verified = %s WHERE id = %s", (verified, user_id))
        conn.commit()
    finally:
        conn.close()


def db_create_verification_token(user_id, expires_in_hours=24):
    """Create a verification token; returns (token, expires_at)."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now() + __timedelta_hours(expires_in_hours)
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO email_verification_tokens (token, user_id, expires_at) VALUES (%s, %s, %s)",
                (token, user_id, expires_at),
            )
        conn.commit()
        return token, expires_at
    finally:
        conn.close()


def db_consume_verification_token(token):
    """If token is valid, return user_id and delete token; else return None."""
    conn = get_db_connection()
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT user_id FROM email_verification_tokens WHERE token = %s AND expires_at > NOW()",
                (token,),
            )
            row = cur.fetchone()
        if not row:
            return None
        user_id = row["user_id"]
        with conn.cursor() as cur:
            cur.execute("DELETE FROM email_verification_tokens WHERE token = %s", (token,))
        conn.commit()
        return user_id
    finally:
        conn.close()


def db_create_password_reset_token(user_id, expires_in_hours=1):
    """Create a password reset token; returns (token, expires_at)."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now() + __timedelta_hours(expires_in_hours)
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO password_reset_tokens (token, user_id, expires_at) VALUES (%s, %s, %s)",
                (token, user_id, expires_at),
            )
        conn.commit()
        return token, expires_at
    finally:
        conn.close()


def db_consume_password_reset_token(token):
    """If token is valid, return user_id and delete token; else return None."""
    conn = get_db_connection()
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT user_id FROM password_reset_tokens WHERE token = %s AND expires_at > NOW()",
                (token,),
            )
            row = cur.fetchone()
        if not row:
            return None
        user_id = row["user_id"]
        with conn.cursor() as cur:
            cur.execute("DELETE FROM password_reset_tokens WHERE token = %s", (token,))
        conn.commit()
        return user_id
    finally:
        conn.close()


def db_update_password(user_id, new_password_hash):
    """Update a user's password."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (new_password_hash, user_id))
        conn.commit()
    finally:
        conn.close()


def __timedelta_hours(hours):
    return timedelta(hours=hours)


def send_email(to_email, subject, body_text, body_html=None):
    """Send an email via Resend. Requires RESEND_API_KEY and FROM_EMAIL (e.g. 'Sous Chef <onboarding@resend.dev>')."""
    api_key = os.environ.get('RESEND_API_KEY')
    from_email = os.environ.get('FROM_EMAIL', 'Sous Chef <onboarding@resend.dev>')
    if not api_key:
        logger.warning("RESEND_API_KEY not set; skipping send_email.")
        return False
    try:
        resend.api_key = api_key
        params = {
            "from": from_email,
            "to": [to_email],
            "subject": subject,
            "text": body_text,
        }
        if body_html:
            params["html"] = body_html
        resend.Emails.send(params)
        logger.info(f"Email sent to {to_email} ({subject})")
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False


def hash_password(password):
    """Hash a password using SHA256."""
    return hashlib.sha256(password.encode()).hexdigest()


# JWT auth (works on mobile without cookies; optional fallback to session)
_JWT_SECRET = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
_JWT_ALGORITHM = 'HS256'
_JWT_EXPIRY_DAYS = int(os.environ.get('JWT_EXPIRY_DAYS', '7'))


def _encode_jwt(user_id: str) -> str:
    """Return a JWT containing user_id and exp."""
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(days=_JWT_EXPIRY_DAYS),
        'iat': datetime.utcnow(),
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


def _decode_jwt(token: str):
    """Decode and verify JWT; return payload dict or None."""
    try:
        return jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
    except Exception:
        return None


def get_current_user_id():
    """Get the current user ID from Authorization Bearer token or session."""
    auth = request.headers.get('Authorization')
    if auth and auth.startswith('Bearer '):
        token = auth[7:].strip()
        payload = _decode_jwt(token)
        if payload:
            return payload.get('user_id')
    return session.get('user_id')

def require_auth(f):
    """Decorator to require authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function


# Recipe storage (PostgreSQL Option A: user_id, recipe_id, saved_at, title columns + data JSONB)
def db_get_recipes_for_user(user_id):
    """Return list of recipe dicts for user, sorted by saved_at desc."""
    conn = get_db_connection()
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT recipe_id, saved_at, title, data FROM saved_recipes WHERE user_id = %s ORDER BY saved_at DESC",
                (user_id,),
            )
            rows = cur.fetchall()
        out = []
        for row in rows:
            recipe = dict(row["data"])
            recipe["id"] = str(row["recipe_id"])
            recipe["user_id"] = user_id
            recipe["saved_at"] = row["saved_at"].isoformat() if hasattr(row["saved_at"], "isoformat") else row["saved_at"]
            if row.get("title") is not None:
                recipe["title"] = row["title"]
            out.append(recipe)
        return out
    finally:
        conn.close()


def db_get_recipe(user_id, recipe_id):
    """Return one recipe dict or None."""
    conn = get_db_connection()
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT recipe_id, saved_at, title, data FROM saved_recipes WHERE user_id = %s AND recipe_id = %s",
                (user_id, recipe_id),
            )
            row = cur.fetchone()
        if not row:
            return None
        recipe = dict(row["data"])
        recipe["id"] = str(row["recipe_id"])
        recipe["user_id"] = user_id
        recipe["saved_at"] = row["saved_at"].isoformat() if hasattr(row["saved_at"], "isoformat") else row["saved_at"]
        if row.get("title") is not None:
            recipe["title"] = row["title"]
        return recipe
    finally:
        conn.close()


def db_save_recipe(user_id, recipe_id, recipe_data):
    """Insert or update one recipe. recipe_data is the full recipe dict (stored in data JSONB)."""
    saved_at = recipe_data.get("saved_at")
    if isinstance(saved_at, str):
        try:
            saved_at = datetime.fromisoformat(saved_at.replace("Z", "+00:00"))
        except ValueError:
            saved_at = datetime.now()
    elif saved_at is None:
        saved_at = datetime.now()
    title = recipe_data.get("title")
    conn = get_db_connection()
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO saved_recipes (user_id, recipe_id, saved_at, title, data)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id, recipe_id)
                DO UPDATE SET saved_at = EXCLUDED.saved_at, title = EXCLUDED.title, data = EXCLUDED.data
                """,
                (user_id, recipe_id, saved_at, title, Jsonb(recipe_data)),
            )
        conn.commit()
        return True
    finally:
        conn.close()


def db_delete_recipe(user_id, recipe_id):
    """Delete one recipe. Returns True if a row was deleted."""
    conn = get_db_connection()
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "DELETE FROM saved_recipes WHERE user_id = %s AND recipe_id = %s",
                (user_id, recipe_id),
            )
        conn.commit()
        return True
    finally:
        conn.close()


# Authentication endpoints
@app.route('/auth/register', methods=['POST'])
def register():
    """Register a new user. Requires email verification before login."""
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        email = (data.get('email') or '').strip()
        
        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400
        if not email:
            return jsonify({'error': 'Email is required for registration'}), 400
        if len(username) < 3:
            return jsonify({'error': 'Username must be at least 3 characters'}), 400
        if len(password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400
        
        if db_get_user_by_username(username):
            return jsonify({'error': 'Username already exists'}), 400
        if db_get_user_by_email(email):
            return jsonify({'error': 'An account with this email already exists'}), 400
        
        user_id = str(uuid.uuid4())
        created_at = datetime.now()
        password_hash = hash_password(password)
        try:
            db_create_user(user_id, username, email, password_hash, created_at, email_verified=False)
        except Exception as e:
            if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
                return jsonify({'error': 'Username already exists'}), 400
            logger.error(f"Failed to create user: {e}")
            return jsonify({'error': 'Failed to save user'}), 500
        
        # Create verification token and send email
        token, _ = db_create_verification_token(user_id, expires_in_hours=24)
        base_url = (os.environ.get('APP_BASE_URL') or os.environ.get('FRONTEND_ORIGIN') or 'http://localhost:4200').rstrip('/')
        verify_url = f"{base_url}/verify-email?token={token}"
        body_text = f"Hi {username},\n\nPlease verify your email by opening this link:\n{verify_url}\n\nThe link expires in 24 hours."
        body_html = f"<p>Hi {username},</p><p>Please <a href=\"{verify_url}\">verify your email</a>.</p><p>The link expires in 24 hours.</p>"
        send_email(email, "Verify your email - Sous Chef", body_text, body_html)
        
        logger.info(f"Registered new user: {username} (pending verification)")
        return jsonify({
            'message': 'Registration successful. Please check your email to verify your account before logging in.',
            'email_sent': True,
        }), 201
    except Exception as e:
        logger.error(f"Error registering user: {str(e)}")
        return jsonify({'error': f'Failed to register user: {str(e)}'}), 500


@app.route('/auth/login', methods=['POST'])
def login():
    """Login a user. Rejects unverified accounts."""
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        
        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400
        
        user = db_get_user_by_username(username)
        if not user:
            return jsonify({'error': 'Invalid username or password'}), 401
        
        if not user.get('email_verified', True):
            return jsonify({'error': 'Please verify your email before logging in. Check your inbox for the verification link.'}), 403
        
        password_hash = hash_password(password)
        if user['password_hash'] != password_hash:
            return jsonify({'error': 'Invalid username or password'}), 401
        
        session['user_id'] = str(user['id'])
        session['username'] = user['username']
        token = _encode_jwt(str(user['id']))
        logger.info(f"User logged in: {username}")
        return jsonify({
            'message': 'Login successful',
            'user': {
                'id': str(user['id']),
                'username': user['username'],
                'email': user.get('email'),
            },
            'token': token,
        }), 200
    except Exception as e:
        logger.error(f"Error logging in: {str(e)}")
        return jsonify({'error': f'Failed to login: {str(e)}'}), 500


@app.route('/auth/logout', methods=['POST'])
def logout():
    """Logout the current user."""
    session.clear()
    return jsonify({'message': 'Logout successful'}), 200


@app.route('/auth/verify-email', methods=['GET', 'POST'])
def verify_email():
    """Verify email using token from link. GET ?token=... or POST {"token": "..."}."""
    token = request.args.get('token') or (request.get_json() or {}).get('token')
    if not token:
        return jsonify({'error': 'Verification token is required'}), 400
    user_id = db_consume_verification_token(token)
    if not user_id:
        return jsonify({'error': 'Invalid or expired verification link. You may request a new one by registering again.'}), 400
    db_set_user_email_verified(user_id, True)
    logger.info(f"Email verified for user_id={user_id}")
    return jsonify({'message': 'Email verified. You can now log in.'}), 200


@app.route('/auth/forgot-password', methods=['POST'])
def forgot_password():
    """Send a password reset link to the given email."""
    data = request.get_json() or {}
    email = (data.get('email') or '').strip()
    if not email:
        return jsonify({'error': 'Email is required'}), 400
    user = db_get_user_by_email(email)
    if not user:
        return jsonify({'message': 'If an account exists with this email, you will receive a reset link.'}), 200
    token, _ = db_create_password_reset_token(user['id'], expires_in_hours=1)
    base_url = (os.environ.get('APP_BASE_URL') or os.environ.get('FRONTEND_ORIGIN') or 'http://localhost:4200').rstrip('/')
    reset_url = f"{base_url}/reset-password?token={token}"
    body_text = f"Hi {user['username']},\n\nReset your password by opening this link:\n{reset_url}\n\nThe link expires in 1 hour."
    body_html = f"<p>Hi {user['username']},</p><p><a href=\"{reset_url}\">Reset your password</a>.</p><p>The link expires in 1 hour.</p>"
    send_email(email, "Reset your password - Sous Chef", body_text, body_html)
    return jsonify({'message': 'If an account exists with this email, you will receive a reset link.'}), 200


@app.route('/auth/reset-password', methods=['POST'])
def reset_password():
    """Set new password using token from email link."""
    data = request.get_json() or {}
    token = (data.get('token') or '').strip() or request.args.get('token')
    new_password = (data.get('new_password') or data.get('password') or '').strip()
    if not token:
        return jsonify({'error': 'Reset token is required'}), 400
    if not new_password or len(new_password) < 6:
        return jsonify({'error': 'New password must be at least 6 characters'}), 400
    user_id = db_consume_password_reset_token(token)
    if not user_id:
        return jsonify({'error': 'Invalid or expired reset link. Please request a new one.'}), 400
    db_update_password(user_id, hash_password(new_password))
    logger.info(f"Password reset for user_id={user_id}")
    return jsonify({'message': 'Password updated. You can now log in with your new password.'}), 200


@app.route('/auth/me', methods=['GET'])
def get_current_user():
    """Get the current logged-in user."""
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({'user': None}), 200
    
    user = db_get_user_by_id(user_id)
    if user:
        return jsonify({
            'user': {
                'id': str(user['id']),
                'username': user['username'],
                'email': user.get('email'),
            }
        }), 200
    
    return jsonify({'user': None}), 200


# Recipe endpoints (now per-user)
@app.route('/recipes', methods=['POST'])
@require_auth
def save_recipe():
    """Save a recipe for the current user."""
    try:
        user_id = get_current_user_id()
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Recipe data is required'}), 400
        
        # Generate unique ID if not provided
        recipe_id = data.get('id') or str(uuid.uuid4())
        
        # Full recipe payload (stored in data JSONB; saved_at/title also in columns for Option A)
        recipe_data = {
            'id': recipe_id,
            'user_id': user_id,
            'title': data.get('title'),
            'total_time': data.get('total_time'),
            'yields': data.get('yields'),
            'ingredients': data.get('ingredients', []),
            'instructions': data.get('instructions', []),
            'image': data.get('image'),
            'host': data.get('host'),
            'nutrients': data.get('nutrients'),
            'source_url': data.get('source_url'),
            'saved_at': datetime.now().isoformat(),
        }
        
        db_save_recipe(user_id, recipe_id, recipe_data)
        logger.info(f"Saved recipe {recipe_id} for user {user_id}")
        return jsonify(recipe_data), 201
    except Exception as e:
        logger.error(f"Error saving recipe: {str(e)}")
        return jsonify({'error': f'Failed to save recipe: {str(e)}'}), 500


@app.route('/recipes', methods=['GET'])
@require_auth
def list_recipes():
    """Get all saved recipes for the current user (sorted by saved_at desc)."""
    try:
        user_id = get_current_user_id()
        recipe_list = db_get_recipes_for_user(user_id)
        return jsonify(recipe_list), 200
    except Exception as e:
        logger.error(f"Error listing recipes: {str(e)}")
        return jsonify({'error': f'Failed to list recipes: {str(e)}'}), 500


@app.route('/recipes/<recipe_id>', methods=['GET'])
@require_auth
def get_recipe(recipe_id):
    """Get a specific recipe by ID (only if it belongs to the current user)."""
    try:
        user_id = get_current_user_id()
        recipe = db_get_recipe(user_id, recipe_id)
        if recipe:
            return jsonify(recipe), 200
        return jsonify({'error': 'Recipe not found'}), 404
    except Exception as e:
        logger.error(f"Error getting recipe: {str(e)}")
        return jsonify({'error': f'Failed to get recipe: {str(e)}'}), 500


@app.route('/recipes/<recipe_id>', methods=['DELETE'])
@require_auth
def delete_recipe(recipe_id):
    """Delete a recipe by ID (only if it belongs to the current user)."""
    try:
        user_id = get_current_user_id()
        existing = db_get_recipe(user_id, recipe_id)
        if not existing:
            return jsonify({'error': 'Recipe not found'}), 404
        db_delete_recipe(user_id, recipe_id)
        logger.info(f"Deleted recipe {recipe_id} for user {user_id}")
        return jsonify({'message': 'Recipe deleted successfully'}), 200
    except Exception as e:
        logger.error(f"Error deleting recipe: {str(e)}")
        return jsonify({'error': f'Failed to delete recipe: {str(e)}'}), 500


# Ensure table exists when app loads (for both dev server and gunicorn)
if DATABASE_URL:
    try:
        init_db()
        logger.info("PostgreSQL saved_recipes table ready")
    except Exception as e:
        logger.warning("PostgreSQL init_db failed (table may already exist): %s", e)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run the sous-chef Flask API')
    parser.add_argument('-p', '--port', type=int, default=4100, help='Port to run on (default: 4100)')
    args = parser.parse_args()
    app.run(debug=True, host='0.0.0.0', port=args.port)

