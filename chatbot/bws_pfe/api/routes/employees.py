import json
import logging
from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from api.db     import get_engine
from api.models import EmployeeCreate, EmployeeUpdate, EmployeeOut, AVAILABLE_MODULES

router = APIRouter(prefix='/employees', tags=['employees'])
log    = logging.getLogger('aria.api')


def _row_to_dict(row) -> dict:
    modules = row.allowed_modules
    if isinstance(modules, str):
        modules = json.loads(modules)
    return {
        'id'             : row.id,
        'user_id'        : row.user_id,
        'name'           : row.name,
        'allowed_modules': modules or [],
        'is_admin'       : bool(row.is_admin),
        'created_at'     : str(row.created_at),
        'updated_at'     : str(row.updated_at),
    }


def _engine():
    """Retourne le moteur DB ou lève HTTP 503 si indisponible."""
    engine = get_engine()
    if engine is None:
        raise HTTPException(503, 'Base de données non disponible.')
    return engine


def _validate_modules(modules: list):
    """Vérifie que tous les modules demandés sont dans la liste autorisée."""
    invalid = [m for m in modules if m not in AVAILABLE_MODULES]
    if invalid:
        raise HTTPException(422, f'Modules invalides : {invalid}. Disponibles : {AVAILABLE_MODULES}')


@router.get('', response_model=list[EmployeeOut])
def list_employees():
    with _engine().connect() as conn:
        rows = conn.execute(
            text('SELECT * FROM aria_employees ORDER BY name')
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


@router.get('/modules', response_model=list[str])
def list_modules():
    return AVAILABLE_MODULES


@router.get('/{user_id}', response_model=EmployeeOut)
def get_employee(user_id: str):
    with _engine().connect() as conn:
        row = conn.execute(
            text('SELECT * FROM aria_employees WHERE user_id = :uid'),
            {'uid': user_id}
        ).fetchone()
    if row is None:
        raise HTTPException(404, f'Employé "{user_id}" introuvable.')
    return _row_to_dict(row)


@router.post('', response_model=EmployeeOut, status_code=201)
def create_employee(body: EmployeeCreate):
    _validate_modules(body.allowed_modules)

    engine = _engine()
    with engine.connect() as conn:
        if conn.execute(
            text('SELECT id FROM aria_employees WHERE user_id = :uid'),
            {'uid': body.user_id}
        ).fetchone():
            raise HTTPException(409, f'Employé "{body.user_id}" existe déjà.')

        conn.execute(
            text('INSERT INTO aria_employees (user_id, name, allowed_modules, is_admin) '
                 'VALUES (:uid, :name, :modules, :admin)'),
            {
                'uid'    : body.user_id,
                'name'   : body.name,
                'modules': json.dumps(body.allowed_modules, ensure_ascii=False),
                'admin'  : int(body.is_admin),
            }
        )
        conn.commit()
        row = conn.execute(
            text('SELECT * FROM aria_employees WHERE user_id = :uid'),
            {'uid': body.user_id}
        ).fetchone()

    log.info(f'[EMPLOYEE] Créé : {body.user_id} | modules={body.allowed_modules}')
    return _row_to_dict(row)


@router.put('/{user_id}', response_model=EmployeeOut)
def update_employee(user_id: str, body: EmployeeUpdate):
    if body.allowed_modules is not None:
        _validate_modules(body.allowed_modules)

    engine = _engine()
    with engine.connect() as conn:
        if conn.execute(
            text('SELECT id FROM aria_employees WHERE user_id = :uid'),
            {'uid': user_id}
        ).fetchone() is None:
            raise HTTPException(404, f'Employé "{user_id}" introuvable.')

        fields, params = [], {'uid': user_id}
        if body.name is not None:
            fields.append('name = :name')
            params['name'] = body.name
        if body.allowed_modules is not None:
            fields.append('allowed_modules = :modules')
            params['modules'] = json.dumps(body.allowed_modules, ensure_ascii=False)
        if body.is_admin is not None:
            fields.append('is_admin = :admin')
            params['admin'] = int(body.is_admin)

        if fields:
            conn.execute(
                text(f'UPDATE aria_employees SET {", ".join(fields)} WHERE user_id = :uid'),
                params
            )
            conn.commit()

        row = conn.execute(
            text('SELECT * FROM aria_employees WHERE user_id = :uid'),
            {'uid': user_id}
        ).fetchone()

    log.info(f'[EMPLOYEE] Mis à jour : {user_id}')
    return _row_to_dict(row)


@router.delete('/{user_id}', status_code=204)
def delete_employee(user_id: str):
    engine = _engine()
    with engine.connect() as conn:
        result = conn.execute(
            text('DELETE FROM aria_employees WHERE user_id = :uid'),
            {'uid': user_id}
        )
        conn.commit()
    if result.rowcount == 0:
        raise HTTPException(404, f'Employé "{user_id}" introuvable.')
    log.info(f'[EMPLOYEE] Supprimé : {user_id}')
