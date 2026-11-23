# Источники данных

- Контур трассы `data/es-1991.geojson` — Tomislav Bacinger, «f1-circuits» (https://github.com/bacinger/f1-circuits), лицензия MIT (`data/LICENSE_f1-circuits.md`). Данные неофициальные.
- Рельеф `data/terrain/*.png` — AWS Terrain Tiles (Mapzen, Terrarium), https://registry.opendata.aws/terrain-tiles/ — открытые данные; источники высот: SRTM, ETOPO1 и др. (атрибуция: «© Mapzen, data sources: https://github.com/tilezen/joerd/blob/master/docs/attribution.md»).
- Длины секторов: схема трассы Circuit de Barcelona-Catalunya (circuitcat.alkamelsystems.com): S1 1557 м, S2 1722 м, S3 1376 м.
- Время круга: ориентир — гонка Гран-при Испании 2024 (Википедия): быстрейший круг 1:17.115, средний круг победителя 1:20.3. Модель скорости настроена на летящий круг 1:18.0.
- Машина: модель «AMR-24 V1» (Abu Saif, CC BY 4.0) — см. `../real-f1/CREDITS.md`.
- Шрифт табло: Inter (SIL Open Font License).
- Окружение (Poly Haven, CC0, https://polyhaven.com/license): небо «kloppenheim_07_puresky»; текстуры asphalt_02, aerial_grass_rock, gravel, concrete; модели island_tree_01, island_tree_02, tree_small_02, searsia_lucida, shrub_01, shrub_03, concrete_road_barrier, modular_chainlink_fence, old_tyre, plastic_monobloc_chair_01. Скачиваются `tools/get_assets.py` (в репозиторий не положены).
- Голос радио: Piper (MIT), голос en_US-joe-medium (датасет OHF-Voice, CC0). Фразы синтезированы, голос не подражает реальному пилоту.
- Звук двигателя, шин, тормозов, ветра и эффектов синтезирован кодом (`tools/audio.py`).
