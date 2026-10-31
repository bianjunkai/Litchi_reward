"""Authenticated, paginated parent views and a read-only reversal preview."""
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, Query


def reversal_preview(db, op_id):
    row = db.execute('SELECT * FROM operations WHERE id=?', (op_id,)).fetchone()
    if not row:
        raise HTTPException(404, '找不到原操作')
    source = dict(row)
    result = {'operation': source, 'can_reverse': False, 'blockers': [], 'assets': [],
              'badges_remove': [], 'badges_restore': [], 'blocking_operation_ids': []}
    if source['reversed_at'] or source['reversal_of']:
        result['blockers'].append('该操作已撤销或本身为撤销记录')
        return result
    dependencies = [r[0] for r in db.execute('''SELECT DISTINCT spent_operation_id FROM child_badges
        WHERE operation_id=? AND spent_operation_id IS NOT NULL AND reversed_at IS NULL
        ORDER BY spent_operation_id''', (op_id,))]
    result['blocking_operation_ids'] = dependencies
    if dependencies:
        result['blockers'].append('徽章已兑换，请先撤销后续操作：' + '、'.join(f'#{n}' for n in dependencies))
    assets = {}
    for entry in db.execute('''SELECT l.*,a.code,a.name,a.icon,ca.balance FROM ledger l
        JOIN asset_types a ON a.id=l.asset_type_id LEFT JOIN child_assets ca
        ON ca.asset_type_id=l.asset_type_id AND ca.child_id=l.child_id
        WHERE l.operation_id=? ORDER BY l.id''', (op_id,)):
        asset = assets.setdefault(entry['asset_type_id'], {
            'code': entry['code'], 'name': entry['name'], 'icon': entry['icon'],
            'before': entry['balance'], 'delta': 0, 'after': entry['balance']})
        if asset['after'] is None:
            result['blockers'].append(f"{entry['name']}账户不存在")
            continue
        asset['delta'] -= entry['delta']
        asset['after'] -= entry['delta']
        if asset['after'] < 0:
            result['blockers'].append(f"{entry['name']}余额不足，请先撤销后续使用或核对账目")
    result['assets'] = list(assets.values())
    for field, condition in [('badges_remove', 'cb.operation_id=?'), ('badges_restore', 'cb.spent_operation_id=?')]:
        result[field] = [dict(r) for r in db.execute(f'''SELECT b.name,b.code,cb.color,COUNT(*) AS count
            FROM child_badges cb JOIN badges b ON b.id=cb.badge_id
            WHERE {condition} AND cb.reversed_at IS NULL GROUP BY b.id,cb.color ORDER BY b.id,cb.color''', (op_id,))]
    result['blockers'] = list(dict.fromkeys(result['blockers']))
    result['can_reverse'] = not result['blockers']
    return result


def filters(db, child_id, alias, timestamp, search, from_date, to_date, search_columns):
    if not db.execute('SELECT 1 FROM children WHERE id=?', (child_id,)).fetchone():
        raise HTTPException(404, '找不到孩子')
    clauses, params = [f'{alias}.child_id=?'], [child_id]
    if from_date and to_date and from_date > to_date:
        raise HTTPException(422, '开始日期不能晚于结束日期')
    zone = ZoneInfo(db.execute("SELECT value FROM settings WHERE key='family_timezone'").fetchone()[0])
    try:
        for value, end in [(from_date, False), (to_date, True)]:
            if value:
                day = value + timedelta(days=1) if end else value
                bound = datetime.combine(day, time.min, zone).astimezone(timezone.utc).isoformat()
                clauses.append(f'julianday({alias}.{timestamp}) {"<" if end else ">="} julianday(?)')
                params.append(bound)
    except (OverflowError, ValueError):
        raise HTTPException(422, '日期超出可查询范围')
    exact = search.strip()
    if exact.startswith('#') and exact[1:].isascii() and exact[1:].isdigit():
        clauses.append(f'{search_columns[-1]}=?')
        params.append('#' + str(int(exact[1:])))
    elif exact:
        query = search.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        parts = [f"{column} LIKE ? ESCAPE '\\'" for column in search_columns]
        params.extend([f'%{query}%'] * len(parts))
        clauses.append('(' + ' OR '.join(parts) + ')')
    return clauses, params


def page(db, table, alias, clauses, params, before_id, limit, select='*', joins=''):
    where = ' AND '.join(clauses)
    total = db.execute(f'SELECT COUNT(*) FROM {table} {alias} {joins} WHERE {where}', params).fetchone()[0]
    if before_id is not None:
        where += f' AND {alias}.id<?'
        params = [*params, before_id]
    rows = [dict(r) for r in db.execute(f'SELECT {select} FROM {table} {alias} {joins} WHERE {where} ORDER BY {alias}.id DESC LIMIT ?', [*params, limit + 1])]
    more = len(rows) > limit
    items = rows[:limit]
    return {'items': items, 'total': total, 'has_more': more,
            'next_before_id': items[-1]['id'] if more else None}


def register_parent_views(app, get_db, parent):
    @app.get('/api/parent/review')
    def review(child_id: int = Query(1, ge=1),
               status: Literal['all', 'pending', 'approved', 'rejected', 'reversed'] = 'pending',
               search: str = Query('', max_length=160), from_date: date | None = None, to_date: date | None = None,
               before_id: int | None = Query(None, ge=1), limit: int = Query(20, ge=1, le=100),
               token=Depends(parent), db=Depends(get_db)):
        clauses, params = filters(db, child_id, 'r', 'requested_at', search, from_date, to_date,
                                  ['r.product_name', "'#' || r.id"])
        if status != 'all':
            clauses.append('r.status=?')
            params.append(status)
        result = page(db, 'redemptions', 'r', clauses, params, before_id, limit, 'r.*')
        result['coupon_balance'] = db.execute('''SELECT ca.balance FROM child_assets ca JOIN asset_types a
            ON a.id=ca.asset_type_id WHERE ca.child_id=? AND a.code='coupon' ''', (child_id,)).fetchone()[0]
        result['counts'] = dict.fromkeys(('pending', 'approved', 'rejected', 'reversed'), 0)
        result['counts'].update({r[0]: r[1] for r in db.execute('SELECT status,COUNT(*) FROM redemptions WHERE child_id=? GROUP BY status', (child_id,))})
        return result

    @app.get('/api/parent/history')
    def history(child_id: int = Query(1, ge=1), view: Literal['operations', 'ledger'] = 'operations',
                kind: Literal['all', 'task', 'manual', 'stars_to_badge', 'badges_to_coupon', 'redemption', 'reversal'] = 'all',
                state: Literal['all', 'active', 'reversed', 'reversal'] = 'all',
                asset: Literal['all', 'study_star', 'tidy_star', 'meal_star', 'gold_star', 'coupon'] = 'all',
                direction: Literal['all', 'in', 'out'] = 'all',
                search: str = Query('', max_length=160), from_date: date | None = None, to_date: date | None = None,
                before_id: int | None = Query(None, ge=1), limit: int = Query(20, ge=1, le=100),
                token=Depends(parent), db=Depends(get_db)):
        if view == 'operations':
            clauses, params = filters(db, child_id, 'o', 'created_at', search, from_date, to_date, ['o.reason', "'#' || o.id"])
            if kind != 'all':
                clauses.append('o.kind=?')
                params.append(kind)
            if state == 'active':
                clauses.append('o.reversed_at IS NULL AND o.reversal_of IS NULL')
            elif state == 'reversed':
                clauses.append('o.reversed_at IS NOT NULL')
            elif state == 'reversal':
                clauses.append('o.reversal_of IS NOT NULL')
            result = page(db, 'operations', 'o', clauses, params, before_id, limit, 'o.*')
            ids = [item['id'] for item in result['items']]
            changes = {}
            badge_changes = {}
            if ids:
                marks = ','.join('?' for _ in ids)
                for row in db.execute(f'''SELECT l.operation_id,a.code,a.name,a.icon,SUM(l.delta) AS delta
                    FROM ledger l JOIN asset_types a ON a.id=l.asset_type_id WHERE l.operation_id IN ({marks})
                    GROUP BY l.operation_id,a.id ORDER BY a.id''', ids):
                    changes.setdefault(row['operation_id'], []).append(dict(row))
                for row in db.execute(f'''SELECT entry.operation_id,b.code,b.name,entry.color,SUM(entry.delta) AS delta
                    FROM (
                        SELECT operation_id, badge_id, color, 1 AS delta FROM child_badges
                            WHERE operation_id IN ({marks}) AND reversed_at IS NULL
                        UNION ALL
                        SELECT spent_operation_id AS operation_id,badge_id,color,-1 AS delta FROM child_badges
                            WHERE spent_operation_id IN ({marks}) AND reversed_at IS NULL
                    ) entry JOIN badges b ON b.id=entry.badge_id
                    GROUP BY entry.operation_id,b.id,entry.color ORDER BY b.id,entry.color''', [*ids,*ids]):
                    badge_changes.setdefault(row['operation_id'], []).append(dict(row))
            for item in result['items']:
                item['asset_changes'] = changes.get(item['id'], [])
                item['badge_changes'] = badge_changes.get(item['id'], [])
            return result
        clauses, params = filters(db, child_id, 'l', 'created_at', search, from_date, to_date, ['l.reason', "'#' || l.operation_id"])
        if asset != 'all':
            clauses.append('a.code=?')
            params.append(asset)
        if direction != 'all':
            clauses.append('l.delta>0' if direction == 'in' else 'l.delta<0')
        return page(db, 'ledger', 'l', clauses, params, before_id, limit,
                    'l.*,a.code,a.name AS asset_name,a.icon,o.reversed_at,o.reversal_of',
                    'JOIN asset_types a ON a.id=l.asset_type_id LEFT JOIN operations o ON o.id=l.operation_id')

    @app.get('/api/parent/operations/{op_id}/preview')
    def preview(op_id: int, token=Depends(parent), db=Depends(get_db)):
        return reversal_preview(db, op_id)
