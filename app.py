from flask import Flask, render_template, request, redirect
from flask import Response
from flask_pymongo import pymongo
from flask import make_response
from flask_paginate import Pagination, get_page_parameter
import pymongo.collection


COONECTIONS_STRING = "mongodb+srv://User1:ASDFGHJKL@cluster0.lnesjcy.mongodb.net/?retryWrites=true&w=majority"
client = pymongo.MongoClient(COONECTIONS_STRING)
db = client.get_database("school_submission_system")
reviews_collection = pymongo.collection.Collection(db, "reviews")
users_collection = pymongo.collection.Collection(db, "users")
works_collection = pymongo.collection.Collection(db, "works")

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('index.html')  # Uisti sa, že máš index.html v priečinku templates

@app.route('/users', methods=['GET', 'POST'])
def manage_users():
    if request.method == 'POST':
        # Spracovanie registrácie používateľa
        name = request.form['name']
        surname = request.form['surname']
        email = request.form['email']
        password = request.form['password']
        
        # Uloženie do databázy
        users_collection.insert_one({
            "name": name,
            "surname": surname,
            "email": email,
            "password": password  # V reálnom svete by si mal heslo hashovať
        })
        return redirect('/')
    
    # Získanie všetkých používateľov z databázy na zobrazenie
    users = users_collection.find()
    return render_template('users.html', users=users)  # Uisti sa, že máš users.html v priečinku templates

if __name__ == '__main__':
    app.run(debug=True)  # Spustí aplikáciu na localhost:5000
