# Copyright 2026 The Toolflation Authors
# SPDX-License-Identifier: Apache-2.0

"""Amazon: products as targets, Apify Amazon actors as tools."""
import re

from ..grading import first, integer, is_url, number, text

SEARCH, KEYWORDS = 'amazon', ('amazon',)
NOUN, TARGET = 'Amazon', 'product'
IDENTITY = 'ASIN and product title as listed on Amazon'
PRIVATE = ('email', 'phone', 'reviewer', 'author', 'profile')
PRICE_EXEMPT = r'\bpric(e|es|ing)\b'  # a product field here, not a fee claim
JUDGE_NOTE = ('"Reviews" on its own means review texts and does not claim reviews_count or rating; count those only when the '
              'listing speaks of the number of reviews or ratings, or of the star rating. ')
ALIASES = {
    'asin': ['asin', 'ASIN', 'originalAsin'],
    'title': ['title', 'product_title', 'productName', 'product_name', 'name'],
    'price': ['price', 'product_price', 'currentPrice', 'current_price'],
    'rating': ['rating', 'stars', 'product_star_rating', 'star_rating', 'averageRating', 'average_rating'],
    'reviews_count': ['reviewsCount', 'reviews_count', 'review_count', 'reviewCount', 'product_num_ratings', 'ratingsCount', 'ratings_count', 'ratingsTotal'],
    'brand': ['brand', 'brandName', 'brand_name', 'manufacturer'],
    'bestseller_rank': ['bestseller_rank', 'best_sellers_rank', 'bestsellerRanks', 'bestSellersRank', 'bestsellers_rank', 'salesRank', 'sales_rank', 'bsr', 'position'],
    'availability': ['availability', 'inStockText', 'in_stock_text', 'stockStatus', 'stock_status', 'inStock', 'in_stock'],
    'seller': ['seller', 'sold_by', 'soldBy', 'seller_name', 'sellerName', 'business_name'],
    'category': ['category', 'categories', 'breadCrumbs', 'breadcrumbs', 'categoryName', 'category_name', 'bestseller_category'],
    'image_url': ['image_url', 'imageUrl', 'mainImage', 'main_image', 'thumbnailImage', 'image', 'product_photo', 'images', 'imageUrls'],
    'features': ['features', 'feature_bullets', 'featureBullets', 'bullet_points', 'bulletPoints', 'aboutThisItem', 'about_this_item'],
    'description': ['description', 'productDescription', 'product_description'],
    'specifications': ['specs', 'specifications', 'attributes', 'productOverview', 'product_overview', 'productDetails', 'product_details', 'technical_details', 'details'],
}
REVIEW_KEYS = ('reviewId', 'review_id', 'reviewUrl', 'verified_purchase', 'isVerifiedPurchase', 'helpfulVotes', 'helpful_count', 'body')
PRODUCT_KEYS = ('asin', 'productName', 'productUrl', 'product_name', 'url')
ASIN = re.compile(r'/(?:dp|gp/product)/([A-Z0-9]{10})')
CAP = {'automly/amazon-products-scraper---fast-efficient-with-sales-data': 0.25, 'powerai/amazon-product-search-scraper': 0.30,
       'junglee/amazon-bestsellers': 0.15}
LISTS = {'Electronics': 'https://www.amazon.com/Best-Sellers-Electronics/zgbs/electronics',
         'Home & Kitchen': 'https://www.amazon.com/Best-Sellers-Home-Kitchen/zgbs/home-garden',
         'Beauty': 'https://www.amazon.com/Best-Sellers-Beauty/zgbs/beauty',
         'Toys': 'https://www.amazon.com/Best-Sellers-Toys-Games/zgbs/toys-and-games',
         'PC & Video Games': 'https://www.amazon.com/Best-Sellers-Video-Games/zgbs/videogames',
         'Garden': 'https://www.amazon.com/Best-Sellers-Patio-Lawn-Garden/zgbs/lawn-garden'}


def question(target, field):
    return f"For the Amazon product with ASIN {target['asin']} ({target['title']}), what is its {field['ask']}?"


def product_url(target):
    return f"https://www.amazon.com/dp/{target['asin']}"


def money(value):
    """A price as a number: {'value': 37.99}, '$37.99' or 37.99."""
    if isinstance(value, dict):
        value = value.get('value', value.get('amount'))
    if isinstance(value, str):
        match = re.search(r'\d[\d,]*(\.\d+)?', value)
        value = float(match.group().replace(',', '')) if match else None
    return value


def canonical(record):
    """Map a provider record onto the shared field names.
    A review row describes the product only by ASIN, name and URL: its rating, title and images are the review's."""
    if any(k in record for k in REVIEW_KEYS):
        record = {k: v for k, v in record.items() if k in PRODUCT_KEYS}
    row = {field: first(record, keys) for field, keys in ALIASES.items()}
    url = first(record, ['url', 'product_url', 'productUrl', 'link'])
    if row['asin'] is None and isinstance(url, str) and ASIN.search(url):
        row['asin'] = ASIN.search(url).group(1)
    row['price'] = money(row['price'])
    if isinstance(row['rating'], str):
        row['rating'] = money(row['rating'])
    if isinstance(row['seller'], dict):
        row['seller'] = row['seller'].get('name')
    if isinstance(row['image_url'], list):
        row['image_url'] = row['image_url'][0]
    if isinstance(row['image_url'], dict):
        row['image_url'] = first(row['image_url'], ['url', 'link', 'hiRes', 'large', 'src'])
    return row


def is_target(row, target):
    return str(row['asin'] or '').strip().upper() == target['asin']


def delivered(field, value):
    """Is this value a real answer for the field?"""
    if value in (None, '', [], {}):
        return False
    if field == 'price':
        return number(value, 0.01, 1e6)
    if field == 'rating':
        return number(value, 0, 5)
    if field == 'reviews_count':
        return integer(value, 0, 1e8)
    if field == 'bestseller_rank':
        return integer(value, 1, 1e8) or (isinstance(value, (list, dict)) and bool(value)) or (isinstance(value, str) and any(c.isdigit() for c in value))
    if field == 'availability':
        return isinstance(value, bool) or text(value)
    if field == 'image_url':
        return is_url(value)
    if field in ('features', 'specifications', 'category'):
        return bool(value) if isinstance(value, (list, dict)) else text(value)
    return text(value)  # brand, seller, description


# Matrix inputs: product tools get the ASIN (or its product URL) and the smallest paid amount the schema allows; list
# crawlers get the best-seller list of the product's category; the seller-leads database gets the category name.
BUILDERS = {
    'junglee/amazon-bestsellers': lambda t: {'categoryUrls': [LISTS[t['category']]], 'maxItemsPerStartUrl': 20, 'depthOfCrawl': 1, 'detailedInformation': True},
    'automly/amazon-products-scraper---fast-efficient-with-sales-data': lambda t: {'asins': [t['asin']], 'fullDetails': True, 'marketplace': 'com'},
    'amazon-scraper/amazon-bestsellers-scraper': lambda t: {'urls': [LISTS[t['category']]], 'nextPage': False},
    'jdtpnjtp/amazon-reviews': lambda t: {'products': [t['asin']], 'country': 'us', 'maxReviewsPerAsin': 1},
    'santamaria-automations/amazon-search-scraper': lambda t: {'searchQueries': [t['asin']], 'country': 'US', 'maxResultsPerQuery': 5, 'maxPages': 1},
    'automation-lab/amazon-reviews-scraper': lambda t: {'asins': [t['asin']], 'marketplace': 'US', 'maxReviewsPerProduct': 1},
    'powerai/amazon-product-search-scraper': lambda t: {'query': t['asin'], 'maxResults': 20, 'geo': 'US'},
    'harvestlab/amazon-scraper': lambda t: {'productUrls': [product_url(t)], 'maxProducts': 1, 'fetchDetails': True},
    'xmiso_scrapers/eu-amazon-sellers-email-leads': lambda t: {'amazon_category': t['category'], 'seller_country': 'US', 'max_results': 5},
    'igolaizola/amazon-search': lambda t: {'search': f"https://www.amazon.com/s?k={t['asin']}", 'maxItems': 5},
}
