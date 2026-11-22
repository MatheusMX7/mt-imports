-- SQLite (gerado dos modelos). A API cria as tabelas sozinha ao iniciar; este arquivo é só referência.
CREATE TABLE admins (
	id INTEGER NOT NULL, 
	email VARCHAR(160) NOT NULL, 
	password_hash VARCHAR(100) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (email)
);

CREATE TABLE categories (
	id INTEGER NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	description TEXT NOT NULL, 
	image TEXT NOT NULL, 
	sort_order INTEGER NOT NULL, 
	active BOOLEAN NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE coupons (
	id INTEGER NOT NULL, 
	code VARCHAR(40) NOT NULL, 
	kind VARCHAR(10) NOT NULL, 
	value NUMERIC(10, 2) NOT NULL, 
	expires_on DATE, 
	max_uses INTEGER, 
	min_purchase NUMERIC(10, 2) NOT NULL, 
	used_count INTEGER NOT NULL, 
	active BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (code)
);

CREATE TABLE customers (
	id INTEGER NOT NULL, 
	first_name VARCHAR(80) NOT NULL, 
	last_name VARCHAR(80) NOT NULL, 
	phone VARCHAR(30) NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE settings (
	id INTEGER NOT NULL, 
	store_name VARCHAR(120) NOT NULL, 
	whatsapp VARCHAR(30) NOT NULL, 
	address VARCHAR(250) NOT NULL, 
	hours VARCHAR(160) NOT NULL, 
	moto_fee NUMERIC(10, 2) NOT NULL, 
	pix_key VARCHAR(160) NOT NULL, 
	pay_info TEXT NOT NULL, 
	pickup_info TEXT NOT NULL, 
	socials VARCHAR(250) NOT NULL, 
	logo_url TEXT NOT NULL, 
	banner_url TEXT NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE orders (
	id INTEGER NOT NULL, 
	idem_key VARCHAR(80) NOT NULL, 
	customer_id INTEGER, 
	customer JSON NOT NULL, 
	ship_method VARCHAR(20) NOT NULL, 
	cep VARCHAR(12) NOT NULL, 
	pay_method VARCHAR(30) NOT NULL, 
	pay_note TEXT NOT NULL, 
	notes TEXT NOT NULL, 
	internal_note TEXT NOT NULL, 
	coupon_code VARCHAR(40) NOT NULL, 
	subtotal NUMERIC(10, 2) NOT NULL, 
	discount NUMERIC(10, 2) NOT NULL, 
	shipping NUMERIC(10, 2), 
	total NUMERIC(10, 2), 
	status VARCHAR(40) NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (idem_key), 
	FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE SET NULL
);

CREATE INDEX ix_orders_status ON orders (status);

CREATE INDEX ix_orders_created_at ON orders (created_at);

CREATE TABLE products (
	id INTEGER NOT NULL, 
	category_id INTEGER, 
	name VARCHAR(200) NOT NULL, 
	description TEXT NOT NULL, 
	price NUMERIC(10, 2) NOT NULL, 
	promo_price NUMERIC(10, 2), 
	stock INTEGER NOT NULL, 
	sizes JSON NOT NULL, 
	colors JSON NOT NULL, 
	active BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(category_id) REFERENCES categories (id) ON DELETE SET NULL
);

CREATE INDEX ix_products_category_id ON products (category_id);

CREATE TABLE order_items (
	id INTEGER NOT NULL, 
	order_id INTEGER NOT NULL, 
	product_id INTEGER, 
	category_id INTEGER, 
	name VARCHAR(200) NOT NULL, 
	variation VARCHAR(120) NOT NULL, 
	qty INTEGER NOT NULL, 
	unit_price NUMERIC(10, 2) NOT NULL, 
	subtotal NUMERIC(10, 2) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(order_id) REFERENCES orders (id) ON DELETE CASCADE, 
	FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE SET NULL
);

CREATE INDEX ix_order_items_order_id ON order_items (order_id);

CREATE TABLE product_images (
	id INTEGER NOT NULL, 
	product_id INTEGER NOT NULL, 
	url TEXT NOT NULL, 
	sort_order INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE CASCADE
);

CREATE INDEX ix_product_images_product_id ON product_images (product_id);
