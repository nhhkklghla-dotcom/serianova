from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import json
import random
import string
import qrcode
from io import BytesIO
import base64
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'serianova_secret_key_2026'
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(BASE_DIR, "database.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ========== إعدادات رفع الملفات ==========
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ========== قائمة المحافظات السورية ==========
SYRIAN_CITIES = [
    'دمشق', 'ريف دمشق', 'حلب', 'حمص', 'حماة', 'اللاذقية', 'طرطوس',
    'دير الزور', 'الحسكة', 'الرقة', 'إدلب', 'درعا', 'السويداء', 'القنيطرة'
]

# ========== البحث ==========
@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    if query:
        # البحث في اسم المنتج والوصف
        products = Product.query.filter(
            (Product.name.contains(query)) | (Product.description.contains(query))
        ).all()
    else:
        products = []
    return render_template('search_results.html', products=products, query=query)

# ========== API للبحث السريع (اختياري) ==========
@app.route('/api/search')
def api_search():
    query = request.args.get('q', '').strip()
    if query:
        products = Product.query.filter(Product.name.contains(query)).limit(10).all()
        results = [{'id': p.id, 'name': p.name, 'price': p.price, 'image': p.image_url} for p in products]
        return jsonify(results)
    return jsonify([])
# ========== نماذج قاعدة البيانات ==========
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    price = db.Column(db.Float, nullable=False)
    old_price = db.Column(db.Float, default=0)
    category = db.Column(db.String(50), nullable=False)
    subcategory = db.Column(db.String(50), default='')
    image_url = db.Column(db.String(300))
    images = db.Column(db.Text, default='')
    description = db.Column(db.Text, default='')
    is_bestseller = db.Column(db.Boolean, default=False)
    is_new = db.Column(db.Boolean, default=False)
    stock = db.Column(db.Integer, default=10)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(50), unique=True)
    tracking_number = db.Column(db.String(50), unique=True)
    customer_name = db.Column(db.String(100), nullable=False)
    customer_phone = db.Column(db.String(20), nullable=False)
    customer_address = db.Column(db.String(300), nullable=False)
    city = db.Column(db.String(50), nullable=False)
    notes = db.Column(db.Text, default='')
    total_amount = db.Column(db.Float, nullable=False)
    shipping_fee = db.Column(db.Float, default=15000)
    items = db.Column(db.Text)
    status = db.Column(db.String(30), default='pending_payment')
    payment_method = db.Column(db.String(30), default='شام كاش مسبق الدفع')
    payment_status = db.Column(db.String(30), default='pending')
    shamsi_cash_number = db.Column(db.String(50))
    coupon_code = db.Column(db.String(50), default='')
    discount_amount = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_status_arabic(self):
        status_map = {
            'pending_payment': 'في انتظار الدفع',
            'payment_confirmed': 'تم تأكيد الدفع',
            'processing': 'قيد التجهيز',
            'shipped': 'تم الشحن',
            'delivered': 'تم التوصيل',
            'cancelled': 'ملغي'
        }
        return status_map.get(self.status, self.status)

class TrackingHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    status = db.Column(db.String(30))
    note = db.Column(db.String(200))
    location = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Coupon(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    discount_type = db.Column(db.String(20), default='percentage')
    discount_value = db.Column(db.Float, nullable=False)
    min_order_amount = db.Column(db.Float, default=0)
    max_discount = db.Column(db.Float, default=0)
    valid_from = db.Column(db.DateTime, default=datetime.utcnow)
    valid_to = db.Column(db.DateTime)
    usage_limit = db.Column(db.Integer, default=1)
    used_count = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ========== الصفحات الرئيسية ==========
@app.route('/')
def index():
    bestsellers = Product.query.filter_by(is_bestseller=True).limit(8).all()
    watches = Product.query.filter_by(category='ساعات').limit(4).all()
    fashion = Product.query.filter_by(category='أزياء نسائية').limit(4).all()
    return render_template('index.html', bestsellers=bestsellers, watches=watches, fashion=fashion)

@app.route('/products/<category>')
def products(category):
    page = request.args.get('page', 1, type=int)
    per_page = 12
    sort_by = request.args.get('sort', 'newest')
    products_query = Product.query.filter_by(category=category)
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    if min_price:
        products_query = products_query.filter(Product.price >= min_price)
    if max_price:
        products_query = products_query.filter(Product.price <= max_price)
    on_sale = request.args.get('on_sale')
    if on_sale == 'true':
        products_query = products_query.filter(Product.old_price > 0)
    if sort_by == 'price_asc':
        products_query = products_query.order_by(Product.price.asc())
    elif sort_by == 'price_desc':
        products_query = products_query.order_by(Product.price.desc())
    elif sort_by == 'bestseller':
        products_query = products_query.order_by(Product.is_bestseller.desc())
    else:
        products_query = products_query.order_by(Product.created_at.desc())
    pagination = products_query.paginate(page=page, per_page=per_page, error_out=False)
    price_range = db.session.query(db.func.min(Product.price), db.func.max(Product.price)).filter_by(category=category).first()
    return render_template('products.html',
                         products=pagination.items,
                         category=category,
                         pagination=pagination,
                         min_possible_price=price_range[0] or 0,
                         max_possible_price=price_range[1] or 1000000,
                         current_min_price=min_price or 0,
                         current_max_price=max_price or (price_range[1] or 1000000),
                         sort_by=sort_by,
                         on_sale=on_sale == 'true')

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    related = Product.query.filter_by(category=product.category).limit(4).all()
    return render_template('product_detail.html', product=product, related=related)

# ========== السلة (باستخدام Session) ==========
@app.route('/api/cart/add', methods=['POST'])
def add_to_cart():
    data = request.get_json()
    cart = session.get('cart', {})
    product_id = str(data['product_id'])
    if product_id in cart:
        cart[product_id]['quantity'] += data.get('quantity', 1)
    else:
        product = Product.query.get(product_id)
        if product:
            cart[product_id] = {
                'id': product.id,
                'name': product.name,
                'price': product.price,
                'quantity': data.get('quantity', 1),
                'image': product.image_url
            }
    session['cart'] = cart
    cart_count = sum(item['quantity'] for item in cart.values())
    return jsonify({'success': True, 'cart_count': cart_count})

@app.route('/cart/update/<product_id>/<action>')
def cart_update(product_id, action):
    cart = session.get('cart', {})
    if product_id in cart:
        if action == 'increase':
            cart[product_id]['quantity'] += 1
        elif action == 'decrease':
            cart[product_id]['quantity'] -= 1
            if cart[product_id]['quantity'] <= 0:
                del cart[product_id]
        elif action == 'remove':
            del cart[product_id]
    session['cart'] = cart
    return redirect(url_for('view_cart'))

@app.route('/api/cart/count')
def cart_count():
    cart = session.get('cart', {})
    count = sum(item['quantity'] for item in cart.values())
    return jsonify({'count': count})

@app.route('/cart')
def view_cart():
    cart = session.get('cart', {})
    subtotal = sum(item['price'] * item['quantity'] for item in cart.values())
    shipping_fee = 15000 if subtotal > 0 else 0
    total = subtotal + shipping_fee
    return render_template('cart.html', cart=cart, subtotal=subtotal, shipping_fee=shipping_fee, total=total)

# ========== كوبونات الخصم ==========
@app.route('/api/apply-coupon', methods=['POST'])
def apply_coupon():
    data = request.get_json()
    code = data['code'].upper()
    subtotal = data['subtotal']
    coupon = Coupon.query.filter_by(code=code, is_active=True).first()
    if not coupon:
        return jsonify({'valid': False, 'message': 'الكوبون غير صالح'})
    now = datetime.utcnow()
    if coupon.valid_to and now > coupon.valid_to:
        return jsonify({'valid': False, 'message': 'انتهت صلاحية الكوبون'})
    if subtotal < coupon.min_order_amount:
        return jsonify({'valid': False, 'message': f'الحد الأدنى للطلب: {coupon.min_order_amount:,.0f} ل.س'})
    if coupon.usage_limit and coupon.used_count >= coupon.usage_limit:
        return jsonify({'valid': False, 'message': 'تم استخدام هذا الكوبون بأقصى عدد مرات'})
    if coupon.discount_type == 'percentage':
        discount_amount = subtotal * (coupon.discount_value / 100)
        if coupon.max_discount > 0 and discount_amount > coupon.max_discount:
            discount_amount = coupon.max_discount
    else:
        discount_amount = min(coupon.discount_value, subtotal)
    session['discount_amount'] = discount_amount
    session['coupon_code'] = code
    return jsonify({'valid': True, 'discount_amount': discount_amount})

# ========== إتمام الطلب ==========
@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    cart = session.get('cart', {})
    if not cart:
        return redirect(url_for('index'))
    subtotal = sum(item['price'] * item['quantity'] for item in cart.values())
    shipping_fee = 15000
    discount_amount = session.get('discount_amount', 0)
    coupon_code = session.get('coupon_code', '')
    total = subtotal + shipping_fee - discount_amount
    if request.method == 'POST':
        order_number = f"SER-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(100,999)}"
        tracking_number = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
        order = Order(
            order_number=order_number,
            tracking_number=tracking_number,
            customer_name=request.form['name'],
            customer_phone=request.form['phone'],
            customer_address=request.form['address'],
            city=request.form['city'],
            notes=request.form.get('notes', ''),
            total_amount=total,
            shipping_fee=shipping_fee,
            items=json.dumps(cart, ensure_ascii=False),
            payment_method='شام كاش مسبق الدفع',
            status='pending_payment',
            payment_status='pending',
            coupon_code=coupon_code,
            discount_amount=discount_amount
        )
        db.session.add(order)
        db.session.commit()
        tracking = TrackingHistory(order_id=order.id, status='pending_payment', note='تم استلام طلبك، يرجى إتمام الدفع عبر شام كاش')
        db.session.add(tracking)
        db.session.commit()
        if coupon_code:
            coup = Coupon.query.filter_by(code=coupon_code).first()
            if coup:
                coup.used_count += 1
                db.session.commit()
        session.pop('cart', None)
        session.pop('discount_amount', None)
        session.pop('coupon_code', None)
        return render_template('order_success.html', order=order)
    return render_template('checkout.html', subtotal=subtotal, shipping_fee=shipping_fee,
                         total=total, cities=SYRIAN_CITIES, discount_amount=discount_amount,
                         coupon_code=coupon_code)

@app.route('/api/confirm-payment', methods=['POST'])
def confirm_payment():
    data = request.get_json()
    order = Order.query.filter_by(order_number=data['order_number']).first()
    if order and order.status == 'pending_payment':
        order.shamsi_cash_number = data['transaction_number']
        order.status = 'payment_confirmed'
        order.payment_status = 'paid'
        order.updated_at = datetime.utcnow()
        tracking = TrackingHistory(order_id=order.id, status='payment_confirmed', note=f'تم تأكيد الدفع عبر شام كاش - رقم العملية: {data["transaction_number"]}')
        db.session.add(tracking)
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False})

# ========== تتبع الطلبات ==========
@app.route('/track-order', methods=['GET', 'POST'])
def track_order():
    if request.method == 'POST':
        tracking_number = request.form['tracking_number']
        order = Order.query.filter_by(tracking_number=tracking_number).first()
        if order:
            history = TrackingHistory.query.filter_by(order_id=order.id).order_by(TrackingHistory.created_at).all()
            return render_template('order_tracking.html', order=order, history=history)
        else:
            return render_template('track_order.html', error='رقم التتبع غير صحيح')
    return render_template('track_order.html')

@app.route('/track/<tracking_number>')
def track_direct(tracking_number):
    order = Order.query.filter_by(tracking_number=tracking_number).first()
    if order:
        history = TrackingHistory.query.filter_by(order_id=order.id).order_by(TrackingHistory.created_at).all()
        return render_template('order_tracking.html', order=order, history=history)
    return render_template('track_order.html', error='رقم التتبع غير صحيح')

@app.route('/api/generate-payment-qr/<order_number>')
def generate_payment_qr(order_number):
    order = Order.query.filter_by(order_number=order_number).first()
    if not order:
        return "Order not found", 404
    payment_text = f"شام كاش: 9144145975221710\nالمبلغ: {order.total_amount} ل.س\nالطلب: {order.order_number}"
    qr = qrcode.make(payment_text)
    img_io = BytesIO()
    qr.save(img_io, 'PNG')
    img_io.seek(0)
    img_data = base64.b64encode(img_io.getvalue()).decode()
    return f'<img src="data:image/png;base64,{img_data}" style="width:250px;">'

# ========== إدارة المنتجات (رفع صور متعددة) ==========
@app.route('/admin/product', methods=['POST'])
def add_product():
    uploaded_images = []
    if 'images' in request.files:
        files = request.files.getlist('images')
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                uploaded_images.append(f'/static/uploads/{filename}')
    main_image = ''
    if 'main_image' in request.files:
        main_file = request.files['main_image']
        if main_file and allowed_file(main_file.filename):
            main_filename = secure_filename(f"main_{datetime.now().strftime('%Y%m%d%H%M%S')}_{main_file.filename}")
            main_file.save(os.path.join(app.config['UPLOAD_FOLDER'], main_filename))
            main_image = f'/static/uploads/{main_filename}'
    product = Product(
        name=request.form['name'],
        price=float(request.form['price']),
        old_price=float(request.form.get('old_price', 0)),
        category=request.form['category'],
        image_url=main_image,
        images=','.join(uploaded_images),
        description=request.form.get('description', ''),
        is_bestseller='is_bestseller' in request.form,
        is_new='is_new' in request.form,
        stock=int(request.form.get('stock', 10))
    )
    db.session.add(product)
    db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/product/<int:product_id>/delete', methods=['POST'])
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    return jsonify({'success': True})

# ========== لوحة التحكم ==========
@app.route('/admin')
def admin():
    orders = Order.query.order_by(Order.created_at.desc()).all()
    products = Product.query.all()
    coupons = Coupon.query.all()
    return render_template('admin.html', orders=orders, products=products, coupons=coupons)

@app.route('/admin/order/<int:order_id>/status', methods=['POST'])
def update_order_status(order_id):
    order = Order.query.get_or_404(order_id)
    new_status = request.json['status']
    order.status = new_status
    order.updated_at = datetime.utcnow()
    status_note = {
        'payment_confirmed': 'تم تأكيد الدفع، جاري تجهيز الطلب',
        'processing': 'الطلب قيد التجهيز',
        'shipped': 'تم الشحن',
        'delivered': 'تم التوصيل',
        'cancelled': 'تم إلغاء الطلب'
    }
    tracking = TrackingHistory(order_id=order.id, status=new_status, note=status_note.get(new_status, 'تم تحديث الحالة'))
    db.session.add(tracking)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/admin/coupon', methods=['POST'])
def add_coupon():
    coupon = Coupon(
        code=request.form['code'].upper(),
        discount_type=request.form['discount_type'],
        discount_value=float(request.form['discount_value']),
        min_order_amount=float(request.form.get('min_order_amount', 0)),
        max_discount=float(request.form.get('max_discount', 0)),
        valid_from=datetime.strptime(request.form['valid_from'], '%Y-%m-%d') if request.form.get('valid_from') else datetime.utcnow(),
        valid_to=datetime.strptime(request.form['valid_to'], '%Y-%m-%d') if request.form.get('valid_to') else None,
        usage_limit=int(request.form.get('usage_limit', 1)),
        is_active='is_active' in request.form
    )
    db.session.add(coupon)
    db.session.commit()
    return redirect(url_for('admin'))

@app.route('/api/stats')
def get_stats():
    total_orders = Order.query.count()
    total_revenue = db.session.query(db.func.sum(Order.total_amount)).filter(Order.payment_status == 'paid').scalar() or 0
    pending_orders = Order.query.filter_by(status='pending_payment').count()
    return jsonify({'total_orders': total_orders, 'total_revenue': total_revenue, 'pending_orders': pending_orders})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if Product.query.count() == 0:
            sample_products = [
                Product(name='ساعة سيريانوغا الفاخرة - ذهبية', price=250000, old_price=350000, category='ساعات', image_url='https://images.unsplash.com/photo-1524592094714-0f0654e20314?w=300', is_bestseller=True, is_new=True),
                Product(name='ساعة جلدية أنيقة', price=180000, old_price=250000, category='ساعات', image_url='https://images.unsplash.com/photo-1524805444758-089113d48a6d?w=300', is_bestseller=True),
                Product(name='ساعة رياضية ذكية', price=220000, old_price=0, category='ساعات', image_url='https://images.unsplash.com/photo-1579586337278-3befd40fd17a?w=300', is_new=True),
                Product(name='فستان سهرة طويل', price=350000, old_price=450000, category='أزياء نسائية', image_url='https://images.unsplash.com/photo-1539008835657-9e8e9680c956?w=300', is_bestseller=True),
                Product(name='طقم كاجوال نسائي', price=220000, old_price=0, category='أزياء نسائية', image_url='https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=300', is_new=True),
                Product(name='حقيبة يد جلدية', price=150000, old_price=200000, category='اكسسوارات', image_url='https://images.unsplash.com/photo-1584917865442-de89df76afd3?w=300', is_bestseller=True),
                Product(name='عطر فرنسي فاخر', price=120000, old_price=200000, category='عطور', image_url='https://images.unsplash.com/photo-1541643600914-78b084683601?w=300', is_bestseller=True),
            ]
            for p in sample_products:
                db.session.add(p)
            db.session.commit()
        if Coupon.query.count() == 0:
            sample_coupons = [
                Coupon(code='WELCOME10', discount_type='percentage', discount_value=10, min_order_amount=50000, max_discount=25000, valid_to=datetime.utcnow() + timedelta(days=30), usage_limit=100, is_active=True),
                Coupon(code='SAVE20', discount_type='percentage', discount_value=20, min_order_amount=100000, max_discount=50000, valid_to=datetime.utcnow() + timedelta(days=15), usage_limit=50, is_active=True),
            ]
            for c in sample_coupons:
                db.session.add(c)
            db.session.commit()
    app.run(debug=True)