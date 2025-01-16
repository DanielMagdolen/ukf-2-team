from flask import Flask, render_template, request, redirect, url_for, flash, session
import pymongo
from pymongo import errors
from bson import ObjectId
import os
from werkzeug.utils import secure_filename
import logging
from bson import ObjectId
from flask import flash, redirect, url_for
from datetime import datetime



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
roles_collection = db["roles"]
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


def is_logged_in():
    """ Skontrolovanie, či je používateľ prihlásený. """
    if 'user_id' not in session:
        flash("Pre prístup na túto stránku sa musíte prihlásiť.", "error")
        return False
    return True

@app.route('/')
def index():
    return redirect(url_for('first_page'))  # Ensure this redirects to the first_page

@app.route('/first_page')
def first_page():
    conferences = list(conferences_collection.find().sort("date", 1))  # Fetching conferences
    return render_template('first_page.html', conferences=conferences)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = users_collection.find_one({'email': email})

        if user and user['password'] == password:
            session['user_id'] = str(user['_id'])
            session['email'] = user['email']
            return redirect(url_for('view_conferences')) 
        
        flash("Boli zadané nesprávne prihlasovacie údaje.", "error")
        return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("Boli ste odhlásený/á.", "success")
    return redirect(url_for('login'))

@app.route('/visitor_page')
def visitor_page():
    conferences = list(conferences_collection.find().sort("date", 1)) # Načítanie konferencií
    return render_template('visitor_page.html', conferences = conferences)

@app.route('/view_conferences')
def view_conferences():
    if 'user_id' not in session:
        flash("Pre prístup na túto stránku sa musíte prihlásiť.", "error")
        return redirect(url_for('login'))

    # Získanie aktuálnej role z databázy
    role_entry = roles_collection.find_one({
        "user_id": ObjectId(session['user_id'])
    })

    if role_entry:
        session['role'] = role_entry['role']
    else:
        session['role'] = 'visitor'

    conferences = list(conferences_collection.find().sort("date", 1))  # Načítanie konferencií
    return render_template('view_conferences.html', conferences=conferences)



@app.route('/student_dashboard')
def student_dashboard():
    if 'user_id' not in session or ((session.get('role') != 'student') and (session.get('role') != 'recenzent,student')):
        return redirect(url_for('login'))

    user_id = ObjectId(session['user_id'])

    if 'current_conference_id' not in session:
        flash("Vyberte si, prosím, konferenciu, do ktorej chcete vstúpiť.", "error")
        return redirect(url_for('view_conferences'))

    conference_id = ObjectId(session['current_conference_id'])

    # Načítanie dátumu konferencie
    conference = conferences_collection.find_one({'_id': conference_id})
    conference_date = conference.get('date')  # Predpokladáme, že 'date' je uložené ako datetime objekt

    # Načítanie prác pre daného študenta a konferenciu
    works = list(works_collection.find({'user_id': user_id, 'conference_id': conference_id}))

    # Prepojenie posudkov k prácam
    for work in works:
        review = reviews_collection.find_one({'work_id': work['_id']})

        if review:
            work['review'] = review['decision']
        else:
            work['review'] = None

    # Pridanie informácie o možnosti editácie
    current_date = datetime.now()
    is_editable = current_date < conference_date

    return render_template('student_dashboard.html', works=works, is_editable=is_editable)


@app.route('/edit_work_stud/<work_id>', methods=['GET', 'POST'])
def edit_work_stud(work_id):
    if 'user_id' not in session or session.get('role') not in ['recenzent', 'recenzent,student', 'student']:
        flash("Musíte byť prihlásený/á ako recenzent alebo študent.", "error")
        return redirect(url_for('login'))

    # Načítanie práce zozbieranej podľa work_id
    work = works_collection.find_one({"_id": ObjectId(work_id)})
    
    if not work:
        flash("Práca neexistuje.", "error")
        return redirect(url_for('rec_stud_dashboard'))  # Ak práca neexistuje, vráť sa na dashboard

    if request.method == 'POST':
        # Spracovanie formulára na editovanie práce
        work_data = {
            'title': request.form['title'],
            'description': request.form['description'],
            'school': request.form['school'],
            'faculty': request.form['faculty'],
            # ďalšie údaje...
        }

        # Uloženie zmien do databázy
        works_collection.update_one({"_id": ObjectId(work_id)}, {"$set": work_data})

        # Presmerovanie na správny dashboard podľa roly
        if 'recenzent' in session['role']:
            return redirect(url_for('rec_stud_dashboard'))  # Ak je recenzent, presmerovať na rec_stud_dashboard
        else:
            return redirect(url_for('student_dashboard'))  # Ak je študent, presmerovať na student_dashboard

    # Ak je metóda GET, zobrazí sa formulár na editovanie
    return render_template('edit_work_stud.html', work=work)


@app.route('/delete_work_stud/<work_id>', methods=['POST'])
def delete_work_stud(work_id):
    if 'user_id' not in session or ((session.get('role') != 'student') and (session.get('role') != 'recenzent,student')):
        return redirect(url_for('login'))

    work = works_collection.find_one({'_id': ObjectId(work_id), 'user_id': ObjectId(session['user_id'])})

    if not work:
        flash("Práca nebola nájdená alebo nemáte povolenie ju odstrániť.", "error")
        return redirect(url_for('student_dashboard'))

    works_collection.delete_one({'_id': ObjectId(work_id)})
    flash("Práca bola úspešne odstránená.", "success")
    return redirect(url_for('student_dashboard'))





@app.route('/recenzent_dashboard')
def recenzent_dashboard():
    if 'user_id' not in session or ((session.get('role') != 'recenzent') and (session.get('role') != 'recenzent,student')):
        return redirect(url_for('login'))

    # Získame ID recenzenta z relácie
    reviewer_id = ObjectId(session['user_id'])

    # Skontrolujeme, či je recenzent prihlásený do konferencie
    if 'current_conference_id' not in session:
        flash("Vyberte si, prosím, konferenciu na zobrazenie vašich priradených prác.", "error")
        return redirect(url_for('view_conferences'))

    # Získame ID aktuálnej konferencie
    conference_id = session['current_conference_id']

    # Získame priradené práce pre recenzenta v tejto konferencii
    works = list(works_collection.find({
        'recenzent': ObjectId(reviewer_id),  # Priradený recenzent
        'conference_id': ObjectId(conference_id)  # Konferencia, kde je práca priradená
    }))

    # Načítame posudky pre každú prácu a pridáme ich k práci
    for work in works:
        # Získame posudok pre túto prácu
        review = reviews_collection.find_one({'work_id': work['_id']})

        # Ak posudok existuje, pripojíme ho k práci
        if review:
            work['review'] = review['decision']  # Tu môžeš pridať ďalšie detaily, ak sú potrebné
            work['review_id'] = review['_id']  # Pridáme ID posudku, ak ho chceš zobraziť neskôr
        else:
            work['review'] = None  # Ak posudok neexistuje

        # Získame používateľa (študenta) podľa user_id
        student = users_collection.find_one({"_id": ObjectId(work['user_id'])})
        if student:
            work['student_name'] = f"{student['surname']} {student['name']}"
        else:
            work['student_name'] = "Neznámy študent"

    # Zobrazíme stránku s priradenými prácami
    return render_template('recenzent_dashboard.html', works=works)



@app.route('/delete_work/<work_id>', methods=['POST'])
def delete_work(work_id):
    if 'user_id' not in session or session['role'] != 'admin':
        flash('Nemáte oprávnenie na vymazanie práce.', 'error')
        return redirect(url_for('admin_dashboard'))

    # Vymazanie práce z databázy
    result = works_collection.delete_one({'_id': ObjectId(work_id)})
    if result.deleted_count > 0:
        flash("Práca bola úspešne vymazaná.", "success")
    else:
        flash("Práca nebola nájdená.", "error")

    return redirect(url_for('admin_dashboard'))

@app.route('/edit_work/<work_id>', methods=['GET', 'POST'])
def edit_work(work_id):
    # Skontrolovanie, či je používateľ prihlásený a má rolu 'admin'
    if 'user_id' not in session or session.get('role') != 'admin':
        flash("Nemáte oprávnenie na úpravu tejto práce.", "error")
        return redirect(url_for('admin_dashboard'))

    # Zaistíme, že work_id je validný ObjectId
    try:
        work = works_collection.find_one({"_id": ObjectId(work_id)})
    except Exception as e:
        flash("Neplatný ID formát.", "error")
        return redirect(url_for('admin_dashboard'))

    if not work:
        flash("Práca nebola nájdená.", "danger")
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        # Získame dáta z formulára a vykonáme úpravy
        title = request.form['title']
        description = request.form['description']
        # Môžete pridať ďalšie polia podľa potreby

        # Aktualizujeme prácu v databáze
        try:
            works_collection.update_one(
                {"_id": ObjectId(work_id)},
                {"$set": {"title": title, "description": description}}
            )
            flash("Práca bola úspešne upravená.", "success")
            return redirect(url_for('admin_dashboard'))  # Presmerujeme späť na dashboard
        except Exception as e:
            flash("Nastala chyba pri ukladaní zmien.", "danger")
            return redirect(url_for('edit_work', work_id=work_id))  # Zostaneme na tej istej stránke v prípade chyby

    # Ak je požiadavka GET, zobrazíme formulár pre úpravu
    return render_template('edit_work.html', work=work)




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
        flash("Neboli pridané žiadne práce.", "error")

    return render_template('admin_dashboard.html', works=works)

@app.route('/add_work', methods=['GET', 'POST'])
def add_work():
    if 'user_id' not in session or ((session.get('role') != 'student') and (session.get('role') != 'recenzent,student')):
        flash("Musíte byť prihlásený/á ako študent.", "error")
        return redirect(url_for('login'))

    current_conference_id = session.get('current_conference_id')

    if not current_conference_id:
        flash("Najprv je potrebné vybrať si konferenciu.", "error")
        return redirect(url_for('view_conferences'))

    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        school = request.form.get('school')
        faculty = request.form.get('faculty')
        year = request.form.get('year')
        conference_id = current_conference_id
        file = request.files.get('file')

        if not file or not allowed_file(file.filename):
            flash("Neplatný alebo chýbajúci súbor. Povolené formáty: pdf, doc, docx", "error")
            return redirect(url_for('add_work'))

        try:
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

            works_collection.insert_one({
                "user_id": ObjectId(session['user_id']),
                "conference_id": ObjectId(conference_id),
                "title": title,
                "description": description,
                "school": school,
                "faculty": faculty,
                "year": year,
                "file_path": file_path,
                "uploaded_at": datetime.utcnow()
            })

            flash("Práca bola úspešne pridaná do vybranej konferencie.", "success")
            
            # Presmerovanie na správny dashboard podľa role
            if session.get('role') == 'recenzent,student':
                return redirect(url_for('rec_stud_dashboard'))
            else:
                return redirect(url_for('student_dashboard'))

        except Exception as e:
            logging.error(f"Error adding work: {e}")
            flash("Nastala chyba pri pridávaní vašej práce. Skúste, prosím, opäť neskôr.", "error")
            return redirect(url_for('add_work'))

    conferences = list(conferences_collection.find({"_id": ObjectId(current_conference_id)}))
    if not conferences:
        flash("Nie sú dostupné konferencie, do ktorých by sa dala pridať práca.", "error")
        return redirect(url_for('student_dashboard'))

    conference_name = conferences[0]['name'] if conferences else 'Unknown Conference'

    return render_template('add_work.html', conferences=conferences, selected_conference_id=current_conference_id, conference_name=conference_name)



























@app.route('/view_review/<work_id>', methods=['GET'])
def view_review(work_id):
    if 'user_id' not in session or ((session.get('role') != 'student') and (session.get('role') != 'recenzent,student')):
        flash("Musíte byť prihlásený/á ako študent.", "error")
        return redirect(url_for('login'))

    # Získame detail práce podľa ID
    work = works_collection.find_one({'_id': ObjectId(work_id)})
    if not work:
        flash("Práca neexistuje.", "error")
        return redirect(url_for('student_dashboard'))  # Ak práca neexistuje, presmerujeme na dashboard

    # Overenie prístupových práv
    if str(work['user_id']) != str(session['user_id']):
        flash("Nemáte prístup k tomuto posudku.", "error")
        return redirect(url_for('student_dashboard'))

    # Získame posudok pre danú prácu
    review = reviews_collection.find_one({'work_id': ObjectId(work_id)})

    if review:
        work['review'] = review  # Ak existuje posudok, pripojíme ho k práci
    else:
        work['review'] = None  # Ak posudok neexistuje, nastavíme hodnotu na None

    return render_template('view_review.html', work=work, review=review)

@app.route('/view_review_student/<work_id>', methods=['GET'])
def view_review_student(work_id):
    if 'user_id' not in session:
        flash("Musíte byť prihlásený/á.", "error")
        return redirect(url_for('login'))

    # Získame informácie o práci
    work = works_collection.find_one({'_id': ObjectId(work_id)})
    if not work:
        flash("Práca neexistuje.", "error")
        return redirect(url_for('student_dashboard'))  # Ak práca neexistuje, presmerujeme na dashboard

    # Overíme, že tento študent má právo vidieť tento posudok
    if str(work['user_id']) != str(session['user_id']):
        flash("Nemáte prístup k tomuto posudku.", "error")
        return redirect(url_for('student_dashboard'))

    # Získame posudok pre danú prácu
    review = reviews_collection.find_one({'work_id': ObjectId(work_id)})

    if review:
        work['review'] = review
    else:
        work['review'] = None  # Ak posudok neexistuje

    return render_template('view_review_student.html', work=work, review=review)


@app.route('/view_review_admin/<work_id>', methods=['GET'])
def view_review_admin(work_id):
    if 'user_id' not in session:
        flash("Musíte byť prihlásený/á.", "error")
        return redirect(url_for('login'))

    # Skontrolujeme, či je prihlásený používateľ administrátor (predpokladajme, že používateľ má atribút 'role')
    user = users_collection.find_one({'_id': ObjectId(session['user_id'])})
    if not user or user['role'] != 'admin':
        flash("Nemáte prístup k tomuto posudku.", "error")
        return redirect(url_for('admin_dashboard'))  # Ak nie je administrátor, presmerujeme na admin dashboard

    # Získanie detailov o práci
    work = works_collection.find_one({'_id': ObjectId(work_id)})
    if not work:
        flash("Práca neexistuje.", "error")
        return redirect(url_for('admin_dashboard'))  # Ak práca neexistuje, presmerujeme na dashboard

    # Získanie posudku k práci
    review = reviews_collection.find_one({'work_id': ObjectId(work_id)})

    if review:
        work['review'] = review
    else:
        work['review'] = None  # Ak posudok neexistuje, zobrazíme None

    # Ak je recenzent priradený k posudku, získať údaje o recenzentovi
    reviewer = None
    if review and review.get('user_id'):
        reviewer = users_collection.find_one({'_id': ObjectId(review['user_id'])})

    return render_template('view_review_admin.html', work=work, review=review, reviewer=reviewer)

@app.route('/view_review_recenzent/<work_id>', methods=['GET'])
def view_review_recenzent(work_id):
    if 'user_id' not in session:
        flash("Musíte byť prihlásený/á.", "error")
        return redirect(url_for('login'))

    # Získame informácie o práci
    work = works_collection.find_one({'_id': ObjectId(work_id)})
    if not work:
        flash("Práca neexistuje.", "error")
        return redirect(url_for('recenzent_dashboard'))  # Ak práca neexistuje, presmerujeme na dashboard

    # Skontrolujeme, že recenzent je priradený k tejto práci
    reviewer_id = str(session['user_id'])
    if 'recenzent' not in work or str(work['recenzent']) != reviewer_id:
        flash("Nemáte prístup k tomuto posudku.", "error")
        return redirect(url_for('recenzent_dashboard'))

    # Získame posudok pre danú prácu
    review = reviews_collection.find_one({'work_id': ObjectId(work_id)})

    if review:
        work['review'] = review
    else:
        work['review'] = None  # Ak posudok neexistuje

    return render_template('view_review_recenzent.html', work=work, review=review)







@app.route('/create_conference', methods=['GET', 'POST'])
def create_conference():
    if request.method == 'POST':
        # Načítanie údajov z formulára
        name = request.form['name']
        date = datetime.strptime(request.form['date'], '%Y-%m-%d')  # Konvertovanie dátumu
        description = request.form['description']

        # Uloženie konferencie do databázy
        new_conference = {
            'name': name,
            'date': date,
            'description': description
        }
        conferences_collection.insert_one(new_conference)

        flash("Konferencia bola úspešne vytvorená.", "success")
        return redirect(url_for('view_conferences'))

    return render_template('create_conference.html')

@app.route('/delete_conference/<conference_id>', methods=['POST'])
def delete_conference(conference_id):
    if 'user_id' not in session or session['role'] != 'admin':
        flash("Nemáte oprávnenie na vymazanie konferencie.", "error")
        return redirect(url_for('view_conferences'))

    # Vymazanie konferencie z databázy
    conferences_collection.delete_one({'_id': ObjectId(conference_id)})

    flash("Konferencia bola úspešne vymazaná.", "success")
    return redirect(url_for('view_conferences'))



# Trasa na načítanie konferencie na úpravu
@app.route('/edit_conference/<conference_id>', methods=['GET'])
def edit_conference(conference_id):
    if 'user_id' not in session or session['role'] != 'admin':
        flash("Nemáte oprávnenie na úpravu konferencie.", "error")
        return redirect(url_for('view_conferences'))

    # Načítanie konferencie z databázy
    conference = conferences_collection.find_one({'_id': ObjectId(conference_id)})
    if not conference:
        flash("Konferencia nebola nájdená.", "error")
        return redirect(url_for('view_conferences'))

    return render_template('edit_conference.html', conference=conference)

# Trasa na spracovanie aktualizácie konferencie
@app.route('/update_conference/<conference_id>', methods=['POST'])
def update_conference(conference_id):
    if 'user_id' not in session or session['role'] != 'admin':
        flash("Nemáte oprávnenie na úpravu konferencie.", "error")
        return redirect(url_for('view_conferences'))

    # Získanie údajov z formulára
    name = request.form['name']
    description = request.form['description']
    date = datetime.strptime(request.form['date'], '%Y-%m-%d')

    # Aktualizácia konferencie v databáze
    conferences_collection.update_one(
        {'_id': ObjectId(conference_id)},
        {'$set': {'name': name, 'description': description, 'date': date}}
    )

    flash("Konferencia bola úspešne upravená.", "success")
    return redirect(url_for('view_conferences'))

@app.route('/enter_conference/<conference_id>', methods=['POST'])
def enter_conference(conference_id):
    if 'user_id' not in session:
        flash("Musíte sa prihlásiť, aby ste vedeli vstúpiť do konferencie.", "error")
        return redirect(url_for('login'))

    conference = conferences_collection.find_one({"_id": ObjectId(conference_id)})
    if not conference:
        flash("Konferencia nebola nájdená.", "error")
        return redirect(url_for('view_conferences'))

    session['current_conference_id'] = str(conference['_id'])
    session['current_conference_name'] = conference['name']

    roles = roles_collection.find({
        "conference_id": ObjectId(session['current_conference_id']),
        "user_id": ObjectId(session['user_id'])
    })

    roles_list = [role['role'] for role in roles]
    current_role = "visitor"  # Predvolená rola

    if "admin" in roles_list:
        current_role = "admin"
    elif "recenzent,student" in roles_list:
        current_role = "recenzent,student"
    elif "student" in roles_list:
        current_role = "student"
    elif "recenzent" in roles_list:
        current_role = "recenzent"

    session['role'] = current_role

    # Presmerovanie na základe aktuálnej role
    if current_role == "visitor":
        return redirect(url_for('visitor_page'))
    elif current_role == "student":
        return redirect(url_for('student_dashboard'))
    elif current_role == "recenzent":
        return redirect(url_for('recenzent_dashboard'))
    elif current_role == "recenzent,student":
        return redirect(url_for('rec_stud_dashboard'))
    elif current_role == "admin":
        return redirect(url_for('admin_dashboard'))
    else:
        flash("Neznáma rola.", "error")
        return redirect(url_for('view_conferences'))



@app.route('/rec_stud_dashboard')
def rec_stud_dashboard():
    if 'user_id' not in session or session.get('role') not in ['recenzent', 'recenzent,student']:
        flash("Musíte byť prihlásený/á ako recenzent alebo študent.", "error")
        return redirect(url_for('login'))

    user_id = ObjectId(session['user_id'])
    conference_id = ObjectId(session['current_conference_id'])

    if not conference_id:
        flash("Nie je vybraná žiadna konferencia.", "error")
        return redirect(url_for('view_conferences'))

    # Načítanie dátumu konferencie
    conference = conferences_collection.find_one({'_id': conference_id})
    conference_date = conference.get('date')  # Predpokladáme, že 'date' je uložené ako datetime objekt

    # Načítanie prác priradených recenzentovi
    reviewer_works = list(works_collection.find({
        "recenzent": user_id,
        "conference_id": conference_id
    }))

    # Načítanie prác nahraných študentom
    student_works = list(works_collection.find({
        "user_id": user_id,
        "conference_id": conference_id
    }))

    # Prepojenie posudkov a údajov o študentoch pre recenzentské práce
    for work in reviewer_works:
        review = reviews_collection.find_one({'work_id': work['_id']})
        work['review'] = review['decision'] if review else None
        student = users_collection.find_one({"_id": work['user_id']})
        work['student_name'] = f"{student['surname']} {student['name']}" if student else "Neznámy študent"

    # Pridanie informácie o možnosti editácie pre študentské práce
    current_date = datetime.now()
    is_editable = current_date < conference_date if conference_date else False

    return render_template('rec_stud_dashboard.html',
                           student_works=student_works,
                           reviewer_works=reviewer_works,
                           is_editable=is_editable)






def get_reviewers_for_conference(conference_id):
    # Získame používateľov s roľou recenzenta alebo recenzenta a študenta v danej konferencii
    reviewers = db.roles.find({
        "conference_id": ObjectId(conference_id),
        "role": {"$in": ["recenzent", "recenzent,student"]}
    })
    
    # Získame list používateľov
    reviewer_ids = [r['user_id'] for r in reviewers]
    
    # Získame podrobnosti o týchto používateľoch
    users = db.users.find({"_id": {"$in": reviewer_ids}})
    
    return users
@app.route('/assign_recenzent/<work_id>', methods=['GET', 'POST'])
def assign_recenzent(work_id):
    # Skontrolujeme, či je prihlásený admin
    if 'user_id' not in session or session.get('role') != 'admin':
        flash("Musíte byť prihlásený/á ako admin.", "error")
        return redirect(url_for('login'))

    # Načítame prácu podľa work_id
    work = works_collection.find_one({'_id': ObjectId(work_id)})
    if not work:
        flash("Práca so zadaným ID neexistuje.", "error")
        return redirect(url_for('admin_dashboard'))

    # Načítame všetkých recenzentov z kolekcie roles
    reviewers = roles_collection.find({
        'role': {'$in': ['recenzent', 'recenzent,student']}
    })

    # Pre každý recenzent získaj meno a priezvisko z kolekcie users
    reviewer_data = []
    seen_reviewers = set()  # Na sledovanie už pridaných recenzentov

    for reviewer in reviewers:
        user_id = reviewer['user_id']
        
        # Skontroluj, či už tento recenzent bol pridaný
        if user_id not in seen_reviewers:
            user = users_collection.find_one({'_id': user_id})
            if user:
                reviewer_data.append({
                    'user_id': user_id,
                    'name': user.get('name', 'N/A'),
                    'surname': user.get('surname', 'N/A')
                })
                seen_reviewers.add(user_id)  # Pridaj recenzenta do množiny

    # Ak je to POST požiadavka, spracujeme formulár
    if request.method == 'POST':
        reviewer_id = request.form.get('reviewer_id')

        # Skontrolujeme, či je vybrané ID recenzenta
        if not reviewer_id:
            flash("Vyberte, prosím, recenzenta.", "error")
            return redirect(url_for('assign_recenzent', work_id=work_id))

        # Uložíme recenzenta k práci
        result = works_collection.update_one(
            {'_id': ObjectId(work_id)},
            {'$set': {'recenzent': ObjectId(reviewer_id)}}
        )

        if result.modified_count > 0:
            flash("Recenzent bol úspešne priradený k práci.", "success")
        else:
            flash("Nastala chyba pri priraďovaní recenzenta.", "error")

        return redirect(url_for('admin_dashboard'))

    # Ak je to GET požiadavka, zobrazíme stránku
    return render_template('assign_recenzent.html', work=work, reviewers=reviewer_data)













@app.route('/admin_dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    # Skontrolujeme, či je používateľ prihlásený a má rolu admin
    if 'user_id' not in session or session.get('role') != 'admin':
        flash("Musíte byť prihlásený/á ako admin.", "error")
        return redirect(url_for('login'))

    # Získame hodnoty zo žiadosti (query params)
    selected_student_id = request.args.get('student_id')
    selected_reviewer_id = request.args.get('reviewer_id')

    # Načítanie konferencií
    conferences = list(conferences_collection.find().sort("date", 1))

    # Načítanie všetkých používateľov podľa konferencie z kolekcie roles
    roles = list(roles_collection.find({
        "conference_id": ObjectId(session['current_conference_id']),
    }))

    user_ids = [role["user_id"] for role in roles]
    users = list(users_collection.find({"_id": {"$in": user_ids}}))

    # Rozdelenie na študentov a recenzentov
    students = []
    reviewers = []
    for user in users:
        user_roles = [role['role'] for role in roles if role['user_id'] == user['_id']]
        user['is_student'] = any('student' in role for role in user_roles)
        if user['is_student']:
            students.append(user)
        if any(role in ['recenzent', 'recenzent,student'] for role in user_roles):
            reviewers.append(user)

    # Načítanie prác
    query = {"conference_id": ObjectId(session['current_conference_id'])}
    if selected_student_id:
        query['user_id'] = ObjectId(selected_student_id)
    if selected_reviewer_id:
        query['recenzent'] = ObjectId(selected_reviewer_id)

    works = list(works_collection.find(query))
    
    for work in works:
        user = users_collection.find_one({"_id": ObjectId(work.get("user_id"))})
        work["full_name"] = f"{user.get('surname', '')} {user.get('name', '')}".strip() if user else "Neznámy"
        reviewer = users_collection.find_one({"_id": ObjectId(work.get("recenzent"))}) if work.get("recenzent") else None
        work["reviewer_name"] = f"{reviewer.get('surname', '')} {reviewer.get('name', '')}".strip() if reviewer else "Nepriradený"
        conference = conferences_collection.find_one({"_id": ObjectId(work.get("conference_id"))})
        work["conference_name"] = conference["name"] if conference else "Nepriradená konferencia"
        review = reviews_collection.find_one({"work_id": work['_id']})
        work["review"] = review['decision'] if review else "Posudok nebol pridaný"

    return render_template(
        'admin_dashboard.html',
        works=works,
        conferences=conferences,
        students=students,
        reviewers=reviewers,
        selected_student_id=selected_student_id,
        selected_reviewer_id=selected_reviewer_id
    )


















@app.route("/view_users_roles/<conference_id>", methods=["GET", "POST"])
def view_users_roles(conference_id):
    try:
        # Načítavame roly pre danú konferenciu
        roles = roles_collection.find({"conference_id": ObjectId(conference_id)})
        
        # Načítavame používateľov podľa user_id
        users = {
            str(user["_id"]): {
                "name": user["name"],
                "surname": user["surname"]
            } for user in users_collection.find()
        }
        
        # Prevod na zoznam, pridané meno a priezvisko používateľa
        roles_info = []
        for role in roles:
            user_info = users.get(str(role["user_id"]), {"name": "Neznámy", "surname": "Používateľ"})
            roles_info.append({
                "user_id": str(role["user_id"]),
                "role": role["role"],
                "user_name": user_info["name"],
                "user_surname": user_info["surname"]
            })

        # Výpis záznamov priamo do konzoly
        for role in roles_info:
            print(f"Načítaná rola pre šablónu: {role}")
        
        if request.method == "POST":
            user_id = request.form["user_id"]
            new_role = request.form["role"]
            # Aktualizujeme rolu používateľa
            roles_collection.update_one(
                {"user_id": ObjectId(user_id), "conference_id": ObjectId(conference_id)},
                {"$set": {"role": new_role}}
            )
            return redirect(request.url)

        # Odovzdávame dáta do šablóny
        return render_template("view_users_roles.html", roles_info=roles_info)

    except Exception as e:
        return f"Chyba pri načítavaní rolí: {str(e)}"




@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Získame údaje z formulára
        surname = request.form['surname']
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']  # Heslo bez hashovania
        school = request.form['school']

        # Vytvorenie nového používateľa
        new_user = {
            'surname': surname,
            'name': name,
            'email': email,
            'password': password,  # Uložíme heslo ako bolo zadané
            'school': school
        }

        # Uložíme používateľa do kolekcie users
        result = users_collection.insert_one(new_user)
        user_id = result.inserted_id

        # Získame všetky konferencie, do ktorých priradíme používateľa ako "visitor"
        conferences = conferences_collection.find()

        # Pre každú konferenciu vytvoríme záznam v kolekcii roles
        for conference in conferences:
            role_document = {
                'conference_id': conference['_id'],
                'user_id': ObjectId(user_id),
                'role': 'visitor'
            }
            roles_collection.insert_one(role_document)

        # Po registrácii môžeme pridať používateľa do session, ak je to potrebné
        session['user_id'] = str(user_id)
        session['role'] = 'visitor'

        flash('Registrácia bola úspešná, môžete sa prihlásiť.', 'success')
        return redirect(url_for('login'))  # Po registrácii presmeruj na prihlásenie

    return render_template('register.html')


@app.route('/view_review_rec_stud/<work_id>', methods=['GET'])
def view_review_rec_stud(work_id):
    try:
        # Skontrolujeme, či je používateľ prihlásený
        if 'user_id' not in session:
            flash("Musíte byť prihlásený/á.", "error")
            return redirect(url_for('login'))

        # Získame informácie o práci
        work = works_collection.find_one({"_id": ObjectId(work_id)})
        if not work:
            flash("Práca neexistuje.", "error")
            return redirect(url_for('rec_stud_dashboard'))  # Ak práca neexistuje, presmerujeme na dashboard

        # Skontrolujeme, akú rolu má používateľ
        user_role = session.get('role')

        # Ak má používateľ rolu "recenzent", skontrolujeme, či je priradený k tejto práci
        if 'recenzent' in user_role:
            reviewer_id = str(session['user_id'])
            if 'recenzent' not in work or str(work['recenzent']) != reviewer_id:
                flash("Nemáte prístup k tomuto posudku.", "error")
                return redirect(url_for('rec_stud_dashboard'))  # Ak recenzent nie je priradený, presmerujeme

        # Získame posudok pre danú prácu
        review = reviews_collection.find_one({'work_id': ObjectId(work_id), 'user_id': ObjectId(session['user_id'])})

        if review:
            work['review'] = review
        else:
            work['review'] = None  # Ak posudok neexistuje

        # Rozhodneme, ktorú šablónu zobraziť podľa roly používateľa
        if 'recenzent' in user_role:
            return render_template('view_review_recenzent.html', work=work, review=review)
        elif 'recenzent,student' in user_role:
            return render_template('view_review_rec_stud.html', work=work, review=review)

    except Exception as e:
        logging.error(f"Chyba pri načítaní posudku: {e}")
        flash("Nastala chyba pri načítaní posudku. Skúste to znova.", "error")
        return redirect(url_for('rec_stud_dashboard'))



# Funkcia pre presmerovanie na stránku s posudkom
@app.route('/review_redirect/<work_id>', methods=['POST'])
def review_redirect(work_id):
    try:
        # Overenie, či je používateľ prihlásený a má rolu recenzenta alebo recenzenta-študenta
        if 'user_id' not in session or (session.get('role') not in ['recenzent', 'recenzent,student']):
            flash("Musíte byť prihlásený/á ako recenzent.", "error")
            return redirect(url_for('login'))

        # Načítanie posudku pre aktuálneho používateľa
        existing_review = reviews_collection.find_one({
            "user_id": ObjectId(session['user_id']),
            "work_id": ObjectId(work_id)
        })

        if existing_review:
            if 'recenzent' in session['role']:
                return redirect(url_for('view_review_recenzent', work_id=work_id))
            elif 'recenzent,student' in session['role']:
                return redirect(url_for('view_review_rec_stud', work_id=work_id))

        return redirect(url_for('add_review', work_id=work_id))

    except Exception as e:
        logging.error(f"Error in review_redirect: {e}")
        flash("Nastala chyba pri spracovaní požiadavky. Skúste to znova.", "error")
        return redirect(url_for('recenzent_dashboard'))


@app.route('/add_review/<work_id>', methods=['GET', 'POST'])
def add_review(work_id):
    # Logovanie hodnoty roly
    print(f"User role: {session.get('role')}")

    # Overenie, či je používateľ prihlásený a má rolu recenzenta alebo recenzenta,študenta
    if 'user_id' not in session or (session.get('role') not in ['recenzent', 'recenzent,student']):
        flash("Musíte byť prihlásený/á ako recenzent.", "error")
        return redirect(url_for('login'))

    # Načítanie práce podľa ID
    work = works_collection.find_one({'_id': ObjectId(work_id)})
    if not work:
        flash("Práca neexistuje.", "error")
        return redirect(url_for('recenzent_dashboard'))

    # Načítanie posudku pre aktuálneho recenzenta a prácu
    existing_review = reviews_collection.find_one({
        "user_id": ObjectId(session['user_id']),
        "work_id": ObjectId(work_id)
    })

    # Ak už existuje posudok, zobrazí sa iba posudok
    if existing_review:
        return render_template('view_review.html', review=existing_review, work=work)

    # Spracovanie formulára (POST žiadosť)
    if request.method == 'POST':
        file = request.files.get('file')
        decision = request.form.get('decision')

        # Overenie, či bol nahraný súbor
        if not file or not allowed_file(file.filename):
            flash("Neplatný alebo chýbajúci súbor. Povolené formáty: pdf, doc, docx", "error")
            return redirect(url_for('add_review', work_id=work_id))

        try:
            # Uloženie súboru na server
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

            # Uloženie posudku do databázy
            review_data = {
                "user_id": ObjectId(session['user_id']),  # ID recenzenta
                "work_id": ObjectId(work_id),  # ID priradenej práce
                "goal": request.form['goal'],
                "methodology": request.form['methodology'],
                "results": request.form['results'],
                "practical_value": request.form['practical_value'],
                "grammar": request.form['grammar'],
                "structure": request.form['structure'],
                "citations": request.form['citations'],
                "decision": decision,  # Záverečné rozhodnutie
                "file_path": file_path,  # Cesta k súboru
                "uploaded_at": datetime.utcnow()  # Čas nahratia
            }

            # Uloženie posudku do databázy
            reviews_collection.insert_one(review_data)

            flash("Posudok bol úspešne pridaný k práci.", "success")
            return redirect(url_for('recenzent_dashboard'))

        except Exception as e:
            logging.error(f"Error adding review: {e}")
            flash("Nastala chyba pri pridávaní vášho posudku. Skúste, prosím, opäť neskôr.", "error")
            return redirect(url_for('add_review', work_id=work_id))

    # Zobrazenie formulára na pridanie posudku (GET žiadosť)
    return render_template('add_review.html', work=work)





if __name__ == '__main__':
    app.run(debug=True)
