"""
第九套留出评测集：Sakila，第三个库，验证泛化。由独立出题人在未见过被测系统表现和已有题目的情况下编写。
sakila 40 题（H9S01–H9S40，陷阱 4）。

**已用过一次。**这套题于 951bfe9 冻结并推送后第一次运行，三组都用冻结时的代码和评测器，每题 3 次，
结果见 docs/实验记录.md「第九套留出集：Sakila，换一个没见过的库」：

    组         端到端    运行通过   首轮检索召回
    完整       36/40     109/120    450/459
    无元数据   38/40     114/120    400/459
    无规则     38/40     110/120    450/459

组间逐题比都不显著（p≈0.69、1.00）。元数据的收益在检索（召回 87% → 98%），规则的收益在少写出跑不通的
SQL（执行报错后修正 24 → 4 次），端到端都没有测出差别。完整组剩下的失败都是已知的 SQL 结构错误。
运行中两次岔子（记录文件共用、两组没跑起来）都按事先写定的合并规则处理，见实验记录。
没有发现可证明没法判分的题，冻结版就是最终版。

当时的运行方案：

    完整       有业务元数据、有 SQL 规则——就是现在的系统
    无元数据   --meta none：手写的表描述、别名、辨析全丢掉，只留字段名、类型、样例值
    无规则     --sql-rules off：SQL 提示词里不放 SQLite 写法（那些规则是照电商、Chinook 的失败写的）

和留出集八（同样的难题规范，当前版本 88/90、60/60）对照，看换到没见过的库上掉多少；后两组看元数据、
规则各自在新库上值多少。

Sakila 的业务元数据在出题之前写好、先提交（4720176），写的时候一道题都没有，只描述 Schema 和数据。
出题规范在第八套那份上改的（eval/blind_materials/出题规范_第九套.md）：库换成 Sakila，40 题、陷阱 4、
至少覆盖 13 张表，去掉只适用于电商的默认口径。材料 sakila.md 由 make_dictionary.py 从库和元数据生成。
不读 README、docs/、eval/ 已有题目和 git 历史，不运行被测系统。

冻结前我没有读过题目：去重和机械校验全由脚本（eval/blind_materials/check_holdout.py）完成，只输出题号
和检查项；出题人的回报里也不含题目内容。组装进仓库时只换了导入、加了这段文件头。

候选路径的验证 SQL 在 eval/cases_holdout9_alt_sql.json。
冻结之后只允许修可证明没法判分的题，逐条记录，冻结版和修正版两个分数都报。

---- 以下是出题人写的说明 ----

第九套盲写评测题（Sakila，加难版）。

40 题：H9S01–H9S40，其中陷阱题 4 道（H9S09、H9S18、H9S27、H9S36）。
参考 SQL 均在 sakila.db（SQLite）上验证可执行、结果不退化、TopN 无并列。
"""

from eval.cases import EvalCase

HOLDOUT9_SAKILA_CASES = [
    EvalCase(
        id="H9S01",
        query="老板想知道钱主要是哪些国家的客户贡献的：按付钱的客户住在哪个国家算，所有付款都算进去（没对应到具体某次租借的付款也算），付款总额排前 5 的是哪几个国家？列出国家和总金额，金额保留两位小数。",
        reference_sql=(
            "SELECT co.country, ROUND(SUM(p.amount), 2) AS total_amount "
            "FROM payment p "
            "JOIN customer c ON c.customer_id = p.customer_id "
            "JOIN address a ON a.address_id = c.address_id "
            "JOIN city ci ON ci.city_id = a.city_id "
            "JOIN country co ON co.country_id = ci.country_id "
            "GROUP BY co.country_id, co.country "
            "ORDER BY SUM(p.amount) DESC "
            "LIMIT 5"
        ),
        must_hit_columns=[
            "country.country",
            "payment.amount",
            "payment.customer_id",
            "customer.address_id",
            "address.city_id",
            "city.country_id",
        ],
        tags=["难度:难", "考点:多表连接"],
        note="考付款经客户→地址→城市→国家的 5 表连接后按国家汇总取前 5，第 5、6 名相差 100 以上，无并列。题面写明按付钱的客户归属、所有付款都算（含 5 笔没有关联租借的付款），排除了绕道租借表找客户、漏掉这 5 笔的口径（那样 India、China、Japan 会少 1–4 元）。",
    ),
    EvalCase(
        id="H9S02",
        query="每个影片类型里，最能挣钱的两部片子是哪两部？列出类型、片名和这部片子一共收到的钱（保留两位小数）。",
        reference_sql=(
            "WITH film_rev AS ("
            "  SELECT cat.category_id, cat.name AS category, f.film_id, f.title, SUM(p.amount) AS rev "
            "  FROM payment p "
            "  JOIN rental r ON r.rental_id = p.rental_id "
            "  JOIN inventory i ON i.inventory_id = r.inventory_id "
            "  JOIN film f ON f.film_id = i.film_id "
            "  JOIN film_category fc ON fc.film_id = f.film_id "
            "  JOIN category cat ON cat.category_id = fc.category_id "
            "  GROUP BY cat.category_id, cat.name, f.film_id, f.title"
            "), ranked AS ("
            "  SELECT category, title, rev, "
            "         ROW_NUMBER() OVER (PARTITION BY category_id ORDER BY rev DESC) AS rn "
            "  FROM film_rev"
            ") "
            "SELECT category, title, ROUND(rev, 2) AS revenue FROM ranked WHERE rn <= 2"
        ),
        must_hit_columns=[
            "category.name",
            "film.title",
            "payment.amount",
            "payment.rental_id",
            "rental.inventory_id",
            "inventory.film_id",
            "film_category.category_id",
        ],
        tags=["难度:难", "考点:窗口排名", "考点:多表连接"],
        note="考分组取前 N：收入=付款金额，经付款→租借→拷贝→影片→类型 6 表连接，每类型取收入前 2；16 个类型的第 2、3 名均不并列。",
    ),
    EvalCase(
        id="H9S03",
        query="想看看客户都是被什么类型的片子'领进门'的：每位客户第一次来租的那部片子是什么类型，按类型数一数各有多少位客户。列出类型和客户数。",
        reference_sql=(
            "WITH first_rental AS ("
            "  SELECT r.customer_id, r.inventory_id FROM rental r "
            "  WHERE r.rental_date = (SELECT MIN(r2.rental_date) FROM rental r2 WHERE r2.customer_id = r.customer_id)"
            ") "
            "SELECT cat.name AS category, COUNT(*) AS customer_count "
            "FROM first_rental fr "
            "JOIN inventory i ON i.inventory_id = fr.inventory_id "
            "JOIN film_category fc ON fc.film_id = i.film_id "
            "JOIN category cat ON cat.category_id = fc.category_id "
            "GROUP BY cat.category_id, cat.name"
        ),
        must_hit_columns=[
            "rental.rental_date",
            "rental.customer_id",
            "rental.inventory_id",
            "inventory.film_id",
            "film_category.category_id",
            "category.name",
        ],
        tags=["难度:难", "考点:相对时间", "考点:两层聚合", "考点:多表连接"],
        note="考先取每位客户的首次租借（按租出时间，已验证 599 位客户的首次租借都没有同一时刻并列），再按该次影片的类型计数；16 个类型合计 599。",
    ),
    EvalCase(
        id="H9S04",
        query="有多少位客户是什么类型的片子都租过——店里的每一个影片类型都至少租过一部？",
        reference_sql=(
            "SELECT COUNT(*) AS customer_count FROM ("
            "  SELECT r.customer_id "
            "  FROM rental r "
            "  JOIN inventory i ON i.inventory_id = r.inventory_id "
            "  JOIN film_category fc ON fc.film_id = i.film_id "
            "  GROUP BY r.customer_id "
            "  HAVING COUNT(DISTINCT fc.category_id) = (SELECT COUNT(*) FROM category)"
            ")"
        ),
        must_hit_columns=[
            "rental.customer_id",
            "rental.inventory_id",
            "inventory.film_id",
            "film_category.category_id",
        ],
        tags=["难度:难", "考点:否定集合", "考点:两层聚合"],
        note="考'全都租过'的关系除法：按客户数租过的不同类型数，等于类型总数 16 的客户，答案 19。",
    ),
    EvalCase(
        id="H9S05",
        query="有多少位客户从来没租过 Horror 类的片子？",
        reference_sql=(
            "SELECT COUNT(*) AS customer_count FROM customer c "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM rental r "
            "  JOIN inventory i ON i.inventory_id = r.inventory_id "
            "  JOIN film_category fc ON fc.film_id = i.film_id "
            "  JOIN category cat ON cat.category_id = fc.category_id "
            "  WHERE cat.name = 'Horror' AND r.customer_id = c.customer_id"
            ")"
        ),
        must_hit_columns=[
            "customer.customer_id",
            "rental.customer_id",
            "rental.inventory_id",
            "inventory.film_id",
            "film_category.category_id",
            "category.name",
        ],
        tags=["难度:中等", "考点:否定集合", "考点:多表连接"],
        note="考'从没……'：全部 599 位客户中，在租借→拷贝→类型链路上找不到 Horror 的客户，答案 148。",
    ),
    EvalCase(
        id="H9S06",
        query="2005 年 5 月来租过碟、可 6 月一次都没来的客户有哪些？列出他们的名和姓。",
        reference_sql=(
            "SELECT c.first_name, c.last_name FROM customer c "
            "WHERE EXISTS (SELECT 1 FROM rental r WHERE r.customer_id = c.customer_id "
            "              AND r.rental_date >= '2005-05-01' AND r.rental_date < '2005-06-01') "
            "AND NOT EXISTS (SELECT 1 FROM rental r WHERE r.customer_id = c.customer_id "
            "                AND r.rental_date >= '2005-06-01' AND r.rental_date < '2005-07-01')"
        ),
        must_hit_columns=[
            "rental.rental_date",
            "rental.customer_id",
            "customer.first_name",
            "customer.last_name",
        ],
        tags=["难度:难", "考点:否定集合", "考点:相对时间"],
        note="考流失客户：5 月有租借且 6 月无租借，按租出时间算整月，8 人。",
    ),
    EvalCase(
        id="H9S07",
        query="2005 年 6、7、8 这三个月，每个月的营业额比上个月多了多少（少了就写负数）？月份按付款时间算，写成 2005-06 这样，金额保留两位小数。列出月份和变化的金额。",
        reference_sql=(
            "WITH m AS ("
            "  SELECT strftime('%Y-%m', payment_date) AS month, SUM(amount) AS rev "
            "  FROM payment GROUP BY strftime('%Y-%m', payment_date)"
            "), d AS ("
            "  SELECT month, rev - LAG(rev) OVER (ORDER BY month) AS diff FROM m"
            ") "
            "SELECT month, ROUND(diff, 2) AS change_amount FROM d "
            "WHERE month IN ('2005-06', '2005-07', '2005-08')"
        ),
        must_hit_columns=["payment.payment_date", "payment.amount"],
        tags=["难度:难", "考点:窗口排名", "考点:相对时间"],
        note="考环比：按付款月份汇总营业额后和上个月比（6 月和 5 月比），3 行；月份按付款时间已在题面写明（没有关联租借的 5 笔付款只有付款时间）。",
    ),
    EvalCase(
        id="H9S08",
        query="2005 年 7 月里，有租借的每一天各租出去多少次？顺便给出从 7 月 1 日算起、截至当天一共租出去多少次。列出日期（写成 2005-07-06 这样）、当天次数和累计次数。",
        reference_sql=(
            "WITH d AS ("
            "  SELECT date(rental_date) AS day, COUNT(*) AS cnt FROM rental "
            "  WHERE rental_date >= '2005-07-01' AND rental_date < '2005-08-01' "
            "  GROUP BY date(rental_date)"
            ") "
            "SELECT day, cnt AS daily_count, SUM(cnt) OVER (ORDER BY day) AS cumulative_count FROM d"
        ),
        must_hit_columns=["rental.rental_date", "rental.rental_id"],
        tags=["难度:难", "考点:窗口排名"],
        note="考累计：7 月只有 14 天有租借，按租出日期逐日计数并做当月累计，最后一天累计 6709（=7 月总数）。",
    ),
    EvalCase(
        id="H9S09",
        query="女客户和男客户，谁更爱租碟？各租了多少次？",
        reference_sql="SELECT 1 WHERE 0",
        must_hit_columns=[],
        tags=["难度:中等", "陷阱题"],
        note="陷阱题：库里没有客户性别信息（客户表只有姓名、邮箱、地址、门店、是否活跃），不能按名字猜性别。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H9S10",
        query="从租出到归还不超过 24 小时的租借有多少笔？正好 24 小时也算，还没还的不算。",
        reference_sql=(
            "SELECT COUNT(*) AS rental_count FROM rental "
            "WHERE return_date IS NOT NULL "
            "AND julianday(return_date) - julianday(rental_date) <= 1"
        ),
        must_hit_columns=["rental.return_date", "rental.rental_date"],
        tags=["难度:中等", "考点:相对时间"],
        note="考两个时间点的间隔：归还时间减租出时间 ≤ 24 小时，含正好 24 小时（有 2 笔），答案 848；按秒数算和按儒略日算结果一致。",
    ),
    EvalCase(
        id="H9S11",
        query="哪 3 个影片类型逾期还碟的次数最多？各逾期了多少次？逾期是指从租出到归还的实际时长（精确到秒）超过了这部片子规定的租期天数，还没还的不算。",
        reference_sql=(
            "SELECT cat.name AS category, COUNT(*) AS overdue_count "
            "FROM rental r "
            "JOIN inventory i ON i.inventory_id = r.inventory_id "
            "JOIN film f ON f.film_id = i.film_id "
            "JOIN film_category fc ON fc.film_id = f.film_id "
            "JOIN category cat ON cat.category_id = fc.category_id "
            "WHERE r.return_date IS NOT NULL "
            "AND julianday(r.return_date) - julianday(r.rental_date) > f.rental_duration "
            "GROUP BY cat.category_id, cat.name "
            "ORDER BY overdue_count DESC "
            "LIMIT 3"
        ),
        must_hit_columns=[
            "rental.return_date",
            "rental.rental_date",
            "film.rental_duration",
            "category.name",
            "film_category.category_id",
            "inventory.film_id",
        ],
        tags=["难度:难", "考点:多表连接", "考点:相对时间"],
        note="考逾期口径：精确时长严格大于租期天数（正好等于的 2 笔不算），5 表连接后按类型取前 3；第 3、4 名为 574 与 571，不并列。",
    ),
    EvalCase(
        id="H9S12",
        query="只看 2005 年的租借，同一位客户相邻两次来租碟之间最长隔了多少天？找出隔得最久的 3 位客户，列出名、姓和这个最长间隔（按精确到秒的时间差折成天数，保留两位小数）。",
        reference_sql=(
            "WITH g AS ("
            "  SELECT customer_id, "
            "         julianday(rental_date) - julianday(LAG(rental_date) OVER (PARTITION BY customer_id ORDER BY rental_date)) AS gap "
            "  FROM rental WHERE rental_date >= '2005-01-01' AND rental_date < '2006-01-01'"
            "), mx AS ("
            "  SELECT customer_id, MAX(gap) AS max_gap FROM g GROUP BY customer_id"
            ") "
            "SELECT c.first_name, c.last_name, ROUND(mx.max_gap, 2) AS max_gap_days "
            "FROM mx JOIN customer c ON c.customer_id = mx.customer_id "
            "ORDER BY mx.max_gap DESC "
            "LIMIT 3"
        ),
        must_hit_columns=[
            "rental.rental_date",
            "rental.customer_id",
            "customer.first_name",
            "customer.last_name",
        ],
        tags=["难度:难", "考点:窗口排名", "考点:相对时间"],
        note="考和上一条记录比较：每位客户 2005 年内按租出时间排序，相邻两次间隔取最大，再取前 3；限定 2005 年是为了排除 2005-08 到 2006-02 的断档。第 3、4 名为 39.19 与 38.86。",
    ),
    EvalCase(
        id="H9S13",
        query="有多少位客户曾经在同一天里一口气租了 5 张或更多的碟？'同一天'按租出日期的自然日算。",
        reference_sql=(
            "SELECT COUNT(DISTINCT customer_id) AS customer_count FROM ("
            "  SELECT customer_id, date(rental_date) AS d FROM rental "
            "  GROUP BY customer_id, date(rental_date) "
            "  HAVING COUNT(*) >= 5"
            ")"
        ),
        must_hit_columns=["rental.customer_id", "rental.rental_date"],
        tags=["难度:中等", "考点:两层聚合"],
        note="考先按客户×自然日计数、筛出 ≥5 的组合，再对客户去重计数：组合 45 个，客户 44 位（问的是客户数）。",
    ),
    EvalCase(
        id="H9S14",
        query="按每位客户第一次来租碟的月份算，每个月各来了多少位新客户？月份写成 2005-05 这样。",
        reference_sql=(
            "SELECT strftime('%Y-%m', first_date) AS month, COUNT(*) AS new_customers FROM ("
            "  SELECT customer_id, MIN(rental_date) AS first_date FROM rental GROUP BY customer_id"
            ") GROUP BY strftime('%Y-%m', first_date)"
        ),
        must_hit_columns=["rental.customer_id", "rental.rental_date"],
        tags=["难度:难", "考点:相对时间", "考点:两层聚合"],
        note="考首次：先取每位客户最早租出时间，再按其月份计数，3 行（不能用客户创建时间，那是导入时间）。",
    ),
    EvalCase(
        id="H9S15",
        query="按影片类型看，每个类型店里一共有多少张碟，这些碟一共被租出去过多少次？两家店合起来算，列出类型、碟的张数和出租次数。",
        reference_sql=(
            "WITH copies AS ("
            "  SELECT fc.category_id, COUNT(*) AS copy_count "
            "  FROM inventory i JOIN film_category fc ON fc.film_id = i.film_id "
            "  GROUP BY fc.category_id"
            "), rents AS ("
            "  SELECT fc.category_id, COUNT(*) AS rental_count "
            "  FROM rental r "
            "  JOIN inventory i ON i.inventory_id = r.inventory_id "
            "  JOIN film_category fc ON fc.film_id = i.film_id "
            "  GROUP BY fc.category_id"
            ") "
            "SELECT cat.name AS category, copies.copy_count, rents.rental_count "
            "FROM category cat "
            "JOIN copies ON copies.category_id = cat.category_id "
            "JOIN rents ON rents.category_id = cat.category_id"
        ),
        must_hit_columns=[
            "category.name",
            "film_category.category_id",
            "inventory.inventory_id",
            "rental.rental_id",
            "rental.inventory_id",
        ],
        tags=["难度:难", "考点:两层聚合", "考点:多表连接"],
        note="考不同粒度分别汇总再合并：拷贝数在库存粒度、出租次数在租借粒度，直接连在一起数会把拷贝数放大；拷贝数含 1 张从没租出过的拷贝，用内连接租借再去重会漏掉它。16 行。",
    ),
    EvalCase(
        id="H9S16",
        query="Woodridge 那家店的碟，2005 年 8 月一共被租出去多少次？",
        reference_sql=(
            "SELECT COUNT(*) AS rental_count "
            "FROM rental r "
            "JOIN inventory i ON i.inventory_id = r.inventory_id "
            "JOIN store s ON s.store_id = i.store_id "
            "JOIN address a ON a.address_id = s.address_id "
            "JOIN city ci ON ci.city_id = a.city_id "
            "WHERE ci.city = 'Woodridge' "
            "AND r.rental_date >= '2005-08-01' AND r.rental_date < '2005-09-01'"
        ),
        must_hit_columns=[
            "city.city",
            "store.address_id",
            "address.city_id",
            "inventory.store_id",
            "rental.rental_date",
        ],
        tags=["难度:难", "考点:多表连接"],
        note="考门店按地址城市称呼：门店→地址→城市定位 Woodridge 店，租借按拷贝所在门店归属（数据字典口径），5 表连接，答案 2885。",
    ),
    EvalCase(
        id="H9S17",
        query="有没有哪张碟从进店到现在一次都没被租出去过？列出这张碟的编号、片名和它放在几号店。",
        reference_sql=(
            "SELECT i.inventory_id, f.title, i.store_id "
            "FROM inventory i JOIN film f ON f.film_id = i.film_id "
            "WHERE NOT EXISTS (SELECT 1 FROM rental r WHERE r.inventory_id = i.inventory_id)"
        ),
        must_hit_columns=["inventory.inventory_id", "rental.inventory_id", "film.title", "inventory.store_id"],
        tags=["难度:中等", "考点:否定集合"],
        note="考拷贝粒度的'从没……'：4581 张拷贝中只有 1 张没有任何租借记录；问的是碟（拷贝）不是影片。",
    ),
    EvalCase(
        id="H9S18",
        query="哪位导演拍的片子在我们店被租得最多？列出导演和被租次数。",
        reference_sql="SELECT 1 WHERE 0",
        must_hit_columns=[],
        tags=["难度:中等", "陷阱题"],
        note="陷阱题：库里只有演员和影片的关系，没有导演信息，不能拿演员代替。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H9S19",
        query="片库里一部片子都没用到的语言有哪些？",
        reference_sql=(
            "SELECT l.name FROM language l "
            "WHERE NOT EXISTS (SELECT 1 FROM film f WHERE f.language_id = l.language_id)"
        ),
        must_hit_columns=["language.name", "film.language_id"],
        tags=["难度:简单", "考点:否定集合"],
        note="考语言表与影片语言的反连接：6 种语言里 5 种没有影片使用；原始语言全为空，不影响结果。",
    ),
    EvalCase(
        id="H9S20",
        query="跟 PENELOPE GUINESS 在同一部片子里合作过的演员有多少位？她自己不算，同一个人只算一次。",
        reference_sql=(
            "SELECT COUNT(DISTINCT fa2.actor_id) AS coactor_count "
            "FROM actor a "
            "JOIN film_actor fa1 ON fa1.actor_id = a.actor_id "
            "JOIN film_actor fa2 ON fa2.film_id = fa1.film_id AND fa2.actor_id <> fa1.actor_id "
            "WHERE a.first_name = 'PENELOPE' AND a.last_name = 'GUINESS'"
        ),
        must_hit_columns=["actor.first_name", "actor.last_name", "film_actor.actor_id", "film_actor.film_id"],
        tags=["难度:中等"],
        note="考出演关系自连接并去重：PENELOPE GUINESS 在演员表中唯一，答案 79。",
    ),
    EvalCase(
        id="H9S21",
        query="哪 3 位演员演的片子最能挣钱？一部片子收到的钱全额算到片中每位演员头上，列出演员的名、姓和金额（保留两位小数）。",
        reference_sql=(
            "SELECT a.first_name, a.last_name, ROUND(SUM(p.amount), 2) AS revenue "
            "FROM actor a "
            "JOIN film_actor fa ON fa.actor_id = a.actor_id "
            "JOIN inventory i ON i.film_id = fa.film_id "
            "JOIN rental r ON r.inventory_id = i.inventory_id "
            "JOIN payment p ON p.rental_id = r.rental_id "
            "GROUP BY a.actor_id, a.first_name, a.last_name "
            "ORDER BY SUM(p.amount) DESC "
            "LIMIT 3"
        ),
        must_hit_columns=[
            "actor.first_name",
            "actor.last_name",
            "film_actor.film_id",
            "inventory.film_id",
            "rental.inventory_id",
            "payment.rental_id",
            "payment.amount",
        ],
        tags=["难度:难", "考点:多表连接"],
        note="考演员→出演→拷贝→租借→付款 5 表连接，收入不拆分；按演员编号分组（演员表有同名 SUSAN DAVIS，但不在前列），第 3、4 名为 2689.25 与 2655.28。",
    ),
    EvalCase(
        id="H9S22",
        query="附赠内容里有 Behind the Scenes 的片子中，被租次数最多的 4 部是哪些？列出片名和被租次数。",
        reference_sql=(
            "SELECT f.title, COUNT(*) AS rental_count "
            "FROM film f "
            "JOIN inventory i ON i.film_id = f.film_id "
            "JOIN rental r ON r.inventory_id = i.inventory_id "
            "WHERE f.special_features LIKE '%Behind the Scenes%' "
            "GROUP BY f.film_id, f.title "
            "ORDER BY rental_count DESC "
            "LIMIT 4"
        ),
        must_hit_columns=["film.special_features", "film.title", "inventory.film_id", "rental.inventory_id"],
        tags=["难度:中等"],
        note="考逗号组合字段的包含判断 + 影片→拷贝→租借计数；第 4 名 32 次、第 5 名 31 次，不并列（取前 5 会并列，所以问前 4）。",
    ),
    EvalCase(
        id="H9S23",
        query="现在被借出去还没还回来的碟，要是都按赔偿价算，各家店分别值多少钱？按碟本来放在哪家店算，列出门店编号和金额（保留两位小数）。",
        reference_sql=(
            "SELECT i.store_id, ROUND(SUM(f.replacement_cost), 2) AS total_replacement_cost "
            "FROM rental r "
            "JOIN inventory i ON i.inventory_id = r.inventory_id "
            "JOIN film f ON f.film_id = i.film_id "
            "WHERE r.return_date IS NULL "
            "GROUP BY i.store_id"
        ),
        must_hit_columns=["rental.return_date", "inventory.store_id", "film.replacement_cost"],
        tags=["难度:中等"],
        note="考未还=归还时间为空（183 笔，各对应不同拷贝），金额用赔偿价而非租金，门店按拷贝所在门店；2 行。",
    ),
    EvalCase(
        id="H9S24",
        query="每家店租出去最多的 3 个影片类型是哪些？门店按碟放在哪家店算，列出门店编号、类型和出租次数。",
        reference_sql=(
            "WITH c AS ("
            "  SELECT i.store_id, cat.name AS category, COUNT(*) AS rental_count "
            "  FROM rental r "
            "  JOIN inventory i ON i.inventory_id = r.inventory_id "
            "  JOIN film_category fc ON fc.film_id = i.film_id "
            "  JOIN category cat ON cat.category_id = fc.category_id "
            "  GROUP BY i.store_id, cat.category_id, cat.name"
            "), ranked AS ("
            "  SELECT store_id, category, rental_count, "
            "         ROW_NUMBER() OVER (PARTITION BY store_id ORDER BY rental_count DESC) AS rn "
            "  FROM c"
            ") "
            "SELECT store_id, category, rental_count FROM ranked WHERE rn <= 3"
        ),
        must_hit_columns=[
            "inventory.store_id",
            "rental.inventory_id",
            "film_category.category_id",
            "category.name",
        ],
        tags=["难度:难", "考点:窗口排名", "考点:多表连接"],
        note="考分组前 N：租借→拷贝→类型 4 表连接，按拷贝所在门店分组取前 3；1 号店第 3、4 名 568/557，2 号店 598/580，不并列。",
    ),
    EvalCase(
        id="H9S25",
        query="在客户人数不少于 20 位的国家里，每个国家最舍得花钱的客户是谁？列出国家、客户的名和姓，以及他一共付了多少钱（保留两位小数）。",
        reference_sql=(
            "WITH cust AS ("
            "  SELECT co.country_id, co.country, c.customer_id, c.first_name, c.last_name "
            "  FROM customer c "
            "  JOIN address a ON a.address_id = c.address_id "
            "  JOIN city ci ON ci.city_id = a.city_id "
            "  JOIN country co ON co.country_id = ci.country_id"
            "), big AS ("
            "  SELECT country_id FROM cust GROUP BY country_id HAVING COUNT(*) >= 20"
            "), spend AS ("
            "  SELECT cust.country_id, cust.country, cust.first_name, cust.last_name, SUM(p.amount) AS total "
            "  FROM cust JOIN payment p ON p.customer_id = cust.customer_id "
            "  WHERE cust.country_id IN (SELECT country_id FROM big) "
            "  GROUP BY cust.country_id, cust.country, cust.customer_id, cust.first_name, cust.last_name"
            "), ranked AS ("
            "  SELECT country, first_name, last_name, total, "
            "         ROW_NUMBER() OVER (PARTITION BY country_id ORDER BY total DESC) AS rn "
            "  FROM spend"
            ") "
            "SELECT country, first_name, last_name, ROUND(total, 2) AS total_paid FROM ranked WHERE rn = 1"
        ),
        must_hit_columns=[
            "country.country",
            "customer.address_id",
            "address.city_id",
            "city.country_id",
            "customer.first_name",
            "customer.last_name",
            "payment.amount",
            "payment.customer_id",
        ],
        tags=["难度:难", "考点:窗口排名", "考点:多表连接", "考点:两层聚合"],
        note="考先按国家筛客户数 ≥20（8 个国家），再在国家内按客户付款总额取第 1；各国第 1、2 名均不并列（China 最接近：159.68 与 159.64）。",
    ),
    EvalCase(
        id="H9S26",
        query="有多少位客户的付款总额高于全体客户的人均付款额？",
        reference_sql=(
            "WITH t AS (SELECT customer_id, SUM(amount) AS total FROM payment GROUP BY customer_id) "
            "SELECT COUNT(*) AS customer_count FROM t "
            "WHERE total > (SELECT SUM(amount) * 1.0 / (SELECT COUNT(*) FROM customer) FROM payment)"
        ),
        must_hit_columns=["payment.customer_id", "payment.amount"],
        tags=["难度:中等", "考点:两层聚合"],
        note="考先按客户汇总、再和客户层面的平均比；599 位客户都有付款，人均=总额/599（等于各客户总额的平均），不是单笔付款的平均，答案 285。",
    ),
    EvalCase(
        id="H9S27",
        query="两位店员 2005 年 7 月的工资各是多少？",
        reference_sql="SELECT 1 WHERE 0",
        must_hit_columns=[],
        tags=["难度:中等", "陷阱题"],
        note="陷阱题：员工表没有工资、薪酬字段，经手收款金额不是工资。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H9S28",
        query="有多少部片子只在其中一家店有碟、另一家店一张都没有？",
        reference_sql=(
            "SELECT COUNT(*) AS film_count FROM ("
            "  SELECT film_id FROM inventory GROUP BY film_id HAVING COUNT(DISTINCT store_id) = 1"
            ")"
        ),
        must_hit_columns=["inventory.film_id", "inventory.store_id"],
        tags=["难度:中等", "考点:否定集合"],
        note="考'只……'：按影片数有拷贝的门店数，恰为 1 的影片 395 部；一张拷贝都没有的 42 部不算（题面要求在一家店有碟）。",
    ),
    EvalCase(
        id="H9S29",
        query="有多少部片子直到 2005 年 7 月才第一次被租出去？",
        reference_sql=(
            "SELECT COUNT(*) AS film_count FROM ("
            "  SELECT i.film_id, MIN(r.rental_date) AS first_date "
            "  FROM rental r JOIN inventory i ON i.inventory_id = r.inventory_id "
            "  GROUP BY i.film_id"
            ") WHERE first_date >= '2005-07-01' AND first_date < '2005-08-01'"
        ),
        must_hit_columns=["rental.rental_date", "rental.inventory_id", "inventory.film_id"],
        tags=["难度:难", "考点:相对时间", "考点:两层聚合"],
        note="考首次：先按影片取最早租出时间，再筛首次落在 2005 年 7 月的影片，答案 58；不能直接筛 7 月有租借的影片。",
    ),
    EvalCase(
        id="H9S30",
        query="哪位演员一部 G 级的片子都没演过？列出名和姓。",
        reference_sql=(
            "SELECT a.first_name, a.last_name FROM actor a "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM film_actor fa JOIN film f ON f.film_id = fa.film_id "
            "  WHERE fa.actor_id = a.actor_id AND f.rating = 'G'"
            ")"
        ),
        must_hit_columns=["film.rating", "film_actor.actor_id", "film_actor.film_id", "actor.first_name", "actor.last_name"],
        tags=["难度:中等", "考点:否定集合"],
        note="考'从没……'：200 位演员都有出演记录，只有 1 位没有任何 G 级影片。",
    ),
    EvalCase(
        id="H9S31",
        query="Lethbridge 那家店的店长一共经手收了多少钱？列出店长的名、姓和收款总额（保留两位小数）。",
        reference_sql=(
            "SELECT st.first_name, st.last_name, ROUND(SUM(p.amount), 2) AS total_collected "
            "FROM store s "
            "JOIN address a ON a.address_id = s.address_id "
            "JOIN city ci ON ci.city_id = a.city_id "
            "JOIN staff st ON st.staff_id = s.manager_staff_id "
            "JOIN payment p ON p.staff_id = st.staff_id "
            "WHERE ci.city = 'Lethbridge' "
            "GROUP BY st.staff_id, st.first_name, st.last_name"
        ),
        must_hit_columns=[
            "city.city",
            "store.address_id",
            "address.city_id",
            ["store.manager_staff_id", "staff.store_id"],
            "payment.staff_id",
            "payment.amount",
            "staff.first_name",
            "staff.last_name",
        ],
        tags=["难度:难", "考点:多表连接"],
        note="考城市→地址→门店→店长→收款 5 表连接；'经手收'按收款员工而非办理租借的员工。店长也可经员工所在门店找到（两条路径结果一致，见 alt_sql）。",
    ),
    EvalCase(
        id="H9S32",
        query="哪些城市住着不止一位客户？列出城市、所在国家和客户人数。",
        reference_sql=(
            "SELECT ci.city, co.country, COUNT(*) AS customer_count "
            "FROM customer c "
            "JOIN address a ON a.address_id = c.address_id "
            "JOIN city ci ON ci.city_id = a.city_id "
            "JOIN country co ON co.country_id = ci.country_id "
            "GROUP BY ci.city_id, ci.city, co.country "
            "HAVING COUNT(*) > 1"
        ),
        must_hit_columns=["city.city", "country.country", "customer.address_id", "address.city_id", "city.country_id"],
        tags=["难度:中等", "考点:多表连接"],
        note="考客户→地址→城市→国家 4 表连接后按城市（连同城市编号，London 有重名）计数筛选，2 行。",
    ),
    EvalCase(
        id="H9S33",
        query="跟 2005 年 7 月比，8 月出租次数掉得最多的 3 个影片类型是哪些？列出类型和少租了多少次（写成正数）。",
        reference_sql=(
            "WITH m AS ("
            "  SELECT cat.category_id, cat.name AS category, "
            "         SUM(CASE WHEN r.rental_date >= '2005-07-01' AND r.rental_date < '2005-08-01' THEN 1 ELSE 0 END) AS jul, "
            "         SUM(CASE WHEN r.rental_date >= '2005-08-01' AND r.rental_date < '2005-09-01' THEN 1 ELSE 0 END) AS aug "
            "  FROM rental r "
            "  JOIN inventory i ON i.inventory_id = r.inventory_id "
            "  JOIN film_category fc ON fc.film_id = i.film_id "
            "  JOIN category cat ON cat.category_id = fc.category_id "
            "  GROUP BY cat.category_id, cat.name"
            ") "
            "SELECT category, jul - aug AS decrease FROM m ORDER BY jul - aug DESC LIMIT 3"
        ),
        must_hit_columns=["rental.rental_date", "rental.inventory_id", "film_category.category_id", "category.name"],
        tags=["难度:难", "考点:相对时间", "考点:多表连接"],
        note="考比上个月：按类型分别数 7 月、8 月出租次数取差，降幅前 3；16 个类型都是下降，第 3、4 名降幅 80 与 77。",
    ),
    EvalCase(
        id="H9S34",
        query="按影片类型看，已经还回来的租借平均一次租了多少天？找出平均最长的 3 个类型，天数按租出到归还精确到秒的时间差折算，保留两位小数。",
        reference_sql=(
            "SELECT cat.name AS category, "
            "       ROUND(AVG(julianday(r.return_date) - julianday(r.rental_date)), 2) AS avg_days "
            "FROM rental r "
            "JOIN inventory i ON i.inventory_id = r.inventory_id "
            "JOIN film_category fc ON fc.film_id = i.film_id "
            "JOIN category cat ON cat.category_id = fc.category_id "
            "WHERE r.return_date IS NOT NULL "
            "GROUP BY cat.category_id, cat.name "
            "ORDER BY AVG(julianday(r.return_date) - julianday(r.rental_date)) DESC "
            "LIMIT 3"
        ),
        must_hit_columns=["rental.return_date", "rental.rental_date", "film_category.category_id", "category.name"],
        tags=["难度:难", "考点:相对时间", "考点:多表连接"],
        note="考实际租借时长（归还−租出，不是规定租期）按类型取平均，前 3：5.20/5.18/5.15，第 4 名 5.08。",
    ),
    EvalCase(
        id="H9S35",
        query="住在 Canada 的客户最爱租哪个类型的片子？列出类型和租借次数。",
        reference_sql=(
            "SELECT cat.name AS category, COUNT(*) AS rental_count "
            "FROM rental r "
            "JOIN customer c ON c.customer_id = r.customer_id "
            "JOIN address a ON a.address_id = c.address_id "
            "JOIN city ci ON ci.city_id = a.city_id "
            "JOIN country co ON co.country_id = ci.country_id "
            "JOIN inventory i ON i.inventory_id = r.inventory_id "
            "JOIN film_category fc ON fc.film_id = i.film_id "
            "JOIN category cat ON cat.category_id = fc.category_id "
            "WHERE co.country = 'Canada' "
            "GROUP BY cat.category_id, cat.name "
            "ORDER BY rental_count DESC "
            "LIMIT 1"
        ),
        must_hit_columns=[
            "country.country",
            "city.country_id",
            "address.city_id",
            "customer.address_id",
            "rental.customer_id",
            "rental.inventory_id",
            "film_category.category_id",
            "category.name",
        ],
        tags=["难度:难", "考点:多表连接"],
        note="考客户地理链路与租借→类型链路共 8 表连接；'最爱'按租借次数，第 1 名 15 次、第 2 名 14 次，不并列。",
    ),
    EvalCase(
        id="H9S36",
        query="扣掉房租、水电和人工这些开销之后，两家店 2005 年 7 月各净赚了多少钱？",
        reference_sql="SELECT 1 WHERE 0",
        must_hit_columns=[],
        tags=["难度:中等", "陷阱题"],
        note="陷阱题：库里只有收入（付款），没有房租、水电、人工等成本数据，算不出净利润。",
        expect_unanswerable=True,
    ),
    EvalCase(
        id="H9S37",
        query="租一次标价 4.99 的片子里，PG-13 级的有多少部？",
        reference_sql="SELECT COUNT(*) AS film_count FROM film WHERE rental_rate = 4.99 AND rating = 'PG-13'",
        must_hit_columns=["film.rental_rate", "film.rating"],
        tags=["难度:简单"],
        note="单表双条件计数：标价用租借定价而非实收，分级取值 PG-13，答案 77。",
    ),
    EvalCase(
        id="H9S38",
        query="2005 年 8 月一共收了多少钱？按付款时间算，保留两位小数。",
        reference_sql=(
            "SELECT ROUND(SUM(amount), 2) AS total_amount FROM payment "
            "WHERE payment_date >= '2005-08-01' AND payment_date < '2005-09-01'"
        ),
        must_hit_columns=["payment.amount", "payment.payment_date"],
        tags=["难度:简单"],
        note="单表按付款时间筛整月求和；题面写明按付款时间，含 1 笔没有关联租借的付款。",
    ),
    EvalCase(
        id="H9S39",
        query="两位店员各自哪一天收钱收得最多？按付款日期算，列出店员的名、姓、日期（写成 2005-08-01 这样）和当天收款总额（保留两位小数）。",
        reference_sql=(
            "WITH d AS ("
            "  SELECT p.staff_id, date(p.payment_date) AS day, SUM(p.amount) AS total "
            "  FROM payment p GROUP BY p.staff_id, date(p.payment_date)"
            "), ranked AS ("
            "  SELECT staff_id, day, total, "
            "         ROW_NUMBER() OVER (PARTITION BY staff_id ORDER BY total DESC) AS rn "
            "  FROM d"
            ") "
            "SELECT s.first_name, s.last_name, ranked.day, ROUND(ranked.total, 2) AS day_total "
            "FROM ranked JOIN staff s ON s.staff_id = ranked.staff_id "
            "WHERE ranked.rn = 1"
        ),
        must_hit_columns=["payment.staff_id", "payment.payment_date", "payment.amount", "staff.first_name", "staff.last_name"],
        tags=["难度:难", "考点:两层聚合", "考点:窗口排名"],
        note="考先按收款员工×付款日汇总，再在员工内取最高的一天；'收钱'按收款员工而非办理租借的员工。两人第 1、2 名均不并列（最接近 1442.55 与 1441.85）。",
    ),
    EvalCase(
        id="H9S40",
        query="既演过 Comedy 片、又演过 Horror 片的演员有多少位？",
        reference_sql=(
            "SELECT COUNT(*) AS actor_count FROM ("
            "  SELECT fa.actor_id "
            "  FROM film_actor fa "
            "  JOIN film_category fc ON fc.film_id = fa.film_id "
            "  JOIN category cat ON cat.category_id = fc.category_id "
            "  WHERE cat.name IN ('Comedy', 'Horror') "
            "  GROUP BY fa.actor_id "
            "  HAVING COUNT(DISTINCT cat.name) = 2"
            ")"
        ),
        must_hit_columns=["film_actor.actor_id", "film_actor.film_id", "film_category.category_id", "category.name"],
        tags=["难度:中等", "考点:否定集合"],
        note="考'同时……'：同一演员的出演影片中两个类型都出现，答案 115；不能用一行同时等于两个类型的写法。",
    ),
]
