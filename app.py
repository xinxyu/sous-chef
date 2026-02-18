from flask import Flask, request, jsonify, session
from recipe_scrapers import scrape_me
from flask_cors import CORS
import logging
import requests
from bs4 import BeautifulSoup
import re
import json
import os
from datetime import datetime
import uuid
import hashlib
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
CORS(app, supports_credentials=True)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Storage files
RECIPES_FILE = 'saved_recipes.json'
USERS_FILE = 'users.json'


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
                if isinstance(data, dict):
                    recipe_data = data
                elif isinstance(data, list):
                    # Find the Recipe object in the list
                    recipe_data = next((item for item in data if item.get('@type') == 'Recipe'), {})
                
                if recipe_data.get('@type') == 'Recipe' and 'recipeIngredient' in recipe_data:
                    ingredients_raw = recipe_data['recipeIngredient']
                    if isinstance(ingredients_raw, list):
                        # Handle both string and object formats
                        processed_ingredients = []
                        for ing in ingredients_raw:
                            if isinstance(ing, str):
                                processed_ingredients.append(ing.strip())
                            elif isinstance(ing, dict):
                                # Some sites structure ingredients as objects
                                # Try to combine quantity, unit, and name
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
    try:
        data = request.get_json()
        url = data.get('url') if data else request.form.get('url')
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        logger.info(f"Scraping recipe from: {url}")
        
        # Scrape the recipe
        scraper = scrape_me(url, wild_mode=True)
        
        # Extract recipe data
        ingredients = scraper.ingredients()
        logger.info(f"recipe-scrapers found {len(ingredients) if ingredients else 0} ingredients")
        
        # If ingredients are empty or missing, try fallback parsing
        if not ingredients or len(ingredients) == 0:
            logger.warning(f"No ingredients found by recipe-scrapers, trying fallback parser")
            ingredients = fallback_parse_ingredients(url)
            if ingredients:
                logger.info(f"Fallback parser successfully extracted {len(ingredients)} ingredients")
            else:
                logger.warning(f"Fallback parser also failed to find ingredients")
        else:
            logger.info(f"Using {len(ingredients)} ingredients from recipe-scrapers")
        
        recipe_data = {
            'title': scraper.title(),
            'total_time': scraper.total_time(),
            'yields': scraper.yields(),
            'ingredients': ingredients,
            'instructions': scraper.instructions_list(),
            'image': scraper.image(),
            'host': scraper.host(),
            'nutrients': scraper.nutrients() if hasattr(scraper, 'nutrients') else None,
            'source_url': url,
        }
        
        return jsonify(recipe_data), 200
        
    except Exception as e:
        logger.error(f"Error scraping recipe: {str(e)}")
        return jsonify({'error': f'Failed to scrape recipe: {str(e)}'}), 500


# User management functions
def load_users():
    """Load users from file."""
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading users: {e}")
            return {}
    return {}

def save_users(users):
    """Save users to file."""
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(users, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Error saving users: {e}")
        return False

def hash_password(password):
    """Hash a password using SHA256."""
    return hashlib.sha256(password.encode()).hexdigest()

def get_current_user_id():
    """Get the current logged-in user ID from session."""
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


# Recipe storage functions (per-user)
def load_recipes():
    """Load saved recipes from file, organized by user."""
    if os.path.exists(RECIPES_FILE):
        try:
            with open(RECIPES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading recipes: {e}")
            return {}
    return {}

def save_recipes(recipes):
    """Save recipes to file."""
    try:
        with open(RECIPES_FILE, 'w', encoding='utf-8') as f:
            json.dump(recipes, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Error saving recipes: {e}")
        return False


# Authentication endpoints
@app.route('/auth/register', methods=['POST'])
def register():
    """Register a new user."""
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        email = data.get('email', '').strip()
        
        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400
        
        if len(username) < 3:
            return jsonify({'error': 'Username must be at least 3 characters'}), 400
        
        if len(password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400
        
        users = load_users()
        
        # Check if username already exists
        if username in users:
            return jsonify({'error': 'Username already exists'}), 400
        
        # Create new user
        user_id = str(uuid.uuid4())
        users[username] = {
            'id': user_id,
            'username': username,
            'email': email,
            'password_hash': hash_password(password),
            'created_at': datetime.now().isoformat(),
        }
        
        if save_users(users):
            # Auto-login after registration
            session['user_id'] = user_id
            session['username'] = username
            logger.info(f"Registered new user: {username}")
            return jsonify({
                'message': 'User registered successfully',
                'user': {
                    'id': user_id,
                    'username': username,
                    'email': email,
                }
            }), 201
        else:
            return jsonify({'error': 'Failed to save user'}), 500
            
    except Exception as e:
        logger.error(f"Error registering user: {str(e)}")
        return jsonify({'error': f'Failed to register user: {str(e)}'}), 500


@app.route('/auth/login', methods=['POST'])
def login():
    """Login a user."""
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        
        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400
        
        users = load_users()
        
        if username not in users:
            return jsonify({'error': 'Invalid username or password'}), 401
        
        user = users[username]
        password_hash = hash_password(password)
        
        if user['password_hash'] != password_hash:
            return jsonify({'error': 'Invalid username or password'}), 401
        
        # Set session
        session['user_id'] = user['id']
        session['username'] = username
        
        logger.info(f"User logged in: {username}")
        return jsonify({
            'message': 'Login successful',
            'user': {
                'id': user['id'],
                'username': username,
                'email': user.get('email'),
            }
        }), 200
            
    except Exception as e:
        logger.error(f"Error logging in: {str(e)}")
        return jsonify({'error': f'Failed to login: {str(e)}'}), 500


@app.route('/auth/logout', methods=['POST'])
def logout():
    """Logout the current user."""
    session.clear()
    return jsonify({'message': 'Logout successful'}), 200


@app.route('/auth/me', methods=['GET'])
def get_current_user():
    """Get the current logged-in user."""
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({'user': None}), 200
    
    users = load_users()
    username = session.get('username')
    
    if username and username in users:
        user = users[username]
        return jsonify({
            'user': {
                'id': user['id'],
                'username': username,
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
        
        # Add timestamp and user_id
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
        
        recipes = load_recipes()
        
        # Initialize user's recipe list if needed
        if user_id not in recipes:
            recipes[user_id] = {}
        
        recipes[user_id][recipe_id] = recipe_data
        
        if save_recipes(recipes):
            logger.info(f"Saved recipe {recipe_id} for user {user_id}")
            return jsonify(recipe_data), 201
        else:
            return jsonify({'error': 'Failed to save recipe'}), 500
            
    except Exception as e:
        logger.error(f"Error saving recipe: {str(e)}")
        return jsonify({'error': f'Failed to save recipe: {str(e)}'}), 500


@app.route('/recipes', methods=['GET'])
@require_auth
def list_recipes():
    """Get all saved recipes for the current user."""
    try:
        user_id = get_current_user_id()
        recipes = load_recipes()
        
        # Get recipes for current user
        user_recipes = recipes.get(user_id, {})
        
        # Return as list sorted by saved_at (most recent first)
        recipe_list = list(user_recipes.values())
        recipe_list.sort(key=lambda x: x.get('saved_at', ''), reverse=True)
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
        recipes = load_recipes()
        
        user_recipes = recipes.get(user_id, {})
        if recipe_id in user_recipes:
            return jsonify(user_recipes[recipe_id]), 200
        else:
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
        recipes = load_recipes()
        
        if user_id in recipes and recipe_id in recipes[user_id]:
            del recipes[user_id][recipe_id]
            if save_recipes(recipes):
                logger.info(f"Deleted recipe {recipe_id} for user {user_id}")
                return jsonify({'message': 'Recipe deleted successfully'}), 200
            else:
                return jsonify({'error': 'Failed to save after deletion'}), 500
        else:
            return jsonify({'error': 'Recipe not found'}), 404
    except Exception as e:
        logger.error(f"Error deleting recipe: {str(e)}")
        return jsonify({'error': f'Failed to delete recipe: {str(e)}'}), 500


if __name__ == '__main__':
    # Run API backend on 4100 so an Angular dev server can use 4200
    app.run(debug=True, host='0.0.0.0', port=4100)

