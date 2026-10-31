"""Child requests select five badge instances; only a parent approval spends them."""
from typing import Literal

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator, model_validator

from database import utc_now
from parent_views import page
from reward_rules import BADGE_COLORS, BADGES_PER_COUPON


class BadgeChoice(BaseModel):
    badge_id: int = Field(ge=1, strict=True)
    color: str
    count: int = Field(ge=1, le=BADGES_PER_COUPON, strict=True)

    @field_validator('color')
    @classmethod
    def valid_color(cls, value):
        if value not in BADGE_COLORS:
            raise ValueError('请选择有效的徽章颜色')
        return value


class CouponRequestInput(BaseModel):
    child_id: int = Field(default=1, ge=1, strict=True)
    selections: list[BadgeChoice] = Field(min_length=1, max_length=BADGES_PER_COUPON)

    @model_validator(mode='after')
    def five_distinct_choices(self):
        if sum(item.count for item in self.selections) != BADGES_PER_COUPON:
            raise ValueError('每张兑换券需要选择 5 枚徽章')
        if len({(item.badge_id,item.color) for item in self.selections}) != len(self.selections):
            raise ValueError('相同类型和颜色请合并数量')
        return self


def register_coupon_requests(app, get_db, parent, child_exists, convert, audit):
    @app.post('/api/coupon-requests')
    def request_coupon(payload: CouponRequestInput, db=Depends(get_db)):
        child_exists(db,payload.child_id)
        existing = db.execute("SELECT id FROM coupon_requests WHERE child_id=? AND status='pending'",(payload.child_id,)).fetchone()
        if existing:
            return {'success':True,'id':existing['id'],'message':'已有换券申请在等待家长审批，请勿重复提交'}
        selected_ids = []
        for item in payload.selections:
            rows = db.execute('''SELECT cb.id FROM child_badges cb JOIN badges b ON b.id=cb.badge_id
                WHERE cb.child_id=? AND cb.badge_id=? AND cb.color=? AND cb.reversed_at IS NULL
                AND cb.spent_operation_id IS NULL AND b.active=1 AND b.code IN ('sports','life','fire','royal')
                ORDER BY cb.id LIMIT ?''',(payload.child_id,item.badge_id,item.color,item.count)).fetchall()
            if len(rows) != item.count:
                raise HTTPException(409,'选中的徽章数量已变化，请刷新背包后重新选择')
            selected_ids.extend(row['id'] for row in rows)
        request_id = db.execute('INSERT INTO coupon_requests(child_id,requested_at) VALUES (?,?)',
            (payload.child_id,utc_now())).lastrowid
        db.executemany('INSERT INTO coupon_request_badges(request_id,child_badge_id) VALUES (?,?)',
            [(request_id,badge_id) for badge_id in selected_ids])
        audit(db,'coupon_requested',f'request:{request_id}')
        return {'success':True,'id':request_id,'message':'换券申请已提交，家长同意后才扣除徽章并获得兑换券'}

    @app.get('/api/parent/coupon-requests', dependencies=[Depends(parent)])
    @app.get('/api/coupon-requests')
    def list_requests(child_id: int=Query(1,ge=1),
                      status: Literal['all','pending','approved','rejected','reversed']='all',
                      before_id: int | None=Query(None,ge=1), limit: int=Query(20,ge=1,le=100), db=Depends(get_db)):
        child_exists(db,child_id)
        clauses,params = ['r.child_id=?'],[child_id]
        if status != 'all':
            clauses.append('r.status=?'); params.append(status)
        result = page(db,'coupon_requests','r',clauses,params,before_id,limit,'r.*')
        for item in result['items']:
            rows = db.execute('''SELECT b.id AS badge_id,b.code,b.name,cb.color,COUNT(*) AS count,
                SUM(CASE WHEN cb.reversed_at IS NULL AND cb.spent_operation_id IS NULL AND b.active=1
                    AND b.code IN ('sports','life','fire','royal') THEN 1 ELSE 0 END) AS usable_count
                FROM coupon_request_badges link JOIN child_badges cb ON cb.id=link.child_badge_id
                JOIN badges b ON b.id=cb.badge_id WHERE link.request_id=? GROUP BY b.id,cb.color ORDER BY b.id,cb.color''',
                (item['id'],)).fetchall()
            item['selections'] = [dict(row) for row in rows]
            item['can_approve'] = item['status']=='pending' and sum(row['usable_count'] for row in rows)==BADGES_PER_COUPON
        result['pending_count'] = db.execute("SELECT COUNT(*) FROM coupon_requests WHERE child_id=? AND status='pending'",(child_id,)).fetchone()[0]
        return result

    @app.post('/api/parent/coupon-requests/{request_id}/{action}')
    def review_request(request_id: int, action: Literal['approve','reject'], token=Depends(parent), db=Depends(get_db)):
        item = db.execute('SELECT * FROM coupon_requests WHERE id=?',(request_id,)).fetchone()
        if not item:
            raise HTTPException(404,'找不到换券申请')
        if item['status'] != 'pending':
            raise HTTPException(409,'这笔换券申请已处理，请刷新核对')
        result = {'success':True}
        if action=='approve':
            ids = [row['child_badge_id'] for row in db.execute(
                'SELECT child_badge_id FROM coupon_request_badges WHERE request_id=?',(request_id,))]
            result = convert(db,item['child_id'],ids)
        status = 'approved' if action=='approve' else 'rejected'
        db.execute('UPDATE coupon_requests SET status=?,processed_at=?,operation_id=? WHERE id=?',
            (status,utc_now(),result.get('operation_id'),request_id))
        audit(db,'coupon_request_'+status,f'request:{request_id}')
        return {**result,'status':status}
