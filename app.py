import pandas as pd
import os
import io
import uuid
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import pytz

# --- KONFIGURASI APLIKASI ---
app = Flask(__name__)
app.secret_key = 'kunci-rahasia-super-aman-ganti-ini'
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- KONFIGURASI FILE, KOLOM, DAN DATA STATIS ---
JADWAL_FILE_PATH = os.path.join(app.config['UPLOAD_FOLDER'], 'jadwal.xlsx')
USER_DATA_FILE = 'users.csv'

JADWAL_COLUMNS = [
    'ID', 'Dosen', 'Mata Kuliah', 'SKS', 'Kelas', 'Hari', 'Jam Mulai',
    'Jam Selesai', 'Gedung', 'Lantai', 'Ruangan', 'Tipe Kelas'
]

# Data statis untuk tampilan visual, akan selalu ada meskipun excel kosong
RUANGAN_STATIS = [
     'B4A', 'B4B', 'B4C', 'B4D', 'B4E', 'B4F', 'B4G', 'B4H'
]
TIME_SLOTS = [
    "07:00-07:50", "07:50-08:40", "08:40-09:30", "09:30-10:20", "10:20-11:10",
    "11:10-12:00", "12:00-13:00", "13:00-13:50", "13:50-14:40", "14:40-15:30", "15:30-16:20"
]
ISTIRAHAT_SLOTS = ["12:00-13:00"]
DAYS = ["SENIN", "SELASA", "RABU", "KAMIS", "JUMAT", "SABTU"]


# --- FUNGSI HELPER ---

def get_jadwal_data():
    """Membaca data jadwal. Membuat file kosong dengan header jika tidak ada."""
    if not os.path.exists(JADWAL_FILE_PATH):
        pd.DataFrame(columns=JADWAL_COLUMNS).to_excel(JADWAL_FILE_PATH, index=False)
    try:
        df = pd.read_excel(JADWAL_FILE_PATH)
        for col in JADWAL_COLUMNS:
            if col not in df.columns: df[col] = None
        return df
    except Exception:
        return pd.DataFrame(columns=JADWAL_COLUMNS)

def save_jadwal_data(df):
    """Menyimpan DataFrame ke Excel dengan urutan kolom yang benar."""
    df[JADWAL_COLUMNS].to_excel(JADWAL_FILE_PATH, index=False)

def get_user_df():
    """Membaca data pengguna, membuat file jika belum ada."""
    if not os.path.exists(USER_DATA_FILE):
        pd.DataFrame(columns=['username', 'password']).to_csv(USER_DATA_FILE, index=False)
    return pd.read_csv(USER_DATA_FILE)

def save_user_df(df):
    df.to_csv(USER_DATA_FILE, index=False)

def login_required(f):
    """Decorator untuk memastikan pengguna sudah login."""
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash('Anda harus login untuk mengakses halaman ini.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# --- RUTE OTENTIKASI ---
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'username' in session: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username, password = request.form['username'], request.form['password']
        users_df = get_user_df()
        user_data = users_df[users_df['username'] == username]
        if not user_data.empty and check_password_hash(user_data.iloc[0]['password'], password):
            session['username'] = username
            flash('Login berhasil!', 'success')
            return redirect(url_for('dashboard'))
        flash('Username atau password salah.', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'username' in session: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username, password = request.form['username'], request.form['password']
        users_df = get_user_df()
        if not users_df[users_df['username'] == username].empty:
            flash('Username sudah ada, silakan gunakan yang lain.', 'warning')
            return redirect(url_for('register'))
        new_user = pd.DataFrame([{'username': username, 'password': generate_password_hash(password)}])
        save_user_df(pd.concat([users_df, new_user], ignore_index=True))
        flash('Registrasi berhasil! Silakan login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    session.pop('username', None)
    flash('Anda telah berhasil logout.', 'info')
    return redirect(url_for('login'))

# --- RUTE APLIKASI UTAMA ---

@app.route('/dashboard')
@login_required
def dashboard():
    df = get_jadwal_data()
    total_ruangan = len(RUANGAN_STATIS)
    stats = {"total": total_ruangan, "dipakai": 0, "maintenance": 0, "tersedia": total_ruangan}

    if not df.empty:
        # Logika perhitungan status sama seperti sebelumnya
        tz, now = pytz.timezone('Asia/Jakarta'), datetime.now(pytz.timezone('Asia/Jakarta'))
        hari_map = {'MONDAY': 'SENIN', 'TUESDAY': 'SELASA', 'WEDNESDAY': 'RABU', 'THURSDAY': 'KAMIS', 'FRIDAY': 'JUMAT', 'SATURDAY': 'SABTU'}
        hari_ini_id, waktu_sekarang = hari_map.get(now.strftime('%A').upper()), now.strftime('%H:%M')
        jadwal_hari_ini = df[df['Hari'].str.upper() == hari_ini_id]
        ruangan_dipakai, ruangan_maintenance = set(), set()
        for _, row in jadwal_hari_ini.iterrows():
            jam_mulai, jam_selesai = str(row.get('Jam Mulai', '')), str(row.get('Jam Selesai', ''))
            if jam_mulai and jam_selesai and jam_mulai <= waktu_sekarang < jam_selesai:
                if "MAINTENANCE" in str(row.get('Mata Kuliah', '')).upper():
                    ruangan_maintenance.add(row.get('Ruangan'))
                else:
                    ruangan_dipakai.add(row.get('Ruangan'))
        ruangan_dipakai -= ruangan_maintenance
        stats['dipakai'] = len(ruangan_dipakai)
        stats['maintenance'] = len(ruangan_maintenance)
        stats['tersedia'] = total_ruangan - stats['dipakai'] - stats['maintenance']
        
    return render_template('dashboard.html', stats=stats)


@app.route('/jadwal_view')
@login_required
def jadwal_view():
    jadwal_df = get_jadwal_data()
    jadwal_data = jadwal_df.fillna('').to_dict('records')
    return render_template('jadwal_view.html', jadwal_data=jadwal_data, columns=JADWAL_COLUMNS)

@app.route('/ruangan_tersedia')
@login_required
def ruangan_tersedia():
    """Tampilan grid visual, berfungsi bahkan saat data kosong."""
    jadwal_df = get_jadwal_data()
    ruangan_list = RUANGAN_STATIS # Selalu gunakan daftar ruangan statis
    
    # Inisialisasi grid dengan status default "Tersedia"
    schedule_grid = {ruangan: {day: {slot: {"status": "Tersedia", "info": ""} for slot in TIME_SLOTS} for day in DAYS} for ruangan in ruangan_list}
    
    # Selalu tandai slot istirahat
    for ruangan in ruangan_list:
        for day in DAYS:
            for slot in ISTIRAHAT_SLOTS:
                if slot in schedule_grid[ruangan][day]:
                    schedule_grid[ruangan][day][slot] = {"status": "Istirahat", "info": "Waktu Istirahat"}

    # Timpa grid dengan data dari Excel jika ada
    if not jadwal_df.empty:
        for _, row in jadwal_df.iterrows():
            ruangan, hari, jam_mulai, jam_selesai = row.get('Ruangan'), row.get('Hari'), str(row.get('Jam Mulai','')), str(row.get('Jam Selesai',''))
            if not all([ruangan, hari, jam_mulai, jam_selesai]) or pd.isna(ruangan): continue
            
            hari = hari.upper()
            if hari in DAYS and ruangan in ruangan_list:
                for slot in TIME_SLOTS:
                    slot_start, slot_end = slot.split('-')
                    if max(jam_mulai, slot_start) < min(jam_selesai, slot_end):
                        info_text = f"{row.get('Mata Kuliah', '')} - {row.get('Dosen', '')}"
                        status = "Maintenance" if "MAINTENANCE" in str(row.get('Mata Kuliah', '')).upper() else "Dipakai"
                        # Jangan timpa slot istirahat kecuali itu maintenance
                        if schedule_grid[ruangan][hari][slot]['status'] != 'Istirahat' or status == 'Maintenance':
                            schedule_grid[ruangan][hari][slot] = {"status": status, "info": info_text}
            
    return render_template('ruangan_tersedia.html', schedule_grid=schedule_grid, days=DAYS, time_slots=TIME_SLOTS, ruangan_list=ruangan_list)


@app.route('/booking_manual', methods=['GET', 'POST'])
@login_required
def booking_manual():
    if request.method == 'POST':
        df = get_jadwal_data()
        new_booking_data = {col: request.form.get(col) for col in JADWAL_COLUMNS if col != 'ID'}
        new_booking_data['ID'] = uuid.uuid4().hex[:8].upper()
        
        new_booking_df = pd.DataFrame([new_booking_data])
        updated_df = pd.concat([df, new_booking_df], ignore_index=True)
        save_jadwal_data(updated_df)
        
        flash(f"Booking baru dengan ID {new_booking_data['ID']} berhasil ditambahkan!", 'success')
        return redirect(url_for('jadwal_view'))

    return render_template('booking_manual.html', ruangan_list=RUANGAN_STATIS)


@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files or not request.files['file'].filename:
            flash('Tidak ada file yang dipilih.', 'warning')
            return redirect(request.url)
        file = request.files['file']
        if file and file.filename.endswith(('.xlsx', '.xls')):
            file.save(JADWAL_FILE_PATH)
            flash('File jadwal berhasil diunggah dan diperbarui!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Format file tidak valid. Harap unggah file .xlsx atau .xls.', 'danger')
    return render_template('upload.html')


@app.route('/download_excel')
@login_required
def download_excel():
    if not os.path.exists(JADWAL_FILE_PATH) or get_jadwal_data().empty:
        flash('Tidak ada data jadwal untuk diunduh.', 'warning')
        return redirect(url_for('dashboard'))
    return send_file(JADWAL_FILE_PATH, as_attachment=True, download_name='jadwal_terbaru.xlsx')


if __name__ == '__main__':
    app.run(debug=True) 