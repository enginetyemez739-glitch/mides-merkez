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
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            return response.json()
    except:
        pass
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
    # Malzemeler tablosu olası tüm adlandırma varyasyonlarıyla taranır
    for tbl in ["Malzemeler", "malzemeler", "MALZEMELER", "stok", "Stoklar"]:
        kayitlar = supabase_get(tbl)
        if kayitlar:
            return pd.DataFrame(kayitlar)
    return pd.DataFrame(columns=["ID", "Stok No", "Ürün Adı", "Miktar", "Birim", "Eklenme Tarihi", "SKT", "Üretim Tarihi", "Giriş Tarihi", "Resim Yolu", "Kritik Stok", "Alım Türü", "Sözleşme No", "Sözleşme Tarihi", "Sözleşme Bitiş Tarihi", "Sözleşme Kritik"])

def hareketleri_getir():
    for tbl in ["Hareket_Gecmisi", "hareket_gecmisi", "HareketGecmisi"]:
        kayitlar = supabase_get(tbl)
        if kayitlar:
            return pd.DataFrame(kayitlar).sort_values(by="ID", ascending=False)
    return pd.DataFrame(columns=["ID", "Tarih", "Kullanıcı", "İşlem", "Ürün Adı", "Miktar", "Açıklama"])

def geri_bildirimleri_getir():
    for tbl in ["Geri_Bildirimler", "geri_bildirimler", "GeriBildirimler"]:
        kayitlar = supabase_get(tbl)
        if kayitlar:
            return pd.DataFrame(kayitlar).sort_values(by="ID", ascending=False)
    return pd.DataFrame(columns=["ID", "Tarih", "Kullanıcı", "Tür", "Mesaj"])

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
kullanici_ham = []
aktif_kullanici_tablosu = "Kullanıcılar"
for tbl in ["Kullanıcılar", "kullanicilar", "Users", "users"]:
    res = supabase_get(tbl)
    if res:
        kullanici_ham = res
        aktif_kullanici_tablosu = tbl
        break

df_kullanicilar = pd.DataFrame(kullanici_ham)

if 'giris_yapildi' not in st.session_state:
    st.session_state.update({'giris_yapildi': False, 'kullanici': "", 'rol': "", 'sifre_degistirme_modu': False, 'ilk_giris_uyarisi': False})

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
            supabase_update(aktif_kullanici_tablosu, st.session_state['kullanici'], "Kullanıcı Adi", guncelleme_data)
            
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
                
                if df_kullanicilar.empty:
                    if str(kadi_input).strip() == "Gida_Sorumlusu" and str(sifre_input).strip() == "Efee5307":
                        st.session_state['giris_yapildi'] = True
                        st.session_state['kullanici'] = "Gida_Sorumlusu"
                        st.session_state['rol'] = "admin"
                        st.rerun()
                    else:
                        st.error("❌ 'Kullanıcılar' tablosuna erişilemedi.")
                else:
                    if 'Kullanıcı Adi' in df_kullanicilar.columns and 'Sifre' in df_kullanicilar.columns:
                        kullanici = df_kullanicilar[(df_kullanicilar['Kullanıcı Adi'].astype(str).str.strip() == str(kadi_input).strip()) & (df_kullanicilar['Sifre'].astype(str).str.strip() == str(girilen_hash).strip())]
                    else:
                        kullanici = pd.DataFrame()

                    if not kullanici.empty:
                        yetki = kullanici['Yetki'].values[0] if 'Yetki' in kullanici.columns else "Yönetici"
                        ilk_giris = str(kullanici['İlk Giriş'].values[0]).strip().lower() if 'İlk Giriş' in kullanici.columns else "hayır"
                        
                        st.session_state['kullanici'] = kadi_input
                        st.session_state['rol'] = "admin" if str(yetki).strip().lower() in ["yönetici", "yonetici", "admin"] else "personel"
                        
                        if 'Telegram Token' in kullanici.columns and not pd.isna(kullanici['Telegram Token'].values[0]):
                            st.session_state['telegram_token'] = str(kullanici['Telegram Token'].values[0])
                        if 'Telegram Chat ID' in kullanici.columns and not pd.isna(kullanici['Telegram Chat ID'].values[0]):
                            st.session_state['telegram_chat_id'] = str(kullanici['Telegram Chat ID'].values[0])

                        if ilk_giris == "evet":
                            st.session_state['sifre_degistirme_modu'] = True
                            st.session_state['ilk_giris_uyarisi'] = True
                            st.rerun()
                        else:
                            son_gun_val = kullanici['Son Güncelleme'].values[0] if 'Son Güncelleme' in kullanici.columns else None
                            if pd.isna(son_gun_val) or not son_gun_val:
                                st.session_state['giris_yapildi'] = True
                                st.rerun()
                            else:
                                son_guncelleme = pd.to_datetime(son_gun_val, errors='coerce')
                                gecen_gun = (datetime.today() - son_guncelleme).days if not pd.isna(son_guncelleme) else 0
                                if gecen_gun >= 90:
                                    st.session_state['sifre_degistirme_modu'] = True
                                    st.rerun()
                                else:
                                    st.session_state['giris_yapildi'] = True
                                    st.rerun()
                    elif str(kadi_input).strip() == "Gida_Sorumlusu" and str(sifre_input).strip() == "Efee5307":
                        st.session_state['giris_yapildi'] = True
                        st.session_state['kullanici'] = "Gida_Sorumlusu"
                        st.session_state['rol'] = "admin"
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
                    skt = datetime.strptime(skt_metni, '%Y-%m-%d
