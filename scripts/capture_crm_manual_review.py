"""Read-only private evidence snapshot of the local CRM/RAG pilot.

Run with the CRM Python (PyMySQL installed). No provider/Telegram calls,
schema changes, message deletion, polling restart, or environment export.
Different components are captured separately, not a distributed transaction.
"""
import argparse
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import subprocess
import sys


def serial(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return {'hex': bytes(value).hex()}
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(type(value).__name__)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--crm-root', type=Path, required=True)
    parser.add_argument('--rag-root', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    crm, rag, output = args.crm_root.resolve(), args.rag_root.resolve(), args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(crm))
    from tools.collect_support_baseline import load_config
    import pymysql
    config = load_config(crm / '.local/crm.env')
    if config['host'] != '127.0.0.1' or config['database'] != 'crm_rag_demo':
        raise SystemExit('Only the isolated local pilot database is permitted')
    manifest = {'started_at_utc': datetime.now(timezone.utc).isoformat(), 'files': {}, 'repositories': {}}

    def save(name, content):
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        manifest['files'][name] = {'bytes': len(content), 'sha256': sha256(content).hexdigest()}

    with pymysql.connect(**config, cursorclass=pymysql.cursors.DictCursor) as connection:
        with connection.cursor() as cursor:
            cursor.execute('SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            cursor.execute('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY')
            cursor.execute("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE()")
            names = [row['TABLE_NAME'] for row in cursor.fetchall()]
            names = sorted(name for name in names if (name.startswith('support_v2_')
                           and name not in ('support_v2_client_tokens', 'support_v2_schema_migrations'))
                           or name in ('ui_state', 'bot_events', 'events', 'event_logs'))
            tables = {}
            for name in names:
                cursor.execute('SELECT * FROM `' + name + '`')
                tables[name] = cursor.fetchall()
            save('crm/tables.json', json.dumps(tables, ensure_ascii=False, indent=2, default=serial).encode())
        connection.rollback()
    source = rag / '.local/crm-state.sqlite3'
    with sqlite3.connect('file:' + source.as_posix() + '?mode=ro', uri=True) as connection:
        with sqlite3.connect(output / 'rag-state.sqlite3') as backup:
            connection.backup(backup)
    raw = (output / 'rag-state.sqlite3').read_bytes()
    manifest['files']['rag-state.sqlite3'] = {'bytes': len(raw), 'sha256': sha256(raw).hexdigest()}
    for name, root in [('crm', crm), ('rag', rag)]:
        manifest['repositories'][name] = {
            'root': str(root),
            'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
            'status': subprocess.check_output(['git', 'status', '--short', '--branch'], cwd=root, text=True),
        }
        candidates = set((root / '.local').glob('*.log'))
        candidates.update((root / '.local').glob('*runtime.json'))
        candidates.update((root / '.local').glob('*.jsonl'))
        if name == 'crm':
            candidates.add(root / 'logs/tg_bot.log')
            candidates.add(root / 'bot/var/bot_state.pkl')
        for path in sorted(candidates):
            if path.is_file():
                content = path.read_bytes()
                relative = name + '/' + path.relative_to(root).as_posix().replace('.local/', 'local/')
                save(relative, content)
                manifest['files'][relative]['changed_during_read'] = path.read_bytes() != content
        files = [*sorted((root / 'app').glob('*.py')), *sorted((root / 'bot').glob('*.py')),
                 *sorted((root / 'services/support').glob('*.py'))]
        manifest['repositories'][name]['source_sha256'] = {
            p.relative_to(root).as_posix(): sha256(p.read_bytes()).hexdigest() for p in files}
    manifest['completed_at_utc'] = datetime.now(timezone.utc).isoformat()
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'private_snapshot': str(output), 'captured_files': len(manifest['files']),
                      'mysql_tables': {name: len(rows) for name, rows in tables.items()}}, ensure_ascii=True))


if __name__ == '__main__':
    main()
