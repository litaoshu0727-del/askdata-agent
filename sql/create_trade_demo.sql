PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS interest_info;
DROP TABLE IF EXISTS trade_summary;

CREATE TABLE trade_summary (
    user_id INTEGER PRIMARY KEY,
    total_trade_count INTEGER NOT NULL,
    total_trade_amount REAL NOT NULL,
    active_days INTEGER NOT NULL,
    last_trade_time TEXT
);

CREATE TABLE interest_info (
    user_id INTEGER PRIMARY KEY,
    interest_rate REAL NOT NULL,
    rate_type TEXT NOT NULL,
    effective_status TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES trade_summary(user_id)
);

INSERT INTO trade_summary (
    user_id,
    total_trade_count,
    total_trade_amount,
    active_days,
    last_trade_time
) VALUES
    (1001, 12,     5300.50,    5,   '2024-05-01'),
    (1002, 5800,   230000.00,  180, '2024-05-06'),
    (1003, 56000,  1800000.00, 320, '2024-05-10'),
    (1004, 102430, 3700000.00, 365, '2024-05-11'),
    (1005, 0,      0.00,       0,   NULL),
    (1006, 50001,  910000.00,  250, '2024-05-13'),
    (1007, 49999,  870000.00,  245, '2024-05-13'),
    (1008, 76000,  2500000.00, 330, '2024-05-14'),
    (1009, 340,    35000.00,   40,  '2024-05-15'),
    (1010, 88888,  3200000.00, 350, '2024-05-16');

INSERT INTO interest_info (
    user_id,
    interest_rate,
    rate_type,
    effective_status
) VALUES
    (1001, 2.35, 'standard',   'active'),
    (1002, 3.12, 'vip',        'active'),
    (1003, 4.58, 'high_value', 'active'),
    (1004, 4.95, 'high_value', 'active'),
    (1005, 1.80, 'standard',   'inactive'),
    (1006, 4.20, 'high_value', 'active'),
    (1007, 3.88, 'vip',        'active'),
    (1008, 5.15, 'high_value', 'inactive'),
    (1009, 2.80, 'standard',   'active'),
    (1010, 5.05, 'high_value', 'active');
