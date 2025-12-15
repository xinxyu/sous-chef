from flask import Flask, request, jsonify
from recipe_scrapers import scrape_me
from flask_cors import CORS
import logging

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
        recipe_data = {
            'title': scraper.title(),
            'total_time': scraper.total_time(),
            'yields': scraper.yields(),
            'ingredients': scraper.ingredients(),
            'instructions': scraper.instructions_list(),
            'image': scraper.image(),
            'host': scraper.host(),
            'nutrients': scraper.nutrients() if hasattr(scraper, 'nutrients') else None,
        }
        
        return jsonify(recipe_data), 200
        
    except Exception as e:
        logger.error(f"Error scraping recipe: {str(e)}")
        return jsonify({'error': f'Failed to scrape recipe: {str(e)}'}), 500


if __name__ == '__main__':
    # Run API backend on 4100 so an Angular dev server can use 4200
    app.run(debug=True, host='0.0.0.0', port=4100)

