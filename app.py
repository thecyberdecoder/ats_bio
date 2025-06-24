import os
import re
import json
import sqlite3
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, send_file
)
import pandas as pd
from fpdf import FPDF

DB_PATH = "db/biodata.db"
FIELDS_PATH = "db/fields.json"
FIELD_MANAGER_PWD = "88888"
MAX_ITEMS = 30

USERS = {
    'chennai.ats@ats.com': {'password': '123456', 'role': 'a', 'prefix': 'Chennai'},
    'madurai.ats@ats.com': {'password': '123456', 'role': 'b', 'prefix': 'Madurai'},
    'coimbatore.ats@ats.com': {'password': '123456', 'role': 'c', 'prefix': 'Coimbatore'},
    'hqrs.ats@ats.com': {'password': '123456', 'role': 'x', 'prefix': 'Headquarters'}
}

app = Flask(__name__)
app.secret_key = "super-secret-key"

def get_fields():
    if os.path.exists(FIELDS_PATH):
        with open(FIELDS_PATH, "r", encoding="utf-8") as f:
            fields = json.load(f)
        return [(re.sub(r'\W', '_', f[0]), f[1]) for f in fields]
    # fallback default
    return [
        ("prefix", "Team Prefix"), ("sno", "S.No"), ("GPF_CPS_No", "GPF/CPS No"), ("IFHRMS_No", "IFHRMS No"),
        ("Salutation", "Salutation"), ("name", "Name"), ("father_name", "Father's Name"), ("dob", "Date of Birth"),
        ("gender", "Gender"), ("Mobile_no", "CUG Mobile No"), ("Email_ID", "Email ID"), ("PAN_No", "PAN No"),
        ("Aadhar_No", "Aadhar No"), ("Designation", "Designation"), ("Marital_Status", "Marital Status"),
        ("Native_Place_District", "Native Place/District"), ("address", "Address"),
        ("Police_Station_Limit", "Police Station Limit"), ("Native_Assembly", "Native Assembly"),
        ("Blood_Group", "Blood Group"), ("Date_of_Entry_into_service", "Date of Entry into service"),
        ("Date_of_Retirement", "Date of Retirement"), ("Appointment_Rank", "Appointment Rank"),
        ("Direct_20_Rank_Promoted_ACP", "Direct/20%/Rank Promoted/ACP"), ("Date_of_Promotion_in_Present_Rank", "Date of Promotion in Present Rank"),
        ("Date_of_Completion_of_Probation", "Date of Completion of Probation"),
        ("Religion_Hindu_Muslim_Christian", "Religion(Hindu/Muslim/Christian)"),
        ("Community_SC_ST_BC_MBC", "Community (SC/ST/BC/MBC)"), ("Caste", "Caste"),
        ("Educational_Qualification", "Educational Qualification"), ("Additional_Technical_Qualification", "Additional/Technical Qualification"),
        ("Languages_Known", "Languages Known"), ("Law_Mark", "Law Mark"), ("Rewards", "Rewards"),
        ("Medals_Received", "Medals Received"), ("Default", "Default"), ("Present_Station", "Present Station"),
        ("Date_of_Relieving_on_Formerly_District_City", "Date of Relieving on Formerly District/City"),
        ("Date_of_Joining_in_ATS", "Date of Joining in ATS"), ("ATS_Unit", "ATS Unit"),
        ("bank", "Bank Name"), ("account", "Account No"), ("ifsc", "IFSC"), ("remarks", "Remarks"),
        ("date_increment", "Date of Increment"), ("notify_days_increment", "Notify Days Before Increment"),
        ("date_superannuation", "Date of Superannuation"), ("notify_days_superannuation", "Notify Days Before Superannuation"),
        ("role", "Role"), ("owner_email", "Owner Email")
    ]

def save_fields(fields):
    os.makedirs(os.path.dirname(FIELDS_PATH), exist_ok=True)
    with open(FIELDS_PATH, "w", encoding="utf-8") as f:
        json.dump([[k, v] for k, v in fields], f, ensure_ascii=False, indent=2)

def is_valid_field_key(key):
    return re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', key) is not None

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    fields = get_fields()
    cols = ', '.join(
        f'"{field}" TEXT' if "date" not in field and "notify" not in field and field not in ("sno", "prefix")
        else (f'"{field}" INTEGER' if "notify" in field or field in ("sno", "prefix") else f'"{field}" TEXT')
        for field, _ in fields
    )
    c.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='biodata'")
    exists = c.fetchone()
    if exists:
        c.execute("PRAGMA table_info(biodata)")
        db_fields = [row[1] for row in c.fetchall()]
        required_fields = [f[0] for f in fields]
        if db_fields[1:] != required_fields:
            c.execute("DROP TABLE biodata")
            conn.commit()
            exists = False
    if not exists:
        c.execute(f'''
            CREATE TABLE IF NOT EXISTS biodata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                {cols}
            )
        ''')
        conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def require_login(func):
    from functools import wraps
    @wraps(func)
    def wrapper(*a, **k):
        if 'user_email' not in session:
            return redirect(url_for('login'))
        return func(*a, **k)
    return wrapper

# FORCE LOGIN FOR ALMOST ALL ROUTES (except login, logout, static, field_manager)
@app.before_request
def require_login_for_all():
    allowed_endpoints = {'login', 'static', 'logout', 'field_manager'}
    if (request.endpoint not in allowed_endpoints
        and not (request.endpoint or '').startswith('static')
        and 'user_email' not in session):
        return redirect(url_for('login'))

init_db()

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_email' in session:
        return redirect(url_for('index'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        pwd = request.form.get('password', '').strip()
        user = USERS.get(email)
        if user and user['password'] == pwd:
            session.clear()
            session['user_email'] = email
            session['user_role'] = user['role']
            session['user_prefix'] = user['prefix']
            flash('Logged in successfully.', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid credentials.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/')
@require_login
def index():
    fields = get_fields()
    conn = get_db_connection()
    user_email = session['user_email']
    user_role = session['user_role']
    search = request.args.get('search', '').strip()
    if user_role == 'x':
        base_query = 'SELECT * FROM biodata'
        params = []
        if search:
            search_fields = [f[0] for f in fields if f[0] != "owner_email"]
            like_expr = ' OR '.join([f'"{field}" LIKE ?' for field in search_fields])
            base_query += f' WHERE {like_expr}'
            params += [f'%{search}%' for _ in search_fields]
    else:
        base_query = 'SELECT * FROM biodata WHERE "owner_email"=?'
        params = [user_email]
        if search:
            search_fields = [f[0] for f in fields if f[0] != "owner_email"]
            like_expr = ' OR '.join([f'"{field}" LIKE ?' for field in search_fields])
            base_query += f' AND ({like_expr})'
            params += [f'%{search}%' for _ in search_fields]
    base_query += ' ORDER BY "sno" ASC'
    entries = conn.execute(base_query, params).fetchall()
    conn.close()
    return render_template('index.html', fields=fields, entries=entries, user_role=user_role, search=search)

@app.route('/add', methods=['GET', 'POST'])
@require_login
def add_entry():
    fields = get_fields()
    if request.method == 'POST':
        values = []
        for field, _ in fields:
            if field == "owner_email":
                values.append(session['user_email'])
            elif field == "role":
                values.append(session['user_role'])
            elif field == "prefix":
                values.append(session['user_prefix'])
            else:
                values.append(request.form.get(field, '').strip())
        name_idx = next((i for i, f in enumerate(fields) if f[0] == 'name'), None)
        if name_idx is not None and not values[name_idx]:
            flash('Name is required.', 'danger')
            return render_template('add_edit.html', fields=fields, action='Add')
        user_role = session['user_role']
        user_email = session['user_email']
        conn = get_db_connection()
        if user_role != 'x':
            count = conn.execute('SELECT COUNT(*) FROM biodata WHERE owner_email=?', (user_email,)).fetchone()[0]
            if count >= MAX_ITEMS:
                conn.close()
                flash(f'Maximum {MAX_ITEMS} entries allowed.', 'warning')
                return render_template('add_edit.html', fields=fields, action='Add')
        placeholders = ', '.join(['?'] * len(fields))
        cols = ', '.join([f'"{f[0]}"' for f in fields])
        conn.execute(f'INSERT INTO biodata ({cols}) VALUES ({placeholders})', values)
        conn.commit()
        conn.close()
        flash('Biodata entry added successfully.', 'success')
        return redirect(url_for('index'))
    return render_template('add_edit.html', fields=fields, action='Add')

@app.route('/edit/<int:entry_id>', methods=['GET', 'POST'])
@require_login
def edit_entry(entry_id):
    fields = get_fields()
    conn = get_db_connection()
    entry = conn.execute('SELECT * FROM biodata WHERE id=?', (entry_id,)).fetchone()
    if not entry:
        conn.close()
        flash('Entry not found.', 'danger')
        return redirect(url_for('index'))
    if session['user_role'] != 'x' and entry['owner_email'] != session['user_email']:
        conn.close()
        flash('Permission denied.', 'danger')
        return redirect(url_for('index'))
    if request.method == 'POST':
        values = []
        for field, _ in fields:
            if field == "owner_email":
                values.append(entry['owner_email'])
            elif field == "role":
                values.append(entry['role'])
            elif field == "prefix":
                values.append(entry['prefix'])
            else:
                values.append(request.form.get(field, '').strip())
        set_clause = ', '.join([f'"{f[0]}"=?' for f in fields])
        conn.execute(f'UPDATE biodata SET {set_clause} WHERE id=?', values + [entry_id])
        conn.commit()
        conn.close()
        flash('Entry updated.', 'success')
        return redirect(url_for('index'))
    entry_values = [entry[field] if field in entry.keys() else '' for field, _ in fields]
    entry_values = (entry_values + [''] * len(fields))[:len(fields)]
    conn.close()
    return render_template('add_edit.html', fields=fields, entry=entry_values, action='Edit')

@app.route('/delete/<int:entry_id>', methods=['POST'])
@require_login
def delete_entry(entry_id):
    conn = get_db_connection()
    entry = conn.execute('SELECT * FROM biodata WHERE id=?', (entry_id,)).fetchone()
    if not entry:
        conn.close()
        flash('Entry not found.', 'danger')
        return redirect(url_for('index'))
    if session['user_role'] != 'x' and entry['owner_email'] != session['user_email']:
        conn.close()
        flash('Permission denied.', 'danger')
        return redirect(url_for('index'))
    conn.execute('DELETE FROM biodata WHERE id=?', (entry_id,))
    conn.commit()
    conn.close()
    flash('Entry deleted.', 'success')
    return redirect(url_for('index'))

@app.route('/export/excel')
@require_login
def export_excel():
    fields = get_fields()
    conn = get_db_connection()
    user_email = session['user_email']
    user_role = session['user_role']
    if user_role == 'x':
        entries = conn.execute('SELECT * FROM biodata ORDER BY id ASC').fetchall()
    else:
        entries = conn.execute('SELECT * FROM biodata WHERE owner_email=? ORDER BY id ASC', (user_email,)).fetchall()
    conn.close()
    data = []
    for row in entries:
        data.append([row[f[0]] for f in fields])
    df = pd.DataFrame(data, columns=[f[1] for f in fields])
    file_path = "biodata_export.xlsx"
    df.to_excel(file_path, index=False)
    return send_file(file_path, as_attachment=True)

@app.route('/export/pdf')
@require_login
def export_pdf():
    fields = get_fields()
    conn = get_db_connection()
    user_email = session['user_email']
    user_role = session['user_role']
    if user_role == 'x':
        entries = conn.execute('SELECT * FROM biodata ORDER BY id ASC').fetchall()
    else:
        entries = conn.execute('SELECT * FROM biodata WHERE owner_email=? ORDER BY id ASC', (user_email,)).fetchall()
    conn.close()
    file_path = "biodata_export.pdf"
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_font("Arial", size=8)
    col_width = 277 / max(1, len(fields))
    row_height = 7
    for _, label in fields:
        pdf.cell(col_width, row_height, str(label), border=1)
    pdf.ln(row_height)
    for row in entries:
        for field, _ in fields:
            val = str(row[field]) if row[field] is not None else ''
            pdf.cell(col_width, row_height, val, border=1)
        pdf.ln(row_height)
    pdf.output(file_path)
    return send_file(file_path, as_attachment=True)

@app.route('/fields', methods=['GET', 'POST'])
def field_manager():
    reserved = {"owner_email", "role", "prefix"}
    unlocked = session.get("fm_unlocked", False)
    if request.method == 'POST':
        if not unlocked:
            pwd = request.form.get('manager_pwd', '')
            if pwd == FIELD_MANAGER_PWD:
                session['fm_unlocked'] = True
                unlocked = True
            else:
                flash("Incorrect Field Manager password.", "danger")
                return render_template('field_manager.html', fields=get_fields(), unlocked=False, reserved=reserved)
        fields = get_fields()
        action = request.form.get('action')
        idx = request.form.get('field_idx')
        key = request.form.get('field_key', '').strip()
        label = request.form.get('field_label', '').strip()
        pos = request.form.get('field_pos')
        # Add at end
        if action == 'add':
            if not key or not label:
                flash("Key and label required.", "danger")
            elif not is_valid_field_key(key):
                flash('Invalid field key. Letters/numbers/underscores, cannot start with digit.', 'danger')
            elif any(key == f[0] for f in fields):
                flash('Duplicate field key.', 'danger')
            else:
                fields.append((key, label))
                save_fields(fields)
                flash("Field added at end.", "success")
        # Insert at position (1-based)
        elif action == 'insert':
            try:
                pos = int(pos)
            except Exception:
                pos = None
            if not key or not label or pos is None:
                flash("Key, label, and position required.", "danger")
            elif not is_valid_field_key(key):
                flash('Invalid field key.', 'danger')
            elif any(key == f[0] for f in fields):
                flash('Duplicate field key.', 'danger')
            elif not (1 <= pos <= len(fields)+1):
                flash('Invalid position.', 'danger')
            else:
                fields.insert(pos-1, (key, label))
                save_fields(fields)
                flash(f"Field inserted at position {pos}.", "success")
        # Rename field label
        elif action == 'rename' and idx is not None:
            idx = int(idx)
            if fields[idx][0] in reserved:
                flash("Cannot rename system field.", "danger")
            else:
                fields[idx] = (fields[idx][0], label)
                save_fields(fields)
                flash("Field label renamed.", "success")
        # Remove field
        elif action == 'remove' and idx is not None:
            idx = int(idx)
            if fields[idx][0] in reserved:
                flash("Cannot remove system field.", "danger")
            else:
                fields.pop(idx)
                save_fields(fields)
                if os.path.exists(DB_PATH):
                    os.remove(DB_PATH)
                flash("Field removed. All biodata deleted (DB reset).", "warning")
        # Move up
        elif action == 'moveup' and idx is not None:
            idx = int(idx)
            if idx > 0:
                fields[idx-1], fields[idx] = fields[idx], fields[idx-1]
                save_fields(fields)
                flash("Field moved up.", "info")
        # Move down
        elif action == 'movedown' and idx is not None:
            idx = int(idx)
            if idx < len(fields)-1:
                fields[idx+1], fields[idx] = fields[idx], fields[idx+1]
                save_fields(fields)
                flash("Field moved down.", "info")
        # Save and restart
        elif action == 'save_and_exit':
            save_fields(fields)
            if os.path.exists(DB_PATH):
                os.remove(DB_PATH)
            session.pop("fm_unlocked", None)
            flash("Fields updated. All biodata deleted. Please reload the application.", "success")
            return redirect(url_for("login"))
        return render_template('field_manager.html', fields=get_fields(), unlocked=True, reserved=reserved)
    session['fm_unlocked'] = False
    return render_template('field_manager.html', fields=get_fields(), unlocked=False, reserved=reserved)

if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0", port=10000)