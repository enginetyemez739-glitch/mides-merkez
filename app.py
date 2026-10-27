import streamlit as st
import pandas as pd
from datetime import datetime
import os
import qrcode
from io import BytesIO
from PIL import Image
import requests
import cv2
import numpy as np
import hashlib
import base64

st.set_page_config(page_title="MİDES - Akıllı Depo", page_icon="📦", layout="wide")

def sifre_hashle(sifre):
    return hashlib.sha256(str(sifre).encode('utf-8')).hexdigest()

# --- SUPABASE BAĞLANTI AYARLARI ---
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

def supabase_get(table):
    url = f"{SUPABASE_URL}/rest/v1/{table}?select=*"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        return response.json()
    return []

def supabase_insert(table, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    response = requests.post(url, headers=HEADERS, json=data)
    return response.status_code in [200, 201]

def supabase_update(table, id_val, id_col, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}?{id_col}=eq.{id_val}"
    response = requests.patch(url, headers=HEADERS, json=data)
    return response.status_code == 200

def supabase_delete(table, id_val, id_col):
    url = f"{SUPABASE_URL}/rest/v1/{table}?{id_col}=eq.{id_val}"
    response = requests.delete(url, headers=HEADERS)
    return response.status_code == 204

def verileri_getir():
    kayitlar = supabase_get("Malzemeler")
    if not kayitlar:
        return pd.DataFrame(columns=["ID", "Stok No", "Ürün Adı", "Miktar", "Birim", "Eklenme Tarihi", "SKT", "Üretim Tarihi", "Giriş Tarihi", "Resim Yolu", "Kritik Stok", "Alım Türü", "Sözleşme No", "Sözleşme Tarihi", "Sözleşme Bitiş Tarihi", "Sözleşme Kritik"])
    return pd.DataFrame(kayitlar)

def hareketleri_getir():
    kayitlar = supabase_get("Hareket_Gecmisi")
    if not kayitlar:
        return pd.DataFrame(columns=["ID", "Tarih", "Kullanıcı", "İşlem", "Ürün Adı", "Miktar", "Açıklama"])
    return pd.DataFrame(kayitlar).sort_values(by="ID", ascending=False)

def geri_bildirimleri_getir():
    kayitlar = supabase_get("Geri_Bildirimler")
    if not kayitlar:
        return pd.DataFrame(columns=["ID", "Tarih", "Kullanıcı", "Tür", "Mesaj"])
    return pd.DataFrame(kayitlar).sort_values(by="ID", ascending=False)

def log_kaydet(kullanici, islem_tipi, urun_adi, miktar, aciklama):
    zaman = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    df_hareket = hareketleri_getir()
    yeni_id = 1 if df_hareket.empty else int(df_hareket['ID'].max()) + 1
    data = {
        "ID": yeni_id,
        "Tarih": zaman,
        "Kullanıcı": kullanici,
        "İşlem": islem_tipi,
        "Ürün Adı": urun_adi,
        "Miktar": miktar,
        "Açıklama": aciklama
    }
    supabase_insert("Hareket_Gecmisi", data)

def qr_olustur(metin):
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(metin)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def telegram_mesaj_gonder(mesaj):
    if 'telegram_token' in st.session_state and 'telegram_chat_id' in st.session_state:
        token = st.session_state['telegram_token']
        chat_id = st.session_state['telegram_chat_id']
        if token and chat_id and str(token).lower() != "nan" and str(chat_id).lower() != "nan":
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {"chat_id": chat_id, "text": mesaj}
            try: requests.post(url, data=payload)
            except: pass

# --- OTURUM YÖNETİMİ ---
df_kullanicilar = pd.DataFrame(supabase_get("Kullanıcılar"))

if 'giris_yapildi' not in st.session_state:
    st.session_state.update({
        'giris_yapildi': False, 
        'kullanici': "", 
        'rol': "", 
        'sifre_degistirme_modu': False, 
        'ilk_giris_uyarisi': False,
        'telegram_token': "",
        'telegram_chat_id': ""
    })

if st.session_state['sifre_degistirme_modu']:
    if st.session_state.get('ilk_giris_uyarisi'):
        st.warning("⚠️ Sisteme ilk girişiniz! Lütfen devam etmek için şifrenizi belirleyin.")
    else:
        st.warning("⚠️ Şifrenizin kullanım süresi dolmuş. Lütfen yeni şifre belirleyin.")
        
    yeni_sifre = st.text_input("Yeni Şifre:", type="password")
    yeni_sifre_tekrar = st.text_input("Yeni Şifre (Tekrar):", type="password")
    
    if st.button("Şifreyi Güncelle"):
        if yeni_sifre == yeni_sifre_tekrar and len(yeni_sifre) >= 4:
            bugun = datetime.today().strftime('%Y-%m-%d')
            yeni_sifre_hash = sifre_hashle(yeni_sifre)
            guncelleme_data = {"Sifre": yeni_sifre_hash, "Son Güncelleme": bugun, "İlk Giriş": "Hayır"}
            supabase_update("Kullanıcılar", st.session_state['kullanici'], "Kullanıcı Adi", guncelleme_data)
            
            st.success("Şifreniz güncellendi! Lütfen sayfayı yenileyerek giriş yapın.")
            st.session_state['sifre_degistirme_modu'] = False
            st.session_state['giris_yapildi'] = False
            st.session_state['ilk_giris_uyarisi'] = False
            st.rerun()
        else:
            st.error("Şifreler uyuşmuyor veya çok kısa.")
    st.stop()

if not st.session_state.get('giris_yapildi', False):
    st.markdown("<h1 style='text-align: center;'> 📦 MİDES Depo Yönetim Sistemi</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            kadi_input = st.text_input("Kullanıcı Adı")
            sifre_input = st.text_input("Şifre", type="password")
            
            if st.form_submit_button("Giriş Yap", use_container_width=True):
                girilen_hash = sifre_hashle(sifre_input)
                
                # Kullanıcıyı filtrele (Supabase sütun adıyla tam uyumlu)
                kullanici = df_kullanicilar[(df_kullanicilar['Kullanıcı Adi'] == kadi_input) & (df_kullanicilar['Sifre'] == girilen_hash)]
                
                if not kullanici.empty:
                    yetki = kullanici['Yetki'].values[0]
                    ilk_giris = str(kullanici['İlk Giriş'].values[0]).strip().lower() if 'İlk Giriş' in kullanici.columns else "hayır"
                    
                    st.session_state['kullanici'] = kadi_input
                    st.session_state['rol'] = str(yetki).strip().lower()
                    
                    # Veritabanından (Supabase) kullanıcının Telegram bilgilerini çekiyoruz
                    if 'Telegram Token' in kullanici.columns and not pd.isna(kullanici['Telegram Token'].values[0]):
                        st.session_state['telegram_token'] = str(kullanici['Telegram Token'].values[0])
                    if 'Telegram Chat ID' in kullanici.columns and not pd.isna(kullanici['Telegram Chat ID'].values[0]):
                        st.session_state['telegram_chat_id'] = str(kullanici['Telegram Chat ID'].values[0])
                    
                    if ilk_giris == "evet":
                        st.session_state['sifre_degistirme_modu'] = True
                        st.session_state['ilk_giris_uyarisi'] = True
                        st.rerun()
                    else:
                        son_guncelleme_val = kullanici['Son Güncelleme'].values[0] if 'Son Güncelleme' in kullanici.columns else None
                        if pd.isna(son_guncelleme_val):
                            st.session_state['giris_yapildi'] = True
                            st.rerun()
                        else:
                            son_guncelleme = pd.to_datetime(son_guncelleme_val, errors='coerce')
                            gecen_gun = (datetime.today() - son_guncelleme).days if not pd.isna(son_guncelleme) else 0
                            if gecen_gun >= 90:
                                st.session_state['sifre_degistirme_modu'] = True
                                st.rerun()
                            else:
                                st.session_state['giris_yapildi'] = True
                                st.rerun()
                else:
                    st.error("❌ Kullanıcı adı veya şifre hatalı!")
else:
    df = verileri_getir()
    bugun = datetime.now().date()
    
    c_ust1, c_ust2 = st.columns([4, 1])
    with c_ust1: st.title("📦 MİDES - Merkezi İkmal ve Depo Sistemi")
    with c_ust2:
        st.write(f"👤 {st.session_state['kullanici']} ({'Yönetici' if st.session_state['rol'] == 'admin' else 'Personel'})")
        if st.button("🚪 Çıkış Yap"):
            st.session_state['giris_yapildi'] = False
            st.rerun()

    sekme1, sekme2, sekme3, sekme6, sekme4, sekme5, sekme7, sekme8 = st.tabs(["📊 Özet", "➕ Ürün Ekle", "🔄 Güncelle", "⚡ Hızlı İşlem", "🪪 Ürün Kartı", "📝 Geçmiş", "📑 Sözleşmeler", "💬 Geri Bildirim"])

    with sekme1:
        st.markdown("### 📋 Depo Uyarıları")
        krt_sayisi = 0
        telegram_raporu = "⚠️ MİDES KRİTİK UYARI RAPORU ⚠️\n\n"
        
        for index, row in df.iterrows():
            urun_adi = str(row.get('Ürün Adı', 'Bilinmeyen Ürün')).strip()
            stok_no = str(row.get('Stok No', '-'))
            miktar_metni = str(row.get('Miktar', '0')).strip()
            birim = str(row.get('Birim', '')).strip()
            
            try:
                skt_metni = str(row.get('SKT', '')).strip()
                if skt_metni and skt_metni != "-" and skt_metni.lower() != "nan":
                    skt = datetime.strptime(skt_metni, '%Y-%m-%d').date()
                    kalan = (skt - bugun).days
                    uyari_baslik = f"{urun_adi} (Stok No: {stok_no} | {miktar_metni} {birim})"
                    
                    if kalan < 0:
                        st.error(f"❌ {uyari_baslik} - TARİHİ GEÇTİ! ({skt_metni})")
                        telegram_raporu += f"{uyari_baslik} - TARİHİ GEÇTİ!\n"
                        krt_sayisi += 1
                    elif 0 <= kalan <= 30:
                        st.warning(f"⚠️ {uyari_baslik} - SKT'ye {kalan} gün kaldı! ({skt_metni})")
                        telegram_raporu += f"⚠️ {uyari_baslik} - {kalan} gün kaldı!\n"
                        krt_sayisi += 1
            except: pass
            
            try:
                kritik_metni = str(row.get('Kritik Stok', '10')).strip()
                if not miktar_metni or miktar_metni.lower() == "nan": miktar_metni = "0"
                if not kritik_metni or kritik_metni.lower() == "nan": kritik_metni = "10"
                
                miktar_val = float(miktar_metni)
                kritik_val = float(kritik_metni)
                
                if miktar_val <= kritik_val:
                    st.error(f"📉 STOK ALARMI: {urun_adi} (Stok No: {stok_no}) bitmek üzere! (Kalan: {int(miktar_val)} {birim})")
                    telegram_raporu += f"📉 ALARM: {urun_adi} (Stok No: {stok_no}) (Kalan: {int(miktar_val)} {birim})\n"
                    krt_sayisi += 1
            except: pass

        if krt_sayisi == 0:
            st.success("✅ Depo durumu çok iyi. Tarihi yaklaşan veya stoğu tükenen ürün yok.")
            telegram_raporu += "✅ Kritik ürün bulunmamaktadır. Depo güvende!"

        if st.button("📲 Telegram'a Rapor Gönder", type="primary"):
            telegram_mesaj_gonder(telegram_raporu)
            st.toast("✅ Gönderildi!")
            
        st.divider()
        st.markdown("### 📦 Stok Numarasına Göre Genel Toplamlar")
        try:
            df['Miktar_Sayi'] = pd.to_numeric(df['Miktar'], errors='coerce').fillna(0)
            toplam_stok_df = df.groupby('Stok No').agg({'Ürün Adı': 'first', 'Miktar_Sayi': 'sum', 'Birim': 'first'}).reset_index()
            toplam_stok_df.rename(columns={'Miktar_Sayi': 'Toplam Miktar'}, inplace=True)
            toplam_stok_df = toplam_stok_df[['Stok No', 'Ürün Adı', 'Toplam Miktar', 'Birim']]
            st.dataframe(toplam_stok_df, use_container_width=True, hide_index=True)
        except: st.info("Toplamlar hesaplanırken hata oluştu.")

        st.markdown("### 🔍 Detaylı Parti Listesi")
        gosterilecek_df = df.drop(columns=['Resim Yolu', 'Miktar_Sayi'], errors='ignore')
        st.dataframe(gosterilecek_df, use_container_width=True, hide_index=True)

    with sekme2:
        st.subheader("Depoya Yeni Ürün Ekle")
        with st.form("urun_ekle_formu"):
            col1, col2 = st.columns(2)
        
            with col1:
                stok_no = st.text_input("Stok Numarası (Barkod)")
                urun_adi = st.text_input("Ürün Adı")
                miktar = st.number_input("Miktar", min_value=0.0, step=1.0)
                birim = st.selectbox("Birim", ["Kg", "Litre", "Adet", "Kutu", "Paket"])
                alim_turu = st.selectbox("Alım Türü", ["Merkezi Alım", "Piyasa Alımı"])
                
            with col2:
                kritik_seviye = st.number_input("Depo Kritik Uyarı Seviyesi", min_value=1, value=20)
                uretim_tarihi = st.date_input("Üretim Tarihi")
                skt = st.date_input("Son Kullanma Tarihi (SKT)")
                
                st.markdown("---")
                sozlesme_no = st.text_input("Sözleşme No (Sadece Piyasa Alımı İçin)")
                sozlesme_tarihi = st.date_input("Sözleşme Tarihi")
                sozlesme_bitis = st.date_input("Sözleşme Bitiş Tarihi")
                sozlesme_kritik = st.number_input("Sözleşme / Yıllık Kritik Sınırı", min_value=0.0, value=20.0, step=1.0)
                
            ekle_btn = st.form_submit_button("Ürünü Kaydet", use_container_width=True)
        
        if ekle_btn:
            if urun_adi and stok_no:
                bugun_tarih = datetime.now().strftime("%Y-%m-%d")
                yeni_id = 1 if df.empty else int(df['ID'].max()) + 1
                
                s_no = sozlesme_no if alim_turu == "Piyasa Al
