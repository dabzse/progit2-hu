# Tipográfiai és Helyesírási Eszközök a Pro Git (Magyar) Projekthez

Ez a dokumentáció a Pro Git 2 magyar fordításához készült automatikus tipográfiai és helyesírási eszközök működését, szabályait és használatát mutatja be.

A lefordított könyv (főként a PDF, EPUB és HTML változatok) tördelése során gyakran előfordultak tipográfiai hibák – például a sorok végén magányosan árválkodó névelők („a”, „az”) vagy nem megfelelően elválasztott összetett szavak. Mivel az Asciidoctor és a Rakefile alapértelmezetten nem tartalmaz ilyen előfeldolgozást, az alábbi önálló és beépített eszközök valósítják meg ezen szabályok automatikus érvényesítését.

Minden eszköz elérhető mind **Python 3** (`.py`), mind **Ruby** (`.rb`) nyelven, valamint közvetlenül a **Rakefile**-ból is futtatható.

---

## 1. Az elkészült eszközök

### A) `fix_orphan_a.py` és `fix_orphan_a.rb`

* **Cél:** Általános, nyelvfüggetlen eszköz az árva egybetűs szavak (alapértelmezetten az `a` és `A`) sorvégi és szó előtti rögzítésére.
* **Működés:** A magányosan álló `a` / `A` utáni szóközt vagy sortörést nem törhető szóközre (Unicode U+00A0 `\u00A0` vagy kapcsolóval AsciiDoc `{nbsp}`) cseréli. Így a böngészők és a PDF-tördelő (Prawn) a névelőt és a rákövetkező szót egyetlen elválaszthatatlan egységként kezeli, megakadályozva a sorvégi árvulást.
* **Többnyelvűség:** A `--words` kapcsolóval bármely más nyelvhez is használható (pl. `--words a,A,o,O` portugálhoz vagy `--words a,A,y,Y` szláv nyelvekhez).

### B) `fix_hu_typographical_rules.py` és `fix_hu_typographical_rules.rb`

* **Cél:** Kifejezetten a magyar helyesírási (AkH. 12.) és tipográfiai szabályok automatikus érvényesítése az AsciiDoc forrásfájlokban.
* **Megvalósított szabályok:**
  1. **`e-mail-cím` és e-mail összetételek:**
     * A helytelen alakokat (`email cím`, `e-mail cím`, `email-cím`) a szabályos **`e-mail-cím`** alakra javítja minden ragozott formájával együtt (`e-mail-címet`, `e-mail-címek`, `e-mail-címe`, `e-mail-címünk`, `e-mail-címeid`, `e-mail-címével`, stb.).
     * **Nem törhető kötőjellel** (Unicode U+2011, `\u2011`) látja el: `e‑mail‑cím`, így a szó soha nem tördelhető szét sor végén `e-` és `mail` darabokra.
     * Ugyanezt elvégzi a többi e-mail összetételnél is: `e‑mail‑fiók`, `e‑mail‑értesítés`, `e‑mail‑szolgáltatás`, `e‑mail‑munkafolyamat`, `e‑mail‑alapú`, `e‑mail‑küldés`, `e‑mail‑üzenet`, `e‑mail‑kliens`.
     * Az önálló `e-mail` szót is nem törhető kötőjellel látja el.
  2. **Magyar árva szavak (névelők és kötőszavak):**
     * Határozott és határozatlan névelők: `a`, `az`, `egy`, `A`, `Az`, `Egy`
     * Kötőszavak: `és`, `s`, `És`, `S`, `de`, `De`
     * A szavak után nem törhető szóközt tesz, megelőzve a sorvégi lebegést.
  3. **Számok, sorszámok és mértékegységek:**
     * Sorszámok szerkezeti elemek előtt: `1. ábra`, `2. táblázat`, `3. fejezet`, `4. szakasz`, `5. oldal`, `1. pont` ➔ a pont után nem törhető szóköz kerül.
     * Mértékegységek és mennyiségek: `100 bájt`, `64 bit`, `10 MB`, `5 perc`, `24 óra`, stb. ➔ a szám és a mértékegység közé nem törhető szóköz kerül.
     * Gyakori rövidítések: `pl. `, `kb. `, `i. e. `, `i. sz. ` ➔ a rövidítés után nem törhető szóköz kerül.
  4. **Gondolatjel (Dashes):**
     * A szövegközi gondolatjel (` -- ` vagy ` – `) elé nem törhető szóközt tesz (`\u00A0– `), így a gondolatjel soha nem kerülhet egy új sor legelejére.
  5. **Magyar idézőjelek (opcionális, `--fix-quotes`):**
     * A sima egyenes idézőjeleket (`"..."`) a magyar szabványos alsó-felső macskakörömre (`„...”`) cseréli a folyószövegben.

---

## 2. AsciiDoc szintaxisvédelem (Syntax-Aware Tokenizer)

Az eszközök intelligens szintaxiselemzővel rendelkeznek, amely a forrásfájlokat védett blokkokra és folyószövegre bontja. **Garantáltan érintetlenül hagyja az alábbi elemeket:**

* **Kódblokkok:** `----` (forráskód / listing), `....` (literal), `++++` (passthrough) blokkok teljes tartalma.
* **Inline kódok:** `` `user.email` ``, `` `git commit -a -m "Hibás e-mail cím"` ``.
* **Webcímek és e-mail címek:** `https://github.com`, `<user@example.com>`.
* **AsciiDoc direktívák és metaadatok:** `image::...`, `video::...`, `include::...`, `:attribute: value`, `ifdef::...`, `endif::`.
* **Hivatkozások és azonosítók:** `[[anchor_id]]`, `[#anchor_id]`, `<<anchor,címke>>`, `link:...[...]`, `xref:...[...]`.
* **Tárgymutató bejegyzések és sorszámozott megjegyzések:** `(((index,kifejezés)))`, calloutok (`<1>`, `<2>`).
* **Megjegyzések:** `// ...`.

A javítások kizárólag a valódi folyószövegben (bekezdések, fejezetcímek, listaelemek szövege, táblázatcellák szövege) lépnek érvénybe.

---

## 3. Rakefile integráció

A projekt [Rakefile](Rakefile) fájlja ki lett egészítve a szükséges feladatokkal, így külső függőségek nélkül közvetlenül futtathatók:

```bash
# 1. Magyar tipográfiai és helyesírási szabályok javítása (e-mail-cím, névelők, számok stb.)
rake book:fix_hu_typography

# 2. Árva 'a' és 'A' betűk javítása (nyelvfüggetlen)
rake book:fix_orphan_a

# 3. Tipográfiai ellenőrzés módosítás nélkül (pl. CI / PR ellenőrzéshez, kilépési kóddal)
rake book:check_typography
```

---

## 4. Parancssori használat és kapcsolók

Mind a Python, mind a Ruby változatok gazdag parancssori eszköztárral rendelkeznek:

### Általános kapcsolók

* `-w`, `--write`: A módosítások helyben történő mentése a fájlokba.
* `-n`, `--dry-run`: Előnézet és számlálás fájlmódosítás nélkül (alapértelmezett).
* `-d`, `--diff`: Egységes (unified) diff mutatása a változtatásokról.
* `-c`, `--check`: Kilépés `1`-es hibakóddal, ha javítandó hiba található (automatizált CI munkafolyamatokhoz).
* `--use-entity`: Unicode `\u00A0` helyett az AsciiDoc `{nbsp}` entitás használata.

### Futtatási példák

```bash
# Előnézet és statisztika készítése a teljes könyvről:
python3 fix_hu_typographical_rules.py --dry-run
# Vagy Ruby-val:
ruby fix_hu_typographical_rules.rb --dry-run

# Diff megtekintése egy adott fejezeten:
python3 fix_hu_typographical_rules.py book/06-github/sections/1-setting-up-account.asc --diff

# Tényleges javítás végrehajtása az összes fájlon:
python3 fix_hu_typographical_rules.py --write
# Vagy Ruby-val:
ruby fix_hu_typographical_rules.rb --write

# Csak az e-mail és az árva betűk szabályainak futtatása:
python3 fix_hu_typographical_rules.py --rules email,orphans --write

# Csak az árva 'a' javítása {nbsp} formátummal:
python3 fix_orphan_a.py --use-entity --write
```

---

## 5. Tesztelési statisztikák a könyv állapotán

A teljes [book/](book/) könyvtáron lefutatott száraz teszt eredményei:

| Kategória                           | `fix_orphan_a` | `fix_hu_typographical_rules` |
| :---------------------------------- | :------------- | :--------------------------- |
| **Vizsgált fájlok száma**           | 109            | 109                          |
| **Érintett fájlok száma**           | 105            | 105                          |
| **Összes javítás**                  | **8 225**      | **14 489**                   |
| - Árva névelők és kötőszavak        | 8 225          | 14 111                       |
| - `e-mail-cím` és összetételek      | -              | 57                           |
| - Gondolatjelek (` -- `, ` – `)     | -              | 290                          |
| - Számok, sorszámok, mértékegységek | -              | 31                           |
