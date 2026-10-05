# chinook（数字音乐商店） 数据库：Schema 与数据字典

SQLite 库文件：`chinook.db`，共 11 张表。

## 建表语句

```sql
CREATE TABLE [Album]
(
    [AlbumId] INTEGER  NOT NULL,
    [Title] NVARCHAR(160)  NOT NULL,
    [ArtistId] INTEGER  NOT NULL,
    CONSTRAINT [PK_Album] PRIMARY KEY  ([AlbumId]),
    FOREIGN KEY ([ArtistId]) REFERENCES [Artist] ([ArtistId]) 
		ON DELETE NO ACTION ON UPDATE NO ACTION
);

CREATE TABLE [Artist]
(
    [ArtistId] INTEGER  NOT NULL,
    [Name] NVARCHAR(120),
    CONSTRAINT [PK_Artist] PRIMARY KEY  ([ArtistId])
);

CREATE TABLE [Customer]
(
    [CustomerId] INTEGER  NOT NULL,
    [FirstName] NVARCHAR(40)  NOT NULL,
    [LastName] NVARCHAR(20)  NOT NULL,
    [Company] NVARCHAR(80),
    [Address] NVARCHAR(70),
    [City] NVARCHAR(40),
    [State] NVARCHAR(40),
    [Country] NVARCHAR(40),
    [PostalCode] NVARCHAR(10),
    [Phone] NVARCHAR(24),
    [Fax] NVARCHAR(24),
    [Email] NVARCHAR(60)  NOT NULL,
    [SupportRepId] INTEGER,
    CONSTRAINT [PK_Customer] PRIMARY KEY  ([CustomerId]),
    FOREIGN KEY ([SupportRepId]) REFERENCES [Employee] ([EmployeeId]) 
		ON DELETE NO ACTION ON UPDATE NO ACTION
);

CREATE TABLE [Employee]
(
    [EmployeeId] INTEGER  NOT NULL,
    [LastName] NVARCHAR(20)  NOT NULL,
    [FirstName] NVARCHAR(20)  NOT NULL,
    [Title] NVARCHAR(30),
    [ReportsTo] INTEGER,
    [BirthDate] DATETIME,
    [HireDate] DATETIME,
    [Address] NVARCHAR(70),
    [City] NVARCHAR(40),
    [State] NVARCHAR(40),
    [Country] NVARCHAR(40),
    [PostalCode] NVARCHAR(10),
    [Phone] NVARCHAR(24),
    [Fax] NVARCHAR(24),
    [Email] NVARCHAR(60),
    CONSTRAINT [PK_Employee] PRIMARY KEY  ([EmployeeId]),
    FOREIGN KEY ([ReportsTo]) REFERENCES [Employee] ([EmployeeId]) 
		ON DELETE NO ACTION ON UPDATE NO ACTION
);

CREATE TABLE [Genre]
(
    [GenreId] INTEGER  NOT NULL,
    [Name] NVARCHAR(120),
    CONSTRAINT [PK_Genre] PRIMARY KEY  ([GenreId])
);

CREATE TABLE [Invoice]
(
    [InvoiceId] INTEGER  NOT NULL,
    [CustomerId] INTEGER  NOT NULL,
    [InvoiceDate] DATETIME  NOT NULL,
    [BillingAddress] NVARCHAR(70),
    [BillingCity] NVARCHAR(40),
    [BillingState] NVARCHAR(40),
    [BillingCountry] NVARCHAR(40),
    [BillingPostalCode] NVARCHAR(10),
    [Total] NUMERIC(10,2)  NOT NULL,
    CONSTRAINT [PK_Invoice] PRIMARY KEY  ([InvoiceId]),
    FOREIGN KEY ([CustomerId]) REFERENCES [Customer] ([CustomerId]) 
		ON DELETE NO ACTION ON UPDATE NO ACTION
);

CREATE TABLE [InvoiceLine]
(
    [InvoiceLineId] INTEGER  NOT NULL,
    [InvoiceId] INTEGER  NOT NULL,
    [TrackId] INTEGER  NOT NULL,
    [UnitPrice] NUMERIC(10,2)  NOT NULL,
    [Quantity] INTEGER  NOT NULL,
    CONSTRAINT [PK_InvoiceLine] PRIMARY KEY  ([InvoiceLineId]),
    FOREIGN KEY ([InvoiceId]) REFERENCES [Invoice] ([InvoiceId]) 
		ON DELETE NO ACTION ON UPDATE NO ACTION,
    FOREIGN KEY ([TrackId]) REFERENCES [Track] ([TrackId]) 
		ON DELETE NO ACTION ON UPDATE NO ACTION
);

CREATE TABLE [MediaType]
(
    [MediaTypeId] INTEGER  NOT NULL,
    [Name] NVARCHAR(120),
    CONSTRAINT [PK_MediaType] PRIMARY KEY  ([MediaTypeId])
);

CREATE TABLE [Playlist]
(
    [PlaylistId] INTEGER  NOT NULL,
    [Name] NVARCHAR(120),
    CONSTRAINT [PK_Playlist] PRIMARY KEY  ([PlaylistId])
);

CREATE TABLE [PlaylistTrack]
(
    [PlaylistId] INTEGER  NOT NULL,
    [TrackId] INTEGER  NOT NULL,
    CONSTRAINT [PK_PlaylistTrack] PRIMARY KEY  ([PlaylistId], [TrackId]),
    FOREIGN KEY ([PlaylistId]) REFERENCES [Playlist] ([PlaylistId]) 
		ON DELETE NO ACTION ON UPDATE NO ACTION,
    FOREIGN KEY ([TrackId]) REFERENCES [Track] ([TrackId]) 
		ON DELETE NO ACTION ON UPDATE NO ACTION
);

CREATE TABLE [Track]
(
    [TrackId] INTEGER  NOT NULL,
    [Name] NVARCHAR(200)  NOT NULL,
    [AlbumId] INTEGER,
    [MediaTypeId] INTEGER  NOT NULL,
    [GenreId] INTEGER,
    [Composer] NVARCHAR(220),
    [Milliseconds] INTEGER  NOT NULL,
    [Bytes] INTEGER,
    [UnitPrice] NUMERIC(10,2)  NOT NULL,
    CONSTRAINT [PK_Track] PRIMARY KEY  ([TrackId]),
    FOREIGN KEY ([AlbumId]) REFERENCES [Album] ([AlbumId]) 
		ON DELETE NO ACTION ON UPDATE NO ACTION,
    FOREIGN KEY ([GenreId]) REFERENCES [Genre] ([GenreId]) 
		ON DELETE NO ACTION ON UPDATE NO ACTION,
    FOREIGN KEY ([MediaTypeId]) REFERENCES [MediaType] ([MediaTypeId]) 
		ON DELETE NO ACTION ON UPDATE NO ACTION
);
```

## 数据字典

### Album

专辑表，347 张。每张专辑属于且只属于一位艺术家，曲目通过 AlbumId 挂在专辑下。

| 字段 | 类型 | 说明 |
|---|---|---|
| AlbumId | INTEGER | 专辑唯一标识。 |
| Title | NVARCHAR(160) | 专辑名称，例如 Balls to the Wall。注意 Employee.Title 也叫 Title，那个是员工职位，两者毫无关系。 |
| ArtistId | INTEGER | 所属艺术家，外键指向 Artist.ArtistId。 |

### Artist

艺术家表，275 位。每位艺术家下挂若干张专辑，专辑下再挂曲目，是曲库三层结构的最上层。

| 字段 | 类型 | 说明 |
|---|---|---|
| ArtistId | INTEGER | 艺术家唯一标识。 |
| Name | NVARCHAR(120) | 艺术家名称，例如 AC/DC、Aerosmith。问“哪位艺术家/哪个歌手/哪支乐队叫什么”时输出这个字段。 |

### Customer

客户表，59 位买唱片的人，记录姓名、公司、联系方式和所在地，并挂着一位专属的销售支持员工（SupportRepId）。注意与 Employee 区分：本表是**买东西的客户**，Employee 是这家公司的员工，两张表有 11 个同名字段。本表只有联系方式与地址，没有出生日期、年龄、性别字段。

| 字段 | 类型 | 说明 |
|---|---|---|
| CustomerId | INTEGER | 客户唯一标识。 |
| FirstName | NVARCHAR(40) | 客户的名（given name），例如 Luís。Employee.FirstName 是员工的名，别取错表。 |
| LastName | NVARCHAR(20) | 客户的姓（family name），例如 Gonçalves。Employee.LastName 是员工的姓。 |
| Company | NVARCHAR(80) | 客户所属公司，多数为空（59 位客户里 49 位是个人，没有公司）。 |
| Address | NVARCHAR(70) | 客户的街道地址。Employee.Address 是员工住址，Invoice.BillingAddress 是开票地址。 |
| City | NVARCHAR(40) | 客户所在城市。同名字段有两个：Employee.City 是员工所在城市，Invoice.BillingCity 是开票城市。问客户在哪些城市用本字段。 |
| State | NVARCHAR(40) | 客户所在州/省，可为空。 |
| Country | NVARCHAR(40) | 客户所在国家，例如 Brazil、Germany、Canada。同名字段有两个：Employee.Country（员工所在国，全是 Canada）、Invoice.BillingCountry（开票国家）。问“客户分布在哪些国家”用本字段；问“哪个国家开票金额最高”应该用 Invoice.BillingCountry。 |
| PostalCode | NVARCHAR(10) | 客户邮编。 |
| Phone | NVARCHAR(24) | 客户电话。Employee.Phone 是员工电话。 |
| Fax | NVARCHAR(24) | 客户传真，可为空。 |
| Email | NVARCHAR(60) | 客户邮箱。Employee.Email 是员工邮箱（都是 @chinookcorp.com）。 |
| SupportRepId | INTEGER | 负责该客户的销售支持员工，外键指向 Employee.EmployeeId。这是客户与员工之间唯一的关联路径，做“每位销售支持了多少客户 / 带来多少销售额”时必走这里。 |

### Employee

员工表，8 人，记录姓名、职位、上下级关系、入职与出生日期、以及联系方式。这是**公司内部的员工**，不是客户；与 Customer 有 11 个同名字段，问客户属性时别落到这张表上。员工与客户的关系通过 Customer.SupportRepId 建立。

| 字段 | 类型 | 说明 |
|---|---|---|
| EmployeeId | INTEGER | 员工唯一标识。 |
| LastName | NVARCHAR(20) | 员工的姓。Customer.LastName 是客户的姓。 |
| FirstName | NVARCHAR(20) | 员工的名。Customer.FirstName 是客户的名。 |
| Title | NVARCHAR(30) | 员工职位，取值如 General Manager、Sales Manager、Sales Support Agent、IT Staff。注意 Album.Title 也叫 Title，那个是专辑名称。 |
| ReportsTo | INTEGER | 直属上级的员工 ID，外键指回本表 Employee.EmployeeId，是自引用层级。为空表示没有上级（总经理）；非空表示这名员工需要向上汇报。 |
| BirthDate | DATETIME | 员工出生日期。**只有员工有这个字段，客户没有**——Customer 表里不存在出生日期或年龄，所以“客户多少岁”这类问题本库答不了。 |
| HireDate | DATETIME | 员工入职日期。 |
| Address | NVARCHAR(70) | 员工住址。Customer.Address 是客户地址。 |
| City | NVARCHAR(40) | 员工所在城市，取值如 Edmonton、Calgary、Lethbridge。Customer.City 是客户所在城市，问员工在哪些城市用本字段。 |
| State | NVARCHAR(40) | 员工所在州/省，本库全为 AB。 |
| Country | NVARCHAR(40) | 员工所在国家，本库全为 Canada。Customer.Country 是客户所在国家，两者别混。 |
| PostalCode | NVARCHAR(10) | 员工邮编。 |
| Phone | NVARCHAR(24) | 员工电话。 |
| Fax | NVARCHAR(24) | 员工传真。 |
| Email | NVARCHAR(60) | 员工邮箱，域名均为 @chinookcorp.com。 |

### Genre

音乐流派表，25 种，取值如 Rock、Jazz、Metal、Latin。曲目通过 Track.GenreId 挂到流派上。

| 字段 | 类型 | 说明 |
|---|---|---|
| GenreId | INTEGER | 流派唯一标识。 |
| Name | NVARCHAR(120) | 流派名称，例如 Rock、Jazz、Metal。按流派分组统计时，输出的流派名就是这个字段；筛选“摇滚 / Rock 的曲目”也是在这个字段上过滤。 |

### Invoice

发票表，412 张，一张发票对应一位客户的一次购买。Total 已经是该发票所有明细行的合计，算销售总额直接对 Total 求和即可，不必再去 join InvoiceLine。开票地址是下单时写入的快照，与 Customer 当前地址未必一致。

| 字段 | 类型 | 说明 |
|---|---|---|
| InvoiceId | INTEGER | 发票唯一标识。统计“开了多少张发票”就是数这个字段。 |
| CustomerId | INTEGER | 下单客户，外键指向 Customer.CustomerId。 |
| InvoiceDate | DATETIME | 开票日期，本库唯一的业务时间字段——其他日期字段只有 Employee 的入职日期和出生日期，都不是交易时间。所有按年、按月、按时间段的销售分析都以它为准。 |
| BillingAddress | NVARCHAR(70) | 开票街道地址，下单时的快照。 |
| BillingCity | NVARCHAR(40) | 开票城市。与 Customer.City（客户当前城市）、Employee.City（员工城市）同为“城市”，但口径不同：本字段跟着这张发票走，做销售额地域拆分时用它。 |
| BillingState | NVARCHAR(40) | 开票州/省，可为空。 |
| BillingCountry | NVARCHAR(40) | 开票国家。做“哪个国家卖得最多、各国销售额”这类分析时用它，因为金额（Total）就挂在本表上，不用跨表。区别于 Customer.Country（客户登记的国家）与 Employee.Country（员工所在国家）。 |
| BillingPostalCode | NVARCHAR(10) | 开票邮编。 |
| Total | NUMERIC(10,2) | 发票总金额，等于该发票下所有明细行 UnitPrice × Quantity 之和。这是本库唯一的成交金额指标：问销售额、营收、开票金额、客户消费总额，都是对它求和。 |

### InvoiceLine

发票明细行，2240 行，一行表示某张发票买了某一首曲目。它是曲目与销售之间唯一的桥：算某首曲目/某个流派卖了多少钱、卖了多少份，都要从这里出发。

| 字段 | 类型 | 说明 |
|---|---|---|
| InvoiceLineId | INTEGER | 明细行唯一标识。 |
| InvoiceId | INTEGER | 所属发票，外键指向 Invoice.InvoiceId。按它分组可以得到每张发票有几个明细行。 |
| TrackId | INTEGER | 售出的曲目，外键指向 Track.TrackId。按它计数得到曲目销量——这才是“卖了多少”，PlaylistTrack.TrackId 是歌单收录，不是销量。 |
| UnitPrice | NUMERIC(10,2) | 成交单价，下单时写入的价格快照，取值 0.99 或 1.99。与 Track.UnitPrice 同名：那个是曲库里的目录标价，本字段是这笔交易实际成交的价格，两者可以不相等。 |
| Quantity | INTEGER | 购买数量，本库所有明细行都是 1。 |

### MediaType

媒体文件格式表，5 种，取值如 MPEG audio file、Protected AAC audio file、Protected MPEG-4 video file。描述的是文件编码格式，不是音乐风格。

| 字段 | 类型 | 说明 |
|---|---|---|
| MediaTypeId | INTEGER | 媒体格式唯一标识。 |
| Name | NVARCHAR(120) | 媒体格式名称，例如 MPEG audio file。这是文件编码格式，不是音乐流派，也不是歌名。 |

### Playlist

歌单表，18 个，取值如 Music、Movies、TV Shows、90’s Music。歌单与曲目是多对多，收录关系存在 PlaylistTrack。

| 字段 | 类型 | 说明 |
|---|---|---|
| PlaylistId | INTEGER | 歌单唯一标识。 |
| Name | NVARCHAR(120) | 歌单名称，例如 Music、Movies、90’s Music。 |

### PlaylistTrack

歌单与曲目的多对多收录关系表，8715 行，只有两个外键。一行表示“某首曲目被收录进某个歌单”。**它不是播放记录**：库里没有任何播放、收听、点击行为数据，因此无法回答播放次数、收听时长、最近播放时间这类问题。

| 字段 | 类型 | 说明 |
|---|---|---|
| PlaylistId | INTEGER | 所属歌单，外键指向 Playlist.PlaylistId。 |
| TrackId | INTEGER | 被收录的曲目，外键指向 Track.TrackId。按 TrackId 计数得到的是“这首曲目被几个歌单收录”，不是播放次数，也不是销量（销量看 InvoiceLine）。 |

### Track

曲目表，3503 首，是整个曲库的事实主体。一首曲目挂在一张专辑下，带一个流派、一种媒体格式，并通过 InvoiceLine 产生销售。

| 字段 | 类型 | 说明 |
|---|---|---|
| TrackId | INTEGER | 曲目唯一标识。 |
| Name | NVARCHAR(200) | 曲目名称，也就是歌名，例如 Fast As a Shark。问“哪首歌/曲目叫什么”时输出这个字段。 |
| AlbumId | INTEGER | 所属专辑，外键指向 Album.AlbumId。字段允许为空（单曲可以不属于任何专辑），本库中实际都有值。 |
| MediaTypeId | INTEGER | 媒体文件格式，外键指向 MediaType.MediaTypeId。 |
| GenreId | INTEGER | 所属音乐流派，外键指向 Genre.GenreId，本库中每首曲目都有流派。按流派（Rock、Jazz 等）分组统计曲目时必走这条关联。 |
| Composer | NVARCHAR(220) | 作曲者姓名，自由文本，多人以逗号分隔，约四分之一的曲目为空。它不是 Artist 表的外键——作曲者与表演的艺术家是两回事，库里也没有作曲者的独立维度表。 |
| Milliseconds | INTEGER | 曲目时长，单位毫秒。这是音频本身的长度，与播放行为无关——库里没有任何播放记录。 |
| Bytes | INTEGER | 音频文件大小，单位字节。 |
| UnitPrice | NUMERIC(10,2) | 曲目的目录标价，取值 0.99 或 1.99。这是曲库里挂出来的价格；实际成交价记在 InvoiceLine.UnitPrice，两者同名同类型，含义不同。 |
