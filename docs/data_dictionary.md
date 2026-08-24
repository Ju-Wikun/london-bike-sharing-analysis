# 数据字典

## `fact_system_hourly`

一行代表原始行程聚合中出现的一个小时。

| 字段 | 类型 | 说明 |
|---|---|---|
| `ts` | TIMESTAMP | 伦敦当地出发时间取整到小时 |
| `ride_count` | BIGINT | 该小时的行程次数，非负 |

## `fact_weather_hourly`

一行代表 Open-Meteo 的一个连续天气小时。

| 字段 | 类型 | 说明 |
|---|---|---|
| `ts` | TIMESTAMP | 小时时间戳 |
| `temperature_c` | DOUBLE | 2 米气温，摄氏度 |
| `humidity_pct` | DOUBLE | 2 米相对湿度，0-100 |
| `precipitation_mm` | DOUBLE | 小时降水量，毫米 |
| `wind_speed_kmh` | DOUBLE | 10 米风速，km/h |
| `weather_code` | INTEGER | WMO 天气代码 |

## `dim_date`

一行代表 2020-2025 年的一个日历日，共 2,192 行。

| 字段 | 类型 | 说明 |
|---|---|---|
| `date_key` | DATE | 日期主键 |
| `year`, `month`, `day` | INTEGER | 日期拆分字段 |
| `weekday_num` | INTEGER | 周一为 0、周日为 6 |
| `weekday_label` | VARCHAR | 英文星期名称 |
| `is_weekend` | BOOLEAN | 是否周六或周日 |
| `is_holiday` | BOOLEAN | 是否英格兰和威尔士公共假期 |
| `day_type` | VARCHAR | `workday` 或 `non_workday` |

## `dim_holiday`

来自 GOV.UK 的地区公共假期记录。日期维表只使用 `england-and-wales`。

## `analytics_hourly`

保留全部原始观测骑行小时并附加日期、天气和质量状态的审计视图。

## `analytics_hourly_quality`

业务分析与看板使用的质量过滤视图。它排除 4 个不完整源日期，并加入 21 个经源批次核实的零骑行小时。`record_status` 区分原始观测与确认零值。

## `source_batch`

一行代表一个 TfL 原始批次，共 242 行。记录文件大小、日期格式、解析行数、有效/无效出发时间、最早/最晚时间、覆盖日期数和审计状态。

## `hour_coverage_exception`

一行代表一个天气时钟与骑行聚合的差异小时，共 82 行。`classification` 为 `confirmed_zero_trip_hour`、`source_gap` 或 `nonexistent_local_hour`。

## `known_data_anomaly`

记录 4 个已确认不完整的官方源日期及其观测行程量、观测小时、缺口小时和证据说明。

## 行程级展示数据边界

站点与路线看板使用固定种子选取的 80 个 TfL 文件，每个最多读取 10,000 行；过滤后保留 793,323 条有效记录。有效时长范围为 60-10,800 秒。该样例没有作为仓库输入提交，避免发布大型、难审计的派生明细。
