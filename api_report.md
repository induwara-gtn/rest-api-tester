# Swagger-Driven API Test Report

**Generated:** 2026-02-13 08:04:30  
**Base URL:** `https://searchservice-uat.feedgma.com`  
**Total Endpoints Tested:** 7  

## Summary

| # | Method | Path | Status | JSON | Time (ms) | Auth | Result |
|---|--------|------|:------:|:----:|:---------:|:----:|:------:|
| 1 | GET | `/tickers-all/source/keys` | 401 | Y | 660.52 | OK | **FAIL** |
| 2 | GET | `/tickers-all/source/data` | 401 | Y | 626.33 | OK | **FAIL** |
| 3 | GET | `/tickers-all/search` | 401 | Y | 498.63 | OK | **FAIL** |
| 4 | GET | `/tickers-all/keys/data` | 401 | Y | 590.25 | OK | **FAIL** |
| 5 | GET | `/v2/tickers-all/source/data` | 401 | Y | 504.89 | OK | **FAIL** |
| 6 | GET | `/v2/tickers-all/search` | 401 | Y | 487.2 | OK | **FAIL** |
| 7 | GET | `/v2/tickers-all/keys/data` | 401 | Y | 536.19 | OK | **FAIL** |

**Pass Rate:** 0/7 (0%)  
**Auth Enforced:** 7/7 | **Auth Open:** 0/7  

---

## Group: api clients

### GET `/tickers-all/source/keys`

**Summary:** Ticker List  
**Tags:** tickers-all  

#### Baseline Test

| Check | Result |
|-------|--------|
| Status Code | 401 FAIL |
| Valid JSON | PASS |
| Response Time | 660.52ms FAIL |

#### Auth Enforcement

PASS - Returned `401` without token.  

#### Parameter Analysis

| Parameter | Spec Required | Test Required | Status Without |
|-----------|:------------:|:------------:|:--------------:|
| `username` | No | Yes | 401 |
| `password` | No | Yes | 401 |
| `source-id` | Yes | Yes | 401 |
| `last-update-time` | No | Yes | 401 |
| `response-type` | No | Yes | 401 |
| `rows` | No | Yes | 401 |
| `page` | No | Yes | 401 |
| `filter` | No | Yes | 401 |
| `type` | No | Yes | 401 |
| `ignore-status` | No | Yes | 401 |
| `tradable` | No | Yes | 401 |
| `time` | No | Yes | 401 |

#### Empty Value Warnings

- `username` returned `401` (unexpected)
- `password` returned `401` (unexpected)
- `source-id` returned `401` (unexpected)
- `last-update-time` returned `401` (unexpected)
- `response-type` returned `401` (unexpected)
- `rows` returned `401` (unexpected)
- `page` returned `401` (unexpected)
- `filter` returned `401` (unexpected)
- `type` returned `401` (unexpected)
- `ignore-status` returned `401` (unexpected)
- `tradable` returned `401` (unexpected)
- `time` returned `401` (unexpected)

---

### GET `/tickers-all/source/data`

**Summary:** Ticker Details by Venue  
**Tags:** tickers-all  

#### Baseline Test

| Check | Result |
|-------|--------|
| Status Code | 401 FAIL |
| Valid JSON | PASS |
| Response Time | 626.33ms FAIL |

#### Auth Enforcement

PASS - Returned `401` without token.  

#### Parameter Analysis

| Parameter | Spec Required | Test Required | Status Without |
|-----------|:------------:|:------------:|:--------------:|
| `username` | No | Yes | 401 |
| `password` | No | Yes | 401 |
| `source-id` | Yes | Yes | 401 |
| `lang` | No | Yes | 401 |
| `required-fields` | No | Yes | 401 |
| `last-update-time` | No | Yes | 401 |
| `response-type` | No | Yes | 401 |
| `rows` | No | Yes | 401 |
| `page` | No | Yes | 401 |
| `filter` | No | Yes | 401 |
| `type` | No | Yes | 401 |
| `ignore-status` | No | Yes | 401 |
| `tradable` | No | Yes | 401 |
| `time` | No | Yes | 401 |

#### Empty Value Warnings

- `username` returned `401` (unexpected)
- `password` returned `401` (unexpected)
- `source-id` returned `401` (unexpected)
- `lang` returned `401` (unexpected)
- `required-fields` returned `401` (unexpected)
- `last-update-time` returned `401` (unexpected)
- `response-type` returned `401` (unexpected)
- `rows` returned `401` (unexpected)
- `page` returned `401` (unexpected)
- `filter` returned `401` (unexpected)
- `type` returned `401` (unexpected)
- `ignore-status` returned `401` (unexpected)
- `tradable` returned `401` (unexpected)
- `time` returned `401` (unexpected)

---

### GET `/tickers-all/search`

**Summary:** Ticker Search  
**Tags:** tickers-all  

#### Baseline Test

| Check | Result |
|-------|--------|
| Status Code | 401 FAIL |
| Valid JSON | PASS |
| Response Time | 498.63ms FAIL |

#### Auth Enforcement

PASS - Returned `401` without token.  

#### Parameter Analysis

| Parameter | Spec Required | Test Required | Status Without |
|-----------|:------------:|:------------:|:--------------:|
| `username` | No | Yes | 401 |
| `password` | No | Yes | 401 |
| `term` | Yes | Yes | 400 |
| `fields` | Yes | Yes | 400 |
| `required-fields` | No | Yes | 401 |
| `response-type` | No | Yes | 401 |
| `sort-field` | No | Yes | 401 |
| `sort-asc` | No | Yes | 401 |
| `rows` | No | Yes | 401 |
| `page` | No | Yes | 401 |
| `filter` | No | Yes | 401 |
| `type` | No | Yes | 401 |
| `ignore-status` | No | Yes | 401 |
| `num-filter` | No | Yes | 401 |
| `time` | No | Yes | 401 |

#### Empty Value Warnings

- `username` returned `401` (unexpected)
- `password` returned `401` (unexpected)
- `term` returned `401` (unexpected)
- `fields` returned `401` (unexpected)
- `required-fields` returned `401` (unexpected)
- `response-type` returned `401` (unexpected)
- `sort-field` returned `401` (unexpected)
- `sort-asc` returned `401` (unexpected)
- `rows` returned `401` (unexpected)
- `page` returned `401` (unexpected)
- `filter` returned `401` (unexpected)
- `type` returned `401` (unexpected)
- `ignore-status` returned `401` (unexpected)
- `num-filter` returned `401` (unexpected)
- `time` returned `401` (unexpected)

---

### GET `/tickers-all/keys/data`

**Summary:** Ticker Details  
**Tags:** tickers-all  

#### Baseline Test

| Check | Result |
|-------|--------|
| Status Code | 401 FAIL |
| Valid JSON | PASS |
| Response Time | 590.25ms FAIL |

#### Auth Enforcement

PASS - Returned `401` without token.  

#### Parameter Analysis

| Parameter | Spec Required | Test Required | Status Without |
|-----------|:------------:|:------------:|:--------------:|
| `username` | No | Yes | 401 |
| `password` | No | Yes | 401 |
| `source-id` | No | Yes | 401 |
| `keys` | Yes | Yes | 400 |
| `lang` | No | Yes | 401 |
| `required-fields` | No | Yes | 401 |
| `last-update-time` | No | Yes | 401 |
| `response-type` | No | Yes | 401 |
| `rows` | No | Yes | 401 |
| `page` | No | Yes | 401 |
| `filter` | No | Yes | 401 |
| `type` | No | Yes | 401 |
| `ignore-status` | No | Yes | 401 |
| `tradable` | No | Yes | 401 |
| `time` | No | Yes | 401 |

#### Empty Value Warnings

- `username` returned `401` (unexpected)
- `password` returned `401` (unexpected)
- `source-id` returned `401` (unexpected)
- `keys` returned `401` (unexpected)
- `lang` returned `401` (unexpected)
- `required-fields` returned `401` (unexpected)
- `last-update-time` returned `401` (unexpected)
- `response-type` returned `401` (unexpected)
- `rows` returned `401` (unexpected)
- `page` returned `401` (unexpected)
- `filter` returned `401` (unexpected)
- `type` returned `401` (unexpected)
- `ignore-status` returned `401` (unexpected)
- `tradable` returned `401` (unexpected)
- `time` returned `401` (unexpected)

---

## Group: internal integrations

### GET `/v2/tickers-all/source/data`

**Summary:**   
**Tags:** tickers-all-v-2  

#### Baseline Test

| Check | Result |
|-------|--------|
| Status Code | 401 FAIL |
| Valid JSON | PASS |
| Response Time | 504.89ms FAIL |

#### Auth Enforcement

PASS - Returned `401` without token.  

#### Parameter Analysis

| Parameter | Spec Required | Test Required | Status Without |
|-----------|:------------:|:------------:|:--------------:|
| `username` | No | Yes | 401 |
| `password` | No | Yes | 401 |
| `source-id` | No | Yes | 401 |
| `lang` | No | Yes | 401 |
| `required-fields` | No | Yes | 401 |
| `last-update-time` | No | Yes | 401 |
| `response-type` | No | Yes | 401 |
| `rows` | No | Yes | 401 |
| `page` | No | Yes | 401 |
| `filter` | No | Yes | 401 |
| `type` | No | Yes | 401 |
| `ignore-status` | No | Yes | 401 |
| `time` | No | Yes | 401 |
| `tradable` | No | Yes | 401 |

#### Empty Value Warnings

- `username` returned `401` (unexpected)
- `password` returned `401` (unexpected)
- `source-id` returned `401` (unexpected)
- `lang` returned `401` (unexpected)
- `required-fields` returned `401` (unexpected)
- `last-update-time` returned `401` (unexpected)
- `response-type` returned `401` (unexpected)
- `rows` returned `401` (unexpected)
- `page` returned `401` (unexpected)
- `filter` returned `401` (unexpected)
- `type` returned `401` (unexpected)
- `ignore-status` returned `401` (unexpected)
- `time` returned `401` (unexpected)
- `tradable` returned `401` (unexpected)

---

### GET `/v2/tickers-all/search`

**Summary:**   
**Tags:** tickers-all-v-2  

#### Baseline Test

| Check | Result |
|-------|--------|
| Status Code | 401 FAIL |
| Valid JSON | PASS |
| Response Time | 487.2ms FAIL |

#### Auth Enforcement

PASS - Returned `401` without token.  

#### Parameter Analysis

| Parameter | Spec Required | Test Required | Status Without |
|-----------|:------------:|:------------:|:--------------:|
| `username` | No | Yes | 401 |
| `password` | No | Yes | 401 |
| `term` | Yes | Yes | 400 |
| `fields` | Yes | Yes | 400 |
| `required-fields` | No | Yes | 401 |
| `response-type` | No | Yes | 401 |
| `sort-field` | No | Yes | 401 |
| `sort-asc` | No | Yes | 401 |
| `rows` | No | Yes | 401 |
| `filter` | No | Yes | 401 |
| `type` | No | Yes | 401 |
| `numfilter` | No | Yes | 401 |
| `page` | No | Yes | 401 |
| `ignore-status` | No | Yes | 401 |
| `time` | No | Yes | 401 |

#### Empty Value Warnings

- `username` returned `401` (unexpected)
- `password` returned `401` (unexpected)
- `term` returned `401` (unexpected)
- `fields` returned `401` (unexpected)
- `required-fields` returned `401` (unexpected)
- `response-type` returned `401` (unexpected)
- `sort-field` returned `401` (unexpected)
- `sort-asc` returned `401` (unexpected)
- `rows` returned `401` (unexpected)
- `filter` returned `401` (unexpected)
- `type` returned `401` (unexpected)
- `numfilter` returned `401` (unexpected)
- `page` returned `401` (unexpected)
- `ignore-status` returned `401` (unexpected)
- `time` returned `401` (unexpected)

---

### GET `/v2/tickers-all/keys/data`

**Summary:**   
**Tags:** tickers-all-v-2  

#### Baseline Test

| Check | Result |
|-------|--------|
| Status Code | 401 FAIL |
| Valid JSON | PASS |
| Response Time | 536.19ms FAIL |

#### Auth Enforcement

PASS - Returned `401` without token.  

#### Parameter Analysis

| Parameter | Spec Required | Test Required | Status Without |
|-----------|:------------:|:------------:|:--------------:|
| `username` | No | Yes | 403 |
| `password` | No | Yes | 403 |
| `keys` | Yes | Yes | 400 |
| `lang` | No | Yes | 401 |
| `required-fields` | No | Yes | 401 |
| `last-update-time` | No | Yes | 401 |
| `response-type` | No | Yes | 401 |
| `rows` | No | Yes | 401 |
| `filter` | No | Yes | 401 |
| `type` | No | Yes | 401 |
| `page` | No | Yes | 401 |
| `ignore-status` | No | Yes | 401 |
| `time` | No | Yes | 401 |
| `tradable` | No | Yes | 401 |

#### Empty Value Warnings

- `username` returned `401` (unexpected)
- `password` returned `401` (unexpected)
- `keys` returned `401` (unexpected)
- `lang` returned `401` (unexpected)
- `required-fields` returned `401` (unexpected)
- `last-update-time` returned `401` (unexpected)
- `response-type` returned `401` (unexpected)
- `rows` returned `401` (unexpected)
- `filter` returned `401` (unexpected)
- `type` returned `401` (unexpected)
- `page` returned `401` (unexpected)
- `ignore-status` returned `401` (unexpected)
- `time` returned `401` (unexpected)
- `tradable` returned `401` (unexpected)

---


*Report generated by Swagger-Driven API Test Suite - 2026-02-13 08:04:30*