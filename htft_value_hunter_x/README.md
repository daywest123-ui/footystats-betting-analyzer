# HT/FT VALUE HUNTER X — MOBILE V1

Telefon merkezli HT/FT + value + backtest motoru. Mevcut FootyStats analiz projesine ayrı bir modül olarak eklenmiştir.

## Özellikler
- 9 HT/FT olasılığı: 1/1, 1/X, 1/2, X/1, X/X, X/2, 2/1, 2/X, 2/2
- Poisson gol modeli
- Fair odds / implied probability / value
- Kronolojik rolling backtest
- Brier Score
- GitHub Actions veri güncelleme iskeleti
- GitHub Pages için mobil panel

## Kullanım
```bash
pip install -r htft_value_hunter_x/requirements.txt
python htft_value_hunter_x/engine.py --home "Team A" --away "Team B" --home-goals 1.8 --away-goals 1.1
python htft_value_hunter_x/backtest.py --input htft_value_hunter_x/data/matches.csv
```

V1 garanti kazanç iddiasında bulunmaz; amaç olasılıkları ölçmek, kalibre etmek ve geçmişte test etmektir.

## V2
Elo, xG, ev/deplasman split, form, piyasa hareketi, FootyStats sinyalleri ve market bazlı calibration/ROI eklenecek.
