"""Back up the local database to a folder your cloud client already syncs.

Principle (local-first): we do NOT talk to the Google/Dropbox APIs and keep no
OAuth keys. We write a consistent snapshot of the database into a local folder
that your desktop Google Drive / Dropbox / iCloud client then pushes to the
cloud. No keys, works with any of those providers.

The snapshot uses SQLite's online backup API (safe with WAL). Optionally, when
`cryptography` is installed and BACKUP_KEY is set, the file is encrypted (Fernet)
— useful since it lands in the cloud.
"""
import base64
import hashlib
import os
import sqlite3
from datetime import datetime
from pathlib import Path

import engine_bridge as eb
import planner

KEEP = 14              # how many recent backups to keep
SUBDIR = "kist-backups"

# Backup encryption format. `KISTB2` = versioned header + random per-file salt +
# Fernet token. Legacy files (unsalted sha256, pre-hardening) still decrypt.
_MAGIC = b"KISTB2\n"
_SALT_LEN = 16
PBKDF2_ITERS = 600_000  # OWASP 2023 baseline for PBKDF2-HMAC-SHA256


class BackupError(Exception):
    pass


def _db_path():
    for r in eb._rows("PRAGMA database_list"):
        if r.get("name") == "main" and r.get("file"):
            return r["file"]
    return None


def _first(base: Path, pattern: str):
    try:
        return next(iter(sorted(base.glob(pattern))), None)
    except Exception:
        return None


def list_destinations():
    """Detect common cloud-synced folders (only ones that exist)."""
    home = Path.home()
    cs = home / "Library/CloudStorage"
    cands = [
        ("gdrive", "Google Drive", _first(cs, "GoogleDrive-*/My Drive")
            or _first(cs, "GoogleDrive-*/M\u00f3j dysk")),  # localized clients; never the virtual root
        ("gdrive_legacy", "Google Drive", home / "Google Drive"),
        ("dropbox", "Dropbox", home / "Dropbox"),
        ("dropbox_cs", "Dropbox", _first(cs, "Dropbox*")),
        ("icloud", "iCloud Drive", home / "Library/Mobile Documents/com~apple~CloudDocs"),
    ]
    seen, out = set(), []
    for key, label, p in cands:
        if p and Path(p).exists() and str(p) not in seen:
            seen.add(str(p))
            out.append({"key": key, "label": label, "path": str(p)})
    return out


def _folder():
    d = planner.get_setting("backup_dir")
    return os.path.join(d, SUBDIR) if d else None


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    """PBKDF2-HMAC-SHA256(passphrase, salt) -> Fernet key (urlsafe-b64, 32 B).
    Salted and costly, so offline brute-force from a stolen .enc is expensive."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                     iterations=PBKDF2_ITERS)
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))


def _maybe_encrypt(path):
    """Encrypt with Fernet (PBKDF2, versioned header + salt).

    FAIL-CLOSED: the backup lands in a cloud-synced folder, so we never silently
    drop a plaintext finance DB there. If BACKUP_KEY is set but `cryptography` is
    missing -> error (the user asked for encryption and didn't get it). If no key
    -> error, unless `backup_allow_plaintext` is explicitly enabled.
    """
    key = os.environ.get("BACKUP_KEY", "")
    if not key:
        # settings are stored as str(v), so `False` reads back as truthy "False";
        # parse to a real bool explicitly, otherwise this fails OPEN.
        allow = str(planner.get_setting("backup_allow_plaintext") or "").strip().lower()
        if allow in ("1", "true", "yes", "on"):
            return path, False
        raise BackupError(
            "unencrypted cloud backup blocked — set BACKUP_KEY in .env or "
            "explicitly enable plaintext backup (backup_allow_plaintext) in settings")
    try:
        from cryptography.fernet import Fernet
    except Exception:
        raise BackupError(
            "BACKUP_KEY is set but the cryptography library is missing — "
            "pip install cryptography (refusing to drop a plaintext DB to the cloud)")
    salt = os.urandom(_SALT_LEN)
    fkey = _derive_key(key, salt)
    data = Path(path).read_bytes()
    enc = path + ".enc"
    Path(enc).write_bytes(_MAGIC + salt + Fernet(fkey).encrypt(data))
    os.remove(path)
    return enc, True


def _prune(folder):
    files = sorted(Path(folder).glob("finance-*.db*"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[KEEP:]:
        try:
            old.unlink()
        except Exception:
            pass


def set_destination(path):
    planner.set_settings({"backup_dir": path})
    return {"ok": True, "dir": path}


def create_backup():
    folder = _folder()
    if not folder:
        return {"ok": False, "error": "no backup folder set — choose one in Control Center"}
    src = _db_path()
    if not src or not os.path.exists(src):
        return {"ok": False, "error": "database file not found"}
    os.makedirs(folder, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = os.path.join(folder, f"finance-{ts}.db")
    s = sqlite3.connect(src)
    d = sqlite3.connect(out)
    try:
        s.backup(d)          # consistent snapshot (handles WAL)
    finally:
        d.close()
        s.close()
    try:
        final, encrypted = _maybe_encrypt(out)
    except BackupError as e:
        # fail-closed: never leave the plaintext snapshot behind in the cloud folder
        try:
            os.remove(out)
        except OSError:
            pass
        return {"ok": False, "error": str(e)}
    _prune(folder)
    size = os.path.getsize(final)
    return {"ok": True, "file": os.path.basename(final), "dir": folder,
            "encrypted": encrypted, "size_kb": round(size / 1024, 1)}


def list_backups():
    """Snapshots in the backup folder, newest first (excludes safety copies)."""
    folder = _folder()
    if not folder or not os.path.isdir(folder):
        return []
    out = []
    for p in sorted(Path(folder).glob("finance-*.db*"), key=lambda p: p.stat().st_mtime, reverse=True):
        out.append({"file": p.name,
                    "when": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="minutes"),
                    "size_kb": round(p.stat().st_size / 1024, 1),
                    "encrypted": p.name.endswith(".enc")})
    return out


def _decrypt_to(src, dst):
    from cryptography.fernet import Fernet
    key = os.environ["BACKUP_KEY"]
    blob = Path(src).read_bytes()
    if blob.startswith(_MAGIC):                 # KISTB2: header + salt + token
        salt = blob[len(_MAGIC):len(_MAGIC) + _SALT_LEN]
        token = blob[len(_MAGIC) + _SALT_LEN:]
        fkey = _derive_key(key, salt)
    else:                                       # legacy: unsalted sha256 (pre-hardening)
        fkey = base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest())
        token = blob
    Path(dst).write_bytes(Fernet(fkey).decrypt(token))


def restore(filename):
    """Restore a snapshot into the live DB. Makes a pre-restore safety copy first,
    and writes via SQLite's backup API (safe with WAL / open connections)."""
    folder = _folder()
    if not folder:
        return {"ok": False, "error": "no backup folder set"}
    if not filename or "/" in filename or ".." in filename:
        return {"ok": False, "error": "invalid backup name"}
    src = Path(folder) / filename
    if not src.exists():
        return {"ok": False, "error": "backup not found"}
    live = _db_path()
    if not live or not os.path.exists(live):
        return {"ok": False, "error": "live database not found"}

    plain, tmp = str(src), None
    if filename.endswith(".enc"):
        if not os.environ.get("BACKUP_KEY"):
            return {"ok": False, "error": "encrypted backup — set BACKUP_KEY to restore"}
        try:
            import cryptography  # noqa: F401
        except Exception:
            return {"ok": False, "error": "encrypted backup — pip install cryptography to restore"}
        tmp = str(src) + ".plain.tmp"
        try:
            _decrypt_to(str(src), tmp)
        except Exception as e:
            return {"ok": False, "error": "decrypt failed: " + str(e)[:60]}
        plain = tmp

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    safety = os.path.join(folder, f"pre-restore-{ts}.db")
    try:
        sl = sqlite3.connect(live); sd = sqlite3.connect(safety)
        sl.backup(sd); sd.close(); sl.close()
    except Exception:
        safety = None
    try:
        ss = sqlite3.connect(plain); dl = sqlite3.connect(live)
        ss.backup(dl); dl.close(); ss.close()
    except Exception as e:
        return {"ok": False, "error": "restore failed: " + str(e)[:80]}
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)
    return {"ok": True, "restored": filename,
            "safety_copy": os.path.basename(safety) if safety else None}


def set_auto(enabled):
    planner.set_settings({"backup_auto": bool(enabled)})
    return {"ok": True, "auto": bool(enabled)}


def maybe_auto_backup(min_hours=24):
    """If auto-backup is on and the newest snapshot is older than min_hours (or
    none exists), create one. Best-effort; safe to call on every app start."""
    try:
        if not planner.get_setting("backup_auto") or not _folder():
            return None
        st = status()
        last = st.get("last")
        if last:
            age_h = (datetime.now() - datetime.fromisoformat(last["when"])).total_seconds() / 3600
            if age_h < min_hours:
                return None
        return create_backup()
    except Exception:
        return None


def status():
    d = planner.get_setting("backup_dir") or ""
    folder = _folder()
    last, count = None, 0
    if folder and os.path.isdir(folder):
        files = sorted(Path(folder).glob("finance-*.db*"), key=lambda p: p.stat().st_mtime, reverse=True)
        count = len(files)
        if files:
            f = files[0]
            last = {"name": f.name,
                    "when": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="minutes")}
    enc_ready = bool(os.environ.get("BACKUP_KEY"))
    try:
        import cryptography  # noqa: F401
        enc_avail = True
    except Exception:
        enc_avail = False
    return {"dir": d, "configured": bool(d), "last": last, "count": count,
            "auto": bool(planner.get_setting("backup_auto")),
            "destinations": list_destinations(),
            "backups": list_backups(),
            "encryption": {"on": enc_ready and enc_avail, "lib": enc_avail,
                           "hint": "" if enc_avail else "optional: pip install cryptography + BACKUP_KEY in .env"}}
