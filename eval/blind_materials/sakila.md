# sakila（DVD 租赁连锁店） 数据库：Schema 与数据字典

SQLite 库文件：`sakila.db`，共 15 张表。

## 建表语句

```sql
CREATE TABLE actor (
  actor_id INTEGER NOT NULL ,
  first_name VARCHAR(45) NOT NULL,
  last_name VARCHAR(45) NOT NULL,
  last_update TIMESTAMP NOT NULL,
  PRIMARY KEY  (actor_id)
  );

CREATE TABLE address (
  address_id INTEGER NOT NULL,
  address VARCHAR(50) NOT NULL,
  address2 VARCHAR(50) DEFAULT NULL,
  district VARCHAR(20) NOT NULL,
  city_id INT  NOT NULL,
  postal_code VARCHAR(10) DEFAULT NULL,
  phone VARCHAR(20) NOT NULL,
  last_update TIMESTAMP NOT NULL,
  PRIMARY KEY  (address_id),
  CONSTRAINT fk_address_city FOREIGN KEY (city_id) REFERENCES city (city_id) ON DELETE NO ACTION ON UPDATE CASCADE
);

CREATE TABLE category (
  category_id INTEGER NOT NULL,
  name VARCHAR(25) NOT NULL,
  last_update TIMESTAMP NOT NULL,
  PRIMARY KEY  (category_id)
);

CREATE TABLE city (
  city_id INTEGER NOT NULL,
  city VARCHAR(50) NOT NULL,
  country_id INT NOT NULL,
  last_update TIMESTAMP NOT NULL,
  PRIMARY KEY  (city_id),
  CONSTRAINT fk_city_country FOREIGN KEY (country_id) REFERENCES country (country_id) ON DELETE NO ACTION ON UPDATE CASCADE
);

CREATE TABLE country (
  country_id INTEGER NOT NULL,
  country VARCHAR(50) NOT NULL,
  last_update TIMESTAMP,
  PRIMARY KEY  (country_id)
);

CREATE TABLE customer (
  customer_id INTEGER NOT NULL,
  store_id INT NOT NULL,
  first_name VARCHAR(45) NOT NULL,
  last_name VARCHAR(45) NOT NULL,
  email VARCHAR(50) DEFAULT NULL,
  address_id INT NOT NULL,
  active CHAR(1) DEFAULT 'Y' NOT NULL,
  create_date TIMESTAMP NOT NULL,
  last_update TIMESTAMP NOT NULL,
  PRIMARY KEY  (customer_id),
  CONSTRAINT fk_customer_store FOREIGN KEY (store_id) REFERENCES store (store_id) ON DELETE NO ACTION ON UPDATE CASCADE,
  CONSTRAINT fk_customer_address FOREIGN KEY (address_id) REFERENCES address (address_id) ON DELETE NO ACTION ON UPDATE CASCADE
);

CREATE TABLE film (
  film_id INTEGER NOT NULL,
  title VARCHAR(255) NOT NULL,
  description BLOB SUB_TYPE TEXT DEFAULT NULL,
  release_year VARCHAR(4) DEFAULT NULL,
  language_id INT NOT NULL,
  original_language_id INT DEFAULT NULL,
  rental_duration SMALLINT  DEFAULT 3 NOT NULL,
  rental_rate DECIMAL(4,2) DEFAULT 4.99 NOT NULL,
  length SMALLINT DEFAULT NULL,
  replacement_cost DECIMAL(5,2) DEFAULT 19.99 NOT NULL,
  rating VARCHAR(10) DEFAULT 'G',
  special_features VARCHAR(100) DEFAULT NULL,
  last_update TIMESTAMP NOT NULL,
  PRIMARY KEY  (film_id),
  CONSTRAINT CHECK_special_features CHECK(special_features is null or
                                                           special_features like '%Trailers%' or
                                                           special_features like '%Commentaries%' or
                                                           special_features like '%Deleted Scenes%' or
                                                           special_features like '%Behind the Scenes%'),
  CONSTRAINT CHECK_special_rating CHECK(rating in ('G','PG','PG-13','R','NC-17')),
  CONSTRAINT fk_film_language FOREIGN KEY (language_id) REFERENCES language (language_id) ,
  CONSTRAINT fk_film_language_original FOREIGN KEY (original_language_id) REFERENCES language (language_id)
);

CREATE TABLE film_actor (
  actor_id INT NOT NULL,
  film_id  INT NOT NULL,
  last_update TIMESTAMP NOT NULL,
  PRIMARY KEY  (actor_id,film_id),
  CONSTRAINT fk_film_actor_actor FOREIGN KEY (actor_id) REFERENCES actor (actor_id) ON DELETE NO ACTION ON UPDATE CASCADE,
  CONSTRAINT fk_film_actor_film FOREIGN KEY (film_id) REFERENCES film (film_id) ON DELETE NO ACTION ON UPDATE CASCADE
);

CREATE TABLE film_category (
  film_id INT NOT NULL,
  category_id INT  NOT NULL,
  last_update TIMESTAMP NOT NULL,
  PRIMARY KEY (film_id, category_id),
  CONSTRAINT fk_film_category_film FOREIGN KEY (film_id) REFERENCES film (film_id) ON DELETE NO ACTION ON UPDATE CASCADE,
  CONSTRAINT fk_film_category_category FOREIGN KEY (category_id) REFERENCES category (category_id) ON DELETE NO ACTION ON UPDATE CASCADE
);

CREATE TABLE inventory (
  inventory_id INTEGER NOT NULL,
  film_id INT NOT NULL,
  store_id INT NOT NULL,
  last_update TIMESTAMP NOT NULL,
  PRIMARY KEY  (inventory_id),
  CONSTRAINT fk_inventory_store FOREIGN KEY (store_id) REFERENCES store (store_id) ON DELETE NO ACTION ON UPDATE CASCADE,
  CONSTRAINT fk_inventory_film FOREIGN KEY (film_id) REFERENCES film (film_id) ON DELETE NO ACTION ON UPDATE CASCADE
);

CREATE TABLE language (
  language_id INTEGER NOT NULL ,
  name CHAR(20) NOT NULL,
  last_update TIMESTAMP NOT NULL,
  PRIMARY KEY (language_id)
);

CREATE TABLE payment (
  payment_id INTEGER NOT NULL,
  customer_id INT  NOT NULL,
  staff_id INT NOT NULL,
  rental_id INT DEFAULT NULL,
  amount DECIMAL(5,2) NOT NULL,
  payment_date TIMESTAMP NOT NULL,
  last_update TIMESTAMP NOT NULL,
  PRIMARY KEY  (payment_id),
  CONSTRAINT fk_payment_rental FOREIGN KEY (rental_id) REFERENCES rental (rental_id) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT fk_payment_customer FOREIGN KEY (customer_id) REFERENCES customer (customer_id) ,
  CONSTRAINT fk_payment_staff FOREIGN KEY (staff_id) REFERENCES staff (staff_id)
);

CREATE TABLE rental (
  rental_id INTEGER NOT NULL,
  rental_date TIMESTAMP NOT NULL,
  inventory_id INT  NOT NULL,
  customer_id INT  NOT NULL,
  return_date TIMESTAMP DEFAULT NULL,
  staff_id INT  NOT NULL,
  last_update TIMESTAMP NOT NULL,
  PRIMARY KEY (rental_id),
  CONSTRAINT fk_rental_staff FOREIGN KEY (staff_id) REFERENCES staff (staff_id) ,
  CONSTRAINT fk_rental_inventory FOREIGN KEY (inventory_id) REFERENCES inventory (inventory_id) ,
  CONSTRAINT fk_rental_customer FOREIGN KEY (customer_id) REFERENCES customer (customer_id)
);

CREATE TABLE staff (
  staff_id INTEGER NOT NULL,
  first_name VARCHAR(45) NOT NULL,
  last_name VARCHAR(45) NOT NULL,
  address_id INT NOT NULL,
  picture BLOB DEFAULT NULL,
  email VARCHAR(50) DEFAULT NULL,
  store_id INT NOT NULL,
  active SMALLINT DEFAULT 1 NOT NULL,
  username VARCHAR(16) NOT NULL,
  password VARCHAR(40) DEFAULT NULL,
  last_update TIMESTAMP NOT NULL,
  PRIMARY KEY  (staff_id),
  CONSTRAINT fk_staff_store FOREIGN KEY (store_id) REFERENCES store (store_id) ON DELETE NO ACTION ON UPDATE CASCADE,
  CONSTRAINT fk_staff_address FOREIGN KEY (address_id) REFERENCES address (address_id) ON DELETE NO ACTION ON UPDATE CASCADE
);

CREATE TABLE store (
  store_id INTEGER NOT NULL,
  manager_staff_id INT NOT NULL,
  address_id INT NOT NULL,
  last_update TIMESTAMP NOT NULL,
  PRIMARY KEY  (store_id),
  CONSTRAINT fk_store_staff FOREIGN KEY (manager_staff_id) REFERENCES staff (staff_id) ,
  CONSTRAINT fk_store_address FOREIGN KEY (address_id) REFERENCES address (address_id)
);
```

## 数据字典

### actor

演员表，200 位演员。演员和影片是多对多，经 film_actor 关联。注意与 customer、staff 区分：三张表都有 first_name、last_name，本表是**演员**。

| 字段 | 类型 | 说明 |
|---|---|---|
| actor_id | INTEGER | 演员唯一标识。 |
| first_name | VARCHAR(45) | 演员的名，全大写英文，例如 PENELOPE。customer.first_name 是客户的名，staff.first_name 是员工的名。 |
| last_name | VARCHAR(45) | 演员的姓，全大写英文，例如 GUINESS。 |
| last_update | TIMESTAMP | 演员这一行最后一次被修改的时间（数据维护用），集中在 2006-02-15 前后。不是业务时间：问租借、付款、注册发生在什么时候时不要用它。 |

### address

地址表，603 个地址，客户、员工、门店的地址都在这里（customer、staff、store 各有 address_id）。地址只到街道，城市在 city 表、国家在 country 表。区（district）和电话（phone）这两列没有数据。

| 字段 | 类型 | 说明 |
|---|---|---|
| address_id | INTEGER | 地址唯一标识。 |
| address | VARCHAR(50) | 街道地址，例如 47 MySakila Drive。 |
| address2 | VARCHAR(50) | 地址第二行，全部为空。 |
| district | VARCHAR(20) | 地址所在的区、省或州。这份 SQLite 数据里 603 行全是一个空格，没有数据：按省、州统计答不了，地域只能到城市（city）和国家（country）。 |
| city_id | INT | 所在城市，外键指向 city.city_id。 |
| postal_code | VARCHAR(10) | 邮编，有 4 个为空。 |
| phone | VARCHAR(20) | 联系电话（客户、员工、门店的电话都记在地址上）。这份 SQLite 数据里 603 行全是一个空格，没有电话数据。 |
| last_update | TIMESTAMP | 地址这一行最后一次被修改的时间（数据维护用），集中在 2006-02-15 前后。不是业务时间：问租借、付款、注册发生在什么时候时不要用它。 |

### category

影片分类表，16 个类型，例如 Action、Comedy、Horror。注意 name 字段：本表是分类名，language.name 是语言名。

| 字段 | 类型 | 说明 |
|---|---|---|
| category_id | INTEGER | 分类唯一标识。 |
| name | VARCHAR(25) | 分类名称，英文，例如 Action、Animation、Children、Comedy、Documentary、Horror。 |
| last_update | TIMESTAMP | 分类这一行最后一次被修改的时间（数据维护用），集中在 2006-02-15 前后。不是业务时间：问租借、付款、注册发生在什么时候时不要用它。 |

### city

城市表，600 个城市，每个城市属于一个国家。客户、门店的城市经 address.city_id 关联到这里。

| 字段 | 类型 | 说明 |
|---|---|---|
| city_id | INTEGER | 城市唯一标识。 |
| city | VARCHAR(50) | 城市名称，英文，例如 Lethbridge、Woodridge。有一个重名：London 有两个（英国、加拿大），按城市分组时连同 city_id 一起分组更稳。 |
| country_id | INT | 所属国家，外键指向 country.country_id。 |
| last_update | TIMESTAMP | 城市这一行最后一次被修改的时间（数据维护用），集中在 2006-02-15 前后。不是业务时间：问租借、付款、注册发生在什么时候时不要用它。 |

### country

国家表，109 个国家。客户、门店的国家经 address → city → country 关联到这里。

| 字段 | 类型 | 说明 |
|---|---|---|
| country_id | INTEGER | 国家唯一标识。 |
| country | VARCHAR(50) | 国家名称，英文，例如 Canada、Australia、United States。 |
| last_update | TIMESTAMP | 国家这一行最后一次被修改的时间（数据维护用），集中在 2006-02-15 前后。不是业务时间：问租借、付款、注册发生在什么时候时不要用它。 |

### customer

客户表，599 位租碟的顾客，记录姓名、邮箱、地址和注册门店。注意与 staff、actor 区分：三张表都有 first_name、last_name，本表是**租东西的客户**。客户住在哪个城市、国家，要经 address → city → country 三层关联。

| 字段 | 类型 | 说明 |
|---|---|---|
| customer_id | INTEGER | 客户唯一标识。 |
| store_id | INT | 客户注册所在的门店，外键指向 store.store_id。是客户归属哪家店，不是每笔租借在哪家店办的：租借在哪家店，看租出去的那张拷贝 inventory.store_id。 |
| first_name | VARCHAR(45) | 客户的名，全大写英文，例如 MARY。actor.first_name 是演员的名，staff.first_name 是员工的名。 |
| last_name | VARCHAR(45) | 客户的姓，全大写英文，例如 SMITH。 |
| email | VARCHAR(50) | 客户邮箱。staff.email 是员工邮箱。 |
| address_id | INT | 客户地址，外键指向 address.address_id。 |
| active | CHAR(1) | 是否活跃客户，'1' 是活跃（584 位）、'0' 是不活跃（15 位）。存的是字符。 |
| create_date | TIMESTAMP | 客户记录的创建时间。599 位客户全在 2006-02-14 22:04 这一刻，是导入数据的时间，不能当注册时间做分析。 |
| last_update | TIMESTAMP | 客户这一行最后一次被修改的时间（数据维护用），集中在 2006-02-15 前后。不是业务时间：问租借、付款、注册发生在什么时候时不要用它。 |

### film

影片表，1000 部影片（片名、简介、时长、分级、租借定价）。一部影片可以有多张实体拷贝放在门店里出租，拷贝在 inventory 表；租借记录挂在拷贝上，不直接挂在影片上：影片 → inventory → rental。所有影片的上映年份都是 2006、语言都是英语。

| 字段 | 类型 | 说明 |
|---|---|---|
| film_id | INTEGER | 影片唯一标识。 |
| title | VARCHAR(255) | 片名，全大写英文，例如 ACADEMY DINOSAUR。问“哪部电影/片名是什么”时输出这个字段。 |
| description | BLOB SUB_TYPE TEXT | 影片简介，一句英文剧情概要。 |
| release_year | VARCHAR(4) | 上映年份。1000 部影片全是 2006，按年份分组没有区分度。 |
| language_id | INT | 影片语言，外键指向 language.language_id。全部影片都是 1（English）。 |
| original_language_id | INT | 原始语言，外键指向 language.language_id。全部为空，没有数据。 |
| rental_duration | SMALLINT | 租期：这部影片一次可以租几天（3 到 7 天），是规定的期限，不是实际租了多久。实际租了多久要用 rental.return_date 减 rental.rental_date；超过租期就是逾期。 |
| rental_rate | DECIMAL(4,2) | 租借标价：租一次（一个租期）要付多少钱，取值 0.99、2.99、4.99。是定价，不是收入；实际收了多少钱看 payment.amount（含逾期费，可能和标价不同）。 |
| length | SMALLINT | 片长，单位分钟（46 到 185）。 |
| replacement_cost | DECIMAL(5,2) | 赔偿价：拷贝丢失或损坏时顾客要赔的钱（9.99 到 29.99）。不是租金，也不是收入。 |
| rating | VARCHAR(10) | 美国电影分级，取值 G、PG、PG-13、R、NC-17。 |
| special_features | VARCHAR(100) | 附赠内容，逗号分隔的组合，取值来自 Trailers、Commentaries、Deleted Scenes、Behind the Scenes 四种，例如 Trailers,Commentaries。判断带不带某一种用 LIKE '%Trailers%'。 |
| last_update | TIMESTAMP | 影片这一行最后一次被修改的时间（数据维护用），集中在 2006-02-15 前后。不是业务时间：问租借、付款、注册发生在什么时候时不要用它。 |

### film_actor

影片与演员的关联表（多对多），5462 行：一行表示某位演员出演了某部影片。

| 字段 | 类型 | 说明 |
|---|---|---|
| actor_id | INT | 演员，外键指向 actor.actor_id。 |
| film_id | INT | 影片，外键指向 film.film_id。 |
| last_update | TIMESTAMP | 这条出演记录这一行最后一次被修改的时间（数据维护用），集中在 2006-02-15 前后。不是业务时间：问租借、付款、注册发生在什么时候时不要用它。 |

### film_category

影片与分类的关联表，1000 行：每部影片恰好属于一个分类。

| 字段 | 类型 | 说明 |
|---|---|---|
| film_id | INT | 影片，外键指向 film.film_id。 |
| category_id | INT | 分类，外键指向 category.category_id。 |
| last_update | TIMESTAMP | 这条分类记录这一行最后一次被修改的时间（数据维护用），集中在 2006-02-15 前后。不是业务时间：问租借、付款、注册发生在什么时候时不要用它。 |

### inventory

库存表，4581 张实体拷贝（DVD）。一部影片可以有多张拷贝，分放在两家门店；有 42 部影片一张拷贝都没有。租借的是拷贝：rental.inventory_id 指向这里，要知道租的是哪部影片、在哪家店租的，都要经过本表。

| 字段 | 类型 | 说明 |
|---|---|---|
| inventory_id | INTEGER | 拷贝唯一标识。数“有多少张拷贝/库存多少张”就是数这个字段。 |
| film_id | INT | 这张拷贝是哪部影片，外键指向 film.film_id。 |
| store_id | INT | 这张拷贝放在哪家门店，外键指向 store.store_id。租借在哪家店办的、哪家店的出租量，按租出去的拷贝所在门店算，用这个字段；customer.store_id 是客户注册的门店。 |
| last_update | TIMESTAMP | 拷贝这一行最后一次被修改的时间（数据维护用），集中在 2006-02-15 前后。不是业务时间：问租借、付款、注册发生在什么时候时不要用它。 |

### language

语言表，6 种语言（English、Italian、Japanese、Mandarin、French、German）。影片实际只用到 English。注意 name 字段：本表是语言名，category.name 是分类名。

| 字段 | 类型 | 说明 |
|---|---|---|
| language_id | INTEGER | 语言唯一标识。 |
| name | CHAR(20) | 语言名称，英文，例如 English、Japanese。 |
| last_update | TIMESTAMP | 语言这一行最后一次被修改的时间（数据维护用），集中在 2006-02-15 前后。不是业务时间：问租借、付款、注册发生在什么时候时不要用它。 |

### payment

付款表，16049 笔，本库唯一的收入记录：营业额、收入、客户付了多少钱，都对 amount 求和。每笔付款对应一笔租借（rental_id），另有 5 笔没有关联租借。金额是实收，含逾期费，可能和影片标价 rental_rate 不同。

| 字段 | 类型 | 说明 |
|---|---|---|
| payment_id | INTEGER | 付款唯一标识。 |
| customer_id | INT | 付款的客户，外键指向 customer.customer_id。 |
| staff_id | INT | 收款的员工，外键指向 staff.staff_id。办理租借的员工是 rental.staff_id，两者有一半左右不是同一个人。 |
| rental_id | INT | 对应的租借，外键指向 rental.rental_id。有 5 笔为空。 |
| amount | DECIMAL(5,2) | 实收金额（0 到 11.99），含逾期费。营业额、收入、销售额、客户消费都是对它求和。 |
| payment_date | TIMESTAMP | 付款时间，带时分秒和毫秒。按月统计收入时用它；rental.rental_date 是租出时间。 |
| last_update | TIMESTAMP | 付款记录这一行最后一次被修改的时间（数据维护用），集中在 2006-02-15 前后。不是业务时间：问租借、付款、注册发生在什么时候时不要用它。 |

### rental

租借表，16044 笔：一位客户在某个时间租走一张拷贝，归还后记下归还时间。租借时间从 2005-05-24 到 2006-02-14，集中在 2005 年 5–8 月，2006 年只有 2 月的 182 笔。每笔租借恰好对应一笔付款（payment.rental_id）。租的是哪部影片要经 inventory 找到 film，在哪家店租的看 inventory.store_id。

| 字段 | 类型 | 说明 |
|---|---|---|
| rental_id | INTEGER | 租借唯一标识。数“租了多少次/出租量”就是数这个字段。 |
| rental_date | TIMESTAMP | 租出时间，带时分秒和毫秒，例如 2005-05-24 22:53:30.000。按租借发生的日期、月份统计时用它；payment.payment_date 是付款时间。 |
| inventory_id | INT | 租走的拷贝，外键指向 inventory.inventory_id。 |
| customer_id | INT | 租借的客户，外键指向 customer.customer_id。 |
| return_date | TIMESTAMP | 归还时间。为空表示还没还（183 笔）。实际租了多久 = 归还时间 − 租出时间；超过影片的租期 film.rental_duration 就是逾期。 |
| staff_id | INT | 办理这笔租借的员工，外键指向 staff.staff_id。收款员工是 payment.staff_id，可能是另一位。 |
| last_update | TIMESTAMP | 租借记录这一行最后一次被修改的时间（数据维护用），集中在 2006-02-15 前后。不是业务时间：问租借、付款、注册发生在什么时候时不要用它。 |

### staff

员工表，2 位员工（Mike Hillyer、Jon Stephens），各在一家门店上班，也是两家店的店长。注意与 customer、actor 区分：三张表都有 first_name、last_name，本表是**店员**。

| 字段 | 类型 | 说明 |
|---|---|---|
| staff_id | INTEGER | 员工唯一标识。 |
| first_name | VARCHAR(45) | 员工的名，例如 Mike。 |
| last_name | VARCHAR(45) | 员工的姓，例如 Hillyer。 |
| address_id | INT | 员工住址，外键指向 address.address_id。 |
| picture | BLOB | 员工照片，全部为空。 |
| email | VARCHAR(50) | 员工邮箱。customer.email 是客户邮箱。 |
| store_id | INT | 员工上班的门店，外键指向 store.store_id。 |
| active | SMALLINT | 是否在职，1 是在职。两位员工都在职。 |
| username | VARCHAR(16) | 员工登录用户名。 |
| password | VARCHAR(40) | 登录密码，已清空，不可用。 |
| last_update | TIMESTAMP | 员工这一行最后一次被修改的时间（数据维护用），集中在 2006-02-15 前后。不是业务时间：问租借、付款、注册发生在什么时候时不要用它。 |

### store

门店表，2 家门店，各有一位店长（manager_staff_id）和一个地址。门店本身没有名字，用 store_id（1、2）或门店地址所在城市来称呼。

| 字段 | 类型 | 说明 |
|---|---|---|
| store_id | INTEGER | 门店唯一标识，1 或 2。 |
| manager_staff_id | INT | 店长，外键指向 staff.staff_id。 |
| address_id | INT | 门店地址，外键指向 address.address_id。 |
| last_update | TIMESTAMP | 门店这一行最后一次被修改的时间（数据维护用），集中在 2006-02-15 前后。不是业务时间：问租借、付款、注册发生在什么时候时不要用它。 |
