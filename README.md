# Paradise.SPL — фильтр фида Cyclone для Prom.ua

`filter.py` скачивает поставщицкий фид [https://cyclone.ua/rss/cyclone_prom.xml](https://cyclone.ua/rss/cyclone_prom.xml), оставляет отобранные предложения и новые Bi-LED и записывает `public/cyclone_prom.xml`. Если скачивание или отбор не удались, скрипт завершается с ошибкой, и на сайте остаётся последняя удачная выкладка.

Workflow `.github/workflows/update.yml` запускается каждые 2 часа и вручную (`workflow_dispatch`), собирает фид и публикует каталог `public` на GitHub Pages.

Готовый фид для импорта по ссылке в Prom.ua:

https://hfidef-web.github.io/paradise-feeds/cyclone_prom.xml
