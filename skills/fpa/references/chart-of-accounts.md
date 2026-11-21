# Chart of Accounts Mapping

Mapping precedence (recorded per account as `source`):

1. `explicit` - user mapping CSV (`account,line`). Always ask for one when the CoA is
   non-standard; it is the single biggest accuracy lever.
2. `range` - numeric scheme below.
3. `keyword` - account-name match (EN + VI). Disclose as low confidence.
4. `unmapped` - excluded from the P&L and reported with its net amount.

Valid line names: `revenue, contra_revenue, cogs, opex_personnel, opex_sales_marketing,
opex_rnd, opex_facilities, opex_ga, depreciation_amortization, other_income,
interest_expense, other_expense, income_tax, asset, liability, equity`.

## `generic` scheme (US-style 4-digit)

| Range | Line |
|---|---|
| 1xxx / 2xxx / 3xxx | asset / liability / equity |
| 40xx-48xx | revenue |
| 49xx | contra_revenue |
| 5xxx | cogs |
| 60-61xx | opex_personnel |
| 62-63xx | opex_sales_marketing |
| 64xx | opex_rnd |
| 65xx | opex_facilities |
| 66-67xx, 69xx, 7xxx | opex_ga |
| 68xx | depreciation_amortization |
| 80xx | other_income |
| 81-82xx | interest_expense |
| 83-89xx | other_expense |
| 9xxx | income_tax |

## `vas` scheme (Vietnam, Circular 200/2014/TT-BTC; mostly compatible with 133)

| Account | Meaning | Line |
|---|---|---|
| 1xx, 2xx | Assets (214 accumulated depreciation is contra-asset) | asset |
| 3xx | Liabilities | liability |
| 4xx | Owner's equity (421 retained earnings) | equity |
| 511 | Doanh thu bán hàng và cung cấp dịch vụ | revenue |
| 521 | Các khoản giảm trừ doanh thu | contra_revenue |
| 515 | Doanh thu hoạt động tài chính | other_income |
| 632 | Giá vốn hàng bán | cogs |
| 635 | Chi phí tài chính | interest_expense |
| 641 (6411 staff, 6414 depreciation) | Chi phí bán hàng | opex_sales_marketing / personnel / D&A |
| 642 (6421 staff, 6424 depreciation) | Chi phí quản lý doanh nghiệp | opex_ga / personnel / D&A |
| 711 | Thu nhập khác | other_income |
| 811 | Chi phí khác | other_expense |
| 821 | Chi phí thuế TNDN | income_tax |
| 911 | Xác định kết quả kinh doanh (closing) | **excluded** - remove closing entries |

VAS note: 621/622/627 (production costs) roll into 154 then 632 under the
perpetual method. If 621-627 appear with P&L-like balances, map them explicitly
(usually `cogs`) and confirm with the accountant.

## Example explicit mapping

```csv
account,line
6250,opex_rnd
7100,other_income
5900,opex_ga
```
