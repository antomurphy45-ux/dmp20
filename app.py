
import json, os, secrets, sqlite3, hashlib, hmac, base64, mimetypes, io, csv, shutil, zipfile, tempfile, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote, parse_qs as _parse_qs
from pathlib import Path
from datetime import date, timedelta

BASE=Path(__file__).parent
DEFAULT_DATA_DIR=BASE/"data"
DEFAULT_DB=DEFAULT_DATA_DIR/"construction_control.db"
LEGACY_DB=BASE/"construction_control.db"
_env_db=os.getenv("CONSTRUCTION_CONTROL_DB")
if _env_db:
    DB_PATH=Path(_env_db).resolve()
else:
    # One canonical local database path. If an older build used the root DB,
    # migrate it once rather than silently creating a second empty database.
    DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    if LEGACY_DB.exists() and not DEFAULT_DB.exists():
        try: shutil.copy2(LEGACY_DB, DEFAULT_DB)
        except Exception: pass
    DB_PATH=DEFAULT_DB.resolve()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
# No-disk Render bootstrap: if the configured runtime DB is absent, seed it
# from the packaged 565 KB baseline database. Never overwrite an existing DB.
BUNDLED_DB=BASE/"render_seed.db"
if _env_db and DB_PATH != BUNDLED_DB and not DB_PATH.exists() and BUNDLED_DB.exists():
    try: shutil.copy2(BUNDLED_DB, DB_PATH)
    except Exception: pass
STATIC=(BASE/"static").resolve()
UPLOADS=Path(os.getenv("CONSTRUCTION_CONTROL_UPLOADS", str(DEFAULT_DATA_DIR/"uploads"))).resolve()
UPLOADS.mkdir(parents=True, exist_ok=True)
BACKUPS=Path(os.getenv("CONSTRUCTION_CONTROL_BACKUPS", str(DEFAULT_DATA_DIR/"backups"))).resolve()
BACKUPS.mkdir(parents=True, exist_ok=True)
RESTORE_LOCK=threading.RLock()
SESSION_HOURS=max(1, int(os.getenv("SESSION_HOURS", "8")))
PORT=int(os.getenv("PORT", "3000"))

SCHEMA="""
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS companies(
 id TEXT PRIMARY KEY, name TEXT NOT NULL, country TEXT NOT NULL,
 tier TEXT NOT NULL, logo_url TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS company_settings(
 company_id TEXT PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
 accent_color TEXT NOT NULL DEFAULT '#2563eb', sidebar_color TEXT NOT NULL DEFAULT '#0f172a',
 background_color TEXT NOT NULL DEFAULT '#f1f5f9', card_color TEXT NOT NULL DEFAULT '#ffffff',
 text_color TEXT NOT NULL DEFAULT '#0f172a', density TEXT NOT NULL DEFAULT 'comfortable',
 dashboard_default TEXT NOT NULL DEFAULT 'management', updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS users(
 id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id),
 name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
 active INTEGER NOT NULL DEFAULT 1, role TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS roles(
 id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id),
 name TEXT NOT NULL, access_level INTEGER NOT NULL DEFAULT 1,
 parent_role_id TEXT REFERENCES roles(id), UNIQUE(company_id,name));
CREATE TABLE IF NOT EXISTS permissions(
 role_id TEXT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
 module TEXT NOT NULL, action TEXT NOT NULL, allowed INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(role_id,module,action));
CREATE TABLE IF NOT EXISTS org_levels(
 id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
 name TEXT NOT NULL, parent_id TEXT REFERENCES org_levels(id), UNIQUE(company_id,name));
CREATE TABLE IF NOT EXISTS user_levels(
 user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
 level_id TEXT NOT NULL REFERENCES org_levels(id));
CREATE TABLE IF NOT EXISTS projects(
 id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
 name TEXT NOT NULL, level_id TEXT REFERENCES org_levels(id), manloader REAL NOT NULL DEFAULT 0,
 start_date TEXT, finish_date TEXT, client_name TEXT NOT NULL DEFAULT '',
 site_address TEXT NOT NULL DEFAULT '', scope_ref TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS project_access(
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 PRIMARY KEY(user_id,project_id));
CREATE TABLE IF NOT EXISTS sessions(
 token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 expires_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS audit(
 id INTEGER PRIMARY KEY AUTOINCREMENT, company_id TEXT NOT NULL REFERENCES companies(id),
 user_id TEXT, action TEXT NOT NULL, target TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS module_records(
 id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
 project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, module TEXT NOT NULL,
 title TEXT NOT NULL, data_json TEXT NOT NULL DEFAULT "{}", created_by TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS idx_module_records_scope ON module_records(company_id,project_id,module);
CREATE TABLE IF NOT EXISTS bulk_imports(
 id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
 project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, module TEXT NOT NULL,
 filename TEXT NOT NULL, rows_read INTEGER NOT NULL, rows_imported INTEGER NOT NULL,
 rows_rejected INTEGER NOT NULL, errors_json TEXT NOT NULL DEFAULT '[]',
 created_by TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS idx_bulk_imports_scope ON bulk_imports(company_id,project_id,module);
CREATE TABLE IF NOT EXISTS attachments(
 id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
 project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, record_id TEXT,
 filename TEXT NOT NULL, stored_name TEXT NOT NULL UNIQUE, mime_type TEXT NOT NULL, size_bytes INTEGER NOT NULL,
 uploaded_by TEXT REFERENCES users(id), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS idx_attachments_scope ON attachments(company_id,project_id);
CREATE TABLE IF NOT EXISTS workflows(
 id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
 project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, record_id TEXT NOT NULL,
 module TEXT NOT NULL, requested_by TEXT REFERENCES users(id), approver_user_id TEXT REFERENCES users(id),
 status TEXT NOT NULL DEFAULT 'Pending', decision_note TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, decided_at TEXT);
CREATE INDEX IF NOT EXISTS idx_workflows_scope ON workflows(company_id,project_id,status);
CREATE TABLE IF NOT EXISTS notifications(
 id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
 type TEXT NOT NULL, title TEXT NOT NULL, message TEXT NOT NULL, read_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(company_id,user_id,read_at,created_at);
CREATE TABLE IF NOT EXISTS plans(
 id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
 project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, name TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'Draft', baseline INTEGER NOT NULL DEFAULT 0,
 created_by TEXT REFERENCES users(id), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS plan_tasks(
 id TEXT PRIMARY KEY, plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
 project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, parent_id TEXT REFERENCES plan_tasks(id) ON DELETE SET NULL,
 name TEXT NOT NULL, start_date TEXT NOT NULL, finish_date TEXT NOT NULL, percent_complete INTEGER NOT NULL DEFAULT 0,
 planned_men REAL NOT NULL DEFAULT 0, predecessor_id TEXT REFERENCES plan_tasks(id) ON DELETE SET NULL,
 milestone INTEGER NOT NULL DEFAULT 0, notes TEXT NOT NULL DEFAULT '',
 dependency_type TEXT NOT NULL DEFAULT 'FS', lag_days INTEGER NOT NULL DEFAULT 0,
 activity_id TEXT, actual_start TEXT, actual_finish TEXT, baseline_start TEXT, baseline_finish TEXT,
 task_status TEXT NOT NULL DEFAULT 'Starting', held_up_reason TEXT NOT NULL DEFAULT '', status_notes TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS idx_plans_scope ON plans(company_id,project_id);
CREATE INDEX IF NOT EXISTS idx_plan_tasks_scope ON plan_tasks(plan_id,project_id,start_date);
CREATE TABLE IF NOT EXISTS plan_calendar_exceptions(
 id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
 project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, plan_id TEXT REFERENCES plans(id) ON DELETE CASCADE,
 exception_date TEXT NOT NULL, working INTEGER NOT NULL DEFAULT 0, reason TEXT NOT NULL DEFAULT '',
 UNIQUE(company_id,project_id,plan_id,exception_date));
CREATE INDEX IF NOT EXISTS idx_plan_calendar_scope ON plan_calendar_exceptions(company_id,project_id,plan_id,exception_date);
CREATE TABLE IF NOT EXISTS plan_updates(
 id TEXT PRIMARY KEY, plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
 company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 update_date TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', created_by TEXT REFERENCES users(id),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS plan_update_tasks(
 id TEXT PRIMARY KEY, update_id TEXT NOT NULL REFERENCES plan_updates(id) ON DELETE CASCADE,
 plan_task_id TEXT NOT NULL REFERENCES plan_tasks(id) ON DELETE CASCADE,
 percent_complete INTEGER NOT NULL, actual_start TEXT, actual_finish TEXT,
 UNIQUE(update_id,plan_task_id));
CREATE INDEX IF NOT EXISTS idx_plan_updates_scope ON plan_updates(company_id,project_id,plan_id,update_date);
CREATE TABLE IF NOT EXISTS staff(
 id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
 staff_ref TEXT NOT NULL, name TEXT NOT NULL, position TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(company_id,staff_ref));
CREATE INDEX IF NOT EXISTS idx_staff_scope ON staff(company_id,active,name);
CREATE TABLE IF NOT EXISTS staff_training_records(
 id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
 staff_id TEXT NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
 training_name TEXT NOT NULL, provider TEXT NOT NULL DEFAULT '',
 completed_date TEXT NOT NULL, expiry_date TEXT, certificate_ref TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'Completed', notes TEXT NOT NULL DEFAULT '',
 created_by TEXT REFERENCES users(id), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_staff_training_scope ON staff_training_records(company_id,staff_id,expiry_date,training_name);
CREATE TABLE IF NOT EXISTS staff_training_documents(
 id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
 staff_id TEXT NOT NULL REFERENCES staff(id) ON DELETE CASCADE, training_id TEXT NOT NULL REFERENCES staff_training_records(id) ON DELETE CASCADE,
 filename TEXT NOT NULL, stored_name TEXT NOT NULL UNIQUE, mime_type TEXT NOT NULL, size_bytes INTEGER NOT NULL,
 uploaded_by TEXT REFERENCES users(id), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_staff_training_documents_scope ON staff_training_documents(company_id,staff_id,training_id);
CREATE TABLE IF NOT EXISTS project_staff_assignments(
 id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
 project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, staff_id TEXT NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
 assignment_role TEXT NOT NULL, assignment_status TEXT NOT NULL DEFAULT 'Active', start_date TEXT NOT NULL, finish_date TEXT,
 notes TEXT NOT NULL DEFAULT '', created_by TEXT REFERENCES users(id), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS idx_project_staff_assignment_day ON project_staff_assignments(company_id,project_id,start_date,finish_date,assignment_status);
CREATE TABLE IF NOT EXISTS task_staff_assignments(
 id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
 project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
 task_id TEXT NOT NULL REFERENCES plan_tasks(id) ON DELETE CASCADE, staff_id TEXT NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
 role_on_task TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', assigned_by TEXT REFERENCES users(id),
 assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, unassigned_at TEXT);
CREATE INDEX IF NOT EXISTS idx_task_staff_active ON task_staff_assignments(company_id,project_id,task_id,unassigned_at);
CREATE TABLE IF NOT EXISTS task_work_logs(
 id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
 project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, task_id TEXT NOT NULL REFERENCES plan_tasks(id) ON DELETE CASCADE,
 staff_id TEXT NOT NULL REFERENCES staff(id) ON DELETE CASCADE, work_date TEXT NOT NULL, hours REAL NOT NULL DEFAULT 0,
 note TEXT NOT NULL DEFAULT '', created_by TEXT REFERENCES users(id), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS idx_task_work_scope ON task_work_logs(company_id,project_id,task_id,work_date);
CREATE TABLE IF NOT EXISTS daily_attendance(
 id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
 project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, staff_id TEXT NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
 work_date TEXT NOT NULL, onsite INTEGER NOT NULL DEFAULT 1, hours REAL NOT NULL DEFAULT 0, notes TEXT NOT NULL DEFAULT '',
 created_by TEXT REFERENCES users(id), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(company_id,project_id,staff_id,work_date));
CREATE INDEX IF NOT EXISTS idx_daily_attendance_scope ON daily_attendance(company_id,project_id,work_date);
"""

MODULES=["Documents","Projects","Daily Control","Manpower","RFIs","Risks","Actions","Snags","Materials","Procurement","RAMS","Permits","Commissioning","Variations","Cost Control","Handover","Reports"]
ACTIONS=["View","Create","Edit","Approve","Delete","Export"]
TIERS={
 "individual":{"users":1,"projects":3,"storage_gb":1,"features":["core"]},
 "small":{"users":10,"projects":20,"storage_gb":10,"features":["core","compliance"]},
 "business":{"users":100,"projects":100,"storage_gb":100,"features":["core","commercial","compliance","handover","management"]},
 "enterprise":{"users":10000,"projects":10000,"storage_gb":5000,"features":["core","commercial","compliance","handover","management","api","sso"]}
}
def storage_status():
    parent=DB_PATH.parent
    try:
        root_dev=os.stat("/").st_dev
        data_dev=os.stat(parent).st_dev
        separate_device=(data_dev != root_dev)
    except Exception:
        separate_device=False
    return {
        "db_path": str(DB_PATH),
        "db_exists": DB_PATH.exists(),
        "db_size_bytes": DB_PATH.stat().st_size if DB_PATH.exists() else 0,
        "data_dir": str(parent),
        "data_dir_mount": os.path.ismount(str(parent)),
        "separate_filesystem": separate_device,
        "persistent_required": os.getenv("CONSTRUCTION_CONTROL_REQUIRE_PERSISTENT_STORAGE","0") == "1",
    }

def db():
    c=sqlite3.connect(DB_PATH, timeout=15)
    c.row_factory=sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA busy_timeout=15000")
    # WAL keeps the single-instance SQLite service resilient to concurrent browser requests.
    try: c.execute("PRAGMA journal_mode=WAL")
    except sqlite3.DatabaseError: pass
    c.execute("PRAGMA synchronous=NORMAL")
    return c
def _safe_backup_name(name):
    return ''.join(ch if ch.isalnum() or ch in ('-', '_', '.') else '_' for ch in name)[:120]

def make_backup_zip_bytes():
    """Create a consistent SQLite + uploads backup without copying a live WAL file directly."""
    with tempfile.TemporaryDirectory(prefix="cc-backup-") as td:
        snap=Path(td)/"construction_control.db"
        src=sqlite3.connect(DB_PATH, timeout=30)
        try:
            src.execute("PRAGMA busy_timeout=30000")
            try: src.execute("PRAGMA wal_checkpoint(PASSIVE)")
            except Exception: pass
            dst=sqlite3.connect(snap)
            try: src.backup(dst)
            finally: dst.close()
        finally:
            src.close()
        # Sessions are machine/runtime state, not project data. Do not carry active logins.
        clean=sqlite3.connect(snap, timeout=30)
        try:
            clean.execute("DELETE FROM sessions")
            clean.commit()
            check=clean.execute("PRAGMA integrity_check").fetchone()[0]
            if str(check).lower() != "ok": raise ValueError("Database integrity check failed while creating backup")
        finally: clean.close()
        manifest={
            "format":"construction-control-backup",
            "version":1,
            "created_at":date.today().isoformat(),
            "database_filename":"construction_control.db",
            "includes_uploads":UPLOADS.exists(),
            "note":"Full application database backup. Restoring replaces the destination database data; a server-side pre-restore backup is created automatically."
        }
        bio=io.BytesIO()
        total=0
        with zipfile.ZipFile(bio,"w",zipfile.ZIP_DEFLATED) as z:
            z.writestr("manifest.json",json.dumps(manifest,indent=2))
            z.write(snap,"construction_control.db")
            if UPLOADS.exists():
                for f in UPLOADS.rglob("*"):
                    if not f.is_file() or f.is_symlink(): continue
                    rel=f.relative_to(UPLOADS).as_posix()
                    if rel.startswith("../") or rel=="": continue
                    size=f.stat().st_size
                    if total+size>50*1024*1024: raise ValueError("Uploads are too large for a single backup (50 MB limit)")
                    z.write(f,"uploads/"+rel)
                    total+=size
        return bio.getvalue()

def _extract_backup(raw):
    if len(raw)>55*1024*1024: raise ValueError("Backup file is too large (55 MB maximum)")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names=set(z.namelist())
        if "manifest.json" not in names or "construction_control.db" not in names:
            raise ValueError("Invalid Construction Control backup: manifest.json and construction_control.db are required")
        manifest=json.loads(z.read("manifest.json").decode("utf-8"))
        if manifest.get("format")!="construction-control-backup" or int(manifest.get("version",0))!=1:
            raise ValueError("Unsupported backup format")
        for n in names:
            if n.startswith("/") or ".." in Path(n).parts:
                raise ValueError("Backup contains an unsafe path")
        with tempfile.TemporaryDirectory(prefix="cc-restore-") as td:
            root=Path(td); dbfile=root/"construction_control.db"; dbfile.write_bytes(z.read("construction_control.db"))
            test=sqlite3.connect(dbfile, timeout=30); test.row_factory=sqlite3.Row
            try:
                ok=test.execute("PRAGMA integrity_check").fetchone()[0]
                if str(ok).lower()!="ok": raise ValueError("Backup database failed integrity check")
                tables={r[0] for r in test.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                required={"companies","users","projects","plans","plan_tasks"}
                if not required.issubset(tables): raise ValueError("Backup database is missing required Construction Control tables")
                companies=[r[0] for r in test.execute("SELECT id FROM companies")]
                if not companies: raise ValueError("Backup contains no company")
            finally: test.close()
            upload_root=root/"uploads"; upload_root.mkdir()
            for n in names:
                if n.startswith("uploads/") and not n.endswith("/"):
                    rel=Path(n[len("uploads/"):])
                    dest=upload_root/rel; dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(z.read(n))
            return manifest, dbfile.read_bytes(), upload_root.read_bytes() if upload_root.is_file() else None, root

def handle_backup_export(self,c,u):
    if not require_admin(self,u): return
    try:
        raw=make_backup_zip_bytes()
        filename=f"Construction_Control_Backup_{date.today().isoformat()}.zip"
        self.send_response(200); self.send_header("Content-Type","application/zip"); self.send_header("Content-Disposition",f'attachment; filename="{filename}"'); self.send_header("Content-Length",str(len(raw))); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(raw)
    except Exception as e:
        self.j(500,{"error":str(e)})

def _multipart_backup(self):
    ctype=self.headers.get("Content-Type","")
    if not ctype.lower().startswith("multipart/form-data"): raise ValueError("Expected a backup ZIP upload")
    n=int(self.headers.get("Content-Length","0"))
    if n<=0 or n>55*1024*1024: raise ValueError("Backup upload is missing or larger than 55 MB")
    raw=self.rfile.read(n)
    msg=__import__('email.parser',fromlist=['BytesParser']).BytesParser(policy=__import__('email.policy',fromlist=['default']).default).parsebytes(("Content-Type: "+ctype+"\r\nMIME-Version: 1.0\r\n\r\n").encode()+raw)
    for part in msg.iter_attachments():
        payload=part.get_payload(decode=True) or b""
        if payload: return part.get_filename() or "backup.zip", payload
    raise ValueError("No backup ZIP found")

def handle_backup_restore(self,c,u):
    if not require_admin(self,u): return
    try:
        filename,raw=_multipart_backup(self)
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            names=set(z.namelist())
            if "manifest.json" not in names or "construction_control.db" not in names: raise ValueError("Invalid Construction Control backup")
            manifest=json.loads(z.read("manifest.json").decode("utf-8"))
            if manifest.get("format")!="construction-control-backup" or int(manifest.get("version",0))!=1: raise ValueError("Unsupported backup format")
            for n in names:
                if n.startswith("/") or ".." in Path(n).parts: raise ValueError("Backup contains an unsafe path")
            with tempfile.TemporaryDirectory(prefix="cc-restore-") as td:
                root=Path(td); incoming=root/"construction_control.db"; incoming.write_bytes(z.read("construction_control.db"))
                check=sqlite3.connect(incoming,timeout=30); check.row_factory=sqlite3.Row
                try:
                    integrity=check.execute("PRAGMA integrity_check").fetchone()[0]
                    if str(integrity).lower()!="ok": raise ValueError("Backup database failed integrity check")
                    if not check.execute("SELECT 1 FROM companies WHERE id=?",(u["company_id"],)).fetchone(): raise ValueError("This backup belongs to a different company and cannot be restored here")
                finally: check.close()
                # Protect the live state before replacement.
                with RESTORE_LOCK:
                    pre=make_backup_zip_bytes()
                    stamp=__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')
                    prefile=BACKUPS/f"pre_restore_{stamp}_{_safe_backup_name(filename)}"
                    prefile.write_bytes(pre)
                    # Close this request's connection before replacing the DB file.
                    c.close()
                    os.replace(incoming,DB_PATH)
                    # Restore uploads only after the database is safely swapped.
                    if UPLOADS.exists():
                        shutil.rmtree(UPLOADS,ignore_errors=True)
                    UPLOADS.mkdir(parents=True,exist_ok=True)
                    for n in names:
                        if n.startswith("uploads/") and not n.endswith("/"):
                            rel=Path(n[len("uploads/"):]); dest=(UPLOADS/rel).resolve()
                            if not str(dest).startswith(str(UPLOADS)+os.sep): raise ValueError("Unsafe upload path")
                            dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(z.read(n))
                self.j(200,{"ok":True,"restored":True,"filename":filename,"pre_restore_backup":str(prefile.name),"message":"Backup restored. Please log out and back in so the new database session is used."})
    except Exception as e:
        self.j(400,{"error":str(e)})

def pw_hash(p):
    salt=secrets.token_bytes(16); digest=hashlib.scrypt(p.encode(),salt=salt,n=2**14,r=8,p=1)
    return salt.hex()+":"+digest.hex()
def public_user(u):
    # Security boundary: never serialize the database user row directly.
    # Use an explicit allow-list so future sensitive columns cannot leak by accident.
    allowed = ("id", "company_id", "name", "email", "active", "role", "created_at")
    return {k: u[k] for k in allowed if k in u.keys()}

def public_company(c):
    # Same rule for company data returned to the browser.
    allowed = ("id", "name", "country", "tier", "logo_url", "created_at")
    return {k: c[k] for k in allowed if k in c.keys()}
def pw_ok(p,stored):
    try:
        salt,digest=stored.split(":"); got=hashlib.scrypt(p.encode(),salt=bytes.fromhex(salt),n=2**14,r=8,p=1).hex()
        return hmac.compare_digest(got,digest)
    except Exception: return False
def seed_dub84_from_source(c):
    """Idempotently seed the DUB84 Infil programme extracted from the supplied workbook.
    The JSON source is generated from the workbook's cached/displayed values. No actual
    progress is fabricated: imported activities start at 0% / Starting so the site team
    can update live status from the Morning Brief.
    """
    source=BASE/"dub84_programme.json"
    if not source.exists():
        return
    try:
        payload=json.loads(source.read_text(encoding="utf-8"))
    except Exception:
        return
    company_id="C1"; level_id="L3"; created_by="U1"
    project=payload.get("project") or {}
    code=str(project.get("id") or "DUB84").strip()
    if not code:
        return
    prow=c.execute("SELECT id FROM projects WHERE id=?",(code,)).fetchone()
    if not prow:
        c.execute("INSERT INTO projects(id,company_id,name,level_id,manloader,start_date,finish_date,client_name,site_address,scope_ref) VALUES(?,?,?,?,?,?,?,?,?,?)",
                  (code,company_id,project.get("name") or code,level_id,float(project.get("manloader_peak") or 0),project.get("start_date"),project.get("finish_date"),project.get("client_name") or "",project.get("site_address") or code,project.get("scope_ref") or source.name))
    # Make the imported demo project visible to every active user in the same company.
    # This also repairs access on an existing persistent Render database after redeploy.
    c.execute("INSERT OR IGNORE INTO project_access(user_id,project_id) SELECT id, ? FROM users WHERE company_id=? AND active=1",(code,company_id))
    plan_id="PLAN-"+code
    c.execute("INSERT OR IGNORE INTO plans(id,company_id,project_id,name,status,baseline,created_by) VALUES(?,?,?,?,?,?,?)",
              (plan_id,company_id,code,(project.get("name") or code)+" Master Programme","Live",1,created_by))
    # Never overwrite live user progress. Seed only when this programme has no activities.
    count=c.execute("SELECT COUNT(*) FROM plan_tasks WHERE project_id=?",(code,)).fetchone()[0]
    if count==0:
        task_map={str(t.get("activity_id")):t for t in payload.get("tasks",[]) if t.get("activity_id")}
        for t in payload.get("tasks",[]):
            aid=str(t.get("activity_id") or "").strip()
            if not aid: continue
            parent=str(t.get("parent_id") or "").strip() or None
            if parent and parent not in task_map: parent=None
            name=str(t.get("name") or aid).strip()
            start=str(t.get("start_date") or "").strip(); finish=str(t.get("finish_date") or "").strip()
            if not start or not finish: continue
            men=float(t.get("planned_men") or 0)
            notes=str(t.get("notes") or "").strip()
            source_row=t.get("source_row")
            if source_row and f"Source row {source_row}" not in notes:
                notes=(notes+" | " if notes else "")+f"Source row {source_row}."
            tid=aid
            c.execute("""INSERT INTO plan_tasks(id,plan_id,project_id,parent_id,name,start_date,finish_date,percent_complete,planned_men,milestone,notes,activity_id,task_status,baseline_start,baseline_finish)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (tid,plan_id,code,parent,name,start,finish,0,men,1 if t.get("milestone") else 0,notes,aid,"Starting",start,finish))
    c.commit()

def repair_demo_project_access(c):
    """Repair visibility of seeded DUB projects on persistent databases.
    This is intentionally limited to the known seeded demonstration projects and
    does not alter user-created project permissions.
    """
    for project_id in ("DUB10", "DUB50", "DUB84"):
        if c.execute("SELECT 1 FROM projects WHERE id=? AND company_id=?",(project_id,"C1")).fetchone():
            c.execute("INSERT OR IGNORE INTO project_access(user_id,project_id) SELECT id, ? FROM users WHERE company_id=? AND active=1",(project_id,"C1"))

def seed_image_staff(c):
    """Seed the staff register from the supplied labour-board screenshots.
    The screenshot legend defines the labour level colours. Badge markers are
    retained as metadata: * = Airport Badge, ** = AWS Badge, */** = both.
    No project dates or assignments are invented from the image.
    """
    company_id="C1"
    people=[
        ("IMG-COLM-KEIGHERY","Colm Keighery","Unspecified","","AWS Ballycoolin / AWS Tyrellstown","#ffffff"),
        ("IMG-JAMIE-MURRAY","Jamie Murray","Electrician","AWS Badge","AWS Ballycoolin / AWS Tyrellstown","#ff0000"),
        ("IMG-LORCAN-OTOOLE","Lorcan O'Toole","Electrician","AWS Badge","AWS Ballycoolin / AWS Tyrellstown","#ff0000"),
        ("IMG-SEAN-TIMLIN","Sean Timlin","2nd Year","AWS Badge","AWS Ballycoolin / AWS Tyrellstown","#00ff00"),
        ("IMG-CALUM-DALY","Calum Daly","2nd Year","Airport Badge + AWS Badge","AWS Ballycoolin / AWS Tyrellstown","#00ff00"),
        ("IMG-IAN-FOX","Ian Fox (T)","Site Management","AWS Badge","AWS Clon (E2882)","#ffbd0a"),
        ("IMG-JORDAN-LAWRENCE","Jordan Lawrence","Site Management","AWS Badge","AWS Clon (E2882)","#ffbd0a"),
        ("IMG-JAKE-SHERLOCK","Jake Sherlock","Site Management","AWS Badge","AWS Clon (E2882)","#ffbd0a"),
        ("IMG-MARK-GIBSON","Mark Gibson (T)","Charge Hand","AWS Badge","AWS Clon (E2882)","#5b8f3b"),
        ("IMG-CONOR-FITZPATRICK","Conor Fitzpatrick (T)","Charge Hand","AWS Badge","AWS Clon (E2882)","#5b8f3b"),
        ("IMG-PRATIK-KAMBLE","Pratik Kamble","Engineers","","AWS Clon (E2882)","#f6d1ab"),
        ("IMG-ROSS-DOUGLAS","Ross Douglas","Engineers","Airport Badge","AWS Clon (E2882)","#f6d1ab"),
        ("IMG-DEAN-SMITH","Dean Smith","Electrician","AWS Badge","AWS Clon (E2882)","#ff0000"),
        ("IMG-KEITH-MURRAY","Keith Murray","Electrician","AWS Badge","AWS Clon (E2882)","#ff0000"),
        ("IMG-CONOR-SNELL","Conor Snell","Electrician","Airport Badge + AWS Badge","AWS Clon (E2882)","#ff0000"),
        ("IMG-COLM-COX","Colm Cox","Electrician","Airport Badge + AWS Badge","AWS Clon (E2882)","#ff0000"),
        ("IMG-VIJAY-SUNDARAM","Vijay Sundaram (T)","Electrician","AWS Badge","AWS Clon (E2882)","#ff0000"),
        ("IMG-CHRISTIAN-WILLIAMS","Christian Williams","Electrician","Airport Badge + AWS Badge","AWS Clon (E2882)","#ff0000"),
        ("IMG-ADAM-POOLE","Adam Poole","Electrician","Airport Badge + AWS Badge","AWS Clon (E2882)","#ff0000"),
        ("IMG-DEAN-FLYNN","Dean Flynn","4th Year","AWS Badge","AWS Clon (E2882)","#ff00d8"),
        ("IMG-LUKE-OREILLY","Luke O'Reilly","3rd Year","AWS Badge","AWS Clon (E2882)","#ffff00"),
        ("IMG-DARRAGH-MURRAY","Darragh Murray","2nd Year","AWS Badge","AWS Clon (E2882)","#00ff00"),
        ("IMG-LEE-GALLAGHER","Lee Gallagher","2nd Year","AWS Badge","AWS Clon (E2882)","#00ff00"),
        ("IMG-SEAN-BOYLE","Sean Boyle","2nd Year","Airport Badge + AWS Badge","AWS Clon (E2882)","#00ff00"),
        ("IMG-DARIUS-DRAGUSIN","Darius Dragusin","2nd Year","AWS Badge","AWS Clon (E2882)","#00ff00"),
        ("IMG-STEPHEN-BLAKE","Stephen Blake","GO","AWS Badge","AWS Clon (E2882)","#c0c0c0"),
        ("IMG-ANTHONY-MURPHY","Anthony Murphy","Site Management","AWS Badge","DUB 10","#ffbd0a"),
        ("IMG-JOHN-SHELLEY","John Shelley (T)","Charge Hand","AWS Badge","DUB 10","#5b8f3b"),
        ("IMG-KEITH-MURPHY","Keith Murphy","Site Management","AWS Badge","Microsoft","#ffbd0a"),
        ("IMG-WILLIAM-OBRIEN","William O Brien","Site Management","AWS Badge","Vodafone (E2881)","#ffbd0a"),
    ]
    # Preserve historical rows/assignments. Deactivate only the old seeded placeholder
    # registers; never deactivate user-created staff on restart.
    c.execute("UPDATE staff SET active=0, updated_at=CURRENT_TIMESTAMP WHERE company_id=? AND (staff_ref LIKE 'D10-%' OR staff_ref LIKE 'D50-%' OR staff_ref LIKE 'STD-%')",(company_id,))
    for ref,name,level,badge,group,color in people:
        row=c.execute("SELECT id FROM staff WHERE company_id=? AND staff_ref=?",(company_id,ref)).fetchone()
        # Position remains the established assignment vocabulary where possible; the screenshot level is stored separately.
        pos = {"Site Management":"Construction Manager","Charge Hand":"Charge Hand","Engineers":"Engineer","Electrician":"Electrician","4th Year":"4th Year","3rd Year":"3rd Year","2nd Year":"2nd Year","1st Year":"1st Year","GO":"GO","Unspecified":"Unspecified"}[level]
        if row:
            sid=row[0]
            c.execute("UPDATE staff SET name=?,position=?,labour_level=?,badge_type=?,source_group=?,display_color=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(name,pos,level,badge,group,color,sid))
        else:
            sid="ST-"+ref
            c.execute("INSERT OR IGNORE INTO staff(id,company_id,staff_ref,name,position,active,labour_level,badge_type,source_group,display_color) VALUES(?,?,?,?,?,?,?,?,?,?)",(sid,company_id,ref,name,pos,1,level,badge,group,color))
    # Repair any older rows that pre-date the new columns.
    c.execute("UPDATE staff SET labour_level=position WHERE company_id=? AND (labour_level IS NULL OR labour_level='')",(company_id,))
    c.commit()

def seed_dub_demo_data(c):
    """Idempotent DUB10/DUB50 demonstration programmes based on the supplied SOW.
    These records are intentionally demo/population data so the daily-control workflow
    is usable immediately on a fresh/local installation.
    """
    company_id="C1"; level_id="L3"; created_by="U1"
    roles=["Construction Manager","Foreman","Charge Hand","Electrician","4th Year","3rd Year","2nd Year","1st Year","GO"]
    people=[
        ("D10-CM","DUB10 CM","Construction Manager"),("D10-FM","DUB10 Foreman","Foreman"),("D10-CH","DUB10 Charge Hand","Charge Hand"),
        ("D10-E1","DUB10 Electrician 1","Electrician"),("D10-E2","DUB10 Electrician 2","Electrician"),("D10-4Y","DUB10 4th Year","4th Year"),
        ("D10-3Y","DUB10 3rd Year","3rd Year"),("D10-2Y","DUB10 2nd Year","2nd Year"),("D10-GO","DUB10 GO","GO"),
        ("D50-CM","DUB50 CM","Construction Manager"),("D50-FM","DUB50 Foreman","Foreman"),("D50-CH","DUB50 Charge Hand","Charge Hand"),
        ("D50-E1","DUB50 Electrician 1","Electrician"),("D50-E2","DUB50 Electrician 2","Electrician"),("D50-4Y","DUB50 4th Year","4th Year"),
        ("D50-3Y","DUB50 3rd Year","3rd Year"),("D50-2Y","DUB50 2nd Year","2nd Year"),("D50-GO","DUB50 GO","GO"),
    ]
    for ref,name,position in people:
        c.execute("INSERT OR IGNORE INTO staff(id,company_id,staff_ref,name,position,active) VALUES(?,?,?,?,?,1)",
                  ("ST-"+ref,company_id,ref,name,position))
    # Keep a useful standard C1 staff register available on fresh/repaired databases.
    standard_people=[
        ("STD-CM","Michael Byrne","Construction Manager"),("STD-PM","Paul Kelly","Project Manager"),
        ("STD-SM","Sean Murphy","Site Manager"),("STD-FM","Liam Doyle","Foreman"),("STD-CH","John Ryan","Charge Hand"),
        ("STD-E1","Mark Walsh","Electrician"),("STD-E2","David Nolan","Electrician"),("STD-4Y","Tom O'Brien","4th Year"),
        ("STD-3Y","Chris Moore","3rd Year"),("STD-2Y","Jack Flynn","2nd Year"),("STD-1Y","Adam Hayes","1st Year"),
        ("STD-GO","Ben Collins","GO"),("STD-MECH","Eoin Power","Construction Manager"),("STD-FIRE","Gary Fox","Construction Manager"),("STD-IT","Luke Burke","Electrician"),("STD-BMS","Ross Casey","Electrician")
    ]
    for ref,name,position in standard_people:
        c.execute("INSERT OR IGNORE INTO staff(id,company_id,staff_ref,name,position,active) VALUES(?,?,?,?,?,1)",("ST-"+ref,company_id,ref,name,position))
    projects=[
        ("DUB10","DUB10 — Data Centre Construction Project","2026-08-31","2027-05-10",9,"SOW-DC-001 Rev 1.1"),
        ("DUB50","DUB50 — Data Centre Construction Project","2026-09-07","2027-05-17",9,"SOW-DC-001 Rev 1.1"),
    ]
    activities=[
        ("Mobilisation / Site Establishment",0,14,2,1),
        ("Enabling Works / Plinths / Hardstanding",21,56,5,2),
        ("MV Switchgear / Transformers",49,98,10,3),
        ("LV Boards / UPS / Generators",77,154,14,4),
        ("Chillers / Dry Coolers / CRAH",91,168,12,5),
        ("Raised Floor / Aisle Containment",105,168,8,6),
        ("Fire Alarm / Suppression",119,182,7,7),
        ("BMS / Security Installation",133,196,6,8),
        ("Copper / Fibre Cabling",147,196,8,9),
        ("Pre-Commissioning / EHOA",175,196,10,10),
        ("Level 1–3 Commissioning Verification",182,210,8,11),
        ("Level 4 Functional Performance Testing",196,224,8,12),
        ("Level 5 IST / Utility Loss Testing",210,238,10,13),
        ("Client Training / Handover",238,252,5,14),
        ("Practical Completion / Snagging Closeout",245,252,4,15),
    ]
    for code,name,start,finish,man,_scope in projects:
        prow=c.execute("SELECT id FROM projects WHERE id=?",(code,)).fetchone()
        if not prow:
            c.execute("INSERT INTO projects(id,company_id,name,level_id,manloader,start_date,finish_date,client_name,site_address,scope_ref) VALUES(?,?,?,?,?,?,?,?,?,?)",
                      (code,company_id,name,level_id,man,start,finish,"Data Centre Client",code+" Data Centre Site","SOW-DC-001 Rev 1.1"))
            c.execute("INSERT OR IGNORE INTO project_access(user_id,project_id) SELECT id, ? FROM users WHERE company_id=? AND active=1",(code,company_id))
        else:
            c.execute("UPDATE projects SET name=?,manloader=?,start_date=?,finish_date=?,scope_ref=? WHERE id=?",
                      (name,man,start,finish,"SOW-DC-001 Rev 1.1",code))
            c.execute("INSERT OR IGNORE INTO project_access(user_id,project_id) SELECT id, ? FROM users WHERE company_id=? AND active=1",(code,company_id))
        plan_id="PLAN-"+code
        c.execute("INSERT OR IGNORE INTO plans(id,company_id,project_id,name,status,baseline,created_by) VALUES(?,?,?,?,?,?,?)",
                  (plan_id,company_id,code,code+" Master Programme","Live",1,created_by))
        # Seed programme activities once; don't overwrite user progress on subsequent starts.
        count=c.execute("SELECT COUNT(*) FROM plan_tasks WHERE project_id=?",(code,)).fetchone()[0]
        if count==0:
            from datetime import date,timedelta
            base=date.fromisoformat(start)
            task_ids=[]
            for i,(label,ofs_start,ofs_finish,men,seq) in enumerate(activities,1):
                ts=(base+timedelta(days=ofs_start)).isoformat(); tf=(base+timedelta(days=ofs_finish)).isoformat()
                tid=f"{code}-T{i:02d}"
                pct=100 if date(2026,9,20) > (base+timedelta(days=ofs_finish)) else (15 if date(2026,9,20) >= (base+timedelta(days=ofs_start)) else 0)
                status="Finished" if date(2026,9,20) > (base+timedelta(days=ofs_finish)) else ("Ongoing" if date(2026,9,20) >= (base+timedelta(days=ofs_start)) else "Starting")
                c.execute("INSERT INTO plan_tasks(id,plan_id,project_id,name,start_date,finish_date,percent_complete,planned_men,predecessor_id,milestone,notes,activity_id,task_status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          (tid,plan_id,code,label,ts,tf,pct,float(men),task_ids[-1] if task_ids else None,1 if i in (15,) else 0,"SOW-DC-001 Rev 1.1 scope activity",tid,status))
                task_ids.append(tid)
        # Assign the nine role grades to the project for the full programme.
        start_date=start; finish_date=finish
        prefix="D10" if code=="DUB10" else "D50"
        for ref,name,position in people:
            if not ref.startswith(prefix): continue
            sid="ST-"+ref; aid=f"AS-{code}-{ref}"
            c.execute("INSERT OR IGNORE INTO project_staff_assignments(id,company_id,project_id,staff_id,assignment_role,assignment_status,start_date,finish_date,notes,created_by) VALUES(?,?,?,?,?,?,?,?,?,?)",
                      (aid,company_id,code,sid,position,"Active",start_date,finish_date,"Seeded programme assignment",created_by))
            # Put each person against a representative task matching their role.
            task_num={"Construction Manager":1,"Foreman":2,"Charge Hand":2,"Electrician":3,"4th Year":4,"3rd Year":5,"2nd Year":6,"1st Year":7,"GO":8}.get(position,1)
            tid=f"{code}-T{task_num:02d}"
            c.execute("INSERT OR IGNORE INTO task_staff_assignments(id,company_id,project_id,plan_id,task_id,staff_id,role_on_task,notes,assigned_by) VALUES(?,?,?,?,?,?,?,?,?)",
                      (f"TA-{code}-{ref}",company_id,code,plan_id,tid,sid,position,"Seeded task assignment",created_by))
    c.commit()

def seed(c):
    c.executescript(SCHEMA)
    # Ensure every company always has the complete access ladder and a persistent settings row.
    for company in c.execute("SELECT id FROM companies").fetchall():
        cid=company[0]
        c.execute("INSERT OR IGNORE INTO company_settings(company_id) VALUES(?)",(cid,))
        ensure_ladder_roles(c,cid)
    # Lightweight schema migration for planning enhancements.
    existing={r[1] for r in c.execute("PRAGMA table_info(plan_tasks)").fetchall()}
    for col,typ,default in [
        ("dependency_type","TEXT NOT NULL DEFAULT 'FS'",None),
        ("lag_days","INTEGER NOT NULL DEFAULT 0",None),
        ("actual_start","TEXT",None),("actual_finish","TEXT",None),
        ("baseline_start","TEXT",None),("baseline_finish","TEXT",None),("activity_id","TEXT",None),
        ("task_status","TEXT NOT NULL DEFAULT 'Starting'",None),("held_up_reason","TEXT NOT NULL DEFAULT ''",None),("status_notes","TEXT NOT NULL DEFAULT ''",None)]:
        if col not in existing: c.execute(f"ALTER TABLE plan_tasks ADD COLUMN {col} {typ}")
    # Backfill stable Excel activity references for older programme rows.
    c.execute("UPDATE plan_tasks SET activity_id=id WHERE activity_id IS NULL OR activity_id='' ")
    # Project manpower baseline: set once at project setup; daily manpower is actual onsite attendance.
    project_cols={r[1] for r in c.execute("PRAGMA table_info(projects)").fetchall()}
    if "manloader" not in project_cols:
        c.execute("ALTER TABLE projects ADD COLUMN manloader REAL NOT NULL DEFAULT 0")
    for col, typ, default in [
        ("start_date","TEXT",None),("finish_date","TEXT",None),
        ("client_name","TEXT NOT NULL DEFAULT ''",None),
        ("site_address","TEXT NOT NULL DEFAULT ''",None),
        ("scope_ref","TEXT NOT NULL DEFAULT ''",None),
    ]:
        if col not in project_cols:
            c.execute(f"ALTER TABLE projects ADD COLUMN {col} {typ}")
    staff_cols={r[1] for r in c.execute("PRAGMA table_info(staff)").fetchall()}
    for col, typ in [("labour_level","TEXT NOT NULL DEFAULT ''"),("badge_type","TEXT NOT NULL DEFAULT ''"),("source_group","TEXT NOT NULL DEFAULT ''"),("display_color","TEXT NOT NULL DEFAULT ''")]:
        if col not in staff_cols: c.execute(f"ALTER TABLE staff ADD COLUMN {col} {typ}")
    company_cols={r[1] for r in c.execute("PRAGMA table_info(companies)").fetchall()}
    if "logo_url" not in company_cols:
        c.execute("ALTER TABLE companies ADD COLUMN logo_url TEXT NOT NULL DEFAULT ''")
    role_cols={r[1] for r in c.execute("PRAGMA table_info(roles)").fetchall()}
    if "access_level" not in role_cols:
        c.execute("ALTER TABLE roles ADD COLUMN access_level INTEGER NOT NULL DEFAULT 1")
    if "parent_role_id" not in role_cols:
        c.execute("ALTER TABLE roles ADD COLUMN parent_role_id TEXT")
    role_level_map={"Viewer":1,"Site User":2,"Foreman / Charge Hand":3,"Site Manager":4,"Project Manager":5,"Construction Manager":6,"Business Unit Lead":7,"Company Director":8,"Company Administrator":9}
    for rname,rlevel in role_level_map.items():
        c.execute("UPDATE roles SET access_level=? WHERE name=? AND (access_level IS NULL OR access_level=1)",(rlevel,rname))
    if c.execute("SELECT COUNT(*) FROM companies").fetchone()[0]:
        pm = c.execute("SELECT id FROM roles WHERE company_id='C1' AND name='Project Manager'").fetchone()
        if pm:
            c.executemany("INSERT OR IGNORE INTO permissions(role_id,module,action,allowed) VALUES(?,?,?,1)",[(pm["id"],m,"Approve") for m in ("Projects","RFIs","Risks","Actions","Snags")])
            c.commit()
        for cid in [r["id"] for r in c.execute("SELECT id FROM companies").fetchall()]:
            ensure_ladder_roles(c,cid)
        seed_dub_demo_data(c)
        seed_dub84_from_source(c)
        seed_image_staff(c)
        c.commit()
        return
    c.execute("INSERT INTO companies(id,name,country,tier) VALUES(?,?,?,?)",("C1","Demo Construction Company","Ireland","business"))
    c.execute("INSERT INTO companies(id,name,country,tier) VALUES(?,?,?,?)",("C2","Small Builder Demo","Ireland","small"))
    for cid,role,level in [("C1","Company Administrator",9),("C1","Project Manager",5),("C2","Site User",2)]:
        c.execute("INSERT INTO roles(id,company_id,name,access_level) VALUES(?,?,?,?)",(cid+"-"+role.replace(" ","-"),cid,role,level))
    ensure_ladder_roles(c,"C1")
    ensure_ladder_roles(c,"C2")
    c.execute("INSERT OR IGNORE INTO company_settings(company_id) VALUES(?)",("C1",))
    c.execute("INSERT OR IGNORE INTO company_settings(company_id) VALUES(?)",("C2",))
    roles={r["name"]:r["id"] for r in c.execute("SELECT id,name FROM roles")}
    for rid in roles.values():
        for m in MODULES:
            for a in ACTIONS:
                allow=1 if "Administrator" in rid else 0
                c.execute("INSERT OR IGNORE INTO permissions VALUES(?,?,?,?)",(rid,m,a,allow))
    pm=roles["Project Manager"]
    for m in ["Projects","Daily Control","Manpower","RFIs","Risks","Actions","Snags"]:
        for a in ["View","Create","Edit","Export"]: c.execute("UPDATE permissions SET allowed=1 WHERE role_id=? AND module=? AND action=?",(pm,m,a))
    c.execute("UPDATE permissions SET allowed=1 WHERE role_id=? AND module IN ('Projects','RFIs','Risks','Actions','Snags') AND action='Approve'",(pm,))
    su=roles["Site User"]
    for m in ["Projects","Daily Control","Manpower","Snags"]:
        for a in ["View","Create","Edit"]: c.execute("UPDATE permissions SET allowed=1 WHERE role_id=? AND module=? AND action=?",(su,m,a))
    c.execute("INSERT INTO users(id,company_id,name,email,password_hash,active,role) VALUES(?,?,?,?,?,?,?)",("U1","C1","Company Owner","owner@demo.local",pw_hash("DemoPass!123"),1,"Company Administrator"))
    c.execute("INSERT INTO users(id,company_id,name,email,password_hash,active,role) VALUES(?,?,?,?,?,?,?)",("U2","C1","Project Manager","manager@demo.local",pw_hash("DemoPass!123"),1,"Project Manager"))
    c.execute("INSERT INTO users(id,company_id,name,email,password_hash,active,role) VALUES(?,?,?,?,?,?,?)",("U3","C2","Site User","site@demo.local",pw_hash("DemoPass!123"),1,"Site User"))
    c.execute("INSERT INTO org_levels(id,company_id,name) VALUES(?,?,?)",("L1","C1","Executive"))
    c.execute("INSERT INTO org_levels(id,company_id,name) VALUES(?,?,?)",("L2","C1","Operations"))
    c.execute("INSERT INTO org_levels(id,company_id,name,parent_id) VALUES(?,?,?,?)",("L3","C1","Project Management","L2"))
    c.execute("INSERT INTO projects(id,company_id,name,level_id,manloader) VALUES(?,?,?,?,?)",("P1","C1","Project Alpha","L3",12))
    c.execute("INSERT INTO projects(id,company_id,name,level_id,manloader) VALUES(?,?,?,?,?)",("P2","C2","Project Beta",None,8))
    c.execute("INSERT INTO project_access(user_id,project_id) VALUES(?,?)",("U2","P1"))
    c.execute("INSERT INTO project_access(user_id,project_id) VALUES(?,?)",("U3","P2"))
    seed_dub_demo_data(c)
    seed_dub84_from_source(c)
    seed_image_staff(c)
    repair_demo_project_access(c)
    c.commit()

def init_db(path=None):
    global DB_PATH
    old=DB_PATH
    if path: DB_PATH=Path(path)
    c=db()
    try: seed(c)
    finally: c.close()
    if path: DB_PATH=old

def can_access_project(c, user, project_id):
    # Accept a user id for compatibility with Phase 5C tests, while the server uses the full user row.
    if isinstance(user, str):
        user=c.execute("SELECT * FROM users WHERE id=?",(user,)).fetchone()
    if not user: return False
    row=c.execute("SELECT company_id FROM projects WHERE id=?",(project_id,)).fetchone()
    if not row or row["company_id"]!=user["company_id"] or not user["active"]: return False
    if user["role"]=="Company Administrator": return True
    return bool(c.execute("SELECT 1 FROM project_access WHERE user_id=? AND project_id=?",(user["id"],project_id)).fetchone())

def project_manloader(c, company_id, project_id):
    """Return the project-level manpower baseline. Legacy daily planned_men is only read for migration compatibility."""
    row=c.execute("SELECT manloader FROM projects WHERE id=? AND company_id=?",(project_id,company_id)).fetchone()
    baseline=float(row[0] or 0) if row else 0.0
    if baseline>0: return baseline
    legacy=c.execute("SELECT data_json FROM module_records WHERE company_id=? AND project_id=? AND module='Manpower'",(company_id,project_id)).fetchall()
    total=0.0
    found=False
    for r in legacy:
        try:
            d=json.loads(r[0] or "{}")
            if "planned_men" in d:
                total+=float(d.get("planned_men") or 0); found=True
        except Exception: pass
    return total if found else 0.0

def role_id(c, company_id, name):
    r=c.execute("SELECT id FROM roles WHERE company_id=? AND name=?",(company_id,name)).fetchone(); return r["id"] if r else None

def audit_row(c, u, action, target):
    c.execute("INSERT INTO audit(company_id,user_id,action,target) VALUES(?,?,?,?)",(u["company_id"],u["id"],action,target))

ACCESS_LADDER = [
    (1, "Viewer", "View-only project access"),
    (2, "Site User", "Daily site updates and basic records"),
    (3, "Foreman / Charge Hand", "Site control, tasks, manpower and site records"),
    (4, "Site Manager", "Site management, compliance and approvals within assigned projects"),
    (5, "Project Manager", "Full project delivery control and approvals"),
    (6, "Construction Manager", "Multi-project delivery and management control"),
    (7, "Business Unit Lead", "Business-unit oversight across projects"),
    (8, "Company Director", "Company-wide operational oversight"),
    (9, "Company Administrator", "Full company administration and security control"),
]

LADDER_PERMISSION_PRESETS = {
    1:[("Projects","View"),("Daily Control","View"),("Manpower","View"),("Reports","View")],
    2:[(m,a) for m in ("Projects","Daily Control","Manpower","Snags") for a in ("View","Create","Edit")],
    3:[(m,a) for m in ("Projects","Daily Control","Manpower","RFIs","Risks","Actions","Snags","Materials","Permits","RAMS") for a in ("View","Create","Edit","Export")],
    4:[(m,a) for m in MODULES for a in ("View","Create","Edit","Export")],
    5:[(m,a) for m in MODULES for a in ("View","Create","Edit","Approve","Export")],
    6:[(m,a) for m in MODULES for a in ("View","Create","Edit","Approve","Export")],
    7:[(m,a) for m in MODULES for a in ("View","Create","Edit","Approve","Export")],
    8:[(m,a) for m in MODULES for a in ("View","Create","Edit","Approve","Export")],
    9:[(m,a) for m in MODULES for a in ACTIONS],
}

def ensure_ladder_roles(c, company_id):
    previous=None
    for level,name,_desc in ACCESS_LADDER:
        row=c.execute("SELECT id FROM roles WHERE company_id=? AND name=?",(company_id,name)).fetchone()
        if row:
            rid=row["id"]
            c.execute("UPDATE roles SET access_level=?,parent_role_id=? WHERE id=?",(level,previous,rid))
        else:
            rid=f"{company_id}-LADDER-{level}"
            c.execute("INSERT INTO roles(id,company_id,name,access_level,parent_role_id) VALUES(?,?,?,?,?)",(rid,company_id,name,level,previous))
            c.executemany("INSERT INTO permissions(role_id,module,action,allowed) VALUES(?,?,?,0)",[(rid,m,a) for m in MODULES for a in ACTIONS])
            for mod,act in LADDER_PERMISSION_PRESETS[level]:
                c.execute("UPDATE permissions SET allowed=1 WHERE role_id=? AND module=? AND action=?",(rid,mod,act))
        previous=rid

def ladder_info(level):
    for n,name,desc in ACCESS_LADDER:
        if int(level)==n: return {"level":n,"name":name,"description":desc}
    return {"level":1,"name":"Viewer","description":"View-only project access"}

def has_permission(c, u, module, action):
    if u["role"] == "Company Administrator": return True
    rid = role_id(c, u["company_id"], u["role"])
    if not rid: return False
    # A role inherits permissions from its parent roles, forming a simple access ladder.
    seen=set()
    while rid and rid not in seen:
        seen.add(rid)
        row = c.execute("SELECT allowed,parent_role_id FROM permissions LEFT JOIN roles ON roles.id=permissions.role_id WHERE permissions.role_id=? AND permissions.module=? AND permissions.action=?", (rid,module,action)).fetchone()
        if row and row["allowed"]: return True
        rr=c.execute("SELECT parent_role_id FROM roles WHERE id=? AND company_id=?",(rid,u["company_id"])).fetchone()
        rid=rr["parent_role_id"] if rr else None
    return False

def staff_record(c,u,staff_id):
    return c.execute("SELECT * FROM staff WHERE id=? AND company_id=?",(staff_id,u['company_id'])).fetchone()

def task_record(c,u,task_id):
    return c.execute("SELECT pt.*,p.company_id FROM plan_tasks pt JOIN plans p ON p.id=pt.plan_id WHERE pt.id=? AND p.company_id=?",(task_id,u['company_id'])).fetchone()

def valid_module(module):
    return module in MODULES

def task_planned_men_for_day(c,u,project_id,day):
    total=0.0
    rows=c.execute("SELECT pt.planned_men,pt.start_date,pt.finish_date FROM plan_tasks pt JOIN plans pl ON pl.id=pt.plan_id WHERE pt.project_id=? AND pl.company_id=?",(project_id,u["company_id"])).fetchall()
    for r in rows:
        try:
            if r["start_date"]<=day<=r["finish_date"]:
                total += float(r["planned_men"] or 0)
        except Exception:
            pass
    return round(total,1)

def daily_attendance_summary(c,u,project_id,day):
    rows=c.execute("SELECT a.*,s.staff_ref,s.name,s.position FROM daily_attendance a JOIN staff s ON s.id=a.staff_id WHERE a.company_id=? AND a.project_id=? AND a.work_date=? ORDER BY s.name",(u["company_id"],project_id,day)).fetchall()
    onsite=[r for r in rows if int(r["onsite"] or 0)==1]
    return rows, len(onsite), round(sum(float(r["hours"] or 0) for r in onsite),1)

BULK_IMPORT_SPECS={
    "Daily Control":[("Title",True,"text"),("Date",True,"date"),("Status",False,"text"),("Planned Activities",False,"text"),("Completed Activities",False,"text"),("Delays",False,"text"),("Constraints",False,"text"),("Notes",False,"text")],
    "Manpower":[("Title",True,"text"),("Date",True,"date"),("Role",True,"role"),("Actual Men",True,"number"),("Hours",True,"number"),("Notes",False,"text")],
    "RFIs":[("Title",True,"text"),("RFI No",False,"text"),("Subject",True,"text"),("Status",False,"text"),("Due Date",False,"date"),("Raised By",False,"text"),("Response",False,"text"),("Notes",False,"text")],
    "Risks":[("Title",True,"text"),("Risk ID",False,"text"),("Description",True,"text"),("Status",False,"text"),("Owner",False,"text"),("Due Date",False,"date"),("Likelihood",False,"number"),("Impact",False,"number"),("Mitigation",False,"text"),("Notes",False,"text")],
    "Actions":[("Title",True,"text"),("Action ID",False,"text"),("Description",True,"text"),("Status",False,"text"),("Owner",False,"text"),("Due Date",False,"date"),("Priority",False,"text"),("Notes",False,"text")],
    "Snags":[("Title",True,"text"),("Snag ID",False,"text"),("Description",True,"text"),("Status",False,"text"),("Location",False,"text"),("Owner",False,"text"),("Due Date",False,"date"),("Notes",False,"text")],
    "Materials":[("Title",True,"text"),("Item",True,"text"),("Description",False,"text"),("Quantity",True,"number"),("Unit",True,"text"),("Status",False,"text"),("Required Date",False,"date"),("Supplier",False,"text"),("Notes",False,"text")],
    "Procurement":[("Title",True,"text"),("PO/Ref",False,"text"),("Item",True,"text"),("Supplier",False,"text"),("Quantity",False,"number"),("Status",False,"text"),("Required Date",False,"date"),("Delivery Date",False,"date"),("Notes",False,"text")],
    "RAMS":[("Title",True,"text"),("Ref",False,"text"),("Status",False,"text"),("Review Date",False,"date"),("Approved By",False,"text"),("Notes",False,"text")],
    "Permits":[("Title",True,"text"),("Permit Ref",False,"text"),("Type",True,"text"),("Status",False,"text"),("Start Date",False,"date"),("Expiry Date",False,"date"),("Issued By",False,"text"),("Notes",False,"text")],
    "Commissioning":[("Title",True,"text"),("System",True,"text"),("Test",True,"text"),("Status",False,"text"),("Planned Date",False,"date"),("Actual Date",False,"date"),("Result",False,"text"),("Notes",False,"text")],
    "Variations":[("Title",True,"text"),("Variation Ref",False,"text"),("Description",True,"text"),("Status",False,"text"),("Value",False,"number"),("Date",False,"date"),("Approved Value",False,"number"),("Notes",False,"text")],
    "Cost Control":[("Title",True,"text"),("Cost Code",False,"text"),("Description",True,"text"),("Budget",False,"number"),("Committed",False,"number"),("Actual",False,"number"),("Forecast",False,"number"),("Notes",False,"text")],
    "Handover":[("Title",True,"text"),("Description",False,"text"),("Status",False,"text"),("Due Date",False,"date"),("Owner",False,"text"),("Notes",False,"text")],
    "Reports":[("Title",True,"text"),("Report Type",True,"text"),("Date",True,"date"),("Status",False,"text"),("Author",False,"text"),("Notes",False,"text")],
}
PROGRAMME_IMPORT_HEADERS=[("Activity ID",True,"text"),("Activity",True,"text"),("Parent ID",False,"text"),("Start Date",True,"date"),("Finish Date",True,"date"),("% Complete",False,"number"),("Planned Men",False,"number"),("Predecessor ID",False,"text"),("Dependency Type",False,"text"),("Lag Days",False,"number"),("Milestone",False,"text"),("Notes",False,"text"),("Actual Start",False,"date"),("Actual Finish",False,"date"),("Baseline Start",False,"date"),("Baseline Finish",False,"date")]

def make_programme_xlsx_template(plan_name=""):
    import zipfile
    headers=[x[0] for x in PROGRAMME_IMPORT_HEADERS]
    example=["A001","EXAMPLE — DELETE THIS ROW BEFORE IMPORT","","2026-10-01","2026-10-02","0","2","","FS","0","No","Example activity","","","",""]
    rows=[headers,example]
    def sheet_xml(vals):
        sr=[]
        for r,rv in enumerate(vals,1):
            cells=''.join(f'<c r="{xlsx_col(c)}{r}" t="inlineStr"><is><t>{xml_escape(v)}</t></is></c>' for c,v in enumerate(rv,1))
            sr.append(f'<row r="{r}">{cells}</row>')
        return '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'+''.join(sr)+'</sheetData></worksheet>'
    instr=["Construction Control Programme Import Template",f"Programme: {plan_name or 'selected programme'}","One workbook imports activities into the selected programme.","Delete the example row before importing.","Do not rename, reorder, add or remove columns.","Activity ID must be unique within this workbook and is used for Parent/Predecessor references.","Dates must be YYYY-MM-DD. % Complete must be 0-100. Planned Men and Lag Days must be numeric and non-negative.","Dependency Type: FS, SS, FF or SF. Lag Days are working days.","Milestone must be Yes or No.","Import is atomic: if any row is invalid, nothing is imported.","Existing activity IDs in the selected programme are rejected."]
    instr_xml=''.join(f'<row r="{i}"><c r="A{i}" t="inlineStr"><is><t>{xml_escape(v)}</t></is></c></row>' for i,v in enumerate(instr,1))
    ct='<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>'
    rels='<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'
    wb='<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Instructions" sheetId="1" r:id="rId1"/><sheet name="Template" sheetId="2" r:id="rId2"/></sheets></workbook>'
    wb_rels='<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/></Relationships>'
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml',ct); z.writestr('_rels/.rels',rels); z.writestr('xl/workbook.xml',wb); z.writestr('xl/_rels/workbook.xml.rels',wb_rels); z.writestr('xl/worksheets/sheet1.xml',f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{instr_xml}</sheetData></worksheet>'); z.writestr('xl/worksheets/sheet2.xml',sheet_xml(rows))
    return bio.getvalue()

ROLE_VALUES=["Construction Manager","Foreman","Charge Hand","Electrician","4th Year","3rd Year","2nd Year","1st Year","GO"]

def bulk_spec(module):
    return BULK_IMPORT_SPECS.get(module)

def normalise_cell(v):
    if v is None: return ""
    if hasattr(v,"isoformat") and not isinstance(v,str): return v.isoformat()
    return str(v).strip()

def import_data_key(header):
    import re
    return re.sub(r"[^a-z0-9]+","_",str(header).strip().lower()).strip("_")

def validate_bulk_row(module, headers, values):
    spec=bulk_spec(module)
    if not spec: return None, ["Bulk import is not supported for this module"]
    data={h:normalise_cell(values.get(h,"")) for h,_,_ in spec}
    errors=[]
    for h,required,typ in spec:
        v=data[h]
        if required and not v: errors.append(f"{h} is required"); continue
        if not v: continue
        if typ=="date":
            try:
                date.fromisoformat(v[:10])
            except Exception:
                try:
                    serial=float(v); data[h]=(date(1899,12,30)+timedelta(days=serial)).isoformat()
                except Exception: errors.append(f"{h} must be YYYY-MM-DD (Excel dates are also accepted)")
        elif typ=="number":
            try: float(v.replace(",",""))
            except Exception: errors.append(f"{h} must be a number")
        elif typ=="role" and v not in ROLE_VALUES:
            errors.append(f"Role must be one of: {', '.join(ROLE_VALUES)}")
    if errors: return None, errors
    title=data.pop("Title")
    clean={}
    for k,v in data.items():
        if v!="":
            if any(k==h and typ=="number" for h,_,typ in spec):
                clean[import_data_key(k)]=float(v.replace(",",""))
            else: clean[import_data_key(k)]=v
    return {"title":title,"data":clean}, []

def validate_individual_record(module,title,data):
    spec=bulk_spec(module)
    if not spec: return None,["Data entry is not supported for this module"]
    if not isinstance(data,dict): return None,["Data must be an object"]
    values={"Title":str(title or '').strip()}; allowed={import_data_key(h):h for h,_,_ in spec if h!='Title'}; unknown=[]; legacy_planned=None
    for k,v in data.items():
        if k=='Title': continue
        nk=import_data_key(k)
        if module=="Manpower" and nk=="planned_men":
            # Backward-compatible API input only. New UI/template no longer exposes this field.
            legacy_planned=v
            continue
        if nk in allowed: values[allowed[nk]]=v
        else: unknown.append(k)
    if unknown: return None,["Unknown field(s): "+', '.join(map(str,unknown))]
    result,errs=validate_bulk_row(module,[x[0] for x in spec],values)
    if result is not None and module=="Manpower" and legacy_planned is not None:
        try: result["data"]["planned_men"]=float(str(legacy_planned).replace(",",""))
        except Exception: return None,["Planned Men must be a number"]
    return result,errs


def require_admin(self,u):
    if u["role"]!="Company Administrator": self.j(403,{"error":"Administrator permission required"}); return False
    return True

def notify(c, company_id, user_id, project_id, typ, title, message):
    nid=secrets.token_hex(8)
    c.execute("INSERT INTO notifications(id,company_id,user_id,project_id,type,title,message) VALUES(?,?,?,?,?,?,?)",(nid,company_id,user_id,project_id,typ,title,message))
    return nid

def workflow_record(c,u,wid):
    return c.execute("SELECT * FROM workflows WHERE id=? AND company_id=?",(wid,u["company_id"])).fetchone()

def valid_workflow_target(c,u,project_id,module,record_id):
    if not valid_module(module) or not can_access_project(c,u,project_id): return False
    return bool(c.execute("SELECT 1 FROM module_records WHERE id=? AND company_id=? AND project_id=? AND module=?",(record_id,u["company_id"],project_id,module)).fetchone())

def plan_is_working(c, company_id, project_id, plan_id, dt):
    # Monday-Friday by default; explicit project/plan exception overrides.
    r=c.execute("SELECT working FROM plan_calendar_exceptions WHERE company_id=? AND project_id=? AND (plan_id=? OR plan_id IS NULL) AND exception_date=? ORDER BY plan_id IS NOT NULL DESC LIMIT 1",(company_id,project_id,plan_id,dt.isoformat())).fetchone()
    if r is not None: return bool(r[0])
    return dt.weekday()<5

def working_days(c, company_id, project_id, plan_id, a, b):
    if b<a: return 0
    from datetime import timedelta
    n=0; cur=a
    while cur<=b:
        if plan_is_working(c,company_id,project_id,plan_id,cur): n+=1
        cur+=timedelta(days=1)
    return n

def add_plan_workdays(c, company_id, project_id, plan_id, dt, n):
    from datetime import timedelta
    cur=dt; step=1 if n>=0 else -1; left=abs(n)
    while left:
        cur+=timedelta(days=step)
        if plan_is_working(c,company_id,project_id,plan_id,cur): left-=1
    return cur

def xml_escape(s):
    return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;").replace("'","&apos;")

def xlsx_col(n):
    out=""
    while n:
        n,rem=divmod(n-1,26); out=chr(65+rem)+out
    return out

def make_xlsx_template(module):
    import zipfile
    spec=bulk_spec(module); headers=[x[0] for x in spec]
    rows=[headers,["EXAMPLE — DELETE THIS ROW BEFORE IMPORT"]+['']*(len(headers)-1)]
    sheet_rows=[]
    for r,vals in enumerate(rows,1):
        cells=[]
        for c,v in enumerate(vals,1):
            ref=f"{xlsx_col(c)}{r}"
            cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{xml_escape(v)}</t></is></c>')
        sheet_rows.append(f'<row r="{r}">'+''.join(cells)+'</row>')
    instr=["Construction Control Bulk Import Template",f"Module: {module}","Use the Template sheet for import.","Delete the example row before importing.","Do not rename, reorder, add or remove columns.","Dates must be YYYY-MM-DD. Numbers must be numeric.","Required fields must be completed.","Import is atomic: any invalid data row means nothing is imported.","One workbook = one project + one module."]
    if module=="Manpower": instr.append("Allowed roles: "+", ".join(ROLE_VALUES))
    instr_xml=''.join(f'<row r="{i}"><c r="A{i}" t="inlineStr"><is><t>{xml_escape(v)}</t></is></c></row>' for i,v in enumerate(instr,1))
    content_types="""<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>"""
    rels="""<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>"""
    wb="""<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Instructions" sheetId="1" r:id="rId1"/><sheet name="Template" sheetId="2" r:id="rId2"/></sheets></workbook>"""
    wb_rels="""<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/></Relationships>"""
    sh1=f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{instr_xml}</sheetData></worksheet>"""
    sh2=f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{''.join(sheet_rows)}</sheetData></worksheet>"""
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,"w",zipfile.ZIP_DEFLATED) as z:
        for name,data in {"[Content_Types].xml":content_types,"_rels/.rels":rels,"xl/workbook.xml":wb,"xl/_rels/workbook.xml.rels":wb_rels,"xl/worksheets/sheet1.xml":sh1,"xl/worksheets/sheet2.xml":sh2}.items(): z.writestr(name,data)
    return bio.getvalue()

def parse_xlsx_rows(raw):
    import zipfile, xml.etree.ElementTree as ET
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            names=z.namelist()
            sheet="xl/worksheets/sheet2.xml" if "xl/worksheets/sheet2.xml" in names else next((n for n in names if n.startswith("xl/worksheets/sheet")),None)
            if not sheet: raise ValueError("Workbook has no worksheet")
            root=ET.fromstring(z.read(sheet))
    except zipfile.BadZipFile: raise ValueError("File is not a valid .xlsx workbook")
    ns={"m":"http://schemas.openxmlformats.org/spreadsheetml/2006/main"}; out=[]
    for row in root.findall(".//m:sheetData/m:row",ns):
        cells={}
        for cell in row.findall("m:c",ns):
            ref=cell.attrib.get("r",""); col="".join(ch for ch in ref if ch.isalpha()); idx=0
            for ch in col: idx=idx*26+ord(ch.upper())-64
            typ=cell.attrib.get("t")
            if typ=="inlineStr": val="".join(t.text or "" for t in cell.findall(".//m:t",ns))
            else:
                v=cell.find("m:v",ns); val=v.text if v is not None else ""
            cells[idx]=val
        if cells: out.append([cells.get(i,"") for i in range(1,max(cells)+1)])
    return out


TASK_IMPORT_HEADERS=["Task ID","Task","Start Date","Duration (working days)","Status","% Complete","Planned Men","Notes"]
TASK_STATUS_VALUES=("Starting","Ongoing","Held Up","Finished")
LEGACY_TASK_STATUS_MAP={"Not Started":"Starting","Started":"Ongoing"}
LEGACY_TASK_STATUS_REVERSE={"Starting":"Not Started","Ongoing":"Started","Held Up":"Held Up","Finished":"Finished"}
HELD_UP_REASONS=("Material","Design/RFI","Access","Labour","Permit","Client","Other")

def task_status(percent, explicit=None):
    if explicit in TASK_STATUS_VALUES: return explicit
    try: p=int(percent or 0)
    except Exception: p=0
    if p>=100: return "Finished"
    if p>0: return "Ongoing"
    return "Starting"

def task_progress(status,pct):
    s=LEGACY_TASK_STATUS_MAP.get(str(status or "").strip(),str(status or "").strip())
    if s=="Finished": return 100
    if s=="Starting": return 0
    try: p=int(pct)
    except Exception: p=1
    return max(1,min(99,p))

def assignment_rows_for_day(c, company_id, project_id, day):
    # Project assignment is the source of truth for daily site control. A staff
    # member may have been marked inactive in the master staff list after being
    # assigned, but an active assignment still needs to appear in the project's
    # daily attendance list. This also prevents the Staff tab and Daily Site
    # Control from disagreeing about who is assigned to a project.
    return c.execute("""SELECT a.*,s.id AS member_id,s.staff_ref,s.name,s.position,s.active AS staff_active
        FROM project_staff_assignments a
        JOIN staff s ON s.id=a.staff_id WHERE a.company_id=? AND a.project_id=?
        AND a.assignment_status='Active' AND a.start_date<=? AND (a.finish_date IS NULL OR a.finish_date>=?)
        ORDER BY s.name""",
        (company_id,project_id,day,day)).fetchall()

def make_task_xlsx_template(plan_name=""):
    import zipfile
    headers=TASK_IMPORT_HEADERS
    rows=[headers,["TASK-001","Example task","2026-09-21","3","Not Started","0","2","Delete this example row before import"]]
    def sheet(vals):
        out=[]
        for r,rv in enumerate(vals,1):
            cells=''.join(f'<c r="{xlsx_col(c)}{r}" t="inlineStr"><is><t>{xml_escape(v)}</t></is></c>' for c,v in enumerate(rv,1))
            out.append(f'<row r="{r}">{cells}</row>')
        return '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'+''.join(out)+'</sheetData></worksheet>'
    instructions=[
        "Construction Control Task Import Template",
        f"Programme: {plan_name}",
        "Delete the example row before importing.",
        "Required: Task, Start Date and Duration (working days).",
        "Status: Not Started, Started or Finished.",
        "Finished = 100%; Not Started = 0%; Started uses the % Complete value (1-99).",
        "Duration is in Monday-Friday working days.",
        "Task ID is optional for new tasks; if supplied it must be unique within the workbook.",
        "Import is atomic: if any row is invalid, no tasks are imported.",
    ]
    instr_xml=''.join(f'<row r="{i}"><c r="A{i}" t="inlineStr"><is><t>{xml_escape(v)}</t></is></c></row>' for i,v in enumerate(instructions,1))
    ct='<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>'
    rels='<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/package/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'
    wb='<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Instructions" sheetId="1" r:id="rId1"/><sheet name="Template" sheetId="2" r:id="rId2"/></sheets></workbook>'
    wb_rels='<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="worksheets/sheet2.xml"/></Relationships>'
    # Correct worksheet relationship types for Office Open XML.
    wb_rels=wb_rels.replace("application/vnd.openxmlformats.org","http://schemas.openxmlformats.org")
    sh1=f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{instr_xml}</sheetData></worksheet>'
    sh2=sheet(rows)
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,"w",zipfile.ZIP_DEFLATED) as z:
        for n,v in {"[Content_Types].xml":ct,"_rels/.rels":rels,"xl/workbook.xml":wb,"xl/_rels/workbook.xml.rels":wb_rels,"xl/worksheets/sheet1.xml":sh1,"xl/worksheets/sheet2.xml":sh2}.items(): z.writestr(n,v)
    return bio.getvalue()

class Handler(BaseHTTPRequestHandler):
    def end_headers(self):
        # Baseline browser security headers applied to API and static responses.
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        # HSTS is only safe to emit when the request is actually HTTPS (including a TLS
        # reverse proxy such as Render). Local HTTP development therefore remains usable.
        # parse_request() can fail before BaseHTTPRequestHandler creates `headers`
        # (for example when an HTTPS/TLS client accidentally connects to this plain
        # HTTP development port). Never let the security-header hook mask the real
        # 400 error with AttributeError.
        request_headers = getattr(self, "headers", None)
        forwarded_proto = request_headers.get("X-Forwarded-Proto", "").lower() if request_headers else ""
        if forwarded_proto == "https":
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        super().end_headers()

    def j(self,status,obj,headers=None):
        self.send_response(status); self.send_header("Content-Type","application/json"); self.send_header("Cache-Control","no-store")
        for k,v in (headers or {}).items(): self.send_header(k,v)
        self.end_headers(); self.wfile.write(json.dumps(obj).encode())
    def xlsx_response(self, data, filename):
        # HTTP/1.1 headers are latin-1 in BaseHTTPRequestHandler; programme names may contain
        # Unicode punctuation such as an em dash, so use a safe ASCII download filename.
        safe_filename=filename.replace(chr(34),"").encode("ascii","ignore").decode("ascii")
        self.send_response(200); self.send_header("Content-Type","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.send_header("Content-Disposition",f'attachment; filename="{safe_filename}"'); self.send_header("Content-Length",str(len(data))); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(data)

    def multipart_file(self):
        from email.parser import BytesParser
        from email.policy import default
        ctype=self.headers.get("Content-Type","")
        if not ctype.lower().startswith("multipart/form-data"): raise ValueError("Expected an Excel file upload")
        n=int(self.headers.get("Content-Length","0"))
        if n<=0 or n>12*1024*1024: raise ValueError("Upload is missing or too large")
        raw=self.rfile.read(n)
        msg=BytesParser(policy=default).parsebytes(("Content-Type: "+ctype+"\r\nMIME-Version: 1.0\r\n\r\n").encode()+raw)
        for part in msg.iter_attachments():
            payload=part.get_payload(decode=True) or b""
            if payload: return part.get_filename() or "upload.xlsx", payload
        raise ValueError("No uploaded file found")

    def _task_import_rows(self,raw):
        rows=parse_xlsx_rows(raw)
        return rows

    def handle_programme_export(self,c,u,plan_id):
        plan=c.execute("SELECT * FROM plans WHERE id=? AND company_id=?",(plan_id,u["company_id"])).fetchone()
        if not plan or not can_access_project(c,u,plan["project_id"]): self.j(404,{"error":"Programme not found"}); return
        if not has_permission(c,u,"Projects","View"): self.j(403,{"error":"Project view permission required"}); return
        rows=c.execute("SELECT * FROM plan_tasks WHERE plan_id=? AND project_id=? ORDER BY start_date,id",(plan_id,plan["project_id"])).fetchall()
        headers=[x[0] for x in PROGRAMME_IMPORT_HEADERS]
        data=[headers]
        for x in rows:
            aid=x["activity_id"] or x["id"]
            parent=""
            pred=""
            if x["parent_id"]:
                r=c.execute("SELECT activity_id,id FROM plan_tasks WHERE id=? AND plan_id=?",(x["parent_id"],plan_id)).fetchone(); parent=(r["activity_id"] or r["id"]) if r else ""
            if x["predecessor_id"]:
                r=c.execute("SELECT activity_id,id FROM plan_tasks WHERE id=? AND plan_id=?",(x["predecessor_id"],plan_id)).fetchone(); pred=(r["activity_id"] or r["id"]) if r else ""
            data.append([aid,x["name"],parent,x["start_date"],x["finish_date"],str(x["percent_complete"] or 0),str(x["planned_men"] or 0),pred,x["dependency_type"] or "FS",str(x["lag_days"] or 0),"Yes" if x["milestone"] else "No",x["notes"] or "",x["actual_start"] or "",x["actual_finish"] or "",x["baseline_start"] or "",x["baseline_finish"] or ""])
        bio=io.BytesIO(); import zipfile
        def esc(v): return xml_escape(v)
        def sheet(vals):
            sr=[]
            for r,rv in enumerate(vals,1):
                cells=''.join(f'<c r="{xlsx_col(c)}{r}" t="inlineStr"><is><t>{esc(v)}</t></is></c>' for c,v in enumerate(rv,1))
                sr.append(f'<row r="{r}">{cells}</row>')
            return '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'+''.join(sr)+'</sheetData></worksheet>'
        instructions=["Construction Control Programme Export","This workbook is a round-trip copy of the selected programme.","Activity ID is the stable reference used for updates and Parent/Predecessor links.","Edit existing rows to update them, or add new rows with new Activity IDs.","Use the same columns and formats as the programme import template.","Upload using the Programme Round-trip workflow and review the validation preview before committing."]
        instr=''.join(f'<row r="{i}"><c r="A{i}" t="inlineStr"><is><t>{esc(v)}</t></is></c></row>' for i,v in enumerate(instructions,1))
        ct='<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>'
        rels='<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'
        wb='<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Instructions" sheetId="1" r:id="rId1"/><sheet name="Programme" sheetId="2" r:id="rId2"/></sheets></workbook>'
        wb_rels='<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/></Relationships>'
        with zipfile.ZipFile(bio,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('[Content_Types].xml',ct); z.writestr('_rels/.rels',rels); z.writestr('xl/workbook.xml',wb); z.writestr('xl/_rels/workbook.xml.rels',wb_rels); z.writestr('xl/worksheets/sheet1.xml',f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{instr}</sheetData></worksheet>'); z.writestr('xl/worksheets/sheet2.xml',sheet(data))
        self.xlsx_response(bio.getvalue(),f'Construction_Control_Programme_{plan["name"].replace(chr(34),"")}.xlsx')

    def handle_programme_roundtrip(self,c,u,plan_id,commit=False):
        plan=c.execute("SELECT * FROM plans WHERE id=? AND company_id=?",(plan_id,u["company_id"])).fetchone()
        if not plan or not can_access_project(c,u,plan["project_id"]): self.j(404,{"error":"Programme not found"}); return
        if not has_permission(c,u,"Projects","Edit"): self.j(403,{"error":"Project edit permission required"}); return
        try: filename,raw=self.multipart_file(); rows=parse_xlsx_rows(raw)
        except Exception as e: self.j(400,{"error":str(e)}); return
        expected=[x[0] for x in PROGRAMME_IMPORT_HEADERS]
        if not rows: self.j(400,{"error":"Workbook contains no rows"}); return
        if [str(x).strip() for x in rows[0]]!=expected: self.j(400,{"error":"Programme template columns do not match","expected_columns":expected,"received_columns":rows[0]}); return
        existing_rows=c.execute("SELECT * FROM plan_tasks WHERE plan_id=? AND project_id=?",(plan_id,plan["project_id"])).fetchall()
        existing={ (r["activity_id"] or r["id"]):r for r in existing_rows }
        seen=set(); parsed=[]; errors=[]; refs=[]; changes=[]
        for idx,row in enumerate(rows[1:],2):
            if not any(normalise_cell(x) for x in row): continue
            def cell(name):
                i=expected.index(name); return normalise_cell(row[i] if i<len(row) else "")
            if cell("Activity")=="EXAMPLE — DELETE THIS ROW BEFORE IMPORT": continue
            aid,name=cell("Activity ID"),cell("Activity")
            if not aid or not name: errors.append({"row":idx,"errors":["Activity ID and Activity are required"]}); continue
            if aid in seen: errors.append({"row":idx,"errors":["Duplicate Activity ID in workbook"]}); continue
            seen.add(aid)
            sd,fd=cell("Start Date"),cell("Finish Date")
            try:
                ds,df=date.fromisoformat(sd),date.fromisoformat(fd)
                if df<ds: raise ValueError
            except Exception: errors.append({"row":idx,"errors":["Invalid start/finish date range"]}); continue
            try: pct=int(float(cell("% Complete") or 0)); men=float(cell("Planned Men") or 0); lag=int(float(cell("Lag Days") or 0))
            except Exception: errors.append({"row":idx,"errors":["Percent complete, Planned Men and Lag Days must be numeric"]}); continue
            parent,pred=cell("Parent ID") or None,cell("Predecessor ID") or None; dep=(cell("Dependency Type") or "FS").upper(); ms=(cell("Milestone") or "No").lower()
            if pct<0 or pct>100 or men<0 or lag<0 or dep not in ("FS","SS","FF","SF") or ms not in ("yes","no","1","0"):
                errors.append({"row":idx,"errors":["Invalid progress, manpower, lag, dependency type or milestone value"]}); continue
            def opt(label):
                v=cell(label)
                if v:
                    try: date.fromisoformat(v)
                    except Exception: errors.append({"row":idx,"errors":[f"Invalid {label}"]})
                return v or None
            actual_start,actual_finish,bs,bf=[opt(x) for x in ("Actual Start","Actual Finish","Baseline Start","Baseline Finish")]
            if actual_start and actual_finish and actual_finish<actual_start: errors.append({"row":idx,"errors":["Actual finish cannot be before actual start"]})
            if bs and bf and bf<bs: errors.append({"row":idx,"errors":["Baseline finish cannot be before baseline start"]})
            action="update" if aid in existing else "add"
            parsed.append((aid,name,parent,sd,fd,pct,men,pred,dep,lag,1 if ms in ("yes","1") else 0,cell("Notes"),actual_start,actual_finish,bs,bf,idx,action)); refs.append((parent,pred,idx,aid))
            changes.append({"row":idx,"activity_id":aid,"action":action,"activity":name})
        ids=set(existing)|{x[0] for x in parsed}
        for parent,pred,row,aid in refs:
            if parent and parent not in ids: errors.append({"row":row,"errors":["Parent ID does not exist"]})
            if pred and pred not in ids: errors.append({"row":row,"errors":["Predecessor ID does not exist"]})
            if aid in (parent,pred): errors.append({"row":row,"errors":["Activity cannot reference itself"]})
        graph={k:(existing[k]["predecessor_id"] and (existing[k]["predecessor_id"] if existing[k]["predecessor_id"] in {r["id"] for r in existing.values()} else None)) for k in existing}
        # Convert existing DB predecessor IDs to activity IDs.
        db_to_aid={r["id"]:(r["activity_id"] or r["id"]) for r in existing_rows}
        graph={k:db_to_aid.get(r["predecessor_id"]) for k,r in existing.items()}
        for x in parsed: graph[x[0]]=x[7]
        visiting=set(); visited=set()
        def dfs(k):
            if k in visiting:return False
            if k in visited:return True
            visiting.add(k); q=graph.get(k)
            if q and not dfs(q): return False
            visiting.remove(k); visited.add(k); return True
        if any(not dfs(k) for k in graph): errors.append({"row":0,"errors":["Dependency cycle detected in round-trip"]})
        if errors or not parsed:
            self.j(400,{"error":"Programme round-trip validation failed; nothing was changed","rows_read":max(0,len(rows)-1),"rows_processed":len(parsed),"rows_rejected":len(errors) or 1,"changes":changes,"errors":errors[:100]}); return
        if not commit:
            self.j(200,{"ok":True,"preview":True,"filename":filename,"rows_read":len(rows)-1,"rows_processed":len(parsed),"adds":sum(1 for x in parsed if x[-1]=="add"),"updates":sum(1 for x in parsed if x[-1]=="update"),"unchanged":0,"changes":changes}); return
        try:
            c.execute("BEGIN")
            idmap={aid:(existing[aid]["id"] if aid in existing else secrets.token_hex(8)) for aid,*_ in parsed}
            for aid,name,parent,sd,fd,pct,men,pred,dep,lag,milestone,notes,actual_start,actual_finish,bs,bf,_,action in parsed:
                tid=idmap[aid]; parent_id=idmap.get(parent) if parent else None; pred_id=idmap.get(pred) if pred else None
                if action=="update":
                    c.execute("UPDATE plan_tasks SET parent_id=?,name=?,start_date=?,finish_date=?,percent_complete=?,planned_men=?,predecessor_id=?,milestone=?,notes=?,dependency_type=?,lag_days=?,activity_id=?,actual_start=?,actual_finish=?,baseline_start=?,baseline_finish=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND plan_id=?",(parent_id,name,sd,fd,pct,men,pred_id,milestone,notes,dep,lag,aid,actual_start,actual_finish,bs,bf,tid,plan_id))
                else:
                    c.execute("INSERT INTO plan_tasks(id,plan_id,project_id,parent_id,name,start_date,finish_date,percent_complete,planned_men,predecessor_id,milestone,notes,dependency_type,lag_days,activity_id,actual_start,actual_finish,baseline_start,baseline_finish) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(tid,plan_id,plan["project_id"],parent_id,name,sd,fd,pct,men,pred_id,milestone,notes,dep,lag,aid,actual_start,actual_finish,bs,bf))
            c.execute("UPDATE plans SET updated_at=CURRENT_TIMESTAMP WHERE id=?",(plan_id,)); iid=secrets.token_hex(8); audit_row(c,u,"PROGRAMME_ROUNDTRIP_IMPORT",f"{plan_id}:{iid}"); c.commit()
        except Exception:
            c.rollback(); self.j(400,{"error":"Programme round-trip failed; nothing was changed"}); return
        self.j(200,{"ok":True,"committed":True,"import_id":iid,"filename":filename,"rows_processed":len(parsed),"adds":sum(1 for x in parsed if x[-1]=="add"),"updates":sum(1 for x in parsed if x[-1]=="update")})

    def handle_programme_import(self,c,u,plan_id):
        plan=c.execute("SELECT * FROM plans WHERE id=? AND company_id=?",(plan_id,u["company_id"])).fetchone()
        if not plan or not can_access_project(c,u,plan["project_id"]): self.j(404,{"error":"Programme not found"}); return
        if not has_permission(c,u,"Projects","Edit"): self.j(403,{"error":"Project edit permission required"}); return
        try: filename,raw=self.multipart_file(); rows=parse_xlsx_rows(raw)
        except Exception as e: self.j(400,{"error":str(e)}); return
        expected=[x[0] for x in PROGRAMME_IMPORT_HEADERS]
        if not rows: self.j(400,{"error":"Workbook contains no rows"}); return
        if [str(x).strip() for x in rows[0]]!=expected: self.j(400,{"error":"Programme template columns do not match","expected_columns":expected,"received_columns":rows[0]}); return
        existing={r["id"] for r in c.execute("SELECT id FROM plan_tasks WHERE plan_id=?",(plan_id,)).fetchall()}; seen=set(); parsed=[]; errors=[]; refs=[]
        for idx,row in enumerate(rows[1:],2):
            if not any(normalise_cell(x) for x in row): continue
            def cell(name):
                i=expected.index(name); return normalise_cell(row[i] if i<len(row) else "")
            if cell("Activity")=="EXAMPLE — DELETE THIS ROW BEFORE IMPORT": continue
            aid,name=cell("Activity ID"),cell("Activity")
            if not aid or not name: errors.append({"row":idx,"errors":["Activity ID and Activity are required"]}); continue
            if aid in seen or aid in existing: errors.append({"row":idx,"errors":["Duplicate Activity ID"]}); continue
            seen.add(aid)
            sd,fd=cell("Start Date"),cell("Finish Date")
            try:
                ds,df=date.fromisoformat(sd),date.fromisoformat(fd)
                if df<ds: raise ValueError
            except Exception: errors.append({"row":idx,"errors":["Invalid start/finish date range"]}); continue
            try: pct=int(float(cell("% Complete") or 0)); men=float(cell("Planned Men") or 0); lag=int(float(cell("Lag Days") or 0))
            except Exception: errors.append({"row":idx,"errors":["Percent complete, Planned Men and Lag Days must be numeric"]}); continue
            parent,pred=cell("Parent ID") or None,cell("Predecessor ID") or None; dep=(cell("Dependency Type") or "FS").upper(); ms=(cell("Milestone") or "No").lower()
            if pct<0 or pct>100 or men<0 or lag<0 or dep not in ("FS","SS","FF","SF") or ms not in ("yes","no","1","0"): errors.append({"row":idx,"errors":["Invalid progress, manpower, lag, dependency type or milestone value"]}); continue
            def valid_optional(label):
                v=cell(label)
                if v:
                    try: date.fromisoformat(v)
                    except Exception: errors.append({"row":idx,"errors":[f"Invalid {label}"]})
                return v or None
            actual_start,actual_finish,bs,bf=[valid_optional(x) for x in ("Actual Start","Actual Finish","Baseline Start","Baseline Finish")]
            if actual_start and actual_finish and actual_finish<actual_start: errors.append({"row":idx,"errors":["Actual finish cannot be before actual start"]})
            if bs and bf and bf<bs: errors.append({"row":idx,"errors":["Baseline finish cannot be before baseline start"]})
            parsed.append((aid,name,parent,sd,fd,pct,men,pred,dep,lag,1 if ms in ("yes","1") else 0,cell("Notes"),actual_start,actual_finish,bs,bf,idx)); refs.append((parent,pred,idx,aid))
        ids={x[0] for x in parsed}
        for parent,pred,row,aid in refs:
            if parent and parent not in ids: errors.append({"row":row,"errors":["Parent ID does not exist in import"]})
            if pred and pred not in ids: errors.append({"row":row,"errors":["Predecessor ID does not exist in import"]})
            if aid in (parent,pred): errors.append({"row":row,"errors":["Activity cannot reference itself"]})
        graph={x[0]:x[7] for x in parsed}; visiting=set(); visited=set()
        def dfs(k):
            if k in visiting:return False
            if k in visited:return True
            visiting.add(k); q=graph.get(k)
            if q and not dfs(q): return False
            visiting.remove(k); visited.add(k); return True
        if any(not dfs(k) for k in graph): errors.append({"row":0,"errors":["Dependency cycle detected in import"]})
        if errors or not parsed: self.j(400,{"error":"Programme import validation failed; nothing was imported","rows_read":max(0,len(rows)-1),"rows_imported":0,"rows_rejected":len(errors) or 1,"errors":errors[:100]}); return
        try:
            c.execute("BEGIN"); idmap={x[0]:secrets.token_hex(8) for x in parsed}
            for aid,name,parent,sd,fd,pct,men,pred,dep,lag,milestone,notes,actual_start,actual_finish,bs,bf,_ in parsed:
                c.execute("INSERT INTO plan_tasks(id,plan_id,project_id,parent_id,name,start_date,finish_date,percent_complete,planned_men,predecessor_id,milestone,notes,dependency_type,lag_days,activity_id,actual_start,actual_finish,baseline_start,baseline_finish) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(idmap[aid],plan_id,plan["project_id"],idmap.get(parent) if parent else None,name,sd,fd,pct,men,idmap.get(pred) if pred else None,milestone,notes,dep,lag,aid,actual_start,actual_finish,bs,bf))
            iid=secrets.token_hex(8); audit_row(c,u,"PROGRAMME_BULK_IMPORT",f"{plan_id}:{iid}"); c.commit()
        except Exception:
            c.rollback(); self.j(400,{"error":"Programme import failed; nothing was imported"}); return
        self.j(201,{"ok":True,"import_id":iid,"filename":filename,"rows_read":len(rows)-1,"rows_imported":len(parsed),"rows_rejected":0})

    def handle_bulk_import(self,c,u,project_id,module):
        if not valid_module(module) or not bulk_spec(module): self.j(400,{"error":"Bulk import is not available for this module"}); return
        if not can_access_project(c,u,project_id): self.j(403,{"error":"Project access required"}); return
        if not has_permission(c,u,module,"Create"): self.j(403,{"error":"Create permission required"}); return
        try: filename,raw=self.multipart_file(); rows=parse_xlsx_rows(raw)
        except Exception as e: self.j(400,{"error":str(e)}); return
        expected=[x[0] for x in bulk_spec(module)]
        if not rows: self.j(400,{"error":"Workbook contains no rows"}); return
        headers=[str(x).strip() for x in rows[0]]
        if headers!=expected: self.j(400,{"error":"Template columns do not match the selected module","expected_columns":expected,"received_columns":headers}); return
        imported=[]; rejected=[]; seen=set()
        for idx,row in enumerate(rows[1:],2):
            if not any(normalise_cell(x) for x in row): continue
            vals={expected[i]:row[i] if i<len(row) else "" for i in range(len(expected))}
            # Ignore the bundled example row if the user forgot to delete it.
            if normalise_cell(vals.get("Title"))=="EXAMPLE — DELETE THIS ROW BEFORE IMPORT": continue
            item,errs=validate_bulk_row(module,headers,vals)
            if errs: rejected.append({"row":idx,"errors":errs}); continue
            key=item["title"].casefold()
            if key in seen: rejected.append({"row":idx,"errors":["Duplicate title in this import"]}); continue
            existing=c.execute("SELECT 1 FROM module_records WHERE company_id=? AND project_id=? AND module=? AND lower(title)=lower(?) LIMIT 1",(u["company_id"],project_id,module,item["title"])).fetchone()
            if existing: rejected.append({"row":idx,"errors":["A record with this title already exists in the selected project/module"]}); continue
            seen.add(key); imported.append(item)
        if rejected or not imported:
            self.j(400,{"error":"Import validation failed; nothing was imported","rows_read":max(0,len(rows)-1),"rows_imported":0,"rows_rejected":len(rejected),"errors":rejected[:100]}); return
        try:
            c.execute("BEGIN")
            for item in imported:
                rid=secrets.token_hex(8); c.execute("INSERT INTO module_records(id,company_id,project_id,module,title,data_json,created_by) VALUES(?,?,?,?,?,?,?)",(rid,u["company_id"],project_id,module,item["title"],json.dumps(item["data"]),u["id"]))
            jid=secrets.token_hex(8); c.execute("INSERT INTO bulk_imports(id,company_id,project_id,module,filename,rows_read,rows_imported,rows_rejected,errors_json,created_by) VALUES(?,?,?,?,?,?,?,?,?,?)",(jid,u["company_id"],project_id,module,filename,len(rows)-1,len(imported),0,"[]",u["id"]))
            audit_row(c,u,"BULK_IMPORT",f"{module}:{jid}"); c.commit()
        except Exception:
            c.rollback(); self.j(400,{"error":"Import failed; nothing was imported"}); return
        self.j(201,{"ok":True,"import_id":jid,"filename":filename,"rows_read":len(rows)-1,"rows_imported":len(imported),"rows_rejected":0})

    def body(self):
        n=int(self.headers.get("Content-Length","0"))
        if n < 0 or n > 12*1024*1024:
            raise ValueError("Request body too large")
        return json.loads(self.rfile.read(n) or "{}")
    def auth(self,c):
        raw=next((x.split("=",1)[1] for x in self.headers.get("Cookie","").split("; ") if x.startswith("cc_session=")),None)
        if not raw:return None
        row=c.execute("SELECT u.*,s.expires_at FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>strftime('%s','now')",(hashlib.sha256(raw.encode()).hexdigest(),)).fetchone()
        return row if row and row["active"] else None
    def do(self):
        path=unquote(urlparse(self.path).path)
        # Reject path-normalisation tricks such as /api/projects/P2/../P1.
        # Resource IDs are opaque identifiers, not filesystem paths.
        if path.startswith("/api/"):
            import posixpath
            if posixpath.normpath(path) != path:
                self.j(400,{"error":"Invalid API path"}); return
        if self.command=="GET" and path=="/healthz":
            # Phase 32.18 no-disk mode: the app may run on Render's ephemeral
            # filesystem. Keep the database usable, but expose the storage
            # warning so operators know backups are required.
            st=storage_status()
            self.j(200,{"status":"ok","storage":st,
                        "warning":("Render storage is ephemeral. Download a Full Backup before redeploying or restarting the service."
                                   if not st["data_dir_mount"] else "Persistent storage is mounted.")})
            return
        c=db()
        try:
            if self.command=="POST" and path=="/api/login":
                try:b=self.body()
                except:self.j(400,{"error":"Invalid JSON"});return
                u=c.execute("SELECT * FROM users WHERE lower(email)=lower(?)",(str(b.get("email","")).strip(),)).fetchone()
                if not u or not u["active"] or not pw_ok(str(b.get("password","")),u["password_hash"]): self.j(401,{"error":"Invalid email or password"});return
                raw=secrets.token_urlsafe(32);c.execute("INSERT INTO sessions VALUES(?,?,strftime('%s','now')+?)",(hashlib.sha256(raw.encode()).hexdigest(),u["id"],SESSION_HOURS*3600));audit_row(c,u,"LOGIN","session");c.commit();co=c.execute("SELECT * FROM companies WHERE id=?",(u["company_id"],)).fetchone();self.j(200,{"user":public_user(u),"company":public_company(co)},{"Set-Cookie":f"cc_session={raw}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_HOURS*3600}" + ("; Secure" if self.headers.get("X-Forwarded-Proto","").lower()=="https" or os.getenv("SECURE_COOKIES")=="1" else "")});return
            u=self.auth(c)
            if not u:self.j(401,{"error":"Authentication required"});return
            if self.command=="POST" and path=="/api/logout":
                raw=next((x.split("=",1)[1] for x in self.headers.get("Cookie","").split("; ") if x.startswith("cc_session=")),None)
                if raw:c.execute("DELETE FROM sessions WHERE token_hash=?",(hashlib.sha256(raw.encode()).hexdigest(),))
                audit_row(c,u,"LOGOUT","session");c.commit();self.j(200,{"ok":True},{"Set-Cookie":"cc_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0" + ("; Secure" if self.headers.get("X-Forwarded-Proto","").lower()=="https" or os.getenv("SECURE_COOKIES")=="1" else "")});return
            if self.command=="GET" and path=="/api/storage/status":
                if u["role"] != "Company Administrator": self.j(403,{"error":"Administrator access required"}); return
                self.j(200,{"storage":storage_status()}); return
            if self.command=="GET" and path=="/api/backup/export":
                handle_backup_export(self,c,u); return
            if self.command=="POST" and path=="/api/backup/restore":
                handle_backup_restore(self,c,u); return
            if self.command=="GET" and path=="/api/me":
                co=c.execute("SELECT * FROM companies WHERE id=?",(u["company_id"],)).fetchone();self.j(200,{"user":public_user(u),"company":public_company(co)});return
            if self.command=="GET" and path=="/api/dashboard":
                # Tenant-safe management summary. Non-admins only see projects they can access.
                # Optional as_of lets the UI use the user's local calendar date for daily attention.
                _dq=_parse_qs(urlparse(self.path).query)
                dashboard_day=(_dq.get("as_of") or [date.today().isoformat()])[0]
                try: date.fromisoformat(dashboard_day)
                except Exception: self.j(400,{"error":"as_of must be YYYY-MM-DD"}); return
                if u["role"]=="Company Administrator":
                    projects=c.execute("SELECT id,name FROM projects WHERE company_id=? ORDER BY name",(u["company_id"],)).fetchall()
                else:
                    projects=c.execute("SELECT p.id,p.name FROM projects p JOIN project_access pa ON pa.project_id=p.id WHERE p.company_id=? AND pa.user_id=? ORDER BY p.name",(u["company_id"],u["id"])).fetchall()
                pids=[x["id"] for x in projects]
                summary=[]
                for pr in projects:
                    pid=pr["id"]
                    counts=c.execute("SELECT module,COUNT(*) n FROM module_records WHERE company_id=? AND project_id=? GROUP BY module",(u["company_id"],pid)).fetchall()
                    modules={x["module"]:x["n"] for x in counts}
                    records=sum(modules.values())
                    open_rfIs=c.execute("SELECT COUNT(*) FROM module_records WHERE company_id=? AND project_id=? AND module='RFIs'",(u["company_id"],pid)).fetchone()[0]
                    open_risks=c.execute("SELECT COUNT(*) FROM module_records WHERE company_id=? AND project_id=? AND module='Risks'",(u["company_id"],pid)).fetchone()[0]
                    open_actions=c.execute("SELECT COUNT(*) FROM module_records WHERE company_id=? AND project_id=? AND module='Actions'",(u["company_id"],pid)).fetchone()[0]
                    open_snags=c.execute("SELECT COUNT(*) FROM module_records WHERE company_id=? AND project_id=? AND module='Snags'",(u["company_id"],pid)).fetchone()[0]
                    pending_approvals=c.execute("SELECT COUNT(*) FROM workflows WHERE company_id=? AND project_id=? AND status='Pending'",(u["company_id"],pid)).fetchone()[0]
                    docs=c.execute("SELECT COUNT(*) FROM attachments WHERE company_id=? AND project_id=?",(u["company_id"],pid)).fetchone()[0]
                    plan_rows=c.execute("SELECT * FROM plans WHERE company_id=? AND project_id=? ORDER BY updated_at DESC,created_at DESC",(u["company_id"],pid)).fetchall()
                    plans=[]
                    for pl in plan_rows:
                        tasks=c.execute("SELECT percent_complete,start_date,finish_date FROM plan_tasks WHERE plan_id=? AND project_id=?",(pl["id"],pid)).fetchall()
                        total=len(tasks)
                        progress=round(sum(float(x["percent_complete"] or 0) for x in tasks)/total,1) if total else 0.0
                        finish=max((x["finish_date"] for x in tasks),default=None)
                        plans.append({"id":pl["id"],"name":pl["name"],"status":pl["status"],"baseline":bool(pl["baseline"]),"progress":progress,"activity_count":total,"finish":finish})
                    active_plan=next((x for x in plans if x["status"]=="Active"),plans[0] if plans else None)
                    # Live manpower summary: read the actual project records, not test fixtures.
                    mp_rows=c.execute("SELECT data_json FROM module_records WHERE company_id=? AND project_id=? AND module='Manpower'",(u["company_id"],pid)).fetchall()
                    planned_men=project_manloader(c,u["company_id"],pid)
                    actual_men=man_hours=0.0
                    for mr in mp_rows:
                        try: md=json.loads(mr["data_json"] or "{}")
                        except Exception: md={}
                        try: actual_men += float(md.get("actual_men",0) or 0)
                        except Exception: pass
                        try: man_hours += float(md.get("actual_men",0) or 0) * float(md.get("hours",0) or 0)
                        except Exception: pass
                    # Baseline/current programme variance is calculated from the same plan data exposed to Planning.
                    programme_variance=None
                    if active_plan:
                        bfinish=c.execute("SELECT MAX(baseline_finish) FROM plan_tasks WHERE plan_id=? AND project_id=? AND baseline_finish IS NOT NULL",(active_plan["id"],pid)).fetchone()[0]
                        cfinish=c.execute("SELECT MAX(finish_date) FROM plan_tasks WHERE plan_id=? AND project_id=?",(active_plan["id"],pid)).fetchone()[0]
                        if bfinish and cfinish:
                            try:
                                programme_variance=int(c.execute("SELECT CAST(julianday(?) - julianday(?) AS INTEGER)",(cfinish,bfinish)).fetchone()[0])
                            except Exception:
                                programme_variance=None
                    task_count=0; task_progress_value=0.0
                    today_tasks=[]; late_tasks=[]; planned_today=0.0
                    if active_plan:
                        task_rows=c.execute("SELECT id,name,start_date,finish_date,percent_complete,planned_men,task_status FROM plan_tasks WHERE plan_id=? AND project_id=? ORDER BY start_date,id",(active_plan["id"],pid)).fetchall()
                        task_count=len(task_rows); task_progress_value=round(sum(float(x["percent_complete"] or 0) for x in task_rows)/task_count,1) if task_count else 0.0
                        for tr in task_rows:
                            pct=int(tr["percent_complete"] or 0); st=task_status(pct,tr["task_status"])
                            if tr["start_date"]<=dashboard_day<=tr["finish_date"] and st!="Finished":
                                planned_today += float(tr["planned_men"] or 0)
                            if tr["start_date"]==dashboard_day:
                                today_tasks.append({"id":tr["id"],"plan_id":active_plan["id"],"name":tr["name"],"start_date":tr["start_date"],"finish_date":tr["finish_date"],"percent_complete":pct,"status":st,"planned_men":float(tr["planned_men"] or 0),"bucket":"starting"})
                            elif tr["start_date"]<dashboard_day and st=="Starting":
                                late_tasks.append({"id":tr["id"],"plan_id":active_plan["id"],"name":tr["name"],"start_date":tr["start_date"],"finish_date":tr["finish_date"],"percent_complete":pct,"status":st,"planned_men":float(tr["planned_men"] or 0),"bucket":"late_start"})
                    # Actual attendance is scoped to the selected dashboard day.
                    today_att=c.execute("SELECT COUNT(*) n FROM daily_attendance WHERE company_id=? AND project_id=? AND work_date=? AND onsite=1",(u["company_id"],pid,dashboard_day)).fetchone()[0]
                    daily_saved=bool(c.execute("SELECT 1 FROM module_records WHERE company_id=? AND project_id=? AND module='Daily Control' AND json_extract(data_json,'$.date')=? LIMIT 1",(u["company_id"],pid,dashboard_day)).fetchone())
                    # Management health must see problems recorded against any project programme,
                    # not only whichever plan happens to be selected as active. This prevents a held-up
                    # task being hidden simply because the update was saved against another programme.
                    health_rows=c.execute("SELECT percent_complete,task_status,finish_date FROM plan_tasks WHERE project_id=?",(pid,)).fetchall()
                    held_up=sum(1 for x in health_rows if task_status(x["percent_complete"],x["task_status"])=="Held Up")
                    overdue=sum(1 for x in health_rows if x["finish_date"]<dashboard_day and task_status(x["percent_complete"],x["task_status"])!="Finished")
                    manpower_gap=today_att < planned_today
                    health="red" if held_up or overdue else ("amber" if manpower_gap or late_tasks else "green")
                    summary.append({"project_id":pid,"project_name":pr["name"],"records":records,"modules":modules,
                                    "kpis":{"rfis":open_rfIs,"risks":open_risks,"actions":open_actions,"snags":open_snags,"pending_approvals":pending_approvals,"documents":docs,"tasks":task_count},
                                    "manpower":{"planned_men":planned_men,"actual_men":actual_men,"variance_men":round(actual_men-planned_men,1),"man_hours":man_hours},
                                    "programme":{"finish_variance_days":programme_variance,"task_progress":task_progress_value,"task_count":task_count,"held_up":held_up,"overdue":overdue},"health":health,
                                    "today":{"date":dashboard_day,"tasks_starting":today_tasks,"tasks_late":late_tasks,"planned_men":planned_today,"actual_men":today_att,"daily_saved":daily_saved},
                                    "plans":plans,"active_plan":active_plan})
                total_records=sum(x["records"] for x in summary)
                total_kpis={k:sum(x["kpis"][k] for x in summary) for k in ("rfis","risks","actions","snags","pending_approvals","documents","tasks")}
                recent=c.execute("SELECT a.created_at,a.action,a.target,u.name user_name FROM audit a LEFT JOIN users u ON u.id=a.user_id WHERE a.company_id=? ORDER BY a.id DESC LIMIT 10",(u["company_id"],)).fetchall()
                self.j(200,{"date":dashboard_day,"projects":[dict(x) for x in projects],"project_summary":summary,"total_records":total_records,"total_kpis":total_kpis,"recent_audit":[dict(x) for x in recent]});return
            if self.command=="GET" and path=="/api/project-overview":
                from urllib.parse import parse_qs as _pqs
                qs=_pqs(urlparse(self.path).query); project_id=(qs.get("project_id") or [None])[0]
                if not project_id or not can_access_project(c,u,project_id): self.j(403,{"error":"Project access required"}); return
                project=c.execute("SELECT id,name,company_id,level_id,manloader FROM projects WHERE id=? AND company_id=?",(project_id,u["company_id"])).fetchone()
                if not project: self.j(404,{"error":"Project not found"}); return
                # Only expose module summaries/records the current user can view.
                visible=[m for m in MODULES if has_permission(c,u,m,"View")]
                counts={m:0 for m in visible}; recent=[]; attention=[]
                closed={"closed","complete","completed","approved","resolved","done"}
                rows=c.execute("SELECT id,module,title,data_json,created_at,updated_at FROM module_records WHERE company_id=? AND project_id=? ORDER BY id DESC",(u["company_id"],project_id)).fetchall()
                for r in rows:
                    if r["module"] not in counts: continue
                    counts[r["module"]]+=1
                    try: data=json.loads(r["data_json"] or "{}")
                    except Exception: data={}
                    if len(recent)<10:
                        recent.append({"id":r["id"],"module":r["module"],"title":r["title"],"status":data.get("status") or "Open","created_at":r["created_at"],"updated_at":r["updated_at"]})
                    status=str(data.get("status","")).strip().lower()
                    due=data.get("due_date") or data.get("target_date") or data.get("required_by") or data.get("expiry_date")
                    if due and str(due)<date.today().isoformat() and status not in closed:
                        attention.append({"id":r["id"],"module":r["module"],"title":r["title"],"status":data.get("status") or "Open","due_date":str(due),"kind":"Overdue"})
                pending=c.execute("SELECT COUNT(*) FROM workflows WHERE company_id=? AND project_id=? AND status='Pending'",(u["company_id"],project_id)).fetchone()[0]
                docs=c.execute("SELECT COUNT(*) FROM attachments WHERE company_id=? AND project_id=?",(u["company_id"],project_id)).fetchone()[0] if has_permission(c,u,"Documents","View") else 0
                mp=c.execute("SELECT data_json FROM module_records WHERE company_id=? AND project_id=? AND module='Manpower'",(u["company_id"],project_id)).fetchall() if "Manpower" in visible else []
                planned=project_manloader(c,u["company_id"],project_id); actual=hours=0.0; today=date.today().isoformat(); today_planned=today_actual=today_hours=0.0
                for r in mp:
                    try: d=json.loads(r[0] or "{}")
                    except Exception: d={}
                    try: am=float(d.get("actual_men",0) or 0)
                    except Exception: am=0.0
                    try: hrs=float(d.get("hours",0) or 0)
                    except Exception: hrs=0.0
                    actual+=am; hours+=am*hrs
                    if str(d.get("date",""))==today: today_actual+=am; today_hours+=am*hrs
                programme=None
                plans=c.execute("SELECT * FROM plans WHERE company_id=? AND project_id=? ORDER BY updated_at DESC,created_at DESC",(u["company_id"],project_id)).fetchall()
                active=next((x for x in plans if x["status"]=="Active"),plans[0] if plans else None)
                if active and has_permission(c,u,"Projects","View"):
                    tasks=c.execute("SELECT * FROM plan_tasks WHERE plan_id=? AND project_id=?",(active["id"],project_id)).fetchall()
                    total=len(tasks); progress=round(sum(float(t["percent_complete"] or 0) for t in tasks)/total,1) if total else 0.0
                    finish=max((t["finish_date"] for t in tasks),default=None); baseline=max((t["baseline_finish"] for t in tasks if t["baseline_finish"]),default=None)
                    variance=(date.fromisoformat(finish)-date.fromisoformat(baseline)).days if finish and baseline else None
                    overdue_prog=[t for t in tasks if t["finish_date"]<today and float(t["percent_complete"] or 0)<100]
                    programme={"id":active["id"],"name":active["name"],"status":active["status"],"progress":progress,"activities":total,"finish":finish,"baseline_finish":baseline,"finish_variance_days":variance,"overdue_activities":len(overdue_prog)}
                    today_tasks=[t for t in tasks if t["start_date"]<=today<=t["finish_date"] and float(t["percent_complete"] or 0)<100]
                    today_planned=sum(float(t["planned_men"] or 0) for t in today_tasks)
                self.j(200,{"project":dict(project),"modules":[{"module":m,"count":counts[m]} for m in visible],"kpis":{"records":sum(counts.values()),"pending_approvals":pending,"documents":docs,"actual_men":round(actual,1),"planned_men":round(planned,1),"man_hours":round(hours,1),"today_actual_men":round(today_actual,1),"today_planned_men":round(today_planned,1),"today_man_hours":round(today_hours,1)},"programme":programme,"attention":attention[:12],"recent":recent}); return
            if self.command=="GET" and path=="/api/management":
                # Live "start of day" management/control view. Every figure is derived from persisted
                # project data as of a chosen reporting date (defaults to today), not from TODAY() at
                # read time — so the same request reproduces what the board should have shown on any date.
                from urllib.parse import parse_qs as _pqs
                qs=_pqs(urlparse(self.path).query); as_of_raw=(qs.get("as_of") or [None])[0]
                try:
                    as_of=date.fromisoformat(as_of_raw).isoformat() if as_of_raw else date.today().isoformat()
                except Exception:
                    self.j(400,{"error":"as_of must be YYYY-MM-DD"}); return
                if u["role"]=="Company Administrator":
                    projects=c.execute("SELECT id,name FROM projects WHERE company_id=? ORDER BY name",(u["company_id"],)).fetchall()
                else:
                    projects=c.execute("SELECT p.id,p.name FROM projects p JOIN project_access pa ON pa.project_id=p.id WHERE p.company_id=? AND pa.user_id=? ORDER BY p.name",(u["company_id"],u["id"])).fetchall()
                today=as_of; summary=[]; issues=[]; programme=[]
                status_closed={"closed","complete","completed","approved","resolved","done"}
                for pr in projects:
                    pid=pr["id"]
                    recs=c.execute("SELECT id,module,title,data_json,updated_at FROM module_records WHERE company_id=? AND project_id=?",(u["company_id"],pid)).fetchall()
                    counts={}; open_counts={};
                    for r in recs:
                        counts[r["module"]]=counts.get(r["module"],0)+1
                        try: d=json.loads(r["data_json"] or "{}")
                        except Exception: d={}
                        status=str(d.get("status","")).strip().lower()
                        if status and status not in status_closed: open_counts[r["module"]]=open_counts.get(r["module"],0)+1
                        due=d.get("due_date") or d.get("target_date") or d.get("required_by")
                        if due and str(due) < today and status not in status_closed:
                            issues.append({"project_id":pid,"project_name":pr["name"],"module":r["module"],"record_id":r["id"],"title":r["title"],"due_date":str(due),"status":status or "Open","kind":"Overdue control item"})
                    pending=c.execute("SELECT COUNT(*) FROM workflows WHERE company_id=? AND project_id=? AND status='Pending'",(u["company_id"],pid)).fetchone()[0]
                    # Cumulative manpower (lifetime) alongside today's actual requirement — the recap
                    # flagged that a start-of-day tool needs "what's needed today", not just a running total.
                    mp=c.execute("SELECT data_json FROM module_records WHERE company_id=? AND project_id=? AND module='Manpower'",(u["company_id"],pid)).fetchall(); planned=project_manloader(c,u["company_id"],pid); actual=hours=0.0
                    today_planned=today_actual=today_hours=0.0
                    for r in mp:
                        try:d=json.loads(r[0] or "{}")
                        except Exception:d={}
                        try:am=float(d.get("actual_men",0) or 0)
                        except Exception:am=0.0
                        try:hrs=float(d.get("hours",0) or 0)
                        except Exception:hrs=0.0
                        actual+=am; hours+=am*hrs
                        if str(d.get("date",""))==today:
                            today_actual+=am; today_hours+=am*hrs
                    plans=c.execute("SELECT * FROM plans WHERE company_id=? AND project_id=? ORDER BY updated_at DESC",(u["company_id"],pid)).fetchall()
                    active=next((x for x in plans if x["status"]=="Active"),plans[0] if plans else None)
                    pinfo=None
                    if active:
                        tasks=c.execute("SELECT * FROM plan_tasks WHERE plan_id=? AND project_id=?",(active["id"],pid)).fetchall(); total=len(tasks); prog=round(sum(float(t["percent_complete"] or 0) for t in tasks)/total,1) if total else 0.0
                        finish=max((t["finish_date"] for t in tasks),default=None); bfinish=max((t["baseline_finish"] for t in tasks if t["baseline_finish"]),default=None)
                        variance=None
                        if finish and bfinish: variance=(date.fromisoformat(finish)-date.fromisoformat(bfinish)).days
                        overdue=[t for t in tasks if t["percent_complete"]<100 and t["finish_date"]<today]
                        due_today=[t for t in tasks if t["percent_complete"]<100 and t["finish_date"]==today]
                        in_progress_today=[t for t in tasks if t["start_date"]<=today<=t["finish_date"]]
                        planned_men_required_today=sum(float(t["planned_men"] or 0) for t in in_progress_today)
                        pinfo={"id":active["id"],"name":active["name"],"status":active["status"],"progress":prog,"finish":finish,"baseline_finish":bfinish,"finish_variance_days":variance,"overdue_activities":len(overdue),"due_today":len(due_today),"in_progress_today":len(in_progress_today),"activity_count":total,
                               "planned_men_required_today":planned_men_required_today,
                               "activities_today":[{"id":t["id"],"name":t["name"],"finish_date":t["finish_date"],"percent_complete":t["percent_complete"],"planned_men":t["planned_men"]} for t in in_progress_today]}
                        today_planned=planned_men_required_today
                        programme.append({"project_id":pid,"project_name":pr["name"],**pinfo})
                    if not active:
                        today_planned=0.0
                        for r in mp:
                            try:
                                d=json.loads(r[0] or "{}")
                                if str(d.get("date",""))==today: today_planned+=float(d.get("planned_men",0) or 0)
                            except Exception: pass
                    summary.append({"project_id":pid,"project_name":pr["name"],"records":sum(counts.values()),"counts":counts,"open":open_counts,"pending_approvals":pending,
                                     "manpower":{"planned_men":planned,"actual_men":actual,"variance_men":actual-planned,"man_hours":hours},
                                     "manpower_today":{"planned_men":today_planned,"actual_men":today_actual,"variance_men":today_actual-today_planned,"man_hours":today_hours},
                                     "programme":pinfo})
                # Pending approvals are actionable controls too.
                for w in c.execute("SELECT w.id,w.project_id,w.module,w.record_id,w.created_at,p.name project_name,mr.title FROM workflows w JOIN projects p ON p.id=w.project_id LEFT JOIN module_records mr ON mr.id=w.record_id WHERE w.company_id=? AND w.status='Pending' ORDER BY w.created_at DESC",(u["company_id"],)).fetchall():
                    if any(x["project_id"]==w["project_id"] for x in projects): issues.append({"project_id":w["project_id"],"project_name":w["project_name"],"module":w["module"],"record_id":w["record_id"],"title":w["title"] or "Approval request","due_date":None,"status":"Pending","kind":"Approval required"})
                totals={"projects":len(projects),"records":sum(x["records"] for x in summary),"pending_approvals":sum(x["pending_approvals"] for x in summary),
                        "overdue_items":sum(1 for x in issues if x["kind"]=="Overdue control item"),
                        "programme_overdue":sum(x["programme"]["overdue_activities"] for x in summary if x["programme"]),
                        "programme_due_today":sum(x["programme"]["due_today"] for x in summary if x["programme"]),
                        "planned_men_required_today":sum(x["programme"]["planned_men_required_today"] for x in summary if x["programme"]),
                        "planned_men":sum(x["manpower"]["planned_men"] for x in summary),"actual_men":sum(x["manpower"]["actual_men"] for x in summary),"man_hours":sum(x["manpower"]["man_hours"] for x in summary),
                        "planned_men_today":sum(x["manpower_today"]["planned_men"] for x in summary),"actual_men_today":sum(x["manpower_today"]["actual_men"] for x in summary)}
                self.j(200,{"as_of":today,"totals":totals,"projects":summary,"programme":programme,"issues":issues[:100]});return
            if path.startswith("/api/plan-export/") and self.command=="GET":
                self.handle_programme_export(c,u,path.rsplit("/",1)[1]); return
            if path=="/api/plan-import/roundtrip" and self.command=="POST":
                qs=_parse_qs(urlparse(self.path).query); plan_id=(qs.get("plan_id") or [""])[0]; commit=(qs.get("commit") or ["0"])[0]=="1"
                self.handle_programme_roundtrip(c,u,plan_id,commit); return
            if path=="/api/plan-import/templates" and self.command=="GET":
                plan_id=(_parse_qs(urlparse(self.path).query).get("plan_id") or [""])[0]; plan=c.execute("SELECT * FROM plans WHERE id=? AND company_id=?",(plan_id,u["company_id"])).fetchone()
                if not plan or not can_access_project(c,u,plan["project_id"]): self.j(404,{"error":"Programme not found"}); return
                if not has_permission(c,u,"Projects","Edit"): self.j(403,{"error":"Project edit permission required"}); return
                self.xlsx_response(make_programme_xlsx_template(plan["name"]),"Construction_Control_Programme_Import_Template.xlsx"); return
            if path=="/api/plan-import" and self.command=="POST":
                plan_id=(_parse_qs(urlparse(self.path).query).get("plan_id") or [""])[0]; self.handle_programme_import(c,u,plan_id); return
            if path=="/api/bulk-import/templates" and self.command=="GET":
                module=(_parse_qs(urlparse(self.path).query).get("module") or [""])[0]
                if not valid_module(module) or not bulk_spec(module): self.j(400,{"error":"No bulk template is available for this module"}); return
                if not has_permission(c,u,module,"Create"): self.j(403,{"error":"Create permission required"}); return
                self.xlsx_response(make_xlsx_template(module),f"Construction_Control_{module.replace(' ','_')}_Import_Template.xlsx"); return
            if path=="/api/bulk-import" and self.command=="POST":
                q=_parse_qs(urlparse(self.path).query); self.handle_bulk_import(c,u,(q.get("project_id") or [""])[0],(q.get("module") or [""])[0]); return
            if path=="/api/bulk-import/history" and self.command=="GET":
                q=_parse_qs(urlparse(self.path).query); pid=(q.get("project_id") or [""])[0]
                if not can_access_project(c,u,pid): self.j(403,{"error":"Project access required"}); return
                rows=c.execute("SELECT id,module,filename,rows_read,rows_imported,rows_rejected,errors_json,created_at FROM bulk_imports WHERE company_id=? AND project_id=? ORDER BY created_at DESC LIMIT 50",(u["company_id"],pid)).fetchall()
                self.j(200,{"imports":[dict(r) for r in rows]}); return
            if self.command=="GET" and path=="/api/entitlements":
                co=c.execute("SELECT * FROM companies WHERE id=?",(u["company_id"],)).fetchone();self.j(200,{"tier":co["tier"],**TIERS[co["tier"]]});return
            if path=="/api/settings" and self.command=="GET":
                if not require_admin(self,u): return
                c.execute("INSERT OR IGNORE INTO company_settings(company_id) VALUES(?)",(u["company_id"],)); c.commit()
                row=c.execute("SELECT * FROM company_settings WHERE company_id=?",(u["company_id"],)).fetchone()
                self.j(200,{"settings":dict(row)}); return
            if path=="/api/settings" and self.command=="PUT":
                if not require_admin(self,u): return
                b=self.body(); allowed={"accent_color":"#2563eb","sidebar_color":"#0f172a","background_color":"#f1f5f9","card_color":"#ffffff","text_color":"#0f172a","density":"comfortable","dashboard_default":"management"}
                vals={k:str(b.get(k,allowed[k])).strip() for k in allowed}
                import re
                for k in ("accent_color","sidebar_color","background_color","card_color","text_color"):
                    if not re.fullmatch(r"#[0-9a-fA-F]{6}",vals[k]): self.j(400,{"error":f"{k} must be a 6-digit hex colour"}); return
                if vals["density"] not in ("compact","comfortable","spacious"): self.j(400,{"error":"Invalid density"}); return
                if vals["dashboard_default"] not in ("management","home","daily"): self.j(400,{"error":"Invalid dashboard default"}); return
                c.execute("INSERT OR IGNORE INTO company_settings(company_id) VALUES(?)",(u["company_id"],))
                c.execute("UPDATE company_settings SET accent_color=?,sidebar_color=?,background_color=?,card_color=?,text_color=?,density=?,dashboard_default=?,updated_at=CURRENT_TIMESTAMP WHERE company_id=?",(vals["accent_color"],vals["sidebar_color"],vals["background_color"],vals["card_color"],vals["text_color"],vals["density"],vals["dashboard_default"],u["company_id"]))
                audit_row(c,u,"SETTINGS_EDIT",u["company_id"]); c.commit()
                row=c.execute("SELECT * FROM company_settings WHERE company_id=?",(u["company_id"],)).fetchone()
                self.j(200,{"ok":True,"settings":dict(row)}); return
            if path=="/api/staff/restore-standard" and self.command=="POST":
                if not has_permission(c,u,"Projects","Edit"): self.j(403,{"error":"Project edit permission required"}); return
                standard_people=[("STD-CM","Michael Byrne","Construction Manager"),("STD-PM","Paul Kelly","Project Manager"),("STD-SM","Sean Murphy","Site Manager"),("STD-FM","Liam Doyle","Foreman"),("STD-CH","John Ryan","Charge Hand"),("STD-E1","Mark Walsh","Electrician"),("STD-E2","David Nolan","Electrician"),("STD-4Y","Tom O'Brien","4th Year"),("STD-3Y","Chris Moore","3rd Year"),("STD-2Y","Jack Flynn","2nd Year"),("STD-1Y","Adam Hayes","1st Year"),("STD-GO","Ben Collins","GO"),("STD-MECH","Eoin Power","Construction Manager"),("STD-FIRE","Gary Fox","Construction Manager"),("STD-IT","Luke Burke","Electrician"),("STD-BMS","Ross Casey","Electrician")]
                for ref,name,position in standard_people: c.execute("INSERT OR IGNORE INTO staff(id,company_id,staff_ref,name,position,active) VALUES(?,?,?,?,?,1)",(u["company_id"]+"-"+ref,u["company_id"],ref,name,position))
                c.commit(); audit_row(c,u,"STAFF_STANDARD_RESTORE",u["company_id"]); c.commit(); self.j(200,{"ok":True}); return
            if path=="/api/company" and self.command=="PUT":
                if not require_admin(self,u):return
                b=self.body();name=str(b.get("name","")).strip();country=str(b.get("country","")).strip();logo_url=str(b.get("logo_url","")).strip()
                if not name or not country:self.j(400,{"error":"Company name and country are required"});return
                if len(logo_url)>2048:self.j(400,{"error":"Logo URL is too long"});return
                c.execute("UPDATE companies SET name=?,country=?,logo_url=? WHERE id=?",(name,country,logo_url,u["company_id"]));audit_row(c,u,"COMPANY_EDIT",u["company_id"]);c.commit();self.j(200,{"ok":True});return
            if self.command=="GET" and path=="/api/projects":
                if u["role"]=="Company Administrator": rows=c.execute("SELECT p.*,o.name level_name FROM projects p LEFT JOIN org_levels o ON o.id=p.level_id WHERE p.company_id=? ORDER BY p.name",(u["company_id"],)).fetchall()
                else: rows=c.execute("SELECT p.*,o.name level_name FROM projects p JOIN project_access pa ON pa.project_id=p.id LEFT JOIN org_levels o ON o.id=p.level_id WHERE p.company_id=? AND pa.user_id=? ORDER BY p.name",(u["company_id"],u["id"])).fetchall()
                self.j(200,{"projects":[dict(x) for x in rows]});return
            if path=="/api/daily-site-issue" and self.command=="POST":
                if not has_permission(c,u,"Daily Control","Create") and not has_permission(c,u,"Daily Control","Edit"):
                    self.j(403,{"error":"Daily Control create/edit permission required"}); return
                b=self.body(); pid=str(b.get("project_id","")).strip(); day=str(b.get("date",date.today().isoformat())).strip()
                module=str(b.get("module","")).strip(); title=str(b.get("title","")).strip(); desc=str(b.get("description","")).strip()
                if not pid or not can_access_project(c,u,pid): self.j(403,{"error":"Project access required"}); return
                if module not in ("RFIs","Risks","Actions","Snags"): self.j(400,{"error":"Issue type must be RFIs, Risks, Actions or Snags"}); return
                if not title or not desc: self.j(400,{"error":"Title and description are required"}); return
                data={"date":day,"description":desc,"status":"Open","notes":str(b.get("notes","")).strip()}
                if module=="RFIs": data.update({"subject":desc,"rfi_no":str(b.get("ref","")).strip(),"due_date":str(b.get("due_date","")).strip()})
                elif module=="Risks": data.update({"risk_id":str(b.get("ref","")).strip(),"likelihood":str(b.get("likelihood","")).strip(),"impact":str(b.get("impact","")).strip(),"mitigation":str(b.get("mitigation","")).strip()})
                elif module=="Actions": data.update({"action_id":str(b.get("ref","")).strip(),"priority":str(b.get("priority","Medium")).strip(),"owner":str(b.get("owner","")).strip(),"due_date":str(b.get("due_date","")).strip()})
                else: data.update({"snag_id":str(b.get("ref","")).strip(),"location":str(b.get("location","")).strip(),"owner":str(b.get("owner","")).strip(),"due_date":str(b.get("due_date","")).strip()})
                rid=secrets.token_hex(8)
                c.execute("INSERT INTO module_records(id,company_id,project_id,module,title,data_json,created_by) VALUES(?,?,?,?,?,?,?)",(rid,u["company_id"],pid,module,title,json.dumps(data),u["id"]))
                audit_row(c,u,"DAILY_SITE_ISSUE_CREATE",rid); c.commit(); self.j(201,{"ok":True,"id":rid,"module":module}); return
            if path=="/api/daily-site-control" and self.command=="GET":
                q=_parse_qs(urlparse(self.path).query); pid=(q.get("project_id") or [""])[0]; day=(q.get("date") or [date.today().isoformat()])[0]
                if not pid or not can_access_project(c,u,pid): self.j(403,{"error":"Project access required"}); return
                try: date.fromisoformat(day)
                except Exception: self.j(400,{"error":"Date must be YYYY-MM-DD"}); return
                project=c.execute("SELECT * FROM projects WHERE id=? AND company_id=?",(pid,u["company_id"])).fetchone()
                staff=assignment_rows_for_day(c,u["company_id"],pid,day)
                attendance,actual_men,man_hours=daily_attendance_summary(c,u,pid,day)
                att_by={r["staff_id"]:dict(r) for r in attendance}
                tasks=c.execute("SELECT pt.*,pl.name plan_name FROM plan_tasks pt JOIN plans pl ON pl.id=pt.plan_id WHERE pt.project_id=? AND pl.company_id=? ORDER BY pt.start_date,pt.id",(pid,u["company_id"])).fetchall()
                task_items=[]
                for r in tasks:
                    st=task_status(r["percent_complete"],r["task_status"]); item={"id":r["id"],"name":r["name"],"start_date":r["start_date"],"finish_date":r["finish_date"],"planned_men":float(r["planned_men"] or 0),"percent_complete":int(r["percent_complete"] or 0),"status":st,"held_up_reason":r["held_up_reason"],"status_notes":r["status_notes"]}
                    if r["start_date"]==day: item["bucket"]="starting"
                    elif r["start_date"]<day and st=="Starting": item["bucket"]="late_start"
                    elif r["start_date"]<=day<=r["finish_date"] and st!="Finished": item["bucket"]="active"
                    else: item["bucket"]="other"
                    task_items.append(item)
                dc=c.execute("SELECT * FROM module_records WHERE company_id=? AND project_id=? AND module='Daily Control' AND json_extract(data_json,'$.date')=? ORDER BY created_at DESC LIMIT 1",(u["company_id"],pid,day)).fetchone()
                dc_data=json.loads(dc["data_json"] or "{}") if dc else {}
                controls={}
                for mod in ("RFIs","Risks","Actions","Snags"):
                    controls[mod]=c.execute("SELECT COUNT(*) FROM module_records WHERE company_id=? AND project_id=? AND module=? AND lower(json_extract(data_json,'$.status')) NOT IN ('closed','complete','completed')",(u["company_id"],pid,mod)).fetchone()[0]
                staff_out=[]
                for x in staff:
                    item=dict(x); item["id"]=item["member_id"]; staff_out.append(item)
                self.j(200,{"project":dict(project),"date":day,"staff":staff_out,"attendance":[dict(x) for x in attendance],"actual_men":actual_men,"man_hours":man_hours,"planned_men":task_planned_men_for_day(c,u,pid,day),"tasks":task_items,"controls":controls,"daily":dc_data}); return
            if path=="/api/daily-site-control" and self.command=="POST":
                if not has_permission(c,u,"Daily Control","Edit") and not has_permission(c,u,"Daily Control","Create"):
                    self.j(403,{"error":"Daily Control create/edit permission required"}); return
                b=self.body(); pid=str(b.get("project_id","")).strip(); day=str(b.get("date",date.today().isoformat())).strip()
                if not pid or not can_access_project(c,u,pid): self.j(403,{"error":"Project access required"}); return
                try: date.fromisoformat(day)
                except Exception: self.j(400,{"error":"Date must be YYYY-MM-DD"}); return
                attendance=b.get("attendance",[]); task_updates=b.get("tasks",[])
                if not isinstance(attendance,list) or not isinstance(task_updates,list): self.j(400,{"error":"attendance and tasks must be lists"}); return
                staff_ids={r["id"] for r in c.execute("SELECT id FROM staff WHERE company_id=?",(u["company_id"],)).fetchall()}
                validated_att=[]
                for item in attendance:
                    sid=str(item.get("staff_id","")).strip()
                    if sid not in staff_ids: self.j(400,{"error":"Invalid staff member in attendance"}); return
                    onsite=1 if item.get("onsite",False) else 0
                    try: hours=float(item.get("hours",0) or 0)
                    except Exception: self.j(400,{"error":"Hours must be numeric"}); return
                    if hours<0 or hours>24: self.j(400,{"error":"Hours must be between 0 and 24"}); return
                    if not onsite: hours=0
                    validated_att.append((sid,onsite,hours,str(item.get("notes","")).strip()))
                validated_tasks=[]
                for item in task_updates:
                    tid=str(item.get("id","")).strip(); tr=c.execute("SELECT id,task_status FROM plan_tasks WHERE id=? AND project_id=?",(tid,pid)).fetchone()
                    if not tr: self.j(400,{"error":"Invalid task in daily update"}); return
                    try: pct=int(item.get("percent_complete"))
                    except Exception: self.j(400,{"error":"Task progress must be an integer"}); return
                    if pct<0 or pct>100: self.j(400,{"error":"Task progress must be 0-100"}); return
                    raw_status=item.get("status",None)
                    if raw_status is None or str(raw_status).strip()=="":
                        status=task_status(pct)
                    else:
                        status=LEGACY_TASK_STATUS_MAP.get(str(raw_status).strip(),str(raw_status).strip())
                    if status not in TASK_STATUS_VALUES: self.j(400,{"error":"Task status must be Starting, Ongoing, Held Up or Finished"}); return
                    reason=str(item.get("held_up_reason","")).strip()
                    if status=="Held Up" and reason not in HELD_UP_REASONS: self.j(400,{"error":"A valid held-up reason is required"}); return
                    if status!="Held Up": reason=""
                    validated_tasks.append((task_progress(status,pct),status,reason,str(item.get("status_notes","")).strip(),tid))
                # Atomic daily save: attendance + task progress + one daily control record.
                for sid,onsite,hours,notes in validated_att:
                    old=c.execute("SELECT id FROM daily_attendance WHERE company_id=? AND project_id=? AND staff_id=? AND work_date=?",(u["company_id"],pid,sid,day)).fetchone()
                    if old: c.execute("UPDATE daily_attendance SET onsite=?,hours=?,notes=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(onsite,hours,notes,old["id"]))
                    else:
                        aid=secrets.token_hex(8); c.execute("INSERT INTO daily_attendance(id,company_id,project_id,staff_id,work_date,onsite,hours,notes,created_by) VALUES(?,?,?,?,?,?,?,?,?)",(aid,u["company_id"],pid,sid,day,onsite,hours,notes,u["id"]))
                for pct,status,reason,status_notes,tid in validated_tasks:
                    actual_start=day if pct>0 else None
                    actual_finish=day if pct==100 else None
                    c.execute("UPDATE plan_tasks SET percent_complete=?,task_status=?,held_up_reason=?,status_notes=?,actual_start=COALESCE(actual_start,?),actual_finish=? WHERE id=? AND project_id=?",(pct,status,reason,status_notes,actual_start,actual_finish,tid,pid))
                title=f"Daily Site Control - {day}"
                data={"date":day,"status":str(b.get("status","Complete")).strip() or "Complete","planned_activities":str(b.get("planned_activities","")).strip(),"completed_activities":str(b.get("completed_activities","")).strip(),"delays":str(b.get("delays","")).strip(),"constraints":str(b.get("constraints","")).strip(),"notes":str(b.get("notes","")).strip(),"safety_check":str(b.get("safety_check","Not recorded")).strip(),"deliveries":str(b.get("deliveries","")).strip()}
                old=c.execute("SELECT id FROM module_records WHERE company_id=? AND project_id=? AND module='Daily Control' AND json_extract(data_json,'$.date')=? ORDER BY created_at DESC LIMIT 1",(u["company_id"],pid,day)).fetchone()
                if old: c.execute("UPDATE module_records SET title=?,data_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(title,json.dumps(data),old["id"])); rid=old["id"]
                else: rid=secrets.token_hex(8); c.execute("INSERT INTO module_records(id,company_id,project_id,module,title,data_json,created_by) VALUES(?,?,?,?,?,?,?)",(rid,u["company_id"],pid,"Daily Control",title,json.dumps(data),u["id"]))
                audit_row(c,u,"DAILY_SITE_CONTROL_SAVE",rid); c.commit(); self.j(200,{"ok":True,"record_id":rid}); return
            if path=="/api/staff" and self.command=="GET":
                if not has_permission(c,u,"Projects","View"): self.j(403,{"error":"Project view permission required"}); return
                q=_parse_qs(urlparse(self.path).query); active=q.get("active",["1"])[0]
                if active in ("0","1"):
                    rows=c.execute("SELECT * FROM staff WHERE company_id=? AND active=? ORDER BY name",(u["company_id"],int(active))).fetchall()
                else:
                    rows=c.execute("SELECT * FROM staff WHERE company_id=? ORDER BY active DESC,name",(u["company_id"],)).fetchall()
                self.j(200,{"staff":[dict(x) for x in rows]}); return
            if path=="/api/staff" and self.command=="POST":
                if not has_permission(c,u,"Projects","Edit"): self.j(403,{"error":"Project edit permission required"}); return
                b=self.body(); name=str(b.get("name","")).strip(); position=str(b.get("position","")).strip(); ref=str(b.get("staff_ref","")).strip()
                if not name or not position: self.j(400,{"error":"Name and position are required"}); return
                if not ref: ref="STAFF-"+secrets.token_hex(4).upper()
                if c.execute("SELECT 1 FROM staff WHERE company_id=? AND staff_ref=?",(u["company_id"],ref)).fetchone(): self.j(409,{"error":"Staff reference already exists"}); return
                sid=secrets.token_hex(8); active=1 if b.get("active",True) else 0
                labour_level=str(b.get("labour_level",position)).strip(); badge_type=str(b.get("badge_type","")).strip(); source_group=str(b.get("source_group","")).strip(); display_color=str(b.get("display_color","")).strip()
                c.execute("INSERT INTO staff(id,company_id,staff_ref,name,position,active,labour_level,badge_type,source_group,display_color) VALUES(?,?,?,?,?,?,?,?,?,?)",(sid,u["company_id"],ref,name,position,active,labour_level,badge_type,source_group,display_color)); audit_row(c,u,"STAFF_CREATE",sid); c.commit(); self.j(201,{"id":sid}); return
            if path=="/api/project-assignments" and self.command=="GET":
                q=_parse_qs(urlparse(self.path).query); pid=(q.get("project_id") or [""])[0]; sid=(q.get("staff_id") or [""])[0]; aid=(q.get("assignment_id") or [""])[0]
                if pid and not can_access_project(c,u,pid): self.j(403,{"error":"Project access required"}); return
                rows=c.execute("""SELECT a.*,s.name,s.staff_ref,s.position,p.name project_name FROM project_staff_assignments a
                    JOIN staff s ON s.id=a.staff_id JOIN projects p ON p.id=a.project_id WHERE a.company_id=?
                    AND (?='' OR a.project_id=?) AND (?='' OR a.staff_id=?) AND (?='' OR a.id=?) ORDER BY a.start_date DESC,s.name""",(u["company_id"],pid,pid,sid,sid,aid,aid)).fetchall()
                self.j(200,{"assignments":[dict(x) for x in rows]}); return
            if path=="/api/project-assignments" and self.command=="POST":
                if not has_permission(c,u,"Projects","Edit"): self.j(403,{"error":"Project edit permission required"}); return
                b=self.body(); pid=str(b.get("project_id","")).strip(); sid=str(b.get("staff_id","")).strip(); role=str(b.get("assignment_role","")).strip(); start=str(b.get("start_date","")).strip(); finish=str(b.get("finish_date","")).strip() or None
                if not pid or not can_access_project(c,u,pid) or not staff_record(c,u,sid): self.j(400,{"error":"Valid project and staff member are required"}); return
                if not role or role not in ROLE_VALUES: self.j(400,{"error":"Use an established labour role"}); return
                try: date.fromisoformat(start); (date.fromisoformat(finish) if finish else None)
                except Exception: self.j(400,{"error":"Assignment dates must be YYYY-MM-DD"}); return
                if finish and finish<start: self.j(400,{"error":"Assignment finish cannot be before start"}); return
                aid=secrets.token_hex(8); c.execute("INSERT INTO project_staff_assignments(id,company_id,project_id,staff_id,assignment_role,assignment_status,start_date,finish_date,notes,created_by) VALUES(?,?,?,?,?,?,?,?,?,?)",(aid,u["company_id"],pid,sid,role,"Active",start,finish,str(b.get("notes","")).strip(),u["id"])); audit_row(c,u,"PROJECT_STAFF_ASSIGN",aid); c.commit(); self.j(201,{"id":aid}); return
            if path.startswith("/api/project-assignments/") and self.command=="PUT":
                if not has_permission(c,u,"Projects","Edit"): self.j(403,{"error":"Project edit permission required"}); return
                aid=path.rsplit("/",1)[1]; row=c.execute("SELECT * FROM project_staff_assignments WHERE id=? AND company_id=?",(aid,u["company_id"])).fetchone()
                if not row or not can_access_project(c,u,row["project_id"]): self.j(404,{"error":"Assignment not found"}); return
                b=self.body(); status=str(b.get("assignment_status",row["assignment_status"])).strip(); finish=str(b.get("finish_date",row["finish_date"] or "")).strip() or None; start=str(b.get("start_date",row["start_date"])).strip(); role=str(b.get("assignment_role",row["assignment_role"])).strip()
                if status not in ("Active","Finished","Held"): self.j(400,{"error":"Invalid assignment status"}); return
                if role not in ROLE_VALUES: self.j(400,{"error":"Use an established labour role"}); return
                try: date.fromisoformat(start); (date.fromisoformat(finish) if finish else None)
                except Exception: self.j(400,{"error":"Assignment dates must be YYYY-MM-DD"}); return
                if finish and finish<start: self.j(400,{"error":"Assignment finish cannot be before start"}); return
                c.execute("UPDATE project_staff_assignments SET assignment_role=?,start_date=?,assignment_status=?,finish_date=?,notes=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(role,start,status,finish,str(b.get("notes",row["notes"])).strip(),aid)); audit_row(c,u,"PROJECT_STAFF_ASSIGN_UPDATE",aid); c.commit(); self.j(200,{"ok":True}); return
            if path.startswith("/api/staff/") and "/training" in path:
                parts=path.strip('/').split('/')
                sid=parts[2] if len(parts)>2 else ""
                st=staff_record(c,u,sid)
                if not st: self.j(404,{"error":"Staff member not found"}); return
                if not has_permission(c,u,"Projects","View"): self.j(403,{"error":"Project view permission required"}); return
                if len(parts)==4 and parts[3]=="training" and self.command=="GET":
                    rows=c.execute("SELECT * FROM staff_training_records WHERE company_id=? AND staff_id=? ORDER BY COALESCE(expiry_date,'9999-12-31'),completed_date DESC,training_name",(u["company_id"],sid)).fetchall()
                    self.j(200,{"training":[dict(x) for x in rows]}); return
                if len(parts)>=5 and parts[3]=="training":
                    tid=parts[4]
                    tr=c.execute("SELECT * FROM staff_training_records WHERE id=? AND staff_id=? AND company_id=?",(tid,sid,u["company_id"])).fetchone()
                    if not tr: self.j(404,{"error":"Training record not found"}); return
                    if len(parts)==6 and parts[5]=="documents" and self.command=="GET":
                        rows=c.execute("SELECT id,staff_id,training_id,filename,mime_type,size_bytes,uploaded_by,created_at FROM staff_training_documents WHERE company_id=? AND staff_id=? AND training_id=? ORDER BY id DESC",(u["company_id"],sid,tid)).fetchall()
                        self.j(200,{"documents":[dict(x) for x in rows]}); return
                    if len(parts)==6 and parts[5]=="documents" and self.command=="POST":
                        if not has_permission(c,u,"Projects","Edit"): self.j(403,{"error":"Project edit permission required"}); return
                        b=self.body(); filename=str(b.get("filename","")).strip(); mime=str(b.get("mime_type") or "application/octet-stream"); raw=b.get("content_base64","")
                        if not filename or not raw: self.j(400,{"error":"Filename and content are required"}); return
                        if len(filename)>180 or "/" in filename or "\\" in filename or "\x00" in filename: self.j(400,{"error":"Invalid filename"}); return
                        try: data=base64.b64decode(raw,validate=True)
                        except Exception: self.j(400,{"error":"Invalid base64 content"}); return
                        if len(data)>10*1024*1024: self.j(413,{"error":"Document is larger than 10 MB"}); return
                        did=secrets.token_hex(8); stored=did+".bin"
                        UPLOADS.mkdir(parents=True,exist_ok=True); (UPLOADS/stored).write_bytes(data)
                        c.execute("INSERT INTO staff_training_documents(id,company_id,staff_id,training_id,filename,stored_name,mime_type,size_bytes,uploaded_by) VALUES(?,?,?,?,?,?,?,?,?)",(did,u["company_id"],sid,tid,filename,stored,mime,len(data),u["id"]))
                        audit_row(c,u,"STAFF_TRAINING_DOCUMENT_UPLOAD",did); c.commit(); self.j(201,{"id":did}); return
                if len(parts)==4 and parts[3]=="training" and self.command=="POST":
                    if not has_permission(c,u,"Projects","Edit"): self.j(403,{"error":"Project edit permission required"}); return
                    b=self.body(); name=str(b.get("training_name","")).strip(); provider=str(b.get("provider","")).strip(); completed=str(b.get("completed_date","")).strip(); expiry=str(b.get("expiry_date","")).strip() or None; cert=str(b.get("certificate_ref","")).strip(); status=str(b.get("status","Completed")).strip() or "Completed"; notes=str(b.get("notes","")).strip()
                    if not name or not completed: self.j(400,{"error":"Training name and completed date are required"}); return
                    try: date.fromisoformat(completed); (date.fromisoformat(expiry) if expiry else None)
                    except Exception: self.j(400,{"error":"Training dates must be YYYY-MM-DD"}); return
                    if expiry and expiry<completed: self.j(400,{"error":"Expiry date cannot be before completed date"}); return
                    if status not in ("Completed","Current","Expired","Pending"): self.j(400,{"error":"Invalid training status"}); return
                    tid=secrets.token_hex(8)
                    c.execute("INSERT INTO staff_training_records(id,company_id,staff_id,training_name,provider,completed_date,expiry_date,certificate_ref,status,notes,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(tid,u["company_id"],sid,name,provider,completed,expiry,cert,status,notes,u["id"]))
                    audit_row(c,u,"STAFF_TRAINING_CREATE",tid); c.commit(); self.j(201,{"id":tid}); return
                if len(parts)==5 and parts[3]=="training" and self.command in ("PUT","DELETE"):
                    if not has_permission(c,u,"Projects","Edit"): self.j(403,{"error":"Project edit permission required"}); return
                    tid=parts[4]; row=c.execute("SELECT * FROM staff_training_records WHERE id=? AND staff_id=? AND company_id=?",(tid,sid,u["company_id"])).fetchone()
                    if not row: self.j(404,{"error":"Training record not found"}); return
                    if self.command=="DELETE":
                        c.execute("DELETE FROM staff_training_records WHERE id=?",(tid,)); audit_row(c,u,"STAFF_TRAINING_DELETE",tid); c.commit(); self.j(200,{"ok":True}); return
                    b=self.body(); name=str(b.get("training_name",row["training_name"])).strip(); provider=str(b.get("provider",row["provider"])).strip(); completed=str(b.get("completed_date",row["completed_date"])).strip(); expiry=str(b.get("expiry_date",row["expiry_date"] or "")).strip() or None; cert=str(b.get("certificate_ref",row["certificate_ref"])).strip(); status=str(b.get("status",row["status"])).strip() or "Completed"; notes=str(b.get("notes",row["notes"])).strip()
                    if not name or not completed: self.j(400,{"error":"Training name and completed date are required"}); return
                    try: date.fromisoformat(completed); (date.fromisoformat(expiry) if expiry else None)
                    except Exception: self.j(400,{"error":"Training dates must be YYYY-MM-DD"}); return
                    if expiry and expiry<completed: self.j(400,{"error":"Expiry date cannot be before completed date"}); return
                    if status not in ("Completed","Current","Expired","Pending"): self.j(400,{"error":"Invalid training status"}); return
                    c.execute("UPDATE staff_training_records SET training_name=?,provider=?,completed_date=?,expiry_date=?,certificate_ref=?,status=?,notes=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(name,provider,completed,expiry,cert,status,notes,tid)); audit_row(c,u,"STAFF_TRAINING_EDIT",tid); c.commit(); self.j(200,{"ok":True}); return
            if path.startswith("/api/staff-training-documents/"):
                did=path.rsplit("/",1)[1]; row=c.execute("SELECT * FROM staff_training_documents WHERE id=? AND company_id=?",(did,u["company_id"])).fetchone()
                if not row: self.j(404,{"error":"Training document not found"}); return
                if self.command=="GET":
                    if not has_permission(c,u,"Projects","View"): self.j(403,{"error":"Project view permission required"}); return
                    data=(UPLOADS/row["stored_name"]).read_bytes()
                    self.send_response(200); self.send_header("Content-Type",row["mime_type"]); self.send_header("Content-Length",str(len(data))); self.send_header("Content-Disposition",f'attachment; filename="{row["filename"].replace(chr(34),"")}"'); self.end_headers(); self.wfile.write(data); return
                if self.command=="DELETE":
                    if not has_permission(c,u,"Projects","Edit"): self.j(403,{"error":"Project edit permission required"}); return
                    try: (UPLOADS/row["stored_name"]).unlink()
                    except FileNotFoundError: pass
                    c.execute("DELETE FROM staff_training_documents WHERE id=? AND company_id=?",(did,u["company_id"])); audit_row(c,u,"STAFF_TRAINING_DOCUMENT_DELETE",did); c.commit(); self.j(200,{"ok":True}); return
            if path.startswith("/api/staff/"):
                parts=path.strip('/').split('/'); sid=parts[2] if len(parts)>2 else ""; st=staff_record(c,u,sid)
                if not st: self.j(404,{"error":"Staff member not found"}); return
                if len(parts)==3 and self.command=="PUT":
                    if not has_permission(c,u,"Projects","Edit"): self.j(403,{"error":"Project edit permission required"}); return
                    b=self.body(); name=str(b.get("name",st["name"])).strip(); position=str(b.get("position",st["position"])).strip(); ref=str(b.get("staff_ref",st["staff_ref"])).strip(); active=1 if b.get("active",bool(st["active"])) else 0
                    if not name or not position or not ref: self.j(400,{"error":"Name, position and staff reference are required"}); return
                    if c.execute("SELECT 1 FROM staff WHERE company_id=? AND staff_ref=? AND id<>?",(u["company_id"],ref,sid)).fetchone(): self.j(409,{"error":"Staff reference already exists"}); return
                    labour_level=str(b.get("labour_level",st["labour_level"] or position)).strip(); badge_type=str(b.get("badge_type",st["badge_type"] or "")).strip(); source_group=str(b.get("source_group",st["source_group"] or "")).strip(); display_color=str(b.get("display_color",st["display_color"] or "")).strip()
                    c.execute("UPDATE staff SET staff_ref=?,name=?,position=?,active=?,labour_level=?,badge_type=?,source_group=?,display_color=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND company_id=?",(ref,name,position,active,labour_level,badge_type,source_group,display_color,sid,u["company_id"])); audit_row(c,u,"STAFF_EDIT",sid); c.commit(); self.j(200,{"ok":True}); return
                if len(parts)==3 and self.command=="DELETE":
                    if not has_permission(c,u,"Projects","Edit"): self.j(403,{"error":"Project edit permission required"}); return
                    # Keep history intact: deactivate rather than physically delete a staff member used on tasks.
                    c.execute("UPDATE staff SET active=0,updated_at=CURRENT_TIMESTAMP WHERE id=? AND company_id=?",(sid,u["company_id"])); audit_row(c,u,"STAFF_DEACTIVATE",sid); c.commit(); self.j(200,{"ok":True}); return
            if path.startswith("/api/tasks/"):
                parts=path.strip('/').split('/'); tid=parts[2] if len(parts)>2 else ""
                task=task_record(c,u,tid)
                if task and len(parts)>=4 and parts[3] in ("staff","history","work"):
                    if not can_access_project(c,u,task["project_id"]): self.j(404,{"error":"Task not found"}); return
                    if parts[3]=="staff" and self.command=="GET":
                        rows=c.execute("SELECT a.*,s.staff_ref,s.name,s.position FROM task_staff_assignments a JOIN staff s ON s.id=a.staff_id WHERE a.task_id=? AND a.company_id=? ORDER BY a.unassigned_at IS NULL DESC,a.assigned_at",(tid,u["company_id"])).fetchall()
                        self.j(200,{"assignments":[dict(x) for x in rows]}); return
                    if parts[3]=="staff" and self.command=="POST":
                        if not has_permission(c,u,"Projects","Edit"): self.j(403,{"error":"Project edit permission required"}); return
                        b=self.body(); sid=str(b.get("staff_id","")).strip(); st=staff_record(c,u,sid)
                        if not st or not st["active"]: self.j(400,{"error":"Active staff member is required"}); return
                        if c.execute("SELECT 1 FROM task_staff_assignments WHERE task_id=? AND staff_id=? AND unassigned_at IS NULL",(tid,sid)).fetchone(): self.j(409,{"error":"Staff member is already assigned to this task"}); return
                        aid=secrets.token_hex(8); role=str(b.get("role_on_task",st["position"])).strip() or st["position"]
                        c.execute("INSERT INTO task_staff_assignments(id,company_id,project_id,plan_id,task_id,staff_id,role_on_task,notes,assigned_by) VALUES(?,?,?,?,?,?,?,?,?)",(aid,u["company_id"],task["project_id"],task["plan_id"],tid,sid,role,str(b.get("notes","")).strip(),u["id"])); audit_row(c,u,"TASK_STAFF_ASSIGN",aid); c.commit(); self.j(201,{"id":aid}); return
                    if parts[3]=="staff" and len(parts)==5 and self.command=="DELETE":
                        if not has_permission(c,u,"Projects","Edit"): self.j(403,{"error":"Project edit permission required"}); return
                        aid=parts[4]; row=c.execute("SELECT id FROM task_staff_assignments WHERE id=? AND task_id=? AND company_id=? AND unassigned_at IS NULL",(aid,tid,u["company_id"])).fetchone()
                        if not row: self.j(404,{"error":"Assignment not found"}); return
                        c.execute("UPDATE task_staff_assignments SET unassigned_at=CURRENT_TIMESTAMP WHERE id=?",(aid,)); audit_row(c,u,"TASK_STAFF_UNASSIGN",aid); c.commit(); self.j(200,{"ok":True}); return
                    if parts[3]=="work" and self.command=="GET":
                        rows=c.execute("SELECT w.*,s.staff_ref,s.name,s.position FROM task_work_logs w JOIN staff s ON s.id=w.staff_id WHERE w.task_id=? AND w.company_id=? ORDER BY w.work_date DESC,w.created_at DESC",(tid,u["company_id"])).fetchall()
                        self.j(200,{"work_logs":[dict(x) for x in rows]}); return
                    if parts[3]=="work" and self.command=="POST":
                        if not has_permission(c,u,"Projects","Edit"): self.j(403,{"error":"Project edit permission required"}); return
                        b=self.body(); sid=str(b.get("staff_id","")).strip(); st=staff_record(c,u,sid); wd=str(b.get("work_date","")).strip()
                        if not st: self.j(400,{"error":"Valid staff member is required"}); return
                        try: hours=float(b.get("hours",0) or 0)
                        except Exception: self.j(400,{"error":"Hours must be numeric"}); return
                        try: date.fromisoformat(wd)
                        except Exception: self.j(400,{"error":"Valid work date is required"}); return
                        if hours<0 or hours>24: self.j(400,{"error":"Hours must be between 0 and 24"}); return
                        wid=secrets.token_hex(8); c.execute("INSERT INTO task_work_logs(id,company_id,project_id,task_id,staff_id,work_date,hours,note,created_by) VALUES(?,?,?,?,?,?,?,?,?)",(wid,u["company_id"],task["project_id"],tid,sid,wd,hours,str(b.get("note","")).strip(),u["id"])); audit_row(c,u,"TASK_WORK_LOG",wid); c.commit(); self.j(201,{"id":wid}); return
                    if parts[3]=="history" and self.command=="GET":
                        assigns=c.execute("SELECT a.*,s.staff_ref,s.name,s.position FROM task_staff_assignments a JOIN staff s ON s.id=a.staff_id WHERE a.task_id=? AND a.company_id=? ORDER BY a.assigned_at",(tid,u["company_id"])).fetchall()
                        logs=c.execute("SELECT w.*,s.staff_ref,s.name,s.position FROM task_work_logs w JOIN staff s ON s.id=w.staff_id WHERE w.task_id=? AND w.company_id=? ORDER BY w.work_date,w.created_at",(tid,u["company_id"])).fetchall()
                        self.j(200,{"task":dict(task),"assignments":[dict(x) for x in assigns],"work_logs":[dict(x) for x in logs]}); return
                # Fall through to the existing task GET/PUT handler for /api/tasks/{id}.
            if path=="/api/projects" and self.command=="POST":
                if not require_admin(self,u):return
                b=self.body();name=str(b.get("name","")).strip();co=c.execute("SELECT tier FROM companies WHERE id=?",(u["company_id"],)).fetchone();limit=TIERS[co["tier"]]["projects"]
                if not name:self.j(400,{"error":"Project name is required"});return
                if c.execute("SELECT COUNT(*) FROM projects WHERE company_id=?",(u["company_id"],)).fetchone()[0]>=limit:self.j(403,{"error":"Project limit reached for subscription tier"});return
                pid=secrets.token_hex(6);lid=b.get("level_id") or None
                try: manloader=float(b.get("manloader",0) or 0)
                except Exception: self.j(400,{"error":"Manloader must be numeric"}); return
                if manloader<0: self.j(400,{"error":"Manloader cannot be negative"}); return
                if lid and not c.execute("SELECT 1 FROM org_levels WHERE id=? AND company_id=?",(lid,u["company_id"])).fetchone():self.j(400,{"error":"Invalid organisation level"});return
                start=str(b.get("start_date","")).strip() or None; finish=str(b.get("finish_date","")).strip() or None
                for d in (start,finish):
                    if d:
                        try: date.fromisoformat(d)
                        except Exception: self.j(400,{"error":"Project dates must be YYYY-MM-DD"});return
                if start and finish and finish<start:self.j(400,{"error":"Project finish cannot be before start"});return
                client=str(b.get("client_name","")).strip();addr=str(b.get("site_address","")).strip();scope=str(b.get("scope_ref","")).strip()
                c.execute("INSERT INTO projects(id,company_id,name,level_id,manloader,start_date,finish_date,client_name,site_address,scope_ref) VALUES(?,?,?,?,?,?,?,?,?,?)",(pid,u["company_id"],name,lid,manloader,start,finish,client,addr,scope));audit_row(c,u,"PROJECT_CREATE",pid);c.commit();self.j(201,{"id":pid});return
            if path.startswith("/api/projects/"):
                pid=path.rsplit("/",1)[1]
                if self.command=="GET":
                    if not can_access_project(c,u,pid):self.j(403,{"error":"Project access denied"});return
                    p=c.execute("SELECT p.*,o.name level_name FROM projects p LEFT JOIN org_levels o ON o.id=p.level_id WHERE p.id=? AND p.company_id=?",(pid,u["company_id"])).fetchone();self.j(200,{"project":dict(p)});return
                if self.command=="PUT":
                    if not require_admin(self,u):return
                    if not c.execute("SELECT 1 FROM projects WHERE id=? AND company_id=?",(pid,u["company_id"])).fetchone():self.j(404,{"error":"Project not found"});return
                    b=self.body();name=str(b.get("name","")).strip();lid=b.get("level_id") or None
                    try: manloader=float(b.get("manloader",0) or 0)
                    except Exception: self.j(400,{"error":"Manloader must be numeric"}); return
                    if manloader<0: self.j(400,{"error":"Manloader cannot be negative"}); return
                    if not name:self.j(400,{"error":"Project name is required"});return
                    if lid and not c.execute("SELECT 1 FROM org_levels WHERE id=? AND company_id=?",(lid,u["company_id"])).fetchone():self.j(400,{"error":"Invalid organisation level"});return
                    start=str(b.get("start_date","")).strip() or None; finish=str(b.get("finish_date","")).strip() or None
                    for d in (start,finish):
                        if d:
                            try: date.fromisoformat(d)
                            except Exception: self.j(400,{"error":"Project dates must be YYYY-MM-DD"});return
                    if start and finish and finish<start:self.j(400,{"error":"Project finish cannot be before start"});return
                    client=str(b.get("client_name","")).strip();addr=str(b.get("site_address","")).strip();scope=str(b.get("scope_ref","")).strip()
                    c.execute("UPDATE projects SET name=?,level_id=?,manloader=?,start_date=?,finish_date=?,client_name=?,site_address=?,scope_ref=? WHERE id=? AND company_id=?",(name,lid,manloader,start,finish,client,addr,scope,pid,u["company_id"]));audit_row(c,u,"PROJECT_EDIT",pid);c.commit();self.j(200,{"ok":True});return
            if self.command=="GET" and path=="/api/org":
                rows=c.execute("SELECT o.*,p.name parent_name FROM org_levels o LEFT JOIN org_levels p ON p.id=o.parent_id WHERE o.company_id=? ORDER BY o.name",(u["company_id"],)).fetchall();self.j(200,{"levels":[dict(x) for x in rows]});return
            if path=="/api/org" and self.command=="POST":
                if not require_admin(self,u):return
                b=self.body();name=str(b.get("name","")).strip();parent=b.get("parent_id") or None
                if not name:self.j(400,{"error":"Level name is required"});return
                if parent and not c.execute("SELECT 1 FROM org_levels WHERE id=? AND company_id=?",(parent,u["company_id"])).fetchone():self.j(400,{"error":"Invalid parent level"});return
                lid=secrets.token_hex(5);c.execute("INSERT INTO org_levels(id,company_id,name,parent_id) VALUES(?,?,?,?)",(lid,u["company_id"],name,parent));audit_row(c,u,"ORG_LEVEL_CREATE",lid);c.commit();self.j(201,{"id":lid});return
            if path.startswith("/api/org/") and self.command=="PUT":
                if not require_admin(self,u):return
                lid=path.rsplit("/",1)[1];b=self.body();name=str(b.get("name","")).strip();parent=b.get("parent_id") or None
                if not name:self.j(400,{"error":"Level name is required"});return
                if parent==lid:self.j(400,{"error":"A level cannot be its own parent"});return
                if parent and not c.execute("SELECT 1 FROM org_levels WHERE id=? AND company_id=?",(parent,u["company_id"])).fetchone():self.j(400,{"error":"Invalid parent level"});return
                if not c.execute("SELECT 1 FROM org_levels WHERE id=? AND company_id=?",(lid,u["company_id"])).fetchone():self.j(404,{"error":"Level not found"});return
                c.execute("UPDATE org_levels SET name=?,parent_id=? WHERE id=? AND company_id=?",(name,parent,lid,u["company_id"]));audit_row(c,u,"ORG_LEVEL_EDIT",lid);c.commit();self.j(200,{"ok":True});return
            if self.command=="GET" and path=="/api/users":
                if not require_admin(self,u):return
                rows=c.execute("SELECT id,name,email,active,role,created_at FROM users WHERE company_id=? ORDER BY name",(u["company_id"],)).fetchall();self.j(200,{"users":[dict(x) for x in rows]});return
            if path=="/api/users" and self.command=="POST":
                if not require_admin(self,u):return
                b=self.body();name=str(b.get("name","")).strip();email=str(b.get("email","")).strip().lower();pw=str(b.get("password",""));role=str(b.get("role","")).strip();active=1 if b.get("active",True) else 0
                co=c.execute("SELECT tier FROM companies WHERE id=?",(u["company_id"],)).fetchone();
                if c.execute("SELECT COUNT(*) FROM users WHERE company_id=?",(u["company_id"],)).fetchone()[0]>=TIERS[co["tier"]]["users"]:self.j(403,{"error":"User limit reached for subscription tier"});return
                if not name or not email or not pw or not role:self.j(400,{"error":"Name, email, password and role are required"});return
                if len(pw)<10:self.j(400,{"error":"Temporary password must be at least 10 characters"});return
                if not role_id(c,u["company_id"],role):self.j(400,{"error":"Invalid role"});return
                if c.execute("SELECT 1 FROM users WHERE lower(email)=lower(?)",(email,)).fetchone():self.j(409,{"error":"Email already exists"});return
                uid=secrets.token_hex(6);c.execute("INSERT INTO users(id,company_id,name,email,password_hash,active,role) VALUES(?,?,?,?,?,?,?)",(uid,u["company_id"],name,email,pw_hash(pw),active,role));audit_row(c,u,"USER_CREATE",uid);c.commit();self.j(201,{"id":uid});return
            if path.startswith("/api/users/"):
                parts=path.strip('/').split('/');uid=parts[2]
                target=c.execute("SELECT * FROM users WHERE id=? AND company_id=?",(uid,u["company_id"])).fetchone()
                if not target:self.j(404,{"error":"User not found"});return
                if not require_admin(self,u):return
                if len(parts)==3 and self.command=="PUT":
                    b=self.body();name=str(b.get("name","")).strip();role=str(b.get("role","")).strip();active=1 if b.get("active",True) else 0
                    if not name or not role:self.j(400,{"error":"Name and role are required"});return
                    if not role_id(c,u["company_id"],role):self.j(400,{"error":"Invalid role"});return
                    if uid==u["id"] and not active:self.j(400,{"error":"You cannot disable your own account"});return
                    c.execute("UPDATE users SET name=?,role=?,active=? WHERE id=?",(name,role,active,uid));audit_row(c,u,"USER_EDIT",uid);c.commit();self.j(200,{"ok":True});return
                if len(parts)==4 and parts[3]=="access":
                    if self.command=="GET":
                        rows=c.execute("SELECT project_id FROM project_access pa JOIN projects p ON p.id=pa.project_id WHERE pa.user_id=? AND p.company_id=?",(uid,u["company_id"])).fetchall();self.j(200,{"project_ids":[x[0] for x in rows]});return
                    if self.command=="PUT":
                        ids=self.body().get("project_ids",[]);valid={x[0] for x in c.execute("SELECT id FROM projects WHERE company_id=?",(u["company_id"],)).fetchall()}
                        if not isinstance(ids,list) or any(x not in valid for x in ids):self.j(400,{"error":"One or more projects are invalid"});return
                        c.execute("DELETE FROM project_access WHERE user_id=?",(uid,))
                        c.executemany("INSERT INTO project_access(user_id,project_id) VALUES(?,?)",[(uid,x) for x in ids]);audit_row(c,u,"PROJECT_ACCESS_EDIT",uid);c.commit();self.j(200,{"ok":True});return
            if self.command=="GET" and path=="/api/roles":
                if not require_admin(self,u):return
                rows=c.execute("SELECT r.*,pr.name parent_name,COUNT(p.module) permission_count FROM roles r LEFT JOIN roles pr ON pr.id=r.parent_role_id LEFT JOIN permissions p ON p.role_id=r.id WHERE r.company_id=? GROUP BY r.id ORDER BY r.access_level DESC,r.name",(u["company_id"],)).fetchall();self.j(200,{"roles":[dict(x) for x in rows],"ladder":[{"level":n,"name":name,"description":desc} for n,name,desc in ACCESS_LADDER]});return
            if path=="/api/roles" and self.command=="POST":
                if not require_admin(self,u):return
                b=self.body();name=str(b.get("name","")).strip()
                if not name:self.j(400,{"error":"Role name is required"});return
                if role_id(c,u["company_id"],name):self.j(409,{"error":"Role already exists"});return
                try: level=int(b.get("access_level",1))
                except Exception: level=1
                if level<1 or level>9:self.j(400,{"error":"Access level must be 1-9"});return
                parent_id=b.get("parent_role_id") or None
                if parent_id:
                    pr=c.execute("SELECT access_level FROM roles WHERE id=? AND company_id=?",(parent_id,u["company_id"])).fetchone()
                    if not pr or int(pr["access_level"])>=level:self.j(400,{"error":"Parent role must be lower in the access ladder"});return
                rid=secrets.token_hex(6);c.execute("INSERT INTO roles(id,company_id,name,access_level,parent_role_id) VALUES(?,?,?,?,?)",(rid,u["company_id"],name,level,parent_id))
                c.executemany("INSERT INTO permissions(role_id,module,action,allowed) VALUES(?,?,?,0)",[(rid,m,a) for m in MODULES for a in ACTIONS])
                # Ladder preset: higher levels receive all permissions of lower levels plus the next management layer.
                preset = {
                    1: [("Projects","View"),("Daily Control","View"),("Manpower","View"),("Reports","View")],
                    2: [(m,a) for m in ("Projects","Daily Control","Manpower","Snags") for a in ("View","Create","Edit")],
                    3: [(m,a) for m in ("Projects","Daily Control","Manpower","RFIs","Risks","Actions","Snags","Materials","Permits","RAMS") for a in ("View","Create","Edit","Export")],
                    4: [(m,a) for m in MODULES if m not in ("Users","Roles") for a in ("View","Create","Edit","Export")],
                    5: [(m,a) for m in MODULES for a in ("View","Create","Edit","Approve","Export")],
                    6: [(m,a) for m in MODULES for a in ("View","Create","Edit","Approve","Export")],
                    7: [(m,a) for m in MODULES for a in ("View","Create","Edit","Approve","Export")],
                    8: [(m,a) for m in MODULES for a in ("View","Create","Edit","Approve","Export")],
                    9: [(m,a) for m in MODULES for a in ACTIONS],
                }.get(level,[])
                for mod,act in preset:
                    c.execute("UPDATE permissions SET allowed=1 WHERE role_id=? AND module=? AND action=?",(rid,mod,act))
                audit_row(c,u,"ROLE_CREATE",rid);c.commit();self.j(201,{"id":rid,"access_level":level});return
            if path.startswith("/api/roles/"):
                parts=path.strip('/').split('/');rid=parts[2];r=c.execute("SELECT * FROM roles WHERE id=? AND company_id=?",(rid,u["company_id"])).fetchone()
                if not r:self.j(404,{"error":"Role not found"});return
                if not require_admin(self,u):return
                if len(parts)==3 and self.command=="GET":
                    ps=c.execute("SELECT module,action,allowed FROM permissions WHERE role_id=? ORDER BY module,action",(rid,)).fetchall();self.j(200,{"role":dict(r),"permissions":[dict(x) for x in ps]});return
                if len(parts)==4 and parts[3]=="permissions" and self.command=="PUT":
                    items=self.body().get("permissions",[])
                    if not isinstance(items,list):self.j(400,{"error":"Invalid permissions"});return
                    allowed={(m,a) for m in MODULES for a in ACTIONS}
                    for x in items:
                        if (x.get("module"),x.get("action")) not in allowed:self.j(400,{"error":"Invalid permission entry"});return
                    c.execute("DELETE FROM permissions WHERE role_id=?",(rid,));c.executemany("INSERT INTO permissions(role_id,module,action,allowed) VALUES(?,?,?,?)",[(rid,x["module"],x["action"],1 if x.get("allowed") else 0) for x in items]);audit_row(c,u,"ROLE_PERMISSIONS_EDIT",rid);c.commit();self.j(200,{"ok":True});return
            if path=="/api/notifications" and self.command=="GET":
                rows=c.execute("SELECT id,project_id,type,title,message,read_at,created_at FROM notifications WHERE company_id=? AND user_id=? ORDER BY id DESC LIMIT 100",(u["company_id"],u["id"])).fetchall()
                self.j(200,{"notifications":[dict(x) for x in rows]}); return
            if path.startswith("/api/notifications/") and self.command=="PUT":
                nid=path.rsplit("/",1)[1]
                if not c.execute("SELECT 1 FROM notifications WHERE id=? AND company_id=? AND user_id=?",(nid,u["company_id"],u["id"])).fetchone(): self.j(404,{"error":"Notification not found"}); return
                c.execute("UPDATE notifications SET read_at=CURRENT_TIMESTAMP WHERE id=? AND company_id=? AND user_id=?",(nid,u["company_id"],u["id"])); c.commit(); self.j(200,{"ok":True}); return
            if path=="/api/workflows" and self.command=="GET":
                from urllib.parse import parse_qs
                qs=parse_qs(urlparse(self.path).query); project_id=(qs.get("project_id") or [None])[0]
                if not project_id or not can_access_project(c,u,project_id): self.j(403,{"error":"Project access required"}); return
                rows=c.execute("SELECT w.*,rq.name requester_name,ap.name approver_name FROM workflows w LEFT JOIN users rq ON rq.id=w.requested_by LEFT JOIN users ap ON ap.id=w.approver_user_id WHERE w.company_id=? AND w.project_id=? ORDER BY w.id DESC",(u["company_id"],project_id)).fetchall()
                self.j(200,{"workflows":[dict(x) for x in rows]}); return
            if path=="/api/workflows" and self.command=="POST":
                if not has_permission(c,u,"Projects","Approve"): self.j(403,{"error":"Approval workflow permission required"}); return
                b=self.body(); project_id=str(b.get("project_id","")).strip(); module=str(b.get("module","")).strip(); record_id=str(b.get("record_id","")).strip(); approver=str(b.get("approver_user_id","")).strip()
                if not valid_workflow_target(c,u,project_id,module,record_id): self.j(400,{"error":"Invalid project, module or record"}); return
                target=c.execute("SELECT * FROM users WHERE id=? AND company_id=? AND active=1",(approver,u["company_id"])).fetchone()
                if not target or not can_access_project(c,target,project_id): self.j(400,{"error":"Approver must be an active user with project access"}); return
                if c.execute("SELECT 1 FROM workflows WHERE company_id=? AND record_id=? AND status='Pending'",(u["company_id"],record_id)).fetchone(): self.j(409,{"error":"A pending approval already exists for this record"}); return
                wid=secrets.token_hex(8); c.execute("INSERT INTO workflows(id,company_id,project_id,record_id,module,requested_by,approver_user_id) VALUES(?,?,?,?,?,?,?)",(wid,u["company_id"],project_id,record_id,module,u["id"],approver))
                c.execute("UPDATE module_records SET updated_at=CURRENT_TIMESTAMP WHERE id=? AND company_id=?",(record_id,u["company_id"]))
                notify(c,u["company_id"],approver,project_id,"Approval Requested","Approval required",f"{module} record {record_id} requires your approval.")
                audit_row(c,u,"APPROVAL_REQUEST",wid); c.commit(); self.j(201,{"id":wid}); return
            if path.startswith("/api/workflows/"):
                wid=path.rsplit("/",1)[1]; w=workflow_record(c,u,wid)
                if not w or not can_access_project(c,u,w["project_id"]): self.j(404,{"error":"Workflow not found"}); return
                if self.command=="PUT":
                    if w["status"]!="Pending": self.j(409,{"error":"Workflow is already decided"}); return
                    if u["id"]!=w["approver_user_id"] and u["role"]!="Company Administrator": self.j(403,{"error":"Only the assigned approver or administrator can decide"}); return
                    if not has_permission(c,u,w["module"],"Approve") and u["role"]!="Company Administrator": self.j(403,{"error":"Approve permission required"}); return
                    b=self.body(); decision=str(b.get("decision","")).strip().title(); note=str(b.get("note","")).strip()
                    if decision not in ("Approved","Rejected"): self.j(400,{"error":"Decision must be Approved or Rejected"}); return
                    c.execute("UPDATE workflows SET status=?,decision_note=?,decided_at=CURRENT_TIMESTAMP WHERE id=? AND company_id=?",(decision,note,wid,u["company_id"]))
                    notify(c,u["company_id"],w["requested_by"],w["project_id"],"Approval Decision",f"Approval {decision}",f"Your {w['module']} approval request was {decision.lower()}.")
                    audit_row(c,u,"APPROVAL_"+decision.upper(),wid); c.commit(); self.j(200,{"ok":True,"status":decision}); return
            if path=="/api/plans" and self.command=="GET":
                from urllib.parse import parse_qs
                qs=parse_qs(urlparse(self.path).query); pid=(qs.get("project_id") or [None])[0]
                if not pid or not can_access_project(c,u,pid): self.j(403,{"error":"Project access required"}); return
                if not has_permission(c,u,"Projects","View"): self.j(403,{"error":"Project view permission required"}); return
                rows=c.execute("SELECT * FROM plans WHERE company_id=? AND project_id=? ORDER BY created_at DESC",(u["company_id"],pid)).fetchall()
                self.j(200,{"plans":[dict(x) for x in rows]}); return
            if path=="/api/plans" and self.command=="POST":
                if not has_permission(c,u,"Projects","Create"): self.j(403,{"error":"Project create permission required"}); return
                b=self.body(); pid=str(b.get("project_id","")).strip(); name=str(b.get("name","")).strip()
                if not pid or not can_access_project(c,u,pid): self.j(403,{"error":"Project access required"}); return
                if not name: self.j(400,{"error":"Plan name is required"}); return
                plan_id=secrets.token_hex(8); c.execute("INSERT INTO plans(id,company_id,project_id,name,created_by) VALUES(?,?,?,?,?)",(plan_id,u["company_id"],pid,name,u["id"])); audit_row(c,u,"PLAN_CREATE",plan_id); c.commit(); self.j(201,{"id":plan_id}); return
            # Standalone Tasks view backed by programme activities. Tasks remain programme-linked so
            # status/progress changes made here are immediately reflected in Programme/Gantt and project KPIs.
            if path=="/api/task-alerts" and self.command=="GET":
                # Live task notice board: only tasks belonging to projects the user can access.
                today=date.today().isoformat(); projects=c.execute("SELECT p.id,p.name FROM projects p WHERE p.company_id=? AND ( ? = 'Company Administrator' OR EXISTS (SELECT 1 FROM project_access pa WHERE pa.project_id=p.id AND pa.user_id=?)) ORDER BY p.name",(u["company_id"],u["role"],u["id"])).fetchall()
                today_rows=[]; overdue_rows=[]
                for pr in projects:
                    rows=c.execute("SELECT pt.*,pl.name plan_name FROM plan_tasks pt JOIN plans pl ON pl.id=pt.plan_id WHERE pl.company_id=? AND pt.project_id=? ORDER BY pt.start_date,pt.id",(u["company_id"],pr["id"])).fetchall()
                    for r in rows:
                        status=task_status(r["percent_complete"],r["task_status"]); legacy_status=LEGACY_TASK_STATUS_REVERSE.get(status,status); item={"id":r["id"],"project_id":pr["id"],"project_name":pr["name"],"plan_id":r["plan_id"],"plan_name":r["plan_name"],"name":r["name"],"start_date":r["start_date"],"finish_date":r["finish_date"],"status":legacy_status,"control_status":status,"percent_complete":float(r["percent_complete"] or 0)}
                        if str(r["start_date"])==today and status=="Starting": today_rows.append(item)
                        if str(r["start_date"])<today and status=="Starting": overdue_rows.append(item)
                self.j(200,{"today":today,"today_tasks":today_rows,"overdue_tasks":overdue_rows,"today_count":len(today_rows),"overdue_count":len(overdue_rows)}); return

            if path=="/api/tasks" and self.command=="GET":
                from urllib.parse import parse_qs as _pqs
                q=_pqs(urlparse(self.path).query); pid=(q.get("project_id") or [""])[0]; plan_id=(q.get("plan_id") or [""])[0]
                if not pid or not can_access_project(c,u,pid): self.j(403,{"error":"Project access required"}); return
                if not has_permission(c,u,"Projects","View"): self.j(403,{"error":"Project view permission required"}); return
                plan=c.execute("SELECT * FROM plans WHERE id=? AND company_id=? AND project_id=?",(plan_id,u["company_id"],pid)).fetchone()
                if not plan: self.j(404,{"error":"Programme not found"}); return
                rows=c.execute("SELECT * FROM plan_tasks WHERE plan_id=? AND project_id=? ORDER BY start_date,id",(plan_id,pid)).fetchall()
                out=[]
                for r in rows:
                    start=date.fromisoformat(r["start_date"]); finish=date.fromisoformat(r["finish_date"])
                    control_status=task_status(r["percent_complete"],r["task_status"])
                    legacy_status=LEGACY_TASK_STATUS_REVERSE.get(control_status,control_status)
                    out.append({**dict(r),"status":legacy_status,"control_status":control_status,
                                "duration_working_days":working_days(c,u["company_id"],pid,plan_id,start,finish)})
                total=len(out); progress=round(sum(float(x["percent_complete"] or 0) for x in out)/total,1) if total else 0.0
                counts={s:sum(1 for x in out if x["status"]==s) for s in ("Not Started","Started","Finished")}
                control_counts={s:sum(1 for x in out if x["control_status"]==s) for s in TASK_STATUS_VALUES}
                self.j(200,{"project_id":pid,"plan":dict(plan),"tasks":out,"overall_progress":progress,"counts":counts,"control_counts":control_counts}); return

            if path=="/api/tasks" and self.command=="POST":
                if not has_permission(c,u,"Projects","Edit"): self.j(403,{"error":"Project edit permission required"}); return
                b=self.body(); pid=str(b.get("project_id","")).strip(); plan_id=str(b.get("plan_id","")).strip()
                if not pid or not can_access_project(c,u,pid): self.j(403,{"error":"Project access required"}); return
                plan=c.execute("SELECT * FROM plans WHERE id=? AND company_id=? AND project_id=?",(plan_id,u["company_id"],pid)).fetchone()
                if not plan: self.j(404,{"error":"Programme not found"}); return
                name=str(b.get("name",b.get("task",""))).strip(); start_s=str(b.get("start_date","")).strip()
                try: start=date.fromisoformat(start_s)
                except Exception: self.j(400,{"error":"Valid start date is required"}); return
                try: dur=int(b.get("duration_working_days",b.get("duration",1)))
                except Exception: dur=0
                if not name or dur<1 or dur>10000: self.j(400,{"error":"Task and a positive duration are required"}); return
                finish=add_plan_workdays(c,u["company_id"],pid,plan_id,start,dur-1)
                status_raw=str(b.get("status","Starting")).strip()
                status=LEGACY_TASK_STATUS_MAP.get(status_raw,status_raw)
                if status not in TASK_STATUS_VALUES: self.j(400,{"error":"Status must be Starting, Ongoing, Held Up or Finished"}); return
                try: pct=task_progress(status,b.get("percent_complete",0))
                except Exception: pct=0
                try: men=float(b.get("planned_men",0) or 0)
                except Exception: self.j(400,{"error":"Planned men must be numeric"}); return
                if men<0: self.j(400,{"error":"Planned men cannot be negative"}); return
                tid=secrets.token_hex(8)
                activity_id=str(b.get("task_id") or "").strip() or None
                if activity_id and c.execute("SELECT 1 FROM plan_tasks WHERE plan_id=? AND activity_id=?",(plan_id,activity_id)).fetchone(): self.j(400,{"error":"Task ID already exists in this programme"}); return
                actual_start=start.isoformat() if status in ("Ongoing","Held Up","Finished") else None
                actual_finish=finish.isoformat() if status=="Finished" else None
                c.execute("""INSERT INTO plan_tasks(id,plan_id,project_id,name,start_date,finish_date,percent_complete,planned_men,notes,activity_id,actual_start,actual_finish,task_status)
                             VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",(tid,plan_id,pid,name,start.isoformat(),finish.isoformat(),pct,men,str(b.get("notes","")).strip(),activity_id,actual_start,actual_finish,status))
                audit_row(c,u,"TASK_CREATE",tid); c.commit(); self.j(201,{"id":tid,"status":status,"finish_date":finish.isoformat()}); return

            if path.startswith("/api/tasks/") and self.command=="PUT":
                if not has_permission(c,u,"Projects","Edit"): self.j(403,{"error":"Project edit permission required"}); return
                tid=path.rsplit("/",1)[1]; b=self.body()
                supplied_pid=str(b.get("project_id","")).strip()
                if supplied_pid:
                    task=c.execute("""SELECT pt.*,p.name plan_name FROM plan_tasks pt JOIN plans p ON p.id=pt.plan_id
                                      WHERE pt.id=? AND pt.project_id=? AND p.company_id=?""",(tid,supplied_pid,u["company_id"])).fetchone()
                else:
                    task=c.execute("""SELECT pt.*,p.name plan_name FROM plan_tasks pt JOIN plans p ON p.id=pt.plan_id
                                      WHERE pt.id=? AND p.company_id=?""",(tid,u["company_id"])).fetchone()
                if not task or not can_access_project(c,u,task["project_id"]): self.j(404,{"error":"Task not found"}); return
                status_raw=str(b.get("status",task_status(task["percent_complete"],task["task_status"]))).strip()
                status=LEGACY_TASK_STATUS_MAP.get(status_raw,status_raw)
                if status not in TASK_STATUS_VALUES: self.j(400,{"error":"Status must be Starting, Ongoing, Held Up or Finished"}); return
                pct=task_progress(status,b.get("percent_complete",task["percent_complete"]))
                actual_start=b.get("actual_start",task["actual_start"]) or None
                actual_finish=b.get("actual_finish",task["actual_finish"]) or None
                if status in ("Ongoing","Held Up","Finished") and not actual_start: actual_start=task["start_date"]
                if status=="Finished" and not actual_finish: actual_finish=task["finish_date"]
                if status=="Starting": actual_start=None; actual_finish=None; pct=0
                if status=="Finished": pct=100
                reason=str(b.get("held_up_reason",task["held_up_reason"] or "")).strip() if status=="Held Up" else ""
                if status=="Held Up" and reason not in HELD_UP_REASONS: self.j(400,{"error":"A valid held-up reason is required"}); return
                status_notes=str(b.get("status_notes",task["status_notes"] or "")).strip()
                c.execute("UPDATE plan_tasks SET percent_complete=?,task_status=?,held_up_reason=?,status_notes=?,actual_start=?,actual_finish=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND project_id=?",(pct,status,reason,status_notes,actual_start,actual_finish,tid,task["project_id"]))
                audit_row(c,u,"TASK_STATUS_UPDATE",tid); c.commit(); self.j(200,{"ok":True,"status":status,"percent_complete":pct}); return

            if path=="/api/task-import/templates" and self.command=="GET":
                from urllib.parse import parse_qs as _pqs
                plan_id=(_pqs(urlparse(self.path).query).get("plan_id") or [""])[0]
                plan=c.execute("SELECT * FROM plans WHERE id=? AND company_id=?",(plan_id,u["company_id"])).fetchone()
                if not plan or not can_access_project(c,u,plan["project_id"]): self.j(404,{"error":"Programme not found"}); return
                if not has_permission(c,u,"Projects","Edit"): self.j(403,{"error":"Project edit permission required"}); return
                self.xlsx_response(make_task_xlsx_template(plan["name"]),"Construction_Control_Task_Import_Template.xlsx"); return

            if path=="/api/task-import" and self.command=="POST":
                from urllib.parse import parse_qs as _pqs
                plan_id=(_pqs(urlparse(self.path).query).get("plan_id") or [""])[0]
                plan=c.execute("SELECT * FROM plans WHERE id=? AND company_id=?",(plan_id,u["company_id"])).fetchone()
                if not plan or not can_access_project(c,u,plan["project_id"]): self.j(404,{"error":"Programme not found"}); return
                if not has_permission(c,u,"Projects","Edit"): self.j(403,{"error":"Project edit permission required"}); return
                try: filename,raw=self.multipart_file(); rows=self._task_import_rows(raw)
                except Exception as e: self.j(400,{"error":str(e)}); return
                if not rows: self.j(400,{"error":"Workbook contains no task rows"}); return
                headers=[str(x).strip() for x in rows[0]]
                if headers!=TASK_IMPORT_HEADERS: self.j(400,{"error":"Invalid task template columns","expected_columns":TASK_IMPORT_HEADERS,"received_columns":headers}); return
                items=[]; ids=set(); errors=[]
                for rn,row in enumerate(rows[1:],2):
                    if not any(str(v).strip() for v in row): continue
                    row=(row+[""]*len(headers))[:len(headers)]
                    task_id,name,start_s,dur_s,status,pct_s,men_s,notes=[str(v).strip() for v in row]
                    if task_id:
                        if task_id in ids: errors.append(f"Row {rn}: duplicate Task ID"); continue
                        ids.add(task_id)
                    if not name: errors.append(f"Row {rn}: Task is required"); continue
                    try: start=date.fromisoformat(start_s)
                    except Exception: errors.append(f"Row {rn}: Start Date must be YYYY-MM-DD"); continue
                    try: dur=int(float(dur_s))
                    except Exception: errors.append(f"Row {rn}: Duration must be a whole number"); continue
                    if dur<1: errors.append(f"Row {rn}: Duration must be at least 1 working day"); continue
                    st_raw=status or "Starting"
                    st=LEGACY_TASK_STATUS_MAP.get(st_raw,st_raw)
                    if st not in TASK_STATUS_VALUES: errors.append(f"Row {rn}: invalid Status"); continue
                    try: pct=int(float(pct_s or 0))
                    except Exception: errors.append(f"Row {rn}: % Complete must be numeric"); continue
                    if pct<0 or pct>100: errors.append(f"Row {rn}: % Complete must be 0-100"); continue
                    if st=="Finished" and pct not in (0,100): errors.append(f"Row {rn}: Finished tasks must have 100% complete"); continue
                    if st=="Starting" and pct not in (0,): errors.append(f"Row {rn}: Starting tasks must have 0% complete"); continue
                    if st in ("Ongoing","Held Up") and pct in (0,100): errors.append(f"Row {rn}: {st} tasks must have % Complete between 1 and 99"); continue
                    try: men=float(men_s or 0)
                    except Exception: errors.append(f"Row {rn}: Planned Men must be numeric"); continue
                    if men<0: errors.append(f"Row {rn}: Planned Men cannot be negative"); continue
                    pct=task_progress(st,pct); finish=add_plan_workdays(c,u["company_id"],plan["project_id"],plan_id,start,dur-1)
                    items.append((task_id or secrets.token_hex(6),name,start.isoformat(),finish.isoformat(),pct,men,notes,st))
                existing={r["activity_id"] for r in c.execute("SELECT activity_id FROM plan_tasks WHERE plan_id=? AND activity_id IS NOT NULL",(plan_id,)).fetchall()}
                for x in items:
                    if x[0] in existing: errors.append(f"Task ID already exists: {x[0]}")
                if errors: self.j(400,{"error":"Task import rejected","errors":errors[:50],"rows_rejected":len(errors)}); return
                try:
                    c.execute("BEGIN"); imported=0
                    for task_id,name,start,finish,pct,men,notes,st in items:
                        tid=secrets.token_hex(8); aid=task_id
                        ast=start if st in ("Ongoing","Held Up","Finished") else None; aft=finish if st=="Finished" else None
                        c.execute("""INSERT INTO plan_tasks(id,plan_id,project_id,name,start_date,finish_date,percent_complete,planned_men,notes,activity_id,actual_start,actual_finish,task_status)
                                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",(tid,plan_id,plan["project_id"],name,start,finish,pct,men,notes,aid,ast,aft,st)); imported+=1
                    audit_row(c,u,"TASK_BULK_IMPORT",plan_id); c.commit()
                except Exception:
                    c.rollback(); raise
                self.j(201,{"filename":filename,"rows_read":len(rows)-1,"rows_imported":imported,"rows_rejected":0}); return
            if path.startswith("/api/plans/"):
                parts=path.strip("/").split("/"); plan_id=parts[2] if len(parts)>2 else ""
                plan=c.execute("SELECT * FROM plans WHERE id=? AND company_id=?",(plan_id,u["company_id"])).fetchone()
                if not plan or not can_access_project(c,u,plan["project_id"]): self.j(404,{"error":"Plan not found"}); return
                if len(parts)==3 and self.command=="GET":
                    if not has_permission(c,u,"Projects","View"): self.j(403,{"error":"Project view permission required"}); return
                    tasks=c.execute("SELECT * FROM plan_tasks WHERE plan_id=? AND project_id=? ORDER BY start_date,id",(plan_id,plan["project_id"])).fetchall()
                    self.j(200,{"plan":dict(plan),"tasks":[dict(x) for x in tasks]}); return
                if len(parts)==4 and parts[3] in ("gantt","resources","lookahead","comparison","integration") and self.command=="GET":
                    if not has_permission(c,u,"Projects","View"): self.j(403,{"error":"Project view permission required"}); return
                    rows=[dict(x) for x in c.execute("SELECT * FROM plan_tasks WHERE plan_id=? AND project_id=? ORDER BY start_date,id",(plan_id,plan["project_id"])).fetchall()]
                    by={x["id"]:x for x in rows}
                    def d(v): return date.fromisoformat(v)
                    def workdays(a,b): return working_days(c,u["company_id"],plan["project_id"],plan_id,a,b)
                    def add_workdays(dt,n): return add_plan_workdays(c,u["company_id"],plan["project_id"],plan_id,dt,n)
                    # Validate dates, references, dependency types and lag.
                    valid_types={"FS","SS","FF","SF"}
                    for x in rows:
                        try:
                            sd,fd=d(x["start_date"]),d(x["finish_date"])
                            if fd<sd: raise ValueError
                        except Exception: self.j(409,{"error":"Invalid task date range"}); return
                        if x["predecessor_id"] and x["predecessor_id"] not in by: self.j(409,{"error":"Invalid predecessor reference"}); return
                        if x.get("dependency_type") not in valid_types: self.j(409,{"error":"Invalid dependency type"}); return
                        if int(x.get("lag_days") or 0)<0: self.j(409,{"error":"Lag days cannot be negative"}); return
                    # Detect dependency cycles.
                    visiting=set(); visited=set()
                    def dfs(tid):
                        if tid in visiting: return False
                        if tid in visited: return True
                        visiting.add(tid); pred=by[tid]["predecessor_id"]
                        if pred and not dfs(pred): return False
                        visiting.remove(tid); visited.add(tid); return True
                    if any(not dfs(x["id"]) for x in rows): self.j(409,{"error":"Dependency cycle detected"}); return
                    ordered=sorted(rows,key=lambda x:(x["start_date"],x["id"]))
                    es={}; ef={}
                    # Calendar scheduling with Monday-Friday working-day duration. Dependency types and lag are supported.
                    for x in ordered:
                        orig_s,orig_f=d(x["start_date"]),d(x["finish_date"]); duration=max(1,workdays(orig_s,orig_f))
                        start=orig_s; finish=add_workdays(start,duration-1)
                        pred=x["predecessor_id"]
                        if pred:
                            ps,pf=es[pred],ef[pred]; lag=int(x.get("lag_days") or 0); typ=x["dependency_type"]
                            if typ=="FS": start=max(start,add_workdays(pf,lag+1)); finish=add_workdays(start,duration-1)
                            elif typ=="SS": start=max(start,add_workdays(ps,lag)); finish=add_workdays(start,duration-1)
                            elif typ=="FF": finish=max(finish,add_workdays(pf,lag)); start=add_workdays(finish,-(duration-1))
                            elif typ=="SF": finish=max(finish,add_workdays(ps,lag)); start=add_workdays(finish,-(duration-1))
                        es[x["id"]]=start; ef[x["id"]]=finish
                    project_finish=max(ef.values()) if ef else None
                    lf={}; ls={}
                    for x in reversed(ordered):
                        children=[y for y in rows if y["predecessor_id"]==x["id"]]
                        duration=max(1,workdays(d(x["start_date"]),d(x["finish_date"])))
                        if not children: latest_finish=project_finish
                        else:
                            candidates=[]
                            for y in children:
                                typ=y["dependency_type"]; lag=int(y.get("lag_days") or 0)
                                if typ=="FS": candidates.append(add_workdays(ls[y["id"]],-(lag+1)))
                                elif typ=="SS": candidates.append(add_workdays(ls[y["id"]],-lag)+timedelta(days=duration-1))
                                elif typ=="FF": candidates.append(add_workdays(lf[y["id"]],-lag))
                                else: candidates.append(add_workdays(lf[y["id"]],-lag)+timedelta(days=duration-1))
                            latest_finish=min(candidates)
                        lf[x["id"]]=latest_finish; ls[x["id"]]=add_workdays(latest_finish,-(duration-1))
                    for x in rows:
                        x["scheduled_start"]=es[x["id"]].isoformat(); x["scheduled_finish"]=ef[x["id"]].isoformat(); x["critical"]=(ls[x["id"]]==es[x["id"]]); x["float_days"]=(ls[x["id"]]-es[x["id"]]).days
                        x["variance_days"]=(d(x["actual_finish"])-d(x["finish_date"])).days if x.get("actual_finish") else None
                    start=min((d(x["scheduled_start"]) for x in rows),default=None); finish=max((d(x["scheduled_finish"]) for x in rows),default=None)
                    if parts[3]=="resources":
                        daily={}; cur=start
                        while cur and finish and cur<=finish:
                            if cur.weekday()<5: daily[cur.isoformat()]=0
                            cur+=timedelta(days=1)
                        for x in rows:
                            cur=es[x["id"]]
                            while cur<=ef[x["id"]]:
                                if cur.weekday()<5: daily[cur.isoformat()]=daily.get(cur.isoformat(),0)+float(x["planned_men"] or 0)
                                cur+=timedelta(days=1)
                        self.j(200,{"plan":dict(plan),"daily":daily,"peak_men":max(daily.values(),default=0)}); return
                    if parts[3]=="lookahead":
                        q=urlparse(self.path).query; import urllib.parse as _up; params=_up.parse_qs(q); days=max(1,min(28,int(params.get("days",[14])[0])))
                        today=date.today(); horizon=today+timedelta(days=days-1)
                        upcoming=[x for x in rows if d(x["scheduled_finish"])>=today and d(x["scheduled_start"])<=horizon]
                        self.j(200,{"plan":dict(plan),"from":today.isoformat(),"to":horizon.isoformat(),"tasks":upcoming}); return
                    if parts[3] in ("comparison","integration"):
                        # Programme vs baseline and live construction-control integration.
                        import urllib.parse as _up
                        def parse_data(r):
                            try: return json.loads(r["data_json"] or "{}")
                            except Exception: return {}
                        baseline_tasks=[]
                        for x in rows:
                            bs=x.get("baseline_start"); bf=x.get("baseline_finish")
                            if bs and bf:
                                baseline_tasks.append({
                                    "id":x["id"], "name":x["name"], "baseline_start":bs, "baseline_finish":bf,
                                    "current_start":x["start_date"], "current_finish":x["finish_date"],
                                    "scheduled_start":x["scheduled_start"], "scheduled_finish":x["scheduled_finish"],
                                    "start_variance_days":(d(x["start_date"])-d(bs)).days,
                                    "finish_variance_days":(d(x["finish_date"])-d(bf)).days,
                                    "scheduled_finish_variance_days":(d(x["scheduled_finish"])-d(bf)).days,
                                    "percent_complete":x["percent_complete"], "actual_start":x.get("actual_start"), "actual_finish":x.get("actual_finish")
                                })
                        # Pull Daily Control and Manpower records only from this company/project.
                        dc=c.execute("SELECT * FROM module_records WHERE company_id=? AND project_id=? AND module='Daily Control'",(u["company_id"],plan["project_id"])).fetchall()
                        mp=c.execute("SELECT * FROM module_records WHERE company_id=? AND project_id=? AND module='Manpower'",(u["company_id"],plan["project_id"])).fetchall()
                        daily=[]; total_planned=total_actual=0.0; days_logged=0; completed_entries=0
                        for r in dc:
                            z=parse_data(r); day=z.get("date") or r["created_at"][:10]
                            daily.append({"date":day,"status":z.get("status",""),"planned_activities":z.get("planned_activities",""),"completed_activities":z.get("completed_activities",""),"delays":z.get("delays","")})
                            days_logged+=1
                            if str(z.get("completed_activities","")).strip(): completed_entries+=1
                        manpower_by_day={}; manpower_rows=[]
                        project_baseline=project_manloader(c,u["company_id"],plan["project_id"])
                        for r in mp:
                            z=parse_data(r); day=z.get("date") or r["created_at"][:10]
                            planned=0.0
                            try: actual=float(z.get("actual_men",0) or 0)
                            except: actual=0.0
                            try: hours=float(z.get("hours",0) or 0)
                            except: hours=0.0
                            v=manpower_by_day.setdefault(day,{"planned_men":0.0,"actual_men":0.0,"man_hours":0.0})
                            v["actual_men"]+=actual; v["man_hours"]+=actual*hours
                            total_actual+=actual
                            manpower_rows.append({"date":day,"role":z.get("role",""),"planned_men":None,"actual_men":actual,"hours":hours,"man_hours":actual*hours})
                        total_planned=project_baseline
                        # Planned daily manpower comes from programme tasks, not daily attendance entries.
                        for t in rows:
                            try:
                                a=date.fromisoformat(t["start_date"]); b=date.fromisoformat(t["finish_date"])
                                day=a
                                while day<=b:
                                    if day.weekday()<5:
                                        v=manpower_by_day.setdefault(day.isoformat(),{"planned_men":0.0,"actual_men":0.0,"man_hours":0.0})
                                        v["planned_men"]+=float(t["planned_men"] or 0)
                                    day+=timedelta(days=1)
                            except Exception: pass
                        # Weighted programme progress: working-day duration as weight.
                        weights=[]; weighted_done=0.0; weight_total=0.0
                        for x in rows:
                            w=max(1,workdays(d(x["start_date"]),d(x["finish_date"])))
                            weight_total+=w; weighted_done+=w*float(x["percent_complete"] or 0)
                            weights.append({"id":x["id"],"name":x["name"],"percent_complete":x["percent_complete"],"weight_days":w})
                        programme_progress=round(weighted_done/weight_total,1) if weight_total else 0.0
                        if parts[3]=="comparison":
                            self.j(200,{"plan":dict(plan),"baseline_set":bool(baseline_tasks),"tasks":baseline_tasks,"programme_progress":programme_progress,"baseline_finish":max((x["baseline_finish"] for x in baseline_tasks),default=None),"current_finish":max((x["scheduled_finish"] for x in rows),default=None)}); return
                        self.j(200,{"plan":dict(plan),"programme_progress":programme_progress,"daily_control":{"days_logged":days_logged,"completed_activity_entries":completed_entries,"records":daily},"manpower":{"total_planned_men_entries":total_planned,"total_actual_men_entries":total_actual,"by_day":manpower_by_day,"rows":manpower_rows},"tasks":weights}); return
                    self.j(200,{"plan":dict(plan),"start_date":start.isoformat() if start else None,"finish_date":finish.isoformat() if finish else None,"tasks":rows}); return
                if len(parts)==4 and parts[3]=="updates" and self.command=="GET":
                    if not has_permission(c,u,"Projects","View"): self.j(403,{"error":"Project view permission required"}); return
                    ups=c.execute("SELECT pu.*,u.name user_name FROM plan_updates pu LEFT JOIN users u ON u.id=pu.created_by WHERE pu.plan_id=? AND pu.company_id=? AND pu.project_id=? ORDER BY pu.update_date DESC,pu.created_at DESC",(plan_id,u["company_id"],plan["project_id"])).fetchall()
                    out=[]
                    for up in ups:
                        ts=c.execute("SELECT put.*,pt.name task_name FROM plan_update_tasks put JOIN plan_tasks pt ON pt.id=put.plan_task_id WHERE put.update_id=? ORDER BY pt.start_date,pt.id",(up["id"],)).fetchall()
                        out.append({"id":up["id"],"update_date":up["update_date"],"note":up["note"],"created_by":up["created_by"],"user_name":up["user_name"],"created_at":up["created_at"],"tasks":[dict(x) for x in ts]})
                    self.j(200,{"plan":dict(plan),"updates":out}); return
                if len(parts)==4 and parts[3]=="performance" and self.command=="GET":
                    if not has_permission(c,u,"Projects","View"): self.j(403,{"error":"Project view permission required"}); return
                    rows=[dict(x) for x in c.execute("SELECT * FROM plan_tasks WHERE plan_id=? AND project_id=? ORDER BY start_date,id",(plan_id,plan["project_id"])).fetchall()]
                    def parse_date(v):
                        try: return date.fromisoformat(v)
                        except Exception: return None
                    weights=[]; total=0.0
                    for x in rows:
                        a=parse_date(x["start_date"]); b=parse_date(x["finish_date"])
                        w=max(1,working_days(c,u["company_id"],plan["project_id"],plan_id,a,b)) if a and b else 1
                        total+=w; weights.append((x,w))
                    current=round(sum(w*float(x["percent_complete"] or 0) for x,w in weights)/total,1) if total else 0.0
                    ups=c.execute("SELECT * FROM plan_updates WHERE plan_id=? AND company_id=? AND project_id=? ORDER BY update_date,created_at",(plan_id,u["company_id"],plan["project_id"])).fetchall()
                    trend=[]
                    for up in ups:
                        vals=c.execute("SELECT plan_task_id,percent_complete FROM plan_update_tasks WHERE update_id=?",(up["id"],)).fetchall(); by={x["plan_task_id"]:x["percent_complete"] for x in vals}
                        prog=round(sum(w*float(by.get(x["id"],x["percent_complete"]) or 0) for x,w in weights)/total,1) if total else 0.0
                        trend.append({"update_id":up["id"],"date":up["update_date"],"progress":prog,"note":up["note"]})
                    mp=c.execute("SELECT * FROM module_records WHERE company_id=? AND project_id=? AND module='Manpower'",(u["company_id"],plan["project_id"])).fetchall()
                    def record_data(r):
                        try: return json.loads(r["data_json"] or "{}")
                        except Exception: return {}
                    manpower={}
                    project_baseline=project_manloader(c,u["company_id"],plan["project_id"])
                    for r in mp:
                        z=record_data(r); day=z.get("date") or r["created_at"][:10]
                        pm=0.0
                        try: am=float(z.get("actual_men",0) or 0)
                        except: am=0.0
                        v=manpower.setdefault(day,{"planned_men":0.0,"actual_men":0.0,"man_hours":0.0})
                        v["planned_men"]+=pm; v["actual_men"]+=am
                        try: v["man_hours"]+=am*float(z.get("hours",0) or 0)
                        except: pass
                    resource=[]
                    for day,v in sorted(manpower.items()):
                        v=dict(v); v["variance_men"]=round(v["actual_men"]-v["planned_men"],1); resource.append({"date":day,**v})
                    total_pm=sum(x["planned_men"] for x in resource); total_am=sum(x["actual_men"] for x in resource)
                    self.j(200,{"plan":dict(plan),"current_progress":current,"update_count":len(trend),"trend":trend,"manpower":resource,"manpower_totals":{"planned_men":round(project_baseline,1),"actual_men":round(total_am,1),"variance_men":round(total_am-project_baseline,1)}}); return
                if len(parts)==4 and parts[3]=="update" and self.command=="POST":
                    if not has_permission(c,u,"Projects","Edit"): self.j(403,{"error":"Project edit permission required"}); return
                    b=self.body(); update_date=str(b.get("update_date","")).strip() or date.today().isoformat(); note=str(b.get("note","")).strip(); items=b.get("tasks",[])
                    try: date.fromisoformat(update_date)
                    except Exception: self.j(400,{"error":"Invalid update date"}); return
                    if not isinstance(items,list): self.j(400,{"error":"Tasks must be a list"}); return
                    seen=set(); validated=[]
                    for item in items:
                        if not isinstance(item,dict) or not item.get("id") or item.get("id") in seen: self.j(400,{"error":"Invalid or duplicate task in update"}); return
                        seen.add(item.get("id")); task=c.execute("SELECT * FROM plan_tasks WHERE id=? AND plan_id=? AND project_id=?",(item.get("id"),plan_id,plan["project_id"])).fetchone()
                        if not task: self.j(400,{"error":"Invalid task in update"}); return
                        try: pct=int(item.get("percent_complete"))
                        except Exception: self.j(400,{"error":"Invalid task progress"}); return
                        if pct<0 or pct>100: self.j(400,{"error":"Invalid task progress"}); return
                        a=item.get("actual_start",task["actual_start"]) or None; f=item.get("actual_finish",task["actual_finish"]) or None
                        if a:
                            try: date.fromisoformat(a)
                            except Exception: self.j(400,{"error":"Invalid actual start"}); return
                        if f:
                            try: date.fromisoformat(f)
                            except Exception: self.j(400,{"error":"Invalid actual finish"}); return
                        if a and f and f<a: self.j(400,{"error":"Actual finish cannot be before actual start"}); return
                        validated.append((task,pct,a,f))
                    if not validated: self.j(400,{"error":"At least one task update is required"}); return
                    uid=secrets.token_hex(8)
                    try:
                        c.execute("BEGIN")
                        c.execute("INSERT INTO plan_updates(id,plan_id,company_id,project_id,update_date,note,created_by) VALUES(?,?,?,?,?,?,?)",(uid,plan_id,u["company_id"],plan["project_id"],update_date,note,u["id"]))
                        for task,pct,a,f in validated:
                            c.execute("INSERT INTO plan_update_tasks(id,update_id,plan_task_id,percent_complete,actual_start,actual_finish) VALUES(?,?,?,?,?,?)",(secrets.token_hex(8),uid,task["id"],pct,a,f))
                            c.execute("UPDATE plan_tasks SET percent_complete=?,task_status=?,actual_start=?,actual_finish=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND plan_id=?",(pct,task_status(pct),a,f,task["id"],plan_id))
                        c.execute("UPDATE plans SET updated_at=CURRENT_TIMESTAMP WHERE id=?",(plan_id,))
                        audit_row(c,u,"PLAN_PROGRAMME_UPDATE",plan_id); audit_row(c,u,"PLAN_UPDATE",uid); c.commit()
                    except Exception:
                        c.rollback(); raise
                    self.j(200,{"id":uid,"updated":len(validated),"updated_tasks":len(validated)}); return
                if len(parts)==4 and parts[3]=="baseline" and self.command=="POST":
                    if not has_permission(c,u,"Projects","Edit"): self.j(403,{"error":"Project edit permission required"}); return
                    c.execute("UPDATE plan_tasks SET baseline_start=start_date,baseline_finish=finish_date WHERE plan_id=?",(plan_id,))
                    c.execute("UPDATE plans SET baseline=1,updated_at=CURRENT_TIMESTAMP WHERE id=? AND company_id=?",(plan_id,u["company_id"]))
                    audit_row(c,u,"PLAN_BASELINE_SET",plan_id); c.commit(); self.j(200,{"ok":True}); return
                if len(parts)==3 and self.command=="PUT":
                    if not has_permission(c,u,"Projects","Edit"): self.j(403,{"error":"Project edit permission required"}); return
                    b=self.body(); name=str(b.get("name",plan["name"])).strip(); status=str(b.get("status",plan["status"])).strip(); baseline=int(bool(b.get("baseline",plan["baseline"])))
                    if not name or status not in ("Draft","Active","Complete","On Hold"): self.j(400,{"error":"Invalid plan values"}); return
                    c.execute("UPDATE plans SET name=?,status=?,baseline=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND company_id=?",(name,status,baseline,plan_id,u["company_id"])); audit_row(c,u,"PLAN_EDIT",plan_id); c.commit(); self.j(200,{"ok":True}); return
                if len(parts)==3 and self.command=="DELETE":
                    if not has_permission(c,u,"Projects","Delete"): self.j(403,{"error":"Project delete permission required"}); return
                    c.execute("DELETE FROM plans WHERE id=? AND company_id=?",(plan_id,u["company_id"])); audit_row(c,u,"PLAN_DELETE",plan_id); c.commit(); self.j(200,{"ok":True}); return
                if len(parts)==4 and parts[3]=="tasks" and self.command=="POST":
                    if not has_permission(c,u,"Projects","Edit"): self.j(403,{"error":"Project edit permission required"}); return
                    b=self.body(); name=str(b.get("name","")).strip(); start=str(b.get("start_date","")).strip(); finish=str(b.get("finish_date","")).strip(); pct=int(b.get("percent_complete",0)); men=float(b.get("planned_men",0)); parent=b.get("parent_id") or None; pred=b.get("predecessor_id") or None; milestone=int(bool(b.get("milestone",False))); notes=str(b.get("notes","")).strip(); dep=str(b.get("dependency_type","FS")).upper(); lag=int(b.get("lag_days",0)); actual_start=b.get("actual_start") or None; actual_finish=b.get("actual_finish") or None
                    if not name or not start or not finish: self.j(400,{"error":"Task name, start date and finish date are required"}); return
                    if finish < start: self.j(400,{"error":"Finish date cannot be before start date"}); return
                    if pct<0 or pct>100 or men<0 or dep not in ("FS","SS","FF","SF") or lag<0: self.j(400,{"error":"Invalid task values"}); return
                    status=LEGACY_TASK_STATUS_MAP.get(str(b.get("status","")).strip(),str(b.get("status","")).strip()) or task_status(pct)
                    if status not in TASK_STATUS_VALUES: self.j(400,{"error":"Invalid task status"}); return
                    pct=task_progress(status,pct)
                    for ref in (parent,pred):
                        if ref and not c.execute("SELECT 1 FROM plan_tasks WHERE id=? AND plan_id=?",(ref,plan_id)).fetchone(): self.j(400,{"error":"Invalid task reference"}); return
                    tid=secrets.token_hex(8); c.execute("INSERT INTO plan_tasks(id,plan_id,project_id,parent_id,name,start_date,finish_date,percent_complete,planned_men,predecessor_id,milestone,notes,dependency_type,lag_days,actual_start,actual_finish,task_status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(tid,plan_id,plan["project_id"],parent,name,start,finish,pct,men,pred,milestone,notes,dep,lag,actual_start,actual_finish,status)); audit_row(c,u,"PLAN_TASK_CREATE",tid); c.commit(); self.j(201,{"id":tid}); return
                if len(parts)==5 and parts[3]=="tasks":
                    tid=parts[4]; task=c.execute("SELECT * FROM plan_tasks WHERE id=? AND plan_id=? AND project_id=?",(tid,plan_id,plan["project_id"])).fetchone()
                    if not task: self.j(404,{"error":"Task not found"}); return
                    if self.command=="PUT":
                        if not has_permission(c,u,"Projects","Edit"): self.j(403,{"error":"Project edit permission required"}); return
                        b=self.body(); name=str(b.get("name",task["name"])).strip(); start=str(b.get("start_date",task["start_date"])); finish=str(b.get("finish_date",task["finish_date"])); pct=int(b.get("percent_complete",task["percent_complete"])); men=float(b.get("planned_men",task["planned_men"])); dep=str(b.get("dependency_type",task["dependency_type"])).upper(); lag=int(b.get("lag_days",task["lag_days"])); pred=b.get("predecessor_id",task["predecessor_id"]) or None; parent=b.get("parent_id",task["parent_id"]) or None; actual_start=b.get("actual_start",task["actual_start"]) or None; actual_finish=b.get("actual_finish",task["actual_finish"]) or None; milestone=int(bool(b.get("milestone",task["milestone"]))); notes=str(b.get("notes",task["notes"] or ""))
                        if not name or finish<start or pct<0 or pct>100 or men<0 or dep not in ("FS","SS","FF","SF") or lag<0: self.j(400,{"error":"Invalid task values"}); return
                        status=LEGACY_TASK_STATUS_MAP.get(str(b.get("status",task["task_status"] or "")).strip(),str(b.get("status",task["task_status"] or "")).strip()) or task_status(pct,task["task_status"])
                        if status not in TASK_STATUS_VALUES: self.j(400,{"error":"Invalid task status"}); return
                        pct=task_progress(status,pct)
                        if pred and not c.execute("SELECT 1 FROM plan_tasks WHERE id=? AND plan_id=?",(pred,plan_id)).fetchone(): self.j(400,{"error":"Invalid predecessor reference"}); return
                        if parent and not c.execute("SELECT 1 FROM plan_tasks WHERE id=? AND plan_id=?",(parent,plan_id)).fetchone(): self.j(400,{"error":"Invalid parent activity reference"}); return
                        if parent==tid: self.j(400,{"error":"An activity cannot be its own parent"}); return
                        c.execute("UPDATE plan_tasks SET name=?,start_date=?,finish_date=?,percent_complete=?,planned_men=?,parent_id=?,predecessor_id=?,milestone=?,notes=?,dependency_type=?,lag_days=?,actual_start=?,actual_finish=?,task_status=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND plan_id=?",(name,start,finish,pct,men,parent,pred,milestone,notes,dep,lag,actual_start,actual_finish,status,tid,plan_id)); audit_row(c,u,"PLAN_TASK_EDIT",tid); c.commit(); self.j(200,{"ok":True}); return
                    if self.command=="DELETE":
                        if not has_permission(c,u,"Projects","Edit"): self.j(403,{"error":"Project edit permission required"}); return
                        c.execute("DELETE FROM plan_tasks WHERE id=? AND plan_id=?",(tid,plan_id)); audit_row(c,u,"PLAN_TASK_DELETE",tid); c.commit(); self.j(200,{"ok":True}); return
            if path.startswith("/api/plans/") and len(path.strip("/").split("/"))==4:
                pass
            # Programme calendar exceptions and controlled update workflow.
            if path=="/api/plan-calendar" and self.command in ("GET","POST"):
                from urllib.parse import parse_qs
                qs=parse_qs(urlparse(self.path).query); pid=(qs.get("project_id") or [None])[0]; plan_id=(qs.get("plan_id") or [None])[0]
                if self.command=="POST":
                    try: pb=self.body()
                    except Exception: self.j(400,{"error":"Invalid JSON"}); return
                    pid=str(pb.get("project_id",pid) or "").strip(); plan_id=str(pb.get("plan_id",plan_id) or "").strip() or None
                if not pid or not can_access_project(c,u,pid): self.j(403,{"error":"Project access required"}); return
                if plan_id and not c.execute("SELECT 1 FROM plans WHERE id=? AND company_id=? AND project_id=?",(plan_id,u["company_id"],pid)).fetchone(): self.j(404,{"error":"Plan not found"}); return
                if self.command=="GET":
                    rows=c.execute("SELECT * FROM plan_calendar_exceptions WHERE company_id=? AND project_id=? AND (plan_id=? OR plan_id IS NULL) ORDER BY exception_date",(u["company_id"],pid,plan_id)).fetchall(); self.j(200,{"exceptions":[dict(x) for x in rows]}); return
                if not has_permission(c,u,"Projects","Edit"): self.j(403,{"error":"Project edit permission required"}); return
                b=pb; day=str(b.get("exception_date","")).strip(); working=1 if bool(b.get("working",False)) else 0; reason=str(b.get("reason","")).strip()
                try:
                    date.fromisoformat(day)
                except Exception: self.j(400,{"error":"Invalid exception date"}); return
                eid=secrets.token_hex(8)
                c.execute("INSERT INTO plan_calendar_exceptions(id,company_id,project_id,plan_id,exception_date,working,reason) VALUES(?,?,?,?,?,?,?) ON CONFLICT(company_id,project_id,plan_id,exception_date) DO UPDATE SET working=excluded.working,reason=excluded.reason",(eid,u["company_id"],pid,plan_id,day,working,reason)); audit_row(c,u,"PLAN_CALENDAR_UPDATE",day); c.commit(); self.j(200,{"ok":True}); return
            if path.startswith("/api/plan-calendar/") and self.command=="DELETE":
                eid=path.rsplit("/",1)[-1]; row=c.execute("SELECT * FROM plan_calendar_exceptions WHERE id=? AND company_id=?",(eid,u["company_id"])).fetchone()
                if not row or not can_access_project(c,u,row["project_id"]): self.j(404,{"error":"Calendar exception not found"}); return
                if not has_permission(c,u,"Projects","Edit"): self.j(403,{"error":"Project edit permission required"}); return
                c.execute("DELETE FROM plan_calendar_exceptions WHERE id=?",(eid,)); audit_row(c,u,"PLAN_CALENDAR_DELETE",eid); c.commit(); self.j(200,{"ok":True}); return
            if path.startswith("/api/plans/") and path.endswith("/control") and self.command=="GET":
                # Programme Control Centre: objective status, baseline variance, overdue and critical work.
                plan_id=path.strip("/").split("/")[2]
                plan=c.execute("SELECT * FROM plans WHERE id=? AND company_id=?",(plan_id,u["company_id"])).fetchone()
                if not plan or not can_access_project(c,u,plan["project_id"]): self.j(404,{"error":"Plan not found"}); return
                if not has_permission(c,u,"Projects","View"): self.j(403,{"error":"Project view permission required"}); return
                rows=[dict(x) for x in c.execute("SELECT * FROM plan_tasks WHERE plan_id=? AND project_id=? ORDER BY start_date,id",(plan_id,plan["project_id"])).fetchall()]
                today=date.today()
                total_weight=0; weighted_progress=0
                for x in rows:
                    try:
                        sd=date.fromisoformat(x["start_date"]); fd=date.fromisoformat(x["finish_date"])
                    except Exception:
                        self.j(409,{"error":"Invalid task date range"}); return
                    weight=max(1,working_days(c,u["company_id"],plan["project_id"],plan_id,sd,fd))
                    total_weight+=weight; weighted_progress+=weight*int(x.get("percent_complete") or 0)
                progress=round(weighted_progress/total_weight,1) if total_weight else 0
                overdue=[]; critical_incomplete=[]; completed=0; in_progress=0; not_started=0
                for x in rows:
                    pct=int(x.get("percent_complete") or 0)
                    if pct>=100: completed+=1
                    elif pct>0: in_progress+=1
                    else: not_started+=1
                    try: fd=date.fromisoformat(x["finish_date"])
                    except Exception: continue
                    if pct<100 and fd<today:
                        overdue.append({"id":x["id"],"name":x["name"],"finish_date":x["finish_date"],"percent_complete":pct,"days_overdue":(today-fd).days})
                # Reuse Gantt calculation by reproducing the minimal scheduled finish logic with plan calendar.
                # The control report intentionally reports facts, not a subjective health score.
                scheduled_finish=max((x["finish_date"] for x in rows),default=None)
                baseline_finish=max((x["baseline_finish"] for x in rows if x.get("baseline_finish")),default=None)
                current_finish=scheduled_finish
                if baseline_finish and current_finish:
                    try: variance=(date.fromisoformat(current_finish)-date.fromisoformat(baseline_finish)).days
                    except Exception: variance=None
                else: variance=None
                # Critical-path flags are computed by the Gantt endpoint; calculate a conservative critical set here
                # from zero float using the same dependency network.
                by={x["id"]:x for x in rows}; visiting=set(); visited=set(); es={}; ef={}
                def dfs(tid):
                    if tid in visiting: return False
                    if tid in visited: return True
                    visiting.add(tid); pred=by[tid].get("predecessor_id")
                    if pred and pred not in by: return False
                    if pred and not dfs(pred): return False
                    visiting.remove(tid); visited.add(tid); return True
                if any(not dfs(x["id"]) for x in rows): self.j(409,{"error":"Dependency cycle detected"}); return
                ordered=sorted(rows,key=lambda x:(x["start_date"],x["id"]))
                def wd(a,b): return working_days(c,u["company_id"],plan["project_id"],plan_id,a,b)
                def aw(a,n): return add_plan_workdays(c,u["company_id"],plan["project_id"],plan_id,a,n)
                for x in ordered:
                    sd=date.fromisoformat(x["start_date"]); fd=date.fromisoformat(x["finish_date"]); dur=max(1,wd(sd,fd)); start=sd; finish=aw(start,dur-1); pred=x.get("predecessor_id")
                    if pred:
                        ps,pf=es[pred],ef[pred]; lag=int(x.get("lag_days") or 0); typ=x.get("dependency_type") or "FS"
                        if typ=="FS": start=max(start,aw(pf,lag+1)); finish=aw(start,dur-1)
                        elif typ=="SS": start=max(start,aw(ps,lag)); finish=aw(start,dur-1)
                        elif typ=="FF": finish=max(finish,aw(pf,lag)); start=aw(finish,-(dur-1))
                        else: finish=max(finish,aw(ps,lag)); start=aw(finish,-(dur-1))
                    es[x["id"]]=start; ef[x["id"]]=finish
                pf=max(ef.values()) if ef else None; lf={}; ls={}
                for x in reversed(ordered):
                    children=[y for y in rows if y.get("predecessor_id")==x["id"]]; dur=max(1,wd(date.fromisoformat(x["start_date"]),date.fromisoformat(x["finish_date"])))
                    if not children: latest=pf
                    else:
                        vals=[]
                        for y in children:
                            typ=y.get("dependency_type") or "FS"; lag=int(y.get("lag_days") or 0)
                            if typ=="FS": vals.append(aw(ls[y["id"]],-(lag+1)))
                            elif typ=="SS": vals.append(aw(ls[y["id"]],-lag)+__import__('datetime').timedelta(days=dur-1))
                            elif typ=="FF": vals.append(aw(lf[y["id"]],-lag))
                            else: vals.append(aw(lf[y["id"]],-lag)+__import__('datetime').timedelta(days=dur-1))
                        latest=min(vals)
                    lf[x["id"]]=latest; ls[x["id"]]=aw(latest,-(dur-1))
                for x in rows:
                    if x["id"] in es and ls[x["id"]]==es[x["id"]] and int(x.get("percent_complete") or 0)<100:
                        critical_incomplete.append({"id":x["id"],"name":x["name"],"finish_date":x["finish_date"],"percent_complete":int(x.get("percent_complete") or 0)})
                self.j(200,{"plan":dict(plan),"as_of":today.isoformat(),"programme_progress":progress,"activity_counts":{"total":len(rows),"completed":completed,"in_progress":in_progress,"not_started":not_started},"overdue":overdue,"critical_incomplete":critical_incomplete,"baseline_finish":baseline_finish,"current_finish":current_finish,"baseline_finish_variance_days":variance})
                return
            if path.startswith("/api/plans/") and path.endswith("/update") and self.command=="POST":
                parts=path.strip("/").split("/"); plan_id=parts[2] if len(parts)>2 else ""
                plan=c.execute("SELECT * FROM plans WHERE id=? AND company_id=?",(plan_id,u["company_id"])).fetchone()
                if not plan or not can_access_project(c,u,plan["project_id"]): self.j(404,{"error":"Plan not found"}); return
                if not has_permission(c,u,"Projects","Edit"): self.j(403,{"error":"Project edit permission required"}); return
                b=self.body(); updates=b.get("tasks",[])
                if not isinstance(updates,list): self.j(400,{"error":"tasks must be a list"}); return
                validated=[]
                for item in updates:
                    tid=str(item.get("id","")).strip(); task=c.execute("SELECT * FROM plan_tasks WHERE id=? AND plan_id=? AND project_id=?",(tid,plan_id,plan["project_id"])).fetchone()
                    if not task: self.j(400,{"error":"Invalid task in programme update"}); return
                    try: pct=int(item.get("percent_complete",task["percent_complete"]))
                    except Exception: self.j(400,{"error":"Progress must be an integer"}); return
                    actual_start=item.get("actual_start",task["actual_start"]) or None; actual_finish=item.get("actual_finish",task["actual_finish"]) or None
                    if pct<0 or pct>100: self.j(400,{"error":"Progress must be 0-100"}); return
                    if actual_start and actual_finish and actual_finish<actual_start: self.j(400,{"error":"Actual finish cannot be before actual start"}); return
                    validated.append((pct,actual_start,actual_finish,tid))
                for pct,actual_start,actual_finish,tid in validated:
                    c.execute("UPDATE plan_tasks SET percent_complete=?,actual_start=?,actual_finish=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND plan_id=?",(pct,actual_start,actual_finish,tid,plan_id))
                audit_row(c,u,"PLAN_PROGRAMME_UPDATE",plan_id); c.commit(); self.j(200,{"ok":True,"updated":len(validated)}); return
            if path=="/api/module-spec" and self.command=="GET":
                module=(_parse_qs(urlparse(self.path).query).get("module") or [""])[0]
                if not valid_module(module) or not bulk_spec(module):
                    self.j(400,{"error":"No data-entry specification is available for this module"}); return
                if not has_permission(c,u,module,"View"):
                    self.j(403,{"error":"View permission required"}); return
                fields=[{"header":h,"key":import_data_key(h),"required":required,"type":typ} for h,required,typ in bulk_spec(module)]
                self.j(200,{"module":module,"fields":fields,"role_values":ROLE_VALUES}); return
            if path.startswith("/api/module/"):
                parts=path.strip("/").split("/")
                module=parts[2] if len(parts)>2 else ""
                if not valid_module(module): self.j(400,{"error":"Invalid module"}); return
                if len(parts)==3 and self.command=="GET":
                    pid=urlparse(self.path).query
                    from urllib.parse import parse_qs
                    qs=parse_qs(pid); project_id=(qs.get("project_id") or [None])[0]
                    if not project_id or not can_access_project(c,u,project_id): self.j(403,{"error":"Project access required"}); return
                    if not has_permission(c,u,module,"View"): self.j(403,{"error":"View permission required"}); return
                    rows=c.execute("SELECT id,project_id,module,title,data_json,created_by,created_at,updated_at FROM module_records WHERE company_id=? AND project_id=? AND module=? ORDER BY id DESC",(u["company_id"],project_id,module)).fetchall()
                    self.j(200,{"records":[dict(x) for x in rows]}); return
                if len(parts)==3 and self.command=="POST":
                    if not has_permission(c,u,module,"Create"): self.j(403,{"error":"Create permission required"}); return
                    b=self.body(); project_id=str(b.get("project_id","")).strip(); title=str(b.get("title","")).strip(); data=b.get("data",{})
                    if not project_id or not can_access_project(c,u,project_id): self.j(403,{"error":"Project access required"}); return
                    item,errors=validate_individual_record(module,title,data)
                    if errors: self.j(400,{"error":"Data entry validation failed","errors":errors}); return
                    title=item["title"]; data=item["data"]
                    rid=secrets.token_hex(8); c.execute("INSERT INTO module_records(id,company_id,project_id,module,title,data_json,created_by) VALUES(?,?,?,?,?,?,?)",(rid,u["company_id"],project_id,module,title,json.dumps(data),u["id"])); audit_row(c,u,module.upper().replace(" ","_")+"_CREATE",rid); c.commit(); self.j(201,{"id":rid}); return
                if len(parts)==4:
                    rid=parts[3]; row=c.execute("SELECT * FROM module_records WHERE id=? AND company_id=? AND module=?",(rid,u["company_id"],module)).fetchone()
                    if not row: self.j(404,{"error":"Record not found"}); return
                    if not can_access_project(c,u,row["project_id"]): self.j(403,{"error":"Project access required"}); return
                    if self.command=="PUT":
                        if not has_permission(c,u,module,"Edit"): self.j(403,{"error":"Edit permission required"}); return
                        b=self.body(); title=str(b.get("title",row["title"])).strip(); data=b.get("data",{})
                        item,errors=validate_individual_record(module,title,data)
                        if errors: self.j(400,{"error":"Data entry validation failed","errors":errors}); return
                        title=item["title"]; data=item["data"]
                        c.execute("UPDATE module_records SET title=?,data_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND company_id=?",(title,json.dumps(data),rid,u["company_id"])); audit_row(c,u,module.upper().replace(" ","_")+"_EDIT",rid); c.commit(); self.j(200,{"ok":True}); return
                    if self.command=="DELETE":
                        if not has_permission(c,u,module,"Delete"): self.j(403,{"error":"Delete permission required"}); return
                        c.execute("DELETE FROM module_records WHERE id=? AND company_id=?",(rid,u["company_id"])); audit_row(c,u,module.upper().replace(" ","_")+"_DELETE",rid); c.commit(); self.j(200,{"ok":True}); return
            if path=="/api/attachments" and self.command=="GET":
                from urllib.parse import parse_qs
                qs=parse_qs(urlparse(self.path).query); project_id=(qs.get("project_id") or [None])[0]
                if not project_id or not can_access_project(c,u,project_id): self.j(403,{"error":"Project access required"}); return
                if not has_permission(c,u,"Documents","View"): self.j(403,{"error":"Documents view permission required"}); return
                rows=c.execute("SELECT id,project_id,record_id,filename,mime_type,size_bytes,uploaded_by,created_at FROM attachments WHERE company_id=? AND project_id=? ORDER BY id DESC",(u["company_id"],project_id)).fetchall()
                self.j(200,{"attachments":[dict(x) for x in rows]}); return
            if path=="/api/attachments" and self.command=="POST":
                if not has_permission(c,u,"Documents","Create"): self.j(403,{"error":"Documents create permission required"}); return
                b=self.body(); project_id=str(b.get("project_id","")).strip(); filename=str(b.get("filename","")).strip(); mime=str(b.get("mime_type") or "application/octet-stream"); record_id=b.get("record_id") or None
                raw=b.get("content_base64","")
                if not project_id or not can_access_project(c,u,project_id): self.j(403,{"error":"Project access required"}); return
                if not filename or not raw: self.j(400,{"error":"Filename and content are required"}); return
                if len(filename)>180 or "/" in filename or "\\" in filename or "\x00" in filename: self.j(400,{"error":"Invalid filename"}); return
                if record_id and not c.execute("SELECT 1 FROM module_records WHERE id=? AND company_id=? AND project_id=?",(record_id,u["company_id"],project_id)).fetchone(): self.j(400,{"error":"Invalid record for project"}); return
                try: data=base64.b64decode(raw,validate=True)
                except Exception: self.j(400,{"error":"Invalid base64 content"}); return
                if len(data)>10*1024*1024: self.j(413,{"error":"Development upload limit is 10 MB"}); return
                aid=secrets.token_hex(8); stored=aid+".bin"
                (UPLOADS/stored).write_bytes(data)
                c.execute("INSERT INTO attachments(id,company_id,project_id,record_id,filename,stored_name,mime_type,size_bytes,uploaded_by) VALUES(?,?,?,?,?,?,?,?,?)",(aid,u["company_id"],project_id,record_id,filename,stored,mime,len(data),u["id"]))
                audit_row(c,u,"DOCUMENT_UPLOAD",aid); c.commit(); self.j(201,{"id":aid}); return
            if path.startswith("/api/attachments/"):
                aid=path.rsplit("/",1)[1]; row=c.execute("SELECT * FROM attachments WHERE id=? AND company_id=?",(aid,u["company_id"])).fetchone()
                if not row or not can_access_project(c,u,row["project_id"]): self.j(404,{"error":"Attachment not found"}); return
                if self.command=="GET":
                    if not has_permission(c,u,"Documents","View"): self.j(403,{"error":"Documents view permission required"}); return
                    data=(UPLOADS/row["stored_name"]).read_bytes()
                    self.send_response(200); self.send_header("Content-Type",row["mime_type"]); self.send_header("Content-Length",str(len(data))); self.send_header("Content-Disposition",f'attachment; filename="{row["filename"].replace(chr(34),"")}"'); self.end_headers(); self.wfile.write(data); return
                if self.command=="DELETE":
                    if not has_permission(c,u,"Documents","Delete"): self.j(403,{"error":"Documents delete permission required"}); return
                    try:(UPLOADS/row["stored_name"]).unlink()
                    except FileNotFoundError: pass
                    c.execute("DELETE FROM attachments WHERE id=? AND company_id=?",(aid,u["company_id"])); audit_row(c,u,"DOCUMENT_DELETE",aid); c.commit(); self.j(200,{"ok":True}); return
            if self.command=="GET" and path=="/api/audit":
                if not require_admin(self,u):return
                rows=c.execute("SELECT a.*,u.name user_name FROM audit a LEFT JOIN users u ON u.id=a.user_id WHERE a.company_id=? ORDER BY a.id DESC LIMIT 200",(u["company_id"],)).fetchall();self.j(200,{"audit":[dict(x) for x in rows]});return
            self.j(404,{"error":"Not found"})
        except sqlite3.IntegrityError as e:
            self.j(409,{"error":"Database constraint prevented this change"})
        except Exception as e:
            import traceback; traceback.print_exc()
            self.j(500,{"error":"Server error"})
        finally:
            try:
                if c: c.close()
            except Exception:
                pass

    def _static_response(self, head_only=False):
        requested=unquote(urlparse(self.path).path)
        if requested == "/":
            requested="/index.html"
        # Static assets must remain inside the static directory even for encoded ../ paths.
        candidate=(STATIC/requested.lstrip("/")).resolve()
        try:
            candidate.relative_to(STATIC)
        except ValueError:
            self.send_error(400, "Invalid static path"); return
        if not candidate.exists() or not candidate.is_file():
            self.send_error(404); return
        typ=mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        self.send_response(200); self.send_header("Content-Type",typ)
        self.send_header("Cache-Control","no-store")
        self.send_header("Content-Length",str(candidate.stat().st_size)); self.end_headers()
        if not head_only: self.wfile.write(candidate.read_bytes())
    def do_GET(self):
        if self.path.startswith("/api/") or urlparse(self.path).path == "/healthz": return self.do()
        self._static_response(False)
    def do_HEAD(self):
        if self.path.startswith("/api/"): return self.do()
        self._static_response(True)
    def do_POST(self):self.do()
    def do_PUT(self):self.do()
    def do_DELETE(self):self.do()

if __name__=="__main__":
    init_db(); print(f"Construction Control: listening on port {PORT}")
    ThreadingHTTPServer(("0.0.0.0",PORT),Handler).serve_forever()
