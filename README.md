# Paradise.SPL — фіди для Prom.ua

`filter.py` скачивает поставщицкий фид [https://cyclone.ua/rss/cyclone_prom.xml](https://cyclone.ua/rss/cyclone_prom.xml), оставляет отобранные предложения и новые Bi-LED и записывает `public/cyclone_prom.xml`. Логіка Cyclone не змінюється. Якщо скачивание или отбор не удались, скрипт завершается с ошибкой, и на сайте остаётся последняя удачная выкладка.

`decibel.py` скачивает [https://api.decibel.com.ua/feed/drop_uk.xml](https://api.decibel.com.ua/feed/drop_uk.xml) і записує `public/decibel_prom.xml`. Id оферів лишаються як у Decibel (без префікса), ціни й наявність не змінюються. Кожному оферу додаються теги Prom `portal_category_id` і `portal_category_url` за таблицею `decibel_categories.csv`, а також характеристика `Виробник`. `Код запчастини` додається лише якщо у джерелі є артикул (`vendorCode` або явний код). Якщо завантаження не вдалося, оферів менше ніж 300, множина id або ціни розійшлися з джерелом, або для категорії немає категорії порталу, скрипт завершується з помилкою і попередня викладка лишається.

Workflow `.github/workflows/update.yml` запускається кожні 2 години, вручну (`workflow_dispatch`) і на push у `main`. Він збирає обидва фіди і публікує каталог `public` на GitHub Pages.

Готові фіди для імпорту посиланням у Prom.ua:

- https://hfidef-web.github.io/paradise-feeds/cyclone_prom.xml
- https://hfidef-web.github.io/paradise-feeds/decibel_prom.xml
