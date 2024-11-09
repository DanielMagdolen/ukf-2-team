from flask import Flask, render_template, request, redirect, url_for, flash, session
import pymongo
from pymongo import errors
import os
from werkzeug.utils import secure_filename
import datetime

# Konfigurácia pre nahrávanie súborov
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}

COONECTIONS_STRING = "mongodb+srv://User1:ASDFGHJKL@cluster0.lnesjcy.mongodb.net/?retryWrites=true&w=majority"
client = pymongo.MongoClient(COONECTIONS_STRING)
db = client.get_database("school_submission_system")
users_collection = pymongo.collection.Collection(db, "users")
works_collection = pymongo.collection.Collection(db, "works")  # Kolekcia pre práce
reviews_collection = pymongo.collection.Collection(db, "reviews")  # Kolekcia pre recenzie

app = Flask(__name__)
app.secret_key = 'tvoje_tajne_kľúče'  # Potrebné pre session a flash správy
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Vytvorenie unikátneho indexu pre email, ak ešte neexistuje
try:
    users_collection.create_index("email", unique=True)
except errors.OperationFailure:
    pass  # Index už existuje

# Funkcia na kontrolu povolených prípon súborov
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Presmerovanie z koreňovej cesty na prihlasovaciu stránku
@app.route('/')
def home():
    return redirect(url_for('login'))  # Presmerovanie na prihlasovaciu stránku

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        email = request.form['email']
        password = request.form['password']  # Priama hodnota hesla
        school = request.form['school']  # Získanie vybranej školy
        role = request.form['role']  # Získanie vybranej funkcie

        # Kontrola, či emailová adresa už existuje v databáze
        existing_user = users_collection.find_one({'email': email})
        if existing_user:
            flash('Tento email je už zaregistrovaný. Prosím, zadajte iný email.', 'error')  # Zobrazenie chybovej správy
            return redirect(url_for('register'))

        # Uloženie používateľa do databázy
        users_collection.insert_one({
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "password": password,  # Uloženie hesla priamo
            "role": role,  # Uloženie vybranej funkcie
            "school": school  # Uloženie vybranej školy
        })

        flash('Registrácia bola úspešná! Môžete sa prihlásiť.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']  # Priama hodnota hesla

        user = users_collection.find_one({'email': email})

        # Porovnanie hesla priamo bez hashovania
        if user and user['password'] == password:
            # Uloženie informácií o používateľovi do session
            session['user_id'] = str(user['_id'])
            session['email'] = user['email']
            session['role'] = user['role']

            # Rozlíšenie prihláseného používateľa podľa role
            if user['role'] == 'student':
                return redirect(url_for('student_dashboard'))
            elif user['role'] == 'recenzent':
                return redirect(url_for('recenzent_dashboard'))
            elif user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
        else:
            flash('Nesprávne prihlasovacie údaje!', 'error')
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Bol si odhlásený.', 'success')
    return redirect(url_for('login'))

# Dashboard pre študenta
@app.route('/student_dashboard')
def student_dashboard():
    if 'user_id' not in session or session.get('role') != 'student':
        flash('Musíš byť prihlásený ako študent.', 'error')
        return redirect(url_for('login'))

    user_id = session['user_id']
    # Získanie prác nahratých týmto študentom a prevod kurzora na zoznam
    works = list(works_collection.find({'user_id': user_id}))
    return render_template('student_dashboard.html', works=works)

# Dashboard pre recenzenta
@app.route('/recenzent_dashboard')
def recenzent_dashboard():
    if 'user_id' not in session or session.get('role') != 'recenzent':
        flash('Musíš byť prihlásený ako recenzent.', 'error')
        return redirect(url_for('login'))

    return render_template('recenzent_dashboard.html')  # Načítanie šablóny pre recenzenta

# Dashboard pre admina
@app.route('/admin_dashboard')
def admin_dashboard():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Musíš byť prihlásený ako admin.', 'error')
        return redirect(url_for('login'))

    # Získanie všetkých prác bez priradeného recenzenta
    unassigned_works = list(works_collection.find({'recenzent': None}))

    # Získanie všetkých recenzentov
    recenzenti = list(users_collection.find({'role': 'recenzent'}))

    return render_template('admin_dashboard.html', works=unassigned_works, recenzenti=recenzenti)

# Trasa pre pridávanie práce
@app.route('/add_work', methods=['GET', 'POST'])
def add_work():
    if 'user_id' not in session or session.get('role') != 'student':
        flash('Musíš byť prihlásený ako študent.', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        school = request.form['school']
        faculty = request.form['faculty']
        year = request.form['year']
        file = request.files['file']

        if 'file' not in request.files or file.filename == '':
            flash('Nebola vybraná žiadna súbor.', 'error')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # Vytvorenie cesty pre uloženie súboru
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

            # Uloženie informácií o práci do databázy bez priradenia recenzenta
            works_collection.insert_one({
                "user_id": session['user_id'],
                "title": title,
                "description": description,
                "school": school,
                "faculty": faculty,
                "year": year,
                "file_path": file_path,
                "uploaded_at": datetime.datetime.utcnow()
            })

            flash('Práca bola úspešne pridaná!', 'success')
            return redirect(url_for('student_dashboard'))
        else:
            flash('Nepovolený typ súboru. Povolené sú: png, jpg, jpeg, gif, pdf.', 'error')
            return redirect(request.url)

    return render_template('add_work.html')

# Trasa pre priradenie recenzenta (admin)
@app.route('/assign_recenzent/<work_id>/<recenzent_id>', methods=['GET'])
def assign_recenzent(work_id, recenzent_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Musíš byť prihlásený ako admin.', 'error')
        return redirect(url_for('login'))

    # Aktualizácia práce s priradeným recenzentom
    try:
        works_collection.update_one(
            {'_id': pymongo.ObjectId(work_id)},
            {'$set': {'recenzent': recenzent_id}}
        )
        flash('Recenzent bol úspešne priradený.', 'success')
    except Exception as e:
        flash(f'Chyba pri priraďovaní recenzenta: {str(e)}', 'error')

    return redirect(url_for('admin_dashboard'))



if __name__ == '__main__':
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)

    app.run(debug=True)
