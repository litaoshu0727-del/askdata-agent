"""
Chinook 数据集：一个我没有设计的 Schema。

前面所有数字都建立在一个闭环上——电商数据集是我造的，50 道题是我出的，
元数据也是我写的。「元数据质量决定召回准确率」这个结论，
在自己搭的场子里当然成立。

Chinook 是公开的音乐商店示例库，11 张表 64 个字段，英文命名，
自带的歧义比我刻意设计的还狠：

    Name        出现在 5 张表（Artist / Genre / MediaType / Playlist / Track）
    Customer 与 Employee 共享 11 个同名字段（City、Country、Email、Phone……）
    Title       Album 与 Employee 都有
    UnitPrice   Track 与 InvoiceLine 都有，含义不同

而且这些歧义**不是我埋的**——这正是它作为验证集的价值。

它同时测两件事：

1. 换个陌生 Schema 还行不行
2. 元数据到底值多少分

第二件事在这里能测干净：同一个库、同一套题、同一份代码，
唯一的变量是元数据的有无。两个函数各供一组——

    get_chinook_empty_meta()      对照组，一个字都不写
    get_chinook_business_meta()   实验组，11 张表 64 个字段逐一手写

差值就是元数据的价值。

数据来源：https://github.com/lerocha/chinook-database
"""

from __future__ import annotations

import shutil
from pathlib import Path

CHINOOK_SOURCE_ENV = "CHINOOK_DB"


def create_chinook_database(db_path: str | Path, source: str | Path | None = None) -> Path:
    """
    准备 Chinook 数据库。

    和另外两个数据集不同，这里不生成数据——直接复制现成的库文件。
    重点就在于"这不是我造的数据"。

    Args:
        db_path: 目标路径。
        source: 源文件路径。为空时读环境变量 CHINOOK_DB，
            再为空则在 runtime_data/chinook.db 找。
    """
    import os

    db_path = Path(db_path)

    candidates = [
        source,
        os.getenv(CHINOOK_SOURCE_ENV),
        Path("runtime_data") / "chinook.db",
    ]

    for candidate in candidates:
        if not candidate:
            continue

        candidate = Path(candidate)

        if candidate.is_file() and candidate.resolve() != db_path.resolve():
            db_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(candidate, db_path)
            return db_path

        if candidate.is_file():
            return candidate

    if db_path.is_file():
        return db_path

    raise FileNotFoundError(
        "找不到 Chinook 数据库。请下载后放到 runtime_data/chinook.db，"
        "或用 CHINOOK_DB 环境变量指定路径：\n"
        "  curl -L -o runtime_data/chinook.db "
        "https://github.com/lerocha/chinook-database/raw/master/"
        "ChinookDatabase/DataSources/Chinook_Sqlite.sqlite"
    )


def get_chinook_empty_meta() -> dict:
    """
    对照组：**一个字都不写**。

    检索只能靠字段名本身和 SQLite 里抽出来的样例值。
    英文字段名、中文提问，中间没有任何桥。
    """
    return {}


def get_chinook_business_meta() -> dict:
    """
    实验组：11 张表 64 个字段逐一手写。

    写的时候守一条纪律：**只描述 Schema，不看题目**。

    元数据里写的每一句话，都必须是"一个刚接手这个库的数据同学
    照着表结构和样例值就该写下来的话"。歧义辨析来自 Schema 自身
    （Name 在 5 张表里、Customer 与 Employee 同名字段、两个 UnitPrice），
    不来自题库——否则这份元数据就成了答案抄写，A/B 的差值也就没有意义。

    三件事最花时间：

    1. aliases 搭中英桥。用户问"艺人""歌单""开票金额"，
       字段名却是 Artist.Name、Playlist.Name、Invoice.Total。
    2. description 写清近义字段的差别。Track.UnitPrice 是目录标价，
       InvoiceLine.UnitPrice 是成交时的价格快照，两者可以不相等。
    3. 只给最容易混的字段手写 keyword_text，其余交给自动生成。

    **精排文本（rerank_text）一条都不手写**，辨析内容写进 description 和
    business_usage，由默认构建器统一生成。原因是实测出来的：

    手写的 rerank_text 会**整个替换**默认文本，而默认文本里带着表描述、别名、
    用途和样例值。最初给 23 个字段手写了精排文本，平均 105 字，没有一条带表描述。
    结果 Employee.FirstName（手写，79 字，一半篇幅在讲 Customer.FirstName）
    在「2003年入职的员工」这类问题上精排排到 16~18 / 20 名，被整个砍掉；
    同表的 Employee.LastName（没手写，默认文本 294 字，表描述里有"员工""入职""姓名"）
    稳定排前三。手写的精排文本比自动生成的还差。
    """
    meta = {}
    meta.update(_catalog_business_meta())
    meta.update(_sales_business_meta())
    return meta


def _catalog_business_meta() -> dict:
    """
    曲库侧：艺术家、专辑、曲目、流派、媒体格式、歌单。

    这半边的麻烦全集中在一个字段名上：Name 在 Artist、Genre、
    MediaType、Playlist、Track 五张表里都叫 Name，类型都是 NVARCHAR。
    光看字段名和类型，五个完全一样，只能靠描述和别名把它们分开。
    """
    return {
        "Artist": {
            "description": (
                "艺术家表，275 位。每位艺术家下挂若干张专辑，"
                "专辑下再挂曲目，是曲库三层结构的最上层。"
            ),
            "aliases": ["艺术家表", "歌手表", "艺人表", "乐队表", "表演者表"],
            "columns": {
                "ArtistId": {
                    "description": "艺术家唯一标识。",
                    "aliases": ["艺术家ID", "歌手ID", "艺人ID"],
                    "semantic_role": "join_key",
                    "business_usage": "关联 Album.ArtistId，统计艺术家数量时也直接数这个字段。",
                },
                "Name": {
                    "description": (
                        "艺术家名称，例如 AC/DC、Aerosmith。"
                        "问“哪位艺术家/哪个歌手/哪支乐队叫什么”时输出这个字段。"
                    ),
                    "aliases": ["艺术家", "艺术家名称", "歌手", "歌手名", "艺人", "乐队", "乐队名"],
                    "semantic_role": "output_dimension",
                    "business_usage": (
                        "艺术家排行、艺术家明细的展示字段。"
                        "五张表都有 Name 字段：本字段是艺术家（歌手、乐队）名；Track.Name 是歌名、Album.Title 是专辑名、Genre.Name 是流派名、Playlist.Name 是歌单名、MediaType.Name 是文件格式名。"
                    ),
                    "keyword_text": (
                        "Artist.Name 艺术家 艺术家名称 歌手 歌手名字 艺人 乐队 乐队名 表演者 "
                        "哪位艺术家 哪个歌手 艺术家叫什么 AC/DC Aerosmith Accept"
                    ),
                },
            },
        },
        "Album": {
            "description": (
                "专辑表，347 张。每张专辑属于且只属于一位艺术家，"
                "曲目通过 AlbumId 挂在专辑下。"
            ),
            "aliases": ["专辑表", "唱片表", "碟片表"],
            "columns": {
                "AlbumId": {
                    "description": "专辑唯一标识。",
                    "aliases": ["专辑ID", "唱片ID"],
                    "semantic_role": "join_key",
                },
                "Title": {
                    "description": (
                        "专辑名称，例如 Balls to the Wall。"
                        "注意 Employee.Title 也叫 Title，那个是员工职位，两者毫无关系。"
                    ),
                    "aliases": ["专辑名", "专辑名称", "唱片名", "专辑标题"],
                    "semantic_role": "output_dimension",
                    "business_usage": (
                        "专辑排行、专辑明细的展示字段。"
                        "问艺术家叫什么要取 Artist.Name，不是专辑名。"
                    ),
                    "keyword_text": (
                        "Album.Title 专辑 专辑名 专辑名称 唱片名 专辑标题 哪张专辑 专辑叫什么"
                    ),
                },
                "ArtistId": {
                    "description": "所属艺术家，外键指向 Artist.ArtistId。",
                    "aliases": ["艺术家ID", "所属艺术家"],
                    "semantic_role": "join_key",
                    "business_usage": "按艺术家统计专辑数量、或给专辑补上艺术家名字的必经路径。",
                },
            },
        },
        "Track": {
            "description": (
                "曲目表，3503 首，是整个曲库的事实主体。"
                "一首曲目挂在一张专辑下，带一个流派、一种媒体格式，"
                "并通过 InvoiceLine 产生销售。"
            ),
            "aliases": ["曲目表", "歌曲表", "音轨表", "单曲表"],
            "columns": {
                "TrackId": {
                    "description": "曲目唯一标识。",
                    "aliases": ["曲目ID", "歌曲ID", "音轨ID"],
                    "semantic_role": "join_key",
                    "business_usage": "关联 InvoiceLine.TrackId（销售）与 PlaylistTrack.TrackId（歌单收录）。",
                },
                "Name": {
                    "description": (
                        "曲目名称，也就是歌名，例如 Fast As a Shark。"
                        "问“哪首歌/曲目叫什么”时输出这个字段。"
                    ),
                    "aliases": ["曲目", "曲目名称", "歌名", "歌曲名", "单曲名", "音轨名"],
                    "semantic_role": "output_dimension",
                    "business_usage": (
                        "曲目排行、曲目明细的展示字段。"
                        "本字段是歌名；Artist.Name 是艺术家名、Album.Title 是专辑名、Genre.Name 是流派名、Playlist.Name 是歌单名。"
                    ),
                    "keyword_text": (
                        "Track.Name 曲目 曲目名称 歌名 歌曲名 单曲 音轨名 哪首歌 哪首曲目 歌曲叫什么"
                    ),
                },
                "AlbumId": {
                    "description": (
                        "所属专辑，外键指向 Album.AlbumId。"
                        "字段允许为空（单曲可以不属于任何专辑），本库中实际都有值。"
                    ),
                    "aliases": ["专辑ID", "所属专辑"],
                    "semantic_role": "join_key",
                },
                "MediaTypeId": {
                    "description": "媒体文件格式，外键指向 MediaType.MediaTypeId。",
                    "aliases": ["媒体格式ID", "文件格式ID"],
                    "semantic_role": "join_key",
                },
                "GenreId": {
                    "description": (
                        "所属音乐流派，外键指向 Genre.GenreId，本库中每首曲目都有流派。"
                        "按流派（Rock、Jazz 等）分组统计曲目时必走这条关联。"
                    ),
                    "aliases": ["流派ID", "曲风ID", "音乐类型ID", "所属流派"],
                    "semantic_role": "join_key",
                    "business_usage": "曲目与流派之间唯一的关联路径，按流派拆分曲目数、时长、销售额都要用它。",
                    "keyword_text": (
                        "Track.GenreId 流派 曲风 音乐流派 音乐类型 流派ID 按流派 每个流派 Rock Jazz Metal"
                    ),
                },
                "Composer": {
                    "description": (
                        "作曲者姓名，自由文本，多人以逗号分隔，约四分之一的曲目为空。"
                        "它不是 Artist 表的外键——作曲者与表演的艺术家是两回事，"
                        "库里也没有作曲者的独立维度表。"
                    ),
                    "aliases": ["作曲", "作曲者", "词曲作者", "创作者"],
                    "semantic_role": "dimension",
                },
                "Milliseconds": {
                    "description": (
                        "曲目时长，单位毫秒。这是音频本身的长度，"
                        "与播放行为无关——库里没有任何播放记录。"
                    ),
                    "aliases": ["时长", "曲目时长", "歌曲长度", "播放时长", "毫秒数"],
                    "semantic_role": "measure",
                    "business_usage": "按流派、专辑、艺术家汇总总时长时使用；除以 1000 得秒，除以 60000 得分钟。",
                    "keyword_text": (
                        "Track.Milliseconds 时长 曲目时长 歌曲长度 播放时长 总时长 毫秒 多长 多少毫秒"
                    ),
                },
                "Bytes": {
                    "description": "音频文件大小，单位字节。",
                    "aliases": ["文件大小", "字节数", "体积"],
                    "semantic_role": "measure",
                },
                "UnitPrice": {
                    "description": (
                        "曲目的目录标价，取值 0.99 或 1.99。"
                        "这是曲库里挂出来的价格；实际成交价记在 InvoiceLine.UnitPrice，"
                        "两者同名同类型，含义不同。"
                    ),
                    "aliases": ["单价", "曲目单价", "标价", "定价", "售价", "价格"],
                    "semantic_role": "measure",
                    "business_usage": "问“曲目卖多少钱、单价最高多少”时用它；问某张发票里的成交价用 InvoiceLine.UnitPrice。",
                    "keyword_text": (
                        "Track.UnitPrice 曲目单价 单价 标价 定价 售价 价格 曲目价格 多少钱 最贵 最高单价"
                    ),
                },
            },
        },
        "Genre": {
            "description": (
                "音乐流派表，25 种，取值如 Rock、Jazz、Metal、Latin。"
                "曲目通过 Track.GenreId 挂到流派上。"
            ),
            "aliases": ["流派表", "曲风表", "音乐类型表", "音乐风格表"],
            "columns": {
                "GenreId": {
                    "description": "流派唯一标识。",
                    "aliases": ["流派ID", "曲风ID"],
                    "semantic_role": "join_key",
                },
                "Name": {
                    "description": (
                        "流派名称，例如 Rock、Jazz、Metal。"
                        "按流派分组统计时，输出的流派名就是这个字段；"
                        "筛选“摇滚 / Rock 的曲目”也是在这个字段上过滤。"
                    ),
                    "aliases": ["流派", "流派名称", "曲风", "音乐类型", "音乐风格", "类型名称"],
                    "semantic_role": "output_dimension",
                    "business_usage": (
                        "流派维度的展示与筛选字段。"
                        "本字段是流派名；Track.Name 是歌名、MediaType.Name 是文件格式名、Playlist.Name 是歌单名。"
                    ),
                    "keyword_text": (
                        "Genre.Name 流派 流派名称 曲风 音乐类型 音乐风格 每个流派 按流派 "
                        "Rock 摇滚 Jazz 爵士 Metal 金属 Latin Pop"
                    ),
                },
            },
        },
        "MediaType": {
            "description": (
                "媒体文件格式表，5 种，取值如 MPEG audio file、"
                "Protected AAC audio file、Protected MPEG-4 video file。"
                "描述的是文件编码格式，不是音乐风格。"
            ),
            "aliases": ["媒体格式表", "文件格式表", "媒体类型表", "编码格式表"],
            "columns": {
                "MediaTypeId": {
                    "description": "媒体格式唯一标识。",
                    "aliases": ["媒体格式ID", "文件格式ID"],
                    "semantic_role": "join_key",
                },
                "Name": {
                    "description": (
                        "媒体格式名称，例如 MPEG audio file。"
                        "这是文件编码格式，不是音乐流派，也不是歌名。"
                    ),
                    "aliases": ["媒体格式", "文件格式", "媒体类型", "编码格式"],
                    "semantic_role": "output_dimension",
                    "business_usage": "只在问文件格式、编码方式时使用；问音乐类型、曲风、流派要取 Genre.Name。",
                },
            },
        },
        "Playlist": {
            "description": (
                "歌单表，18 个，取值如 Music、Movies、TV Shows、90’s Music。"
                "歌单与曲目是多对多，收录关系存在 PlaylistTrack。"
            ),
            "aliases": ["歌单表", "播放列表表", "列表表"],
            "columns": {
                "PlaylistId": {
                    "description": "歌单唯一标识。",
                    "aliases": ["歌单ID", "播放列表ID"],
                    "semantic_role": "join_key",
                },
                "Name": {
                    "description": "歌单名称，例如 Music、Movies、90’s Music。",
                    "aliases": ["歌单", "歌单名称", "播放列表", "播放列表名称"],
                    "semantic_role": "output_dimension",
                    "business_usage": "本字段是歌单名；Track.Name 是歌名、Genre.Name 是流派名。歌单只是收录关系，不代表被播放过。",
                },
            },
        },
        "PlaylistTrack": {
            "description": (
                "歌单与曲目的多对多收录关系表，8715 行，只有两个外键。"
                "一行表示“某首曲目被收录进某个歌单”。"
                "**它不是播放记录**：库里没有任何播放、收听、点击行为数据，"
                "因此无法回答播放次数、收听时长、最近播放时间这类问题。"
            ),
            "aliases": ["歌单曲目关系表", "歌单收录表", "播放列表明细表"],
            "columns": {
                "PlaylistId": {
                    "description": "所属歌单，外键指向 Playlist.PlaylistId。",
                    "aliases": ["歌单ID"],
                    "semantic_role": "join_key",
                },
                "TrackId": {
                    "description": (
                        "被收录的曲目，外键指向 Track.TrackId。"
                        "按 TrackId 计数得到的是“这首曲目被几个歌单收录”，"
                        "不是播放次数，也不是销量（销量看 InvoiceLine）。"
                    ),
                    "aliases": ["曲目ID"],
                    "semantic_role": "join_key",
                },
            },
        },
    }


def _sales_business_meta() -> dict:
    """
    销售侧：客户、员工、发票、发票明细。

    这半边的麻烦是另一种：Customer 和 Employee 共享 11 个同名字段——
    FirstName、LastName、Address、City、State、Country、PostalCode、
    Phone、Fax、Email，连类型都一样。中文问“城市”“国家”“邮箱”，
    字面上两张表打平，只能靠“这是客户的还是员工的”把它们分开。

    所以这部分每个同名字段都手写了 keyword_text，把“客户/买家”
    和“员工/雇员/职员”这组词分别焊进两边的索引文本里。
    """
    return {
        "Customer": {
            "description": (
                "客户表，59 位买唱片的人，记录姓名、公司、联系方式和所在地，"
                "并挂着一位专属的销售支持员工（SupportRepId）。"
                "注意与 Employee 区分：本表是**买东西的客户**，"
                "Employee 是这家公司的员工，两张表有 11 个同名字段。"
                "本表只有联系方式与地址，没有出生日期、年龄、性别字段。"
            ),
            "aliases": ["客户表", "顾客表", "买家表", "客户信息表"],
            "columns": {
                "CustomerId": {
                    "description": "客户唯一标识。",
                    "aliases": ["客户ID", "顾客ID", "买家ID"],
                    "semantic_role": "join_key",
                    "business_usage": "关联 Invoice.CustomerId，把发票归到客户身上。",
                },
                "FirstName": {
                    "description": (
                        "客户的名（given name），例如 Luís。"
                        "Employee.FirstName 是员工的名，别取错表。"
                    ),
                    "aliases": ["客户名", "客户的名", "名字", "客户姓名"],
                    "semantic_role": "output_dimension",
                    "business_usage": "问“哪个客户/客户是谁”时，通常与 LastName 一起输出。",
                    "keyword_text": (
                        "Customer.FirstName 客户 顾客 买家 客户姓名 客户的名 名字 "
                        "哪个客户 客户是谁 消费最多的客户"
                    ),
                },
                "LastName": {
                    "description": "客户的姓（family name），例如 Gonçalves。Employee.LastName 是员工的姓。",
                    "aliases": ["客户姓", "客户的姓", "姓氏", "客户姓名"],
                    "semantic_role": "output_dimension",
                    "keyword_text": (
                        "Customer.LastName 客户 顾客 买家 客户姓 姓氏 客户姓名 哪个客户 客户是谁"
                    ),
                },
                "Company": {
                    "description": "客户所属公司，多数为空（59 位客户里 49 位是个人，没有公司）。",
                    "aliases": ["公司", "客户公司", "所属公司", "单位"],
                    "semantic_role": "dimension",
                },
                "Address": {
                    "description": "客户的街道地址。Employee.Address 是员工住址，Invoice.BillingAddress 是开票地址。",
                    "aliases": ["客户地址", "地址", "街道地址"],
                    "semantic_role": "dimension",
                },
                "City": {
                    "description": (
                        "客户所在城市。"
                        "同名字段有两个：Employee.City 是员工所在城市，"
                        "Invoice.BillingCity 是开票城市。问客户在哪些城市用本字段。"
                    ),
                    "aliases": ["客户城市", "客户所在城市", "城市"],
                    "semantic_role": "dimension",
                    "business_usage": "按客户地域分析时使用。",
                    "keyword_text": (
                        "Customer.City 客户城市 客户所在城市 客户 顾客 买家 城市 客户分布 客户在哪些城市"
                    ),
                },
                "State": {
                    "description": "客户所在州/省，可为空。",
                    "aliases": ["客户州", "客户省份", "州", "省份"],
                    "semantic_role": "dimension",
                },
                "Country": {
                    "description": (
                        "客户所在国家，例如 Brazil、Germany、Canada。"
                        "同名字段有两个：Employee.Country（员工所在国，全是 Canada）、"
                        "Invoice.BillingCountry（开票国家）。"
                        "问“客户分布在哪些国家”用本字段；"
                        "问“哪个国家开票金额最高”应该用 Invoice.BillingCountry。"
                    ),
                    "aliases": ["客户国家", "客户所在国家", "国家", "客户地区"],
                    "semantic_role": "dimension",
                    "business_usage": "按客户国别做地域分布分析。",
                    "keyword_text": (
                        "Customer.Country 客户国家 客户所在国家 客户 顾客 买家 国家 "
                        "客户分布 客户来自哪些国家 地区分布"
                    ),
                },
                "PostalCode": {
                    "description": "客户邮编。",
                    "aliases": ["客户邮编", "邮政编码", "邮编"],
                    "semantic_role": "dimension",
                },
                "Phone": {
                    "description": "客户电话。Employee.Phone 是员工电话。",
                    "aliases": ["客户电话", "联系电话", "电话"],
                    "semantic_role": "dimension",
                },
                "Fax": {
                    "description": "客户传真，可为空。",
                    "aliases": ["客户传真", "传真"],
                    "semantic_role": "dimension",
                },
                "Email": {
                    "description": "客户邮箱。Employee.Email 是员工邮箱（都是 @chinookcorp.com）。",
                    "aliases": ["客户邮箱", "邮箱", "电子邮件"],
                    "semantic_role": "dimension",
                    "keyword_text": "Customer.Email 客户邮箱 客户 顾客 买家 邮箱 电子邮件 联系方式",
                },
                "SupportRepId": {
                    "description": (
                        "负责该客户的销售支持员工，外键指向 Employee.EmployeeId。"
                        "这是客户与员工之间唯一的关联路径，"
                        "做“每位销售支持了多少客户 / 带来多少销售额”时必走这里。"
                    ),
                    "aliases": ["支持代表", "销售代表", "客服代表", "对接员工"],
                    "semantic_role": "join_key",
                    "keyword_text": (
                        "Customer.SupportRepId 销售代表 支持代表 客服代表 对接员工 "
                        "负责的客户 员工 客户 关联"
                    ),
                },
            },
        },
        "Employee": {
            "description": (
                "员工表，8 人，记录姓名、职位、上下级关系、入职与出生日期、"
                "以及联系方式。这是**公司内部的员工**，不是客户；"
                "与 Customer 有 11 个同名字段，问客户属性时别落到这张表上。"
                "员工与客户的关系通过 Customer.SupportRepId 建立。"
            ),
            "aliases": ["员工表", "雇员表", "职员表", "人员表"],
            "columns": {
                "EmployeeId": {
                    "description": "员工唯一标识。",
                    "aliases": ["员工ID", "雇员ID", "工号"],
                    "semantic_role": "join_key",
                },
                "LastName": {
                    "description": "员工的姓。Customer.LastName 是客户的姓。",
                    "aliases": ["员工姓", "员工姓名", "姓氏"],
                    "semantic_role": "output_dimension",
                    "keyword_text": "Employee.LastName 员工 雇员 职员 员工姓 员工姓名 哪个员工 员工是谁",
                },
                "FirstName": {
                    "description": "员工的名。Customer.FirstName 是客户的名。",
                    "aliases": ["员工名", "员工姓名", "名字"],
                    "semantic_role": "output_dimension",
                    "keyword_text": "Employee.FirstName 员工 雇员 职员 员工名 员工姓名 哪个员工 员工是谁",
                },
                "Title": {
                    "description": (
                        "员工职位，取值如 General Manager、Sales Manager、"
                        "Sales Support Agent、IT Staff。"
                        "注意 Album.Title 也叫 Title，那个是专辑名称。"
                    ),
                    "aliases": ["职位", "岗位", "职务", "头衔"],
                    "semantic_role": "dimension",
                    "keyword_text": (
                        "Employee.Title 职位 岗位 职务 头衔 员工职位 经理 主管 "
                        "General Manager Sales Manager Sales Support Agent"
                    ),
                },
                "ReportsTo": {
                    "description": (
                        "直属上级的员工 ID，外键指回本表 Employee.EmployeeId，是自引用层级。"
                        "为空表示没有上级（总经理）；非空表示这名员工需要向上汇报。"
                    ),
                    "aliases": ["上级", "直属上级", "汇报对象", "上级ID", "汇报给"],
                    "semantic_role": "join_key",
                    "business_usage": "做组织层级、上下级关系分析；按是否为空判断有无上级。",
                    "keyword_text": (
                        "Employee.ReportsTo 上级 直属上级 汇报 汇报对象 向上汇报 "
                        "上下级 组织层级 管理者 下属"
                    ),
                },
                "BirthDate": {
                    "description": (
                        "员工出生日期。**只有员工有这个字段，客户没有**——"
                        "Customer 表里不存在出生日期或年龄，"
                        "所以“客户多少岁”这类问题本库答不了。"
                    ),
                    "aliases": ["出生日期", "生日", "员工生日"],
                    "semantic_role": "time",
                    "keyword_text": "Employee.BirthDate 出生日期 生日 年龄 员工生日 员工年龄 多少岁",
                },
                "HireDate": {
                    "description": "员工入职日期。",
                    "aliases": ["入职日期", "入职时间", "雇佣日期"],
                    "semantic_role": "time",
                },
                "Address": {
                    "description": "员工住址。Customer.Address 是客户地址。",
                    "aliases": ["员工地址", "住址"],
                    "semantic_role": "dimension",
                },
                "City": {
                    "description": (
                        "员工所在城市，取值如 Edmonton、Calgary、Lethbridge。"
                        "Customer.City 是客户所在城市，问员工在哪些城市用本字段。"
                    ),
                    "aliases": ["员工城市", "员工所在城市", "城市"],
                    "semantic_role": "dimension",
                    "keyword_text": (
                        "Employee.City 员工城市 员工所在城市 员工 雇员 职员 城市 "
                        "员工分布 员工在哪些城市"
                    ),
                    "business_usage": "问员工分布在哪些城市时取本字段；Customer.City 是客户所在城市，Invoice.BillingCity 是开票城市。",
                },
                "State": {
                    "description": "员工所在州/省，本库全为 AB。",
                    "aliases": ["员工州", "员工省份", "州", "省份"],
                    "semantic_role": "dimension",
                },
                "Country": {
                    "description": (
                        "员工所在国家，本库全为 Canada。"
                        "Customer.Country 是客户所在国家，两者别混。"
                    ),
                    "aliases": ["员工国家", "员工所在国家", "国家"],
                    "semantic_role": "dimension",
                    "keyword_text": "Employee.Country 员工国家 员工所在国家 员工 雇员 职员 国家 Canada",
                },
                "PostalCode": {
                    "description": "员工邮编。",
                    "aliases": ["员工邮编", "邮政编码", "邮编"],
                    "semantic_role": "dimension",
                },
                "Phone": {
                    "description": "员工电话。",
                    "aliases": ["员工电话", "联系电话", "电话"],
                    "semantic_role": "dimension",
                },
                "Fax": {
                    "description": "员工传真。",
                    "aliases": ["员工传真", "传真"],
                    "semantic_role": "dimension",
                },
                "Email": {
                    "description": "员工邮箱，域名均为 @chinookcorp.com。",
                    "aliases": ["员工邮箱", "邮箱", "电子邮件"],
                    "semantic_role": "dimension",
                    "keyword_text": "Employee.Email 员工邮箱 员工 雇员 职员 邮箱 电子邮件 chinookcorp",
                },
            },
        },
        "Invoice": {
            "description": (
                "发票表，412 张，一张发票对应一位客户的一次购买。"
                "Total 已经是该发票所有明细行的合计，"
                "算销售总额直接对 Total 求和即可，不必再去 join InvoiceLine。"
                "开票地址是下单时写入的快照，与 Customer 当前地址未必一致。"
            ),
            "aliases": ["发票表", "订单表", "账单表", "销售单表"],
            "columns": {
                "InvoiceId": {
                    "description": "发票唯一标识。统计“开了多少张发票”就是数这个字段。",
                    "aliases": ["发票ID", "订单ID", "账单ID", "发票号"],
                    "semantic_role": "join_key",
                    "keyword_text": (
                        "Invoice.InvoiceId 发票 发票ID 订单 账单 发票号 多少张发票 开票数量 发票数"
                    ),
                },
                "CustomerId": {
                    "description": "下单客户，外键指向 Customer.CustomerId。",
                    "aliases": ["客户ID", "下单客户"],
                    "semantic_role": "join_key",
                    "business_usage": "把发票金额归到客户身上，做客户消费排行的必经路径。",
                },
                "InvoiceDate": {
                    "description": (
                        "开票日期，本库唯一的业务时间字段——"
                        "其他日期字段只有 Employee 的入职日期和出生日期，都不是交易时间。"
                        "所有按年、按月、按时间段的销售分析都以它为准。"
                    ),
                    "aliases": ["开票日期", "开票时间", "下单时间", "购买时间", "交易时间", "日期"],
                    "semantic_role": "time",
                    "business_usage": (
                        "SQLite 里用 strftime('%Y', InvoiceDate) 取年份做年度统计。"
                        "Employee.HireDate（入职日期）和 Employee.BirthDate（出生日期）都不是交易时间。"
                    ),
                    "keyword_text": (
                        "Invoice.InvoiceDate 开票日期 开票时间 下单时间 购买时间 交易时间 "
                        "日期 年份 哪一年 每年 按月 时间范围"
                    ),
                },
                "BillingAddress": {
                    "description": "开票街道地址，下单时的快照。",
                    "aliases": ["开票地址", "账单地址"],
                    "semantic_role": "dimension",
                },
                "BillingCity": {
                    "description": (
                        "开票城市。与 Customer.City（客户当前城市）、"
                        "Employee.City（员工城市）同为“城市”，但口径不同："
                        "本字段跟着这张发票走，做销售额地域拆分时用它。"
                    ),
                    "aliases": ["开票城市", "账单城市", "销售城市"],
                    "semantic_role": "dimension",
                    "keyword_text": (
                        "Invoice.BillingCity 开票城市 账单城市 销售城市 发票 城市 按城市 销售额"
                    ),
                },
                "BillingState": {
                    "description": "开票州/省，可为空。",
                    "aliases": ["开票州", "账单省份"],
                    "semantic_role": "dimension",
                },
                "BillingCountry": {
                    "description": (
                        "开票国家。做“哪个国家卖得最多、各国销售额”这类分析时用它，"
                        "因为金额（Total）就挂在本表上，不用跨表。"
                        "区别于 Customer.Country（客户登记的国家）"
                        "与 Employee.Country（员工所在国家）。"
                    ),
                    "aliases": ["开票国家", "账单国家", "销售国家", "国家"],
                    "semantic_role": "dimension",
                    "business_usage": "按国家汇总开票金额、做地域销售排行。",
                    "keyword_text": (
                        "Invoice.BillingCountry 开票国家 账单国家 销售国家 国家 "
                        "按国家 各国 哪个国家 销售额最高的国家 开票金额"
                    ),
                },
                "BillingPostalCode": {
                    "description": "开票邮编。",
                    "aliases": ["开票邮编", "账单邮编"],
                    "semantic_role": "dimension",
                },
                "Total": {
                    "description": (
                        "发票总金额，等于该发票下所有明细行 UnitPrice × Quantity 之和。"
                        "这是本库唯一的成交金额指标：问销售额、营收、开票金额、"
                        "客户消费总额，都是对它求和。"
                    ),
                    "aliases": ["金额", "总金额", "发票金额", "开票金额", "销售额", "营收", "消费金额", "订单金额"],
                    "semantic_role": "measure",
                    "business_usage": (
                        "按客户、国家、时间汇总销售额时求和；不需要再 join 明细表重算。"
                        "Track.UnitPrice 是曲目标价，InvoiceLine.UnitPrice 是明细行成交单价，都不是发票总额。"
                    ),
                    "keyword_text": (
                        "Invoice.Total 金额 总金额 发票金额 开票金额 销售额 营收 收入 "
                        "消费金额 消费总额 花了多少钱 合计 总计 最高金额"
                    ),
                },
            },
        },
        "InvoiceLine": {
            "description": (
                "发票明细行，2240 行，一行表示某张发票买了某一首曲目。"
                "它是曲目与销售之间唯一的桥：算某首曲目/某个流派卖了多少钱、"
                "卖了多少份，都要从这里出发。"
            ),
            "aliases": ["发票明细表", "订单明细表", "明细行表", "销售明细表"],
            "columns": {
                "InvoiceLineId": {
                    "description": "明细行唯一标识。",
                    "aliases": ["明细行ID", "明细ID"],
                    "semantic_role": "join_key",
                },
                "InvoiceId": {
                    "description": (
                        "所属发票，外键指向 Invoice.InvoiceId。"
                        "按它分组可以得到每张发票有几个明细行。"
                    ),
                    "aliases": ["发票ID", "所属发票", "订单ID"],
                    "semantic_role": "join_key",
                    "business_usage": "统计每张发票的明细行数、平均每单几行商品。",
                    "keyword_text": (
                        "InvoiceLine.InvoiceId 发票ID 所属发票 明细行 每张发票 "
                        "平均每张发票 几个明细 行数"
                    ),
                },
                "TrackId": {
                    "description": (
                        "售出的曲目，外键指向 Track.TrackId。"
                        "按它计数得到曲目销量——这才是“卖了多少”，"
                        "PlaylistTrack.TrackId 是歌单收录，不是销量。"
                    ),
                    "aliases": ["曲目ID", "售出曲目"],
                    "semantic_role": "join_key",
                    "business_usage": "把销售额、销量归因到曲目、专辑、艺术家、流派的起点。",
                    "keyword_text": (
                        "InvoiceLine.TrackId 曲目ID 售出曲目 销量 卖了多少 曲目销量 最畅销 卖得最好"
                    ),
                },
                "UnitPrice": {
                    "description": (
                        "成交单价，下单时写入的价格快照，取值 0.99 或 1.99。"
                        "与 Track.UnitPrice 同名：那个是曲库里的目录标价，"
                        "本字段是这笔交易实际成交的价格，两者可以不相等。"
                    ),
                    "aliases": ["成交单价", "明细单价", "成交价", "单价"],
                    "semantic_role": "measure",
                    "business_usage": (
                        "算某首曲目/某个流派的销售额：SUM(UnitPrice * Quantity)。"
                        "也可以直接对 Invoice.Total 求和得到发票层面的金额。"
                    ),
                    "keyword_text": (
                        "InvoiceLine.UnitPrice 成交单价 成交价 明细单价 单价 销售额 卖了多少钱"
                    ),
                },
                "Quantity": {
                    "description": "购买数量，本库所有明细行都是 1。",
                    "aliases": ["数量", "购买数量", "份数"],
                    "semantic_role": "measure",
                    "business_usage": "算销售额时与 UnitPrice 相乘；算销量时求和。",
                },
            },
        },
    }
