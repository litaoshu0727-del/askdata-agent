# ecommerce（电商） 数据库：Schema 与数据字典

SQLite 库文件：`ecommerce.db`，共 11 张表。

## 建表语句

```sql
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
```

## 数据字典

### dim_user

用户维度表，记录用户的注册信息、所在城市、会员等级和注册渠道，是所有用户画像类分析的基础表。本表不含手机号、邮箱、身份证等联系方式与身份信息。

| 字段 | 类型 | 说明 |
|---|---|---|
| user_id | INTEGER | 用户唯一标识。 |
| user_name | TEXT | 用户昵称。当用户问“哪个用户/是谁/用户是谁”时，通常需要输出这个字段而不是 user_id。 |
| register_time | TEXT | 用户注册日期。注意与订单的下单时间区分，这里描述的是用户何时成为会员。 |
| city | TEXT | 用户所在城市。 |
| province | TEXT | 用户所在省份。 |
| gender | TEXT | 用户性别。 |
| age_group | TEXT | 用户年龄段分组，取值形如 18-24、25-30。注意：这是区间，不是精确年龄；库中没有出生日期，无法计算某个用户具体多少岁，问“具体年龄”应判定为缺失。 |
| member_level | TEXT | 会员等级，取值为普通会员、银卡会员、金卡会员、钻石会员。 |
| register_channel | TEXT | 用户注册来源渠道，取值为 APP、小程序、H5、PC官网。 |

### dim_category

商品类目表，两级类目结构，一级类目为美妆护肤、数码电器、食品生鲜，下挂二级类目。

| 字段 | 类型 | 说明 |
|---|---|---|
| category_id | INTEGER | 类目唯一标识。 |
| category_name | TEXT | 类目名称，例如美妆护肤、面部护肤、手机通讯。问“哪个类目”时输出这个字段而不是 category_id。 |
| parent_category_id | INTEGER | 父级类目ID，一级类目该字段为空，二级类目通过它指向所属的一级类目。 |
| category_level | INTEGER | 类目层级，1 为一级类目，2 为二级类目。 |

### dim_shop

店铺维度表，记录店铺名称、店铺类型、主营类目、所在城市和营业状态。本表不含员工、人员编制、经营面积等信息。

| 字段 | 类型 | 说明 |
|---|---|---|
| shop_id | INTEGER | 店铺唯一标识。 |
| shop_name | TEXT | 店铺名称。当用户问“哪些店铺/哪个店铺/店铺排行”时，通常需要输出这个字段而不是 shop_id。 |
| shop_type | TEXT | 店铺类型，取值为旗舰店、专营店、自营店、个人店。 |
| main_category_id | INTEGER | 店铺主营类目ID。 |
| city | TEXT | 店铺所在城市。注意这是店铺的经营地，不是买家所在地。 |
| open_time | TEXT | 店铺开业日期。 |
| shop_status | TEXT | 店铺营业状态，取值为正常营业、休假中、已关店。 |

### dim_product

商品维度表，记录商品名称、所属类目、所属店铺、品牌、标价和成本价。本表不含库存量、可售数量等库存信息。

| 字段 | 类型 | 说明 |
|---|---|---|
| product_id | INTEGER | 商品唯一标识。 |
| product_name | TEXT | 商品名称。当用户问“哪个商品/什么商品/商品叫什么”时，通常需要输出这个字段而不是 product_id。 |
| category_id | INTEGER | 商品所属的**二级**类目ID。商品只挂在二级类目上，从不直接挂一级类目——拿它去关联「美妆护肤」这类一级类目，结果永远是空的。 |
| shop_id | INTEGER | 商品所属店铺ID。 |
| brand | TEXT | 商品品牌。 |
| list_price | REAL | 商品标价，即商品挂牌单价，未计算任何优惠。 |
| cost_price | REAL | 商品成本价。 |
| shelf_status | TEXT | 商品上架状态，取值为在售、已下架、预售。 |

### fact_order

订单主表，一行一笔订单，记录订单的各项金额、订单状态、下单渠道和关键时间节点。是销售分析最核心的事实表。

| 字段 | 类型 | 说明 |
|---|---|---|
| order_id | INTEGER | 订单唯一标识，即订单号。 |
| user_id | INTEGER | 下单用户ID。 |
| shop_id | INTEGER | 下单店铺ID。 |
| order_amount | REAL | 订单商品总金额，即订单内所有商品按标价计算的总和，未扣除优惠、未加运费。 |
| discount_amount | REAL | 订单优惠总金额，包含商品折扣和优惠券抵扣。 |
| freight_amount | REAL | 订单运费金额。 |
| pay_amount | REAL | 订单实付金额，计算口径为订单商品总金额减去优惠金额再加上运费，即用户实际需要支付的钱。 |
| order_status | TEXT | 订单状态，取值为已完成、已支付、待支付、已取消、已退款。 |
| channel | TEXT | 下单渠道，取值为 APP、小程序、PC官网、直播间。按渠道筛选订单时用这个字段。 |
| create_time | TEXT | 订单创建时间，即用户下单的时间。 |
| pay_time | TEXT | 订单支付时间。未支付的订单该字段为空，因此常被用来判断订单是否已支付。 |
| finish_time | TEXT | 订单完成时间，即买家确认收货的时间。注意：库中没有发货时间，因此本字段减去 pay_time 得到的是“支付到确认收货”的总时长，包含商家备货时间，不等于物流时效、配送时长或签收时效，不能用来回答这类问题。 |

### fact_order_item

订单明细表，一行一个商品，记录订单中每个商品的购买数量、单价和明细金额。需要按商品或类目分析时要用这张表。

| 字段 | 类型 | 说明 |
|---|---|---|
| item_id | INTEGER | 订单明细唯一标识。 |
| order_id | INTEGER | 所属订单ID。 |
| product_id | INTEGER | 购买的商品ID。 |
| quantity | INTEGER | 该商品的购买数量（件数）。业务上说的“销量”指的是这个字段求和，不是订单行数。 |
| item_price | REAL | 下单时该商品的单价。 |
| item_discount_amount | REAL | 该商品行的优惠金额。 |
| item_amount | REAL | 该商品行的成交金额，计算口径为单价乘以数量再减去该行优惠。 |

### fact_payment

支付流水表，记录每笔订单的支付渠道、支付金额和支付状态，用于支付渠道分析。

| 字段 | 类型 | 说明 |
|---|---|---|
| payment_id | INTEGER | 支付流水唯一标识。 |
| order_id | INTEGER | 对应订单ID。 |
| pay_channel | TEXT | 支付渠道，取值为支付宝、微信支付、银行卡、花呗分期。 |
| pay_amount | REAL | 本笔支付流水的金额。 |
| pay_status | TEXT | 支付状态。 |
| pay_time | TEXT | 支付发生时间。 |

### fact_refund

退款记录表，记录退款金额、退款原因和退款状态，用于售后分析。

| 字段 | 类型 | 说明 |
|---|---|---|
| refund_id | INTEGER | 退款记录唯一标识。 |
| order_id | INTEGER | 退款对应的订单ID。 |
| refund_amount | REAL | 退款金额，可能是全额退款，也可能是部分退款。 |
| refund_reason | TEXT | 退款原因，取值为七天无理由、商品质量问题、发错货、物流损坏、拍错了。 |
| refund_status | TEXT | 退款状态，取值为退款成功、退款中。 |
| apply_time | TEXT | 退款申请时间。 |
| finish_time | TEXT | 退款完成时间，退款中的记录该字段为空。 |

### fact_user_behavior

用户行为表，记录用户对商品的浏览、加购、收藏行为及停留时长，用于转化漏斗分析。

| 字段 | 类型 | 说明 |
|---|---|---|
| behavior_id | INTEGER | 行为记录唯一标识。 |
| user_id | INTEGER | 产生行为的用户ID。 |
| product_id | INTEGER | 被操作的商品ID。 |
| behavior_type | TEXT | 行为类型，取值为浏览、加购、收藏。 |
| behavior_time | TEXT | 行为发生时间。 |
| stay_seconds | INTEGER | 本次行为的页面停留秒数。 |

### dws_user_summary

用户汇总表，由订单事实表聚合而来，记录每个用户的累计下单笔数、累计实付金额、客单价和退款订单数。查用户级累计指标时优先用这张表，不用再去聚合订单明细。

| 字段 | 类型 | 说明 |
|---|---|---|
| user_id | INTEGER | 用户唯一标识。 |
| total_order_count | INTEGER | 该用户累计下单笔数，含所有状态的订单。 |
| total_pay_amount | REAL | 该用户累计实付金额，即历史所有已支付订单的实付金额之和，可理解为用户消费总额。 |
| avg_order_amount | REAL | 该用户的平均订单金额，也就是通常说的客单价。 |
| refund_order_count | INTEGER | 该用户的退款订单笔数。 |
| active_days | INTEGER | 该用户有下单行为的天数。 |
| last_order_time | TEXT | 该用户最近一次下单时间。 |

### dws_shop_daily

店铺日汇总表，由订单事实表按**下单日期**聚合而来，记录每个店铺每天的 GMV、实付金额、订单量、买家数、退款金额和支付转化率。做店铺经营日报时用这张表。注意：表里所有指标都归属到订单的下单日期，包括退款——某天的 refund_amount 是「那天下的订单后来产生的退款」，不是「那天发生的退款」。

| 字段 | 类型 | 说明 |
|---|---|---|
| stat_date | TEXT | 统计日期，粒度为天，取的是订单的下单日期（fact_order.create_time 的日期部分）。本表所有指标都按这个日期归属。 |
| shop_id | INTEGER | 店铺ID。 |
| gmv | REAL | 店铺当日成交总额，口径为当天所有订单的商品总金额之和，业务上常说的销售额、成交额指的就是它。 |
| pay_amount | REAL | 店铺当日实付金额，只统计已支付订单。 |
| order_count | INTEGER | 店铺当日订单量。 |
| buyer_count | INTEGER | 店铺当日下单买家数，同一用户当天多次下单只计一次。 |
| refund_amount | REAL | 按订单下单日期归属的退款金额：当天下的订单后来产生的退款合计，**不是当天实际发生的退款**。全量合计与 fact_refund.refund_amount 相等，但按日期切分的结果完全不同。 |
| conversion_rate | REAL | 店铺当日支付转化率，口径为已支付买家数除以下单买家数，取值为 0 到 1 之间的小数。 |
