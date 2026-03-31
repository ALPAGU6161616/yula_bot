# YULA Bot - Hetzner Deployment Guide

Bu dokuman YULA Bot'unuzu Hetzner sunucusunda 24/7 çalıştırmak için gerekli adımları içerir.

## 🖥️ Sunucu Bilgileri

- **IP:** 46.62.223.244
- **Tip:** CX23 (2 vCPU, 4GB RAM, 40GB SSD)
- **OS:** Ubuntu
- **Konum:** Helsinki

## 📋 Gereksinimler

- SSH erişimi (root veya sudo yetkisi olan kullanıcı)
- Git veya SCP ile dosya yükleme imkanı
- Binance API anahtarları

## 🚀 Deployment Adımları

### Yöntem 1: Otomatik Deployment (Windows'tan)

1. **PowerShell'de deployment scriptini çalıştırın:**
   ```powershell
   # Git Bash veya WSL kullanıyorsanız:
   bash deploy.sh
   
   # Veya manuel olarak dosyaları yükleyin (aşağıya bakın)
   ```

2. **.env dosyasını güvenli şekilde yükleyin:**
   ```bash
   scp .env root@46.62.223.244:/root/YULA_Bot/
   ```

3. **Sunucuya SSH ile bağlanın:**
   ```bash
   ssh root@46.62.223.244
   ```

4. **Setup scriptini çalıştırın:**
   ```bash
   cd /root/YULA_Bot
   chmod +x setup_server.sh
   ./setup_server.sh
   ```

### Yöntem 2: Manuel Deployment

1. **Dosyaları manuel olarak yükleyin (WinSCP, FileZilla, vs.):**
   - Hedef dizin: `/root/YULA_Bot/`
   - Yüklenecek dosyalar:
     - `bot_runner.py`
     - `binance_ws.py`
     - `config.py`
     - `data_manager.py`
     - `trader.py`
     - `yula_strategy.py`
     - `requirements.txt`
     - `yula-bot.service`
     - `setup_server.sh`
     - `.env` (DİKKAT: Hassas dosya!)

2. **SSH ile bağlanın ve setup'ı çalıştırın:**
   ```bash
   ssh root@46.62.223.244
   cd /root/YULA_Bot
   chmod +x setup_server.sh
   ./setup_server.sh
   ```

## 🎯 Bot Yönetimi

### Temel Komutlar

```bash
# Durum kontrolü
systemctl status yula-bot

# Log'ları canlı izleme
journalctl -u yula-bot -f

# Bot'u durdurma
systemctl stop yula-bot

# Bot'u başlatma
systemctl start yula-bot

# Bot'u yeniden başlatma
systemctl restart yula-bot

# Son 100 log satırı
journalctl -u yula-bot -n 100

# Bugünün log'ları
journalctl -u yula-bot --since today
```

### Konfigürasyon Değişiklikleri

Bot parametrelerini değiştirmek için:

1. Service dosyasını düzenleyin:
   ```bash
   nano /etc/systemd/system/yula-bot.service
   ```

2. `ExecStart` satırındaki parametreleri değiştirin:
   ```
   --timeframe 15m              # Timeframe (5m, 15m, 1h, vs.)
   --pairs ARUSDT.P,TAOUSDT.P   # Trading çiftleri
   --start-from-flat            # Flat pozisyondan başla
   ```

3. Değişiklikleri uygulayın:
   ```bash
   systemctl daemon-reload
   systemctl restart yula-bot
   ```

## 🔍 Monitoring

### Log Format

Bot log'ları şu formatta görünür:
```
[ARUSDT/USDT:USDT] 2025-12-23 16:45:00 signal=1 trades=2
[TAOUSDT/USDT:USDT] 2025-12-23 16:45:00 signal=0 trades=0
```

- `signal=1`: Long sinyal
- `signal=-1`: Short sinyal
- `signal=0`: Sinyal yok
- `trades=X`: Açık trade sayısı

### Hata Ayıklama

**Bot başlamıyorsa:**
```bash
# Detaylı log
journalctl -u yula-bot -xe

# Manuel test
cd /root/YULA_Bot
source venv/bin/activate
python bot_runner.py --timeframe 15m --pairs ARUSDT.P
```

**WebSocket bağlantı hatası:**
- Binance API erişilebilir mi kontrol edin
- Firewall kurallarını kontrol edin

**API hataları:**
- `.env` dosyasındaki anahtarları kontrol edin
- Binance hesabınızda Futures açık mı kontrol edin

## 📊 Kaynak Kullanımı

Bot'un kaynak kullanımını kontrol etmek için:

```bash
# CPU ve RAM kullanımı
top -p $(pgrep -f bot_runner)

# Detaylı sistem bilgisi
htop
```

**Beklenen kullanım:**
- RAM: ~50-100 MB
- CPU: %1-5 (candle kapanışlarında %10-20)
- Network: ~1-5 KB/s

## 🔐 Güvenlik

- `.env` dosyası root kullanıcısına ait olmalı
- Gereksiz portlar kapalı tutulmalı
- SSH key authentication kullanın (password yerine)
- Düzenli sistem güncellemeleri yapın:
  ```bash
  apt update && apt upgrade -y
  ```

## 🆘 Troubleshooting

### Bot kapanıyor/restart oluyor

```bash
# Restart sebeplerini göster
systemctl status yula-bot

# Detaylı log
journalctl -u yula-bot --since "1 hour ago"
```

### Mevcut bot çakışması

Eğer eski bot hala çalışıyorsa:
```bash
# Tüm Python processlerini listele
ps aux | grep python

# İlgili process'i durdur
kill -9 <PID>
```

### Port çakışması

Bot WebSocket kullandığı için port çakışması genelde olmaz, ama kontrol için:
```bash
netstat -tulpn | grep python
```

## 📞 Destek

Sorun yaşarsanız log dosyalarını paylaşın:
```bash
journalctl -u yula-bot -n 200 --no-pager > bot_logs.txt
```
