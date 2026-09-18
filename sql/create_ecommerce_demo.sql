-- ============================================================
-- AskData 电商数据分析 Demo 库
--
-- 分层设计（贴近真实数仓）：
--   dim_*  维度表：用户、店铺、商品、类目
--   fact_* 事实表：订单、订单明细、支付、退款、用户行为
--   dws_*  汇总表：用户汇总、店铺日汇总（由事实表聚合而来，数值保证一致）
--
-- 这套 Schema 刻意埋了几组"近义字段"，用来检验两阶段检索的区分能力：
--   金额类：order_amount / pay_amount / discount_amount / freight_amount
--           / refund_amount / item_amount / gmv / total_pay_amount / avg_order_amount
--   时间类：create_time / pay_time / finish_time / behavior_time / stat_date
--   pay_amount 同时存在于 fact_order 和 fact_payment，必须靠上下文区分
-- ============================================================

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS dws_shop_daily;
DROP TABLE IF EXISTS dws_user_summary;
DROP TABLE IF EXISTS fact_user_behavior;
DROP TABLE IF EXISTS fact_refund;
DROP TABLE IF EXISTS fact_payment;
DROP TABLE IF EXISTS fact_order_item;
DROP TABLE IF EXISTS fact_order;
DROP TABLE IF EXISTS dim_product;
DROP TABLE IF EXISTS dim_shop;
DROP TABLE IF EXISTS dim_category;
DROP TABLE IF EXISTS dim_user;


-- ---------- 维度层 ----------

CREATE TABLE dim_user (
    user_id          INTEGER PRIMARY KEY,
    user_name        TEXT    NOT NULL,
    register_time    TEXT    NOT NULL,
    city             TEXT    NOT NULL,
    province         TEXT    NOT NULL,
    gender           TEXT,
    age_group        TEXT,
    member_level     TEXT    NOT NULL,
    register_channel TEXT    NOT NULL
);

CREATE TABLE dim_category (
    category_id        INTEGER PRIMARY KEY,
    category_name      TEXT    NOT NULL,
    parent_category_id INTEGER,
    category_level     INTEGER NOT NULL
);

CREATE TABLE dim_shop (
    shop_id          INTEGER PRIMARY KEY,
    shop_name        TEXT    NOT NULL,
    shop_type        TEXT    NOT NULL,
    main_category_id INTEGER,
    city             TEXT    NOT NULL,
    open_time        TEXT    NOT NULL,
    shop_status      TEXT    NOT NULL,
    FOREIGN KEY (main_category_id) REFERENCES dim_category(category_id)
);

CREATE TABLE dim_product (
    product_id    INTEGER PRIMARY KEY,
    product_name  TEXT    NOT NULL,
    category_id   INTEGER NOT NULL,
    shop_id       INTEGER NOT NULL,
    brand         TEXT,
    list_price    REAL    NOT NULL,
    cost_price    REAL    NOT NULL,
    shelf_status  TEXT    NOT NULL,
    FOREIGN KEY (category_id) REFERENCES dim_category(category_id),
    FOREIGN KEY (shop_id)     REFERENCES dim_shop(shop_id)
);


-- ---------- 事实层 ----------

CREATE TABLE fact_order (
    order_id        INTEGER PRIMARY KEY,
    user_id         INTEGER NOT NULL,
    shop_id         INTEGER NOT NULL,
    order_amount    REAL    NOT NULL,
    discount_amount REAL    NOT NULL,
    freight_amount  REAL    NOT NULL,
    pay_amount      REAL    NOT NULL,
    order_status    TEXT    NOT NULL,
    channel         TEXT    NOT NULL,
    create_time     TEXT    NOT NULL,
    pay_time        TEXT,
    finish_time     TEXT,
    FOREIGN KEY (user_id) REFERENCES dim_user(user_id),
    FOREIGN KEY (shop_id) REFERENCES dim_shop(shop_id)
);

CREATE TABLE fact_order_item (
    item_id              INTEGER PRIMARY KEY,
    order_id             INTEGER NOT NULL,
    product_id           INTEGER NOT NULL,
    quantity             INTEGER NOT NULL,
    item_price           REAL    NOT NULL,
    item_discount_amount REAL    NOT NULL,
    item_amount          REAL    NOT NULL,
    FOREIGN KEY (order_id)   REFERENCES fact_order(order_id),
    FOREIGN KEY (product_id) REFERENCES dim_product(product_id)
);

CREATE TABLE fact_payment (
    payment_id  INTEGER PRIMARY KEY,
    order_id    INTEGER NOT NULL,
    pay_channel TEXT    NOT NULL,
    pay_amount  REAL    NOT NULL,
    pay_status  TEXT    NOT NULL,
    pay_time    TEXT    NOT NULL,
    FOREIGN KEY (order_id) REFERENCES fact_order(order_id)
);

CREATE TABLE fact_refund (
    refund_id     INTEGER PRIMARY KEY,
    order_id      INTEGER NOT NULL,
    refund_amount REAL    NOT NULL,
    refund_reason TEXT    NOT NULL,
    refund_status TEXT    NOT NULL,
    apply_time    TEXT    NOT NULL,
    finish_time   TEXT,
    FOREIGN KEY (order_id) REFERENCES fact_order(order_id)
);

CREATE TABLE fact_user_behavior (
    behavior_id   INTEGER PRIMARY KEY,
    user_id       INTEGER NOT NULL,
    product_id    INTEGER NOT NULL,
    behavior_type TEXT    NOT NULL,
    behavior_time TEXT    NOT NULL,
    stay_seconds  INTEGER NOT NULL,
    FOREIGN KEY (user_id)    REFERENCES dim_user(user_id),
    FOREIGN KEY (product_id) REFERENCES dim_product(product_id)
);


-- ---------- 汇总层 ----------

CREATE TABLE dws_user_summary (
    user_id            INTEGER PRIMARY KEY,
    total_order_count  INTEGER NOT NULL,
    total_pay_amount   REAL    NOT NULL,
    avg_order_amount   REAL    NOT NULL,
    refund_order_count INTEGER NOT NULL,
    active_days        INTEGER NOT NULL,
    last_order_time    TEXT,
    FOREIGN KEY (user_id) REFERENCES dim_user(user_id)
);

CREATE TABLE dws_shop_daily (
    stat_date       TEXT    NOT NULL,
    shop_id         INTEGER NOT NULL,
    gmv             REAL    NOT NULL,
    pay_amount      REAL    NOT NULL,
    order_count     INTEGER NOT NULL,
    buyer_count     INTEGER NOT NULL,
    refund_amount   REAL    NOT NULL,
    conversion_rate REAL    NOT NULL,
    PRIMARY KEY (stat_date, shop_id),
    FOREIGN KEY (shop_id) REFERENCES dim_shop(shop_id)
);
