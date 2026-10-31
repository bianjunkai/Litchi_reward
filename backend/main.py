import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from database import init_db, pin_hash, transaction, utc_now
from product_images import MAX_IMAGE_TEXT, validate_image
from reward_rules import (BADGE_CODES, BADGE_COLORS, BADGES_PER_COUPON, COUPON_VALUE_FEN,
                          MAX_COUPONS_PER_USE, RULE_VERSION, STAR_CODES, STARS_PER_LIFE_BADGE)

DEFAULT_DB_PATH = str(Path(__file__).parent.parent / 'data' / 'rewards.db')
RULE_KEYS = ('badge_ratio','badges_per_coupon','family_timezone')


def today(zone='Asia/Shanghai'):
    return datetime.now(timezone.utc).astimezone(ZoneInfo(zone)).date().isoformat()


class ChildInput(BaseModel):
    child_id: int = Field(default=1, ge=1)


class ProductQuote(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(max_length=500)
    icon: str = Field(max_length=20)
    price: int = Field(ge=1, le=MAX_COUPONS_PER_USE, strict=True)
    cash_price_fen: int | None = Field(ge=0, le=100_000_000, strict=True)
    image_data: str = Field(default='', max_length=MAX_IMAGE_TEXT)

    _image = field_validator('image_data')(validate_image)


class RedemptionRequest(ChildInput):
    product_id: int = Field(ge=1)
    expected_product: ProductQuote | None = None


class ParentLogin(BaseModel):
    pin: str = Field(min_length=1, max_length=32)


class PinInput(BaseModel):
    pin: str = Field(pattern=r'^[0-9]{6,12}$')


class ProductInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default='', max_length=500)
    icon: str = Field(default='🎁', max_length=20)
    price: int = Field(ge=1, le=MAX_COUPONS_PER_USE, strict=True)
    cash_price_fen: int | None = Field(default=None, ge=0, le=100_000_000, strict=True)
    active: bool = True
    image_data: str = Field(default='', max_length=MAX_IMAGE_TEXT)

    _image = field_validator('image_data')(validate_image)

    @field_validator('name')
    @classmethod
    def meaningful_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('请填写奖励名称')
        return value


class AvailabilityInput(BaseModel):
    active: bool = Field(strict=True)


class TaskInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default='', max_length=500)
    asset_code: str = 'study_star'
    badge_id: int | None = Field(default=None, ge=1)
    badge_color: str | None = None
    amount: int = Field(default=1, ge=1, le=99)
    active: bool = True

    @field_validator('badge_color')
    @classmethod
    def valid_color(cls, value):
        if value is not None and value not in BADGE_COLORS:
            raise ValueError('徽章颜色仅支持绿、橙、红、金、银')
        return value


class BadgeInput(BaseModel):
    code: str = Field(pattern=r'^(sports|life|fire|royal)$')
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default='', max_length=500)
    icon: str = Field(default='⭐', max_length=20)
    color: str = Field(default='#f0aa37', pattern=r'^#[0-9a-fA-F]{6}$')
    threshold: int = Field(default=5, ge=5, le=5)
    active: bool = True

    @field_validator('color')
    @classmethod
    def valid_color(cls, value):
        if value not in BADGE_COLORS:
            raise ValueError('徽章颜色仅支持绿、橙、红、金、银')
        return value


class ConversionInput(ChildInput):
    badge_id: int = Field(ge=1)
    color: str | None = Field(default=None, pattern=r'^#[0-9a-fA-F]{6}$')

    @field_validator('color')
    @classmethod
    def valid_color(cls, value):
        if value is not None and value not in BADGE_COLORS:
            raise ValueError('徽章颜色仅支持绿、橙、红、金、银')
        return value


class ClaimInput(BaseModel):
    color: str | None = None

    @field_validator('color')
    @classmethod
    def valid_color(cls, value):
        if value is not None and value not in BADGE_COLORS:
            raise ValueError('徽章颜色仅支持绿、橙、红、金、银')
        return value


class SettlementInput(BaseModel):
    actual_amount_fen: int = Field(ge=0, le=100_000_000, strict=True)
    coupon_count: int | None = Field(default=None, ge=1, le=MAX_COUPONS_PER_USE, strict=True)
    approve_top_up: bool = False
    note: str = Field(default='', max_length=500)


class AdjustmentInput(ChildInput):
    asset_code: str
    delta: int = Field(ge=-999, le=999, strict=True)
    reason: str = Field(min_length=1, max_length=160)
    expected_balance: int | None = Field(default=None, ge=0, strict=True)

    @field_validator('reason')
    @classmethod
    def meaningful_reason(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('请填写调整原因')
        return value

    @field_validator('delta')
    @classmethod
    def nonzero(cls, value):
        if not value:
            raise ValueError('调整数量不能为 0')
        return value


class BadgeAdjustmentInput(ChildInput):
    badge_id: int = Field(ge=1)
    color: str
    delta: int = Field(ge=-999, le=999, strict=True)
    reason: str = Field(min_length=1, max_length=160)
    expected_count: int = Field(ge=0, strict=True)

    @field_validator('color')
    @classmethod
    def valid_color(cls, value):
        if value not in BADGE_COLORS:
            raise ValueError('徽章颜色仅支持绿、橙、红、金、银')
        return value

    @field_validator('reason')
    @classmethod
    def meaningful_reason(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('请填写调整原因')
        return value

    @field_validator('delta')
    @classmethod
    def nonzero(cls, value):
        if not value:
            raise ValueError('调整数量不能为 0')
        return value


class RulesInput(BaseModel):
    badge_ratio: int = Field(default=5, ge=5, le=5)
    badges_per_coupon: int = Field(default=5, ge=5, le=5)
    coupon_value_fen: int = Field(default=3990, ge=3990, le=3990)
    max_coupons_per_redemption: int = Field(default=5, ge=5, le=5)
    family_timezone: str = 'Asia/Shanghai'

    @field_validator('family_timezone')
    @classmethod
    def valid_zone(cls, value):
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError:
            raise ValueError('无效时区')
        return value


def child_exists(db, child_id):
    child = db.execute('SELECT * FROM children WHERE id=?',(child_id,)).fetchone()
    if not child:
        raise HTTPException(404,'找不到孩子')
    return dict(child)


def rules(db):
    result = dict(db.execute('SELECT key,value FROM settings WHERE key IN (?,?,?)',RULE_KEYS).fetchall())
    return {'badge_ratio':STARS_PER_LIFE_BADGE,'badges_per_coupon':BADGES_PER_COUPON,
            'coupon_value_fen':COUPON_VALUE_FEN,'max_coupons_per_redemption':MAX_COUPONS_PER_USE,
            'family_timezone':result['family_timezone']}


def audit(db, action, detail):
    db.execute('INSERT INTO audit_logs(action,detail,created_at) VALUES (?,?,?)',(action,detail,utc_now()))


def operation(db, child_id, kind, reason, reversal_of=None):
    return db.execute('INSERT INTO operations(child_id,kind,reason,created_at,reversal_of,rule_version) VALUES (?,?,?,?,?,?)',
                      (child_id,kind,reason,utc_now(),reversal_of,RULE_VERSION)).lastrowid


def change_asset(db, child_id, asset_id, delta, reason, op_id):
    changed = db.execute('UPDATE child_assets SET balance=balance+? WHERE child_id=? AND asset_type_id=? AND balance+?>=0',
                        (delta,child_id,asset_id,delta)).rowcount
    if changed!=1:
        raise HTTPException(409,'资产不足，操作未执行')
    db.execute('INSERT INTO ledger(child_id,asset_type_id,delta,reason,reference_type,reference_id,created_at,operation_id) VALUES (?,?,?,?,?,?,?,?)',
               (child_id,asset_id,delta,reason,'operation',op_id,utc_now(),op_id))


def convert_badges_to_coupon(db, child_id, badge_ids=None):
    params = [child_id]
    selected = ''
    if badge_ids is not None:
        if len(badge_ids) != BADGES_PER_COUPON or len(set(badge_ids)) != BADGES_PER_COUPON:
            raise HTTPException(409,'每次需要选择 5 枚不同的可用徽章')
        selected = ' AND cb.id IN (' + ','.join('?' for _ in badge_ids) + ')'
        params.extend(badge_ids)
    owned = db.execute('''SELECT cb.id FROM child_badges cb JOIN badges b ON b.id=cb.badge_id
        WHERE cb.child_id=? AND cb.reversed_at IS NULL AND cb.spent_operation_id IS NULL
        AND b.active=1 AND b.code IN ('sports','life','fire','royal')''' + selected + ' ORDER BY cb.id LIMIT ?',
        [*params,BADGES_PER_COUPON]).fetchall()
    if len(owned) != BADGES_PER_COUPON:
        raise HTTPException(409,'选中的徽章已使用、已撤销或已停用，请核对后重新申请')
    op = operation(db,child_id,'badges_to_coupon',f'{BADGES_PER_COUPON} 枚徽章兑换 1 张券')
    db.executemany('UPDATE child_badges SET spent_operation_id=? WHERE id=?',[(op,row['id']) for row in owned])
    coupon = db.execute("SELECT id FROM asset_types WHERE code='coupon'").fetchone()[0]
    change_asset(db,child_id,coupon,1,'徽章兑换券',op)
    audit(db,'badges_to_coupon',f'operation:{op}')
    return {'success':True,'operation_id':op,'badges_consumed':BADGES_PER_COUPON,'coupon_value_fen':COUPON_VALUE_FEN}


def badge_summary(db, child_id):
    badges = [dict(r) for r in db.execute('''SELECT b.*,
        COUNT(CASE WHEN cb.reversed_at IS NULL THEN cb.id END) AS earned_count,
        COUNT(CASE WHEN cb.reversed_at IS NULL AND cb.spent_operation_id IS NULL THEN cb.id END) AS unspent_count,
        COUNT(CASE WHEN cb.reversed_at IS NULL AND cb.spent_operation_id IS NULL AND b.active=1
            AND b.code IN ('sports','life','fire','royal') THEN cb.id END) AS available_count,
        MAX(CASE WHEN cb.reversed_at IS NULL THEN cb.earned_at END) AS latest_earned_at
        FROM badges b LEFT JOIN child_badges cb ON cb.badge_id=b.id AND cb.child_id=?
        GROUP BY b.id ORDER BY b.id''',(child_id,))]
    colors = db.execute('''SELECT badge_id,color,COUNT(*) AS count,
        SUM(CASE WHEN spent_operation_id IS NULL THEN 1 ELSE 0 END) AS available_count
        FROM child_badges WHERE child_id=? AND reversed_at IS NULL GROUP BY badge_id,color ORDER BY badge_id,color''',
        (child_id,)).fetchall()
    by_badge = {}
    for row in colors:
        by_badge.setdefault(row['badge_id'],[]).append({'color':row['color'],'count':row['count'],
            'available_count':row['available_count']})
    for badge in badges:
        badge['colors'] = by_badge.get(badge['id'],[])
    return badges


def star_claimed(db, child_id, day, asset_id):
    return bool(db.execute('''SELECT 1 FROM task_claims tc JOIN tasks original ON original.id=tc.task_id
        LEFT JOIN ledger l ON l.operation_id=tc.operation_id WHERE tc.child_id=? AND tc.claim_date=?
        AND tc.reversed_at IS NULL AND ((tc.operation_id IS NOT NULL AND l.asset_type_id=? AND l.delta>0)
        OR (tc.operation_id IS NULL AND original.badge_id IS NULL AND original.asset_type_id=?)) LIMIT 1''',
        (child_id,day,asset_id,asset_id)).fetchone())


def create_app(db_path=None, parent_pin=None):
    path = str(db_path or os.getenv('DB_PATH',DEFAULT_DB_PATH))
    legacy = Path(__file__).parent / 'data' / 'rewards.db'
    if not db_path and not os.getenv('DB_PATH') and not Path(path).exists() and legacy.exists():
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        source, target = sqlite3.connect(str(legacy)), sqlite3.connect(path)
        try:
            source.backup(target)
        finally:
            source.close()
            target.close()
    init_db(path,parent_pin if parent_pin is not None else os.getenv('PARENT_PIN') or None)
    app = FastAPI(title='家庭奖励中心',version='0.2.0')
    app.state.db_path = path

    def get_db(request: Request):
        with transaction(path,write=request.method not in {'GET','HEAD'}) as db:
            yield db

    def parent(authorization: str | None=Header(default=None), db=Depends(get_db)):
        token = (authorization or '').removeprefix('Bearer ')
        hashed = hashlib.sha256(token.encode()).hexdigest()
        session = db.execute('SELECT * FROM sessions WHERE token_hash=? AND expires_at>?',(hashed,time.time())).fetchone()
        if not token or not session:
            raise HTTPException(401,'家长会话已锁定，请重新输入 PIN')
        return hashed

    def issue_session(db):
        token = secrets.token_urlsafe(32)
        db.execute('DELETE FROM sessions WHERE expires_at<=?',(time.time(),))
        db.execute('INSERT INTO sessions VALUES (?,?)',(hashlib.sha256(token.encode()).hexdigest(),time.time()+1800))
        return {'authenticated':True,'token':token,'expires_in':1800}

    @app.get('/api/health')
    def health(db=Depends(get_db)):
        db.execute('SELECT 1').fetchone()
        return {'status':'ok','service':'rewards-api'}

    @app.get('/api/auth/status')
    def auth_status(db=Depends(get_db)):
        return {'setup_required':not bool(db.execute('SELECT 1 FROM parent_auth').fetchone())}

    @app.post('/api/auth/setup')
    def setup_pin(payload: PinInput, db=Depends(get_db)):
        if db.execute('SELECT 1 FROM parent_auth').fetchone():
            raise HTTPException(409,'家长 PIN 已设置')
        db.execute('INSERT INTO parent_auth VALUES (1,?)',(pin_hash(payload.pin),))
        audit(db,'pin_setup','家长完成首次设置')
        return issue_session(db)

    @app.post('/api/auth/parent')
    def login(payload: ParentLogin, db=Depends(get_db)):
        now = time.time()
        db.execute('DELETE FROM login_failures WHERE created_at<=?',(now-300,))
        if db.execute('SELECT COUNT(*) FROM login_failures').fetchone()[0]>=5:
            return JSONResponse(status_code=429,content={'detail':'尝试过多，请 5 分钟后再试'},headers={'Retry-After':'300'})
        auth = db.execute('SELECT pin_hash FROM parent_auth WHERE id=1').fetchone()
        if not auth:
            raise HTTPException(409,'请先设置家长 PIN')
        salt = auth['pin_hash'].split(':')[0]
        if not hmac.compare_digest(pin_hash(payload.pin,salt),auth['pin_hash']):
            db.execute('INSERT INTO login_failures VALUES (?)',(now,))
            return JSONResponse(status_code=401,content={'detail':'PIN 码不正确'})
        db.execute('DELETE FROM login_failures')
        return issue_session(db)

    @app.post('/api/auth/logout')
    def logout(token=Depends(parent), db=Depends(get_db)):
        db.execute('DELETE FROM sessions WHERE token_hash=?',(token,))
        return {'success':True}

    @app.post('/api/parent/pin')
    def change_pin(payload: PinInput, token=Depends(parent), db=Depends(get_db)):
        db.execute('UPDATE parent_auth SET pin_hash=? WHERE id=1',(pin_hash(payload.pin),))
        db.execute('DELETE FROM sessions')
        audit(db,'pin_changed','家长更换 PIN，所有会话已锁定')
        return {'success':True}

    @app.get('/api/dashboard/{child_id}')
    def dashboard(child_id: int, db=Depends(get_db)):
        child = child_exists(db,child_id)
        assets = [dict(r) for r in db.execute('''SELECT a.code,a.name,a.icon,a.color,a.active,ca.balance FROM child_assets ca
            JOIN asset_types a ON a.id=ca.asset_type_id WHERE ca.child_id=? ORDER BY a.id''',(child_id,))]
        total = sum(a['balance'] for a in assets if a['active'] and a['code'] in STAR_CODES)
        target = rules(db)['badge_ratio']
        life = db.execute("SELECT active FROM badges WHERE code='life'").fetchone()
        claims = db.execute('SELECT COUNT(*) FROM task_claims WHERE child_id=? AND reversed_at IS NULL',(child_id,)).fetchone()[0]
        badge_counts = badge_summary(db,child_id)
        available = sum(b['available_count'] for b in badge_counts)
        coupons = next(a['balance'] for a in assets if a['code']=='coupon')
        return {'child':child,'assets':assets,'badges':badge_counts,'rules':rules(db),'family_timezone':rules(db)['family_timezone'],
                'progress':{'current':min(total,target),'target':target,'total_stars':total,
                            'enabled':bool(life and life['active']), 'can_redeem':bool(life and life['active'] and total>=target)},
                'badge_progress':{'current':min(available,BADGES_PER_COUPON),'target':BADGES_PER_COUPON,
                                  'available':available,'can_redeem':available>=BADGES_PER_COUPON},
                'coupons':{'balance':coupons,'unit_value_fen':COUPON_VALUE_FEN,'total_value_fen':coupons*COUPON_VALUE_FEN,
                           'max_per_use':MAX_COUPONS_PER_USE,'max_value_per_use_fen':MAX_COUPONS_PER_USE*COUPON_VALUE_FEN},
                'growth':{'tasks_completed':claims}}

    @app.get('/api/tasks')
    def tasks(child_id: int=1, db=Depends(get_db)):
        child_exists(db,child_id)
        day = today(rules(db)['family_timezone'])
        result = [dict(r) for r in db.execute('''SELECT t.*,a.code AS asset_code,a.name AS asset_name,a.icon AS asset_icon,a.color,
            b.name AS badge_name,b.icon AS badge_icon,CASE WHEN tc.id IS NULL THEN 0 ELSE 1 END AS claimed_today
            FROM tasks t JOIN asset_types a ON a.id=t.asset_type_id LEFT JOIN badges b ON b.id=t.badge_id
            LEFT JOIN task_claims tc ON tc.task_id=t.id AND tc.child_id=? AND tc.claim_date=? AND tc.reversed_at IS NULL
            WHERE t.active=1 AND ((t.badge_id IS NULL AND a.active=1 AND a.code IN ('study_star','tidy_star','meal_star'))
                OR (b.active=1 AND b.code IN ('sports','fire','royal'))) ORDER BY t.id''',
            (child_id,day))]
        for task in result:
            if not task['badge_id']:
                task['claimed_today'] = int(star_claimed(db,child_id,day,task['asset_type_id']))
                task['amount'] = 1
        return result

    @app.post('/api/tasks/{task_id}/claim')
    def claim_task(task_id: int, payload: ClaimInput | None=None, child_id: int=1, token=Depends(parent), db=Depends(get_db)):
        child_exists(db,child_id)
        task = db.execute('SELECT * FROM tasks WHERE id=? AND active=1',(task_id,)).fetchone()
        if not task:
            raise HTTPException(404,'找不到任务')
        if task['badge_id']:
            badge = db.execute('SELECT * FROM badges WHERE id=? AND active=1',(task['badge_id'],)).fetchone()
            if not badge:
                raise HTTPException(409,'该徽章已停用')
            if badge['code'] not in ('sports','fire','royal'):
                raise HTTPException(409,'生活徽章只能用 5 枚星星代币兑换')
        elif not db.execute('SELECT 1 FROM asset_types WHERE id=? AND active=1',(task['asset_type_id'],)).fetchone():
            raise HTTPException(409,'该资产已停用')
        day = today(rules(db)['family_timezone'])
        if not task['badge_id']:
            asset = db.execute('SELECT code FROM asset_types WHERE id=?',(task['asset_type_id'],)).fetchone()
            if asset['code'] not in STAR_CODES:
                raise HTTPException(409,'金色代币条件未设置，暂不发放')
            if star_claimed(db,child_id,day,task['asset_type_id']):
                raise HTTPException(409,'今天这项星星代币已经发放，每项每天最多 1 枚')
        previous = db.execute('SELECT * FROM task_claims WHERE task_id=? AND child_id=? AND claim_date=?',(task_id,child_id,day)).fetchone()
        if previous and not previous['reversed_at']:
            raise HTTPException(409,'今天已经领取过这个任务啦')
        op = operation(db,child_id,'task',task['name'])
        if previous:
            db.execute('UPDATE task_claims SET reversed_at=NULL,operation_id=?,created_at=? WHERE id=?',(op,utc_now(),previous['id']))
        else:
            db.execute('INSERT INTO task_claims(task_id,child_id,claim_date,created_at,operation_id) VALUES (?,?,?,?,?)',(task_id,child_id,day,utc_now(),op))
        if task['badge_id']:
            for _ in range(task['amount']):
                db.execute('INSERT INTO child_badges(child_id,badge_id,reason,earned_at,operation_id,color) VALUES (?,?,?,?,?,?)',(child_id,badge['id'],task['name'],utc_now(),op,(payload.color if payload else None) or task['badge_color'] or badge['color']))
        else:
            change_asset(db,child_id,task['asset_type_id'],1,task['name'],op)
        audit(db,'task_claimed',f'operation:{op}')
        return {'success':True,'operation_id':op}

    @app.get('/api/badges')
    def badges(child_id: int=1, db=Depends(get_db)):
        child_exists(db,child_id)
        return badge_summary(db,child_id)

    @app.get('/api/badges/history')
    def badge_history(child_id: int=1, db=Depends(get_db)):
        child_exists(db,child_id)
        return [dict(r) for r in db.execute('SELECT cb.*,b.name,b.icon,b.code,b.active FROM child_badges cb JOIN badges b ON b.id=cb.badge_id WHERE cb.child_id=? ORDER BY cb.id DESC',(child_id,))]

    @app.post('/api/parent/conversions/stars')
    def stars_to_badge(payload: ConversionInput, token=Depends(parent), db=Depends(get_db)):
        child_exists(db,payload.child_id)
        badge = db.execute('SELECT * FROM badges WHERE id=? AND active=1',(payload.badge_id,)).fetchone()
        if not badge:
            raise HTTPException(404,'徽章不存在或已停用')
        if badge['code']!='life':
            raise HTTPException(422,'星星代币只能兑换生活徽章，其他徽章须完成家长设定的任务')
        cost = STARS_PER_LIFE_BADGE
        op = operation(db,payload.child_id,'stars_to_badge',f"兑换{badge['name']}")
        remaining = cost
        assets = db.execute('''SELECT ca.*,a.code FROM child_assets ca JOIN asset_types a ON a.id=ca.asset_type_id
            WHERE ca.child_id=? AND a.active=1 ORDER BY a.id''',(payload.child_id,)).fetchall()
        for asset in assets:
            if asset['code'] not in STAR_CODES:
                continue
            amount = min(remaining,asset['balance'])
            if amount:
                change_asset(db,payload.child_id,asset['asset_type_id'],-amount,f"兑换{badge['name']}",op)
                remaining -= amount
        if remaining:
            raise HTTPException(409,'星星不足，尚未达到兑换条件')
        db.execute('INSERT INTO child_badges(child_id,badge_id,reason,earned_at,operation_id,color) VALUES (?,?,?,?,?,?)',
                   (payload.child_id,badge['id'],f'{cost} 颗星星兑换',utc_now(),op,payload.color or badge['color']))
        audit(db,'stars_to_badge',f'operation:{op}')
        return {'success':True,'operation_id':op}

    @app.post('/api/parent/conversions/coupon')
    def badges_to_coupon(payload: ChildInput, token=Depends(parent), db=Depends(get_db)):
        child_exists(db,payload.child_id)
        return convert_badges_to_coupon(db,payload.child_id)

    @app.get('/api/shop')
    def shop(db=Depends(get_db)):
        return [dict(r) for r in db.execute('SELECT * FROM products WHERE active=1 AND price BETWEEN 1 AND 5 ORDER BY id')]

    @app.post('/api/redemptions')
    def request_redemption(payload: RedemptionRequest, db=Depends(get_db)):
        child_exists(db,payload.child_id)
        existing = db.execute("SELECT id FROM redemptions WHERE child_id=? AND product_id=? AND status='pending'",(payload.child_id,payload.product_id)).fetchone()
        if existing:
            return {'success':True,'id':existing['id'],'message':'这个礼物已经在等待家长确认啦'}
        product = db.execute('SELECT * FROM products WHERE id=? AND active=1',(payload.product_id,)).fetchone()
        if not product:
            raise HTTPException(404,'商品不存在或已下架')
        if not 1<=product['price']<=MAX_COUPONS_PER_USE:
            raise HTTPException(422,'单次最多使用 5 张兑换券')
        if payload.expected_product and any(product[key] != value for key,value in payload.expected_product.model_dump(exclude_unset=True).items()):
            raise HTTPException(409,'礼物信息已更新，请刷新礼物架后重新确认申请')
        item_id = db.execute('''INSERT INTO redemptions(child_id,product_id,requested_at,product_name,price,icon,coupon_value_fen,quoted_amount_fen,rule_version)
            VALUES (?,?,?,?,?,?,?,?,?)''',(payload.child_id,product['id'],utc_now(),product['name'],product['price'],product['icon'],COUPON_VALUE_FEN,product['cash_price_fen'],RULE_VERSION)).lastrowid
        return {'success':True,'id':item_id,'message':'兑换申请已送到家长控制台'}

    @app.get('/api/parent/summary')
    def summary(child_id: int=1, token=Depends(parent), db=Depends(get_db)):
        child_exists(db,child_id)
        return {'pending_redemptions':db.execute("SELECT COUNT(*) FROM redemptions WHERE child_id=? AND status='pending'",(child_id,)).fetchone()[0],
                'pending_coupon_requests':db.execute("SELECT COUNT(*) FROM coupon_requests WHERE child_id=? AND status='pending'",(child_id,)).fetchone()[0],
                'today_claims':db.execute('SELECT COUNT(*) FROM task_claims WHERE child_id=? AND claim_date=? AND reversed_at IS NULL',(child_id,today(rules(db)['family_timezone']))).fetchone()[0]}

    @app.get('/api/parent/redemptions')
    def redemptions(token=Depends(parent), db=Depends(get_db)):
        return [dict(r) for r in db.execute('SELECT r.*,c.name AS child_name FROM redemptions r JOIN children c ON c.id=r.child_id ORDER BY r.id DESC LIMIT 500')]

    @app.post('/api/parent/redemptions/{item_id}/{action}')
    def process_redemption(item_id: int, action: str, payload: SettlementInput | None=None, token=Depends(parent), db=Depends(get_db)):
        if action not in {'approve','reject'}:
            raise HTTPException(400,'不支持的操作')
        item = db.execute('SELECT * FROM redemptions WHERE id=?',(item_id,)).fetchone()
        if not item:
            raise HTTPException(404,'找不到兑换申请')
        if item['status']!='pending':
            raise HTTPException(409,'这笔申请已处理，请刷新页面')
        op = None
        if action=='approve':
            if not 1<=item['price']<=MAX_COUPONS_PER_USE:
                raise HTTPException(409,'旧申请超过 5 张上限，请拒绝后重新申请')
            if payload is None:
                raise HTTPException(422,'请填写实际消费金额并确认结算')
            count = payload.coupon_count if payload.coupon_count is not None else item['price']
            if not 1<=count<=MAX_COUPONS_PER_USE:
                raise HTTPException(422,'单次最多使用 5 张兑换券')
            value = count*COUPON_VALUE_FEN
            top_up = max(0,payload.actual_amount_fen-value)
            forfeited = max(0,value-payload.actual_amount_fen)
            if top_up and not payload.approve_top_up:
                raise HTTPException(409,'消费金额高于券总额，请家长明确同意补足差额后确认')
            op = operation(db,item['child_id'],'redemption',item['product_name'])
            coupon = db.execute("SELECT id FROM asset_types WHERE code='coupon'").fetchone()[0]
            change_asset(db,item['child_id'],coupon,-count,item['product_name'],op)
            db.execute('''UPDATE redemptions SET coupons_used=?,coupon_value_fen=?,actual_amount_fen=?,parent_top_up_fen=?,
                forfeited_fen=?,settlement_note=?,rule_version=? WHERE id=?''',
                (count,COUPON_VALUE_FEN,payload.actual_amount_fen,top_up,forfeited,payload.note,RULE_VERSION,item_id))
        status = 'approved' if action=='approve' else 'rejected'
        db.execute('UPDATE redemptions SET status=?,approved_at=?,operation_id=? WHERE id=?',(status,utc_now(),op,item_id))
        audit(db,'redemption_'+status,f'redemption:{item_id}')
        return {'success':True,'status':status,'operation_id':op}

    @app.post('/api/parent/adjust')
    def adjust(payload: AdjustmentInput, token=Depends(parent), db=Depends(get_db)):
        child_exists(db,payload.child_id)
        asset = db.execute('SELECT id FROM asset_types WHERE code=? AND active=1',(payload.asset_code,)).fetchone()
        if not asset:
            raise HTTPException(404,'找不到可用资产')
        if payload.asset_code=='gold_star' and payload.delta>0:
            raise HTTPException(422,'金色代币尚未设置获得条件，暂不发放')
        current = db.execute('SELECT balance FROM child_assets WHERE child_id=? AND asset_type_id=?', (payload.child_id,asset['id'])).fetchone()
        if payload.expected_balance is not None and (not current or current['balance'] != payload.expected_balance):
            raise HTTPException(409,'余额已变化，请刷新并重新确认调整')
        op = operation(db,payload.child_id,'manual',payload.reason)
        change_asset(db,payload.child_id,asset['id'],payload.delta,payload.reason,op)
        audit(db,'asset_adjusted',f'operation:{op}')
        return {'success':True,'operation_id':op}

    @app.post('/api/parent/badge-adjust')
    def adjust_badges(payload: BadgeAdjustmentInput, token=Depends(parent), db=Depends(get_db)):
        child_exists(db,payload.child_id)
        badge = db.execute('SELECT id,name FROM badges WHERE id=?',(payload.badge_id,)).fetchone()
        if not badge:
            raise HTTPException(404,'找不到徽章类型')
        current = db.execute('''SELECT COUNT(*) FROM child_badges WHERE child_id=? AND badge_id=? AND color=?
            AND reversed_at IS NULL AND spent_operation_id IS NULL''',
            (payload.child_id,payload.badge_id,payload.color)).fetchone()[0]
        if current != payload.expected_count:
            raise HTTPException(409,'该颜色徽章数量已变化，请刷新后重新核对')
        op = operation(db,payload.child_id,'manual',payload.reason)
        if payload.delta > 0:
            db.executemany('''INSERT INTO child_badges(child_id,badge_id,reason,earned_at,operation_id,color)
                VALUES (?,?,?,?,?,?)''',[(payload.child_id,payload.badge_id,payload.reason,utc_now(),op,payload.color)
                for _ in range(payload.delta)])
        else:
            count = -payload.delta
            ids = [row['id'] for row in db.execute('''SELECT id FROM child_badges WHERE child_id=? AND badge_id=? AND color=?
                AND reversed_at IS NULL AND spent_operation_id IS NULL ORDER BY id LIMIT ?''',
                (payload.child_id,payload.badge_id,payload.color,count)).fetchall()]
            if len(ids) < count:
                raise HTTPException(409,'该颜色可用徽章不足，调整未执行')
            db.executemany('UPDATE child_badges SET spent_operation_id=? WHERE id=?',[(op,badge_id) for badge_id in ids])
        audit(db,'badge_adjusted',f'operation:{op}')
        return {'success':True,'operation_id':op}

    @app.get('/api/parent/operations')
    def operations(child_id: int=1, token=Depends(parent), db=Depends(get_db)):
        child_exists(db,child_id)
        return [dict(r) for r in db.execute('SELECT * FROM operations WHERE child_id=? ORDER BY id DESC LIMIT 500',(child_id,))]

    @app.get('/api/parent/ledger')
    def ledger(child_id: int=1, token=Depends(parent), db=Depends(get_db)):
        child_exists(db,child_id)
        return [dict(r) for r in db.execute('SELECT l.*,a.name AS asset_name,a.icon FROM ledger l JOIN asset_types a ON a.id=l.asset_type_id WHERE l.child_id=? ORDER BY l.id DESC LIMIT 1000',(child_id,))]

    @app.post('/api/parent/operations/{op_id}/reverse')
    def reverse(op_id: int, token=Depends(parent), db=Depends(get_db)):
        preview = reversal_preview(db,op_id)
        if not preview['can_reverse']:
            raise HTTPException(409,'；'.join(preview['blockers']))
        source = preview['operation']
        op = operation(db,source['child_id'],'reversal','撤销：'+source['reason'],op_id)
        for entry in db.execute('SELECT * FROM ledger WHERE operation_id=? ORDER BY id',(op_id,)).fetchall():
            change_asset(db,source['child_id'],entry['asset_type_id'],-entry['delta'],'撤销：'+source['reason'],op)
        stamp = utc_now()
        db.execute('UPDATE child_badges SET reversed_at=? WHERE operation_id=?',(stamp,op_id))
        db.execute('UPDATE child_badges SET spent_operation_id=NULL WHERE spent_operation_id=?',(op_id,))
        db.execute('UPDATE task_claims SET reversed_at=? WHERE operation_id=?',(stamp,op_id))
        db.execute("UPDATE redemptions SET status='reversed' WHERE operation_id=?",(op_id,))
        db.execute("UPDATE coupon_requests SET status='reversed' WHERE operation_id=?",(op_id,))
        db.execute('UPDATE operations SET reversed_at=? WHERE id=?',(stamp,op_id))
        audit(db,'operation_reversed',f'operation:{op_id},reversal:{op}')
        return {'success':True,'operation_id':op}

    @app.get('/api/parent/rules')
    def get_rules(token=Depends(parent), db=Depends(get_db)):
        return rules(db)

    @app.put('/api/parent/rules')
    def update_rules(payload: RulesInput, token=Depends(parent), db=Depends(get_db)):
        for key,value in payload.model_dump().items():
            db.execute('UPDATE settings SET value=? WHERE key=?',(str(value),key))
        db.execute("UPDATE badges SET threshold=? WHERE code='life'",(payload.badge_ratio,))
        audit(db,'rules_changed',payload.model_dump_json())
        return rules(db)

    @app.get('/api/parent/products')
    def all_products(token=Depends(parent), db=Depends(get_db)):
        return [dict(r) for r in db.execute('SELECT * FROM products ORDER BY id')]

    def save_product(payload, db, item_id=None):
        image = payload.image_data
        if item_id is not None and 'image_data' not in payload.model_fields_set:
            old = db.execute('SELECT image_data FROM products WHERE id=?',(item_id,)).fetchone()
            if not old:
                raise HTTPException(404,'商品不存在')
            image = old['image_data']
        values = (payload.name,payload.description,payload.icon,payload.price,int(payload.active),payload.cash_price_fen,image)
        if item_id is None:
            item_id = db.execute('INSERT INTO products(name,description,icon,price,active,cash_price_fen,image_data) VALUES (?,?,?,?,?,?,?)',values).lastrowid
        elif not db.execute('UPDATE products SET name=?,description=?,icon=?,price=?,active=?,cash_price_fen=?,image_data=? WHERE id=?',values+(item_id,)).rowcount:
            raise HTTPException(404,'商品不存在')
        audit(db,'product_saved',f'product:{item_id}')
        return {'success':True,'id':item_id}

    @app.patch('/api/parent/products/{item_id}/availability')
    def product_availability(item_id: int, payload: AvailabilityInput, token=Depends(parent), db=Depends(get_db)):
        product = db.execute('SELECT price FROM products WHERE id=?',(item_id,)).fetchone()
        if not product:
            raise HTTPException(404,'商品不存在')
        if payload.active and not 1 <= product['price'] <= MAX_COUPONS_PER_USE:
            raise HTTPException(422,'请先将所需兑换券改为 1–5 张再上架')
        db.execute('UPDATE products SET active=? WHERE id=?',(int(payload.active),item_id))
        audit(db,'product_published' if payload.active else 'product_unlisted',f'product:{item_id}')
        return {'success':True,'id':item_id,'active':payload.active}

    @app.post('/api/parent/products')
    def add_product(payload: ProductInput, token=Depends(parent), db=Depends(get_db)):
        return save_product(payload,db)

    @app.put('/api/parent/products/{item_id}')
    def update_product(item_id: int, payload: ProductInput, token=Depends(parent), db=Depends(get_db)):
        return save_product(payload,db,item_id)

    @app.get('/api/parent/tasks')
    def all_tasks(token=Depends(parent), db=Depends(get_db)):
        return [dict(r) for r in db.execute('SELECT t.*,a.code AS asset_code FROM tasks t JOIN asset_types a ON a.id=t.asset_type_id ORDER BY t.id')]

    def save_task(payload, db, item_id=None):
        asset = db.execute('SELECT id FROM asset_types WHERE code=?',(payload.asset_code,)).fetchone()
        if not asset:
            raise HTTPException(404,'资产不存在')
        if not payload.badge_id and (payload.asset_code not in STAR_CODES or payload.amount!=1):
            raise HTTPException(422,'日常事项只发放橙、绿或红色星星，每项每天 1 枚；金色暂不发放')
        if payload.badge_id and not db.execute('SELECT 1 FROM badges WHERE id=?',(payload.badge_id,)).fetchone():
            raise HTTPException(404,'徽章不存在')
        if payload.badge_id:
            badge = db.execute('SELECT code FROM badges WHERE id=?',(payload.badge_id,)).fetchone()
            if badge['code'] not in ('sports','fire','royal'):
                raise HTTPException(422,'生活徽章只能由 5 枚星星代币兑换获得')
        values = (payload.name,payload.description,asset['id'],payload.amount,int(payload.active),payload.badge_id,payload.badge_color)
        if item_id is None:
            item_id = db.execute('INSERT INTO tasks(name,description,asset_type_id,amount,active,badge_id,badge_color) VALUES (?,?,?,?,?,?,?)',values).lastrowid
        elif not db.execute('UPDATE tasks SET name=?,description=?,asset_type_id=?,amount=?,active=?,badge_id=?,badge_color=? WHERE id=?',values+(item_id,)).rowcount:
            raise HTTPException(404,'任务不存在')
        audit(db,'task_saved',f'task:{item_id}')
        return {'success':True,'id':item_id}

    @app.post('/api/parent/tasks')
    def add_task(payload: TaskInput, token=Depends(parent), db=Depends(get_db)):
        return save_task(payload,db)

    @app.put('/api/parent/tasks/{item_id}')
    def update_task(item_id: int, payload: TaskInput, token=Depends(parent), db=Depends(get_db)):
        return save_task(payload,db,item_id)

    @app.get('/api/parent/badges')
    def all_badges(token=Depends(parent), db=Depends(get_db)):
        return [dict(r) for r in db.execute('SELECT * FROM badges ORDER BY id')]

    def save_badge(payload, db, item_id=None):
        collision = db.execute('SELECT id FROM badges WHERE code=?',(payload.code,)).fetchone()
        if collision and collision['id']!=item_id:
            raise HTTPException(409,'徽章代码已存在')
        values = (payload.code,payload.name,payload.description,payload.icon,payload.color,payload.threshold,int(payload.active))
        if item_id is None:
            item_id = db.execute('INSERT INTO badges(code,name,description,icon,color,threshold,active) VALUES (?,?,?,?,?,?,?)',values).lastrowid
        else:
            old = db.execute('SELECT code FROM badges WHERE id=?',(item_id,)).fetchone()
            if not old:
                raise HTTPException(404,'徽章不存在')
            if old['code']!=payload.code:
                raise HTTPException(409,'四种徽章的类型不能修改')
            db.execute('UPDATE badges SET code=?,name=?,description=?,icon=?,color=?,threshold=?,active=? WHERE id=?',values+(item_id,))
        if payload.code=='life':
            db.execute("UPDATE settings SET value=? WHERE key='badge_ratio'",(str(payload.threshold),))
        audit(db,'badge_saved',f'badge:{item_id}')
        return {'success':True,'id':item_id}

    @app.post('/api/parent/badges')
    def add_badge(payload: BadgeInput, token=Depends(parent), db=Depends(get_db)):
        return save_badge(payload,db)

    @app.put('/api/parent/badges/{item_id}')
    def update_badge(item_id: int, payload: BadgeInput, token=Depends(parent), db=Depends(get_db)):
        return save_badge(payload,db,item_id)

    from backups import register_backups
    from backpack import register_backpack
    from shop import register_shop
    from parent_views import register_parent_views, reversal_preview
    from coupon_requests import register_coupon_requests
    register_backpack(app,get_db)
    register_shop(app,get_db)
    register_parent_views(app,get_db,parent)
    register_coupon_requests(app,get_db,parent,child_exists,convert_badges_to_coupon,audit)
    register_backups(app,get_db,parent,path,RulesInput,rules,audit)
    return app


app = create_app()
