"""The family's agreed rules. Money is always stored as integer fen."""
STARS_PER_LIFE_BADGE = 5
BADGES_PER_COUPON = 5
COUPON_VALUE_FEN = 3990
MAX_COUPONS_PER_USE = 5
RULE_VERSION = 'family-v2'
STAR_CODES = ('study_star','tidy_star','meal_star')
LIFE_BADGE_STAR_CODES = ('tidy_star','meal_star')
SUNFLOWER_BADGE_STAR_CODES = ('study_star',)
BADGE_CODES = ('sports','life','fire','royal')
BADGE_COLORS = ('#4eb478','#f0aa37','#e55353','#d4af37','#aab5c4')
SUNFLOWER_MIGRATION_KEY = 'sunflower_badge_v1'


def migrate_sunflower_badge(tables):
    """Enable the third badge as a star-conversion reward without rewriting history."""
    settings = tables.get('settings', [])
    if any(row['key'] == SUNFLOWER_MIGRATION_KEY for row in settings):
        return False
    fire_badges = [badge for badge in tables.get('badges', []) if badge['code'] == 'fire']
    fire_ids = {badge['id'] for badge in fire_badges}
    for badge in fire_badges:
        badge.update(name='太阳花徽章', description='认真学习、专心阅读，集齐 5 颗橙色学习星星兑换。', icon='🌻', active=1)
    for task in tables.get('tasks', []):
        if task.get('badge_id') in fire_ids:
            task['active'] = 0
    settings.append({'key': SUNFLOWER_MIGRATION_KEY, 'value': 'done'})
    return True


def normalize_legacy_data(tables):
    """Only future configuration changes; earned assets and past deductions stay intact."""
    badges = {b['id']:b for b in tables.get('badges',[])}
    assets = {a['id']:a for a in tables.get('asset_types',[])}
    for badge in badges.values():
        badge['threshold'] = STARS_PER_LIFE_BADGE  # Legacy schema field; not a sports-badge cost.
        if badge['code'] not in BADGE_CODES:
            badge['active'] = 0
        if badge['color'] not in BADGE_COLORS:
            badge['color'] = '#f0aa37'
        if badge['code']=='fire':
            badge.update(name='太阳花徽章', description='认真学习、专心阅读，集齐 5 颗橙色学习星星兑换。', icon='🌻', active=1)
        if badge['code']=='royal' and badge['name']=='王冠徽章':
            badge['name'] = '预留徽章 B'
    for asset in assets.values():
        if asset['code']=='gold_star':
            asset['active'] = 0
    for task in tables.get('tasks',[]):
        badge = badges.get(task.get('badge_id'))
        asset = assets.get(task['asset_type_id'])
        if task.get('badge_id'):
            if not badge or badge['code'] not in ('sports','royal'):
                task['active'] = 0
        else:
            task['amount'] = 1
            if not asset or asset['code'] not in STAR_CODES:
                task['active'] = 0
            defaults = {
                '专心完成今天的学习任务':'好好学习、认真读书',
                '把玩具和书本送回家':'每天收拾桌子和自己的物品',
                '好好吃饭，健康成长':'不拖沓，按时吃完饭',
            }
            task['description'] = defaults.get(task['description'],task['description'])
        if task.get('badge_color') not in (None,*BADGE_COLORS):
            task['badge_color'] = None
    for product in tables.get('products',[]):
        if not 1<=product['price']<=MAX_COUPONS_PER_USE:
            product['active'] = 0
