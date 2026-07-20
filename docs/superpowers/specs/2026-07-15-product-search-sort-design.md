# 商品搜尋與排序 Design

**Status:** Approved
**Date:** 2026-07-15

## 背景與目標

目前 `GET /api/products` 只支援 `category` 篩選，沒有關鍵字搜尋，也沒有排序，預設順序未指定（SQLAlchemy 沒有 `order_by`，順序不保證）。本次新增：
1. 依商品名稱關鍵字搜尋
2. 依價格或上架時間排序（各支援 asc/desc）

兩者皆可與既有的 `category` 篩選同時使用（AND 條件）。

## API 參數

```
GET /api/products?q=<關鍵字>&category=<分類>&sort_by=<price|created_at>&order=<asc|desc>&page=&per_page=
```

| 參數 | 必填 | 允許值 | 無效/缺省時的行為 |
|---|---|---|---|
| `q` | 否 | 任意字串 | 不帶則不套用搜尋篩選 |
| `category` | 否 | 任意字串（既有欄位，行為不變） | 不帶則不套用分類篩選 |
| `sort_by` | 否 | `price`、`created_at` | 其他值或未帶 → fallback `created_at` |
| `order` | 否 | `asc`、`desc` | 其他值或未帶 → fallback `desc` |
| `page` / `per_page` | 否 | 整數 | 沿用既有邏輯（`per_page` 會被 `clamp_per_page` 限制在 1~100） |

**設計原則：** 沿用 `products` 列表既有的「query string 寬鬆風格」——`page`/`per_page` 目前格式錯誤就直接 fallback 到預設值，不回 400。本次的 `sort_by`/`order` 比照辦理，維持一致的錯誤處理風格，不另外用 Marshmallow schema 驗證 query string。

**搜尋比對規則：** 只比對 `Product.name`，不分大小寫、包含比對（substring match），用 SQLAlchemy `Column.ilike(f'%{q}%')`，在 SQLite（開發）與 PostgreSQL（生產）皆可運作，皆走參數化查詢，無 SQL injection 風險。

## Service 層變更

**檔案：** `app/services/product_service.py`

`get_products` 簽名從 `get_products(page, per_page, category)` 改為：

```python
get_products(page, per_page, category, q=None, sort_by=None, order=None)
```

新增排序欄位對照表：

```python
SORTABLE_FIELDS = {
    'price': Product.price,
    'created_at': Product.created_at,
}
```

邏輯：
1. `category` 篩選：不變（`filter_by(category=category)`）
2. `q` 有值時：加上 `Product.name.ilike(f'%{q}%')`
3. 排序：`column = SORTABLE_FIELDS.get(sort_by, Product.created_at)`；`order == 'asc'` 用 `column.asc()`，其餘（含未帶或無效值）用 `column.desc()`
4. 分頁邏輯不變（沿用既有的 `clamp_per_page`）

## Route 層變更

**檔案：** `app/blueprints/products/routes.py`

`get_products()` route 多讀取三個 query string：

```python
q = request.args.get('q')
sort_by = request.args.get('sort_by')
order = request.args.get('order')
```

並傳入 `product_service.get_products(page, per_page, category, q, sort_by, order)`。

## 測試計畫

**檔案：** `tests/test_products.py`（新增測試函式）

- 關鍵字搜尋比對到符合的商品
- 關鍵字搜尋比對不到時回傳空陣列
- `sort_by=price&order=asc` 結果依價格由低到高排序
- `sort_by=price&order=desc` 結果依價格由高到低排序
- `sort_by=created_at&order=asc`（最舊優先）結果依上架時間由舊到新排序
- 未帶 `sort_by`/`order` 時預設依上架時間新到舊排序
- 無效的 `sort_by`/`order` 值會 fallback 到預設排序，不回 400
- 同時帶 `q` 與 `category` 時，結果是兩者的交集

## 已知限制（不在本次範圍）

`q` 沒有跳脫 SQL LIKE 的萬用字元（`%`、`_`）。若使用者輸入的關鍵字剛好含有這些字元，比對語意會跟純字面比對不同（例如 `%` 會被當成「任意字元」的萬用字元，而非字面上的百分比符號）。這不構成安全性問題（仍是參數化查詢），只是搜尋結果可能與預期不同，之後有需要再處理。
