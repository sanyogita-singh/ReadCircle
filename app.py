\
import os
import uuid
from datetime import datetime
from collections import defaultdict
from flask_migrate import Migrate
from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, current_user, login_required, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# 🔷 BASE PATH
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# 🔷 ENSURE INSTANCE FOLDER EXISTS
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
os.makedirs(INSTANCE_DIR, exist_ok=True)

# 🔷 DATABASE PATH (LOCAL)
DB_PATH = os.path.join(INSTANCE_DIR, "app.db")

# 🔷 UPLOADS
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

# 🔷 APP INIT
app = Flask(__name__)

# 🔷 SECRET KEY (CRITICAL)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')

# 🔷 DATABASE CONFIG (RAILWAY + LOCAL FALLBACK)
database_url = os.getenv("DATABASE_URL")

if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or \
    'sqlite:///' + DB_PATH

# 🔷 SQLALCHEMY SETTINGS
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True
}

# 🔷 FILE UPLOAD CONFIG
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# 🔷 INIT DB
db = SQLAlchemy(app)
migrate = Migrate(app, db)



login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ------------------ MODELS ------------------

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    display_name = db.Column(db.String(120), nullable=False)
    contact_email = db.Column(db.String(200))
    contact_phone = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)
    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(200))
    type = db.Column(db.String(50), default='Other')
    image_url = db.Column(db.String(500))
    available = db.Column(db.Boolean, default=True)
    due_at = db.Column(db.DateTime, nullable=True)
    contact_email = db.Column(db.String(200))
    contact_phone = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    owner = db.relationship(
    'User',
    backref=db.backref('books', cascade="all, delete")
    )

class Wishlist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    book = db.relationship(
    'Book',
    backref=db.backref('wishlists', cascade="all, delete")
    )

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Rating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    value = db.Column(db.Integer, nullable=False)  # 1–5

    user = db.relationship('User', backref='ratings')
    book = db.relationship(
    'Book',
    backref=db.backref('ratings', cascade="all, delete")
    )

DEFAULT_BOOK_IMAGES = {
    'Engineering': '/static/defaults/engineering.jpg',
    'Fiction': '/static/defaults/fiction.jpg',
    'Non-Fiction': '/static/defaults/nonfiction.jpg',
    'Business': '/static/defaults/business.jpg',
    'Science': '/static/defaults/science.jpg',
    'Other': '/static/defaults/other.jpg',
}

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in {"png","jpg","jpeg","gif","webp"}

def ensure_default_image(type_value: str, image_url: str) -> tuple[str, str]:
    t = type_value if type_value in DEFAULT_BOOK_IMAGES else 'Other'
    if image_url and image_url.strip():
        return t, image_url.strip()
    return t, DEFAULT_BOOK_IMAGES[t]

def get_avg_rating(book):
    if not book.ratings:
        return 0
    return round(sum(r.value for r in book.ratings) / len(book.ratings), 1)
# ------------------ ROUTES ------------------
@app.route('/rate/<int:book_id>', methods=['POST'])
@login_required
def rate_book(book_id):
    value = int(request.form.get('rating'))

    rating = Rating.query.filter_by(
        user_id=current_user.id,
        book_id=book_id
    ).first()

    if rating:
        rating.value = value
    else:
        rating = Rating(user_id=current_user.id, book_id=book_id, value=value)
        db.session.add(rating)
        print("Rating submitted:", value)

    db.session.commit()
    return redirect(request.referrer or url_for('index'))

@app.route('/')
def index():
    search = request.args.get('search', '').strip()
    filter_type = request.args.get('type', '').strip()

    query = Book.query

    # Text search filter
    if search:
        like = f"%{search}%"
        query = query.filter(
            db.or_(
                Book.title.ilike(like),
                Book.author.ilike(like),
                Book.type.ilike(like)
            )
        )

    # Type dropdown filter
    if filter_type and filter_type != "All":
        query = query.filter(Book.type == filter_type)

    rows = query.order_by(Book.created_at.desc()).all()

    wish_ids = set()
    if current_user.is_authenticated:
        wish_ids = {w.book_id for w in Wishlist.query.filter_by(user_id=current_user.id).all()}

    view = []
    for b in rows:
        owner = User.query.get(b.owner_id)

        avg_rating = get_avg_rating(b)

        user_rating = 0
        if current_user.is_authenticated:
            r = Rating.query.filter_by(
                user_id=current_user.id,
                book_id=b.id
            ).first()
            if r:
                user_rating = r.value

        view.append({
            'id': b.id,
            'title': b.title,
            'author': b.author,
            'type': b.type,
            'image_url': b.image_url,
            'available': b.available,
            'avg_rating': avg_rating,
            'user_rating': user_rating,
            'owner': {
                'id': owner.id if owner else None,
                'name': owner.display_name if owner else 'Owner',
                'email': (b.contact_email or (owner.contact_email if owner else None)),
                'phone': (b.contact_phone or (owner.contact_phone if owner else None)),
            },
            'wishlisted': (b.id in wish_ids)
        })

    # Pass list of all types for dropdown
    book_types = ["All", "Engineering", "Fiction", "Non-Fiction", "Business", "Science", "Other"]

    return render_template('index.html', books=view, search=search, filter_type=filter_type, book_types=book_types)





@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip().lower()
        display_name = request.form['display_name'].strip()
        password = request.form['password']
        contact_email = request.form.get('contact_email','').strip() or None
        contact_phone = request.form.get('contact_phone','').strip() or None

        if not username or not password or not display_name:
            flash('Please complete all required fields.', 'danger')
            return redirect(url_for('register'))
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'warning')
            return redirect(url_for('register'))
        u = User(username=username, display_name=display_name, contact_email=contact_email, contact_phone=contact_phone)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        flash('Registration successful. Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip().lower()
        password = request.form['password']
        u = User.query.filter_by(username=username).first()
        if not u or not u.check_password(password):
            flash('Invalid credentials.', 'danger')
            return redirect(url_for('login'))
        login_user(u)
        flash(f'Welcome back, {u.display_name}', 'success')
        return redirect(url_for('profile'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/books/add', methods=['GET','POST'])
@login_required
def books_add():
    if request.method == 'POST':
        title = request.form['title'].strip()
        author = request.form.get('author','').strip()
        type_value = request.form.get('type','Other').strip()
        image_url_field = request.form.get('image_url','').strip()
        contact_email = request.form.get('contact_email','').strip() or None
        contact_phone = request.form.get('contact_phone','').strip() or None

        if not title:
            flash('Title is required.', 'danger')
            return redirect(url_for('books_add'))

        # Handle file upload if provided
        file = request.files.get('image_file')
        final_image_url = None
        if file and file.filename and allowed_file(file.filename):
            fname = secure_filename(file.filename)
            ext = fname.rsplit('.', 1)[1].lower()
            new_name = f"{uuid.uuid4().hex}.{ext}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], new_name))
            final_image_url = f"/static/uploads/{new_name}"

        final_type, fallback_image = ensure_default_image(type_value, image_url_field)
        image_to_use = final_image_url or fallback_image

        b = Book(
            owner_id=current_user.id,
            title=title,
            author=author,
            type=final_type,
            image_url=image_to_use,
            available=True,
            contact_email=contact_email,
            contact_phone=contact_phone
        )
        db.session.add(b)
        db.session.commit()
        flash('Book added.', 'success')
        return redirect(url_for('profile'))
    return render_template('add_book.html')

@app.route('/profile')
@login_required
def profile():
    my_books = Book.query.filter_by(owner_id=current_user.id).order_by(Book.created_at.desc()).all()
    wishlist = Wishlist.query.filter_by(user_id=current_user.id).order_by(Wishlist.created_at.desc()).all()

    # Build chat partners with last message
    msgs = Message.query.filter(
        (Message.sender_id == current_user.id) | (Message.receiver_id == current_user.id)
    ).order_by(Message.created_at.desc()).all()

    last_by_partner = {}
    for m in msgs:
        partner_id = m.receiver_id if m.sender_id == current_user.id else m.sender_id
        if partner_id not in last_by_partner:
            last_by_partner[partner_id] = m

    partners = []
    for pid, last in last_by_partner.items():
        u = User.query.get(pid)
        if u:
            partners.append({
                'id': u.id,
                'name': u.display_name,
                'last_text': last.text[:80] + ('...' if len(last.text) > 80 else ''),
                'last_time': last.created_at
            })
    # sort by last message time desc
    partners.sort(key=lambda x: x['last_time'], reverse=True)

    return render_template('profile.html', my_books=my_books, wishlist=wishlist, partners=partners)

@app.route('/books/<int:book_id>/status', methods=['POST'])
@login_required
def update_status(book_id):
    b = Book.query.filter_by(id=book_id, owner_id=current_user.id).first()
    if not b:
        abort(404)
    new_status = request.form.get('status')
    if new_status not in ['available','unavailable']:
        flash('Invalid status.', 'danger')
        return redirect(url_for('profile'))
    b.available = (new_status == 'available')
    if b.available:
        b.due_at = None
    db.session.commit()
    flash('Status updated.', 'success')
    return redirect(url_for('profile'))

# ---- Wishlist heart endpoints (idempotent add/remove) ----

@app.route('/wishlist/toggle/<int:book_id>', methods=['POST'])
@login_required
def wishlist_toggle(book_id):
    b = Book.query.get(book_id)
    if not b:
        abort(404)
    existing = Wishlist.query.filter_by(user_id=current_user.id, book_id=book_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        flash('Removed from wishlist.', 'info')
    else:
        db.session.add(Wishlist(user_id=current_user.id, book_id=book_id))
        db.session.commit()
        flash('Added to wishlist.', 'success')
    return redirect(url_for('index'))

# ---- Chat endpoints ----

@app.route('/chat/<int:user_id>', methods=['GET','POST'])
@login_required
def chat(user_id):
    if user_id == current_user.id:
        flash("You cannot chat with yourself.", "warning")
        return redirect(url_for('profile'))
    partner = User.query.get_or_404(user_id)
    if request.method == 'POST':
        text = request.form.get('text','').strip()
        if text:
            db.session.add(Message(sender_id=current_user.id, receiver_id=user_id, text=text))
            db.session.commit()
            return redirect(url_for('chat', user_id=user_id))
    # fetch thread messages
    thread = Message.query.filter(
        db.or_(
            db.and_(Message.sender_id==current_user.id, Message.receiver_id==user_id),
            db.and_(Message.sender_id==user_id, Message.receiver_id==current_user.id),
        )
    ).order_by(Message.created_at.asc()).all()
    return render_template('chat.html', partner=partner, messages=thread)

from flask import abort, redirect, url_for, flash
from flask_login import login_required, current_user

@app.route("/book/delete/<int:book_id>", methods=["POST"])
@login_required
def delete_book(book_id):
    book = Book.query.get_or_404(book_id)

    if book.owner_id != current_user.id:
        abort(403)

    try:
        # 🔷 DELETE RELATED DATA FIRST (CRITICAL)
        Wishlist.query.filter_by(book_id=book.id).delete()
        Rating.query.filter_by(book_id=book.id).delete()

        # 🔷 SAFE IMAGE DELETE
        if book.image_url and "uploads/" in book.image_url:
            image_path = book.image_url.replace("/static/", "static/")
            image_path = os.path.join(BASE_DIR, image_path)

            if os.path.exists(image_path):
                os.remove(image_path)

        db.session.delete(book)
        db.session.commit()

        flash("Book deleted successfully.", "success")

    except Exception as e:
        db.session.rollback()
        print("DELETE ERROR:", e)
        flash("Error deleting book.", "danger")

    return redirect(url_for("profile"))

# ---------- DB INIT (safe for prod when seed=False and drop=False) ----------
def init_db(seed: bool = False, drop: bool = False):
    """
    Initialize database schema.
    - drop=True will drop all tables first (ONLY for local dev resets).
    - seed=True will insert demo users/books (NEVER enable in production).
    """
    if drop:
        db.drop_all()
    db.create_all()

    if not seed:
        print("Database initialized (no seed).")
        return

    # ---- DEMO DATA: for local development only ----
    admin = User(username='admin', display_name='Admin', contact_email='admin@example.com')
    admin.set_password('password')
    db.session.add(admin)
    db.session.commit()

    # Optionally comment out ALL demo book/users below or keep none at all.
    # No 'alice' or 'bob' will be created anymore.
    print('Database initialized with demo seed (admin only).')


with app.app_context():
    db.drop_all()
    db.create_all()