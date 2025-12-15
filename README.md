# sous-chef
A meal planning and recipe app

# Features
1. Recipe scraper - scrape a recipe from a website to remove the ads and get a list of instructions and ingredients
2. Grocery list maker - creates a grocery list from recipes

## Recipe Scraper Setup

### Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

### Running the App

1. Start the Flask server:
```bash
python app.py
```

2. Open your browser and navigate to:
```
http://localhost:5000
```

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
