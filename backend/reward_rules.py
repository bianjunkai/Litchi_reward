"""The family's agreed rules. Money is always stored as integer fen."""
STARS_PER_LIFE_BADGE = 5
BADGES_PER_COUPON = 5
COUPON_VALUE_FEN = 3990
MAX_COUPONS_PER_USE = 5
RULE_VERSION = 'family-v1'
STAR_CODES = ('study_star','tidy_star','meal_star')
BADGE_CODES = ('sports','life','fire','royal')
BADGE_COLORS = ('#4eb478','#f0aa37','#e55353','#d4af37','#aab5c4')


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
        if badge['code']=='fire' and badge['name']=='火花徽章':
            badge['name'] = '预留徽章 A'
        if badge['code']=='royal' and badge['name']=='王冠徽章':
            badge['name'] = '预留徽章 B'
    for asset in assets.values():
        if asset['code']=='gold_star':
            asset['active'] = 0
    for task in tables.get('tasks',[]):
        badge = badges.get(task.get('badge_id'))
        asset = assets.get(task['asset_type_id'])
        if task.get('badge_id'):
            if not badge or badge['code'] not in ('sports','fire','royal'):
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
