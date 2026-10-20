# Copyright 2026 The Toolflation Authors
# SPDX-License-Identifier: Apache-2.0

"""Offline checks: no model and no Apify calls. Needs the dataset in data/ (python -m toolflation.data).

python tests.py"""
import json
import os
import random
import re
import subprocess
import sys
import tempfile

import jsonschema

from toolflation import data, platforms
from toolflation.grading import classify, service_error
from toolflation.market import buyer_seed
from toolflation.server import ENDED, MAX_DESCRIPTION, UPDATE, fee_talk, rejection


def test_instagram_grading():
    ig = platforms.load('instagram')
    target = {'username': 'nasa'}
    profile = ig.canonical({'username': 'nasa', 'fullName': 'NASA', 'followersCount': 104351982, 'followsCount': 91, 'postsCount': 4926,
                            'biography': 'Making the impossible possible', 'external_url': 'https://www.nasa.gov', 'verified': True,
                            'businessCategoryName': None, 'latestPosts': [{'shortCode': 'DcOX3hWFiey', 'url': 'https://www.instagram.com/p/DcOX3hWFiey',
                                                                           'caption': 'With your powers combined', 'likesCount': 0, 'commentsCount': 0}]})
    assert ig.is_target(profile, target) and not ig.is_target({**profile, 'username': 'nasahubble'}, target)
    assert [f for f in ig.ALIASES if ig.delivered(f, profile[f])] == ['username', 'full_name', 'followers_count', 'following_count', 'posts_count',
                                                                       'biography', 'external_url', 'is_verified', 'latest_post_url', 'latest_post_caption']
    post = ig.canonical({'code': 'DcOX3hWFiey', 'caption': {'text': 'Hello'}, 'like_count': 574684, 'comment_count': 4363,
                         'user': {'username': 'nasa', 'full_name': 'NASA', 'is_verified': True}})
    assert ig.is_target(post, target) and post['latest_post_url'] == 'https://www.instagram.com/p/DcOX3hWFiey/' and post['latest_post_caption'] == 'Hello'
    assert ig.delivered('latest_post_likes', post['latest_post_likes']) and post['followers_count'] is None
    sheet = ig.canonical({'Account': 'https://instagram.com/nasa', 'Full Name': 'NASA', 'Followers Count': 104351982, 'Category': 'N/A', 'Post 1': 'Text'})
    assert ig.is_target(sheet, target) and sheet['latest_post_caption'] == 'Text' and not ig.delivered('category', sheet['category'])
    assert not ig.is_target(ig.canonical({'follower_of': 'nasa', 'username': 'someone', 'full_name': 'x'}), target)


def test_amazon_grading():
    am = platforms.load('amazon')
    target = {'asin': 'B0CHWRXH8B'}
    row = am.canonical({'asin': 'B0CHWRXH8B', 'title': 'AirPods Pro', 'price': {'value': 263.86, 'currency': '$'}, 'stars': 4.7, 'reviewsCount': 28781,
                        'brand': 'Apple', 'inStock': True, 'seller': {'name': 'Amazon.com'}, 'breadCrumbs': 'Electronics > Headphones',
                        'thumbnailImage': 'https://m.media-amazon.com/images/I/51NR.jpg', 'features': ['Rich audio'], 'attributes': [{'key': 'Color', 'value': 'White'}]})
    assert am.is_target(row, target) and row['price'] == 263.86 and row['seller'] == 'Amazon.com'
    assert [f for f in am.ALIASES if am.delivered(f, row[f])] == ['asin', 'title', 'price', 'rating', 'reviews_count', 'brand', 'availability', 'seller',
                                                                  'category', 'image_url', 'features', 'specifications']
    parsed = am.canonical({'product_price': '$1,263.86', 'product_star_rating': '4.7', 'url': 'https://www.amazon.com/dp/B0CHWRXH8B?ref=x'})
    assert (parsed['price'], parsed['rating'], parsed['asin']) == (1263.86, 4.7, 'B0CHWRXH8B')
    review = am.canonical({'asin': 'B0CHWRXH8B', 'title': 'Worth it', 'rating': 5, 'verified_purchase': True, 'image_url': 'https://x.com/r.jpg'})
    assert am.is_target(review, target) and review['rating'] is None and review['title'] is None and review['image_url'] is None
    assert am.delivered('bestseller_rank', [{'category': 'Electronics', 'rank': 3}]) and am.delivered('bestseller_rank', '#3 in Electronics')
    assert not am.delivered('bestseller_rank', 0) and not am.delivered('price', 0) and not am.delivered('rating', 5.5)
    assert service_error([{'error_message': 'temporarily unavailable'}]) and not service_error([{'title': 'x'}])
    run = lambda items, error=None: {'error': error, 'items': items}
    assert classify(am, run([], 'boom'), target, ['price', 'brand']) == {'price': 'error', 'brand': 'error'}
    assert classify(am, run([{'asin': 'B000000000', 'price': 5}]), target, ['price'])['price'] == 'no_target'
    assert classify(am, run([{'asin': 'B0CHWRXH8B', 'price': 5}]), target, ['price', 'brand']) == {'price': 'delivered', 'brand': 'missing'}


def test_rules():
    assert rejection('Extract ASIN, title, rating and reviews for any product.') is None
    assert rejection('Cheapest Amazon scraper') and rejection('$0.10/1K results') and rejection('Free to use')
    assert rejection('x' * (MAX_DESCRIPTION + 1)) and rejection('  ')
    assert rejection('Product price and list price', r'\bprices?\b') is None and rejection('Best price per result', r'\bprices?\b')


def test_shelves():
    """Ten tools from ten vendor accounts, valid matrix inputs, round zero within the rules, one question per target and field."""
    for name in platforms.NAMES:
        platform, tables = platforms.load(name), data.load(name)
        tools, targets, fields = tables['tools'], tables['targets'], tables['fields']
        assert len(tools) == 10 and len({t['actor'].split('/')[0] for t in tools}) == 10
        assert sorted(t['tool'] for t in tools) == [f'{name[0].upper()}{i}' for i in range(10)]
        assert all(re.fullmatch(r'tool_[a-z]{4}', t['alias']) for t in tools) and len({t['alias'] for t in tools}) == 10
        assert [f['id'] for f in fields] == list(platform.ALIASES)[-len(fields):]
        assert tables['questions'] == platforms.questions(platform, targets, fields)
        for tool in tools:
            assert len(tool['description']) <= MAX_DESCRIPTION and not fee_talk(tool['description'], platform.PRICE_EXEMPT), tool['tool']
            for target in targets:
                jsonschema.validate(platform.BUILDERS[tool['actor']](target), tool['input_schema'])


def test_listings():
    """Every buyer saw the shelf in the order that its seed gives."""
    for name in platforms.NAMES:
        tables = data.load(name)
        shelf = [t['tool'] for t in tables['tools']]
        for row in tables['choices']:
            order = list(shelf)
            random.Random(buyer_seed(row['seed'], row['round'], row['question'])).shuffle(order)
            assert row['listing'] == order, row


def serve(mode, calls, **env):
    """Run the MCP server in one mode over stdio: initialize, tools/list, then the given tools/call params."""
    with tempfile.TemporaryDirectory() as directory:
        env = {**os.environ, 'MODE': mode, 'LOG': f'{directory}/mcp.jsonl', **env}
        requests = [{'method': 'initialize', 'params': {}}, {'method': 'tools/list', 'params': {}}] + [{'method': 'tools/call', 'params': c} for c in calls]
        process = subprocess.run([sys.executable, '-m', 'toolflation.server'], env=env, text=True, capture_output=True, cwd=data.ROOT,
                                 input=''.join(json.dumps({'jsonrpc': '2.0', 'id': i, **r}) + '\n' for i, r in enumerate(requests)))
        replies = [json.loads(line)['result'] for line in process.stdout.splitlines()]
        return replies[1]['tools'], replies[2:], data.read(f'{directory}/mcp.jsonl')


def test_buyer_server():
    """The buyer's server hides vendors and schemas, records the first call as the choice and ends the session."""
    shelf = [{'alias': t['alias'], 'tool': t['tool'], 'description': t['description']} for t in data.read(data.DATA / 'amazon/tools.json')]
    listed, replies, events = serve('buyer', [{'name': 'read_resource', 'arguments': {}}, {'name': shelf[0]['alias'], 'arguments': {'a': 1}}],
                                    TOOLS=json.dumps(shelf))
    assert [t['name'] for t in listed] == [t['alias'] for t in shelf] and all(t['inputSchema'] == {'type': 'object'} for t in listed)
    assert replies[0]['isError'] and 'Unknown tool' in replies[0]['content'][0]['text']
    assert replies[1]['isError'] and replies[1]['content'][0]['text'] == ENDED
    assert [(e['tool'], e['args']) for e in events if e['event'] == 'call'] == [(shelf[0]['tool'], {'a': 1})]


def test_seller_server():
    calls = [{'name': 'update_description', 'arguments': {'description': 'Free product data', 'reason': 'r'}},
             {'name': 'update_description', 'arguments': json.dumps({'description': 'Ratings and reviews', 'reason': 'r'})}]
    listed, replies, events = serve('seller', calls)
    assert listed == [UPDATE]
    assert [json.loads(r['content'][0]['text'])['accepted'] for r in replies] == [False, True]
    assert [(e['description'], e['rejected'] is None) for e in events if e['event'] == 'submit'] == [('Free product data', False), ('Ratings and reviews', True)]


if __name__ == '__main__':
    for name, test in list(globals().items()):
        if name.startswith('test_'):
            test()
            print('ok', name)
