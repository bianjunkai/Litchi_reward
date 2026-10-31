"""Read-only child-facing history projections of the existing reward ledger."""
from typing import Literal

from fastapi import Depends, HTTPException, Query

from reward_rules import BADGE_CODES


def register_backpack(app, get_db):
    def require_child(db, child_id):
        if not db.execute('SELECT 1 FROM children WHERE id=?', (child_id,)).fetchone():
            raise HTTPException(404, '找不到孩子')

    def page(rows, total, limit):
        more = len(rows) > limit
        items = rows[:limit]
        return {'items': items, 'total': total, 'has_more': more,
                'next_before_id': items[-1]['id'] if more else None}

    @app.get('/api/backpack/ledger')
    def ledger_history(
        wallet: Literal['stars', 'coupon'] = 'stars',
        child_id: int = Query(default=1, ge=1),
        asset_code: Literal['all', 'study_star', 'tidy_star', 'meal_star', 'gold_star', 'coupon'] = 'all',
        direction: Literal['all', 'in', 'out'] = 'all',
        before_id: int | None = Query(default=None, ge=1),
        limit: int = Query(default=20, ge=1, le=100),
        db=Depends(get_db),
    ):
        require_child(db, child_id)
        codes = ('study_star', 'tidy_star', 'meal_star', 'gold_star') if wallet == 'stars' else ('coupon',)
        if asset_code != 'all' and asset_code not in codes:
            raise HTTPException(422, '资产筛选与背包分类不匹配')
        clauses = ['a.code IN (' + ','.join('?' for _ in codes) + ')']
        params = list(codes)
        if asset_code != 'all':
            clauses.append('a.code=?')
            params.append(asset_code)
        if direction != 'all':
            clauses.append('e.delta>0' if direction == 'in' else 'e.delta<0')
        where = ' AND '.join(clauses)
        total = db.execute(f'''SELECT COUNT(*) FROM ledger e JOIN asset_types a ON a.id=e.asset_type_id
            WHERE e.child_id=? AND {where}''', [child_id, *params]).fetchone()[0]
        cursor = ' AND e.id<?' if before_id is not None else ''
        # Calculate each color's balance before applying filters or pagination.
        # IDs represent posting order; timestamps remain the recorded event time.
        rows = [dict(row) for row in db.execute(f'''
            WITH entries AS (
                SELECT l.*, SUM(l.delta) OVER (
                    PARTITION BY l.asset_type_id ORDER BY l.id ROWS UNBOUNDED PRECEDING
                ) AS posted_balance,
                MAX(CASE WHEN l.reference_type='opening_balance' THEN l.id END)
                    OVER (PARTITION BY l.asset_type_id) AS reconciliation_id
                FROM ledger l WHERE l.child_id=?
            )
            SELECT e.id,e.delta,e.reason,e.created_at,e.operation_id,e.reference_type,
                CASE WHEN e.id<e.reconciliation_id OR e.posted_balance<0 THEN NULL
                     ELSE e.posted_balance END AS balance_after,
                a.code AS asset_code,a.name AS asset_name,a.color,a.active,
                COALESCE(o.kind,'legacy') AS kind,COALESCE(o.rule_version,'legacy') AS rule_version,
                o.reversal_of,COALESCE(original.kind,o.kind,'legacy') AS source_kind,
                CASE WHEN o.reversal_of IS NOT NULL THEN 'reversal'
                     WHEN o.reversed_at IS NOT NULL THEN 'reversed' ELSE 'recorded' END AS status
            FROM entries e JOIN asset_types a ON a.id=e.asset_type_id
            LEFT JOIN operations o ON o.id=e.operation_id AND o.child_id=e.child_id
            LEFT JOIN operations original ON original.id=o.reversal_of AND original.child_id=e.child_id
            WHERE {where}{cursor} ORDER BY e.id DESC LIMIT ?
            ''', [child_id, *params, *([before_id] if before_id is not None else []), limit + 1])]
        source_ids = {row['reversal_of'] or row['operation_id'] for row in rows} - {None}
        settlements = {}
        if source_ids:
            marks = ','.join('?' for _ in source_ids)
            for row in db.execute(f'''SELECT operation_id,product_name,status,coupons_used,coupon_value_fen,
                    actual_amount_fen,parent_top_up_fen,forfeited_fen,settlement_note,rule_version
                FROM redemptions WHERE child_id=? AND operation_id IN ({marks}) ORDER BY id''',
                [child_id, *source_ids]):
                settlements[row['operation_id']] = dict(row)
        for row in rows:
            row['settlement'] = settlements.get(row['reversal_of'] or row['operation_id'])
        return {'child_id': child_id, 'wallet': wallet, **page(rows, total, limit)}

    @app.get('/api/backpack/badges')
    def badge_history(
        child_id: int = Query(default=1, ge=1),
        badge_id: int | None = Query(default=None, ge=1),
        status: Literal['all', 'available', 'spent', 'disabled', 'reversed'] = 'all',
        color: str | None = Query(default=None, pattern=r'^#[0-9a-fA-F]{6}$'),
        before_id: int | None = Query(default=None, ge=1),
        limit: int = Query(default=20, ge=1, le=100),
        db=Depends(get_db),
    ):
        require_child(db, child_id)
        codes = ','.join('?' for _ in BADGE_CODES)
        base = f'''WITH history AS (
            SELECT cb.id,cb.badge_id,cb.reason,cb.earned_at,cb.color,cb.operation_id,
                cb.spent_operation_id,cb.reversed_at,b.code,b.name,b.active,
                COALESCE(o.rule_version,'legacy') AS rule_version,spent.created_at AS spent_at,
                CASE WHEN cb.reversed_at IS NOT NULL THEN 'reversed'
                     WHEN cb.spent_operation_id IS NOT NULL THEN 'spent'
                     WHEN b.active=1 AND b.code IN ({codes}) THEN 'available' ELSE 'disabled' END AS status
            FROM child_badges cb JOIN badges b ON b.id=cb.badge_id
            LEFT JOIN operations o ON o.id=cb.operation_id AND o.child_id=cb.child_id
            LEFT JOIN operations spent ON spent.id=cb.spent_operation_id AND spent.child_id=cb.child_id
            WHERE cb.child_id=?
        )'''
        clauses = ['1=1']
        params = [*BADGE_CODES, child_id]
        if badge_id is not None:
            clauses.append('badge_id=?')
            params.append(badge_id)
        if status != 'all':
            clauses.append('status=?')
            params.append(status)
        if color is not None:
            clauses.append('LOWER(color)=LOWER(?)')
            params.append(color)
        where = ' AND '.join(clauses)
        total = db.execute(base + f' SELECT COUNT(*) FROM history WHERE {where}', params).fetchone()[0]
        cursor = ' AND id<?' if before_id is not None else ''
        rows = [dict(row) for row in db.execute(base + f''' SELECT * FROM history
            WHERE {where}{cursor} ORDER BY id DESC LIMIT ?''',
            [*params, *([before_id] if before_id is not None else []), limit + 1])]
        return {'child_id': child_id, 'wallet': 'badges', **page(rows, total, limit)}
