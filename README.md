# Paradise.SPL — фіди для Prom.ua

`filter.py` скачивает поставщицкий фид [https://cyclone.ua/rss/cyclone_prom.xml](https://cyclone.ua/rss/cyclone_prom.xml), оставляет отобранные предложения и новые Bi-LED и записывает `public/cyclone_prom.xml`. Логіка Cyclone не змінюється. Якщо скачивание или отбор не удались, скрипт завершается с ошибкой, и на сайте остаётся последняя удачная выкладка.

`decibel.py` скачивает [https://api.decibel.com.ua/feed/drop_uk.xml](https://api.decibel.com.ua/feed/drop_uk.xml) и записывает `public/decibel_prom.xml`. Id оферов остаются как у Decibel (без префикса), цены и наличие не меняются. Оферы с `<vendor>` KiurLab, SWAG, Deaf Bonce или AVATAR не публикуются: список `EXCLUDED_VENDORS` в начале `decibel.py` (сравнение без регистра и крайних пробелов). Id и цены сверяются с источником без этих брендов. Категории, в которых не осталось оферов, удаляются. Каждому оставшемуся оферу добавляются теги Prom `portal_category_id` и `portal_category_url` по таблице `decibel_categories.csv`, а также характеристика `Виробник`. `Код запчастини` добавляется только если в источнике есть артикул (`vendorCode` или явный код). Исключённые позиции пишутся в `public/decibel_excluded.csv` (UTF-8 с BOM, разделитель `;`, колонки `id;vendor;name`). Если загрузка не удалась, опубликованных оферов меньше 250, id или цены разошлись с источником без исключённых брендов, или у оставшегося офера нет категории портала, скрипт завершается с ошибкой и предыдущая выкладка остаётся.

Workflow `.github/workflows/update.yml` запускається кожні 2 години, вручну (`workflow_dispatch`) і на push у `main`. Він збирає обидва фіди і публікує каталог `public` на GitHub Pages.

Готові фіди для імпорту посиланням у Prom.ua:

- https://hfidef-web.github.io/paradise-feeds/cyclone_prom.xml
- https://hfidef-web.github.io/paradise-feeds/decibel_prom.xml
- https://hfidef-web.github.io/paradise-feeds/decibel_excluded.csv — оферы Decibel, снятые с публикации (удалить на Prom)
