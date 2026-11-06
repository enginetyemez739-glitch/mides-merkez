import os
import pandas as pd
from datetime import datetime
import requests
from supabase import create_client

# GitHub Secrets'tan Supabase bilgilerini al
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def otomatik_rapor_gonder():
    # 1. Kullanıcıları Çek
    res_users = supabase.table('kullanicilar').select("*").execute()
    if not res_users.data: return
    users = pd.DataFrame(res_users.data)
    
    # 2. Telegram bilgisi dolu olanları filtrele
    users_with_tg = users[(users['telegram_token'].notna()) & (users['telegram_token'] != '') & (users['chat_id'].notna()) & (users['chat_id'] != '')]
    bugun = datetime.now().date()
    
    for _, user in users_with_tg.iterrows():
        firma = user['firma']
        token = user['telegram_token']
        chat_id = user['chat_id']
        
        rapor_mesaji = f"⚠️ {firma} - GÜNLÜK OTOMATİK UYARI RAPORU ⚠️\n\n"
        krt_sayisi = 0
        
        # 3. Firmanın hem gıda hem temizlik deposunu tara
        tablolar = ['gida_deposu', 'temizlik_deposu']
        for tablo in tablolar:
            res_items = supabase.table(tablo).select("*").eq('firma', firma).execute()
            if res_items.data:
                items = pd.DataFrame(res_items.data)
                for _, urun in items.iterrows():
                    urun_adi = urun.get('urun_adi', 'Bilinmiyor')
                    miktar = float(urun.get('miktar', 0))
                    birim = urun.get('birim', '')
                    kritik = float(urun.get('kritik_stok', 10))
                    skt_str = urun.get('skt', '')
                    
                    # SKT Kontrolü
                    if skt_str and skt_str != '-':
                        try:
                            skt = datetime.strptime(skt_str, '%Y-%m-%d').date()
                            kalan = (skt - bugun).days
                            if kalan < 0:
                                rapor_mesaji += f"❌ {urun_adi} - TARİHİ GEÇTİ! ({skt_str})\n"
                                krt_sayisi += 1
                            elif 0 <= kalan <= 30:
                                rapor_mesaji += f"⚠️ {urun_adi} - {kalan} gün kaldı!\n"
                                krt_sayisi += 1
                        except: pass
                    
                    # Stok Kontrolü
                    if miktar <= kritik:
                        rapor_mesaji += f"📉 ALARM: {urun_adi} (Kalan: {int(miktar)} {birim})\n"
                        krt_sayisi += 1
        
        # 4. Eğer uyarı varsa Telegram'a gönder
        if krt_sayisi > 0:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, data={"chat_id": chat_id, "text": rapor_mesaji})

if __name__ == "__main__":
    otomatik_rapor_gonder()
