from flask import Flask, render_template, request, redirect, url_for, flash, session
import pymongo
from pymongo import errors
from bson import ObjectId
import os
from werkzeug.utils import secure_filename
import datetime
import logging

# Configuration settings for file upload and MongoDB connection
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx'}  # Allowed attachments are PDF and Word documents
CONNECTION_STRING = "mongodb+srv://User1:ASDFGHJKL@cluster0.lnesjcy.mongodb.net/?retryWrites=true&w=majority"

# Initialize Flask and MongoDB
app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Required for sessions and flash messages
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

client = pymongo.MongoClient(CONNECTION_STRING)
db = client["school_submission_system"]
users_collection = db["users"]
works_collection = db["works"]
reviews_collection = db["reviews"]
conferences_collection = db["conferenc"]  # Correct collection name as 'conferenc'

# Ensure email uniqueness in the users collection
try:
    users_collection.create_index("email", unique=True)
except errors.OperationFailure:
    pass  # Ignore if index already exists

# Utility Functions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def is_logged_in(role=None):
    """Check if user is logged in, optionally check for specific role."""
    if 'user_id' not in session:
        flash('You must be logged in to access this page.', 'error')
        return False
    if role and session.get('role') != role:
        flash(f'You must be logged in as {role}.', 'error')
        return False
    return True

@app.route('/')
def index():
    return redirect(url_for('first_page'))  # Ensure this redirects to the first_page

@app.route('/first_page')
def first_page():
    conferences = list(conferences_collection.find().sort("date", 1))  # Fetching conferences
    return render_template('first_page.html', conferences=conferences)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        surname = request.form['surname']
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        school = request.form['school']
        role = request.form['role']

        # Check if email already exists
        if users_collection.find_one({'email': email}):
            flash('This email is already registered. Please use a different email.', 'error')
            return redirect(url_for('register'))

        # Save user to the database
        users_collection.insert_one({
            "surname": surname,
            "name": name,
            "email": email,
            "password": password,
            "role": role,
            "school": school
        })

        flash('Registration successful! You can now log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = users_collection.find_one({'email': email})

        if user and user['password'] == password:
            session['user_id'] = str(user['_id'])
            session['email'] = user['email']
            session['role'] = user['role']
            return redirect(url_for('view_conferences'))  # Zmenené na 'first_page'
        
        flash('Incorrect login details!', 'error')
        return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

@app.route('/view_conferences')
def view_conferences():
    if 'user_id' not in session:
        flash('You must be logged in to access this page.', 'error')
        return redirect(url_for('login'))

    conferences = list(conferences_collection.find().sort("date", 1))  # Načítanie konferencií
    return render_template('view_conferences.html', conferences=conferences)

@app.route('/student_dashboard')
def student_dashboard():
    if not is_logged_in('student'):
        return redirect(url_for('login'))

    # Získame ID používateľa
    user_id = ObjectId(session['user_id'])

    # Skontroluj, či je vybraná konferencia
    if 'current_conference_id' not in session:
        flash('Please select a conference to enter.', 'error')
        return redirect(url_for('view_conferences'))  # Ak nie je vybraná konferencia, presmerujeme na výber konferencie

    # Získaj ID aktuálnej konferencie
    conference_id = session['current_conference_id']

    # Získaj všetky práce používateľa pre konkrétnu konferenciu
    works = list(works_collection.find({'user_id': user_id, 'conference_id': ObjectId(conference_id)}))

    # Vráť dashboard s prácami
    return render_template('student_dashboard.html', works=works)
@app.route('/recenzent_dashboard')
def recenzent_dashboard():
    if not is_logged_in('recenzent'):
        return redirect(url_for('login'))

    # Získame ID recenzenta z relácie
    reviewer_id = ObjectId(session['user_id'])

    # Skontrolujeme, či je recenzent prihlásený do konferencie
    if 'current_conference_id' not in session:
        flash('Please select a conference to view your assigned works.', 'error')
        return redirect(url_for('view_conferences'))

    # Získame ID aktuálnej konferencie
    conference_id = session['current_conference_id']

    # Získame priradené práce pre recenzenta v tejto konferencii
    works = list(works_collection.find({
        'recenzent': reviewer_id,  # Priradený recenzent
        'conference_id': ObjectId(conference_id)  # Konferencia, kde je práca priradená
    }))

    # Zobrazíme stránku s priradenými prácami
    return render_template('recenzent_dashboard.html', works=works)




@app.route('/admin_dashboard', methods=['GET'])
def admin_dashboard():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('You must be logged in as an admin.', 'error')
        return redirect(url_for('login'))

    # Načítanie konferencií, študentov a recenzentov pre dropdown menu
    conferences = list(conferences_collection.find().sort("date", 1))  # Zmena na 'conference'
    students = list(users_collection.find({"role": "student"}))
    reviewers = list(users_collection.find({"role": "recenzent"}))
    for conference in conferences:
        conference["_id"] = str(conference["_id"])
    for student in students:
        student["_id"] = str(student["_id"])
    for reviewer in reviewers:
        reviewer["_id"] = str(reviewer["_id"])

    # Získanie vybraného študenta a recenzenta z URL parametrov
    selected_student_id = request.args.get('student_id')
    selected_reviewer_id = request.args.get('reviewer_id')

    # Ak nie je žiadny filter, použije sa prázdny objekt pre vyhľadávanie všetkých prác
    query = {"conference_id": ObjectId(session['current_conference_id'])}

    # Filtrovanie podľa študenta, ak je zadané
    if selected_student_id:
        query['user_id'] = ObjectId(selected_student_id)

    # Filtrovanie podľa recenzenta, ak je zadané
    if selected_reviewer_id:
        query['recenzent'] = ObjectId(selected_reviewer_id)

    # Načítanie prác podľa filtrovaného dotazu
    works = list(works_collection.find(query))

    # Načítanie mena študenta, recenzenta a názvu konferencie pre každú prácu
    for work in works:
        # Meno študenta
        user = users_collection.find_one({"_id": ObjectId(work.get("user_id"))})
        work["full_name"] = f"{user.get('surname', '')} {user.get('name', '')}".strip() if user else "Neznámy"

        # Meno recenzenta
        reviewer = users_collection.find_one({"_id": ObjectId(work.get("recenzent"))}) if work.get("recenzent") else None
        work["reviewer_name"] = f"{reviewer.get('surname', '')} {reviewer.get('name', '')}".strip() if reviewer else "Nepriradený"

        # Názov konferencie
        conference = conferences_collection.find_one({"_id": ObjectId(work.get("conference_id"))})  # Zmena na 'conference'
        work["conference_name"] = conference["name"] if conference else "Nepriradená konferencia"

    return render_template(
        'admin_dashboard.html',
        works=works,
        conferences=conferences,
        students=students,
        reviewers=reviewers,
        selected_student_id=selected_student_id,
        selected_reviewer_id=selected_reviewer_id
    )




@app.route('/assign_recenzent', methods=['GET', 'POST'])
def assign_recenzent():
    if not is_logged_in('admin'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Získaj ID práce a ID recenzenta z formulára
        work_id = request.form.get('work_id')
        reviewer_id = request.form.get('reviewer_id')

        if not work_id or not reviewer_id:
            flash('Please select both a work and a reviewer.', 'error')
            return redirect(url_for('admin_dashboard'))

        try:
            # Aktualizuj prácu, priraď recenzenta
            works_collection.update_one(
                {"_id": ObjectId(work_id)},
                {"$set": {"recenzent": ObjectId(reviewer_id)}}
            )
            flash('Reviewer successfully assigned!', 'success')
        except Exception as e:
            flash('Error assigning reviewer.', 'error')
            logging.error(f"Error assigning reviewer: {e}")

        return redirect(url_for('admin_dashboard'))

    # Načítanie všetkých prác a recenzentov (na testovanie GET metódy)
    works = list(works_collection.find())
    reviewers = list(users_collection.find({"role": "recenzent"}))

    return render_template('assign_recenzent.html', works=works, reviewers=reviewers)

    # Get student's name for each work
    for work in works:
        try:
            # Find user by user_id
            user = users_collection.find_one({"_id": ObjectId(work["user_id"])})

            if user:
                full_name = f"{user.get('surname', '')} {user.get('name', '')}"
                work["full_name"] = full_name.strip()  # Remove extra spaces
            else:
                work["full_name"] = "Unknown"
        except Exception as e:
            logging.error(f"Error retrieving user for work {work['_id']}: {e}")
            work["full_name"] = "Unknown"

    if not works:
        flash('No works have been added.', 'error')

    return render_template('admin_dashboard.html', works=works)

  
@app.route('/add_work', methods=['GET', 'POST'])
def add_work():
    if 'user_id' not in session or session.get('role') != 'student':
        flash('You must be logged in as a student.', 'error')
        return redirect(url_for('login'))

    # Získanie aktuálnej konferencie zo session
    current_conference_id = session.get('current_conference_id')

    if not current_conference_id:
        flash('You must be enrolled in a conference first.', 'error')
        return redirect(url_for('view_conferences'))  # Ak nie je vybraná konferencia, presmeruj na výber

    if request.method == 'POST':
        # Získanie údajov z formulára
        title = request.form.get('title')
        description = request.form.get('description')
        school = request.form.get('school')
        faculty = request.form.get('faculty')
        year = request.form.get('year')
        conference_id = current_conference_id  # Automaticky vyplnená konferencia zo session
        file = request.files.get('file')

        # Validácia súboru
        if not file or not allowed_file(file.filename):
            flash('Invalid or missing file. Allowed types: pdf, doc, docx', 'error')
            return redirect(url_for('add_work'))

        try:
            # Uloženie súboru na server
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

            # Vloženie práce do databázy vrátane conference_id
            works_collection.insert_one({
                "user_id": ObjectId(session['user_id']),
                "conference_id": ObjectId(conference_id),  # Prepojenie s konferenciou
                "title": title,
                "description": description,
                "school": school,
                "faculty": faculty,
                "year": year,
                "file_path": file_path,
                "uploaded_at": datetime.datetime.utcnow()
            })

            flash('Work has been successfully added to the selected conference!', 'success')
            return redirect(url_for('student_dashboard'))

        except Exception as e:
            logging.error(f"Error adding work: {e}")
            flash('An error occurred while adding your work. Please try again later.', 'error')
            return redirect(url_for('add_work'))

    # Získanie informácií o konferencii zo session pre predvyplnenie
    conferences = list(conferences_collection.find({"_id": ObjectId(current_conference_id)}))
    if not conferences:
        flash('No conferences available to add work to.', 'error')
        return redirect(url_for('student_dashboard'))

    return render_template('add_work.html', conferences=conferences, selected_conference_id=current_conference_id)


@app.route('/add_review', methods=['GET', 'POST'])
def add_review():
    if 'user_id' not in session or session.get('role') != 'reviewer':
        flash('You must be logged in as a reviewer.', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        file = request.files.get('file')
        decision = request.form.get('decision')

        if not work_id:
            flash('Vyberte prácu.', 'error')
            return redirect(url_for('recenzent_dashboard'))
            
        if not file or not allowed_file(file.filename):
            flash('Neplatný alebo chýbajúci súbor. Podporované formáty: pdf, doc, docx', 'error')
            return redirect(url_for('add_review'))

        try:
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
        
            reviews_collection.insert_one({
                "user_id": ObjectId(session['user_id']),
                "work_id": ObjectId(work_id),
                "file_path": file_path,
                "decision": form.request['decision'],
                "uploaded_at": datetime.datetime.utcnow()
            })

            flash('Posudok bol úspešne pridaný k práci!', 'success')
            return redirect(url_for('recenzent_dashboard'))

        except Exception as e:
            logging.error(f"Error adding review: {e}")
            flash('Nastala chyba pri pridávaní vášho posudku. Skúste, prosím, opäť neskôr.', 'error')
            return redirect(url_for('add_review'))

    conferences = list(conferences_collection.find().sort("date", 1))
    if not conferences:
        flash('Nie sú dostupné konferencie pre pridanie posudku.', 'error')
        return redirect(url_for('recenzent_dashboard'))

    return render_template('add_review.html', conferences = conferences)

@app.route('/enter_conference/<conference_id>', methods=['POST'])
def enter_conference(conference_id):
    if 'user_id' not in session:
        flash('You must be logged in to enter a conference.', 'error')
        return redirect(url_for('login'))

    conference = conferences_collection.find_one({"_id": ObjectId(conference_id)})
    if not conference:
        flash('Conference not found.', 'error')
        return redirect(url_for('view_conferences'))

    # Save conference info in session
    session['current_conference_id'] = str(conference['_id'])
    session['current_conference_name'] = conference['name']

    # Redirect based on user role
    role = session['role']
    if role == 'student':
        return redirect(url_for('student_dashboard'))
    elif role == 'recenzent':
        return redirect(url_for('recenzent_dashboard'))
    elif role == 'admin':
        return redirect(url_for('admin_dashboard'))
    else:
        flash('Unknown role.', 'error')
        return redirect(url_for('view_conferences'))

if __name__ == '__main__':
    app.run(debug=True)
