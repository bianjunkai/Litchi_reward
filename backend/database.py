"""SQLite schema, additive upgrades, and explicit transactions."""
import hashlib
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from reward_rules import RULE_VERSION, SUNFLOWER_MIGRATION_KEY, migrate_sunflower_badge, normalize_legacy_data


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def pin_hash(pin, salt=None):
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac('sha256', pin.encode(), bytes.fromhex(salt), 260_000).hex()
    return f'{salt}:{digest}'


def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=15000')
    return db


@contextmanager
def transaction(path, write=False):
    db = connect(path)
    try:
        db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS children (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, avatar TEXT NOT NULL DEFAULT '🍄');
CREATE TABLE IF NOT EXISTS asset_types (
 id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
 icon TEXT NOT NULL, color TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'currency', active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS child_assets (
 child_id INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE,
 asset_type_id INTEGER NOT NULL REFERENCES asset_types(id), balance INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(child_id,asset_type_id));
CREATE TABLE IF NOT EXISTS tasks (
 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
 asset_type_id INTEGER NOT NULL REFERENCES asset_types(id), amount INTEGER NOT NULL DEFAULT 1,
 active INTEGER NOT NULL DEFAULT 1, badge_id INTEGER REFERENCES badges(id), badge_color TEXT);
CREATE TABLE IF NOT EXISTS task_claims (
 id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER NOT NULL REFERENCES tasks(id),
 child_id INTEGER NOT NULL REFERENCES children(id), claim_date TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL, operation_id INTEGER REFERENCES operations(id), reversed_at TEXT,
 UNIQUE(task_id,child_id,claim_date));
CREATE TABLE IF NOT EXISTS badges (
 id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '', icon TEXT NOT NULL, color TEXT NOT NULL,
 threshold INTEGER NOT NULL DEFAULT 5, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS child_badges (
 id INTEGER PRIMARY KEY AUTOINCREMENT, child_id INTEGER NOT NULL REFERENCES children(id),
 badge_id INTEGER NOT NULL REFERENCES badges(id), reason TEXT NOT NULL DEFAULT '', earned_at TEXT NOT NULL,
 operation_id INTEGER REFERENCES operations(id), spent_operation_id INTEGER REFERENCES operations(id),
 reversed_at TEXT, color TEXT NOT NULL DEFAULT '#f0aa37');
CREATE TABLE IF NOT EXISTS coupon_requests (
 id INTEGER PRIMARY KEY AUTOINCREMENT, child_id INTEGER NOT NULL REFERENCES children(id),
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected','reversed')),
 requested_at TEXT NOT NULL, processed_at TEXT, operation_id INTEGER UNIQUE REFERENCES operations(id));
CREATE TABLE IF NOT EXISTS coupon_request_badges (
 request_id INTEGER NOT NULL REFERENCES coupon_requests(id), child_badge_id INTEGER NOT NULL REFERENCES child_badges(id),
 PRIMARY KEY(request_id,child_badge_id));
CREATE UNIQUE INDEX IF NOT EXISTS one_pending_coupon_request ON coupon_requests(child_id) WHERE status='pending';
CREATE TABLE IF NOT EXISTS products (
 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
 icon TEXT NOT NULL DEFAULT '🎁', price INTEGER NOT NULL, active INTEGER NOT NULL DEFAULT 1, cash_price_fen INTEGER,
 image_data TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS redemptions (
 id INTEGER PRIMARY KEY AUTOINCREMENT, child_id INTEGER NOT NULL REFERENCES children(id),
 product_id INTEGER NOT NULL REFERENCES products(id), status TEXT NOT NULL DEFAULT 'pending',
 requested_at TEXT NOT NULL, approved_at TEXT, operation_id INTEGER REFERENCES operations(id),
 product_name TEXT NOT NULL DEFAULT '', price INTEGER NOT NULL DEFAULT 1, icon TEXT NOT NULL DEFAULT '🎁',
 coupon_value_fen INTEGER, coupons_used INTEGER, actual_amount_fen INTEGER, parent_top_up_fen INTEGER,
 forfeited_fen INTEGER, quoted_amount_fen INTEGER, settlement_note TEXT NOT NULL DEFAULT '', rule_version TEXT NOT NULL DEFAULT 'legacy');
CREATE TABLE IF NOT EXISTS operations (
 id INTEGER PRIMARY KEY AUTOINCREMENT, child_id INTEGER NOT NULL REFERENCES children(id),
 kind TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL, reversed_at TEXT,
 reversal_of INTEGER UNIQUE REFERENCES operations(id), rule_version TEXT NOT NULL DEFAULT 'legacy');
CREATE TABLE IF NOT EXISTS ledger (
 id INTEGER PRIMARY KEY AUTOINCREMENT, child_id INTEGER NOT NULL REFERENCES children(id),
 asset_type_id INTEGER NOT NULL REFERENCES asset_types(id), delta INTEGER NOT NULL,
 reason TEXT NOT NULL, reference_type TEXT NOT NULL DEFAULT '', reference_id INTEGER,
 created_at TEXT NOT NULL, operation_id INTEGER REFERENCES operations(id));
CREATE TABLE IF NOT EXISTS audit_logs (
 id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS parent_auth (id INTEGER PRIMARY KEY CHECK(id=1), pin_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, expires_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS login_failures (created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS ledger_child ON ledger(child_id,asset_type_id);
CREATE TRIGGER IF NOT EXISTS nonnegative_insert BEFORE INSERT ON child_assets
 WHEN NEW.balance<0 BEGIN SELECT RAISE(ABORT,'negative balance'); END;
CREATE TRIGGER IF NOT EXISTS nonnegative_update BEFORE UPDATE OF balance ON child_assets
 WHEN NEW.balance<0 BEGIN SELECT RAISE(ABORT,'negative balance'); END;
"""


def init_db(path, initial_pin=None):
    db = connect(path)
    try:
        request_safety_path = Path(str(path)+'.pre-coupon-requests.db')
        old_badges = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='child_badges'").fetchone()
        has_requests = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='coupon_requests'").fetchone()
        if old_badges and not has_requests and not request_safety_path.exists():
            target = sqlite3.connect(str(request_safety_path))
            try:
                db.backup(target)
            finally:
                target.close()
        product_columns = {r['name'] for r in db.execute('PRAGMA table_info(products)')}
        image_safety_path = Path(str(path)+'.pre-product-images.db')
        if product_columns and 'image_data' not in product_columns and not image_safety_path.exists():
            target = sqlite3.connect(str(image_safety_path))
            try:
                db.backup(target)
            finally:
                target.close()
        has_settings = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='settings'").fetchone()
        family_safety_path = Path(str(path)+'.pre-family-v1.db')
        if has_settings and not db.execute("SELECT 1 FROM settings WHERE key='family_rules_version'").fetchone() and not family_safety_path.exists():
            target = sqlite3.connect(str(family_safety_path))
            try:
                db.backup(target)
            finally:
                target.close()
        legacy_columns = {r['name'] for r in db.execute('PRAGMA table_info(ledger)')}
        safety_path = Path(str(path)+'.pre-v2.db')
        if legacy_columns and 'operation_id' not in legacy_columns and not safety_path.exists():
            target = sqlite3.connect(str(safety_path))
            try:
                db.backup(target)
            finally:
                target.close()
        db.executescript(SCHEMA)
        upgrades = {
            'tasks': {'badge_id':'INTEGER REFERENCES badges(id)', 'badge_color':'TEXT'},
            'products': {'cash_price_fen':'INTEGER', 'image_data':"TEXT NOT NULL DEFAULT ''"},
            'operations': {'rule_version':"TEXT NOT NULL DEFAULT 'legacy'"},
            'task_claims': {'operation_id':'INTEGER REFERENCES operations(id)', 'reversed_at':'TEXT'},
            'child_badges': {'operation_id':'INTEGER REFERENCES operations(id)',
                             'spent_operation_id':'INTEGER REFERENCES operations(id)',
                             'reversed_at':'TEXT', 'color':"TEXT NOT NULL DEFAULT '#f0aa37'"},
            'redemptions': {'operation_id':'INTEGER REFERENCES operations(id)',
                            'product_name':"TEXT NOT NULL DEFAULT ''", 'price':'INTEGER NOT NULL DEFAULT 1',
                            'icon':"TEXT NOT NULL DEFAULT '🎁'", 'coupon_value_fen':'INTEGER',
                            'coupons_used':'INTEGER', 'actual_amount_fen':'INTEGER', 'parent_top_up_fen':'INTEGER',
                            'forfeited_fen':'INTEGER', 'quoted_amount_fen':'INTEGER', 'settlement_note':"TEXT NOT NULL DEFAULT ''",
                            'rule_version':"TEXT NOT NULL DEFAULT 'legacy'"},
            'ledger': {'operation_id':'INTEGER REFERENCES operations(id)'},
        }
        for table, columns in upgrades.items():
            existing = {r['name'] for r in db.execute(f'PRAGMA table_info({table})')}
            for column, spec in columns.items():
                if column not in existing:
                    db.execute(f'ALTER TABLE {table} ADD COLUMN {column} {spec}')
        db.commit()
        sunflower_safety_path = Path(str(path)+'.pre-sunflower-v1.db')
        if (db.execute("SELECT 1 FROM badges WHERE code='fire'").fetchone()
                and not db.execute('SELECT 1 FROM settings WHERE key=?',(SUNFLOWER_MIGRATION_KEY,)).fetchone()
                and not sunflower_safety_path.exists()):
            target = sqlite3.connect(str(sunflower_safety_path))
            try:
                db.backup(target)
            finally:
                target.close()
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT 1 FROM children').fetchone():
            db.execute("INSERT INTO children(name) VALUES ('小勇士')")
            db.executemany('INSERT INTO asset_types(code,name,icon,color,active) VALUES (?,?,?,?,?)', [
                ('study_star','学习星星','🟠','#f08a24',1), ('tidy_star','整理星星','🟢','#41a85f',1),
                ('meal_star','吃饭星星','🔴','#e55353',1), ('gold_star','金色星星','🟡','#e4b83f',0),
                ('coupon','兑换券','🎟️','#6b7cff',1),
            ])
            db.execute('INSERT INTO child_assets SELECT c.id,a.id,0 FROM children c CROSS JOIN asset_types a')
            for name, description, code in [('认真学习','好好学习、认真读书','study_star'),
                                            ('整理物品','每天收拾桌子和自己的物品','tidy_star'),
                                            ('按时吃饭','不拖沓，按时吃完饭','meal_star')]:
                db.execute('INSERT INTO tasks(name,description,asset_type_id) VALUES (?,?,(SELECT id FROM asset_types WHERE code=?))',(name,description,code))
            db.executemany('INSERT INTO badges(code,name,description,icon,color,threshold,active) VALUES (?,?,?,?,?,?,?)', [
                ('sports','体育徽章','坚持运动，身体棒棒！','🍄','#4eb478',5,1),
                ('life','生活徽章','自己的事情自己做！','⭐','#f0aa37',5,1),
                ('fire','太阳花徽章','认真学习、专心阅读，集齐 5 颗橙色学习星星兑换。','🌻','#f0aa37',5,1),
                ('royal','预留徽章 B','条件由家长定义，启用前不参与兑换','👑','#d4af37',5,0),
            ])
            db.execute("INSERT INTO tasks(name,description,asset_type_id,badge_id) VALUES ('运动打卡','完成家长约定的运动目标',(SELECT id FROM asset_types WHERE code='study_star'),(SELECT id FROM badges WHERE code='sports'))")
            db.executemany('INSERT INTO products(name,description,icon,price) VALUES (?,?,?,?)', [
                ('木马王国门票','和家人一起去玩吧','🎠',1), ('小天才充值 39.9 元','由家长确认后充值','⌚',1),
                ('自选小玩具','挑一个喜欢的小礼物','🧸',2), ('周末游乐园','周末冒险开启！','🎡',3),
                ('神秘大奖','打开才知道是什么','🎁',5),
            ])
        for key,value in [('badge_ratio','5'),('badges_per_coupon','5'),('family_timezone','Asia/Shanghai')]:
            db.execute('INSERT OR IGNORE INTO settings VALUES (?,?)',(key,value))
        db.execute("UPDATE redemptions SET product_name=(SELECT name FROM products WHERE id=product_id),price=(SELECT price FROM products WHERE id=product_id),icon=(SELECT icon FROM products WHERE id=product_id) WHERE product_name=''")
        # One-time legacy reconciliation; never hide future ledger corruption at restart.
        if not db.execute("SELECT 1 FROM settings WHERE key='ledger_upgrade_v2'").fetchone():
            for row in db.execute('''SELECT ca.*,COALESCE(SUM(l.delta),0) AS recorded FROM child_assets ca
                LEFT JOIN ledger l ON l.child_id=ca.child_id AND l.asset_type_id=ca.asset_type_id
                GROUP BY ca.child_id,ca.asset_type_id''').fetchall():
                difference = row['balance']-row['recorded']
                if difference:
                    db.execute("INSERT INTO ledger(child_id,asset_type_id,delta,reason,reference_type,created_at) VALUES (?,?,?,'旧版本余额对账补录（原始原因未知）','opening_balance',?)",(row['child_id'],row['asset_type_id'],difference,utc_now()))
            db.execute("INSERT INTO settings VALUES ('ledger_upgrade_v2','done')")
            db.execute("UPDATE badges SET threshold=(SELECT CAST(value AS INTEGER) FROM settings WHERE key='badge_ratio') WHERE code='life'")
        if not db.execute("SELECT 1 FROM settings WHERE key='family_rules_version'").fetchone():
            tables = {t:[dict(r) for r in db.execute(f'SELECT * FROM {t}')] for t in ('badges','asset_types','tasks','products')}
            normalize_legacy_data(tables)
            for table, columns in [('badges',('threshold','active','color','name')),('asset_types',('active',)),
                                   ('tasks',('amount','active','description','badge_color')),('products',('active',))]:
                for row in tables[table]:
                    db.execute(f"UPDATE {table} SET {','.join(c+'=?' for c in columns)} WHERE id=?",tuple(row[c] for c in columns)+(row['id'],))
            db.execute("UPDATE settings SET value='5' WHERE key IN ('badge_ratio','badges_per_coupon')")
            db.execute("INSERT INTO settings VALUES ('family_rules_version',?)",(RULE_VERSION,))
            db.execute("INSERT INTO audit_logs(action,detail,created_at) VALUES ('family_rules_corrected','仅修正后续规则：5 代币换生活徽章；5 已启用徽章换券；每券 3990 分，每次最多 5 张。历史资产和扣款保留。',?)",(utc_now(),))
        tables = {table:[dict(row) for row in db.execute(f'SELECT * FROM {table}')]
                  for table in ('badges','tasks','settings')}
        if migrate_sunflower_badge(tables):
            for badge in tables['badges']:
                if badge['code'] == 'fire':
                    db.execute('UPDATE badges SET name=?,description=?,icon=?,active=? WHERE id=?',
                               (badge['name'],badge['description'],badge['icon'],badge['active'],badge['id']))
            for task in tables['tasks']:
                db.execute('UPDATE tasks SET active=? WHERE id=?',(task['active'],task['id']))
            db.execute('INSERT INTO settings(key,value) VALUES (?,?)',(SUNFLOWER_MIGRATION_KEY,'done'))
            db.execute("INSERT INTO audit_logs(action,detail,created_at) VALUES ('sunflower_badge_enabled','第三种徽章启用为太阳花学习徽章；5 颗橙色星星兑换，绿色／红色星星仅兑换生活徽章。保留既有余额与历史徽章。',?)",(utc_now(),))
        if initial_pin and not db.execute('SELECT 1 FROM parent_auth').fetchone():
            if not initial_pin.isdigit() or not 6<=len(initial_pin)<=12:
                raise ValueError('PARENT_PIN must contain 6–12 digits; omit it for first-time setup')
            db.execute('INSERT INTO parent_auth VALUES (1,?)',(pin_hash(initial_pin),))
        db.commit()
    finally:
        db.close()
