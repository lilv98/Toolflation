# Copyright 2026 The Toolflation Authors
# SPDX-License-Identifier: Apache-2.0

"""Instagram: public accounts as targets, Apify Instagram actors as tools."""
from ..grading import first, integer, is_url, text

SEARCH, KEYWORDS = 'instagram', ('instagram',)
NOUN, TARGET = 'Instagram', 'account'
IDENTITY = 'account username as shown on Instagram'
PRIVATE = ('email', 'phone', 'fbid', 'address')
PRICE_EXEMPT = None
JUDGE_NOTE = ('"Posts" or "post data" on its own claims nothing; count a latest_post field only when the listing names that '
              'post attribute (post URL or link, caption, likes, comments). ')
ALIASES = {
    'username': ['username', 'ownerUsername', 'owner_username', 'user_name', 'handle'],
    'full_name': ['fullName', 'full_name', 'Full Name', 'ownerFullName', 'name'],
    'followers_count': ['followersCount', 'followerCount', 'followers_count', 'follower_count', 'Followers Count', 'followers'],
    'following_count': ['followsCount', 'followingCount', 'following_count', 'follows_count', 'Following Count', 'following'],
    'posts_count': ['postsCount', 'postCount', 'posts_count', 'post_count', 'mediaCount', 'media_count', 'Total Posts'],
    'biography': ['biography', 'Biography', 'bio'],
    'external_url': ['external_url', 'externalUrl', 'External URL', 'bio_link', 'website'],
    'is_verified': ['verified', 'isVerified', 'is_verified'],
    'category': ['businessCategoryName', 'business_category_name', 'category_name', 'categoryName', 'Category', 'category'],
    'latest_post_url': ['post_url', 'postUrl', 'permalink', 'url', 'link'],
    'latest_post_caption': ['caption', 'caption_text', 'text'],
    'latest_post_likes': ['likeCount', 'like_count', 'likesCount', 'likes_count', 'likes'],
    'latest_post_comments': ['commentCount', 'comment_count', 'commentsCount', 'comments_count', 'comments'],
}
POST_KEYS = ('shortcode', 'shortCode', 'code', 'post_url', 'postUrl', 'likeCount', 'like_count', 'commentCount', 'comment_count')
PROFILE = ('username', 'full_name', 'followers_count', 'following_count', 'posts_count', 'biography', 'external_url', 'is_verified', 'category')
CAP = {}


def question(target, field):
    return f"For the Instagram account @{target['username']}, what is its {field['ask']}?"


def profile_url(target):
    return f"https://www.instagram.com/{target['username']}/"


def canonical(record):
    """Profile fields come from the record or its nested owner/user object; post fields from the record when it is a post,
    else from its first listed post. A follower-list row is its own (non-target) account."""
    owner = record.get('owner') or record.get('user') or {}
    flat = {**(owner if isinstance(owner, dict) else {}), **record}
    if isinstance(flat.get('Account'), str) and 'username' not in flat:
        flat['username'] = flat['Account'].rstrip('/').rsplit('/', 1)[-1]
    posts = record.get('latestPosts') or record.get('latest_posts') or record.get('posts')
    post = record if any(k in record for k in POST_KEYS) else (posts[0] if isinstance(posts, list) and posts and isinstance(posts[0], dict) else {})
    row = {field: first(flat if field in PROFILE else post, keys) for field, keys in ALIASES.items()}
    row['latest_post_caption'] = row['latest_post_caption'] or flat.get('Post 1')
    if isinstance(row['latest_post_caption'], dict):
        row['latest_post_caption'] = row['latest_post_caption'].get('text')
    code = first(post, ['shortcode', 'shortCode', 'code'])
    if not is_url(row['latest_post_url']) and code:
        row['latest_post_url'] = f'https://www.instagram.com/p/{code}/'
    if isinstance(row['is_verified'], str):
        row['is_verified'] = {'true': True, 'false': False}.get(row['is_verified'].casefold())
    return row


def is_target(row, target):
    return str(row['username'] or '').strip().lstrip('@').casefold() == target['username'].casefold()


def delivered(field, value):
    if value in (None, '', [], {}) or (isinstance(value, str) and value.strip().upper() in ('N/A', 'NONE', 'NULL')):
        return False
    if field in ('followers_count', 'following_count', 'posts_count'):
        return integer(value, 0, 1e10)
    if field in ('latest_post_likes', 'latest_post_comments'):
        return integer(value, 1, 1e10)  # some tools emit 0 for counts they could not read
    if field == 'is_verified':
        return isinstance(value, bool)
    if field in ('external_url', 'latest_post_url'):
        return is_url(value) and (field == 'external_url' or 'instagram.com/' in value)
    return text(value)  # full_name, biography, category, latest_post_caption


# Matrix inputs: each builder looks one account up by username (or profile URL when the schema wants URLs) and asks for
# the smallest paid amount the schema allows; contact extraction stays off.
BUILDERS = {
    'scraping_solutions/instagram-scraper-followers-following-no-cookies': lambda t: {
        'Account': [t['username']], 'resultsLimit': 50, 'dataToScrape': 'Followers'},
    'data-slayer/instagram-post-details': lambda t: {'postUrls': [profile_url(t)]},
    'instagram-scraper/fast-instagram-post-scraper': lambda t: {'instagramUsernames': [t['username']], 'postsPerProfile': 5},
    'apidojo/instagram-scraper': lambda t: {'startUrls': [profile_url(t)], 'maxItems': 3},
    'apple_yang/instagram-transcripts-scraper': lambda t: {'usernames': [t['username']], 'resultsLimit': 3},
    'sones/instagram-posts-scraper-lowcost': lambda t: {'usernames': [t['username']], 'postsPerProfile': 3},
    'datadoping/instagram-followers-scraper': lambda t: {'usernames': [t['username']], 'max_count': 50},
    'afanasenko/instagram-profile-scraper': lambda t: {
        'operationMode': 'analyzeSpecificAccounts', 'specificUsernamesList': [t['username']], 'maxCountList': 1,
        'extractEmail': False, 'extractPhoneNumber': False, 'extractWebsiteUrl': True, 'extractBusinessCategory': True,
        'extractPosts': True, 'analyzeQuality': True},
    'coderx/instagram-profile-scraper-bio-posts': lambda t: {'usernames': [t['username']]},
    'patient_discovery/instagram-search-reels': lambda t: {'query': t['username'], 'maxPages': 1},
}
