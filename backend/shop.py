"""Read-only, child-scoped views of reward-shop applications."""
from typing import Literal

from fastapi import Depends, HTTPException, Query


def register_shop(app, get_db):
    @app.get('/api/shop/requests')
    def requests(
        child_id: int = Query(default=1, ge=1),
        status: Literal['all', 'pending', 'approved', 'rejected', 'reversed'] = 'all',
        before_id: int | None = Query(default=None, ge=1),
        limit: int = Query(default=20, ge=1, le=100),
        db=Depends(get_db),
    ):
        if not db.execute('SELECT 1 FROM children WHERE id=?', (child_id,)).fetchone():
            raise HTTPException(404, '找不到孩子')
        counts = dict.fromkeys(('pending', 'approved', 'rejected', 'reversed'), 0)
        for row in db.execute('SELECT status,COUNT(*) AS total FROM redemptions WHERE child_id=? GROUP BY status', (child_id,)):
            counts[row['status']] = row['total']
        pending_ids = [row[0] for row in db.execute("SELECT DISTINCT product_id FROM redemptions WHERE child_id=? AND status='pending' ORDER BY product_id", (child_id,))]
        clauses, params = ['r.child_id=?'], [child_id]
        if status != 'all':
            clauses.append('r.status=?')
            params.append(status)
        total = sum(counts.values()) if status == 'all' else counts[status]
        if before_id is not None:
            clauses.append('r.id<?')
            params.append(before_id)
        rows = [dict(row) for row in db.execute(f'''
            SELECT r.id,r.product_id,r.product_name,r.icon,r.price,r.status,r.requested_at,r.approved_at,
                r.coupon_value_fen,r.coupons_used,r.actual_amount_fen,r.parent_top_up_fen,r.forfeited_fen,
                r.quoted_amount_fen,r.settlement_note,r.rule_version,o.reversed_at,
                CASE WHEN p.active=1 AND p.price BETWEEN 1 AND 5 THEN 1 ELSE 0 END AS product_available
            FROM redemptions r LEFT JOIN products p ON p.id=r.product_id
            LEFT JOIN operations o ON o.id=r.operation_id AND o.child_id=r.child_id
            WHERE {' AND '.join(clauses)} ORDER BY r.id DESC LIMIT ?''', [*params, limit + 1])]
        more = len(rows) > limit
        items = rows[:limit]
        for item in items:
            item['product_available'] = bool(item['product_available'])
            item['can_reapply'] = item['status'] != 'pending' and item['product_available'] and item['product_id'] not in pending_ids
        return {'child_id': child_id, 'items': items, 'total': total, 'counts': counts,
                'pending_product_ids': pending_ids, 'has_more': more,
                'next_before_id': items[-1]['id'] if more else None}
