# video-publish-check

**בדיקת סרטון לפני פרסום, בשביל סוכני קוד.** `vpc` יושב על
[claude-eyes](https://github.com/moritzkremb/claude-eyes), שנותן לסוכן תמלול ברמת מילה, חיתוכים,
עוצמה ופריימים, ומוסיף את השכבה שחסרה בו: ספים, בדיקה מול התסריט, חיתוכים שנופלים בתוך מילים,
מעברים רכים, ודוח בעברית שהוא רשימת תיקונים ממוספרת עם חותמות זמן.

```
$ vpc check render.mp4 --script script.md --glossary "סטודיו אילון, קלוד"

# בדיקה לפני פרסום: render.mp4
אורך: 11:42 | מילים לדקה: 151 | LUFS: -17.8 | חיתוכים: 64 | מעברים רכים: 9 | תמלול: elevenlabs (scribe_v2)

## תיקונים (לפי סדר זמן)
1. [0:00] עוצמה משולבת -17.8 LUFS, יעד -14 → לנרמל את המיקס (loudnorm) לפני יצוא
2. [1:12] קריינות מהירה: 178 מילים לדקה בחלון של 30 שניות → להאט את ההקלטה או לקצר את הטקסט
3. [3:41] שקט של 4.2 שניות → לבדוק בפריים: מעבר מכוון או חור 👁
4. [6:05] חיתוך באמצע המילה 'הסטודיו' → להזיז את החיתוך לגבול מילה 👁
5. [9:30] בתסריט אבל לא נאמר: "ועכשיו לחלק החשוב באמת" → להשלים קריינות או לעדכן תסריט
```

## מה eyes נותן ומה vpc מוסיף

| | eyes | vpc |
|---|---|---|
| תמלול עם זמן לכל מילה, חיתוכים, LUFS, OCR, פריימים | ✔ | משתמש |
| קצב קריינות בחלונות של 30 שניות (ממוצע מסתיר קטעים מהירים) | | ✔ |
| שקטים בין מילים, עם הפניה לפריים | | ✔ |
| חיתוך שנופל באמצע מילה | | ✔ |
| diff של התמלול מול התסריט (עברית, בלי ניקוד ופיסוק) | | ✔ |
| מעברים רכים (dissolve, fade). eyes מוצא 0 מהם | | ✔ |
| ספי LUFS ו true peak ליוטיוב | | ✔ |
| דוח בעברית: תיקונים, עבר, לא נבדק | | ✔ |
| סקיל שמחייב בדיקה בעיניים של כל שקט וחיתוך חשוד | | ✔ |

## התקנה

```bash
uv tool install git+https://github.com/meylon7/video-publish-check   # או pipx; מתקין גם claude-eyes
eyes setup --fix                                                      # ffmpeg, whisper.cpp, מודל
eyes setup --download-model large-v3                                  # חובה לעברית
vpc install-skill                                                     # מעתיק את הסקיל ל ~/.claude/skills
```

ב Claude Code אחר כך: `/video-publish-check` עם נתיב הרנדר, או "תבדוק את הרנדר לפני שאני מעלה".

תמלול: כש `ELEVENLABS_API_KEY` מוגדר (סביבה או `.env`), vpc עובר ל ElevenLabs Scribe, שמדויק
יותר בעברית ומעלה את האודיו בלבד. אחרת whisper.cpp מקומי.

## פקודות

```
vpc check RENDER [--script S] [--glossary G] [--lang he] [--out FILE] [--json]
                 [--no-index] [--no-dissolves] [--force]
                 [--wpm-min 110] [--wpm-max 160] [--window 30] [--gap 2.5]
                 [--lufs-target -14] [--lufs-tol 1.5]
vpc dissolves MEDIA [--fps 8] [--json]     מעברים רכים בלבד
vpc install-skill [--to DIR]               הסקיל ל Claude Code (ברירת מחדל ~/.claude/skills)
```

## איך זיהוי המעברים הרכים עובד

חיתוך קשה הוא פריים אחד ששונה בחדות משכניו. dissolve מפזר את אותו שינוי על 0.5 עד 2 שניות,
אז אף פריים לא קופץ ו eyes לא רואה כלום. `vpc` משווה פריימים במרחק חלון (0.5, 1, 2 שניות) במקום
פריימים סמוכים, ודורש שהתמונה תהיה רגועה משני צדי החלון, יחסית לגודל השינוי, כך שתנועה
בתוך סצנה לא נספרת. אם צעד בודד בתוך החלון נושא רוב השינוי, זה חיתוך קשה ו eyes כבר דיווח עליו.
הזמן המדווח הוא הנקודה שבה חצי מהשינוי קרה. נבדק על וידאו סינתטי עם dissolve של שנייה וחצי על
רקע נע: סטייה של 0.06 שניות, והחיתוך הקשה לא דווח.

## מה הכלי לא רואה

- איכות הקליפים עצמם: אצבעות, פנים שמשתנות, תנועה לא טבעית. דגימות, לא זרם.
- טון דיבור, סאונד דיזיין. מוזיקה היא עוצמה וביט בלבד.
- OCR בעברית מחוץ ל Mac (RapidOCR לא תומך בעברית; Apple Vision כן).

## פיתוח

```bash
uv venv && . .venv/bin/activate
uv pip install -e ".[dev]"
pytest
```

הבדיקות בונות וידאו סינתטי עם ffmpeg (צבעים, dissolve, חיתוך קשה) ולא דורשות eyes.

---

## English

Pre publish QA for rendered videos, for coding agents. `vpc` sits on
[claude-eyes](https://github.com/moritzkremb/claude-eyes) (word timed transcript, cuts, loudness, frames)
and adds the decision layer: thresholds, a diff against the script, cuts landing inside spoken words,
soft transition detection (eyes finds none), YouTube loudness targets, and a report that is a numbered
fix list with timestamps. Hebrew first: transcript matching strips niqqud and punctuation, and the
default transcriber switches to ElevenLabs Scribe when a key is present, because small whisper models
break Hebrew.

```bash
uv tool install git+https://github.com/meylon7/video-publish-check
eyes setup --fix && eyes setup --download-model large-v3
vpc install-skill
vpc check render.mp4 --script script.md
```

MIT.
