import os
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, send_from_directory, abort
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# -------------------- App Config --------------------
app = Flask(__name__)
app.config['SECRET_KEY'] = 'change-this-secret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024  # 8 MB
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)

# -------------------- Models --------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='owner')  # 'owner' or 'customer'
    properties = db.relationship('Property', backref='owner', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Property(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    location = db.Column(db.String(200), nullable=False)
    property_type = db.Column(db.String(20), nullable=False)  # 'land' or 'house'
    sale_or_rent = db.Column(db.String(10), nullable=False)   # 'sale' or 'rent'
    price = db.Column(db.Float)   # for sale
    rent = db.Column(db.Float)    # for rent
    area = db.Column(db.Float)    # sq.ft or acres
    rooms = db.Column(db.Integer) # houses only
    contact = db.Column(db.String(120))
    image_filename = db.Column(db.String(255))
    gmap_link = db.Column(db.String(500))  # optional direct Google Maps link
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'))

# -------------------- Helpers --------------------
def current_user():
    uid = session.get('user_id')
    return User.query.get(uid) if uid else None

def login_required():
    if not current_user():
        flash('Please log in first.', 'warning')
        return False
    return True

def save_image(file_storage):
    if not file_storage or file_storage.filename.strip() == "":
        return None
    filename = secure_filename(file_storage.filename)
    base, ext = os.path.splitext(filename)
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    i = 1
    while os.path.exists(path):
        filename = f"{base}_{i}{ext}"
        path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        i += 1
    file_storage.save(path)
    return filename

def build_gmaps_link(location):
    # Safe default link if user didn't paste a direct Google Maps URL
    from urllib.parse import quote_plus
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(location)}"

# -------------------- Routes: Public --------------------
@app.route('/')
def index():
    latest = Property.query.order_by(Property.id.desc()).limit(6).all()
    return render_template('index.html', properties=latest, user=current_user())

@app.route('/properties')
def properties():
    q_location = request.args.get('location', '').strip()
    q_type = request.args.get('type', '')          # land/house
    q_mode = request.args.get('mode', '')          # sale/rent
    q_min_price = request.args.get('min_price', type=float)
    q_max_price = request.args.get('max_price', type=float)
    q_min_rent = request.args.get('min_rent', type=float)
    q_max_rent = request.args.get('max_rent', type=float)
    q_min_area = request.args.get('min_area', type=float)
    q_max_area = request.args.get('max_area', type=float)
    q_rooms = request.args.get('rooms', type=int)

    query = Property.query
    if q_location:
        query = query.filter(Property.location.ilike(f"%{q_location}%"))
    if q_type:
        query = query.filter(Property.property_type == q_type)
    if q_mode:
        query = query.filter(Property.sale_or_rent == q_mode)
    if q_min_price is not None:
        query = query.filter(Property.price >= q_min_price)
    if q_max_price is not None:
        query = query.filter(Property.price <= q_max_price)
    if q_min_rent is not None:
        query = query.filter(Property.rent >= q_min_rent)
    if q_max_rent is not None:
        query = query.filter(Property.rent <= q_max_rent)
    if q_min_area is not None:
        query = query.filter(Property.area >= q_min_area)
    if q_max_area is not None:
        query = query.filter(Property.area <= q_max_area)
    if q_rooms is not None:
        query = query.filter(Property.rooms == q_rooms)

    results = query.order_by(Property.id.desc()).all()
    return render_template('properties.html', properties=results, user=current_user())

@app.route('/property/<int:pid>')
def property_detail(pid):
    p = Property.query.get_or_404(pid)
    return render_template('property_detail.html', property=p, user=current_user())

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# -------------------- Routes: Auth --------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name'].strip()
        email = request.form['email'].strip().lower()
        password = request.form['password']
        role = request.form.get('role', 'owner')
        if not name or not email or not password:
            flash('All fields are required.', 'danger')
            return redirect(url_for('register'))
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'warning')
            return redirect(url_for('register'))
        u = User(name=name, email=email, role=role)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        flash('Registration successful. Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', user=current_user())

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']
        u = User.query.filter_by(email=email).first()
        if not u or not u.check_password(password):
            flash('Invalid email or password.', 'danger')
            return redirect(url_for('login'))
        session['user_id'] = u.id
        flash('Logged in.', 'success')
        return redirect(url_for('index'))
    return render_template('login.html', user=current_user())

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out.', 'info')
    return redirect(url_for('index'))

# -------------------- Routes: Owner CRUD --------------------
@app.route('/add', methods=['GET', 'POST'])
def add_property():
    if not login_required():
        return redirect(url_for('login'))
    if request.method == 'POST':
        title = request.form['title']
        description = request.form.get('description')
        location = request.form['location']
        property_type = request.form['property_type']   # land/house
        sale_or_rent = request.form['sale_or_rent']     # sale/rent
        area = float(request.form['area']) if request.form.get('area') else None
        price = float(request.form['price']) if request.form.get('price') else None
        rent = float(request.form['rent']) if request.form.get('rent') else None
        rooms = int(request.form['rooms']) if request.form.get('rooms') else None
        contact = request.form['contact']
        gmap_link = request.form.get('gmap_link', '').strip()

        if not gmap_link:
            gmap_link = build_gmaps_link(location)

        image_filename = save_image(request.files.get('image'))

        p = Property(
            title=title, description=description, location=location,
            property_type=property_type, sale_or_rent=sale_or_rent,
            area=area, price=price, rent=rent, rooms=rooms,
            contact=contact, image_filename=image_filename,
            gmap_link=gmap_link, owner_id=current_user().id
        )
        db.session.add(p)
        db.session.commit()
        flash('Property added!', 'success')
        return redirect(url_for('properties'))
    return render_template('add_property.html', user=current_user())

@app.route('/edit/<int:pid>', methods=['GET', 'POST'])
def edit_property(pid):
    if not login_required():
        return redirect(url_for('login'))
    p = Property.query.get_or_404(pid)
    # Only owner can edit
    if p.owner_id != current_user().id:
        abort(403)
    if request.method == 'POST':
        p.title = request.form['title']
        p.description = request.form.get('description')
        p.location = request.form['location']
        p.property_type = request.form['property_type']
        p.sale_or_rent = request.form['sale_or_rent']
        p.area = float(request.form['area']) if request.form.get('area') else None
        p.price = float(request.form['price']) if request.form.get('price') else None
        p.rent = float(request.form['rent']) if request.form.get('rent') else None
        p.rooms = int(request.form['rooms']) if request.form.get('rooms') else None
        p.contact = request.form['contact']
        gmap_link = request.form.get('gmap_link', '').strip()
        p.gmap_link = gmap_link or build_gmaps_link(p.location)

        img = request.files.get('image')
        if img and img.filename.strip():
            p.image_filename = save_image(img)

        db.session.commit()
        flash('Property updated!', 'success')
        return redirect(url_for('property_detail', pid=p.id))
    return render_template('edit_property.html', property=p, user=current_user())

@app.route('/delete/<int:pid>', methods=['POST'])
def delete_property(pid):
    if not login_required():
        return redirect(url_for('login'))
    p = Property.query.get_or_404(pid)
    if p.owner_id != current_user().id:
        abort(403)
    # delete image file if exists
    if p.image_filename:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], p.image_filename))
        except OSError:
            pass
    db.session.delete(p)
    db.session.commit()
    flash('Property deleted.', 'danger')
    return redirect(url_for('properties'))

# -------------------- Init DB & Run --------------------
def init_db():
    with app.app_context():
        db.create_all()
        if not User.query.first():
            demo = User(name='Demo Owner', email='owner@example.com', role='owner')
            demo.set_password('demo123')
            db.session.add(demo)
            db.session.commit()

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False, port=3000)

