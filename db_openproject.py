import os
import psycopg
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(override=True)

OPENPROJECT_DB_NAME = os.getenv('OPENPROJECT_DB_NAME')
OPENPROJECT_DB_USER = os.getenv('OPENPROJECT_DB_USER')
OPENPROJECT_DB_PASS = os.getenv('OPENPROJECT_DB_PASS')
OPENPROJECT_DB_HOST = os.getenv('OPENPROJECT_DB_HOST')
OPENPROJECT_DB_PORT = os.getenv('OPENPROJECT_DB_PORT')

if not OPENPROJECT_DB_NAME or not OPENPROJECT_DB_USER or not OPENPROJECT_DB_PASS or not OPENPROJECT_DB_HOST or not OPENPROJECT_DB_PORT:
    raise ValueError("As variáveis de ambiente OPENPROJECT_DB_NAME, OPENPROJECT_DB_USER, OPENPROJECT_DB_PASS, OPENPROJECT_DB_HOST e OPENPROJECT_DB_PORT devem ser definidas.")

CONNECTION_STRING = f"dbname={OPENPROJECT_DB_NAME} user={OPENPROJECT_DB_USER} password={OPENPROJECT_DB_PASS} host={OPENPROJECT_DB_HOST} port={OPENPROJECT_DB_PORT}"

def get_meetings_by_work_package_id(work_package__id: int):
    try:
        with psycopg.connect(CONNECTION_STRING) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT " \
                                "m.id AS meeting_id, " \
                                "m.title AS meeting_title, " \
                                "m.start_time AS meeting_start_time, " \
                                "m.project_id AS project_id, " \
                                "mai.id AS agenda_item_id, " \
                                "mai.title AS agenda_item_title, " \
                                "m.duration AS meeting_duration " \
                            "FROM " \
                                "meetings m " \
                            "JOIN " \
                                "meeting_agenda_items mai ON m.id = mai.meeting_id " \
                            "WHERE " \
                                "mai.work_package_id = %s " \
                            "ORDER BY " \
                                "m.start_time DESC;",
                            (work_package__id,)
                            )
                
                records = cur.fetchall()
                if not records:
                    print(f"Nenhuma reunião encontrada para o work package {work_package__id}.")
                    return []
                
                meeting_ids = list(set(row[0] for row in records if row[0] is not None))
                participants_by_meeting = {}
                if meeting_ids:
                    cur.execute(
                        "SELECT meeting_id, COALESCE(user_id, id) "
                        "FROM meeting_participants "
                        "WHERE meeting_id = ANY(%s);",
                        (meeting_ids,)
                    )
                    for p_row in cur.fetchall():
                        m_id = p_row[0]
                        u_id = p_row[1]
                        if m_id not in participants_by_meeting:
                            participants_by_meeting[m_id] = []
                        if u_id is not None:
                            participants_by_meeting[m_id].append(u_id)
                
                meetings = []
                for row in records:
                    m_id = row[0]
                    meetings.append({
                        "meeting_id": m_id,
                        "meeting_title": row[1],
                        "meeting_start_time": row[2].isoformat() if isinstance(row[2], datetime) else (str(row[2]) if row[2] else None),
                        "project_id": row[3],
                        "agenda_item_id": row[4],
                        "agenda_item_title": row[5],
                        "participants": participants_by_meeting.get(m_id, []),
                        "meeting_duration": float(row[6]) if row[6] is not None else 0.0,
                        "work_package_id": work_package__id
                    })
                return meetings
                    
    except Exception as error:
        print(f"Error connecting to PostgreSQL: {error}")
        return []

def get_openproject_user(user_id: int, meeting_date, project_id: int = None):
    """
    Retorna o nome do usuário e a taxa horária (rate) vigente na data do meeting.
    """
    if not user_id:
        return None
        
    if isinstance(meeting_date, str):
        meeting_date = datetime.fromisoformat(meeting_date)
        
    try:
        with psycopg.connect(CONNECTION_STRING) as conn:
            with conn.cursor() as cur:
                # 1. Obter o nome do usuário
                cur.execute("SELECT firstname, lastname FROM users WHERE id = %s;", (user_id,))
                user_row = cur.fetchone()
                if not user_row:
                    return None
                    
                name = f"{user_row[0]} {user_row[1]}".strip()
                
                # 2. Obter a taxa horária vigente
                rate = None
                
                # Prioridade 1: Taxa específica por projeto ('HourlyRate')
                if project_id is not None:
                    cur.execute("""
                        SELECT rate FROM rates 
                        WHERE user_id = %s AND project_id = %s AND type = 'HourlyRate' AND valid_from <= %s 
                        ORDER BY valid_from DESC LIMIT 1;
                    """, (user_id, project_id, meeting_date))
                    row = cur.fetchone()
                    if row:
                        rate = float(row[0])
                        
                # Prioridade 2: Taxa padrão do usuário ('DefaultHourlyRate' com project_id IS NULL)
                if rate is None:
                    cur.execute("""
                        SELECT rate FROM rates 
                        WHERE user_id = %s AND project_id IS NULL AND type = 'DefaultHourlyRate' AND valid_from <= %s 
                        ORDER BY valid_from DESC LIMIT 1;
                    """, (user_id, meeting_date))
                    row = cur.fetchone()
                    if row:
                        rate = float(row[0])
                        
                # Prioridade 3: Desabilitada para evitar que participantes sem taxa explícita assumam a taxa padrão global do sistema.
                        
                # Fallback final se nenhuma taxa for cadastrada
                if rate is None:
                    rate = 0.0
                    
                return {
                    "name": name,
                    "rate": rate
                }
    except Exception as error:
        print(f"Error in get_openproject_user: {error}")
        return None

def upsert_cost_rate(project_id: int, rate: float, valid_from) -> int:
    """
    Cadastra ou atualiza o CostRate para o CostType de Taxa Horária (id 4) informando o project_id.
    """
    if isinstance(valid_from, str):
        if 'T' in valid_from:
            dt = datetime.fromisoformat(valid_from)
            valid_from_date = dt.date()
        else:
            valid_from_date = datetime.strptime(valid_from, "%Y-%m-%d").date()
    elif isinstance(valid_from, datetime):
        valid_from_date = valid_from.date()
    else:
        valid_from_date = valid_from

    try:
        with psycopg.connect(CONNECTION_STRING) as conn:
            with conn.cursor() as cur:
                # 1. Verifica se já existe um CostRate para este projeto, cost_type_id = 4 e valid_from correspondente
                cur.execute(
                    "SELECT id FROM rates WHERE project_id = %s AND cost_type_id = 4 AND valid_from = %s AND type = 'CostRate';",
                    (project_id, valid_from_date)
                )
                row = cur.fetchone()
                if row:
                    rate_id = row[0]
                    cur.execute(
                        "UPDATE rates SET rate = %s WHERE id = %s;",
                        (rate, rate_id)
                    )
                else:
                    cur.execute(
                        "INSERT INTO rates (valid_from, rate, type, project_id, user_id, cost_type_id) "
                        "VALUES (%s, %s, 'CostRate', %s, NULL, 4) RETURNING id;",
                        (valid_from_date, rate, project_id)
                    )
                    rate_id = cur.fetchone()[0]
                return rate_id
    except Exception as error:
        print(f"Error in upsert_cost_rate: {error}")
        raise

def insert_cost_entry(
    user_id: int,
    project_id: int,
    work_package_id: int,
    cost_type_id: int,
    units: float,
    spent_on,
    comments: str,
    overridden_costs: float,
    costs: float,
    rate_id: int,
    logged_by_id: int,
    entity_type: str,
    entity_id: int
) -> int:
    """
    Registra um registro na tabela cost_entries com todas as informações requeridas.
    Calcula automaticamente os campos tyear, tmonth e tweek a partir de spent_on.
    """
    if isinstance(spent_on, str):
        if 'T' in spent_on:
            dt = datetime.fromisoformat(spent_on)
            spent_on_date = dt.date()
        else:
            spent_on_date = datetime.strptime(spent_on, "%Y-%m-%d").date()
    elif isinstance(spent_on, datetime):
        spent_on_date = spent_on.date()
    else:
        spent_on_date = spent_on

    tyear = spent_on_date.year
    tmonth = spent_on_date.month
    tweek = spent_on_date.isocalendar()[1]

    try:
        with psycopg.connect(CONNECTION_STRING) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO cost_entries ("
                    "  user_id, project_id, work_package_id, cost_type_id, units, spent_on, comments, "
                    "  overridden_costs, costs, rate_id, logged_by_id, entity_type, entity_id, "
                    "  tyear, tmonth, tweek, blocked, created_at, updated_at"
                    ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "RETURNING id;",
                    (
                        user_id, project_id, work_package_id, cost_type_id, units, spent_on_date, comments,
                        overridden_costs, costs, rate_id, logged_by_id, entity_type, entity_id,
                        tyear, tmonth, tweek, False, datetime.now(), datetime.now()
                    )
                )
                cost_entry_id = cur.fetchone()[0]
                return cost_entry_id
    except Exception as error:
        print(f"Error in insert_cost_entry: {error}")
        raise

def delete_cost_entries_by_work_package_id(work_package_id: int) -> int:
    """
    Remove todos os lançamentos de custo (cost_entries) associados a um determinado pacote de trabalho.
    Retorna o número de linhas removidas.
    """
    try:
        with psycopg.connect(CONNECTION_STRING) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM cost_entries WHERE work_package_id = %s OR (entity_type = 'WorkPackage' AND entity_id = %s);",
                    (work_package_id, work_package_id)
                )
                deleted_rows = cur.rowcount
                return deleted_rows
    except Exception as error:
        print(f"Error in delete_cost_entries_by_work_package_id: {error}")
        raise

def get_all_meetings_with_participants() -> list:
    """
    Retorna todas as reuniões do banco de dados com seus respectivos participantes.
    """
    try:
        with psycopg.connect(CONNECTION_STRING) as conn:
            with conn.cursor() as cur:
                # 1. Busca todas as reuniões
                cur.execute(
                    "SELECT id, title, start_time, duration, project_id, state FROM meetings;"
                )
                meeting_rows = cur.fetchall()
                if not meeting_rows:
                    return []
                
                meeting_ids = [row[0] for row in meeting_rows]
                
                # 2. Busca participantes para essas reuniões
                participants_by_meeting = {}
                if meeting_ids:
                    cur.execute(
                        "SELECT meeting_id, COALESCE(user_id, id) "
                        "FROM meeting_participants "
                        "WHERE meeting_id = ANY(%s);",
                        (meeting_ids,)
                    )
                    for p_row in cur.fetchall():
                        m_id = p_row[0]
                        u_id = p_row[1]
                        if m_id not in participants_by_meeting:
                            participants_by_meeting[m_id] = []
                        if u_id is not None:
                            participants_by_meeting[m_id].append(u_id)
                
                meetings = []
                for row in meeting_rows:
                    m_id = row[0]
                    meetings.append({
                        "meeting_id": m_id,
                        "meeting_title": row[1],
                        "meeting_start_time": row[2].isoformat() if isinstance(row[2], datetime) else (str(row[2]) if row[2] else None),
                        "meeting_duration": float(row[3]) if row[3] is not None else 0.0,
                        "project_id": row[4],
                        "meeting_state": row[5],
                        "participants": participants_by_meeting.get(m_id, [])
                    })
                return meetings
    except Exception as error:
        print(f"Error in get_all_meetings_with_participants: {error}")
        return []

def delete_cost_entries_by_meeting_id(meeting_id: int) -> int:
    """
    Remove todos os lançamentos de custo (cost_entries) associados a uma determinada reunião.
    """
    try:
        with psycopg.connect(CONNECTION_STRING) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM cost_entries WHERE entity_type = 'Meeting' AND entity_id = %s;",
                    (meeting_id,)
                )
                deleted_rows = cur.rowcount
                return deleted_rows
    except Exception as error:
        print(f"Error in delete_cost_entries_by_meeting_id: {error}")
        raise



