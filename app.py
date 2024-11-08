from flask import Flask, render_template, request, redirect, url_for
from werkzeug import secure_filename
import pymongo

COONECTIONS_STRING = "mongodb+srv://User1:ASDFGHJKL@cluster0.lnesjcy.mongodb.net/?retryWrites=true&w=majority"
client = pymongo.MongoClient(COONECTIONS_STRING)
db = client.get_database("school_submission_system")
users_collection = pymongo.collection.Collection(db, "users")

app = Flask(__name__)

# Presmerovanie z koreňovej cesty na prihlasovaciu stránku
@app.route('/')
def home():
    return redirect(url_for('login'))  # Presmerovanie na prihlasovaciu stránku

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']  # Priama hodnota hesla
        name = request.form['name']
        school = request.form['school']  # Získanie vybranej školy
        role = request.form['role']  # Získanie vybranej funkcie
        
        # Uloženie používateľa do databázy
        users_collection.insert_one({
            "name": name,
            "email": email,
            "password": password,  # Uloženie hesla priamo
            "role": role,  # Uloženie vybranej funkcie
            "school": school  # Uloženie vybranej školy
        })
        
        # Presmerovanie na príslušný dashboard na základe vybranej funkcie
        if role == 'student':
            return redirect(url_for('student_dashboard'))
        elif role == 'recenzent':
            return redirect(url_for('recenzent_dashboard'))
        elif role == 'admin':
            return redirect(url_for('admin_dashboard'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']  # Priama hodnota hesla
        
        user = users_collection.find_one({'email': email})
        
        # Porovnanie hesla priamo bez hashovania
        if user and user['password'] == password:
            # Rozlíšenie prihláseného používateľa podľa role
            if user['role'] == 'student':
                return redirect(url_for('student_dashboard'))
            elif user['role'] == 'recenzent':
                return redirect(url_for('recenzent_dashboard'))
            elif user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
        else:
            return 'Nesprávne prihlasovacie údaje!', 401
        
    return render_template('login.html')

# Dashboard pre študenta
@app.route('/student_dashboard')
def student_dashboard():
    return render_template('student_dashboard.html')  # Načítanie šablóny pre študenta

# Dashboard pre recenzenta
@app.route('/recenzent_dashboard')
def recenzent_dashboard():
    return render_template('recenzent_dashboard.html')  # Načítanie šablóny pre recenzenta

# Dashboard pre admina
@app.route('/admin_dashboard')
def admin_dashboard():
    return render_template('admin_dashboard.html')  # Načítanie šablóny pre admina


@app.route('/submission_of_work')
def upload_file():
	return render_template('submission_of_work.html')

@app.route('/uploader', methods = ['GET', 'POST'])
def upload_file():
	if request.method == 'POST':
		file = request.files['file']
		file.save(secure_filename(file.filename))
		return 'File was successfully uploaded.'

if __name__ == '__main__':
    app.run(debug=True)
