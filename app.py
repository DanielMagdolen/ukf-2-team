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
conferences_collection = db["conferenc"]  # Assuming you have a collection for conferences

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
    return redirect(url_for('view_conferences'))  # Redirect to view_conferences route

@app.route('/view_conferences')
def view_conferences():
    conferences = list(conferences_collection.find().sort("date", 1))  # Sort by date
    if not conferences:
        flash('No conferences found.', 'error')
    return render_template('view_conferences.html', conferences=conferences)



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
            return redirect(url_for(f"{user['role']}_dashboard"))
        
        flash('Incorrect login details!', 'error')
        return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

@app.route('/student_dashboard')
def student_dashboard():
    if not is_logged_in('student'):
        return redirect(url_for('login'))

    user_id = ObjectId(session['user_id'])
    works = list(works_collection.find({'user_id': user_id}))
    return render_template('student_dashboard.html', works=works)

@app.route('/recenzent_dashboard')
def recenzent_dashboard():
    if not is_logged_in('recenzent'):
        return redirect(url_for('login'))

    return render_template('recenzent_dashboard.html')

@app.route('/admin_dashboard')
def admin_dashboard():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('You must be logged in as an admin.', 'error')
        return redirect(url_for('login'))

    # Get all works submitted by students
    works = list(works_collection.find())

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

@app.route('/assign_recenzent/<work_id>', methods=['POST'])
def assign_recenzent(work_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('You must be logged in as an admin.', 'error')
        return redirect(url_for('login'))

    # Get recenzent_id from the form
    recenzent_id = request.form.get('recenzent_id')

    if not recenzent_id:
        flash('Please select a reviewer.', 'error')
        return redirect(url_for('admin_dashboard'))

    try:
        # Update work in the database with the reviewer
        works_collection.update_one(
            {"_id": ObjectId(work_id)},
            {"$set": {"recenzent": ObjectId(recenzent_id)}}
        )

        flash('Reviewer has been successfully assigned to the work.', 'success')
        return redirect(url_for('admin_dashboard'))

    except Exception as e:
        logging.error(f"Error assigning reviewer: {e}")
        flash('Error assigning reviewer. Please try again.', 'error')
        return redirect(url_for('admin_dashboard'))

@app.route('/add_work', methods=['GET', 'POST'])
def add_work():
    if 'user_id' not in session or session.get('role') != 'student':
        flash('You must be logged in as a student.', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Get form data
        title = request.form.get('title')
        description = request.form.get('description')
        school = request.form.get('school')
        faculty = request.form.get('faculty')
        year = request.form.get('year')
        file = request.files.get('file')

        if not file or not allowed_file(file.filename):
            flash('Invalid or missing file. Allowed types: pdf, doc, docx', 'error')
            return redirect(url_for('add_work'))

        try:
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

            works_collection.insert_one({
                "user_id": ObjectId(session['user_id']),
                "title": title,
                "description": description,
                "school": school,
                "faculty": faculty,
                "year": year,
                "file_path": file_path,
                "uploaded_at": datetime.datetime.utcnow()
            })

            flash('Work has been successfully added!', 'success')
            return redirect(url_for('student_dashboard'))

        except Exception as e:
            logging.error(f"Error adding work: {e}")
            flash('An error occurred while adding your work. Please try again later.', 'error')
            return redirect(url_for('add_work'))

    return render_template('add_work.html')

# Create upload folder if it does not exist and start the app
if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    app.run(debug=True)
