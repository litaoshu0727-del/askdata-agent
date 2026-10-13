"""
大库压力测试：电商库原样保留，再加 12 个相邻业务域的干扰表，凑到上千个字段。

所有结论原先都来自最多 81 个字段的库。真实数仓里，问题只涉及一小块，检索得从上千个字段里
把那几十个找出来；全量 Schema 也塞不进提示词，复核只能走有限扩展。这个库用来测这两件事。

怎么造的：

- **电商 11 张表一字不改**，已有的电商题在这个库上答案不变，仍然唯一
- **干扰域和电商"相邻但不重叠"**：人力、财务、采购、生产、运维、客服、广告、内容、行政、
  法务、培训、数据平台。有大量"金额、时间、状态、城市、名称"之类的通用字段，也有故意的
  近义字段（广告日报的转化率、内容日报的停留时长），但没有用户、订单、店铺、商品、退款
- **避开陷阱题的主题**：不放库存、物流时效、会员积分、优惠券、评价评分、主播、上架日期、
  手机号——否则"答不了"的陷阱题在这个库上就变得"像能答"，测出来的东西没法解读
- **干扰域之间、干扰域和电商之间都没有外键**，域内有外键（桥接表也要在大库上考一考）
- **元数据薄**：只有表描述和字段的中文名，没有手写辨析。真实数仓多数表就是这样，只有自己
  负责的那块写得细
- 每张干扰表带一组审计字段（创建 / 更新时间、创建人、备注、删除标记），真实数仓就是这样
- 固定随机种子，每张干扰表 30 行
"""

from __future__ import annotations

import random
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

from .ecommerce_data import CITIES, create_ecommerce_demo_database, get_ecommerce_business_meta

RANDOM_SEED = 20261013
ROWS_PER_TABLE = 30

# 字段写法：(字段名, 中文名, 类型)
#   id               主键，自增整数
#   fk:<表名>         外键，指向同域某张表的主键
#   name             名称列（output_dimension）
#   enum:a|b|c       枚举
#   city / money / int / ratio / datetime / date / text
Column = Tuple[str, str, str]

DOMAINS: Dict[str, Dict[str, dict]] = {
    "人力资源": {
        "hr_department": {"cn": "部门", "cols": [
            ("department_id", "部门ID", "id"), ("department_name", "部门名称", "name"),
            ("parent_department_id", "上级部门ID", "int"), ("department_level", "部门层级", "enum:一级|二级|三级"),
            ("cost_center_code", "成本中心编码", "text"), ("headcount_budget", "编制人数", "int"),
            ("office_city", "办公城市", "city"), ("established_date", "成立日期", "date"),
            ("department_status", "部门状态", "enum:正常|撤销|合并中"),
        ]},
        "hr_employee": {"cn": "员工", "cols": [
            ("employee_id", "员工ID", "id"), ("employee_name", "员工姓名", "name"),
            ("department_id", "所属部门ID", "fk:hr_department"), ("job_level", "职级", "enum:P4|P5|P6|P7|P8|M1|M2"),
            ("job_title", "岗位名称", "enum:工程师|产品经理|设计师|运营|销售|财务|人事"),
            ("hire_date", "入职日期", "date"), ("employment_status", "在职状态", "enum:在职|离职|试用期"),
            ("work_city", "工作城市", "city"), ("employee_email", "工作邮箱", "text"),
            ("gender", "性别", "enum:男|女"), ("education", "学历", "enum:本科|硕士|博士|大专"),
        ]},
        "hr_payroll": {"cn": "薪资发放记录", "cols": [
            ("payroll_id", "薪资单ID", "id"), ("employee_id", "员工ID", "fk:hr_employee"),
            ("pay_month", "发薪月份", "date"), ("base_salary", "基本工资", "money"), ("bonus_amount", "奖金金额", "money"),
            ("social_insurance_amount", "社保扣款", "money"), ("tax_amount", "个税金额", "money"),
            ("net_salary", "实发工资", "money"), ("pay_status", "发放状态", "enum:已发放|待发放|已冻结"),
        ]},
        "hr_attendance": {"cn": "考勤记录", "cols": [
            ("attendance_id", "考勤记录ID", "id"), ("employee_id", "员工ID", "fk:hr_employee"),
            ("work_date", "出勤日期", "date"), ("check_in_time", "签到时间", "datetime"),
            ("check_out_time", "签退时间", "datetime"), ("work_hours", "工作时长（小时）", "float"),
            ("attendance_type", "出勤类型", "enum:正常|迟到|早退|缺卡|外勤"), ("overtime_hours", "加班时长（小时）", "float"),
        ]},
        "hr_leave_request": {"cn": "请假申请", "cols": [
            ("leave_id", "请假单ID", "id"), ("employee_id", "员工ID", "fk:hr_employee"),
            ("leave_type", "请假类型", "enum:年假|病假|事假|婚假|产假"), ("start_date", "开始日期", "date"),
            ("end_date", "结束日期", "date"), ("leave_days", "请假天数", "float"),
            ("approval_status", "审批状态", "enum:已通过|已驳回|审批中"), ("apply_time", "申请时间", "datetime"),
        ]},
        "hr_job_posting": {"cn": "招聘职位", "cols": [
            ("posting_id", "职位ID", "id"), ("posting_name", "职位名称", "name"),
            ("department_id", "用人部门ID", "fk:hr_department"), ("work_city", "工作地点", "city"),
            ("salary_min", "薪资下限", "money"), ("salary_max", "薪资上限", "money"),
            ("headcount", "招聘人数", "int"), ("posting_status", "职位状态", "enum:招聘中|已关闭|暂停"),
            ("publish_date", "发布日期", "date"),
        ]},
        "hr_interview": {"cn": "面试记录", "cols": [
            ("interview_id", "面试ID", "id"), ("posting_id", "应聘职位ID", "fk:hr_job_posting"),
            ("candidate_name", "候选人姓名", "name"), ("interview_round", "面试轮次", "enum:初试|复试|终面"),
            ("interview_time", "面试时间", "datetime"), ("interview_result", "面试结果", "enum:通过|未通过|待定"),
            ("interviewer_id", "面试官员工ID", "fk:hr_employee"), ("source_channel", "简历来源", "enum:招聘网站|内推|猎头|校招"),
        ]},
        "hr_performance": {"cn": "绩效考核", "cols": [
            ("performance_id", "考核记录ID", "id"), ("employee_id", "员工ID", "fk:hr_employee"),
            ("review_period", "考核周期", "enum:2023上半年|2023下半年|2024上半年|2024下半年"),
            ("performance_grade", "绩效等级", "enum:S|A|B|C|D"), ("kpi_completion_rate", "KPI完成率", "ratio"),
            ("reviewer_id", "考核人员工ID", "int"), ("review_date", "考核日期", "date"),
        ]},
    },
    "财务总账": {
        "fin_account": {"cn": "会计科目", "cols": [
            ("account_id", "科目ID", "id"), ("account_name", "科目名称", "name"), ("account_code", "科目编码", "text"),
            ("account_type", "科目类别", "enum:资产|负债|权益|收入|费用"), ("parent_account_id", "上级科目ID", "int"),
            ("balance_direction", "余额方向", "enum:借|贷"), ("account_status", "科目状态", "enum:启用|停用"),
        ]},
        "fin_voucher": {"cn": "记账凭证", "cols": [
            ("voucher_id", "凭证ID", "id"), ("voucher_no", "凭证号", "text"), ("voucher_date", "凭证日期", "date"),
            ("voucher_type", "凭证字", "enum:记|收|付|转"), ("maker_name", "制单人", "name"),
            ("audit_status", "审核状态", "enum:已审核|未审核|已记账"), ("total_debit_amount", "借方合计", "money"),
            ("total_credit_amount", "贷方合计", "money"), ("attachment_count", "附件张数", "int"),
        ]},
        "fin_voucher_entry": {"cn": "凭证分录", "cols": [
            ("entry_id", "分录ID", "id"), ("voucher_id", "凭证ID", "fk:fin_voucher"), ("account_id", "科目ID", "fk:fin_account"),
            ("entry_summary", "摘要", "text"), ("debit_amount", "借方金额", "money"), ("credit_amount", "贷方金额", "money"),
            ("currency", "币种", "enum:人民币|美元|港币"), ("exchange_rate", "汇率", "float"),
        ]},
        "fin_payable": {"cn": "应付账款", "cols": [
            ("payable_id", "应付单ID", "id"), ("counterparty_name", "往来单位名称", "name"),
            ("payable_amount", "应付金额", "money"), ("paid_amount", "已付金额", "money"),
            ("due_date", "到期日", "date"), ("payable_status", "核销状态", "enum:未付款|部分付款|已付清"),
            ("account_id", "科目ID", "fk:fin_account"), ("create_time", "创建时间", "datetime"),
        ]},
        "fin_receivable": {"cn": "应收账款", "cols": [
            ("receivable_id", "应收单ID", "id"), ("counterparty_name", "往来单位名称", "name"),
            ("receivable_amount", "应收金额", "money"), ("received_amount", "已收金额", "money"),
            ("due_date", "到期日", "date"), ("aging_days", "账龄（天）", "int"),
            ("receivable_status", "收款状态", "enum:未收款|部分收款|已收清"), ("account_id", "科目ID", "fk:fin_account"),
        ]},
        "fin_expense_claim": {"cn": "费用报销", "cols": [
            ("claim_id", "报销单ID", "id"), ("applicant_name", "申请人", "name"),
            ("expense_type", "费用类型", "enum:差旅费|招待费|办公费|交通费|通讯费"), ("claim_amount", "报销金额", "money"),
            ("approved_amount", "核准金额", "money"), ("claim_date", "报销日期", "date"),
            ("claim_status", "报销状态", "enum:已报销|审批中|已驳回"), ("expense_city", "费用发生城市", "city"),
        ]},
        "fin_budget": {"cn": "部门预算", "cols": [
            ("budget_id", "预算ID", "id"), ("budget_name", "预算项目", "name"), ("fiscal_year", "预算年度", "enum:2023|2024|2025"),
            ("budget_amount", "预算金额", "money"), ("used_amount", "已使用金额", "money"),
            ("usage_rate", "预算执行率", "ratio"), ("budget_status", "预算状态", "enum:执行中|已冻结|已结项"),
        ]},
        "fin_input_invoice": {"cn": "进项发票", "cols": [
            ("invoice_id", "发票ID", "id"), ("invoice_no", "发票号码", "text"), ("seller_name", "销售方名称", "name"),
            ("invoice_amount", "发票金额（不含税）", "money"), ("tax_amount", "税额", "money"),
            ("tax_rate", "税率", "ratio"), ("invoice_date", "开票日期", "date"),
            ("verify_status", "认证状态", "enum:已认证|未认证|已作废"),
        ]},
    },
    "采购供应": {
        "proc_supplier": {"cn": "供应商", "cols": [
            ("supplier_id", "供应商ID", "id"), ("supplier_name", "供应商名称", "name"),
            ("supplier_type", "供应商类型", "enum:原材料|包装|服务|设备"), ("supplier_city", "供应商所在城市", "city"),
            ("cooperation_start_date", "合作开始日期", "date"), ("supplier_grade", "供应商分级", "enum:战略|核心|一般|淘汰"),
            ("settlement_cycle_days", "结算账期（天）", "int"), ("supplier_status", "合作状态", "enum:合作中|暂停|终止"),
        ]},
        "proc_purchase_request": {"cn": "采购申请", "cols": [
            ("request_id", "采购申请ID", "id"), ("request_title", "申请标题", "name"),
            ("request_amount", "申请金额", "money"), ("request_date", "申请日期", "date"),
            ("request_status", "申请状态", "enum:已批准|审批中|已驳回"), ("urgency", "紧急程度", "enum:普通|加急|特急"),
            ("requester_name", "申请人", "text"),
        ]},
        "proc_purchase_bill": {"cn": "采购单", "cols": [
            ("bill_id", "采购单ID", "id"), ("bill_no", "采购单号", "text"), ("supplier_id", "供应商ID", "fk:proc_supplier"),
            ("request_id", "采购申请ID", "fk:proc_purchase_request"), ("bill_amount", "采购总额", "money"),
            ("bill_date", "下单日期", "date"), ("expected_arrival_date", "预计到货日期", "date"),
            ("bill_status", "采购单状态", "enum:已下单|已到货|部分到货|已取消"), ("buyer_name", "采购员", "name"),
        ]},
        "proc_purchase_bill_line": {"cn": "采购单明细", "cols": [
            ("line_id", "明细ID", "id"), ("bill_id", "采购单ID", "fk:proc_purchase_bill"),
            ("material_name", "物料名称", "name"), ("purchase_qty", "采购数量", "int"),
            ("unit_price", "采购单价", "money"), ("line_amount", "明细金额", "money"),
            ("unit", "计量单位", "enum:件|箱|千克|吨|套"),
        ]},
        "proc_contract": {"cn": "采购合同", "cols": [
            ("contract_id", "采购合同ID", "id"), ("contract_name", "合同名称", "name"),
            ("supplier_id", "供应商ID", "fk:proc_supplier"), ("contract_amount", "合同金额", "money"),
            ("sign_date", "签订日期", "date"), ("expire_date", "到期日期", "date"),
            ("contract_status", "合同状态", "enum:执行中|已到期|已终止"),
        ]},
        "proc_payment_plan": {"cn": "付款计划", "cols": [
            ("plan_id", "付款计划ID", "id"), ("contract_id", "采购合同ID", "fk:proc_contract"),
            ("plan_amount", "计划付款金额", "money"), ("plan_date", "计划付款日期", "date"),
            ("actual_paid_amount", "实际付款金额", "money"), ("plan_status", "付款状态", "enum:已付|未付|逾期"),
        ]},
        "proc_supplier_assessment": {"cn": "供应商考核", "cols": [
            ("assessment_id", "考核ID", "id"), ("supplier_id", "供应商ID", "fk:proc_supplier"),
            ("assessment_quarter", "考核季度", "enum:2024Q1|2024Q2|2024Q3|2024Q4"),
            ("on_time_delivery_rate", "准时交货率", "ratio"), ("defect_rate", "来料不良率", "ratio"),
            ("assessment_level", "考核结论", "enum:优秀|合格|待改进|不合格"),
        ]},
    },
    "生产制造": {
        "mfg_factory": {"cn": "工厂", "cols": [
            ("factory_id", "工厂ID", "id"), ("factory_name", "工厂名称", "name"), ("factory_city", "工厂所在城市", "city"),
            ("capacity_per_day", "日产能", "int"), ("factory_type", "工厂类型", "enum:自有|代工"),
            ("open_date", "投产日期", "date"), ("factory_status", "运营状态", "enum:运营中|停产|筹建"),
        ]},
        "mfg_production_line": {"cn": "产线", "cols": [
            ("line_id", "产线ID", "id"), ("line_name", "产线名称", "name"), ("factory_id", "所属工厂ID", "fk:mfg_factory"),
            ("line_type", "产线类型", "enum:装配|注塑|包装|检测"), ("designed_capacity", "设计产能", "int"),
            ("line_status", "产线状态", "enum:运行|检修|停用"),
        ]},
        "mfg_material": {"cn": "物料", "cols": [
            ("material_id", "物料ID", "id"), ("material_name", "物料名称", "name"), ("material_code", "物料编码", "text"),
            ("material_category", "物料类别", "enum:原材料|半成品|成品|辅料"), ("unit", "计量单位", "enum:件|千克|米|套"),
            ("standard_cost", "标准成本", "money"), ("safety_stock_days", "安全周转天数", "int"),
        ]},
        "mfg_work_order": {"cn": "生产工单", "cols": [
            ("work_order_id", "工单ID", "id"), ("work_order_no", "工单号", "text"), ("line_id", "产线ID", "fk:mfg_production_line"),
            ("material_id", "产出物料ID", "fk:mfg_material"), ("planned_qty", "计划产量", "int"),
            ("completed_qty", "完工数量", "int"), ("scrap_qty", "报废数量", "int"),
            ("start_time", "开工时间", "datetime"), ("finish_time", "完工时间", "datetime"),
            ("work_order_status", "工单状态", "enum:已完工|生产中|已关闭|待开工"),
        ]},
        "mfg_bom": {"cn": "物料清单", "cols": [
            ("bom_id", "BOM ID", "id"), ("parent_material_id", "成品物料ID", "fk:mfg_material"),
            ("child_material_name", "子件名称", "name"), ("usage_qty", "单位用量", "float"),
            ("loss_rate", "损耗率", "ratio"), ("bom_version", "BOM版本", "enum:V1|V2|V3"),
        ]},
        "mfg_quality_inspection": {"cn": "质检记录", "cols": [
            ("inspection_id", "质检ID", "id"), ("work_order_id", "工单ID", "fk:mfg_work_order"),
            ("inspection_time", "质检时间", "datetime"), ("sample_qty", "抽检数量", "int"),
            ("defect_qty", "不良数量", "int"), ("pass_rate", "合格率", "ratio"),
            ("inspection_result", "质检结论", "enum:合格|让步接收|不合格"), ("inspector_name", "质检员", "name"),
        ]},
        "mfg_downtime": {"cn": "设备停机记录", "cols": [
            ("downtime_id", "停机记录ID", "id"), ("line_id", "产线ID", "fk:mfg_production_line"),
            ("downtime_start", "停机开始时间", "datetime"), ("downtime_minutes", "停机时长（分钟）", "int"),
            ("downtime_reason", "停机原因", "enum:设备故障|换型|缺料|计划保养|停电"), ("loss_amount", "停机损失金额", "money"),
        ]},
    },
    "IT运维": {
        "ops_server": {"cn": "服务器", "cols": [
            ("server_id", "服务器ID", "id"), ("server_name", "主机名", "name"), ("ip_address", "IP地址", "text"),
            ("idc_city", "机房城市", "city"), ("cpu_cores", "CPU核数", "int"), ("memory_gb", "内存（GB）", "int"),
            ("os_type", "操作系统", "enum:CentOS|Ubuntu|Windows Server"), ("server_status", "服务器状态", "enum:运行|下线|维护"),
            ("purchase_date", "采购日期", "date"),
        ]},
        "ops_application": {"cn": "应用系统", "cols": [
            ("app_id", "应用ID", "id"), ("app_name", "应用名称", "name"), ("owner_team", "负责团队", "enum:交易|搜索|推荐|基础架构|数据"),
            ("app_level", "应用等级", "enum:P0|P1|P2|P3"), ("online_date", "上线日期", "date"),
            ("app_status", "应用状态", "enum:运行|下线"),
        ]},
        "ops_deployment": {"cn": "部署关系", "cols": [
            ("deployment_id", "部署ID", "id"), ("app_id", "应用ID", "fk:ops_application"),
            ("server_id", "服务器ID", "fk:ops_server"), ("deploy_time", "部署时间", "datetime"),
            ("instance_count", "实例数", "int"),
        ]},
        "ops_alert": {"cn": "告警事件", "cols": [
            ("alert_id", "告警ID", "id"), ("app_id", "应用ID", "fk:ops_application"),
            ("alert_level", "告警级别", "enum:紧急|严重|警告|提示"), ("alert_time", "告警时间", "datetime"),
            ("recover_time", "恢复时间", "datetime"), ("alert_title", "告警标题", "name"),
            ("handle_status", "处理状态", "enum:已恢复|处理中|已忽略"), ("duration_minutes", "持续时长（分钟）", "int"),
        ]},
        "ops_change_request": {"cn": "变更单", "cols": [
            ("change_id", "变更单ID", "id"), ("app_id", "应用ID", "fk:ops_application"),
            ("change_title", "变更标题", "name"), ("change_type", "变更类型", "enum:发布|配置|扩容|回滚"),
            ("planned_time", "计划变更时间", "datetime"), ("change_result", "变更结果", "enum:成功|失败|已回滚"),
            ("risk_level", "风险等级", "enum:高|中|低"),
        ]},
        "ops_bandwidth_bill": {"cn": "带宽账单", "cols": [
            ("bill_id", "账单ID", "id"), ("idc_city", "机房城市", "city"), ("bill_month", "账单月份", "date"),
            ("bandwidth_mbps", "带宽（Mbps）", "int"), ("traffic_gb", "流量（GB）", "float"),
            ("bill_amount", "账单金额", "money"), ("vendor_name", "运营商", "name"),
        ]},
    },
    "客服工单": {
        "cs_agent": {"cn": "客服坐席", "cols": [
            ("agent_id", "坐席ID", "id"), ("agent_name", "坐席姓名", "name"), ("skill_group", "技能组", "enum:售前|售后|投诉|技术支持"),
            ("work_city", "坐席所在城市", "city"), ("agent_status", "坐席状态", "enum:在线|离线|培训中"),
            ("join_date", "上岗日期", "date"),
        ]},
        "cs_ticket": {"cn": "客服工单", "cols": [
            ("ticket_id", "工单ID", "id"), ("ticket_title", "工单标题", "name"), ("agent_id", "处理坐席ID", "fk:cs_agent"),
            ("ticket_type", "工单类型", "enum:咨询|投诉|建议|故障报修"), ("priority", "优先级", "enum:高|中|低"),
            ("create_time", "创建时间", "datetime"), ("close_time", "关闭时间", "datetime"),
            ("ticket_status", "工单状态", "enum:已解决|处理中|已关闭|已升级"), ("contact_channel", "来源渠道", "enum:电话|在线|邮件|APP"),
            ("resolve_minutes", "解决用时（分钟）", "int"),
        ]},
        "cs_ticket_flow": {"cn": "工单流转记录", "cols": [
            ("flow_id", "流转ID", "id"), ("ticket_id", "工单ID", "fk:cs_ticket"), ("from_agent_id", "转出坐席ID", "int"),
            ("to_agent_id", "转入坐席ID", "fk:cs_agent"), ("flow_time", "流转时间", "datetime"),
            ("flow_reason", "流转原因", "enum:技能不符|升级处理|交接班"),
        ]},
        "cs_call_record": {"cn": "通话记录", "cols": [
            ("call_id", "通话ID", "id"), ("agent_id", "坐席ID", "fk:cs_agent"), ("call_start_time", "通话开始时间", "datetime"),
            ("talk_seconds", "通话时长（秒）", "int"), ("wait_seconds", "排队等待时长（秒）", "int"),
            ("call_direction", "呼叫方向", "enum:呼入|呼出"), ("call_result", "通话结果", "enum:已接通|未接通|中途挂断"),
        ]},
        "cs_knowledge_article": {"cn": "知识库文章", "cols": [
            ("article_id", "文章ID", "id"), ("article_title", "文章标题", "name"), ("article_category", "文章分类", "enum:售后政策|操作指引|常见问题"),
            ("view_count", "浏览次数", "int"), ("helpful_count", "有用次数", "int"), ("update_time", "更新时间", "datetime"),
        ]},
        "cs_shift_schedule": {"cn": "排班表", "cols": [
            ("schedule_id", "排班ID", "id"), ("agent_id", "坐席ID", "fk:cs_agent"), ("shift_date", "排班日期", "date"),
            ("shift_type", "班次", "enum:早班|中班|晚班|休息"), ("planned_hours", "计划工时", "float"),
        ]},
    },
    "广告投放": {
        "ads_advertiser": {"cn": "广告主", "cols": [
            ("advertiser_id", "广告主ID", "id"), ("advertiser_name", "广告主名称", "name"),
            ("industry", "所属行业", "enum:美妆|3C|食品|汽车|教育"), ("advertiser_city", "广告主所在城市", "city"),
            ("account_balance", "账户余额", "money"), ("advertiser_status", "账户状态", "enum:正常|欠费|冻结"),
        ]},
        "ads_campaign": {"cn": "广告计划", "cols": [
            ("campaign_id", "计划ID", "id"), ("campaign_name", "计划名称", "name"), ("advertiser_id", "广告主ID", "fk:ads_advertiser"),
            ("objective", "投放目标", "enum:曝光|点击|转化|下载"), ("daily_budget", "日预算", "money"),
            ("start_date", "开始日期", "date"), ("end_date", "结束日期", "date"),
            ("campaign_status", "计划状态", "enum:投放中|已暂停|已结束"),
        ]},
        "ads_creative": {"cn": "广告创意", "cols": [
            ("creative_id", "创意ID", "id"), ("creative_title", "创意标题", "name"), ("campaign_id", "计划ID", "fk:ads_campaign"),
            ("creative_format", "创意形式", "enum:图片|视频|信息流|开屏"), ("audit_status", "审核状态", "enum:已通过|审核中|已拒绝"),
            ("create_time", "创建时间", "datetime"),
        ]},
        "ads_media_channel": {"cn": "投放媒体", "cols": [
            ("media_id", "媒体ID", "id"), ("media_name", "媒体名称", "name"), ("media_type", "媒体类型", "enum:搜索|社交|视频|资讯"),
            ("billing_mode", "计费方式", "enum:CPC|CPM|CPA"),
        ]},
        "ads_daily_report": {"cn": "广告投放日报", "cols": [
            ("report_id", "日报ID", "id"), ("campaign_id", "计划ID", "fk:ads_campaign"), ("media_id", "媒体ID", "fk:ads_media_channel"),
            ("report_date", "统计日期", "date"), ("impressions", "曝光量", "int"), ("clicks", "点击量", "int"),
            ("ctr", "点击率", "ratio"), ("cost_amount", "消耗金额", "money"), ("conversions", "转化数", "int"),
            ("conversion_rate", "转化率", "ratio"), ("cpa", "单次转化成本", "money"),
        ]},
        "ads_budget_adjustment": {"cn": "预算调整记录", "cols": [
            ("adjust_id", "调整ID", "id"), ("campaign_id", "计划ID", "fk:ads_campaign"), ("adjust_time", "调整时间", "datetime"),
            ("before_budget", "调整前预算", "money"), ("after_budget", "调整后预算", "money"),
            ("adjust_reason", "调整原因", "enum:效果好加量|成本超标|活动结束"),
        ]},
    },
    "内容运营": {
        "cms_author": {"cn": "内容作者", "cols": [
            ("author_id", "作者ID", "id"), ("author_name", "作者笔名", "name"), ("author_type", "作者类型", "enum:签约|自由撰稿|编辑部"),
            ("author_city", "作者所在城市", "city"), ("sign_date", "签约日期", "date"), ("follower_count", "粉丝数", "int"),
        ]},
        "cms_column": {"cn": "内容栏目", "cols": [
            ("column_id", "栏目ID", "id"), ("column_name", "栏目名称", "name"), ("column_type", "栏目类型", "enum:资讯|测评|攻略|专题"),
            ("column_status", "栏目状态", "enum:运营中|已停更"),
        ]},
        "cms_article": {"cn": "内容文章", "cols": [
            ("article_id", "文章ID", "id"), ("article_title", "文章标题", "name"), ("author_id", "作者ID", "fk:cms_author"),
            ("column_id", "栏目ID", "fk:cms_column"), ("publish_time", "发布时间", "datetime"), ("word_count", "字数", "int"),
            ("article_status", "文章状态", "enum:已发布|草稿|已下线"), ("is_original", "是否原创", "enum:是|否"),
        ]},
        "cms_article_daily": {"cn": "文章阅读日报", "cols": [
            ("daily_id", "日报ID", "id"), ("article_id", "文章ID", "fk:cms_article"), ("stat_date", "统计日期", "date"),
            ("read_count", "阅读量", "int"), ("reader_count", "阅读人数", "int"), ("avg_read_seconds", "平均阅读时长（秒）", "int"),
            ("share_count", "分享次数", "int"), ("like_count", "点赞数", "int"),
        ]},
        "cms_topic_plan": {"cn": "选题计划", "cols": [
            ("topic_id", "选题ID", "id"), ("topic_name", "选题名称", "name"), ("column_id", "栏目ID", "fk:cms_column"),
            ("planned_date", "计划发布日期", "date"), ("topic_status", "选题状态", "enum:已立项|撰写中|已完成|已取消"),
        ]},
        "cms_royalty": {"cn": "稿费结算", "cols": [
            ("royalty_id", "结算ID", "id"), ("author_id", "作者ID", "fk:cms_author"), ("settle_month", "结算月份", "date"),
            ("article_count", "结算篇数", "int"), ("royalty_amount", "稿费金额", "money"),
            ("settle_status", "结算状态", "enum:已结算|待结算"),
        ]},
    },
    "行政资产": {
        "adm_office": {"cn": "办公地点", "cols": [
            ("office_id", "办公地点ID", "id"), ("office_name", "办公地点名称", "name"), ("office_city", "所在城市", "city"),
            ("area_sqm", "面积（平方米）", "float"), ("monthly_rent", "月租金", "money"), ("seat_count", "工位数", "int"),
            ("lease_end_date", "租约到期日", "date"),
        ]},
        "adm_fixed_asset": {"cn": "固定资产", "cols": [
            ("asset_id", "资产ID", "id"), ("asset_name", "资产名称", "name"), ("asset_category", "资产类别", "enum:电脑|显示器|家具|车辆|打印机"),
            ("office_id", "存放地点ID", "fk:adm_office"), ("purchase_amount", "购置金额", "money"),
            ("purchase_date", "购置日期", "date"), ("net_value", "账面净值", "money"),
            ("asset_status", "资产状态", "enum:在用|闲置|报废|维修中"),
        ]},
        "adm_asset_assignment": {"cn": "资产领用记录", "cols": [
            ("assignment_id", "领用ID", "id"), ("asset_id", "资产ID", "fk:adm_fixed_asset"), ("assignee_name", "领用人", "name"),
            ("assign_date", "领用日期", "date"), ("return_date", "归还日期", "date"),
        ]},
        "adm_meeting_room": {"cn": "会议室", "cols": [
            ("room_id", "会议室ID", "id"), ("room_name", "会议室名称", "name"), ("office_id", "所在办公地点ID", "fk:adm_office"),
            ("capacity", "容纳人数", "int"), ("has_video", "是否有视频设备", "enum:是|否"),
        ]},
        "adm_room_booking": {"cn": "会议室预订", "cols": [
            ("booking_id", "预订ID", "id"), ("room_id", "会议室ID", "fk:adm_meeting_room"), ("booker_name", "预订人", "name"),
            ("start_time", "开始时间", "datetime"), ("end_time", "结束时间", "datetime"), ("attendee_count", "参会人数", "int"),
            ("booking_status", "预订状态", "enum:已使用|已取消|未签到"),
        ]},
        "adm_travel_request": {"cn": "差旅申请", "cols": [
            ("travel_id", "差旅单ID", "id"), ("applicant_name", "出差人", "name"), ("destination_city", "目的地城市", "city"),
            ("depart_date", "出发日期", "date"), ("return_date", "返回日期", "date"), ("estimated_cost", "预估费用", "money"),
            ("travel_status", "差旅状态", "enum:已批准|审批中|已驳回|已完成"),
        ]},
    },
    "法务合同": {
        "law_counterparty": {"cn": "合同相对方", "cols": [
            ("counterparty_id", "相对方ID", "id"), ("counterparty_name", "相对方名称", "name"),
            ("counterparty_type", "相对方类型", "enum:企业|个人|政府机构"), ("registered_city", "注册城市", "city"),
            ("credit_level", "资信等级", "enum:AAA|AA|A|B"),
        ]},
        "law_contract": {"cn": "法务合同", "cols": [
            ("contract_id", "合同ID", "id"), ("contract_title", "合同标题", "name"), ("counterparty_id", "相对方ID", "fk:law_counterparty"),
            ("contract_type", "合同类型", "enum:销售|采购|服务|租赁|保密协议"), ("contract_amount", "合同金额", "money"),
            ("sign_date", "签署日期", "date"), ("effective_date", "生效日期", "date"), ("expire_date", "到期日期", "date"),
            ("contract_status", "合同状态", "enum:履行中|已到期|已终止|待签署"),
        ]},
        "law_case": {"cn": "诉讼案件", "cols": [
            ("case_id", "案件ID", "id"), ("case_name", "案件名称", "name"), ("counterparty_id", "对方当事人ID", "fk:law_counterparty"),
            ("case_type", "案件类型", "enum:合同纠纷|知识产权|劳动争议|侵权"), ("claim_amount", "争议金额", "money"),
            ("filing_date", "立案日期", "date"), ("case_status", "案件状态", "enum:审理中|已结案|已和解|执行中"),
            ("court_city", "受理法院所在城市", "city"),
        ]},
        "law_compliance_check": {"cn": "合规检查", "cols": [
            ("check_id", "检查ID", "id"), ("check_item", "检查事项", "name"), ("check_date", "检查日期", "date"),
            ("issue_count", "发现问题数", "int"), ("rectified_count", "已整改数", "int"),
            ("risk_level", "风险等级", "enum:高|中|低"),
        ]},
        "law_seal_usage": {"cn": "用印申请", "cols": [
            ("usage_id", "用印ID", "id"), ("contract_id", "合同ID", "fk:law_contract"), ("seal_type", "印章类型", "enum:公章|合同章|法人章|财务章"),
            ("apply_time", "申请时间", "datetime"), ("applicant_name", "申请人", "name"),
            ("usage_status", "用印状态", "enum:已用印|审批中|已驳回"),
        ]},
    },
    "培训学习": {
        "trn_course": {"cn": "培训课程", "cols": [
            ("course_id", "课程ID", "id"), ("course_name", "课程名称", "name"), ("course_category", "课程类别", "enum:管理|技术|通用|合规"),
            ("course_hours", "课时", "float"), ("course_fee", "课程费用", "money"), ("course_status", "课程状态", "enum:上线|下线"),
        ]},
        "trn_lecturer": {"cn": "讲师", "cols": [
            ("lecturer_id", "讲师ID", "id"), ("lecturer_name", "讲师姓名", "name"), ("lecturer_type", "讲师类型", "enum:内部|外部"),
            ("hourly_fee", "课酬（元/小时）", "money"), ("lecturer_city", "讲师所在城市", "city"),
        ]},
        "trn_session": {"cn": "培训班次", "cols": [
            ("session_id", "班次ID", "id"), ("course_id", "课程ID", "fk:trn_course"), ("lecturer_id", "讲师ID", "fk:trn_lecturer"),
            ("session_name", "班次名称", "name"), ("start_date", "开班日期", "date"), ("training_city", "培训城市", "city"),
            ("max_trainees", "人数上限", "int"), ("session_status", "班次状态", "enum:已结束|进行中|未开始|已取消"),
        ]},
        "trn_enrollment": {"cn": "培训报名", "cols": [
            ("enrollment_id", "报名ID", "id"), ("session_id", "班次ID", "fk:trn_session"), ("trainee_name", "学员姓名", "name"),
            ("enroll_time", "报名时间", "datetime"), ("attendance_rate", "出勤率", "ratio"),
            ("completion_status", "结业状态", "enum:已结业|未结业|已退出"),
        ]},
        "trn_exam_result": {"cn": "培训考试成绩", "cols": [
            ("result_id", "成绩ID", "id"), ("enrollment_id", "报名ID", "fk:trn_enrollment"), ("exam_date", "考试日期", "date"),
            ("exam_score", "考试分数", "float"), ("pass_flag", "是否通过", "enum:通过|未通过"),
        ]},
        "trn_certificate": {"cn": "培训证书", "cols": [
            ("certificate_id", "证书ID", "id"), ("enrollment_id", "报名ID", "fk:trn_enrollment"), ("certificate_name", "证书名称", "name"),
            ("issue_date", "发证日期", "date"), ("valid_years", "有效期（年）", "int"),
        ]},
    },
    "数据平台": {
        "dp_table_meta": {"cn": "数据表元信息", "cols": [
            ("meta_id", "元信息ID", "id"), ("table_name_en", "表英文名", "name"), ("data_layer", "数仓分层", "enum:ODS|DWD|DWS|ADS"),
            ("owner_name", "负责人", "text"), ("row_count", "数据行数", "int"), ("storage_gb", "存储量（GB）", "float"),
            ("update_frequency", "更新频率", "enum:实时|小时|天|周"), ("create_time", "创建时间", "datetime"),
        ]},
        "dp_job": {"cn": "调度任务", "cols": [
            ("job_id", "任务ID", "id"), ("job_name", "任务名称", "name"), ("meta_id", "产出表元信息ID", "fk:dp_table_meta"),
            ("schedule_cron", "调度周期", "enum:每天|每小时|每周"), ("job_priority", "任务优先级", "enum:高|中|低"),
            ("job_status", "任务状态", "enum:启用|停用"),
        ]},
        "dp_job_run": {"cn": "任务运行记录", "cols": [
            ("run_id", "运行ID", "id"), ("job_id", "任务ID", "fk:dp_job"), ("run_date", "业务日期", "date"),
            ("start_time", "开始时间", "datetime"), ("end_time", "结束时间", "datetime"), ("run_seconds", "运行时长（秒）", "int"),
            ("run_status", "运行结果", "enum:成功|失败|超时|重跑"), ("output_rows", "产出行数", "int"),
        ]},
        "dp_quality_rule": {"cn": "数据质量规则", "cols": [
            ("rule_id", "规则ID", "id"), ("meta_id", "检查表元信息ID", "fk:dp_table_meta"), ("rule_name", "规则名称", "name"),
            ("rule_type", "规则类型", "enum:非空|唯一|波动|一致性"), ("rule_status", "规则状态", "enum:启用|停用"),
        ]},
        "dp_quality_result": {"cn": "质量检查结果", "cols": [
            ("check_id", "检查ID", "id"), ("rule_id", "规则ID", "fk:dp_quality_rule"), ("check_date", "检查日期", "date"),
            ("abnormal_rows", "异常行数", "int"), ("check_result", "检查结论", "enum:通过|告警|阻断"),
        ]},
        "dp_report_visit": {"cn": "报表访问日志", "cols": [
            ("visit_id", "访问ID", "id"), ("report_name", "报表名称", "name"), ("visitor_name", "访问人", "text"),
            ("visit_time", "访问时间", "datetime"), ("stay_seconds", "页面停留时长（秒）", "int"),
            ("visit_device", "访问终端", "enum:PC|移动端"),
        ]},
    },
}


# 真实数仓的业务表几乎都带这一组审计字段。铺满全库之后，问题里的时间约束对应哪个
# 时间字段更难判断——"创建时间""更新时间"到处都是。
AUDIT_COLUMNS: List[Column] = [
    ("create_time", "创建时间", "datetime"),
    ("update_time", "更新时间", "datetime"),
    ("created_by", "创建人", "text"),
    ("updated_by", "更新人", "text"),
    ("remark", "备注", "text"),
    ("is_deleted", "是否删除", "enum:0|1"),
]

for _tables in DOMAINS.values():
    for _spec in _tables.values():
        _existing = {name for name, _, _ in _spec["cols"]}
        _spec["cols"].extend(col for col in AUDIT_COLUMNS if col[0] not in _existing)


def iter_distractor_tables():
    for domain, tables in DOMAINS.items():
        for table, spec in tables.items():
            yield domain, table, spec


def create_ecommerce_big_database(db_path: str | Path) -> Path:
    """电商库 + 12 个干扰域。电商部分和 create_ecommerce_demo_database 生成的逐表一致。"""
    db_path = Path(create_ecommerce_demo_database(db_path))
    rng = random.Random(RANDOM_SEED)
    conn = sqlite3.connect(str(db_path))

    try:
        for _, table, spec in iter_distractor_tables():
            conn.execute(f'DROP TABLE IF EXISTS "{table}"')
            conn.execute(_create_table_sql(table, spec["cols"]))
        for _, table, spec in iter_distractor_tables():
            rows = [_row(spec["cols"], i, rng) for i in range(1, ROWS_PER_TABLE + 1)]
            marks = ", ".join("?" * len(spec["cols"]))
            conn.executemany(f'INSERT INTO "{table}" VALUES ({marks})', rows)
        conn.commit()
    finally:
        conn.close()

    return db_path


def _sql_type(kind: str) -> str:
    if kind in ("id", "int") or kind.startswith("fk:"):
        return "INTEGER"
    if kind in ("money", "ratio", "float"):
        return "REAL"
    return "TEXT"


def _create_table_sql(table: str, cols: List[Column]) -> str:
    lines, fks = [], []
    for name, _, kind in cols:
        suffix = " PRIMARY KEY" if kind == "id" else ""
        lines.append(f"    {name} {_sql_type(kind)}{suffix}")
        if kind.startswith("fk:"):
            target = kind[3:]
            target_pk = next(c[0] for c in _all_cols(target) if c[2] == "id")
            fks.append(f"    FOREIGN KEY ({name}) REFERENCES {target}({target_pk})")
    return f'CREATE TABLE "{table}" (\n' + ",\n".join(lines + fks) + "\n)"


def _all_cols(table: str) -> List[Column]:
    for _, name, spec in iter_distractor_tables():
        if name == table:
            return spec["cols"]
    raise KeyError(table)


def _row(cols: List[Column], i: int, rng: random.Random) -> tuple:
    base = datetime(2023, 1, 1)
    values = []
    for _, cn, kind in cols:
        if kind == "id":
            values.append(i)
        elif kind.startswith("fk:"):
            values.append(rng.randint(1, ROWS_PER_TABLE))
        elif kind == "name":
            values.append(f"{cn.replace('名称', '').replace('姓名', '')}{i:02d}")
        elif kind.startswith("enum:"):
            values.append(rng.choice(kind[5:].split("|")))
        elif kind == "city":
            values.append(rng.choice(CITIES)[0] if isinstance(CITIES[0], tuple) else rng.choice(CITIES))
        elif kind == "money":
            values.append(round(rng.uniform(100, 200000), 2))
        elif kind == "ratio":
            values.append(round(rng.uniform(0, 1), 4))
        elif kind == "float":
            values.append(round(rng.uniform(0.5, 200), 1))
        elif kind == "int":
            values.append(rng.randint(0, 5000))
        elif kind == "datetime":
            values.append((base + timedelta(minutes=rng.randint(0, 2 * 365 * 24 * 60))).strftime("%Y-%m-%d %H:%M:%S"))
        elif kind == "date":
            values.append((date(2023, 1, 1) + timedelta(days=rng.randint(0, 2 * 365))).isoformat())
        else:  # text
            values.append(f"{cn}-{i:03d}")
    return tuple(values)


def get_ecommerce_big_business_meta() -> dict:
    """电商的完整元数据 + 干扰表的薄元数据（表描述、字段中文名）。"""
    meta = dict(get_ecommerce_business_meta())
    roles = {"id": "join_key", "name": "output_dimension", "city": "dimension", "money": "measure",
             "ratio": "measure", "float": "measure", "int": "measure", "datetime": "time", "date": "time", "text": "attribute"}

    for domain, table, spec in iter_distractor_tables():
        meta[table] = {
            "description": f"{domain}域的{spec['cn']}表。",
            "aliases": [spec["cn"], f"{spec['cn']}表"],
            "columns": {
                name: {
                    "description": f"{spec['cn']}的{cn}。",
                    "aliases": [cn],
                    "semantic_role": "join_key" if kind.startswith("fk:") else ("dimension" if kind.startswith("enum:") else roles.get(kind, "attribute")),
                }
                for name, cn, kind in spec["cols"]
            },
        }
    return meta
