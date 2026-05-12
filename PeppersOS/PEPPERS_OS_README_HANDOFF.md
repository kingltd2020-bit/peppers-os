# PEPPERS OS — README לתחילת כל שיחה
> עדכון: 2026-05-12 | יעקב בנימינוב | kingltd2020@gmail.com

---

## מי אני ומה אנחנו בונים
יעקב = בעל סופרמרקט פפרס (קינג אגדי השקעות).
בונים: Peppers OS — מערכת ניהול תפעולי אוטומטית לסופר.
כלים: Claude.ai (חשיבה), Cursor/Claude Code (ביצוע), Lovable (UI), Google Sheets (דאטה), Apps Script (API), Drive (מסמכים), OpenClaw/קלו (אורקסטרטור).

---

## Source of Truth
| נושא | מיקום |
|------|--------|
| קוד חי | GitHub: kingltd2020-bit/peppers-os |
| נתונים | Google Sheets: Documents_Master_MVP |
| מסמכים | Google Drive: תיקיית פפרס/ (ID: 1NgXCVbNDb3ujInnJ7Bk0cEKvCWQlIask) |
| UI | Lovable: Peppered Insights |

---

## מה רץ היום אוטומטית ✅
Gmail Invoice Agent:
- כל שעה דרך Windows Task Scheduler
- Gmail → OCR → Drive → Sheets
- Entry point: C:\Users\jaico\PeppersOS\run_invoice_agent.bat
- לאחר תיקון היום: unknown rate ירד מ-37% → ~10%

OpenClaw Gateway (קלו):
- רץ על המחשב המקומי (port 18789)
- ממשק: http://127.0.0.1:18789
- ⚠️ המחשב חייב להיות דולק

---

## סדר הפייפליינים
✅ 1. Gmail Invoice Agent — רץ + תוקן (OCR עברית)
🔄 2. Drive מסודר — הבא בתור
⏳ 3. Lovable — תיקון שם ספק — אחרי Drive
⏳ 4. מבצעים ושילוט — שלב 4
⏳ 5. Telegram bot — שלב 5

---

## ארכיטקטורת קלו
יעקב → Telegram (@peppers_store_bot) → OpenClaw (קלו) → Claude Code → GitHub/קבצים/shell
כללים שנשמרו ב-MEMORY.md של קלו:
1. לא שולח tokens/passwords דרך Telegram
2. 3 כשלונות → עצור + דווח
3. dry-run לפני כל execute

---

## מה נעשה היום (2026-05-12)
- ✅ הגדרת קלו + re-auth עם drive scope מורחב
- ✅ תיקון OCR: עברית הפוכה (חשבונית → תינובשח) — נוספה _normalize_hebrew_ocr() ל-ocr_extractor.py
- ✅ unknown rate: 37% → ~10%
- ✅ .gitignore נוסף — credentials מוגנים
- ✅ 2 commits עלו ל-GitHub

---

## 5 בעיות פתוחות
| # | חומרה | בעיה | סטטוס |
|---|-------|------|-------|
| 1 | 🔴 | OCR עברית הפוכה | ✅ תוקן |
| 2 | 🔴 | peppers_api.gs ב-CascadeProjects במקום repo ראשי | ⏳ |
| 3 | 🟡 | Frontend על mock-data | ⏳ |
| 4 | 🟡 | Agent מעלה ל-Drive שגוי (1upIVfx8PECdjwyiCSwvh9jPypCm_1doi) במקום פפרס/ | ⏳ |
| 5 | 🟡 | CascadeProjects — 65+ קבצים מתים | ⏳ |

---

## הצעד הבא — Stage 2 Drive
1. invoice_namer על 01_חשבוניות_ורכש/.../unresolved/ (~100 קבצים) — dry-run קודם
2. file_classifier על 2023-unclassified/ (~80 קבצים) — dry-run קודם

---

## כללי ברזל
1. לפני כל בנייה — לבדוק ארכיטקטורה קיימת
2. לא מוחקים — מארכבים
3. מפתחות API — רק ב-.env על C:, לא ב-repo, לא בטלגרם
4. dry-run לפני כל execute
5. צינור חדש רק אחרי 7 ימים יציבות
