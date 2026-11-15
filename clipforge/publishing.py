"""Fila local de publicação: aprovação, idempotência e confirmação separadas.

Falha ambígua durante envio exige reconciliação humana: nunca repetir upload
sem saber se a plataforma recebeu o primeiro pedido.
"""
from __future__ import annotations

import hashlib
import math
import os
import threading
import time
import uuid
from pathlib import Path

from .social_connectors import configured_connectors


def media_digest(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


class PublishingService:
    def __init__(self, store, connectors=None, *, enabled=None):
        self.store = store
        self.connectors = configured_connectors() if connectors is None else connectors
        self.enabled = os.getenv('PUBLISHING_ENABLED', '0') == '1' if enabled is None else enabled
        self.daily_limit = max(1, int(os.getenv('PUBLISHING_DAILY_LIMIT', '5')))
        self.max_polls = max(1, int(os.getenv('PUBLISHING_MAX_POLLS', '20')))
        self._stop = threading.Event()
        self._thread = None
        self._processing = threading.Lock()
        with store.lock, store._db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS publication_jobs (
                id TEXT PRIMARY KEY, clip_id TEXT NOT NULL, platform TEXT NOT NULL,
                title TEXT NOT NULL, description TEXT NOT NULL, media_sha256 TEXT NOT NULL,
                status TEXT NOT NULL, automatic INTEGER NOT NULL, scheduled_at REAL NOT NULL,
                next_attempt_at REAL NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL,
                operation_id TEXT, remote_id TEXT, visibility TEXT, error TEXT,
                poll_attempts INTEGER NOT NULL DEFAULT 0, submitted_at REAL,
                UNIQUE(clip_id, platform), UNIQUE(media_sha256, platform)
            )''')
            db.execute('''CREATE TABLE IF NOT EXISTS publication_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
                status TEXT NOT NULL, created_at REAL NOT NULL, detail TEXT NOT NULL
            )''')
            # O processo pode ter caído após o POST, antes de persistir o ID remoto.
            db.execute("UPDATE publication_jobs SET status='uncertain', error=? WHERE status='submitting'",
                       ('Envio interrompido; conferir a conta antes de qualquer nova tentativa.',))
            db.commit()

    def all(self):
        with self.store._db() as db:
            return [dict(row) for row in db.execute('SELECT * FROM publication_jobs ORDER BY created_at DESC')]

    def get(self, job_id):
        with self.store._db() as db:
            row = db.execute('SELECT * FROM publication_jobs WHERE id=?', (job_id,)).fetchone()
        return dict(row) if row else None

    def status(self):
        counts = {}
        for job in self.all():
            counts[job['status']] = counts.get(job['status'], 0) + 1
        return {'enabled': bool(self.enabled),
                'automatic_enabled': os.getenv('PUBLISHING_AUTO_ENABLED', '0') == '1',
                'daily_limit': self.daily_limit, 'counts': counts,
                'platforms': [{'platform': name, 'connected': bool(connector.connected),
                               'limitations': connector.limitations}
                              for name, connector in self.connectors.items()]}

    def _validate(self, clip_id, automatic):
        clip = self.store.get(clip_id)
        if not clip:
            raise ValueError('Clipe inexistente.')
        if automatic and os.getenv('PUBLISHING_AUTO_ENABLED', '0') != '1':
            raise ValueError('Publicação automática não foi habilitada explicitamente.')
        if clip['status'] not in ({'ready', 'approved'} if automatic else {'approved'}):
            raise ValueError('Clipe precisa de aprovação editorial e MP4 pronto.')
        if clip['rights_status'] not in {'owned', 'permission_granted'}:
            raise ValueError('Fonte sem direitos de publicação registrados.')
        if clip['rights_status'] == 'permission_granted' and len((clip.get('evidence') or '').strip()) < 8:
            raise ValueError('Autorização de terceiros precisa de evidência rastreável.')
        path = Path(clip.get('output_path') or '')
        if path.is_symlink() or not path.is_file() or path.resolve().parent != self.store.output:
            raise ValueError('MP4 validado indisponível no diretório de saída.')
        return path

    def enqueue(self, clip_id, platform, title, description='', scheduled_at=None, automatic=False):
        if not isinstance(automatic, bool) or isinstance(scheduled_at, bool):
            raise ValueError('Modo automático deve ser booleano; agendamento deve ser timestamp.')
        if not isinstance(platform, str) or not isinstance(title, str) or not isinstance(description, str):
            raise ValueError('Plataforma, título e descrição devem ser textos.')
        if platform not in self.connectors or not self.connectors[platform].connected:
            raise ValueError('Plataforma sem credenciais OAuth configuradas ou conector indisponível.')
        title, description = str(title).strip(), str(description).strip()
        if not title or len(title) > 100 or len(description) > 2200:
            raise ValueError('Título obrigatório de até 100 caracteres; descrição até 2200.')
        scheduled = time.time() if scheduled_at is None else float(scheduled_at)
        if not math.isfinite(scheduled) or scheduled < 0:
            raise ValueError('Agendamento inválido; informe segundos Unix UTC.')
        path = self._validate(clip_id, bool(automatic))
        digest = media_digest(path)
        now, job_id = time.time(), uuid.uuid4().hex
        with self.store.lock, self.store._db() as db:
            db.execute('''INSERT OR IGNORE INTO publication_jobs
                (id,clip_id,platform,title,description,media_sha256,status,automatic,
                 scheduled_at,next_attempt_at,created_at,updated_at)
                VALUES (?,?,?,?,?,?,'queued',?,?,?,?,?)''',
                (job_id, clip_id, platform, title, description, digest, int(bool(automatic)),
                 scheduled, scheduled, now, now))
            row = db.execute('''SELECT * FROM publication_jobs WHERE platform=?
                AND (clip_id=? OR media_sha256=?)''', (platform, clip_id, digest)).fetchone()
            db.commit()
        if row['id'] == job_id:
            self._activity(clip_id, 'queued')
        return dict(row)

    def _activity(self, clip_id, status):
        """Mensagens fixas, sem título privado, URL remota ou credenciais."""
        stages = {
            'queued': ('queued', 'Publicação agendada na fila local'),
            'submitting': ('running', 'Enviando mídia; confirmação ainda pendente'),
            'pending': ('waiting', 'Aguardando confirmação da plataforma'),
            'confirmed': ('complete', 'Plataforma confirmou ID; conferir visibilidade no histórico'),
            'uncertain': ('failed', 'Envio incerto; reconciliação necessária, sem repost automático'),
            'blocked': ('blocked', 'Publicação bloqueada; revise direitos e conexão'),
            'failed': ('failed', 'Plataforma informou falha no processamento'),
            'cancelled': ('idle', 'Publicação cancelada antes do envio'),
        }
        if status in stages:
            self.store.activity.append(clip_id, 'publicacao', *stages[status])

    def _update(self, job_id, status, **fields):
        fields.update(status=status, updated_at=time.time())
        allowed = {'status','updated_at','operation_id','remote_id','visibility','error',
                   'poll_attempts','next_attempt_at','submitted_at'}
        if set(fields) - allowed:
            raise ValueError('Campo interno inválido.')
        with self.store.lock, self.store._db() as db:
            db.execute('UPDATE publication_jobs SET ' + ','.join(f'{key}=?' for key in fields) + ' WHERE id=?',
                       (*fields.values(), job_id))
            db.execute('INSERT INTO publication_events(job_id,status,created_at,detail) VALUES (?,?,?,?)',
                       (job_id, status, time.time(), fields.get('error') or ''))
            db.commit()
        job = self.get(job_id)
        if job:
            self._activity(job['clip_id'], status)
        return job

    def cancel(self, job_id):
        with self.store.lock, self.store._db() as db:
            changed = db.execute("UPDATE publication_jobs SET status='cancelled',updated_at=? WHERE id=? AND status='queued'",
                                 (time.time(), job_id)).rowcount
            db.commit()
        if changed:
            self._activity(self.get(job_id)['clip_id'], 'cancelled')
        return bool(changed)

    def process_one(self):
        if not self.enabled or not self._processing.acquire(blocking=False):
            return None
        try:
            now = time.time()
            # Reserva atômica mesmo quando dois serviços compartilham o SQLite.
            with self.store.lock, self.store._db() as db:
                db.execute('BEGIN IMMEDIATE')
                row = db.execute("""SELECT * FROM publication_jobs WHERE status IN ('queued','pending')
                    AND next_attempt_at<=? ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END,created_at LIMIT 1""", (now,)).fetchone()
                if row is None:
                    return None
                job = dict(row)
                if job['status'] == 'queued':
                    used = db.execute('''SELECT COUNT(*) FROM publication_jobs WHERE platform=?
                        AND submitted_at>=?''', (job['platform'], now - 86400)).fetchone()[0]
                    if used >= self.daily_limit:
                        db.execute('UPDATE publication_jobs SET next_attempt_at=? WHERE id=?', (now + 300, job['id']))
                        db.commit()
                        return None
                    db.execute("UPDATE publication_jobs SET status='submitting',submitted_at=? WHERE id=?", (now,job['id']))
                else:
                    # Lease apenas para consultas idempotentes. O reinício mantém pending.
                    db.execute('UPDATE publication_jobs SET next_attempt_at=? WHERE id=?', (now + 120, job['id']))
                db.commit()
            if job['status'] == 'queued':
                self._activity(job['clip_id'], 'submitting')
            connector = self.connectors.get(job['platform'])
            if connector is None or not connector.connected:
                return self._update(job['id'], 'blocked', error='Conta desconectada; reconecte e revise a fila.')
            if job['status'] == 'queued':
                try:
                    path = self._validate(job['clip_id'], job['automatic'])
                    if media_digest(path) != job['media_sha256']:
                        raise ValueError('MP4 mudou após o agendamento; revisão necessária.')
                except (ValueError, OSError) as exc:
                    return self._update(job['id'], 'blocked', error=str(exc))
                try:
                    operation_id = connector.submit(job, path)
                    if not operation_id:
                        raise ValueError('Plataforma não retornou identificador de operação.')
                except Exception:
                    # Não registrar resposta remota: pode conter tokens ou dados privados.
                    return self._update(job['id'], 'uncertain', error='Envio sem confirmação; reconcilie na plataforma. Não reenviado.')
                return self._update(job['id'], 'pending', operation_id=str(operation_id), next_attempt_at=now + 30)
            attempts = job['poll_attempts'] + 1
            try:
                result = connector.check(job['operation_id'])
                if result.get('state') == 'confirmed':
                    if not result.get('remote_id'):
                        return self._update(job['id'], 'uncertain', error='Confirmação sem ID real de publicação.')
                    return self._update(job['id'], 'confirmed', remote_id=str(result['remote_id']),
                                        visibility=result.get('visibility', 'unknown'), error=None)
                if result.get('state') == 'failed':
                    return self._update(job['id'], 'failed', error='Plataforma rejeitou o processamento.')
            except Exception:
                pass
            if attempts >= self.max_polls:
                return self._update(job['id'], 'uncertain', poll_attempts=attempts,
                                    error='Limite de consultas atingido; conferir status na plataforma.')
            return self._update(job['id'], 'pending', poll_attempts=attempts,
                                next_attempt_at=now + min(3600, 30 * (2 ** min(attempts, 7))))
        finally:
            self._processing.release()

    def start(self):
        if not self.enabled or (self._thread and self._thread.is_alive()):
            return
        self._stop.clear()
        def loop():
            while not self._stop.is_set():
                try:
                    self.process_one()
                except Exception:
                    # Falha do worker não apaga trabalhos nem imprime credenciais.
                    pass
                self._stop.wait(10)
        self._thread = threading.Thread(target=loop, name='publication-queue', daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
