#!/usr/bin/env python3
"""Test script for the fallback ingredient parser."""

import sys
import logging
from app import fallback_parse_ingredients

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

if __name__ == '__main__':
    url = 'https://www.allrecipes.com/recipe/23431/to-die-for-fettuccine-alfredo/'
    if len(sys.argv) > 1:
        url = sys.argv[1]
    
    logger.info(f"Testing fallback parser with URL: {url}")
    ingredients = fallback_parse_ingredients(url)
    
    print(f"\nFound {len(ingredients)} ingredients:")
    for i, ing in enumerate(ingredients, 1):
        print(f"{i}. {ing}")
    
    if not ingredients:
        print("\nERROR: No ingredients found!")
        sys.exit(1)
    else:
        print("\nSUCCESS: Ingredients found!")
        sys.exit(0)
